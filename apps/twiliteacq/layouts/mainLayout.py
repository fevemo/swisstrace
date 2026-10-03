from qfluentwidgets import FluentIcon, NavigationItemPosition

from einstudio.layouts import EINdocPage, EINnavbarLayout, EINstackPage
from einstudio.widgets import (
    EINbutton, EINcardWidget, EINlogDisplayWidget, EINoptionsWidget, EINplotWidget, EINresultsTable, EINrow,
    EINstatusLight,
)


class MainWidget(EINnavbarLayout):
    """Several pages of stacked cards behind the navigation bar.

    Page "Acquisition" (EINstackPage, two columns and a footer):
        Left column: "Run" card, "Acquisition" options
        Right column: the plot, filling the column
        Footer: the log, across both columns
    Page "Settings" (EINstackPage with a title, two columns): "Display" | "Logging" options
    Page "Results" (EINstackPage with a title): statistics of the last run
    Page "Docs" (EINdocPage, at the bottom of the bar): the manual built from doc/source
    """

    def __init__(self, options=None, instrumentConfig=None):
        super().__init__(options, instrumentConfig)

        self._makeAcquisitionPage()
        self._makeSettingsPage()
        self._makeResultsPage()
        self.addPage(EINdocPage(docName="docView"), FluentIcon.HELP, "Docs", NavigationItemPosition.BOTTOM)

    ###############################################################################
    # Pages                                                                       #
    ###############################################################################

    def _makeAcquisitionPage(self):
        plotWidget = EINplotWidget(xLabel="Sample", yLabel="Signal")
        plotWidget.setObjectName("plotWidget")

        logDisplayWidget = EINlogDisplayWidget()
        logDisplayWidget.setObjectName("logDisplayWidget")
        logCard = EINcardWidget(content=logDisplayWidget)
        logCard.setFixedHeight(self.config.logHeight)

        # Every page needs a unique name: it is the page's key in the navigation bar.
        # The page puts every widget that is not a card into one.
        page = EINstackPage("acquisitionPage", columns=2)
        page.addWidget(self._makeRunCard(), column=0)
        page.addWidget(EINoptionsWidget(self.options, subset="acquisition", title="Acquisition"), column=0)
        page.addWidget(plotWidget, stretch=1, column=1)
        page.addFooterWidget(logCard)
        self.addPage(page, FluentIcon.PLAY, "Acquisition")

    def _makeSettingsPage(self):
        page = EINstackPage("settingsPage", title="Settings", columns=2)
        page.addWidget(EINoptionsWidget(self.options, subset="display", title="Display"), column=0)
        page.addWidget(EINoptionsWidget(self.options, subset="logging", title="Logging"), column=1)
        self.addPage(page, FluentIcon.SETTING, "Settings")

    def _makeResultsPage(self):
        # The row labels are the statistics Model.finishRun() returns.
        resultsTable = EINresultsTable(
            rowLabels=["Samples", "Mean", "Std. dev.", "Minimum", "Maximum"],
            colLabels=["Last run"],
        )
        resultsTable.setObjectName("resultsTable")

        page = EINstackPage("resultsPage", title="Results")
        page.addWidget(resultsTable)
        self.addPage(page, FluentIcon.DOCUMENT, "Results")

    ###############################################################################
    # Cards                                                                       #
    ###############################################################################

    def _makeRunCard(self):
        statusLight = EINstatusLight("Idle")
        statusLight.setObjectName("statusLight")

        startButton = EINbutton("Start", role="primary", length="short")
        startButton.setObjectName("startButton")

        stopButton = EINbutton("Stop", length="short")
        stopButton.setObjectName("stopButton")

        runRow = EINrow()
        runRow.addWidget(statusLight)
        runRow.addStretch(1)
        runRow.addWidget(startButton)
        runRow.addWidget(stopButton)

        runCard = EINcardWidget("Run")
        runCard.addRow(runRow)
        return runCard
