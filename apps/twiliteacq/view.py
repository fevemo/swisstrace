import math
import os
import time
from datetime import datetime, timedelta

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import QAbstractItemView, QFileDialog, QHeaderView, QTableWidgetItem, QWidget
from qfluentwidgets import InfoBar, InfoBarPosition, MessageBox, PushButton, TableWidget

from einstudio.tools.einview import EINview
from einstudio.tools.styleengine import StyleEngine
from einstudio.widgets import (
    EINbodyLabel, EINbutton, EINcaptionLabel, EINcheckBox, EINdialog, EINdocWidget, EINdoubleSpinBox, EINdropDown,
    EINhBoxLayout, EINlineEdit, EINlogDisplayWidget, EINoptionRow, EINplotWidget, EINspinBox, EINstatusLight,
    EINtitleLabel, EINvBoxLayout,
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
# The samples selected for a cut (c_plot_curve_5, translucent).
CUT_BRUSH = (243, 218, 114, 40)
# Opacity of the error colour behind a resample section that cannot be applied.
ERROR_ROW_ALPHA = 90
# Marker size of the samples while editing, in pixels.
SAMPLE_MARKER_PX = 5
# Save dialogs: (export kind, file filter, suffix added to the acquisition's name).
RAW_FORMATS = [("csv", "CSV (*.csv)", "_raw.csv"), ("crv", "Curve (*.crv)", ".crv")]
EVENT_FORMATS = [("events", "CSV (*.csv)", "_events.csv")]
CORRECTED_FORMATS = [("bld", "PMOD blood (*.bld)", ".bld"), ("tac", "PMOD TAC (*.tac)", ".tac"),
                     ("csv", "CSV with corrected values (*.csv)", "_corrected.csv")]
EDITED_FORMATS = [("csv", "Acquisitions (*.csv)", "_edited.csv")]
EDITED_SUFFIX = "_edited"


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
            ('saveCorrectedButton',   EINbutton),
            ('correctionFileLabel',   EINcaptionLabel),
            ('useCurrentDataButton',  EINbutton),
            ('loadCorrectionDataButton', EINbutton),
            ('correctionPlot',        EINplotWidget),
            ('cutButton',             EINbutton),
            ('resampleButton',        EINbutton),
            ('saveEditedButton',      EINbutton),
            ('cutRow',                EINoptionRow),
            ('cutAverageSpin',        EINspinBox),
            ('applyCutButton',        EINbutton),
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
        w.cutRow.setVisible(False)
        w.cutAverageSpin.setValue(1)

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
        self._updateEditButtons()
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
        w.saveRawButton.clicked.connect(lambda: self._onSaveRaw("Save raw data", RAW_FORMATS))
        w.saveEventsButton.clicked.connect(lambda: self._onSaveRaw("Save events", EVENT_FORMATS))
        w.saveCorrectedButton.clicked.connect(self._onSaveCorrected)
        w.useCurrentDataButton.clicked.connect(self._onUseCurrentData)
        w.loadCorrectionDataButton.clicked.connect(self._onLoadCorrectionData)
        w.cutButton.clicked.connect(self._onCutClicked)
        w.cutAverageSpin.valueChanged.connect(self._updateCutPreview)
        w.applyCutButton.clicked.connect(self._applyCut)
        w.resampleButton.clicked.connect(self._onResamplingClicked)
        w.saveEditedButton.clicked.connect(self._onSaveEdited)
        self.handles.cutRegion.sigRegionChanged.connect(self._updateCutPreview)
        self.handles.cutRegion.sigRegionChangeFinished.connect(self._snapCutRegion)
        # Any change to the settings redraws the plot and corrects the data again.
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
        vm.correctionDataEdited.connect(self._onCorrectionDataEdited)
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
        # Above the main view, so the corrected curve shows over the coincidences, but
        # deaf to the mouse: panning, zooming and selecting stay with the main view.
        correctedView.setZValue(1)
        correctedView.setMouseEnabled(False, False)
        correctedView.setMenuEnabled(False)
        correctedView.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        # A ViewBox takes every drag, enabled or not: let them through to the main view.
        correctedView.mouseDragEvent = lambda event, axis=None: event.ignore()
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
        # Panning and zooming in y move the corrected axis along with the coincidences'.
        self.handles.mainYRange = item.vb.viewRange()[1]
        item.vb.sigYRangeChanged.connect(self._followYRange)
        # In the corrected view, so the corrected curve does not cover it.
        legend = plot.addLegend(["Coincidences"])
        legend.setParentItem(correctedView)
        legend.setZValue(1)
        _toTopLeft(legend).addItem(self.handles.correctedCurve, "Corrected")

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

        # Editing: the samples selected for a cut, and previews of a cut and of a resampling.
        self.handles.cutRegion = pg.LinearRegionItem(brush=pg.mkBrush(*CUT_BRUSH))
        self.handles.cutRegion.setVisible(False)
        plot.addItem(self.handles.cutRegion)
        self.handles.cutSelectedPoints = pg.ScatterPlotItem(
            size=SAMPLE_MARKER_PX + 2, pen=None, brush=pg.mkBrush(StyleEngine.token("c_plot_curve_5")))
        plot.addItem(self.handles.cutSelectedPoints)
        # Twice as thick as the data, so a preview stands out on a noisy curve.
        previewPen = pg.mkPen(StyleEngine.token("c_plot_curve_4"), width=2 * StyleEngine.px("plot_line_width_px"),
                              style=Qt.PenStyle.DashLine)
        self.handles.cutPreviewCurve, self.handles.resamplePreviewCurve = (
            plot.plot([], [], pen=previewPen, connect="finite", symbol="o", symbolSize=SAMPLE_MARKER_PX + 2,
                      symbolPen=pg.mkPen(StyleEngine.token("c_plot_curve_4")), symbolBrush=None)
            for _ in range(2))
        self.handles.sectionLines = []
        self.handles.cutting = False
        self.handles.resampleDialog = None
        # In cut mode a left drag selects samples instead of panning.
        self.handles.dragPlot = item.vb.mouseDragEvent
        item.vb.mouseDragEvent = self._onCorrectionPlotDragged

        self.handles.correctionData = None
        # Wall time of x = 0 on the plot: the PET start, or the acquisition start without one.
        self.handles.correctionZero = None
        self.handles.selectingPetStart = False
        # The "Fixed value" background, kept while the field shows the measured mean.
        self.handles.fixedBackground = 0.0
        # The resample window shows (set when it shows or hides, so true in its hide event too).
        self.handles.resampling = False

    def _onUseCurrentData(self):
        if self._confirmDiscardEdits("Load the current acquisition"):
            self.viewModel.loadCorrectionData()

    def _onLoadCorrectionData(self):
        if not self._confirmDiscardEdits("Load another file"):
            return
        source = self.viewModel.correctionSource()
        path, _ = QFileDialog.getOpenFileName(self, "Load an acquisition",
                                              os.path.dirname(source) if source else self.viewModel.dataDir(),
                                              "Acquisitions (*.csv)")
        if path:
            self.viewModel.loadCorrectionData(path)

    def _onCorrectionDataLoaded(self, data):
        self._endCutMode()
        if self.handles.resampleDialog is not None:
            self.handles.resampleDialog.close()
        self.handles.correctionData = data
        self.handles.correctionZero = None  # show the whole measurement
        self._showDataName(data)
        self._refreshCorrectionPlot()
        # The PET start's date comes from the data: apply again with the new data's date.
        self._applyCorrection()

    def _onCorrectionDataEdited(self, data):
        self.handles.correctionData = data
        self._showDataName(data)
        self._refreshCorrectionPlot()  # the same time 0, so the zoom stays

    def _showDataName(self, data):
        self.widgets.correctionFileLabel.setText(data["name"])
        self._updateEditButtons()

    def _updateEditButtons(self):
        """Cut and Resampling need data and exclude each other; Save needs unsaved edits."""
        w, h = self.widgets, self.handles
        data = h.correctionData
        w.cutButton.setEnabled(data is not None and not h.resampling)
        w.resampleButton.setEnabled(data is not None and not h.cutting)
        w.saveEditedButton.setEnabled(data is not None and data["unsaved"])

    def _confirmDiscardEdits(self, action):
        """True if there are no unsaved edits, or the user agrees to lose them."""
        if not self.viewModel.hasUnsavedEdits():
            return True
        box = MessageBox("Unsaved edits", f"The edited data has not been saved. {action} and lose the edits?", self)
        return bool(box.exec())

    def _onCorrectionComputed(self, result):
        if result is None:
            self.handles.correctedCurve.setData([], [])
            return
        t, activity, _ = result
        self.handles.correctedCurve.setData(t, activity)

    def _followYRange(self, vb, yRange):
        """Pan and zoom the corrected axis as the coincidence axis was: the same shift and
        scale, relative to each axis's range. While the coincidences fit their range to
        the data, the corrected curve fits its own."""
        h = self.handles
        (a0, b0), (a1, b1) = h.mainYRange, yRange
        h.mainYRange = list(yRange)
        if vb.autoRangeEnabled()[1]:
            h.correctedView.enableAutoRange(axis=pg.ViewBox.YAxis)
            return
        if b0 == a0:
            return
        c0, d0 = h.correctedView.viewRange()[1]
        scale = (d0 - c0) / (b0 - a0)
        h.correctedView.setYRange(c0 + (a1 - a0) * scale, d0 + (b1 - b0) * scale, padding=0)

    def _onCorrectionEdited(self, *_):
        self._refreshCorrectionPlot()
        # Quietly: a PET start being typed is not a time yet.
        self._applyCorrection(quiet=True)

    def _refreshCorrectionPlot(self):
        """Redraw the raw curve and the overlays from the settings as they are on screen.

        Time 0 is the PET start, or the acquisition start while the PET start is not set.
        Each sample is drawn at its time (when its report arrived, or the middle of a
        resampled sample), the time the correction uses.
        """
        w = self.widgets
        petStart = self._petStart()
        self._showMeasuredBackground(petStart)
        data = self.handles.correctionData
        if data is None:
            return
        zero = petStart if petStart is not None else data["start"]
        x = data["t"] - zero
        self.handles.rawCurve.setData(x, data["coincidences"])
        if zero != self.handles.correctionZero and x.size > 0:
            # A new time 0: show the whole measurement again, from its start to its end.
            if self.handles.correctionZero is not None:
                # The cut selection stays on the same samples.
                shift = self.handles.correctionZero - zero
                self.handles.cutRegion.setRegion([edge + shift for edge in self.handles.cutRegion.getRegion()])
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

        # The previews follow the data and its time 0.
        self._updateCutPreview()
        if self.handles.resampling:
            self.handles.resampleDialog.refresh()

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
        self._endCutMode()
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

    def _applyCorrection(self, quiet=False):
        """Send the correction settings to the ViewModel; False if the PET start does not parse.

        With ``quiet``, an unparsable PET start only removes the corrected curve.
        """
        w = self.widgets
        text = w.petStartEdit.text().strip()
        petStart = self._petStart()
        if text and petStart is None:
            if quiet:
                self.handles.correctedCurve.setData([], [])
            else:
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
    # Editing the correction data                                                 #
    ###############################################################################

    def _onCutClicked(self):
        if self.handles.cutting:
            self._endCutMode()
            return
        if self.handles.correctionData is None:
            self._notify("error", "No data", "Load the data to correct first.")
            return
        if self.handles.selectingPetStart:
            self._endPetSelection()
        w = self.widgets
        self.handles.cutting = True
        w.cutButton.setText("Done")
        w.cutRow.setVisible(True)
        self._updateEditButtons()
        self._showSampleMarkers(True)
        self._updateCutPreview()

    def _endCutMode(self):
        if not self.handles.cutting:
            return
        w = self.widgets
        self.handles.cutting = False
        w.cutButton.setText("Cut")
        w.cutRow.setVisible(False)
        self._updateEditButtons()
        self.handles.cutRegion.setVisible(False)
        self._updateCutPreview()
        self._showSampleMarkers(False)

    def _onCorrectionPlotDragged(self, event, axis=None):
        """In cut mode, a left drag on the plot selects the samples to cut; else the plot pans as usual."""
        if not self.handles.cutting or axis is not None or event.button() != Qt.MouseButton.LeftButton:
            self.handles.dragPlot(event, axis)
            return
        event.accept()
        vb = self.widgets.correctionPlot.plotItem.vb
        start = vb.mapSceneToView(event.buttonDownScenePos()).x()
        end = vb.mapSceneToView(event.scenePos()).x()
        # Visible first: setRegion previews and snaps the selection at once.
        self.handles.cutRegion.setVisible(True)
        self.handles.cutRegion.setRegion(sorted((start, end)))

    def _snapCutRegion(self, *_):
        """Move the cut selection's edges to the nearest midway points between samples."""
        data = self.handles.correctionData
        if data is None or data["t"].size < 2:
            return
        x = data["t"] - self.handles.correctionZero
        edges = np.concatenate(([x[0] - (x[1] - x[0]) / 2], (x[:-1] + x[1:]) / 2, [x[-1] + (x[-1] - x[-2]) / 2]))
        snapped = [float(edges[np.abs(edges - edge).argmin()]) for edge in self.handles.cutRegion.getRegion()]
        if snapped[0] != snapped[1]:
            self.handles.cutRegion.setRegion(snapped)

    def _cutWindow(self):
        """The cut selection in PC times, or None when nothing is selected."""
        if not self.handles.cutting or not self.handles.cutRegion.isVisible():
            return None
        start, end = self.handles.cutRegion.getRegion()
        return start + self.handles.correctionZero, end + self.handles.correctionZero

    def _updateCutPreview(self, *_):
        """Show the samples selected and the line, from edge to edge, that would replace them,
        or why there is none."""
        h, w = self.handles, self.widgets
        window = self._cutWindow()
        result, reason = (None, "Drag in the plot to select samples") if window is None \
            else self.viewModel.cutPreview(*window, w.cutAverageSpin.value())
        w.applyCutButton.setEnabled(result is not None)
        if result is None:
            h.cutPreviewCurve.setData([], [])
            h.cutSelectedPoints.setData([], [])
            w.cutRow.contentLabel.setText(reason)
            return
        t, values = result
        zero = h.correctionZero
        h.cutPreviewCurve.setData(t - zero, values)
        selected = (h.correctionData["t"] >= window[0]) & (h.correctionData["t"] <= window[1])
        tSelected = h.correctionData["t"][selected] - zero
        h.cutSelectedPoints.setData(tSelected, h.correctionData["coincidences"][selected])
        w.cutRow.contentLabel.setText(f"{tSelected.size} samples, {tSelected[0]:.1f} to {tSelected[-1]:.1f} s")

    def _applyCut(self):
        window = self._cutWindow()
        if window is not None and self.viewModel.applyCut(*window, self.widgets.cutAverageSpin.value()):
            self.handles.cutRegion.setVisible(False)
            self._updateCutPreview()

    def _showSampleMarkers(self, show):
        """Mark every sample on the raw curve, as while cutting."""
        curve = self.handles.rawCurve
        if not show:
            curve.setSymbol(None)
            return
        curve.setSymbol("o")
        curve.setSymbolSize(SAMPLE_MARKER_PX)
        curve.setSymbolPen(None)
        curve.setSymbolBrush(pg.mkBrush(StyleEngine.token("c_plot_curve_1")))

    def _onResamplingClicked(self):
        """Open the resample window, or close it ("Done") once it is open."""
        if self.handles.resampling:
            self._closeResampleDialog()
        else:
            self._openResampleDialog()

    def _closeResampleDialog(self):
        """Close the resample window, asking first if its sections are not applied."""
        dialog = self.handles.resampleDialog
        if dialog.hasPendingChanges():
            choice = self._askUnappliedResample(dialog.canApply())
            if choice == "cancel":
                dialog.raise_()  # back to the window, in front of the main one
                dialog.activateWindow()
                return
            if choice == "apply" and not self.viewModel.applyResample(dialog.sections()):
                return  # the error is reported; the window stays to fix it
        dialog.close()

    def _askUnappliedResample(self, canApply):
        """Ask what to do with sections not applied: "apply", "discard" or "cancel"."""
        text = ("The sections in the Resample window have changes that have not been applied. "
                "Apply them, discard them, or go back to the window?" if canApply else
                "Some sections in the Resample window cannot be applied (in red). "
                "Discard the changes, or go back to fix them?")
        box = MessageBox("Resampling not applied", text, self)
        box.yesButton.setText("Apply")
        box.yesButton.setEnabled(canApply)
        discardButton = PushButton("Discard", box.buttonGroup)
        discardButton.clicked.connect(lambda: box.done(2))
        box.buttonLayout.insertWidget(1, discardButton, 1, Qt.AlignmentFlag.AlignVCenter)
        return {1: "apply", 2: "discard"}.get(box.exec(), "cancel")

    def _openResampleDialog(self):
        if self.handles.correctionData is None:
            self._notify("error", "No data", "Load the data to correct first.")
            return
        if self.handles.resampleDialog is None:
            dialog = ResampleDialog(self, lambda: self.handles.correctionZero)
            dialog.sectionsChanged.connect(self._previewResample)
            dialog.applyRequested.connect(self._applyResample)
            dialog.visibilityChanged.connect(self._onResampleDialogShown)
            self.handles.resampleDialog = dialog
        self.handles.resampleDialog.setSections(self.viewModel.samplingSections())
        self.handles.resampleDialog.show()
        self.handles.resampleDialog.raise_()

    def _previewResample(self, sections):
        h = self.handles
        self._clearResamplePreview()
        preview = self.viewModel.resamplePreview(sections)
        if preview is None:
            return
        h.resampleDialog.showPreview(preview["counts"], preview["problems"], preview["changes"])
        zero = h.correctionZero
        h.resamplePreviewCurve.setData(preview["t"] - zero, preview["coincidences"])
        pen = pg.mkPen(StyleEngine.token("c_plot_curve_4"), style=Qt.PenStyle.DotLine)
        for boundary in sorted({edge for section in sections for edge in section[:2]}):
            line = pg.InfiniteLine(pos=boundary - zero, angle=90, movable=False, pen=pen)
            self.widgets.correctionPlot.addItem(line)
            h.sectionLines.append(line)

    def _applyResample(self, sections):
        if self.viewModel.applyResample(sections):
            # The sections as the data is now sampled.
            self.handles.resampleDialog.setSections(self.viewModel.samplingSections())

    def _onResampleDialogShown(self, shown):
        """Previews while the window shows (it emits its sections then); no cutting meanwhile."""
        self.handles.resampling = shown
        self.widgets.resampleButton.setText("Done" if shown else "Resampling")
        self._updateEditButtons()
        if not shown:
            self._clearResamplePreview()

    def _clearResamplePreview(self):
        h = self.handles
        h.resamplePreviewCurve.setData([], [])
        for line in h.sectionLines:
            self.widgets.correctionPlot.removeItem(line)
        h.sectionLines = []

    def _onSaveEdited(self):
        source = self.viewModel.correctionSource()
        if source is None:
            return
        # An edited file is saved again under its own name, not as "..._edited_edited.csv".
        stem, extension = os.path.splitext(source)
        target, _ = self._askSavePath("Save edited data", stem.removesuffix(EDITED_SUFFIX) + extension,
                                      EDITED_FORMATS)
        if target and self.viewModel.saveEditedData(target):
            self._notify("success", "Edited data saved", target)

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
        if not self._confirmDiscardEdits("Close"):
            event.ignore()
            return
        self.viewModel.saveState(self._collectState())
        self.viewModel.shutdown()
        event.accept()

    def _notify(self, kind, title, message):
        show = {"error": InfoBar.error, "warning": InfoBar.warning, "success": InfoBar.success,
                "info": InfoBar.info}[kind]
        show(title, message, parent=self, position=InfoBarPosition.TOP_RIGHT,
             duration=-1 if kind == "error" else 4000)


class ResampleDialog(EINdialog):
    """The sections to resample, one row each: start, end, sampling period, and the samples that makes.

    Not modal, so the plot can be zoomed while editing. Times are shown in seconds on
    the Correction plot's axis and kept as PC times, so a section stays on the same
    samples when the plot's time 0 (the PET start) changes. Adjacent sections share
    their boundary: moving one end moves the next section's start. "Add section" splits
    the selected section (the last one without a selection) in two halves; "Delete
    section" gives the section's time to the one before it, so the first one stays.

    Args:
        mainWindow: The View.
        zero: Returns the PC time of the plot's time 0.
    """

    # [(start, end, period)] after every change, PC times.
    sectionsChanged = pyqtSignal(list)
    # The same, when Apply is clicked.
    applyRequested = pyqtSignal(list)
    # True when the window shows, False when it is closed or hidden (Esc, a minimized main window).
    visibilityChanged = pyqtSignal(bool)

    HEADERS = ["Start (s)", "End (s)", "Sampling (s/sample)", "Samples"]

    def __init__(self, mainWindow, zero):
        super().__init__(mainWindow, "Resample")
        self._zero = zero
        self._sections = []
        # From the last preview: whether applying would change the data, and whether it can be applied.
        self._changes = False
        self._valid = False

        self.table = TableWidget(self)
        self.table.setColumnCount(len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.itemChanged.connect(self._onItemChanged)
        self.table.itemSelectionChanged.connect(self._updateButtons)
        self.statusLabel = EINcaptionLabel("")
        self.statusLabel.setWordWrap(True)
        self.addButton = EINbutton("Add section", length="med")
        self.deleteButton = EINbutton("Delete section", length="med")
        self.applyButton = EINbutton("Resample", role="primary", length="short")
        self.addButton.clicked.connect(self._addSection)
        self.deleteButton.clicked.connect(self._deleteSection)
        self.applyButton.clicked.connect(self._onApplyClicked)

        spacing = StyleEngine.px("section_spacing_px")
        content = QWidget(self)
        column = EINvBoxLayout(content, spacing=spacing)
        column.setContentsMargins(spacing, spacing, spacing, spacing)
        column.addWidget(self.table, 1)
        column.addWidget(self.statusLabel)
        buttons = EINhBoxLayout()
        for button in (self.addButton, self.deleteButton):
            buttons.addWidget(button)
        buttons.addStretch(1)
        buttons.addWidget(self.applyButton)
        column.addLayout(buttons)
        self.layout.addWidget(content)
        self.resize(560, 320)

    def sections(self):
        return [tuple(section) for section in self._sections]

    def setSections(self, sections):
        """Show ``[(start, end, period)]`` (PC times) and emit them."""
        self._sections = [list(section) for section in sections]
        self.refresh()

    def refresh(self):
        """Fill the table from the sections, on the plot's current time axis, and emit them."""
        zero = self._zero()
        table = self.table
        table.blockSignals(True)
        table.setRowCount(len(self._sections))
        for row, (start, end, period) in enumerate(self._sections):
            for column, text in enumerate((f"{start - zero:.1f}", f"{end - zero:.1f}", f"{round(period, 3):g}")):
                table.setItem(row, column, QTableWidgetItem(text))
            count = QTableWidgetItem("")
            count.setFlags(count.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row, 3, count)
        table.blockSignals(False)
        self._updateButtons()
        self.sectionsChanged.emit(self.sections())

    def hasPendingChanges(self):
        """True if the sections would change the data, or some cannot be applied."""
        return self._changes or not self._valid

    def canApply(self):
        return self._valid

    def showPreview(self, counts, problems, changes):
        """Show the samples each section would have and mark, in red, the sections that
        cannot be applied, saying why.

        Args:
            counts: Samples per section, None for one with a problem.
            problems: Why each section cannot be applied, ``""`` for one that can.
            changes: Whether applying would change the data; the button says "Done"
                and only closes the window when it would not.
        """
        table = self.table
        errorColor = QColor(StyleEngine.token("c_status_error_bg"))
        errorColor.setAlpha(ERROR_ROW_ALPHA)
        errorBack = QBrush(errorColor)
        table.blockSignals(True)
        for row, (count, problem) in enumerate(zip(counts, problems)):
            table.item(row, 3).setText("-" if count is None else str(count))
            for column in range(table.columnCount()):
                item = table.item(row, column)
                item.setData(Qt.ItemDataRole.BackgroundRole, errorBack if problem else None)
        table.blockSignals(False)
        self.statusLabel.setText("\n".join(f"Section {row + 1}: {problem}"
                                           for row, problem in enumerate(problems) if problem))
        self._valid = not any(problems)
        self._changes = changes
        self.applyButton.setEnabled(self._valid)
        self.applyButton.setText("Done" if self._valid and not changes else "Resample")

    def _onApplyClicked(self):
        if self._changes:
            self.applyRequested.emit(self.sections())
        else:
            self.close()

    def _onItemChanged(self, item):
        try:
            value = float(item.text().replace(",", "."))
        except ValueError:
            value = math.nan
        row, column, sections = item.row(), item.column(), self._sections
        if column == 2:
            if value > 0:
                sections[row][2] = value
        elif math.isfinite(value):
            t = value + self._zero()
            # A boundary moves between its neighbours only, and moves the adjacent section's too.
            if column == 0 and (sections[row - 1][0] if row > 0 else -math.inf) < t < sections[row][1]:
                sections[row][0] = t
                if row > 0:
                    sections[row - 1][1] = t
            elif column == 1 and sections[row][0] < t < (sections[row + 1][1] if row + 1 < len(sections) else math.inf):
                sections[row][1] = t
                if row + 1 < len(sections):
                    sections[row + 1][0] = t
        selected = self._targetRow()
        self.refresh()  # also undoes a rejected value
        self.table.selectRow(selected)

    def _targetRow(self):
        """The selected section, or the last one."""
        rows = {index.row() for index in self.table.selectedIndexes()}
        return min(rows) if rows else len(self._sections) - 1

    def _addSection(self):
        row = self._targetRow()
        start, end, period = self._sections[row]
        middle = (start + end) / 2
        self._sections[row][1] = middle
        self._sections.insert(row + 1, [middle, end, period])
        self.refresh()
        self.table.selectRow(row + 1)

    def _deleteSection(self):
        row = self._targetRow()
        if row == 0:
            return
        self._sections[row - 1][1] = self._sections[row][1]
        del self._sections[row]
        self.refresh()
        self.table.selectRow(row - 1)

    def _updateButtons(self):
        self.deleteButton.setEnabled(len(self._sections) > 1 and self._targetRow() > 0)

    def showEvent(self, event):
        super().showEvent(event)
        self.visibilityChanged.emit(True)
        self.refresh()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.visibilityChanged.emit(False)


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
