"""The app's Model in plain Python, with the simulator: no Qt, no EINstudio."""

import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pytest

from twilite import ConnectionLost, Sample
from twilite.storage import AcquisitionWriter, read_acquisition

from tests.app.conftest import APP_DIR, write_step_run


def acquire_in_thread(model, qrate=1, endAfter_s=None):
    """Run model.acquire() in a thread; return (thread, result dict, events list)."""
    result, events = {}, []

    def run():
        try:
            result["path"] = model.acquire(qrate, endAfter_s, onEvent=lambda kind, text: events.append((kind, text)))
        except Exception as error:  # noqa: BLE001 - checked by the tests
            result["error"] = error

    thread = threading.Thread(target=run)
    thread.start()
    return thread, result, events


def wait_for(condition, timeout=5.0):
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met in time")
        time.sleep(0.05)


def test_model_never_imports_qt():
    code = (
        "import sys, logging; sys.path.insert(0, r'%s'); import model; "
        "m = model.Model(logging.getLogger(), {'twilite': {'host': 'x', 'port': 1, 'simulate': True, "
        "'simulator': {}}}); m.connect(); m.shutdown(); "
        "assert not [n for n in sys.modules if n.startswith(('PyQt', 'qfluent', 'einstudio'))], 'Qt imported'"
    ) % APP_DIR
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_connect_to_simulator(model):
    banner = model.connect()
    assert banner.startswith("Coincident Counter")
    assert model.isConnected()
    model.disconnect()
    assert not model.isConnected()


def test_timed_acquisition_writes_a_file(model):
    model.connect()
    path = model.acquire(qrate=1, endAfter_s=1.0)
    acq = read_acquisition(path)
    assert path.endswith("_twilite.csv")
    # One sample per 100 ms report. The median spacing, not the count, so that a stall of
    # a busy CI machine (it gave 7 samples in 1 s once) does not fail the test.
    spacing = statistics.median(b - a for a, b in zip(acq.t_rel_s, acq.t_rel_s[1:]))
    assert spacing == pytest.approx(0.1, abs=0.03)
    assert 5 <= len(acq) <= 12
    assert acq.t_rel_s[-1] >= 1.0  # ran for the full time
    assert acq.index == sorted(set(acq.index))
    assert acq.metadata["report_rate"] == "qrate 1 (100 ms)"
    assert "simulator" in acq.metadata["device"]
    trace = model.getTrace()
    assert len(trace["t"]) == len(acq)
    assert model.getStats()["samples"] == len(acq)
    assert not model.isAcquiring()
    assert list((Path(model.dataDir) / "rawlogs").glob("*_raw.log"))


def test_stop_from_another_thread(model):
    model.connect()
    thread, result, _ = acquire_in_thread(model)
    wait_for(lambda: model.getStats()["samples"] >= 2)
    model.requestStop()
    thread.join(5)
    assert not thread.is_alive()
    assert "path" in result and model.isConnected()


def test_mark_event_is_stored(model):
    model.connect()
    thread, result, _ = acquire_in_thread(model)
    wait_for(lambda: model.getStats()["samples"] >= 2)
    t = model.markEvent("injection")
    model.requestStop()
    thread.join(5)
    acq = read_acquisition(result["path"])
    assert [(e.kind, e.text) for e in acq.events] == [("mark", "injection")]
    assert acq.events[0].t_rel_s == pytest.approx(t, abs=0.05)


def test_mark_needs_a_running_acquisition(model):
    with pytest.raises(RuntimeError):
        model.markEvent("x")


def test_reconnects_after_connection_loss(model):
    model.connect()
    thread, result, events = acquire_in_thread(model)
    wait_for(lambda: model.getStats()["samples"] >= 2)
    model.simulator.drop_connections()
    wait_for(lambda: ("connection", "reconnected") in events)
    count = model.getStats()["samples"]
    wait_for(lambda: model.getStats()["samples"] > count)
    model.requestStop()
    thread.join(5)
    kinds = [e.kind for e in read_acquisition(result["path"]).events]
    assert kinds.count("connection") == 2
    # The loss shows as a break in the plotted line.
    assert np.isnan(model.getTrace()["coincidences"]).any()


def test_gives_up_after_the_reconnect_attempts(model_factory):
    model = model_factory(reconnectAttempts=0)
    model.connect()
    thread, result, _ = acquire_in_thread(model)
    wait_for(lambda: model.getStats()["samples"] >= 1)
    model.simulator.drop_connections()
    thread.join(5)
    assert isinstance(result["error"], ConnectionLost)
    assert model.lastFile is not None and model.lastFile.exists()  # the file is closed cleanly
    assert not model.isAcquiring()


def test_keep_alive_holds_an_idle_connection(model_factory, monkeypatch):
    import twilite.protocol

    monkeypatch.setattr(twilite.protocol, "KEEPALIVE_INTERVAL_S", 0.1)
    model = model_factory(simulator={"port": 0, "idleTimeout_s": 0.4})
    model.connect()
    for _ in range(10):
        time.sleep(0.1)
        assert model.keepAlive()
    assert model.isConnected()
    assert model.simulator.connection_count == 1


def test_keep_alive_reports_a_closed_connection(model_factory):
    model = model_factory(simulator={"port": 0, "idleTimeout_s": 0.3})
    model.connect()
    time.sleep(0.6)
    model.client._last_traffic -= 60  # due for a keepalive
    assert not model.keepAlive()
    assert not model.isConnected()


def test_acquire_needs_a_connection(model):
    with pytest.raises(RuntimeError):
        model.acquire(1)


def test_custom_isotope(model):
    model.setCorrection("Custom", None, None, 1.0, customHalfLife_s=100.0, customBranchingRatio=0.5)
    assert model.isotope().half_life_s == 100.0
    with pytest.raises(ValueError):
        model.setCorrection("Custom", None, None, 1.0, customHalfLife_s=-1.0)


def test_calibration_factor_from_a_run(model, tmp_path):
    start = 1_790_000_000.0
    path = write_step_run(tmp_path, start)

    t, coincidences = model.loadCalibrationRun(str(path))
    assert len(t) == 60 and coincidences[0] == 120
    assert model.calibrationRunStart() == pytest.approx(start, abs=1e-3)
    model.setCorrection("F-18", None, None, 1.0)
    cf = model.computeCalibration((0, 95), (150, 290), 50.0, referenceTime=start)
    assert cf == pytest.approx(50 * 0.967 / 1000, rel=1e-4)
    # An explicit isotope instead of the correction's: no decay, no branching.
    flat = model.makeIsotope("Custom", 1e12, 1.0)
    assert model.computeCalibration((0, 95), (150, 290), 50.0, start, flat) > cf


def test_partial_files_are_found_and_recovered(model):
    writer = AcquisitionWriter(model.dataDir)
    writer.write_sample(Sample(1, 1, 2, 3, (), "", time.time(), time.monotonic()))
    writer.abandon()
    found = model.findPartialFiles()
    assert found == [str(writer.path)]
    recovered = model.recoverFiles(found)
    assert recovered[0].endswith("_twilite.csv")
    assert model.findPartialFiles() == []


def test_raw_exports(model, tmp_path):
    model.connect()
    path = model.acquire(qrate=1, endAfter_s=0.8)
    model.setCorrection("F-18", read_acquisition(path).t_wall[1], None, 1.0)
    model.export("crv", path, tmp_path / "a.crv")
    model.export("events", path, tmp_path / "a_events.csv")
    model.export("csv", path, tmp_path / "raw.csv")
    assert "activity_kBq_cc" not in (tmp_path / "raw.csv").read_text()  # raw even with a PET start


def test_correction_data_and_corrected_exports(model, tmp_path):
    model.connect()
    assert model.currentFile() is None
    with pytest.raises(ValueError):
        model.exportCorrected("bld", tmp_path / "a.bld")  # nothing loaded
    path = model.acquire(qrate=1, endAfter_s=0.8)
    assert model.currentFile() == path

    t_wall, coincidences = model.loadCorrectionData(path)
    assert len(t_wall) == len(coincidences) >= 3
    assert model.correctData() is None  # no PET start yet
    with pytest.raises(ValueError):
        model.exportCorrected("bld", tmp_path / "a.bld")

    model.setCorrection("F-18", t_wall[1], None, 1.0)
    t, activity, background = model.correctData()
    assert t[0] == pytest.approx(0.0) and len(activity) == len(t_wall) - 1
    assert background == pytest.approx(coincidences[0])
    model.exportCorrected("bld", tmp_path / "a.bld")
    model.exportCorrected("tac", tmp_path / "a.tac")
    model.exportCorrected("csv", tmp_path / "corrected.csv")
    assert (tmp_path / "a.bld").read_text().startswith("sample-time[seconds]")
    assert (tmp_path / "a.tac").read_text().startswith("start[seconds]")
    assert "activity_kBq_cc" in (tmp_path / "corrected.csv").read_text()


def test_correction_data_of_a_running_acquisition(model):
    model.connect()
    thread, result, _ = acquire_in_thread(model)
    deadline = time.monotonic() + 5
    while model.getStats()["samples"] < 2 and time.monotonic() < deadline:
        time.sleep(0.05)
    assert model.currentFile().endswith(".partial.csv")
    t_wall, _ = model.loadCorrectionData(model.currentFile())
    assert len(t_wall) >= 2
    model.requestStop()
    thread.join(5)
    assert "error" not in result


def test_settings_round_trip(model, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert model.loadState() == {}
    model.saveState({"host": "10.0.0.1", "qrate": 5})
    assert model.loadState() == {"host": "10.0.0.1", "qrate": 5}


def test_editing_the_correction_data(model, tmp_path):
    # 5 s samples arriving at 0, 5, ... 295 s.
    path = write_step_run(tmp_path)
    model.loadCorrectionData(str(path))
    start = model.correctionArrays()["start"]
    assert model.samplingSections() == [pytest.approx((start, start + 295, 5.0))]

    t, values = model.cutPreview(start + 20, start + 40, 2)
    # The line from the edge sample before the cut to the one after it.
    assert t - start == pytest.approx([15, 20, 25, 30, 35, 40, 45]) and values == pytest.approx([120] * 7)
    assert not model.hasUnsavedEdits()
    assert model.cut(start + 20, start + 40, 2)
    assert model.correctionArrays()["interpolated"].sum() == 5 and model.hasUnsavedEdits()

    sections = [(start, start + 145, 5.0), (start + 145, start + 295, 30.0)]
    t, values, counts, problems = model.resamplePreview(sections)
    assert counts == [30, 5] and problems == ["", ""] and len(model.correctionData) == 60  # a preview only
    # The merged samples only, each in the middle of the reports it merges (150..175 s, ...).
    assert t - start == pytest.approx([162.5, 192.5, 222.5, 252.5, 282.5])
    assert model.resample(sections)
    assert len(model.correctionData) == 35
    assert model.resample(model.samplingSections()) is False  # nothing to change
    # A wrong section is left out of the preview; the others are still counted.
    _, _, counts, problems = model.resamplePreview([(start, start + 145, 10.0), (start + 145, start + 295, 45.0)])
    assert counts == [15, None] and problems[0] == "" and "multiple of 30 s" in problems[1]
    assert len(model.correctionData) == 35

    with pytest.raises(ValueError, match="as recorded"):
        model.saveEditedData(str(path))  # never over the original
    edited = tmp_path / "edited.csv"
    model.saveEditedData(str(edited))
    assert not model.hasUnsavedEdits() and model.correctionData.path == edited
    model.cut(start + 200, start + 260, 1)
    model.saveEditedData(str(edited))  # an edited file may be overwritten

    model.loadCorrectionData(str(edited))
    # The cut, the resampled second section (the first keeps its sampling) and the second cut.
    assert len(model.correctionData) == 35 and len(model.correctionData.edits) == 3
    # The corrections use the same times: the middle of the last 30 s sample.
    model.setCorrection("F-18", start + 100, 120.0, 1.0)
    t, _, _ = model.correctData()
    assert t[-1] == pytest.approx(282.5 - 100)
