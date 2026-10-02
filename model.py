import numpy as np


class Model:
    """Simulated detector: one reading per call, the latest readings kept in a rolling window.

    Replace the body of ``acquire()`` with a call to your instrument; the ViewModel and
    the View only use the methods below.
    """

    def __init__(self, logger, instrumentConfig):
        self.logger = logger
        self.baseline = instrumentConfig["detector"]["baseline"]
        self.rng = np.random.default_rng()
        self.shape = "Random walk"
        self.noiseLevel = 1.0
        self.windowSize = 300
        self.sampleCount = 0
        self.readings = np.array([])
        self.lastRunStats = {}

    def startRun(self, shape, noiseLevel, windowSize):
        """Clear the readings and set the signal parameters of a new run."""
        self.shape = shape
        self.noiseLevel = noiseLevel
        self.windowSize = windowSize
        self.sampleCount = 0
        self.readings = np.array([])
        self.logger.info(f"Run started: {shape}, noise {noiseLevel}, window of {windowSize} samples.")

    def acquire(self):
        """Take one simulated reading, keep it in the window and return it."""
        phase = 2 * np.pi * self.sampleCount / 100
        if self.shape == "Sine":
            clean = self.baseline + 10 * np.sin(phase)
        elif self.shape == "Square":
            clean = self.baseline + 10 * np.sign(np.sin(phase))
        else:
            previous = self.readings[-1] if self.readings.size else self.baseline
            # A random walk pulled back towards the baseline, so it never drifts away.
            clean = previous + 0.05 * (self.baseline - previous)
        value = clean + self.rng.normal(0.0, self.noiseLevel)
        self.readings = np.append(self.readings, value)[-self.windowSize:]
        self.sampleCount += 1
        return value

    def getTrace(self):
        """Return ``(sampleNumbers, readings)`` of the current window."""
        firstSample = self.sampleCount - self.readings.size
        return np.arange(firstSample, self.sampleCount), self.readings.copy()

    def finishRun(self):
        """Compute, keep and return the statistics of the readings in the window."""
        self.lastRunStats = {
            "Samples": self.sampleCount,
            "Mean": float(np.mean(self.readings)),
            "Std. dev.": float(np.std(self.readings)),
            "Minimum": float(np.min(self.readings)),
            "Maximum": float(np.max(self.readings)),
        }
        return self.lastRunStats
