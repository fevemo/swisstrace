"""ViewModel signals, headless, with pytest-qt."""

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("einstudio")

from tests.app.conftest import load_app_module  # noqa: E402

pytestmark = pytest.mark.app


@pytest.fixture
def viewmodel(qapp, model):
    ViewModel = load_app_module("viewmodel").ViewModel
    vm = ViewModel(model, model.logger)
    yield vm
    vm.shutdown()


def connect(qtbot, vm):
    with qtbot.waitSignal(vm.connectionChanged, timeout=5000) as blocker:
        vm.connect("127.0.0.1", 23)
    assert blocker.args == [True]


def test_connect_emits_status_banner_and_connection(qtbot, viewmodel):
    statuses = []
    viewmodel.statusChanged.connect(lambda status, text: statuses.append(status))
    with qtbot.waitSignal(viewmodel.bannerChanged, timeout=5000) as banner:
        viewmodel.connect("127.0.0.1", 23)
    assert banner.args[0].startswith("Coincident Counter")
    qtbot.waitUntil(lambda: statuses == ["connecting", "connected"], timeout=2000)
    assert viewmodel.isConnected()


def test_signals_of_an_acquisition_in_order(qtbot, viewmodel):
    connect(qtbot, viewmodel)
    order = []
    viewmodel.acquisitionChanged.connect(lambda running: order.append(f"acquisition {running}"))
    viewmodel.traceUpdated.connect(lambda trace: order.append("trace") if "trace" not in order else None)
    viewmodel.acquisitionSaved.connect(lambda path: order.append("saved"))
    viewmodel.startAcquisition(qrate=1)
    qtbot.waitUntil(lambda: viewmodel.model.getStats()["samples"] >= 3, timeout=5000)
    with qtbot.waitSignal(viewmodel.acquisitionSaved, timeout=5000):
        viewmodel.stopAcquisition()
    assert order == ["acquisition True", "trace", "acquisition False", "saved"]
    assert not viewmodel.isAcquiring()


def test_plot_updates_are_throttled(qtbot, model_factory, qapp):
    # 10 reports a second and a 0.1 s counting interval: up to 10 new samples a second.
    model = model_factory(simulator={"port": 0})
    ViewModel = load_app_module("viewmodel").ViewModel
    vm = ViewModel(model, model.logger)
    connect(qtbot, vm)
    updates = []
    vm.traceUpdated.connect(lambda trace: updates.append(trace))
    vm.startAcquisition(qrate=1)
    qtbot.wait(2000)
    with qtbot.waitSignal(vm.acquisitionChanged, timeout=5000):
        vm.stopAcquisition()
    vm.shutdown()
    assert 5 <= len(updates) <= 2 * vm.PLOT_UPDATES_PER_S + 2


def test_idle_connection_is_kept_open(qtbot, model_factory, qapp, monkeypatch):
    import twilite.protocol

    monkeypatch.setattr(twilite.protocol, "KEEPALIVE_INTERVAL_S", 0.1)
    model = model_factory(simulator={"port": 0, "idleTimeout_s": 0.5})
    vm = load_app_module("viewmodel").ViewModel(model, model.logger)
    vm._keepAliveTimer.setInterval(100)
    connect(qtbot, vm)
    errors = []
    vm.errorOccurred.connect(errors.append)
    qtbot.wait(1500)
    assert errors == [] and vm.isConnected()
    assert model.simulator.connection_count == 1
    vm.shutdown()


def test_connection_closed_while_idle_is_reported(qtbot, model_factory, qapp, monkeypatch):
    import twilite.protocol

    monkeypatch.setattr(twilite.protocol, "KEEPALIVE_INTERVAL_S", 0.1)
    model = model_factory()
    vm = load_app_module("viewmodel").ViewModel(model, model.logger)
    vm._keepAliveTimer.setInterval(100)
    connect(qtbot, vm)
    model.simulator.drop_connections()
    with qtbot.waitSignal(vm.connectionChanged, timeout=3000) as blocker:
        pass
    assert blocker.args == [False]
    assert not vm.isConnected()
    vm.shutdown()


def test_start_without_connection_is_refused(qtbot, viewmodel):
    with qtbot.waitSignal(viewmodel.errorOccurred, timeout=1000) as blocker:
        viewmodel.startAcquisition(qrate=1)
    assert "Connect" in blocker.args[0]
    assert not viewmodel.isAcquiring()


def test_second_start_is_refused(qtbot, viewmodel):
    connect(qtbot, viewmodel)
    viewmodel.startAcquisition(qrate=1)
    with qtbot.waitSignal(viewmodel.errorOccurred, timeout=1000) as blocker:
        viewmodel.startAcquisition(qrate=1)
    assert "already running" in blocker.args[0]
    with qtbot.waitSignal(viewmodel.acquisitionChanged, timeout=5000):
        viewmodel.stopAcquisition()


def test_disconnect_during_acquisition_is_refused(qtbot, viewmodel):
    connect(qtbot, viewmodel)
    viewmodel.startAcquisition(qrate=1)
    with qtbot.waitSignal(viewmodel.errorOccurred, timeout=1000):
        viewmodel.disconnect()
    assert viewmodel.isConnected()
    with qtbot.waitSignal(viewmodel.acquisitionChanged, timeout=5000):
        viewmodel.stopAcquisition()


def test_mark_signal(qtbot, viewmodel):
    connect(qtbot, viewmodel)
    viewmodel.startAcquisition(qrate=1)
    qtbot.waitUntil(lambda: viewmodel.model.getStats()["samples"] >= 2, timeout=5000)
    with qtbot.waitSignal(viewmodel.markAdded, timeout=1000) as blocker:
        viewmodel.markEvent("injection")
    assert blocker.args[1] == "injection"
    with qtbot.waitSignal(viewmodel.acquisitionChanged, timeout=5000):
        viewmodel.stopAcquisition()


def test_lost_connection_is_reported(qtbot, model_factory, qapp):
    model = model_factory(reconnectAttempts=0)
    vm = load_app_module("viewmodel").ViewModel(model, model.logger)
    connect(qtbot, vm)
    vm.startAcquisition(qrate=1)
    qtbot.waitUntil(lambda: model.getStats()["samples"] >= 1, timeout=5000)
    with qtbot.waitSignals([vm.errorOccurred, vm.connectionChanged], timeout=5000):
        model.simulator.drop_connections()
    assert not vm.isAcquiring()
    assert vm.exportFile is not None
    vm.shutdown()


def test_invalid_correction_is_reported(qtbot, viewmodel):
    with qtbot.waitSignal(viewmodel.errorOccurred, timeout=1000):
        viewmodel.setCorrection("Custom", None, None, 1.0, customHalfLife_s=-5.0)
