"""A simulated twilite that speaks the same telnet protocol as the device.

Run it with ``python -m twilite.sim --help``.
"""

from twilite.sim.scenarios import SCENARIOS, Counter, Scenario, make_scenario
from twilite.sim.server import DEFAULT_PORT, Faults, TwiliteSimulator

__all__ = [
    "DEFAULT_PORT",
    "SCENARIOS",
    "Counter",
    "Faults",
    "Scenario",
    "TwiliteSimulator",
    "make_scenario",
]
