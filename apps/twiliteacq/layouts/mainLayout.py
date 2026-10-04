from qfluentwidgets import FluentIcon, NavigationItemPosition

from einstudio.layouts import EINdocPage, EINnavbarLayout, EINstackPage
from einstudio.widgets import (
    EINbodyLabel, EINbutton, EINcaptionLabel, EINcardWidget, EINcheckBox, EINdoubleSpinBox, EINdropDown,
    EINlineEdit, EINlogDisplayWidget, EINoptionRow, EINplotWidget, EINspinBox, EINstatusLight, EINswitch,
    EINtitleLabel,
)


def _named(widget, name):
    widget.setObjectName(name)
    return widget


def _row(title, *widgets, content=None):
    row = EINoptionRow(title, content)
    for widget in widgets:
        row.addTrailingWidget(widget)
    return row


class MainWidget(EINnavbarLayout):
    """Pages behind the navigation bar.

    Page "Acquisition" (two columns, log as footer):
        Left: "Connection", "Acquisition" and "Mark event" cards
        Right: the "Display" card, the live plot
    Page "Correction" (two columns): "Correction" | "Export"
    Page "Calibration" (two columns): the controls | the calibration run's plot
    Page "Docs" (at the bottom of the bar): the manual built from doc/source
    """

    def __init__(self, options=None, instrumentConfig=None):
        super().__init__(options, instrumentConfig)

        self._makeAcquisitionPage()
        self._makeCorrectionPage()
        self._makeCalibrationPage()
        self.addPage(EINdocPage(docName="docView"), FluentIcon.HELP, "Docs", NavigationItemPosition.BOTTOM)

    ###############################################################################
    # Pages                                                                       #
    ###############################################################################

    def _makeAcquisitionPage(self):
        plotWidget = _named(EINplotWidget(xLabel="Time (s)", yLabel="Counts"), "plotWidget")

        logCard = EINcardWidget(content=_named(EINlogDisplayWidget(), "logDisplayWidget"))
        logCard.setFixedHeight(self.config.logHeight)

        page = EINstackPage("acquisitionPage", columns=2)
        page.addWidget(self._makeConnectionCard(), column=0)
        page.addWidget(self._makeAcquisitionCard(), column=0)
        page.addWidget(self._makeMarkCard(), column=0)
        page.addWidget(self._makeDisplayCard(), column=1)
        page.addWidget(plotWidget, stretch=1, column=1)
        page.addFooterWidget(logCard)
        self.addPage(page, FluentIcon.PLAY, "Acquisition")

    def _makeCorrectionPage(self):
        page = EINstackPage("correctionPage", title="Correction and export", columns=2)
        page.addWidget(self._makeCorrectionCard(), column=0)
        page.addWidget(self._makeExportCard(), column=1)
        self.addPage(page, FluentIcon.EDIT, "Correction")

    def _makeCalibrationPage(self):
        plot = _named(EINplotWidget(xLabel="Time from run start (s)", yLabel="Coincidences"), "calibrationPlot")
        page = EINstackPage("calibrationPage", title="Calibration", columns=2)
        page.addWidget(self._makeCalibrationCard(), column=0)
        page.addWidget(plot, stretch=1, column=1)
        self.addPage(page, FluentIcon.SPEED_HIGH, "Calibration")

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
        card.addRow(_row("Address", hostEdit, portSpin))
        card.addRow(_row("Status", statusLight, connectButton))
        return card

    def _makeAcquisitionCard(self):
        qrateSpin = _named(EINspinBox(length="vshort"), "qrateSpin")
        qrateSpin.setRange(1, 100)
        endModeDropdown = _named(EINdropDown(length="short"), "endModeDropdown")
        endModeDropdown.addItems(["Manual", "Time"])
        durationSpin = _named(EINdoubleSpinBox(length="short"), "durationSpin")
        durationSpin.setRange(0.1, 1440.0)
        durationSpin.setDecimals(1)
        startButton = _named(EINbutton("Start", role="primary", length="short"), "startButton")
        stopButton = _named(EINbutton("Stop", length="short"), "stopButton")
        elapsedLabel = _named(EINbodyLabel("0:00:00"), "elapsedLabel")
        samplesLabel = _named(EINbodyLabel("0"), "samplesLabel")

        card = EINcardWidget("Acquisition")
        card.addRow(_row("Report every", qrateSpin, EINbodyLabel("x 100 ms"),
                         content="qrate: each sample counts over this period, in counts per second"))
        card.addRow(_row("End by", endModeDropdown, durationSpin, EINbodyLabel("min")))
        card.addRow(_row("Run", startButton, stopButton))
        card.addRow(_row("Elapsed", elapsedLabel))
        card.addRow(_row("Samples", samplesLabel))
        return card

    def _makeMarkCard(self):
        markEdit = _named(EINlineEdit(length="stretch"), "markEdit")
        markEdit.setPlaceholderText("Injection, blood sample, ...")
        markButton = _named(EINbutton("Mark", length="short"), "markButton")
        card = EINcardWidget("Mark event")
        card.addRow(_row("", markEdit, markButton))
        return card

    def _makeDisplayCard(self):
        card = EINcardWidget("Display")
        card.addRow(_row("Curves",
                         _named(EINcheckBox("Coincidences"), "showCoincidencesCheck"),
                         _named(EINcheckBox("Singles 1"), "showSingles1Check"),
                         _named(EINcheckBox("Singles 2"), "showSingles2Check")))
        card.addRow(_row("Corrected", _named(EINswitch(), "correctedSwitch"),
                         content="Coincidences as activity concentration (kBq/cc)"))
        return card

    ###############################################################################
    # Correction page                                                             #
    ###############################################################################

    def _makeCorrectionCard(self):
        isotopeDropdown = _named(EINdropDown(length="short"), "isotopeDropdown")
        halfLifeSpin = _named(EINdoubleSpinBox(length="short"), "halfLifeSpin")
        halfLifeSpin.setRange(0.01, 1e6)
        halfLifeSpin.setDecimals(3)
        branchingSpin = _named(EINdoubleSpinBox(length="short"), "branchingSpin")
        branchingSpin.setRange(0.001, 1.0)
        branchingSpin.setDecimals(4)
        branchingSpin.setSingleStep(0.01)
        petStartEdit = _named(EINlineEdit(length="vlong"), "petStartEdit")
        petStartEdit.setPlaceholderText("YYYY-MM-DD HH:MM:SS")
        petNowButton = _named(EINbutton("Now", length="vshort"), "petNowButton")
        backgroundModeDropdown = _named(EINdropDown(length="long"), "backgroundModeDropdown")
        backgroundModeDropdown.addItems(["Mean before PET start", "Fixed value"])
        backgroundSpin = _named(EINdoubleSpinBox(length="short"), "backgroundSpin")
        backgroundSpin.setRange(0.0, 1e7)
        backgroundSpin.setDecimals(2)
        cfSpin = _named(EINdoubleSpinBox(length="short"), "cfSpin")
        cfSpin.setRange(0.0, 1e6)
        cfSpin.setDecimals(6)
        applyButton = _named(EINbutton("Apply", role="primary", length="short"), "applyCorrectionButton")

        card = EINcardWidget("Correction")
        card.addRow(_row("Isotope", isotopeDropdown))
        card.addRow(_row("Half-life", halfLifeSpin, EINbodyLabel("min"), content="Editable for a custom isotope"))
        card.addRow(_row("Branching ratio", branchingSpin))
        card.addRow(_row("PET scan start", petStartEdit, petNowButton, content="PC clock, synchronised with the PET"))
        card.addRow(_row("Background", backgroundModeDropdown, backgroundSpin))
        card.addRow(_row("Calibration factor", cfSpin, EINbodyLabel("kBq/cc per count")))
        card.addRow(_row("", applyButton))
        return card

    def _makeExportCard(self):
        exportFileLabel = _named(EINcaptionLabel("No acquisition yet"), "exportFileLabel")
        exportFileLabel.setWordWrap(True)
        card = EINcardWidget("Export")
        card.addRow(_row("Acquisition", exportFileLabel,
                         _named(EINbutton("Choose...", length="short"), "chooseExportFileButton")))
        card.addRow(_row("CSV", _named(EINbutton("Export", length="short"), "exportCsvButton"),
                         content="Raw counts, plus corrected values when the PET start is set"))
        card.addRow(_row("PSAMPLE .crv", _named(EINbutton("Export", length="short"), "exportCrvButton"),
                         content="Provisional format until compared with a real .crv"))
        card.addRow(_row("PMOD blood", _named(EINbutton("Export", length="short"), "exportPmodButton"),
                         content="Corrected TAC: seconds and kBq/cc"))
        card.addRow(_row("Events", _named(EINbutton("Export", length="short"), "exportEventsButton")))
        return card

    ###############################################################################
    # Calibration page                                                            #
    ###############################################################################

    def _makeCalibrationCard(self):
        calibrationFileLabel = _named(EINcaptionLabel("No run loaded"), "calibrationFileLabel")
        calibrationFileLabel.setWordWrap(True)
        referenceEdit = _named(EINlineEdit(length="vlong"), "calibrationReferenceEdit")
        referenceEdit.setPlaceholderText("YYYY-MM-DD HH:MM:SS")
        activitySpin = _named(EINdoubleSpinBox(length="short"), "activitySpin")
        activitySpin.setRange(0.0, 1e7)
        activitySpin.setDecimals(3)

        card = EINcardWidget("Calibration factor")
        card.addRow(_row("Run", calibrationFileLabel,
                         _named(EINbutton("Load...", length="short"), "loadCalibrationButton")))
        card.addRow(_row("Background window", _named(EINbodyLabel("-"), "backgroundWindowLabel"),
                         content="Drag the grey region in the plot, before the step"))
        card.addRow(_row("Plateau window", _named(EINbodyLabel("-"), "plateauWindowLabel"),
                         content="Drag the coloured region in the plot, after the step"))
        card.addRow(_row("PET reference time", referenceEdit,
                         _named(EINbutton("Run start", length="short"), "referenceRunStartButton"),
                         content="Time the PET activity is decay-corrected to"))
        card.addRow(_row("PET activity", activitySpin, EINbodyLabel("kBq/cc")))
        card.addRow(_row("Isotope", _named(EINbodyLabel("-"), "calibrationIsotopeLabel"),
                         content="Set on the Correction page"))
        card.addRow(_row("", _named(EINbutton("Compute", role="primary", length="short"), "computeCalibrationButton")))
        card.addRow(_row("Result", _named(EINtitleLabel("-"), "calibrationResultLabel"),
                         _named(EINbutton("Use", length="short"), "useCalibrationButton")))
        return card
