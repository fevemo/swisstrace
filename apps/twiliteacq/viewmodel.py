import os

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from einstudio.tools.threads import runFuncInThread


class ViewModel(QObject):
    """Runs the Model's blocking calls in worker threads and turns their results into signals.

    Every public method checks its prerequisites first (connected? already running?)
    and reports a problem through ``errorOccurred`` instead of raising. The plot gets
    at most ``PLOT_UPDATES_PER_S`` updates a second, whatever the device's report rate.
    """

    PLOT_UPDATES_PER_S = 10
    # How often to check whether the idle connection needs a keepalive.
    KEEPALIVE_CHECK_MS = 2000

    # True when connected, False when disconnected.
    connectionChanged = pyqtSignal(bool)
    # True when an acquisition starts, False when it ends.
    acquisitionChanged = pyqtSignal(bool)
    # (status, text): status is one of disconnected, connecting, connected, acquiring, error.
    statusChanged = pyqtSignal(str, str)
    # The firmware banner after connecting.
    bannerChanged = pyqtSignal(str)
    # The run so far: {"t", "singles1", "singles2", "coincidences"} arrays, NaN where the connection was lost.
    traceUpdated = pyqtSignal(object)
    # {"elapsed_s", "samples", "latest", "losses"}.
    statsUpdated = pyqtSignal(object)
    # (kind, text) of every event stored with the acquisition.
    eventRecorded = pyqtSignal(str, str)
    # (t, text) of a user mark, t in seconds from the acquisition start.
    markAdded = pyqtSignal(float, str)
    # A message for the user.
    errorOccurred = pyqtSignal(str)
    # Path of the file of a finished acquisition.
    acquisitionSaved = pyqtSignal(str)
    # Interrupted acquisition files found at startup.
    partialFilesFound = pyqtSignal(list)
    # (t, coincidences) arrays and the file name of a loaded calibration run.
    calibrationRunLoaded = pyqtSignal(object, object, str)
    # (CF, "") when it can be computed, else (None, why not).
    calibrationComputed = pyqtSignal(object, str)
    # The data loaded on the Correction page: {"name", "unsaved", "t", "coincidences",
    # "interpolated", "start"}; "unsaved" is True while there are edits not saved yet.
    correctionDataLoaded = pyqtSignal(object)
    # The same, after an edit (cut, resample) or after saving the edited data.
    correctionDataEdited = pyqtSignal(object)
    # (t from the PET start, kBq/cc, background) of the loaded data, or None while it cannot be corrected.
    correctionComputed = pyqtSignal(object)
    # The settings of the last session.
    stateRestored = pyqtSignal(dict)

    def __init__(self, model, logger):
        super().__init__()
        self.model = model
        self.logger = logger
        self.exportFile = None
        self.lastCalibrationFactor = None
        self._connecting = False
        self._acquisitionThread = None
        self._lastSampleCount = -1
        self._plotTimer = QTimer()
        self._plotTimer.setInterval(1000 // self.PLOT_UPDATES_PER_S)
        self._plotTimer.timeout.connect(self._emitTrace)
        self._keepingAlive = False
        self._keepAliveTimer = QTimer()
        self._keepAliveTimer.setInterval(self.KEEPALIVE_CHECK_MS)
        self._keepAliveTimer.timeout.connect(self._keepAlive)

    ###########################################################################
    # Connection                                                              #
    ###########################################################################

    def connect(self, host, port):
        if self._connecting or self.model.isConnected():
            return
        self._connecting = True
        self.statusChanged.emit("connecting", "Connecting")
        runFuncInThread(self.model.connect, host, port, callbackFunc=self._onConnected)

    def _onConnected(self, resultError):
        banner, error = resultError
        self._connecting = False
        if error is not None:
            self._report(f"Cannot connect: {error}")
            self.connectionChanged.emit(False)
            return
        self.bannerChanged.emit(banner)
        self.connectionChanged.emit(True)
        self.statusChanged.emit("connected", "Connected")
        self._keepAliveTimer.start()

    def disconnect(self):
        if self._acquisitionThread is not None:
            self.errorOccurred.emit("Stop the acquisition before disconnecting.")
            return
        self._keepAliveTimer.stop()
        self.model.disconnect()
        self.connectionChanged.emit(False)
        self.statusChanged.emit("disconnected", "Disconnected")

    def isConnected(self):
        return self.model.isConnected()

    def _keepAlive(self):
        # The twilite drops a connection that stays idle for about 19 s.
        if self._keepingAlive or self._acquisitionThread is not None:
            return
        if not self.model.isConnected():
            self._keepAliveTimer.stop()
            return
        self._keepingAlive = True
        runFuncInThread(self.model.keepAlive, callbackFunc=self._onKeepAlive)

    def _onKeepAlive(self, resultError):
        alive, error = resultError
        self._keepingAlive = False
        if error is None and alive:
            return
        self._keepAliveTimer.stop()
        if self._acquisitionThread is not None:
            return
        self._report(f"The twilite closed the connection{f': {error}' if error else ''}. Connect again.")
        self.connectionChanged.emit(False)

    ###########################################################################
    # Acquisition                                                             #
    ###########################################################################

    def startAcquisition(self, qrate, endAfter_s=None):
        if not self.model.isConnected():
            self.errorOccurred.emit("Connect to the twilite first.")
            return
        if self._acquisitionThread is not None:
            self.errorOccurred.emit("An acquisition is already running.")
            return
        _, self._acquisitionThread = runFuncInThread(
            self.model.acquire, qrate, endAfter_s, onEvent=self._onModelEvent,
            callbackFunc=self._onAcquisitionFinished,
        )
        self._lastSampleCount = -1
        self._plotTimer.start()
        self.acquisitionChanged.emit(True)
        self.statusChanged.emit("acquiring", "Acquiring")

    def stopAcquisition(self):
        if self._acquisitionThread is not None:
            self.model.requestStop()

    def isAcquiring(self):
        return self._acquisitionThread is not None

    def markEvent(self, text):
        if self._acquisitionThread is None:
            self.errorOccurred.emit("Marks can only be set during an acquisition.")
            return
        try:
            t = self.model.markEvent(text)
        except RuntimeError as error:
            self.errorOccurred.emit(str(error))
            return
        self.eventRecorded.emit("mark", f"{text or 'mark'} at {t:.1f} s")
        self.markAdded.emit(t, text)

    def _onModelEvent(self, kind, text):
        # Called in the acquisition thread; emitting from there is safe.
        self.eventRecorded.emit(kind, text)

    def _onAcquisitionFinished(self, resultError):
        _, error = resultError
        self._acquisitionThread = None
        self._plotTimer.stop()
        self._emitTrace(force=True)
        self.acquisitionChanged.emit(False)
        # The Model closes the file even when the acquisition failed.
        if self.model.lastFile is not None:
            self.exportFile = str(self.model.lastFile)
            self.acquisitionSaved.emit(self.exportFile)
        if error is not None:
            self._report(f"Acquisition ended: {error}")
            if not self.model.isConnected():
                self.connectionChanged.emit(False)
            return
        self.statusChanged.emit("connected", "Connected")

    def _emitTrace(self, force=False):
        stats = self.model.getStats()
        if not force and stats["samples"] == self._lastSampleCount:
            return
        self._lastSampleCount = stats["samples"]
        self.traceUpdated.emit(self.model.getTrace())
        self.statsUpdated.emit(stats)

    ###########################################################################
    # Correction and calibration                                              #
    ###########################################################################

    def setCorrection(self, isotopeName, petStart, fixedBackground, calibrationFactor,
                      customHalfLife_s=None, customBranchingRatio=None):
        try:
            self.model.setCorrection(isotopeName, petStart, fixedBackground, calibrationFactor,
                                     customHalfLife_s, customBranchingRatio)
        except (KeyError, ValueError) as error:
            self.errorOccurred.emit(f"Invalid correction: {error}")
            return
        self._emitTrace(force=True)
        self._computeCorrection()

    def loadCorrectionData(self, path=None):
        """Load an acquisition file to correct; without ``path``, the current acquisition's."""
        path = path or self.model.currentFile()
        if path is None:
            self.errorOccurred.emit("No acquisition yet: run one or load a file.")
            return
        try:
            self.model.loadCorrectionData(path)
        except (OSError, ValueError) as error:
            self.errorOccurred.emit(f"Cannot load the data: {error}")
            return
        self.correctionDataLoaded.emit(self._correctionData())
        self._computeCorrection()

    def _correctionData(self):
        return {"name": self.model.correctionData.path.name, "unsaved": self.model.hasUnsavedEdits(),
                **self.model.correctionArrays()}

    def measuredBackground(self, petStart):
        """Mean rate before ``petStart`` of the loaded data, as "Mean before PET" would use; or None."""
        return self.model.measuredBackground(petStart)

    def correctionSource(self):
        """Path the loaded correction data was read from, or None."""
        data = self.model.correctionData
        return str(data.path) if data is not None else None

    def _computeCorrection(self):
        if self.model.correctionData is None:
            return
        try:
            result = self.model.correctData()
        except ValueError as error:
            self.errorOccurred.emit(f"Cannot correct the data: {error}")
            result = None
        self.correctionComputed.emit(result)

    def loadCalibrationRun(self, path=None):
        """Load an acquisition file as calibration run; without ``path``, the current acquisition's."""
        path = path or self.model.currentFile()
        if path is None:
            self.errorOccurred.emit("No acquisition yet: run one or load a file.")
            return
        try:
            t, coincidences = self.model.loadCalibrationRun(path)
        except (OSError, ValueError) as error:
            self.errorOccurred.emit(f"Cannot load the calibration run: {error}")
            return
        self.calibrationRunLoaded.emit(t, coincidences, os.path.basename(path))

    def isotopeTable(self):
        return self.model.isotopeTable()

    def calibrationRunStart(self):
        return self.model.calibrationRunStart() if self.model.calibrationRun is not None else None

    def computeCalibration(self, backgroundWindow, plateauWindow, activityPet, referenceTime, isotopeName,
                           customHalfLife_s=None, customBranchingRatio=None):
        """Compute CF and emit ``calibrationComputed``, with the reason instead while it cannot be.

        Called on every change of the inputs, so a missing input is not an error.
        ``referenceTime`` is None while the field is empty or invalid.
        """
        cf, reason = None, ""
        if self.model.calibrationRun is None:
            reason = "Load a calibration run"
        elif referenceTime is None:
            reason = "Enter the PET reference time (HH:MM:SS)"
        elif activityPet <= 0:
            reason = "Enter the PET activity"
        else:
            try:
                isotope = self.model.makeIsotope(isotopeName, customHalfLife_s, customBranchingRatio)
                cf = self.model.computeCalibration(backgroundWindow, plateauWindow, activityPet, referenceTime,
                                                   isotope)
            except KeyError as error:
                reason = f"Unknown isotope {error}"
            except ValueError as error:
                reason = str(error)
        self.lastCalibrationFactor = cf
        self.calibrationComputed.emit(cf, reason)

    ###########################################################################
    # Editing the correction data                                             #
    ###########################################################################

    def cutPreview(self, start, end, nAverage):
        """``((t, coincidences), "")`` of the line a cut would draw, or ``(None, why not)``."""
        try:
            return self.model.cutPreview(start, end, nAverage), ""
        except ValueError as error:
            return None, str(error)

    def applyCut(self, start, end, nAverage):
        """Cut ``[start, end]`` (PC times) out of the correction data; False if it cannot be."""
        return self._edit(self.model.cut, start, end, nAverage)

    def samplingSections(self):
        """``[(start, end, period)]`` of the correction data, PC times; ``[]`` without data."""
        try:
            return self.model.samplingSections()
        except ValueError:
            return []

    def resamplePreview(self, sections):
        """The preview of ``Model.resamplePreview``, or None without data."""
        try:
            return self.model.resamplePreview(sections)
        except ValueError:
            return None

    def applyResample(self, sections):
        """Resample the correction data; ``sections`` is ``[(start, end, period)]``; False if it cannot be."""
        return self._edit(self.model.resample, sections)

    def hasUnsavedEdits(self):
        return self.model.hasUnsavedEdits()

    def saveEditedData(self, path):
        """Save the edited data as a new acquisition file; False if it could not be."""
        try:
            self.model.saveEditedData(path)
        except (OSError, ValueError) as error:
            self.errorOccurred.emit(f"Cannot save the edited data: {error}")
            return False
        self.correctionDataEdited.emit(self._correctionData())
        return True

    def _edit(self, func, *args):
        try:
            func(*args)
        except ValueError as error:
            self.errorOccurred.emit(str(error))
            return False
        self.correctionDataEdited.emit(self._correctionData())
        self._computeCorrection()
        return True

    ###########################################################################
    # Files                                                                   #
    ###########################################################################

    def checkPartialFiles(self):
        paths = self.model.findPartialFiles()
        if paths:
            self.partialFilesFound.emit(paths)

    def recoverFiles(self, paths):
        try:
            for path in self.model.recoverFiles(paths):
                self.exportFile = path
                self.acquisitionSaved.emit(path)
        except OSError as error:
            self.errorOccurred.emit(f"Recovery failed: {error}")

    def defaultAddress(self):
        return self.model.host, self.model.port, self.model.simulate

    def dataDir(self):
        return self.model.dataDir

    def export(self, kind, targetPath):
        if self.exportFile is None:
            self.errorOccurred.emit("Run an acquisition first.")
            return
        try:
            self.model.export(kind, self.exportFile, targetPath)
        except (OSError, ValueError) as error:
            self.errorOccurred.emit(f"Export failed: {error}")

    def exportCorrected(self, kind, targetPath):
        if self.model.correctionData is None:
            self.errorOccurred.emit("Load the data to correct first.")
            return
        try:
            self.model.exportCorrected(kind, targetPath)
        except (OSError, ValueError) as error:
            self.errorOccurred.emit(f"Export failed: {error}")

    ###########################################################################
    # Settings and exit                                                       #
    ###########################################################################

    def loadState(self):
        try:
            state = self.model.loadState()
        except (OSError, ValueError) as error:
            self.logger.warning(f"Saved settings not restored: {error}")
            return
        if state:
            self.stateRestored.emit(state)

    def saveState(self, state):
        try:
            self.model.saveState(state)
        except OSError as error:
            self.logger.warning(f"Settings not saved: {error}")

    def shutdown(self):
        """Stop the acquisition, wait for its thread, disconnect; for the window's close."""
        thread = self._acquisitionThread
        if thread is not None:
            self.model.requestStop()
            thread.wait(int((self.model.timeout_s + 2) * 1000))
        self._plotTimer.stop()
        self._keepAliveTimer.stop()
        self.model.shutdown()

    def _report(self, message):
        self.logger.error(message)
        self.statusChanged.emit("error", "Error")
        self.errorOccurred.emit(message)
