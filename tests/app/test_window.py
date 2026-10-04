"""Smoke test: build the real window, connect to the simulator, acquire for 5 s, close."""

import os

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("einstudio")

from tests.app.conftest import APP_DIR, make_instrument_config  # noqa: E402

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


def test_connect_acquire_for_five_seconds_and_close(qtbot, window, tmp_path):
    w = window.widgets
    vm = window.viewModel
    with qtbot.waitSignal(vm.connectionChanged, timeout=5000):
        w.connectButton.click()
    assert w.connectButton.text() == "Disconnect"
    assert w.startButton.isEnabled()

    w.qrateSpin.setValue(1)
    w.startButton.click()
    assert w.stopButton.isEnabled() and not w.startButton.isEnabled()
    qtbot.wait(2500)
    w.markEdit.setText("injection")
    w.markButton.click()
    qtbot.wait(2500)
    with qtbot.waitSignal(vm.acquisitionSaved, timeout=5000) as saved:
        w.stopButton.click()

    assert int(w.samplesLabel.text()) >= 15  # 0.2 s counting interval
    assert len(window.handles.coincidenceCurve.getData()[0]) >= 15
    assert len(window.handles.markLines) == 1
    assert w.startButton.isEnabled()
    assert saved.args[0].endswith("_twilite.csv")
    assert w.exportFileLabel.text() == os.path.basename(saved.args[0])

    window.close()
    assert not vm.isConnected()
    assert (tmp_path / "state.yaml").exists()
