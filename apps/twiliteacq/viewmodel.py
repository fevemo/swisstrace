from PyQt6.QtCore import QObject, QTimer, pyqtSignal


class ViewModel(QObject):
    """Runs the acquisition timer and turns each Model reading into signals for the View."""

    # Emitted after every reading with (sampleNumbers, readings) of the current window.
    traceUpdated = pyqtSignal(object, object)
    # Emitted with True when a run starts and False when it stops.
    runningChanged = pyqtSignal(bool)
    # Emitted when a run stops, with the statistics of its readings ({name: value}).
    runFinished = pyqtSignal(dict)

    def __init__(self, model, logger):
        super().__init__()
        self.model = model
        self.logger = logger
        self.units = "mV"
        self.logEvery = 0
        self.timer = QTimer()
        self.timer.timeout.connect(self._onTick)

    def startAcquisition(self, interval_ms, shape, noiseLevel, windowSize, units, logEvery):
        """Start a run; ``logEvery`` writes every n-th reading to the log, ``0`` none."""
        self.units = units
        self.logEvery = logEvery
        self.model.startRun(shape, noiseLevel, windowSize)
        self.timer.setInterval(interval_ms)
        self.runningChanged.emit(True)
        self._onTick()
        self.timer.start()

    def stopAcquisition(self):
        self.timer.stop()
        stats = self.model.finishRun()
        self.logger.info(f"Run stopped after {stats['Samples']} readings, mean {stats['Mean']:.2f} {self.units}.")
        self.runningChanged.emit(False)
        self.runFinished.emit(stats)

    def _onTick(self):
        value = self.model.acquire()
        self.traceUpdated.emit(*self.model.getTrace())
        if self.logEvery and self.model.sampleCount % self.logEvery == 0:
            self.logger.debug(f"Reading {self.model.sampleCount}: {value:.2f} {self.units}")
