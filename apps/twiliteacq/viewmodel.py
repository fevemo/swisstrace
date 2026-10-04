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
    # (t, coincidences) arrays of a loaded calibration run.
    calibrationRunLoaded = pyqtSignal(object, object)
    # A computed calibration factor.
    calibrationComputed = pyqtSignal(float)
    # The settings of the last session.
    stateRestored = pyqtSignal(dict)

    def __init__(self, model, logger):
        super().__init__()
        self.model = model
        self.logger = logger
        self.showCorrected = False
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
        self.traceUpdated.emit(self.model.getTrace(corrected=self.showCorrected))
        self.statsUpdated.emit(stats)

    def setShowCorrected(self, corrected):
        self.showCorrected = corrected
        self._emitTrace(force=True)

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

    def loadCalibrationRun(self, path):
        try:
            t, coincidences = self.model.loadCalibrationRun(path)
        except (OSError, ValueError) as error:
            self.errorOccurred.emit(f"Cannot load the calibration run: {error}")
            return
        self.calibrationRunLoaded.emit(t, coincidences)

    def isotopeTable(self):
        return self.model.isotopeTable()

    def calibrationRunStart(self):
        return self.model.calibrationRunStart() if self.model.calibrationRun is not None else None

    def computeCalibration(self, backgroundWindow, plateauWindow, activityPet, referenceTime):
        if self.model.calibrationRun is None:
            self.errorOccurred.emit("Load a calibration run first.")
            return
        if activityPet <= 0:
            self.errorOccurred.emit("Enter the phantom activity measured by the PET.")
            return
        try:
            cf = self.model.computeCalibration(backgroundWindow, plateauWindow, activityPet, referenceTime)
        except ValueError as error:
            self.errorOccurred.emit(f"Cannot compute the calibration factor: {error}")
            return
        self.lastCalibrationFactor = cf
        self.calibrationComputed.emit(cf)

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

    def setExportFile(self, path):
        self.exportFile = path

    def defaultAddress(self):
        return self.model.host, self.model.port, self.model.simulate

    def dataDir(self):
        return self.model.dataDir

    def export(self, kind, targetPath):
        if self.exportFile is None:
            self.errorOccurred.emit("Choose an acquisition to export first.")
            return
        try:
            self.model.export(kind, self.exportFile, targetPath)
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
