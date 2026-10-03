"""Shared test setup.

``uv run pytest`` runs the unit, integration and app layers against the simulator.
``uv run pytest --hardware --host <ip>`` runs the integration tests that do not need
fault injection, plus the hardware layer, against a real twilite.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from twilite import protocol
from twilite.sim import Faults, TwiliteSimulator

FIXTURES = Path(__file__).parent / "fixtures"


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("twilite")
    group.addoption("--hardware", action="store_true", help="run against a real twilite")
    group.addoption("--host", help="IP address of the twilite (with --hardware)")
    group.addoption("--port", type=int, default=protocol.DEFAULT_PORT, help="telnet port of the twilite")


def pytest_configure(config: pytest.Config) -> None:
    if config.getoption("--hardware") and not config.getoption("--host"):
        raise pytest.UsageError("--hardware needs --host <ip>")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    hardware = config.getoption("--hardware")
    for item in items:
        if "hardware" in item.keywords and not hardware:
            item.add_marker(pytest.mark.skip(reason="needs --hardware --host <ip>"))
        if "simulator_only" in item.keywords and hardware:
            item.add_marker(pytest.mark.skip(reason="fault injection needs the simulator"))


@dataclass
class Target:
    """Where a test connects: the simulator, or a real device with --hardware."""

    host: str
    port: int
    simulator: TwiliteSimulator | None = None

    @property
    def is_hardware(self) -> bool:
        return self.simulator is None


def start_simulator(faults: Faults | None = None, **kwargs) -> TwiliteSimulator:
    simulator = TwiliteSimulator(port=0, faults=faults, **kwargs)
    simulator.start_in_thread()
    return simulator


@pytest.fixture
def simulator_factory():
    """Start simulators with any options; all are stopped after the test."""
    started: list[TwiliteSimulator] = []

    def factory(faults: Faults | None = None, **kwargs) -> TwiliteSimulator:
        simulator = start_simulator(faults, **kwargs)
        started.append(simulator)
        return simulator

    yield factory
    for simulator in started:
        simulator.stop()


@pytest.fixture
def target(request: pytest.FixtureRequest, simulator_factory) -> Target:
    """A twilite to talk to: the simulator, or the device with --hardware."""
    config = request.config
    if config.getoption("--hardware"):
        return Target(config.getoption("--host"), config.getoption("--port"))
    simulator = simulator_factory()
    return Target("127.0.0.1", simulator.port, simulator=simulator)
