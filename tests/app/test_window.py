"""Smoke test: build the real window, connect to the simulator, acquire for 5 s, close."""

import os
from datetime import datetime

import numpy as np
import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("einstudio")

from tests.app.conftest import APP_DIR, load_app_module, make_instrument_config  # noqa: E402

pytestmark = pytest.mark.app


@pytest.fixture
def window(qapp, qtbot, tmp_path, monkeypatch):
    from einstudio.tools import globals as einGlobals
    from einstudio.tools.asynclogger import NullLogger
    from einstudio.tools.configmanager import ConfigManager
    from einstudio.tools.einapplication import EINApplication
    from einstudio.tools.layoutmanager import LayoutManager
    from einstudio.tools.styleengine import StyleEngine

    # EINApplication runs the app from its folder; state.yaml goes to tmp_path instead.
    monkeypatch.chdir(APP_DIR)
    einGlobals.set_baseDir(str(APP_DIR))
    logger = NullLogger("test")
    configManager = ConfigManager(logger, str(APP_DIR / "config.yaml"), str(APP_DIR))
    Model, ViewModel, View = EINApplication(str(APP_DIR))._importMVC()
    StyleEngine.applyToApp(qapp, configManager, logger)
    instrumentConfig = make_instrument_config(tmp_path / "data")
    model = Model(logger, instrumentConfig)
    model.STATE_FILE = str(tmp_path / "state.yaml")
    viewModel = ViewModel(model, logger)
    layoutManager = LayoutManager(configManager.mainConfig.layoutFile, logger,
                                  options=configManager.options, instrumentConfig=instrumentConfig)
    view = View(viewModel, layoutManager, configManager, logger)
    qtbot.addWidget(view)
    view.show()
    yield view
    view.close()


def test_connect_acquire_for_five_seconds_and_close(qtbot, window, tmp_path, monkeypatch):
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtWidgets import QFileDialog

    w = window.widgets
    vm = window.viewModel
    with qtbot.waitSignal(vm.connectionChanged, timeout=5000):
        w.connectButton.click()
    assert w.connectButton.text() == "Disconnect"
    assert w.runButton.isEnabled() and w.runButton.text() == "Start"

    w.sampleRateDropdown.setCurrentText("0.1")
    w.runButton.click()
    assert w.runButton.isEnabled() and w.runButton.text() == "Stop"
    qtbot.wait(2500)
    w.markEdit.setText("injection")
    w.markButton.click()
    qtbot.wait(2500)
    with qtbot.waitSignal(vm.acquisitionSaved, timeout=5000) as saved:
        w.runButton.click()

    assert w.elapsedLabel.text() != "0:00:00"
    assert len(window.handles.coincidenceCurve.getData()[0]) >= 15
    assert len(window.handles.markLines) == 1
    assert w.runButton.text() == "Start"
    assert saved.args[0].endswith("_twilite.csv")
    assert w.saveRawButton.isEnabled()

    # Correction page: the current acquisition, its PET start, background and save formats.
    h = window.handles
    w.useCurrentDataButton.click()
    assert w.correctionFileLabel.text() == os.path.basename(saved.args[0])
    assert len(h.rawCurve.getData()[0]) >= 15
    assert not h.correctedCurve.getData()[0]  # no PET start yet
    tWall = h.correctionData["t_wall"]
    vb = w.correctionPlot.plotItem.vb
    assert vb.viewRange()[0] == pytest.approx([tWall[0] - h.correctionData["start"], tWall[-1] - h.correctionData["start"]])
    assert w.backgroundSpin.text() == "-"  # no PET start, no mean

    # Select: a click on the plot sets the PET start, time only.
    w.petSelectButton.click()
    assert w.petSelectButton.text() == "Cancel"
    clickAt = (tWall[-3] - h.correctionData["start"], float(np.nanmean(h.correctionData["coincidences"])))
    scenePos = vb.mapViewToScene(QPointF(*clickAt))
    qtbot.mouseClick(w.correctionPlot.viewport(), Qt.MouseButton.LeftButton,
                     pos=w.correctionPlot.mapFromScene(scenePos))
    assert w.petSelectButton.text() == "Select"
    assert w.petStartEdit.text() == datetime.fromtimestamp(round(tWall[-3])).strftime("%H:%M:%S")

    # Time 0 is now the PET start; the plot still shows the whole measurement, from below 0.
    petStart = h.correctionZero
    assert vb.viewRange()[0] == pytest.approx([tWall[0] - petStart, tWall[-1] - petStart])
    assert vb.viewRange()[0][0] < 0
    assert h.petStartLine.isVisible() and h.correctionBackgroundRegion.isVisible()
    assert not h.backgroundLine.isVisible()
    before = h.correctionData["coincidences"][h.correctionData["t_wall"] < petStart]
    assert not w.backgroundSpin.isEnabled()
    assert w.backgroundSpin.value() == pytest.approx(before.mean(), abs=0.01)
    w.applyCorrectionButton.click()
    assert len(h.correctedCurve.getData()[0]) > 0
    assert vb.viewRange()[0][0] < 0  # the corrected curve, from 0 on, does not move the range

    w.backgroundModeDropdown.setCurrentIndex(1)
    assert w.backgroundSpin.isEnabled() and w.backgroundSpin.value() == 0.0  # the fixed value, not the mean
    w.backgroundSpin.setValue(150.0)
    assert h.backgroundLine.isVisible() and not h.correctionBackgroundRegion.isVisible()
    assert not h.correctedCurve.getData()[0]  # stale until the next Apply
    w.backgroundModeDropdown.setCurrentIndex(0)
    assert w.backgroundSpin.value() == pytest.approx(before.mean(), abs=0.01)
    w.backgroundModeDropdown.setCurrentIndex(1)
    assert w.backgroundSpin.value() == 150.0

    answers = iter([(str(tmp_path / "out"), "PMOD TAC (*.tac)"), (str(tmp_path / "typed.bld"), "PMOD TAC (*.tac)")])
    errors = []
    vm.errorOccurred.connect(errors.append)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *args: next(answers)))
    notes = []
    monkeypatch.setattr(window, "_notify", lambda *a: notes.append(a))
    w.saveCorrectedButton.click()
    assert notes == [] and errors == []
    assert (tmp_path / "out.tac").read_text().startswith("start[seconds]")
    w.saveCorrectedButton.click()
    assert (tmp_path / "typed.bld").read_text().startswith("sample-time[seconds]")

    # Calibration page: the current acquisition as run; the factor follows every input.
    w.useCurrentCalibrationButton.click()
    assert w.calibrationFileLabel.text() == os.path.basename(saved.args[0])
    runStart = datetime.fromtimestamp(vm.calibrationRunStart()).strftime("%H:%M:%S")
    assert w.calibrationReferenceEdit.text() == runStart  # filled in from the run
    description = w.calibrationResultRow.contentLabel
    assert description.text() == "Enter the PET activity"
    assert not w.applyCalibrationButton.isEnabled()
    w.activitySpin.setValue(50.0)
    # The simulated run may have no step, so the factor may be missing; then the label says why.
    computed = w.calibrationResultLabel.text() != "-"
    assert w.applyCalibrationButton.isEnabled() == computed
    assert (description.text() == "Apply uses it on the Correction page") == computed
    if computed:
        w.applyCalibrationButton.click()
        assert w.cfSpin.value() == pytest.approx(vm.lastCalibrationFactor, rel=1e-5)
        assert notes[-1][1] == "Calibration factor applied"

    window.close()
    assert not vm.isConnected()
    assert (tmp_path / "state.yaml").exists()
    state = (tmp_path / "state.yaml").read_text()
    assert "background: 150.0" in state  # the fixed value, not the mean
    assert "qrate: 1\n" in state  # 0.1 s


def test_pet_time_takes_the_day_nearest_the_data():
    parseTime = load_app_module("view")._parseTime
    evening = datetime(2026, 10, 9, 23, 50).timestamp()
    assert parseTime("23:55:00", evening) == datetime(2026, 10, 9, 23, 55).timestamp()
    assert parseTime("00:05:00", evening) == datetime(2026, 10, 10, 0, 5).timestamp()  # after midnight
    assert parseTime("23:40:00", datetime(2026, 10, 10, 0, 10).timestamp()) == datetime(2026, 10, 9, 23, 40).timestamp()
    assert parseTime("", evening) is None
    assert parseTime("2026-10-09 23:55:00", evening) is None  # time only
