import os

from PyQt6.QtCore import QUrl

from einstudio.tools.einview import EINview
from einstudio.widgets import (
    EINbutton, EINdocWidget, EINlogDisplayWidget, EINplotWidget, EINresultsTable, EINstatusLight,
)


class View(EINview):
    """Reads the options when a run starts, redraws the plot on every reading, fills the results.

    The option inputs (``<name>_edit``) are added to ``self.widgets`` automatically from
    options.yaml; only the widgets the layout names itself are listed here.
    """

    def makeWidgetsList(self):
        self.expectedWidgets = [
            ('statusLight',      EINstatusLight),
            ('startButton',      EINbutton),
            ('stopButton',       EINbutton),
            ('plotWidget',       EINplotWidget),
            ('logDisplayWidget', EINlogDisplayWidget),
            ('resultsTable',     EINresultsTable),
            ('docView',          EINdocWidget),
        ]

    def configure(self):
        self.setMinimumSize(self.config.mainWindowMinSizeX, self.config.mainWindowMinSizeY)
        self.setWindowTitle(self.config.mainWindowTitle)
        self.widgets.stopButton.setEnabled(False)
        self.widgets.statusLight.setStatus("ready")

        # The curve is a display object kept between signals, so it lives in self.handles.
        self.handles.curve = self.widgets.plotWidget.plot([], [])
        self._showGrid(self.widgets.showGrid_edit.isChecked())
        self._setAutoRange(self.widgets.autoRange_edit.isChecked())

        # The manual exists once it has been built (see doc/source/conf.py).
        indexFile = os.path.join(self.configManager.mainConfig.docPath, "index.html")
        if os.path.isfile(indexFile):
            self.widgets.docView.updateHTML(QUrl.fromLocalFile(indexFile).toString())

    def bindWidgetsActions(self):
        self.widgets.startButton.clicked.connect(self._onStart)
        self.widgets.stopButton.clicked.connect(self.viewModel.stopAcquisition)
        self.widgets.showGrid_edit.checkedChanged.connect(self._showGrid)
        self.widgets.autoRange_edit.checkedChanged.connect(self._setAutoRange)

    def bindSignals(self):
        self.viewModel.traceUpdated.connect(self.handles.curve.setData)
        self.viewModel.runningChanged.connect(self._onRunningChanged)
        self.viewModel.runFinished.connect(self._showResults)
        self.logger.onLogUpdate(self.widgets.logDisplayWidget.updateLog)

    def _onStart(self):
        units = self.widgets.units_edit.text()
        self.widgets.plotWidget.setLabel("left", f"Signal ({units})")
        logEvery = self.widgets.logEvery_edit.value() if self.widgets.logReadings_edit.isChecked() else 0
        self.viewModel.startAcquisition(
            interval_ms=self.widgets.sampleInterval_edit.value(),
            shape=self.widgets.signalShape_edit.currentText(),
            noiseLevel=self.widgets.noiseLevel_edit.value(),
            windowSize=self.widgets.windowSize_edit.value(),
            units=units,
            logEvery=logEvery,
        )

    def _onRunningChanged(self, running):
        self.widgets.startButton.setEnabled(not running)
        self.widgets.stopButton.setEnabled(running)
        if running:
            self.widgets.statusLight.setStatus("running", "Running")
        else:
            self.widgets.statusLight.setStatus("ready", "Idle")

    def _showResults(self, stats):
        self.widgets.resultsTable.setData({name: {"Last run": value} for name, value in stats.items()})

    def _showGrid(self, visible):
        self.widgets.plotWidget.showGrid(x=visible, y=visible)

    def _setAutoRange(self, enabled):
        if enabled:
            self.widgets.plotWidget.enableAutoRange()
        else:
            self.widgets.plotWidget.disableAutoRange()
