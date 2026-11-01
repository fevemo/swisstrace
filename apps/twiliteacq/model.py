import math
import os
import threading
import time
from datetime import datetime

from pathlib import Path

import numpy as np
import yaml


class Model:
    """The twilite connection, the running acquisition, its file, and the correction settings.

    No Qt here: every method is a plain call, and :meth:`acquire` blocks until the
    acquisition ends, so the Model also runs from a script or a test. The driver is
    imported inside :meth:`connect`, so the app starts even when it is missing.
    """

    STATE_FILE = "state.yaml"

    def __init__(self, logger, instrumentConfig):
        self.logger = logger
        config = instrumentConfig["twilite"]
        self.host = config["host"]
        self.port = config["port"]
        self.timeout_s = config.get("timeout_s", 5.0)
        self.reconnectAttempts = config.get("reconnectAttempts", 3)
        self.dataDir = os.path.abspath(config.get("dataDir", "data"))
        self.rawLog = config.get("rawLog", True)
        self.simulate = config.get("simulate", False)
        self.simulatorConfig = config.get("simulator", {})
        self.appVersion = config.get("appVersion", "0.1.0")

        self.client = None
        self.simulator = None
        self.writer = None
        self.lastFile = None
        self.qrate = 10
        self._stopRequested = threading.Event()
        self._lock = threading.Lock()
        # Held by whoever talks to the device: an acquisition, a keepalive, a disconnect.
        self._ioLock = threading.Lock()
        self._clearTrace()

        self.isotopeName = "F-18"
        self.customHalfLife_s = 6586.2
        self.customBranchingRatio = 1.0
        self.petStart = None
        self.fixedBackground = None
        self.calibrationFactor = 1.0
        self.calibrationRun = None
        self.correctionData = None
        # True while correctionData has edits not saved yet.
        self.unsavedEdits = False

    ###########################################################################
    # Connection                                                              #
    ###########################################################################

    def connect(self, host=None, port=None):
        """Connect to the device (or start and connect to the simulator); return the banner."""
        from twilite import TwiliteClient

        if self.client is not None and self.client.connected:
            return self.client.banner
        if host is not None:
            self.host = host
        if port is not None:
            self.port = int(port)
        if self.simulate:
            self._startSimulator()
            host, port = "127.0.0.1", self.simulator.port
        else:
            host, port = self.host, self.port
        rawLog = None
        if self.rawLog:
            rawLog = os.path.join(self.dataDir, "rawlogs", datetime.now().strftime("%Y%m%d_%H%M%S") + "_raw.log")
        self.client = TwiliteClient(host, port, self.timeout_s, rawLog)
        banner = self.client.connect()
        self.logger.info(f"Connected to {host}:{port}: {banner.splitlines()[0] if banner else 'no banner'}")
        return banner

    def _startSimulator(self):
        if self.simulator is not None:
            return
        from twilite.sim import TwiliteSimulator

        sim = self.simulatorConfig
        self.simulator = TwiliteSimulator(
            scenario=sim.get("scenario", "bolus"), isotope=sim.get("isotope", "F-18"), port=sim.get("port", 0),
            idle_timeout_s=sim.get("idleTimeout_s", 19.0),
        )
        self.simulator.start_in_thread()
        self.logger.info(f"Simulated twilite ({self.simulator.scenario.name}) on port {self.simulator.port}")

    def disconnect(self):
        with self._ioLock:
            if self.client is not None:
                self.client.close()
                self.logger.info("Disconnected")
            self.client = None

    def keepAlive(self):
        """Keep an idle connection open; return False if the device has closed it.

        The twilite drops a connection after about 19 s without traffic at the prompt.
        Call this every few seconds while connected; it only talks to the device when
        the connection has been idle for ``KEEPALIVE_INTERVAL_S``, and does nothing
        during an acquisition, whose stream keeps the connection busy anyway.
        """
        from twilite import ConnectionLost
        from twilite.protocol import KEEPALIVE_INTERVAL_S

        if not self._ioLock.acquire(blocking=False):
            return True
        try:
            if self.client is None or not self.client.connected:
                return False
            if self.client.idle_s < KEEPALIVE_INTERVAL_S:
                return True
            try:
                self.client.keepalive()
            except ConnectionLost as error:
                self.logger.warning(f"Connection lost while idle: {error}")
                return False
            return True
        finally:
            self._ioLock.release()

    def isConnected(self):
        return self.client is not None and self.client.connected

    def banner(self):
        return self.client.banner if self.client is not None else ""

    def shutdown(self):
        """Disconnect and stop the simulator; for the app's exit."""
        self.requestStop()
        self.disconnect()
        if self.simulator is not None:
            self.simulator.stop()
            self.simulator = None

    ###########################################################################
    # Acquisition                                                             #
    ###########################################################################

    def acquire(self, qrate, endAfter_s=None, onEvent=None):
        """Acquire until :meth:`requestStop` or ``endAfter_s``; return the file written.

        Blocks. ``onEvent(kind, text)`` is called from this thread for connection
        problems. A stop requested before the acquisition gets going still
        ends it; the request is cleared when the acquisition ends. A lost connection is retried ``reconnectAttempts`` times;
        if that fails, the file is closed and :class:`ConnectionLost` is raised.
        """
        with self._ioLock:
            return self._acquire(qrate, endAfter_s, onEvent)

    def _acquire(self, qrate, endAfter_s=None, onEvent=None):
        from twilite import ConnectionLost

        if not self.isConnected():
            raise RuntimeError("Not connected")
        self.qrate = qrate
        self.lastFile = None
        self.client.set_query_rate(qrate)
        with self._lock:
            self._clearTrace()
        self.writer = self._openWriter(qrate)
        startMono = self.writer.start_mono
        self.logger.info(f"Acquisition started: {self.writer.path.name}, report every {qrate * 100} ms")

        attempts = 0
        try:
            while not self._stopRequested.is_set():
                try:
                    for sample in self.client.stream():
                        attempts = 0
                        self.writer.write_sample(sample)
                        with self._lock:
                            self._appendSample(sample, sample.t_mono - startMono)
                        if endAfter_s and sample.t_mono - startMono >= endAfter_s:
                            self._stopRequested.set()
                        if self._stopRequested.is_set():
                            # Also catches a stop requested just before stream() started.
                            self.client.request_stop()
                    break
                except ConnectionLost as error:
                    self._report(onEvent, "connection", f"lost: {error}")
                    with self._lock:
                        self._appendBreak()
                        self.lossCount += 1
                    while True:
                        attempts += 1
                        if self._stopRequested.is_set() or attempts > self.reconnectAttempts:
                            raise error
                        self.logger.warning(f"Connection lost; reconnecting, attempt {attempts} "
                                            f"of {self.reconnectAttempts}")
                        time.sleep(1.0)
                        try:
                            self.client.connect()
                            self.client.set_query_rate(qrate)
                            break
                        except ConnectionLost as retryError:
                            self.logger.warning(f"Reconnect failed: {retryError}")
                    self._report(onEvent, "connection", "reconnected")
        finally:
            self._stopRequested.clear()
            self.lastFile = self.writer.finish()
            self.logger.info(f"Acquisition saved: {self.lastFile} ({self.writer.sample_count} samples)")
            self.writer = None
        return str(self.lastFile)

    def _report(self, onEvent, kind, text):
        self.writer.write_event(kind, text)
        if onEvent is not None:
            onEvent(kind, text)

    def _openWriter(self, qrate):
        from twilite.storage import AcquisitionWriter

        return AcquisitionWriter(self.dataDir, {
            "device": f"{self.client.host}:{self.client.port}" + (" (simulator)" if self.simulate else ""),
            "firmware": self.client.banner,
            "report_rate": f"qrate {qrate} ({qrate * 100} ms)",
            "app_version": self.appVersion,
            **self._settingsMetadata(),
        })

    def requestStop(self):
        """End a running :meth:`acquire`; safe from any thread."""
        self._stopRequested.set()
        if self.client is not None and self.writer is not None:
            self.client.request_stop()

    def isAcquiring(self):
        return self.writer is not None

    def markEvent(self, text):
        """Store a user event in the running acquisition; return its time from the start."""
        writer = self.writer
        if writer is None:
            raise RuntimeError("No acquisition is running")
        record = writer.write_event("mark", text or "mark")
        self.logger.info(f"Event marked at {record.t_rel_s:.1f} s: {record.text}")
        return record.t_rel_s

    ###########################################################################
    # Live trace                                                              #
    ###########################################################################

    def _clearTrace(self):
        self.tRel, self.tWall, self.singles1, self.singles2, self.coincidences = [], [], [], [], []
        self.sampleCount = 0
        self.lossCount = 0

    def _appendSample(self, sample, tRel):
        self.tRel.append(tRel)
        self.tWall.append(sample.t_wall)
        self.singles1.append(float(sample.singles1))
        self.singles2.append(float(sample.singles2))
        self.coincidences.append(float(sample.coincidences))
        self.sampleCount += 1

    def _appendBreak(self):
        """A NaN point, so the plot shows a lost connection as a break in the line."""
        if self.tRel and not math.isnan(self.coincidences[-1]):
            self.tRel.append(self.tRel[-1])
            self.tWall.append(self.tWall[-1])
            for series in (self.singles1, self.singles2, self.coincidences):
                series.append(math.nan)

    def getTrace(self):
        """Return ``{"t", "singles1", "singles2", "coincidences"}`` arrays of the run so far."""
        with self._lock:
            return {
                "t": np.array(self.tRel),
                "singles1": np.array(self.singles1),
                "singles2": np.array(self.singles2),
                "coincidences": np.array(self.coincidences),
            }

    def getStats(self):
        with self._lock:
            latest = next((c for c in reversed(self.coincidences) if not math.isnan(c)), math.nan)
            elapsed = self.tRel[-1] if self.tRel else 0.0
            return {"elapsed_s": elapsed, "samples": self.sampleCount, "latest": latest,
                    "losses": self.lossCount}

    ###########################################################################
    # Correction                                                              #
    ###########################################################################

    def isotopeTable(self):
        """Return ``{name: (half-life in s, branching ratio)}`` of the tabulated isotopes."""
        from twilite import ISOTOPES

        return {name: (iso.half_life_s, iso.branching_ratio) for name, iso in ISOTOPES.items()}

    def isotope(self):
        return self.makeIsotope(self.isotopeName, self.customHalfLife_s, self.customBranchingRatio)

    @staticmethod
    def makeIsotope(name, customHalfLife_s=None, customBranchingRatio=None):
        """The tabulated isotope ``name``, or for "Custom" one with the given half-life (s) and branching ratio."""
        from twilite import Isotope, get_isotope

        if name == "Custom":
            return Isotope("Custom", customHalfLife_s, customBranchingRatio)
        return get_isotope(name)

    def setCorrection(self, isotopeName, petStart, fixedBackground, calibrationFactor,
                      customHalfLife_s=None, customBranchingRatio=None):
        """Set the correction; ``petStart`` in seconds since the epoch, ``fixedBackground`` None to measure it."""
        self.isotopeName = isotopeName
        if customHalfLife_s is not None:
            self.customHalfLife_s = customHalfLife_s
        if customBranchingRatio is not None:
            self.customBranchingRatio = customBranchingRatio
        self.isotope()  # validates
        self.petStart = petStart
        self.fixedBackground = fixedBackground
        self.calibrationFactor = calibrationFactor
        self.logger.info(f"Correction: {self.isotopeName}, PET start "
                         f"{datetime.fromtimestamp(petStart).isoformat(' ', 'seconds') if petStart else 'not set'}, "
                         f"background {'measured' if fixedBackground is None else fixedBackground}, "
                         f"CF {calibrationFactor:g}")

    def correctionSettings(self):
        from twilite.correction import CorrectionSettings

        if self.petStart is None:
            raise ValueError("Set the PET start time first")
        return CorrectionSettings(self.isotope(), self.petStart, self.fixedBackground, self.calibrationFactor)

    def currentFile(self):
        """File of the running acquisition, or else of the last one; None before any."""
        writer = self.writer
        if writer is not None:
            return str(writer.path)
        return str(self.lastFile) if self.lastFile is not None else None

    def loadCorrectionData(self, path):
        """Read the acquisition to correct; return ``(t_wall, coincidences)`` arrays.

        ``path`` may be the file of the running acquisition: every row written so far is read.
        """
        from twilite.storage import read_acquisition

        acq = read_acquisition(path)
        if len(acq) == 0:
            raise ValueError(f"{os.path.basename(path)} holds no samples")
        self.correctionData = acq
        self.unsavedEdits = False
        self.logger.info(f"Data to correct: {path} ({len(acq)} samples"
                         + (f", {len(acq.edits)} edits" if acq.edits else "") + ")")
        return np.array(acq.t_wall), np.array(acq.coincidences, dtype=float)

    def correctionArrays(self):
        """The loaded data as arrays: ``{"t", "coincidences", "interpolated", "start"}``.

        ``t`` is each sample's time (``twilite.storage.sample_times``: when its report
        arrived, or the middle of a resampled sample); ``start`` the PC time of the
        acquisition start.
        """
        from twilite.storage import sample_times

        acq = self.correctionData
        return {"t": np.array(sample_times(acq)),
                "coincidences": np.array(acq.coincidences, dtype=float),
                "interpolated": np.array(acq.interpolated, dtype=bool), "start": acq.t_wall[0] - acq.t_rel_s[0]}

    def measuredBackground(self, petStart):
        """Mean coincidence rate of the loaded data before ``petStart``; None if there is none."""
        from twilite.correction import background_before_start
        from twilite.storage import sample_times

        acq = self.correctionData
        if acq is None or petStart is None:
            return None
        try:
            return background_before_start([t - petStart for t in sample_times(acq)], acq.coincidences)
        except ValueError:
            return None

    def correctData(self):
        """Correct the loaded data; return ``(t from the PET start, kBq/cc, background used)``.

        Returns None while no data is loaded or the PET start is not set.
        """
        from twilite.correction import apply
        from twilite.storage import sample_times

        if self.correctionData is None or self.petStart is None:
            return None
        acq = self.correctionData
        t, activity, background = apply(self.correctionSettings(), sample_times(acq), acq.coincidences)
        return np.array(t), np.array(activity), background

    ###########################################################################
    # Editing the loaded data                                                 #
    ###########################################################################

    def cutPreview(self, start, end, nAverage):
        """What :meth:`cut` would put in place: ``(t, coincidences)`` arrays of the line from
        edge to edge, through the samples replaced."""
        from twilite.editing import plan_cut

        plan = plan_cut(self._editable(), start, end, nAverage)
        points = sorted([*zip(plan.times, plan.values["coincidences"]),
                         *((t, values["coincidences"]) for t, values in plan.edges)])
        t, values = zip(*points)
        return np.array(t), np.array(values)

    def cut(self, start, end, nAverage):
        """Replace the samples whose time is in ``[start, end]`` (PC times) by a line between their edges.

        The edge values are the means of ``nAverage`` samples on each side.
        """
        from twilite.editing import cut

        self._replaceData(cut(self._editable(), start, end, nAverage))

    def samplingSections(self):
        """How the loaded data is sampled: ``[(start, end, period)]``, PC times and seconds."""
        from twilite.editing import sampling_sections

        return [(s.start, s.end, s.period) for s in sampling_sections(self._editable())]

    def resamplePreview(self, sections):
        """What :meth:`resample` would make, as a dict:

        - ``t``, ``coincidences``: arrays of the merged samples only, the others stay as
          they are; NaN separates runs of them.
        - ``counts``: samples per section, None for a section that cannot be applied.
        - ``problems``: why each section cannot be applied, ``""`` if it can. Such a
          section is left out of the preview.
        - ``changes``: whether applying the sections that can be would change the data.
        """
        from twilite.editing import plan_resample, resample, section_problems
        from twilite.storage import sample_times

        acq = self._editable()
        sections = self._sections(sections)
        problems = section_problems(acq, sections)
        valid = [s for s, problem in zip(sections, problems) if not problem]
        plan = plan_resample(acq, valid)
        edited = resample(acq, valid, plan)
        validCounts = iter(plan.counts)
        counts = [None if problem else next(validCounts) for problem in problems]
        t, values = [], []
        for group, tSample, value in zip(plan.groups, sample_times(edited), edited.coincidences):
            if len(group) > 1:
                t.append(tSample)
                values.append(value)
            elif values and not math.isnan(values[-1]):
                t.append(t[-1])
                values.append(math.nan)
        return {"t": np.array(t), "coincidences": np.array(values, dtype=float), "counts": counts,
                "problems": problems, "changes": plan.changes}

    def resample(self, sections):
        """Resample the loaded data; ``sections`` is ``[(start, end, period)]``, PC times and seconds.

        Raises:
            ValueError: The sections are invalid, or would change nothing.
        """
        from twilite.editing import plan_resample, resample

        acq = self._editable()
        sections = self._sections(sections)
        plan = plan_resample(acq, sections)
        if not plan.changes:
            raise ValueError("Nothing to resample: every section keeps its samples")
        self._replaceData(resample(acq, sections, plan))

    def hasUnsavedEdits(self):
        return self.unsavedEdits

    def saveEditedData(self, path):
        """Write the edited data to ``path``, which then becomes the loaded data's file.

        Raises:
            ValueError: Nothing was edited, or ``path`` is an acquisition as recorded
                (the original data is never overwritten).
        """
        from twilite.storage import read_acquisition, write_acquisition

        acq = self._editable()
        if not acq.edits:
            raise ValueError("The data has not been edited")
        if os.path.exists(path) and not read_acquisition(path).edits:
            raise ValueError(f"{os.path.basename(path)} holds an acquisition as recorded; "
                             "save the edited data under another name")
        write_acquisition(acq, path)
        acq.path = Path(path)
        self.unsavedEdits = False
        self.logger.info(f"Edited data saved: {path} ({len(acq)} samples, {len(acq.edits)} edits)")

    def _editable(self):
        if self.correctionData is None:
            raise ValueError("Load the data to correct first")
        return self.correctionData

    @staticmethod
    def _sections(sections):
        from twilite.editing import Section

        return [Section(*section) for section in sections]

    def _replaceData(self, edited):
        for line in edited.edits[len(self.correctionData.edits):]:
            self.logger.info(f"Edited {edited.path.name}: {line}")
        self.correctionData = edited
        self.unsavedEdits = True

    def _settingsMetadata(self):
        isotope = self.isotope()
        return {
            "isotope": f"{isotope.name} (half-life {isotope.half_life_s:g} s, "
                       f"branching ratio {isotope.branching_ratio:g})",
            "pet_start": datetime.fromtimestamp(self.petStart).isoformat() if self.petStart else "not set",
            "background": "mean before PET start" if self.fixedBackground is None else self.fixedBackground,
            "calibration_factor": self.calibrationFactor,
        }

    ###########################################################################
    # Calibration                                                             #
    ###########################################################################

    def loadCalibrationRun(self, path):
        """Read a finished acquisition for calibration; return ``(t_rel_s, coincidences)``."""
        from twilite.storage import read_acquisition

        self.calibrationRun = read_acquisition(path)
        if len(self.calibrationRun) == 0:
            raise ValueError(f"{os.path.basename(path)} holds no samples")
        self.logger.info(f"Calibration run loaded: {path} ({len(self.calibrationRun)} samples)")
        return np.array(self.calibrationRun.t_rel_s), np.array(self.calibrationRun.coincidences, dtype=float)

    def calibrationRunStart(self):
        """PC time of the calibration run's t = 0, seconds since the epoch."""
        run = self.calibrationRun
        return run.t_wall[0] - run.t_rel_s[0]

    def computeCalibration(self, backgroundWindow, plateauWindow, activityPet, referenceTime, isotope=None):
        """Return CF from the loaded run.

        Args:
            backgroundWindow: ``(start, end)`` in seconds from the run start.
            plateauWindow: ``(start, end)`` in seconds from the run start.
            activityPet: Phantom activity concentration from the PET, kBq/cc.
            referenceTime: PC time the PET activity refers to, seconds since the epoch.
            isotope: The phantom's :class:`~twilite.Isotope`; None for the correction's.
        """
        from twilite.correction import calibration_factor, mean_in_window

        run = self.calibrationRun
        if run is None:
            raise ValueError("Load a calibration run first")
        background = mean_in_window(run.t_rel_s, run.coincidences, *backgroundWindow)
        offset = self.calibrationRunStart() - referenceTime
        tRef = [t + offset for t in run.t_rel_s]
        plateau = (plateauWindow[0] + offset, plateauWindow[1] + offset)
        isotope = isotope or self.isotope()
        cf = calibration_factor(tRef, run.coincidences, background, isotope, plateau, activityPet)
        # Debug: the View recomputes on every change, such as each step of a dragged window.
        self.logger.debug(f"Calibration factor {cf:.6g} (background {background:.4g}, "
                          f"A_PET {activityPet:g} kBq/cc, {isotope.name})")
        return cf

    ###########################################################################
    # Files                                                                   #
    ###########################################################################

    def findPartialFiles(self):
        from twilite.storage import find_partial_files

        return [str(p) for p in find_partial_files(self.dataDir)]

    def recoverFiles(self, paths):
        from twilite.storage import recover

        recovered = []
        for path in paths:
            final = recover(path)
            self.logger.info(f"Recovered {final}")
            recovered.append(str(final))
        return recovered

    def export(self, kind, sourcePath, targetPath):
        """Export the raw data of an acquisition file; ``kind`` is csv, crv or events."""
        from twilite import storage

        acq = storage.read_acquisition(sourcePath)
        if kind == "csv":
            storage.export_csv(acq, targetPath)
        elif kind == "crv":
            storage.export_crv(acq, targetPath)
        elif kind == "events":
            storage.export_events(acq, targetPath)
        else:
            raise ValueError(f"Unknown export {kind!r}")
        self.logger.info(f"Exported {kind}: {targetPath}")
        return targetPath

    def exportCorrected(self, kind, targetPath):
        """Export the loaded data, corrected; ``kind`` is bld (PMOD blood), tac (PMOD TAC) or csv."""
        from twilite import storage

        if self.correctionData is None:
            raise ValueError("Load the data to correct first")
        settings = self.correctionSettings()
        if kind == "bld":
            storage.export_pmod_blood(self.correctionData, targetPath, settings)
        elif kind == "tac":
            storage.export_pmod_tac(self.correctionData, targetPath, settings)
        elif kind == "csv":
            storage.export_csv(self.correctionData, targetPath, settings)
        else:
            raise ValueError(f"Unknown export {kind!r}")
        self.logger.info(f"Exported corrected {kind}: {targetPath}")
        return targetPath

    ###########################################################################
    # Settings between sessions                                               #
    ###########################################################################

    def loadState(self):
        """Return the settings saved by the last session, or ``{}``."""
        if not os.path.exists(self.STATE_FILE):
            return {}
        with open(self.STATE_FILE, encoding="utf-8") as file:
            state = yaml.safe_load(file) or {}
        self.logger.debug(f"Settings restored from {self.STATE_FILE}")
        return state

    def saveState(self, state):
        with open(self.STATE_FILE, "w", encoding="utf-8") as file:
            yaml.safe_dump(state, file, sort_keys=True)
