from PyQt6.QtWidgets import QWidget
from qfluentwidgets import FluentIcon, NavigationItemPosition

from einstudio.layouts import EINdocPage, EINnavbarLayout, EINpage, EINstackPage
from einstudio.tools.styleengine import StyleEngine
from einstudio.widgets import (
    EINbodyLabel, EINbutton, EINcaptionLabel, EINcardWidget, EINcheckBox, EINdoubleSpinBox, EINdropDown,
    EINhBoxLayout, EINlineEdit, EINlogDisplayWidget, EINoptionRow, EINplotWidget, EINspinBox, EINstatusLight,
    EINtitleLabel, EINvBoxWidget, asCard,
)


def _named(widget, name):
    widget.setObjectName(name)
    return widget


def _row(title, *widgets, content=None):
    row = EINoptionRow(title, content)
    for widget in widgets:
        row.addTrailingWidget(widget)
    return row


def _columns(*columns):
    """Equal-width columns side by side, each a list of cards stacked from the top."""
    spacing = StyleEngine.px("section_spacing_px")
    # A plain QWidget, as in EINstackPage: EINhBoxWidget's stylesheet would reach the cards.
    row = QWidget()
    layout = EINhBoxLayout(row, spacing=spacing)
    for cards in columns:
        column = EINvBoxWidget(spacing=spacing)
        for card in cards:
            column.addWidget(card)
        column.addStretch(1)
        layout.addWidget(column, 1)
    return row


class MainWidget(EINnavbarLayout):
    """Pages behind the navigation bar.

    Page "Acquisition" (rows):
        The live plot, full width
        "Connection" over "Acquisition" | "Display and markers" over "Save"
    Page "Correction" (rows):
        The data's plot, full width
        "Tracer" (the isotope) | "Data"
        "Correction" (PET start, background) | "Calibration and export"
    Page "Calibration" (rows):
        The calibration run's plot, full width
        "Calibration run" | "Calibration factor"
    Page "Log": the log
    Page "Docs" (at the bottom of the bar): the manual built from doc/source
    """

    def __init__(self, options=None, instrumentConfig=None):
        super().__init__(options, instrumentConfig)

        self._makeAcquisitionPage()
        self._makeCorrectionPage()
        self._makeCalibrationPage()
        self._makeLogPage()
        self.addPage(EINdocPage(docName="docView"), FluentIcon.HELP, "Docs", NavigationItemPosition.BOTTOM)

    ###############################################################################
    # Pages                                                                       #
    ###############################################################################

    def _makeAcquisitionPage(self):
        plotWidget = _named(EINplotWidget(xLabel="Time (s)", yLabel="Counts per second"), "plotWidget")

        page = EINpage("acquisitionPage")
        page.addWidget(asCard(plotWidget), 1)
        page.addWidget(_columns([self._makeConnectionCard(), self._makeAcquisitionCard()],
                                [self._makeDisplayCard(), self._makeSaveCard()]))
        self.addPage(page, FluentIcon.PLAY, "Acquisition")

    def _makeCorrectionPage(self):
        plot = _named(EINplotWidget(xLabel="Time from PET start (s)", yLabel="Coincidences (counts/s)"),
                      "correctionPlot")
        page = EINpage("correctionPage")
        page.addWidget(asCard(plot), 1)
        page.addWidget(_columns([self._makeIsotopeCard()], [self._makeCorrectionDataCard()]))
        page.addWidget(_columns([self._makeCorrectionCard()], [self._makeCalibrationFactorCard()]))
        self.addPage(page, FluentIcon.EDIT, "Correction")

    def _makeCalibrationPage(self):
        plot = _named(EINplotWidget(xLabel="Time from run start (s)", yLabel="Coincidences (counts/s)"),
                      "calibrationPlot")
        page = EINpage("calibrationPage")
        page.addWidget(asCard(plot), 1)
        page.addWidget(_columns([self._makeCalibrationRunCard()], [self._makeCalibrationCard()]))
        self.addPage(page, FluentIcon.SPEED_MEDIUM, "Calibration")

    def _makeLogPage(self):
        page = EINstackPage("logPage", title="Log")
        page.addWidget(EINcardWidget(content=_named(EINlogDisplayWidget(), "logDisplayWidget")), stretch=1)
        self.addPage(page, FluentIcon.HISTORY, "Log")

    ###############################################################################
    # Acquisition page                                                            #
    ###############################################################################

    def _makeConnectionCard(self):
        hostEdit = _named(EINlineEdit(length="med"), "hostEdit")
        portSpin = _named(EINspinBox(length="vshort"), "portSpin")
        portSpin.setRange(1, 65535)
        statusLight = _named(EINstatusLight("Disconnected"), "statusLight")
        connectButton = _named(EINbutton("Connect", role="primary", length="short"), "connectButton")

        card = EINcardWidget("Connection")
        card.addRow(_row("Address", hostEdit, portSpin, statusLight, connectButton))
        return card

    def _makeAcquisitionCard(self):
        # Seconds per sample: qrate n reports every n x 100 ms, n = 1..100 (0.1 to 10 s).
        sampleRateDropdown = _named(EINdropDown(length="short"), "sampleRateDropdown")
        sampleRateDropdown.addItems(["0.1", "1", "2", "5", "10"])
        endModeDropdown = _named(EINdropDown(length="short"), "endModeDropdown")
        endModeDropdown.addItems(["Manual", "Time"])
        durationSpin = _named(EINdoubleSpinBox(length="short"), "durationSpin")
        durationSpin.setRange(0.1, 1440.0)
        durationSpin.setDecimals(1)
        runButton = _named(EINbutton("Start", role="primary", length="short"), "runButton")
        elapsedLabel = _named(EINbodyLabel("0:00:00"), "elapsedLabel")

        card = EINcardWidget("Acquisition")
        card.addRow(_row("Sample rate", sampleRateDropdown, EINbodyLabel("s")))
        card.addRow(_row("End by", endModeDropdown, durationSpin, EINbodyLabel("min")))
        card.addRow(_row("Run", elapsedLabel, runButton))
        return card

    def _makeSaveCard(self):
        card = EINcardWidget("Save")
        card.addRow(_row("Raw data", _named(EINbutton("Save...", length="short"), "saveRawButton"),
                         content="Counts as CSV or .crv"))
        card.addRow(_row("Events", _named(EINbutton("Save...", length="short"), "saveEventsButton"),
                         content="Marks and connection events as CSV"))
        return card

    def _makeDisplayCard(self):
        markEdit = _named(EINlineEdit(length="stretch"), "markEdit")
        markEdit.setPlaceholderText("Injection, blood sample, ...")
        markButton = _named(EINbutton("Mark", length="short"), "markButton")
        card = EINcardWidget("Display and markers")
        card.addRow(_row("Show in plot",
                         _named(EINcheckBox("Coincidences"), "showCoincidencesCheck"),
                         _named(EINcheckBox("Singles 1"), "showSingles1Check"),
                         _named(EINcheckBox("Singles 2"), "showSingles2Check")))
        card.addRow(_row("Add marker", markEdit, markButton))
        return card

    ###############################################################################
    # Correction page                                                             #
    ###############################################################################

    def _makeIsotopeCard(self):
        isotopeDropdown = _named(EINdropDown(length="short"), "isotopeDropdown")
        halfLifeSpin = _named(EINdoubleSpinBox(length="short"), "halfLifeSpin")
        halfLifeSpin.setRange(0.01, 1e6)
        halfLifeSpin.setDecimals(3)
        branchingSpin = _named(EINdoubleSpinBox(length="short"), "branchingSpin")
        branchingSpin.setRange(0.001, 1.0)
        branchingSpin.setDecimals(4)
        branchingSpin.setSingleStep(0.01)
        card = EINcardWidget("Tracer")
        card.addRow(_row("Isotope", isotopeDropdown, EINbodyLabel("Half-life"), halfLifeSpin, EINbodyLabel("min"),
                         EINbodyLabel("Branching ratio"), branchingSpin))
        return card

    def _makeCorrectionCard(self):
        petStartEdit = _named(EINlineEdit(length="short"), "petStartEdit")
        petStartEdit.setPlaceholderText("HH:MM:SS")
        petSelectButton = _named(EINbutton("Select", length="short"), "petSelectButton")
        backgroundModeDropdown = _named(EINdropDown(length="long"), "backgroundModeDropdown")
        backgroundModeDropdown.addItems(["Mean before PET", "Fixed value"])
        backgroundSpin = _named(EINdoubleSpinBox(length="short"), "backgroundSpin")
        backgroundSpin.setRange(0.0, 1e7)
        backgroundSpin.setDecimals(2)
        card = EINcardWidget("Correction")
        card.addRow(_row("PET scan start", petStartEdit, petSelectButton,
                         content="PC clock, synchronised with the PET; Select: click the plot"))
        card.addRow(_row("Background", backgroundModeDropdown, backgroundSpin, EINbodyLabel("counts/s")))
        return card

    def _makeCalibrationFactorCard(self):
        cfSpin = _named(EINdoubleSpinBox(length="short"), "cfSpin")
        cfSpin.setRange(0.0, 1e6)
        cfSpin.setDecimals(6)
        applyButton = _named(EINbutton("Apply", role="primary", length="short"), "applyCorrectionButton")
        saveButton = _named(EINbutton("Save...", length="short"), "saveCorrectedButton")

        card = EINcardWidget("Calibration and export")
        card.addRow(_row("Calibration factor", cfSpin, EINbodyLabel("kBq/cc per count")))
        card.addRow(_row("Corrected data", applyButton, saveButton,
                         content="PMOD blood (.bld), PMOD TAC (.tac) or CSV"))
        return card

    def _makeCorrectionDataCard(self):
        correctionFileLabel = _named(EINcaptionLabel("No data loaded"), "correctionFileLabel")
        correctionFileLabel.setWordWrap(True)
        card = EINcardWidget("Data")
        card.addRow(_row("Acquisition", correctionFileLabel,
                         _named(EINbutton("Current", length="short"), "useCurrentDataButton"),
                         _named(EINbutton("Load...", length="short"), "loadCorrectionDataButton")))
        return card

    ###############################################################################
    # Calibration page                                                            #
    ###############################################################################

    def _makeCalibrationRunCard(self):
        calibrationFileLabel = _named(EINcaptionLabel("No run loaded"), "calibrationFileLabel")
        calibrationFileLabel.setWordWrap(True)
        card = EINcardWidget("Calibration run")
        card.addRow(_row("Run", calibrationFileLabel,
                         _named(EINbutton("Current", length="short"), "useCurrentCalibrationButton"),
                         _named(EINbutton("Load...", length="short"), "loadCalibrationButton")))
        card.addRow(_row("Background window", _named(EINbodyLabel("-"), "backgroundWindowLabel"),
                         content="Drag the grey region in the plot, before the step"))
        card.addRow(_row("Plateau window", _named(EINbodyLabel("-"), "plateauWindowLabel"),
                         content="Drag the coloured region in the plot, after the step"))
        return card

    def _makeCalibrationCard(self):
        referenceEdit = _named(EINlineEdit(length="short"), "calibrationReferenceEdit")
        referenceEdit.setPlaceholderText("HH:MM:SS")
        activitySpin = _named(EINdoubleSpinBox(length="short"), "activitySpin")
        activitySpin.setRange(0.0, 1e7)
        activitySpin.setDecimals(3)

        card = EINcardWidget("Calibration factor")
        card.addRow(_row("PET reference time", referenceEdit,
                         content="Time the PET activity is decay-corrected to; the run start when loaded"))
        card.addRow(_row("PET activity", activitySpin, EINbodyLabel("kBq/cc")))
        card.addRow(_row("Isotope", _named(EINbodyLabel("-"), "calibrationIsotopeLabel"),
                         content="Set on the Correction page"))
        # The description says why there is no result, or what Apply does.
        card.addRow(_named(_row("Result", _named(EINtitleLabel("-"), "calibrationResultLabel"),
                                _named(EINbutton("Apply", role="primary", length="short"), "applyCalibrationButton"),
                                content="Load a calibration run"), "calibrationResultRow"))
        return card
