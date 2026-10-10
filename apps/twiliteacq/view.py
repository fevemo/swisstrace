import os
import time
from datetime import datetime, timedelta

import pyqtgraph as pg
from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtWidgets import QFileDialog
from qfluentwidgets import InfoBar, InfoBarPosition, MessageBox

from einstudio.tools.einview import EINview
from einstudio.tools.styleengine import StyleEngine
from einstudio.widgets import (
    EINbodyLabel, EINbutton, EINcaptionLabel, EINcheckBox, EINdocWidget, EINdoubleSpinBox, EINdropDown,
    EINlineEdit, EINlogDisplayWidget, EINoptionRow, EINplotWidget, EINspinBox, EINstatusLight, EINtitleLabel,
)

CUSTOM_ISOTOPE = "Custom"
# PET times are entered without a date: the date is the one of the data they refer to.
TIME_FORMAT = "%H:%M:%S"
# ViewModel status -> status light state.
STATUS_LIGHTS = {"disconnected": "off", "connecting": "processing", "connected": "ready",
                 "acquiring": "running", "error": "error"}
# Gap between a plot's legend and its top-left corner, so the legend's border is not clipped.
LEGEND_INSET_PX = 10
# Background windows on the Calibration and Correction plots.
BACKGROUND_BRUSH = (128, 128, 128, 50)
# Save dialogs: (export kind, file filter, suffix added to the acquisition's name).
RAW_FORMATS = [("csv", "CSV (*.csv)", "_raw.csv"), ("crv", "Curve (*.crv)", ".crv")]
EVENT_FORMATS = [("events", "CSV (*.csv)", "_events.csv")]
CORRECTED_FORMATS = [("bld", "PMOD blood (*.bld)", ".bld"), ("tac", "PMOD TAC (*.tac)", ".tac"),
                     ("csv", "CSV with corrected values (*.csv)", "_corrected.csv")]


class View(EINview):
    """Wires the controls to the ViewModel and its signals to the plots and labels.

    Settings are restored from the last session at startup and saved on close; closing
    the window stops a running acquisition and disconnects first.
    """

    def makeWidgetsList(self):
        self.expectedWidgets = [
            # Acquisition page
            ('hostEdit',              EINlineEdit),
            ('portSpin',              EINspinBox),
            ('statusLight',           EINstatusLight),
            ('connectButton',         EINbutton),
            ('sampleRateDropdown',    EINdropDown),
            ('endModeDropdown',       EINdropDown),
            ('durationSpin',          EINdoubleSpinBox),
            ('runButton',             EINbutton),
            ('elapsedLabel',          EINbodyLabel),
            ('markEdit',              EINlineEdit),
            ('markButton',            EINbutton),
            ('showCoincidencesCheck', EINcheckBox),
            ('showSingles1Check',     EINcheckBox),
            ('showSingles2Check',     EINcheckBox),
            ('saveRawButton',         EINbutton),
            ('saveEventsButton',      EINbutton),
            ('plotWidget',            EINplotWidget),
            # Correction page
            ('isotopeDropdown',       EINdropDown),
            ('halfLifeSpin',          EINdoubleSpinBox),
            ('branchingSpin',         EINdoubleSpinBox),
            ('petStartEdit',          EINlineEdit),
            ('petSelectButton',       EINbutton),
            ('backgroundModeDropdown', EINdropDown),
            ('backgroundSpin',        EINdoubleSpinBox),
            ('cfSpin',                EINdoubleSpinBox),
            ('applyCorrectionButton', EINbutton),
            ('saveCorrectedButton',   EINbutton),
            ('correctionFileLabel',   EINcaptionLabel),
            ('useCurrentDataButton',  EINbutton),
            ('loadCorrectionDataButton', EINbutton),
            ('correctionPlot',        EINplotWidget),
            # Calibration page
            ('calibrationFileLabel',  EINcaptionLabel),
            ('useCurrentCalibrationButton', EINbutton),
            ('loadCalibrationButton', EINbutton),
            ('backgroundWindowLabel', EINbodyLabel),
            ('plateauWindowLabel',    EINbodyLabel),
            ('calibrationReferenceEdit', EINlineEdit),
            ('activitySpin',          EINdoubleSpinBox),
            ('calibrationIsotopeLabel', EINbodyLabel),
            ('calibrationResultRow',  EINoptionRow),
            ('calibrationResultLabel', EINtitleLabel),
            ('applyCalibrationButton', EINbutton),
            ('calibrationPlot',       EINplotWidget),
            # Log page
            ('logDisplayWidget',      EINlogDisplayWidget),
            ('docView',               EINdocWidget),
        ]

    ###############################################################################
    # Setup                                                                       #
    ###############################################################################

    def configure(self):
        w = self.widgets
        self.setMinimumSize(self.config.mainWindowMinSizeX, self.config.mainWindowMinSizeY)
        self.setWindowTitle(self.config.mainWindowTitle)

        host, port, _ = self.viewModel.defaultAddress()
        w.hostEdit.setText(host)
        w.portSpin.setValue(port)
        w.sampleRateDropdown.setCurrentText("1")
        w.durationSpin.setValue(60.0)
        w.durationSpin.setEnabled(False)
        w.runButton.setEnabled(False)
        w.markButton.setEnabled(False)
        w.saveRawButton.setEnabled(False)
        w.saveEventsButton.setEnabled(False)
        for check in (w.showCoincidencesCheck, w.showSingles1Check, w.showSingles2Check):
            check.setChecked(True)

        self.handles.isotopes = self.viewModel.isotopeTable()
        w.isotopeDropdown.addItems([*self.handles.isotopes, CUSTOM_ISOTOPE])
        self._onIsotopeChanged()
        w.backgroundSpin.setEnabled(False)
        w.cfSpin.setValue(1.0)

        # Live plot: one curve per series; NaN points (lost connections) break the line.
        plot = w.plotWidget
        self.handles.coincidenceCurve = plot.plot([], [], connect="finite")
        self.handles.singles1Curve = plot.plot([], [], connect="finite")
        self.handles.singles2Curve = plot.plot([], [], connect="finite")
        _toTopLeft(plot.addLegend(["Coincidences", "Singles 1", "Singles 2"]))
        plot.showGrid(x=True, y=True)
        self.handles.markLines = []

        # Calibration plot with the two windows to drag.
        calPlot = w.calibrationPlot
        self.handles.calibrationCurve = calPlot.plot([], [], connect="finite")
        self.handles.backgroundRegion = pg.LinearRegionItem(brush=pg.mkBrush(*BACKGROUND_BRUSH))
        self.handles.plateauRegion = pg.LinearRegionItem(brush=pg.mkBrush(0, 170, 150, 50))
        for region in (self.handles.backgroundRegion, self.handles.plateauRegion):
            region.setVisible(False)
            calPlot.addItem(region)
        calPlot.showGrid(x=True, y=True)
        self._onCalibrationComputed(None, "Load a calibration run")

        self._makeCorrectionPlot()
        self._refreshCorrectionPlot()  # shows "-" as the measured background until data is loaded

        indexFile = os.path.join(self.configManager.mainConfig.docPath, "index.html")
        if os.path.isfile(indexFile):
            w.docView.updateHTML(QUrl.fromLocalFile(os.path.abspath(indexFile)).toString())

        # After bindSignals(), so the signals these emit are connected.
        QTimer.singleShot(0, self.viewModel.loadState)
        QTimer.singleShot(0, self.viewModel.checkPartialFiles)

    def bindWidgetsActions(self):
        w = self.widgets
        w.connectButton.clicked.connect(self._onConnectClicked)
        w.runButton.clicked.connect(self._onRunClicked)
        w.endModeDropdown.currentTextChanged.connect(lambda text: w.durationSpin.setEnabled(text == "Time"))
        w.markButton.clicked.connect(self._onMark)
        w.markEdit.returnPressed.connect(self._onMark)
        for check in (w.showCoincidencesCheck, w.showSingles1Check, w.showSingles2Check):
            check.stateChanged.connect(self._updateCurveVisibility)

        w.isotopeDropdown.currentTextChanged.connect(self._onIsotopeChanged)
        w.petSelectButton.clicked.connect(self._onSelectPetStart)
        w.correctionPlot.scene().sigMouseClicked.connect(self._onCorrectionPlotClicked)
        # Before the edited handler below, so the field is updated when the plot is redrawn.
        w.backgroundModeDropdown.currentIndexChanged.connect(self._onBackgroundModeChanged)
        w.backgroundSpin.valueChanged.connect(self._onBackgroundValueChanged)
        w.applyCorrectionButton.clicked.connect(self._applyCorrection)
        w.saveRawButton.clicked.connect(lambda: self._onSaveRaw("Save raw data", RAW_FORMATS))
        w.saveEventsButton.clicked.connect(lambda: self._onSaveRaw("Save events", EVENT_FORMATS))
        w.saveCorrectedButton.clicked.connect(self._onSaveCorrected)
        w.useCurrentDataButton.clicked.connect(lambda: self.viewModel.loadCorrectionData())
        w.loadCorrectionDataButton.clicked.connect(self._onLoadCorrectionData)
        # Any change to the settings makes the corrected curve stale until the next Apply.
        for signal in (w.isotopeDropdown.currentTextChanged, w.halfLifeSpin.valueChanged,
                       w.branchingSpin.valueChanged, w.petStartEdit.textChanged,
                       w.backgroundModeDropdown.currentIndexChanged, w.backgroundSpin.valueChanged,
                       w.cfSpin.valueChanged):
            signal.connect(self._onCorrectionEdited)

        w.useCurrentCalibrationButton.clicked.connect(lambda: self.viewModel.loadCalibrationRun())
        w.loadCalibrationButton.clicked.connect(self._onLoadCalibration)
        w.applyCalibrationButton.clicked.connect(self._onApplyCalibration)
        self.handles.backgroundRegion.sigRegionChanged.connect(self._updateWindowLabels)
        self.handles.plateauRegion.sigRegionChanged.connect(self._updateWindowLabels)
        # The factor follows every input, the isotope included (as set on the Correction page).
        for signal in (self.handles.backgroundRegion.sigRegionChanged, self.handles.plateauRegion.sigRegionChanged,
                       w.calibrationReferenceEdit.textChanged, w.activitySpin.valueChanged,
                       w.isotopeDropdown.currentTextChanged, w.halfLifeSpin.valueChanged,
                       w.branchingSpin.valueChanged):
            signal.connect(self._computeCalibration)

    def bindSignals(self):
        vm = self.viewModel
        vm.connectionChanged.connect(self._onConnectionChanged)
        vm.acquisitionChanged.connect(self._onAcquisitionChanged)
        vm.statusChanged.connect(self._onStatusChanged)
        vm.traceUpdated.connect(self._onTraceUpdated)
        vm.statsUpdated.connect(self._onStatsUpdated)
        vm.markAdded.connect(self._onMarkAdded)
        vm.eventRecorded.connect(lambda kind, text: self._notify("warning", "Connection", text)
                                 if kind == "connection" else None)
        vm.errorOccurred.connect(lambda message: self._notify("error", "Error", message))
        vm.acquisitionSaved.connect(self._onAcquisitionSaved)
        vm.partialFilesFound.connect(self._onPartialFilesFound)
        vm.calibrationRunLoaded.connect(self._onCalibrationRunLoaded)
        vm.correctionDataLoaded.connect(self._onCorrectionDataLoaded)
        vm.correctionComputed.connect(self._onCorrectionComputed)
        vm.calibrationComputed.connect(self._onCalibrationComputed)
        vm.stateRestored.connect(self._onStateRestored)
        self.logger.onLogUpdate(self.widgets.logDisplayWidget.updateLog)

    ###############################################################################
    # Connection and acquisition                                                  #
    ###############################################################################

    def _onConnectClicked(self):
        if self.viewModel.isConnected():
            self.viewModel.disconnect()
        else:
            self.viewModel.connect(self.widgets.hostEdit.text().strip(), self.widgets.portSpin.value())

    def _onConnectionChanged(self, connected):
        w = self.widgets
        w.connectButton.setText("Disconnect" if connected else "Connect")
        w.hostEdit.setEnabled(not connected)
        w.portSpin.setEnabled(not connected)
        w.runButton.setEnabled(connected or self.viewModel.isAcquiring())
        if not connected:
            self._onStatusChanged("disconnected", "Disconnected")

    def _onStatusChanged(self, status, text):
        self.widgets.statusLight.setStatus(STATUS_LIGHTS[status], text)

    def _onRunClicked(self):
        if self.viewModel.isAcquiring():
            self.viewModel.stopAcquisition()
            return
        w = self.widgets
        endAfter_s = w.durationSpin.value() * 60 if w.endModeDropdown.currentText() == "Time" else None
        for line in self.handles.markLines:
            w.plotWidget.removeItem(line)
        self.handles.markLines = []
        self.viewModel.startAcquisition(self._qrate(), endAfter_s)

    def _onAcquisitionChanged(self, running):
        w = self.widgets
        w.runButton.setText("Stop" if running else "Start")
        w.runButton.setEnabled(running or self.viewModel.isConnected())
        w.markButton.setEnabled(running)
        hasFile = self.viewModel.exportFile is not None
        w.saveRawButton.setEnabled(not running and hasFile)
        w.saveEventsButton.setEnabled(not running and hasFile)
        w.connectButton.setEnabled(not running)
        w.sampleRateDropdown.setEnabled(not running)
        w.endModeDropdown.setEnabled(not running)

    def _qrate(self):
        """The device's ``qrate n`` for the chosen sample rate: one report every n x 100 ms."""
        return round(float(self.widgets.sampleRateDropdown.currentText()) * 10)

    def _onMark(self):
        if not self.viewModel.isAcquiring():
            return
        self.viewModel.markEvent(self.widgets.markEdit.text().strip())
        self.widgets.markEdit.clear()

    def _onMarkAdded(self, t, text):
        line = pg.InfiniteLine(pos=t, angle=90, movable=False, label=text or "mark",
                               labelOpts={"position": 0.9, "rotateAxis": (1, 0)})
        self.widgets.plotWidget.addItem(line)
        self.handles.markLines.append(line)

    def _onTraceUpdated(self, trace):
        t = trace["t"]
        self.handles.coincidenceCurve.setData(t, trace["coincidences"])
        self.handles.singles1Curve.setData(t, trace["singles1"])
        self.handles.singles2Curve.setData(t, trace["singles2"])

    def _onStatsUpdated(self, stats):
        elapsed = int(stats["elapsed_s"])
        self.widgets.elapsedLabel.setText(f"{elapsed // 3600}:{elapsed // 60 % 60:02d}:{elapsed % 60:02d}")

    def _updateCurveVisibility(self):
        w = self.widgets
        self.handles.coincidenceCurve.setVisible(w.showCoincidencesCheck.isChecked())
        self.handles.singles1Curve.setVisible(w.showSingles1Check.isChecked())
        self.handles.singles2Curve.setVisible(w.showSingles2Check.isChecked())

    def _onSaveRaw(self, title, formats):
        source = self.viewModel.exportFile
        if source is None:
            self._notify("error", "Nothing to save", "Run an acquisition first.")
            return
        target, kind = self._askSavePath(title, source, formats)
        if target:
            self.viewModel.export(kind, target)

    ###############################################################################
    # Correction                                                                  #
    ###############################################################################

    def _makeCorrectionPlot(self):
        """Raw coincidences on the left axis, corrected values on their own axis on the right."""
        plot = self.widgets.correctionPlot
        item = plot.plotItem
        self.handles.rawCurve = plot.plot([], [], connect="finite")
        plot.showGrid(x=True, y=True)

        correctedView = pg.ViewBox()
        item.showAxis("right")
        item.scene().addItem(correctedView)
        item.getAxis("right").linkToView(correctedView)
        item.getAxis("right").setLabel("Activity (kBq/cc)")
        correctedView.setXLink(item)

        def syncViews():
            correctedView.setGeometry(item.vb.sceneBoundingRect())
            correctedView.linkedViewChanged(item.vb, correctedView.XAxis)

        item.vb.sigResized.connect(syncViews)
        self.handles.correctedCurve = pg.PlotDataItem(
            [], [], connect="finite", antialias=plot.antialias,
            pen=pg.mkPen(StyleEngine.token("c_plot_curve_2"), width=StyleEngine.px("plot_line_width_px")))
        correctedView.addItem(self.handles.correctedCurve)
        # Only the main view sets the x range (shared through the link), never the corrected curve.
        correctedView.enableAutoRange(axis=pg.ViewBox.XAxis, enable=False)
        self.handles.correctedView = correctedView
        _toTopLeft(plot.addLegend(["Coincidences"])).addItem(self.handles.correctedCurve, "Corrected")

        self.handles.petStartLine = pg.InfiniteLine(pos=0, angle=90, movable=False, label="PET start",
                                                    labelOpts={"position": 0.9, "rotateAxis": (1, 0)})
        self.handles.correctionBackgroundRegion = pg.LinearRegionItem(brush=pg.mkBrush(*BACKGROUND_BRUSH),
                                                                      movable=False)
        self.handles.backgroundLine = pg.InfiniteLine(angle=0, movable=False, label="Background",
                                                      pen=pg.mkPen(StyleEngine.token("c_plot_curve_3"),
                                                                   style=Qt.PenStyle.DashLine),
                                                      labelOpts={"position": 0.12})
        for overlay in (self.handles.petStartLine, self.handles.correctionBackgroundRegion,
                        self.handles.backgroundLine):
            overlay.setVisible(False)
            plot.addItem(overlay)
        self.handles.correctionData = None
        # Wall time of x = 0 on the plot: the PET start, or the acquisition start without one.
        self.handles.correctionZero = None
        self.handles.selectingPetStart = False
        # The "Fixed value" background, kept while the field shows the measured mean.
        self.handles.fixedBackground = 0.0

    def _onLoadCorrectionData(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load an acquisition", self.viewModel.dataDir(),
                                              "Acquisitions (*.csv)")
        if path:
            self.viewModel.loadCorrectionData(path)

    def _onCorrectionDataLoaded(self, data):
        self.handles.correctionData = data
        self.handles.correctionZero = None  # show the whole measurement
        self.widgets.correctionFileLabel.setText(data["name"])
        self._refreshCorrectionPlot()
        # The PET start's date comes from the data: apply again with the new data's date.
        self._applyCorrection()

    def _onCorrectionComputed(self, result):
        if result is None:
            self.handles.correctedCurve.setData([], [])
            return
        t, activity, _ = result
        self.handles.correctedCurve.setData(t, activity)

    def _onCorrectionEdited(self, *_):
        self.handles.correctedCurve.setData([], [])
        self._refreshCorrectionPlot()

    def _refreshCorrectionPlot(self):
        """Redraw the raw curve and the overlays from the settings as they are on screen.

        Time 0 is the PET start, or the acquisition start while the PET start is not set.
        """
        w = self.widgets
        petStart = self._petStart()
        self._showMeasuredBackground(petStart)
        data = self.handles.correctionData
        if data is None:
            return
        zero = petStart if petStart is not None else data["start"]
        x = data["t_wall"] - zero
        self.handles.rawCurve.setData(x, data["coincidences"])
        if zero != self.handles.correctionZero and x.size > 0:
            # A new time 0: show the whole measurement again, from its start to its end.
            self.handles.correctionZero = zero
            vb = w.correctionPlot.plotItem.vb
            vb.setXRange(float(x[0]), float(x[-1]), padding=0)
            vb.enableAutoRange(axis=pg.ViewBox.YAxis)
        w.correctionPlot.setLabel("bottom", "Time from PET start (s)" if petStart is not None
                                  else "Time from acquisition start (s)")
        self.handles.petStartLine.setVisible(petStart is not None)

        fixed = w.backgroundModeDropdown.currentIndex() == 1
        self.handles.backgroundLine.setVisible(fixed)
        if fixed:
            self.handles.backgroundLine.setPos(w.backgroundSpin.value())
        measured = not fixed and petStart is not None and x.size > 0 and bool(x[0] < 0)
        self.handles.correctionBackgroundRegion.setVisible(measured)
        if measured:
            self.handles.correctionBackgroundRegion.setRegion((float(x[0]), 0.0))

    def _petStart(self):
        """The PET scan start in seconds since the epoch, on the loaded data's day; None if unset or invalid."""
        data = self.handles.correctionData
        return _parseTime(self.widgets.petStartEdit.text().strip(), data["start"] if data else None)

    def _onSelectPetStart(self):
        if self.handles.selectingPetStart:
            self._endPetSelection()
            return
        if self.handles.correctionData is None:
            self._notify("error", "No data", "Load the data to correct first.")
            return
        self.handles.selectingPetStart = True
        self.widgets.petSelectButton.setText("Cancel")
        self.widgets.correctionPlot.setCursor(Qt.CursorShape.CrossCursor)
        self._notify("info", "PET scan start", "Click the plot where the PET scan starts.")

    def _endPetSelection(self):
        self.handles.selectingPetStart = False
        self.widgets.petSelectButton.setText("Select")
        self.widgets.correctionPlot.unsetCursor()

    def _onCorrectionPlotClicked(self, event):
        vb = self.widgets.correctionPlot.plotItem.vb
        if (not self.handles.selectingPetStart or event.button() != Qt.MouseButton.LeftButton
                or not vb.sceneBoundingRect().contains(event.scenePos())):
            return
        event.accept()
        x = vb.mapSceneToView(event.scenePos()).x()
        self._endPetSelection()
        stamp = datetime.fromtimestamp(round(self.handles.correctionZero + x))
        self.widgets.petStartEdit.setText(stamp.strftime(TIME_FORMAT))

    def _onBackgroundModeChanged(self, index):
        w = self.widgets
        fixed = index == 1
        w.backgroundSpin.setEnabled(fixed)
        if fixed:
            w.backgroundSpin.setSpecialValueText("")
            w.backgroundSpin.setValue(self.handles.fixedBackground)

    def _onBackgroundValueChanged(self, value):
        if self.widgets.backgroundModeDropdown.currentIndex() == 1:
            self.handles.fixedBackground = value

    def _showMeasuredBackground(self, petStart):
        """In "Mean before PET" mode, show the mean the correction will use, or "-" without one."""
        spin = self.widgets.backgroundSpin
        if self.widgets.backgroundModeDropdown.currentIndex() == 1:
            return
        mean = self.viewModel.measuredBackground(petStart)
        spin.blockSignals(True)
        spin.setSpecialValueText("-" if mean is None else "")
        spin.setValue(spin.minimum() if mean is None else mean)
        spin.blockSignals(False)

    def _onIsotopeChanged(self, *_):
        w = self.widgets
        name = w.isotopeDropdown.currentText()
        custom = name == CUSTOM_ISOTOPE
        w.halfLifeSpin.setEnabled(custom)
        w.branchingSpin.setEnabled(custom)
        if not custom and name in self.handles.isotopes:
            halfLife_s, branchingRatio = self.handles.isotopes[name]
            w.halfLifeSpin.setValue(halfLife_s / 60)
            w.branchingSpin.setValue(branchingRatio)
        w.calibrationIsotopeLabel.setText(name)

    def _applyCorrection(self):
        """Send the correction settings to the ViewModel; False if the PET start does not parse."""
        w = self.widgets
        text = w.petStartEdit.text().strip()
        petStart = self._petStart()
        if text and petStart is None:
            self._notify("error", "Invalid time", f"PET scan start: expected HH:MM:SS, got {text!r}")
            return False
        name = w.isotopeDropdown.currentText()
        custom = name == CUSTOM_ISOTOPE
        self.viewModel.setCorrection(
            name, petStart,
            w.backgroundSpin.value() if w.backgroundModeDropdown.currentIndex() == 1 else None,
            w.cfSpin.value(),
            w.halfLifeSpin.value() * 60 if custom else None,
            w.branchingSpin.value() if custom else None,
        )
        return True

    def _onSaveCorrected(self):
        source = self.viewModel.correctionSource()
        if source is None:
            self._notify("error", "Nothing to save", "Load the data to correct first.")
            return
        if not self.widgets.petStartEdit.text().strip():
            self._notify("error", "No PET start", "Set the PET scan start first.")
            return
        if not self._applyCorrection():
            return
        target, kind = self._askSavePath("Save corrected data", source, CORRECTED_FORMATS)
        if target:
            self.viewModel.exportCorrected(kind, target)

    def _askSavePath(self, title, source, formats):
        """Ask where to save, offering ``formats``; return ``(path, kind)``, or ``(None, None)``.

        The kind follows the extension typed, else the filter chosen, whose extension is
        then added.
        """
        stem = os.path.splitext(source)[0].removesuffix(".partial")
        kind, fileFilter, suffix = formats[0]
        target, chosen = QFileDialog.getSaveFileName(self, title, stem + suffix,
                                                     ";;".join(f[1] for f in formats), fileFilter)
        if not target:
            return None, None
        # Not os.path.splitext: it sees no extension in ".bld".
        byExtension = {"." + f[2].rpartition(".")[2]: f for f in formats}
        typed = os.path.splitext(target)[1].lower()
        if typed in byExtension:
            return target, byExtension[typed][0]
        kind, _, suffix = next((f for f in formats if f[1] == chosen), formats[0])
        return target + "." + suffix.rpartition(".")[2], kind

    def _onAcquisitionSaved(self, path):
        w = self.widgets
        w.saveRawButton.setEnabled(not self.viewModel.isAcquiring())
        w.saveEventsButton.setEnabled(not self.viewModel.isAcquiring())
        self._notify("success", "Saved", path)

    def _onPartialFilesFound(self, paths):
        names = "\n".join(os.path.basename(p) for p in paths)
        box = MessageBox("Interrupted acquisitions",
                         f"These acquisitions did not end cleanly:\n\n{names}\n\nRecover them now? "
                         "Every complete sample is kept.", self)
        if box.exec():
            self.viewModel.recoverFiles(paths)

    ###############################################################################
    # Calibration                                                                 #
    ###############################################################################

    def _onLoadCalibration(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load a calibration run", self.viewModel.dataDir(),
                                              "Acquisitions (*.csv)")
        if path:
            self.viewModel.loadCalibrationRun(path)

    def _onCalibrationRunLoaded(self, t, coincidences, name):
        self.widgets.calibrationFileLabel.setText(name)
        self.handles.calibrationCurve.setData(t, coincidences)
        start, end = float(t[0]), float(t[-1])
        span = max(end - start, 1.0)
        # Starting guesses: background in the first fifth, plateau in the second half.
        self.handles.backgroundRegion.setRegion((start, start + 0.2 * span))
        self.handles.plateauRegion.setRegion((start + 0.5 * span, end))
        for region in (self.handles.backgroundRegion, self.handles.plateauRegion):
            region.setVisible(True)
        # The run start, until the user enters another time.
        start = self.viewModel.calibrationRunStart()
        self.widgets.calibrationReferenceEdit.setText(datetime.fromtimestamp(start).strftime(TIME_FORMAT))
        self._computeCalibration()

    def _updateWindowLabels(self):
        for region, label in ((self.handles.backgroundRegion, self.widgets.backgroundWindowLabel),
                              (self.handles.plateauRegion, self.widgets.plateauWindowLabel)):
            start, end = region.getRegion()
            label.setText(f"{start:.0f} to {end:.0f} s")

    def _computeCalibration(self, *_):
        w = self.widgets
        reference = _parseTime(w.calibrationReferenceEdit.text().strip(), self.viewModel.calibrationRunStart())
        name = w.isotopeDropdown.currentText()
        custom = name == CUSTOM_ISOTOPE
        self.viewModel.computeCalibration(self.handles.backgroundRegion.getRegion(),
                                          self.handles.plateauRegion.getRegion(), w.activitySpin.value(), reference,
                                          name, w.halfLifeSpin.value() * 60 if custom else None,
                                          w.branchingSpin.value() if custom else None)

    def _onCalibrationComputed(self, cf, reason):
        w = self.widgets
        w.calibrationResultLabel.setText("-" if cf is None else f"{cf:.6g}")
        w.calibrationResultRow.contentLabel.setText(reason or "Apply uses it on the Correction page")
        w.applyCalibrationButton.setEnabled(cf is not None)

    def _onApplyCalibration(self):
        cf = self.viewModel.lastCalibrationFactor
        if cf is None:
            return
        self.widgets.cfSpin.setValue(cf)
        if self._applyCorrection():
            self._notify("success", "Calibration factor applied",
                         f"The Correction page now uses {cf:.6g} kBq/cc per count.")

    ###############################################################################
    # Settings and exit                                                           #
    ###############################################################################

    def _onStateRestored(self, state):
        w = self.widgets
        setters = {
            "host": w.hostEdit.setText, "port": w.portSpin.setValue, "qrate": lambda n: w.sampleRateDropdown.setCurrentText(f"{n / 10:g}"),
            "endMode": w.endModeDropdown.setCurrentText, "duration_min": w.durationSpin.setValue,
            "isotope": w.isotopeDropdown.setCurrentText, "backgroundMode": w.backgroundModeDropdown.setCurrentIndex,
            "calibrationFactor": w.cfSpin.setValue,
            "showCoincidences": w.showCoincidencesCheck.setChecked, "showSingles1": w.showSingles1Check.setChecked,
            "showSingles2": w.showSingles2Check.setChecked,
        }
        # Before the mode: switching to "Fixed value" shows it.
        self.handles.fixedBackground = state.get("background", self.handles.fixedBackground)
        for key, setter in setters.items():
            if key in state:
                setter(state[key])
        if state.get("isotope") == CUSTOM_ISOTOPE:
            w.halfLifeSpin.setValue(state.get("customHalfLife_min", w.halfLifeSpin.value()))
            w.branchingSpin.setValue(state.get("customBranchingRatio", w.branchingSpin.value()))
        self._applyCorrection()

    def _collectState(self):
        w = self.widgets
        return {
            "host": w.hostEdit.text().strip(), "port": w.portSpin.value(), "qrate": self._qrate(),
            "endMode": w.endModeDropdown.currentText(), "duration_min": w.durationSpin.value(),
            "isotope": w.isotopeDropdown.currentText(), "customHalfLife_min": w.halfLifeSpin.value(),
            "customBranchingRatio": w.branchingSpin.value(),
            "backgroundMode": w.backgroundModeDropdown.currentIndex(), "background": self.handles.fixedBackground,
            "calibrationFactor": w.cfSpin.value(), "showCoincidences": w.showCoincidencesCheck.isChecked(),
            "showSingles1": w.showSingles1Check.isChecked(), "showSingles2": w.showSingles2Check.isChecked(),
        }

    def closeEvent(self, event):
        self.viewModel.saveState(self._collectState())
        self.viewModel.shutdown()
        event.accept()

    def _notify(self, kind, title, message):
        show = {"error": InfoBar.error, "warning": InfoBar.warning, "success": InfoBar.success,
                "info": InfoBar.info}[kind]
        show(title, message, parent=self, position=InfoBarPosition.TOP_RIGHT,
             duration=-1 if kind == "error" else 4000)


def _toTopLeft(legend):
    """Move a legend from EINplotWidget's top-right corner to the top left; return it."""
    legend.anchor(itemPos=(0, 0), parentPos=(0, 0), offset=(LEGEND_INSET_PX, LEGEND_INSET_PX))
    return legend


def _parseTime(text, near=None):
    """Seconds since the epoch of ``HH:MM:SS`` on the day that puts it closest to ``near``.

    ``near`` (seconds since the epoch, now if None) is the data the time refers to, so a
    PET start just after midnight lands on the right day. Returns None if ``text`` is
    empty or not a time.
    """
    try:
        clock = datetime.strptime(text, TIME_FORMAT).time()
    except ValueError:
        return None
    near = time.time() if near is None else near
    day = datetime.fromtimestamp(near).date()
    candidates = [datetime.combine(day + timedelta(days=d), clock).timestamp() for d in (-1, 0, 1)]
    return min(candidates, key=lambda t: abs(t - near))
