"""Tests that need a real twilite: ``uv run pytest --hardware --host <ip> -s``.

The integration tests also run against the device with ``--hardware``. The tests here
add what only real hardware can show. The operator tests print instructions, so run
them with ``-s``. Set the length of the long run with ``TWILITE_LONG_RUN_MIN``
(default 30).
"""

import os
import threading
import time

import pytest

from twilite import TwiliteClient
from twilite.storage import AcquisitionWriter, read_acquisition

from tests.app.conftest import load_app_module

pytestmark = pytest.mark.hardware


@pytest.fixture
def device(request):
    config = request.config
    return {"host": config.getoption("--host"), "port": config.getoption("--port")}


@pytest.fixture
def model(device, tmp_path):
    import logging

    Model = load_app_module("model").Model
    model = Model(logging.getLogger("twiliteacq.hardware"), {"twilite": {
        **device, "simulate": False, "timeout_s": 5.0, "reconnectAttempts": 60, "dataDir": str(tmp_path),
    }})
    yield model
    model.shutdown()


def operator(message):
    print(f"\n\n>>> OPERATOR: {message}\n", flush=True)


def test_long_run_loses_no_samples(device, tmp_path):
    minutes = float(os.environ.get("TWILITE_LONG_RUN_MIN", "30"))
    client = TwiliteClient(device["host"], device["port"], raw_log=tmp_path / "raw.log")
    client.connect()
    client.set_query_rate(1)  # the fastest report rate
    writer = AcquisitionWriter(tmp_path, {"test": "long run"})
    end = time.monotonic() + minutes * 60
    for sample in client.stream():
        writer.write_sample(sample)
        if time.monotonic() > end:
            client.request_stop()
    client.close()
    acq = read_acquisition(writer.finish())
    assert acq.index == list(range(acq.index[0], acq.index[0] + len(acq)))


def test_idle_connection_survives_with_keepalive(model):
    # The device closes a connection idle at the prompt for about 19 s.
    model.connect()
    end = time.monotonic() + 30
    while time.monotonic() < end:
        assert model.keepAlive(), "the device closed the idle connection"
        time.sleep(2)
    assert model.client.command("help")


def acquire_in_thread(model):
    events = []
    thread = threading.Thread(target=lambda: model.acquire(1, onEvent=lambda k, t: events.append((k, t))))
    thread.start()
    return thread, events


def wait_for(condition, timeout_s):
    deadline = time.monotonic() + timeout_s
    while not condition():
        assert time.monotonic() < deadline, "timed out waiting for the operator"
        time.sleep(0.2)


def test_cable_pull_and_reconnect(model):
    model.connect()
    thread, events = acquire_in_thread(model)
    wait_for(lambda: model.getStats()["samples"] >= 5, 60)
    operator("Pull the network cable now (2 minutes).")
    wait_for(lambda: any(text.startswith("lost") for _, text in events), 120)
    operator("Plug the cable back in (2 minutes).")
    wait_for(lambda: ("connection", "reconnected") in events, 120)
    count = model.getStats()["samples"]
    wait_for(lambda: model.getStats()["samples"] > count + 5, 60)
    model.requestStop()
    thread.join(30)
    acq = read_acquisition(model.lastFile)
    assert [e.text for e in acq.events if e.kind == "connection"][-1] == "reconnected"


def test_power_cycle_during_acquisition(model):
    model.connect()
    thread, events = acquire_in_thread(model)
    wait_for(lambda: model.getStats()["samples"] >= 5, 60)
    operator("Switch the twilite off, wait 10 s, switch it on and start counting again (5 minutes).")
    wait_for(lambda: ("connection", "reconnected") in events, 300)
    count = model.getStats()["samples"]
    wait_for(lambda: model.getStats()["samples"] > count + 5, 120)
    model.requestStop()
    thread.join(30)
    kinds = [kind for kind, _ in events]
    # Expect the counter to restart after a power cycle; record what it actually did.
    print(f"Events during the power cycle: {events}")
    assert "connection" in kinds
