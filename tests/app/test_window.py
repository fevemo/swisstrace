"""Smoke test: build the real window, connect to the simulator, acquire for 5 s, close."""

import os
from datetime import datetime

import numpy as np
import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("einstudio")

from tests.app.conftest import APP_DIR, load_app_module, make_instrument_config, write_step_run  # noqa: E402

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
    tWall = h.correctionData["t"]
    vb = w.correctionPlot.plotItem.vb
    assert vb.viewRange()[0] == pytest.approx([tWall[0] - h.correctionData["start"], tWall[-1] - h.correctionData["start"]])
    assert w.backgroundSpin.text() == "-"  # no PET start, no mean

    # Select: a click on the plot sets the PET start, time only.
    w.petSelectButton.click()
    assert w.petSelectButton.text() == "Cancel"
    # The middle of the run: the field keeps whole seconds, so the PET start may move by up to
    # 0.5 s, and samples must stay on both sides of it.
    middle = tWall[len(tWall) // 2]
    clickAt = (middle - h.correctionData["start"], float(np.nanmean(h.correctionData["coincidences"])))
    scenePos = vb.mapViewToScene(QPointF(*clickAt))
    qtbot.mouseClick(w.correctionPlot.viewport(), Qt.MouseButton.LeftButton,
                     pos=w.correctionPlot.mapFromScene(scenePos))
    assert w.petSelectButton.text() == "Select"
    assert w.petStartEdit.text() == datetime.fromtimestamp(round(middle)).strftime("%H:%M:%S")

    # Time 0 is now the PET start; the plot still shows the whole measurement, from below 0.
    petStart = h.correctionZero
    assert vb.viewRange()[0] == pytest.approx([tWall[0] - petStart, tWall[-1] - petStart])
    assert vb.viewRange()[0][0] < 0
    assert h.petStartLine.isVisible() and h.correctionBackgroundRegion.isVisible()
    assert not h.backgroundLine.isVisible()
    before = h.correctionData["coincidences"][tWall < petStart]
    assert not w.backgroundSpin.isEnabled()
    assert w.backgroundSpin.value() == pytest.approx(before.mean(), abs=0.01)
    # The correction follows the settings: the PET start selected is enough for the curve.
    corrected = h.correctedCurve.getData()[1].copy()
    assert len(corrected) > 0
    assert vb.viewRange()[0][0] < 0  # the corrected curve, from 0 on, does not move the range
    notes = []
    monkeypatch.setattr(window, "_notify", lambda *a: notes.append(a))
    petText = w.petStartEdit.text()
    w.petStartEdit.setText(petText[:4])  # being typed: no curve, no complaint
    assert h.correctedCurve.getData()[0] is None or len(h.correctedCurve.getData()[0]) == 0
    assert notes == []
    w.petStartEdit.setText(petText)
    assert h.correctedCurve.getData()[1] == pytest.approx(corrected)
    w.cfSpin.setValue(w.cfSpin.value() * 2)
    assert h.correctedCurve.getData()[1] == pytest.approx(corrected * 2)
    w.cfSpin.setValue(w.cfSpin.value() / 2)
    # Zooming and panning in y move both axes alike; fitting the data fits both again.
    cv = h.correctedView
    yMain, yCorrected = vb.viewRange()[1], cv.viewRange()[1]
    vb.scaleBy(y=0.5, center=QPointF(0, sum(yMain) / 2))
    assert np.diff(vb.viewRange()[1]) == pytest.approx(np.diff(yMain) / 2)
    assert np.diff(cv.viewRange()[1]) == pytest.approx(np.diff(yCorrected) / 2)
    assert sum(cv.viewRange()[1]) / 2 == pytest.approx(sum(yCorrected) / 2)
    vb.translateBy(y=np.diff(vb.viewRange()[1])[0] / 4)
    assert cv.viewRange()[1][0] - yCorrected[0] == pytest.approx(np.diff(yCorrected)[0] / 4 + np.diff(yCorrected)[0] / 8)
    vb.enableAutoRange(axis="y")
    vb.updateAutoRange()
    assert cv.autoRangeEnabled()[1]

    w.backgroundModeDropdown.setCurrentIndex(1)
    assert w.backgroundSpin.isEnabled() and w.backgroundSpin.value() == 0.0  # the fixed value, not the mean
    w.backgroundSpin.setValue(150.0)
    assert h.backgroundLine.isVisible() and not h.correctionBackgroundRegion.isVisible()
    assert len(h.correctedCurve.getData()[0]) > 0  # corrected again with the fixed value
    w.backgroundModeDropdown.setCurrentIndex(0)
    assert w.backgroundSpin.value() == pytest.approx(before.mean(), abs=0.01)
    w.backgroundModeDropdown.setCurrentIndex(1)
    assert w.backgroundSpin.value() == 150.0

    answers = iter([(str(tmp_path / "out"), "PMOD TAC (*.tac)"), (str(tmp_path / "typed.bld"), "PMOD TAC (*.tac)")])
    errors = []
    vm.errorOccurred.connect(errors.append)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *args: next(answers)))
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


def test_cut_resample_and_save_edited_data(qtbot, window, tmp_path, monkeypatch):
    import sys

    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtWidgets import QFileDialog

    w, h, vm = window.widgets, window.handles, window.viewModel
    notes = []
    monkeypatch.setattr(window, "_notify", lambda *a: notes.append(a))
    # 5 s samples arriving at 0, 5, ... 295 s.
    path = write_step_run(tmp_path)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a: (str(path), "")))
    w.loadCorrectionDataButton.click()
    assert w.cutButton.isEnabled() and w.resampleButton.isEnabled() and not w.saveEditedButton.isEnabled()

    # Cut mode: markers on every sample; a left drag selects, snapped to midway between samples.
    w.cutButton.click()
    assert not w.cutRow.isHidden() and w.cutButton.text() == "Done" and not w.resampleButton.isEnabled()
    assert h.rawCurve.opts["symbol"] == "o" and not w.applyCutButton.isEnabled()
    vb = w.correctionPlot.plotItem.vb

    class Drag:
        accepted = False

        def button(self):
            return Qt.MouseButton.LeftButton

        def buttonDownScenePos(self):
            return vb.mapViewToScene(QPointF(16.0, 100.0))

        def scenePos(self):
            return vb.mapViewToScene(QPointF(34.0, 100.0))

        def isFinish(self):
            return True

        def accept(self):
            self.accepted = True

        def ignore(self):
            self.accepted = False

    # As pyqtgraph's scene sends a drag: to the items under it, top first, until one takes it.
    drag = Drag()
    for item in w.correctionPlot.scene().itemsNearEvent(drag):
        if item.isVisible() and item.isEnabled() and hasattr(item, "mouseDragEvent"):
            item.mouseDragEvent(drag)
            if drag.accepted:
                break
    assert item is vb  # not the corrected curve's view, drawn above it
    assert h.cutRegion.isVisible()
    assert h.cutRegion.getRegion() == pytest.approx((17.5, 32.5))
    assert w.cutRow.contentLabel.text() == "3 samples, 20.0 to 30.0 s"
    # The line runs from the sample before the selection to the one after it.
    assert h.cutPreviewCurve.getData()[0] == pytest.approx([15, 20, 25, 30, 35])
    assert len(h.cutSelectedPoints.getData()[0]) == 3
    w.applyCutButton.click()
    assert w.correctionFileLabel.text() == path.name
    assert w.saveEditedButton.isEnabled() and not h.cutRegion.isVisible()
    w.cutButton.click()
    assert w.cutRow.isHidden() and h.rawCurve.opts["symbol"] is None and w.resampleButton.isEnabled()

    # Resample: one section to start with; split it, sample its second half every 30 s.
    w.resampleButton.click()
    dialog = h.resampleDialog
    table = dialog.table
    assert dialog.isVisible() and not w.cutButton.isEnabled() and w.resampleButton.text() == "Done"
    assert [table.item(0, c).text() for c in range(4)] == ["0.0", "295.0", "5", "60"]
    assert dialog.applyButton.text() == "Done"  # nothing to apply yet
    assert not dialog.deleteButton.isEnabled()  # the first section stays
    dialog.addButton.click()
    assert [[table.item(r, c).text() for c in range(2)] for r in range(2)] == [["0.0", "147.5"], ["147.5", "295.0"]]
    table.item(1, 2).setText("30")
    assert [table.item(r, 3).text() for r in range(2)] == ["30", "5"]
    assert len(h.resamplePreviewCurve.getData()[0]) == 5 and len(h.sectionLines) == 3
    table.item(0, 1).setText("400")  # beyond the next section's end: rejected
    assert table.item(0, 1).text() == "147.5"
    table.item(0, 1).setText("115")  # moves the next section's start too
    assert table.item(1, 0).text() == "115.0" and table.item(1, 3).text() == "6"
    assert dialog.applyButton.text() == "Resample"
    # "Done" in the main window with changes not applied: asks to apply, discard or cancel.
    asked = []
    choice = "cancel"
    monkeypatch.setattr(window, "_askUnappliedResample", lambda canApply: asked.append(canApply) or choice)
    w.resampleButton.click()
    assert asked == [True] and dialog.isVisible() and len(h.correctionData["t"]) == 60
    choice = "apply"
    w.resampleButton.click()
    assert asked == [True, True] and not dialog.isVisible() and len(h.correctionData["t"]) == 24 + 6
    assert w.resampleButton.text() == "Resampling"
    w.resampleButton.click()  # open again: the sections as the data is sampled now
    assert dialog.isVisible() and dialog.applyButton.text() == "Done"
    assert [table.item(r, 2).text() for r in range(2)] == ["5", "30"]  # as the data is sampled now
    table.item(1, 2).setText("5")  # finer than the 30 s samples: refused
    assert dialog.statusLabel.text().startswith("Section 2: ") and "cannot make it finer" in dialog.statusLabel.text()
    assert not dialog.applyButton.isEnabled() and dialog.applyButton.text() == "Resample"
    # Only the wrong section loses its count, and turns red.
    assert [table.item(r, 3).text() for r in range(2)] == ["24", "-"]
    assert table.item(0, 0).background().style() == Qt.BrushStyle.NoBrush
    assert table.item(1, 0).background().style() != Qt.BrushStyle.NoBrush
    table.item(1, 2).setText("45")  # not a multiple of 30 s: refused
    assert "multiple of 30 s" in dialog.statusLabel.text() and not dialog.applyButton.isEnabled()
    table.item(1, 2).setText("30")
    assert dialog.statusLabel.text() == "" and dialog.applyButton.isEnabled()
    assert table.item(1, 0).background().style() == Qt.BrushStyle.NoBrush
    table.selectRow(1)
    dialog.deleteButton.click()
    assert table.rowCount() == 1 and table.item(0, 1).text() == "295.0"
    assert not dialog.applyButton.isEnabled()  # 5 s over the 30 s samples
    dialog.addButton.click()
    table.item(0, 1).setText("115")
    table.item(1, 2).setText("30")  # the sampling as it is
    assert dialog.applyButton.text() == "Done"
    dialog.applyButton.click()  # nothing changes: Done closes the window
    assert not dialog.isVisible() and len(h.correctionData["t"]) == 24 + 6
    assert not h.sectionLines and w.cutButton.isEnabled()
    w.resampleButton.click()
    table.item(0, 2).setText("10")
    choice = "cancel"
    w.resampleButton.click()  # changes not applied: asks again
    assert asked == [True, True, True] and dialog.isVisible()
    choice = "discard"
    w.resampleButton.click()
    assert not dialog.isVisible() and len(h.correctionData["t"]) == 24 + 6
    w.resampleButton.click()  # the next opening starts afresh
    assert dialog.applyButton.text() == "Done" and table.item(0, 2).text() == "5"
    table.item(0, 2).setText("7")
    w.resampleButton.click()
    assert asked[-1] is False  # a section that cannot be applied: discard or cancel only
    assert not dialog.isVisible() and w.resampleButton.text() == "Resampling"

    # Unsaved edits: loading asks first.
    view = sys.modules[type(window).__module__]
    monkeypatch.setattr(view, "MessageBox", type("No", (), {"__init__": lambda *a: None, "exec": lambda self: False}))
    w.loadCorrectionDataButton.click()
    assert vm.hasUnsavedEdits() and len(h.correctionData["t"]) == 30

    # Save: never over the original, suggested as ..._edited.csv.
    answers = iter([str(path), str(tmp_path / "mine_edited.csv")])
    asked = []
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a: (asked.append(a[2]) or next(answers), "")))
    w.saveEditedButton.click()
    assert asked[0] == str(path.with_name(path.stem + "_edited.csv"))
    assert notes[-1][0] == "error" and "as recorded" in notes[-1][2]
    w.saveEditedButton.click()
    assert notes[-1][:2] == ("success", "Edited data saved")
    assert w.correctionFileLabel.text() == "mine_edited.csv" and not w.saveEditedButton.isEnabled()
    w.loadCorrectionDataButton.click()  # no unsaved edits: no question
    assert w.correctionFileLabel.text() == path.name


def test_pet_time_takes_the_day_nearest_the_data():
    parseTime = load_app_module("view")._parseTime
    evening = datetime(2026, 10, 9, 23, 50).timestamp()
    assert parseTime("23:55:00", evening) == datetime(2026, 10, 9, 23, 55).timestamp()
    assert parseTime("00:05:00", evening) == datetime(2026, 10, 10, 0, 5).timestamp()  # after midnight
    assert parseTime("23:40:00", datetime(2026, 10, 10, 0, 10).timestamp()) == datetime(2026, 10, 9, 23, 40).timestamp()
    assert parseTime("", evening) is None
    assert parseTime("2026-10-09 23:55:00", evening) is None  # time only
