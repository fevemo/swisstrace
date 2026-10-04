import os
from datetime import datetime

import pyqtgraph as pg
from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtWidgets import QFileDialog
from qfluentwidgets import InfoBar, InfoBarPosition, MessageBox

from einstudio.tools.einview import EINview
from einstudio.widgets import (
    EINbodyLabel, EINbutton, EINcaptionLabel, EINcheckBox, EINdocWidget, EINdoubleSpinBox, EINdropDown,
    EINlineEdit, EINlogDisplayWidget, EINplotWidget, EINspinBox, EINstatusLight, EINswitch, EINtitleLabel,
)

CUSTOM_ISOTOPE = "Custom"
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
# ViewModel status -> status light state.
STATUS_LIGHTS = {"disconnected": "off", "connecting": "processing", "connected": "ready",
                 "acquiring": "running", "error": "error"}


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
            ('qrateSpin',             EINspinBox),
            ('endModeDropdown',       EINdropDown),
            ('durationSpin',          EINdoubleSpinBox),
            ('startButton',           EINbutton),
            ('stopButton',            EINbutton),
            ('elapsedLabel',          EINbodyLabel),
            ('samplesLabel',          EINbodyLabel),
            ('markEdit',              EINlineEdit),
            ('markButton',            EINbutton),
            ('showCoincidencesCheck', EINcheckBox),
            ('showSingles1Check',     EINcheckBox),
            ('showSingles2Check',     EINcheckBox),
            ('correctedSwitch',       EINswitch),
            ('plotWidget',            EINplotWidget),
            ('logDisplayWidget',      EINlogDisplayWidget),
            # Correction page
            ('isotopeDropdown',       EINdropDown),
            ('halfLifeSpin',          EINdoubleSpinBox),
            ('branchingSpin',         EINdoubleSpinBox),
            ('petStartEdit',          EINlineEdit),
            ('petNowButton',          EINbutton),
            ('backgroundModeDropdown', EINdropDown),
            ('backgroundSpin',        EINdoubleSpinBox),
            ('cfSpin',                EINdoubleSpinBox),
            ('applyCorrectionButton', EINbutton),
            ('exportFileLabel',       EINcaptionLabel),
            ('chooseExportFileButton', EINbutton),
            ('exportCsvButton',       EINbutton),
            ('exportCrvButton',       EINbutton),
            ('exportPmodButton',      EINbutton),
            ('exportEventsButton',    EINbutton),
            # Calibration page
            ('calibrationFileLabel',  EINcaptionLabel),
            ('loadCalibrationButton', EINbutton),
            ('backgroundWindowLabel', EINbodyLabel),
            ('plateauWindowLabel',    EINbodyLabel),
            ('calibrationReferenceEdit', EINlineEdit),
            ('referenceRunStartButton', EINbutton),
            ('activitySpin',          EINdoubleSpinBox),
            ('calibrationIsotopeLabel', EINbodyLabel),
            ('computeCalibrationButton', EINbutton),
            ('calibrationResultLabel', EINtitleLabel),
            ('useCalibrationButton',  EINbutton),
            ('calibrationPlot',       EINplotWidget),
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
        w.qrateSpin.setValue(10)
        w.durationSpin.setValue(60.0)
        w.durationSpin.setEnabled(False)
        w.stopButton.setEnabled(False)
        w.startButton.setEnabled(False)
        w.markButton.setEnabled(False)
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
        plot.addLegend(["Coincidences", "Singles 1", "Singles 2"])
        plot.showGrid(x=True, y=True)
        self.handles.markLines = []

        # Calibration plot with the two windows to drag.
        calPlot = w.calibrationPlot
        self.handles.calibrationCurve = calPlot.plot([], [], connect="finite")
        self.handles.backgroundRegion = pg.LinearRegionItem(brush=pg.mkBrush(128, 128, 128, 50))
        self.handles.plateauRegion = pg.LinearRegionItem(brush=pg.mkBrush(0, 170, 150, 50))
        for region in (self.handles.backgroundRegion, self.handles.plateauRegion):
            region.setVisible(False)
            calPlot.addItem(region)
        calPlot.showGrid(x=True, y=True)

        indexFile = os.path.join(self.configManager.mainConfig.docPath, "index.html")
        if os.path.isfile(indexFile):
            w.docView.updateHTML(QUrl.fromLocalFile(os.path.abspath(indexFile)).toString())

        # After bindSignals(), so the signals these emit are connected.
        QTimer.singleShot(0, self.viewModel.loadState)
        QTimer.singleShot(0, self.viewModel.checkPartialFiles)

    def bindWidgetsActions(self):
        w = self.widgets
        w.connectButton.clicked.connect(self._onConnectClicked)
        w.startButton.clicked.connect(self._onStart)
        w.stopButton.clicked.connect(self.viewModel.stopAcquisition)
        w.endModeDropdown.currentTextChanged.connect(lambda text: w.durationSpin.setEnabled(text == "Time"))
        w.markButton.clicked.connect(self._onMark)
        w.markEdit.returnPressed.connect(self._onMark)
        for check in (w.showCoincidencesCheck, w.showSingles1Check, w.showSingles2Check):
            check.stateChanged.connect(self._updateCurveVisibility)
        w.correctedSwitch.checkedChanged.connect(self._onCorrectedToggled)

        w.isotopeDropdown.currentTextChanged.connect(self._onIsotopeChanged)
        w.petNowButton.clicked.connect(lambda: w.petStartEdit.setText(datetime.now().strftime(TIME_FORMAT)))
        w.backgroundModeDropdown.currentIndexChanged.connect(lambda i: w.backgroundSpin.setEnabled(i == 1))
        w.applyCorrectionButton.clicked.connect(self._applyCorrection)
        w.chooseExportFileButton.clicked.connect(self._onChooseExportFile)
        w.exportCsvButton.clicked.connect(lambda: self._onExport("csv", "_export.csv", "CSV (*.csv)"))
        w.exportCrvButton.clicked.connect(lambda: self._onExport("crv", ".crv", "PSAMPLE curve (*.crv)"))
        w.exportPmodButton.clicked.connect(lambda: self._onExport("pmod", ".bld", "PMOD blood (*.bld)"))
        w.exportEventsButton.clicked.connect(lambda: self._onExport("events", "_events.csv", "CSV (*.csv)"))

        w.loadCalibrationButton.clicked.connect(self._onLoadCalibration)
        w.referenceRunStartButton.clicked.connect(self._setReferenceToRunStart)
        w.computeCalibrationButton.clicked.connect(self._onComputeCalibration)
        w.useCalibrationButton.clicked.connect(self._onUseCalibration)
        self.handles.backgroundRegion.sigRegionChanged.connect(self._updateWindowLabels)
        self.handles.plateauRegion.sigRegionChanged.connect(self._updateWindowLabels)

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
        vm.calibrationComputed.connect(lambda cf: self.widgets.calibrationResultLabel.setText(f"{cf:.6g}"))
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
        w.startButton.setEnabled(connected and not self.viewModel.isAcquiring())
        if not connected:
            self._onStatusChanged("disconnected", "Disconnected")

    def _onStatusChanged(self, status, text):
        self.widgets.statusLight.setStatus(STATUS_LIGHTS[status], text)

    def _onStart(self):
        w = self.widgets
        endAfter_s = w.durationSpin.value() * 60 if w.endModeDropdown.currentText() == "Time" else None
        for line in self.handles.markLines:
            w.plotWidget.removeItem(line)
        self.handles.markLines = []
        self.viewModel.startAcquisition(w.qrateSpin.value(), endAfter_s)

    def _onAcquisitionChanged(self, running):
        w = self.widgets
        w.startButton.setEnabled(not running and self.viewModel.isConnected())
        w.stopButton.setEnabled(running)
        w.markButton.setEnabled(running)
        w.connectButton.setEnabled(not running)
        w.qrateSpin.setEnabled(not running)
        w.endModeDropdown.setEnabled(not running)

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
        self.widgets.samplesLabel.setText(str(stats["samples"]))

    def _updateCurveVisibility(self):
        w = self.widgets
        corrected = w.correctedSwitch.isChecked()
        self.handles.coincidenceCurve.setVisible(w.showCoincidencesCheck.isChecked())
        # Singles are raw counts; they would dwarf a curve in kBq/cc.
        self.handles.singles1Curve.setVisible(w.showSingles1Check.isChecked() and not corrected)
        self.handles.singles2Curve.setVisible(w.showSingles2Check.isChecked() and not corrected)

    def _onCorrectedToggled(self, corrected):
        if corrected and not self.widgets.petStartEdit.text().strip():
            self._notify("warning", "No PET start", "Set and apply the PET scan start on the Correction page.")
        self.widgets.plotWidget.setLabel("left", "Activity (kBq/cc)" if corrected else "Counts")
        self._updateCurveVisibility()
        self.viewModel.setShowCorrected(corrected)

    ###############################################################################
    # Correction and export                                                       #
    ###############################################################################

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
        w = self.widgets
        text = w.petStartEdit.text().strip()
        petStart = _parseTime(text) if text else None
        if text and petStart is None:
            self._notify("error", "Invalid time", f"PET scan start: expected {TIME_FORMAT}, got {text!r}")
            return
        name = w.isotopeDropdown.currentText()
        custom = name == CUSTOM_ISOTOPE
        self.viewModel.setCorrection(
            name, petStart,
            w.backgroundSpin.value() if w.backgroundModeDropdown.currentIndex() == 1 else None,
            w.cfSpin.value(),
            w.halfLifeSpin.value() * 60 if custom else None,
            w.branchingSpin.value() if custom else None,
        )

    def _onAcquisitionSaved(self, path):
        self.widgets.exportFileLabel.setText(os.path.basename(path))
        self._notify("success", "Saved", path)

    def _onChooseExportFile(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose an acquisition", self.viewModel.dataDir(),
                                              "Acquisitions (*.csv)")
        if path:
            self.viewModel.setExportFile(path)
            self.widgets.exportFileLabel.setText(os.path.basename(path))

    def _onExport(self, kind, suffix, fileFilter):
        source = self.viewModel.exportFile
        if source is None:
            self._notify("error", "Nothing to export", "Run an acquisition or choose a file first.")
            return
        if kind in ("csv", "pmod"):
            self._applyCorrection()
        default = os.path.splitext(source)[0] + suffix
        target, _ = QFileDialog.getSaveFileName(self, "Export", default, fileFilter)
        if target:
            self.viewModel.export(kind, target)

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
            self.widgets.calibrationFileLabel.setText(os.path.basename(path))
            self.viewModel.loadCalibrationRun(path)

    def _onCalibrationRunLoaded(self, t, coincidences):
        self.handles.calibrationCurve.setData(t, coincidences)
        start, end = float(t[0]), float(t[-1])
        span = max(end - start, 1.0)
        # Starting guesses: background in the first fifth, plateau in the second half.
        self.handles.backgroundRegion.setRegion((start, start + 0.2 * span))
        self.handles.plateauRegion.setRegion((start + 0.5 * span, end))
        for region in (self.handles.backgroundRegion, self.handles.plateauRegion):
            region.setVisible(True)
        self.widgets.calibrationResultLabel.setText("-")
        if not self.widgets.calibrationReferenceEdit.text().strip():
            self._setReferenceToRunStart()

    def _setReferenceToRunStart(self):
        start = self.viewModel.calibrationRunStart()
        if start is not None:
            self.widgets.calibrationReferenceEdit.setText(datetime.fromtimestamp(start).strftime(TIME_FORMAT))

    def _updateWindowLabels(self):
        for region, label in ((self.handles.backgroundRegion, self.widgets.backgroundWindowLabel),
                              (self.handles.plateauRegion, self.widgets.plateauWindowLabel)):
            start, end = region.getRegion()
            label.setText(f"{start:.0f} to {end:.0f} s")

    def _onComputeCalibration(self):
        text = self.widgets.calibrationReferenceEdit.text().strip()
        reference = _parseTime(text)
        if reference is None:
            self._notify("error", "Invalid time", f"PET reference time: expected {TIME_FORMAT}, got {text!r}")
            return
        self._applyCorrection()  # the isotope comes from the Correction page
        self.viewModel.computeCalibration(self.handles.backgroundRegion.getRegion(),
                                          self.handles.plateauRegion.getRegion(),
                                          self.widgets.activitySpin.value(), reference)

    def _onUseCalibration(self):
        cf = self.viewModel.lastCalibrationFactor
        if cf is None:
            self._notify("error", "No result", "Compute a calibration factor first.")
            return
        self.widgets.cfSpin.setValue(cf)
        self._applyCorrection()
        self._notify("success", "Calibration factor", f"Now using {cf:.6g}")

    ###############################################################################
    # Settings and exit                                                           #
    ###############################################################################

    def _onStateRestored(self, state):
        w = self.widgets
        setters = {
            "host": w.hostEdit.setText, "port": w.portSpin.setValue, "qrate": w.qrateSpin.setValue,
            "endMode": w.endModeDropdown.setCurrentText, "duration_min": w.durationSpin.setValue,
            "isotope": w.isotopeDropdown.setCurrentText, "backgroundMode": w.backgroundModeDropdown.setCurrentIndex,
            "background": w.backgroundSpin.setValue, "calibrationFactor": w.cfSpin.setValue,
            "showCoincidences": w.showCoincidencesCheck.setChecked, "showSingles1": w.showSingles1Check.setChecked,
            "showSingles2": w.showSingles2Check.setChecked,
        }
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
            "host": w.hostEdit.text().strip(), "port": w.portSpin.value(), "qrate": w.qrateSpin.value(),
            "endMode": w.endModeDropdown.currentText(), "duration_min": w.durationSpin.value(),
            "isotope": w.isotopeDropdown.currentText(), "customHalfLife_min": w.halfLifeSpin.value(),
            "customBranchingRatio": w.branchingSpin.value(),
            "backgroundMode": w.backgroundModeDropdown.currentIndex(), "background": w.backgroundSpin.value(),
            "calibrationFactor": w.cfSpin.value(), "showCoincidences": w.showCoincidencesCheck.isChecked(),
            "showSingles1": w.showSingles1Check.isChecked(), "showSingles2": w.showSingles2Check.isChecked(),
        }

    def closeEvent(self, event):
        self.viewModel.saveState(self._collectState())
        self.viewModel.shutdown()
        event.accept()

    def _notify(self, kind, title, message):
        show = {"error": InfoBar.error, "warning": InfoBar.warning, "success": InfoBar.success}[kind]
        show(title, message, parent=self, position=InfoBarPosition.TOP_RIGHT,
             duration=-1 if kind == "error" else 4000)


def _parseTime(text):
    """Seconds since the epoch of ``YYYY-MM-DD HH:MM:SS``, or of ``HH:MM:SS`` today; None if invalid."""
    for fmt in (TIME_FORMAT, "%Y-%m-%dT%H:%M:%S", "%H:%M:%S"):
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if fmt == "%H:%M:%S":
            parsed = datetime.combine(datetime.now().date(), parsed.time())
        return parsed.timestamp()
    return None
