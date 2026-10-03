"""Count generators for the simulated twilite.

A scenario gives the expected singles and coincidence rates at time t (seconds since
the simulator started). :class:`Counter` turns them into Poisson counts with a fixed
seed, so a test always sees the same numbers.
"""

from __future__ import annotations

import ast
import math
import random
import re
from dataclasses import dataclass, field
from pathlib import Path

from twilite import protocol
from twilite.isotopes import ISOTOPES, Isotope

#: Background levels from the manual's example lines (LYSO intrinsic activity).
BACKGROUND_SINGLES1 = 2000.0
BACKGROUND_SINGLES2 = 1550.0
BACKGROUND_COINCIDENCES = 120.0
#: Extra singles per coincidence of a positron source in the detector.
SINGLES_PER_COINCIDENCE = 8.0


def poisson(rng: random.Random, mean: float) -> int:
    """Draw a Poisson count; uses the normal approximation for large means."""
    if mean <= 0:
        return 0
    if mean > 50:
        return max(0, round(rng.gauss(mean, math.sqrt(mean))))
    limit, k, p = math.exp(-mean), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


@dataclass
class Scenario:
    """No source: the LYSO background only."""

    name = "background"
    isotope: Isotope = field(default_factory=lambda: ISOTOPES["F-18"])

    @property
    def decay_constant(self) -> float:
        return math.log(2) / self.isotope.half_life_s

    def signal(self, t: float) -> float:
        """Coincidence rate of the source alone, per second."""
        return 0.0

    def rates(self, t: float) -> tuple[float, float, float]:
        """Expected ``(singles1, singles2, coincidences)`` per second at time t."""
        s = self.signal(t)
        return (BACKGROUND_SINGLES1 + SINGLES_PER_COINCIDENCE * s,
                BACKGROUND_SINGLES2 + SINGLES_PER_COINCIDENCE * s,
                BACKGROUND_COINCIDENCES + s)


@dataclass
class Bolus(Scenario):
    """Background, then a gamma-variate peak with a slow tail, decaying."""

    name = "bolus"
    arrival_s: float = 30.0
    time_to_peak_s: float = 20.0
    peak_cps: float = 4000.0
    alpha: float = 3.0
    tail_fraction: float = 0.15
    tail_rise_s: float = 120.0

    def signal(self, t: float) -> float:
        if t <= self.arrival_s:
            return 0.0
        dt = t - self.arrival_s
        x = dt / self.time_to_peak_s
        gamma_variate = x ** self.alpha * math.exp(self.alpha * (1 - x))
        tail = self.tail_fraction * (1 - math.exp(-dt / self.tail_rise_s))
        return self.peak_cps * (gamma_variate + tail) * math.exp(-self.decay_constant * dt)


@dataclass
class CalibrationStep(Scenario):
    """Background, then a step when the source goes in; the source decays from t = 0."""

    name = "calibration-step"
    step_s: float = 60.0
    level_cps: float = 3000.0

    def signal(self, t: float) -> float:
        if t < self.step_s:
            return 0.0
        return self.level_cps * math.exp(-self.decay_constant * t)


@dataclass
class LongDecay(Scenario):
    """A source present from the start, decaying over several half-lives."""

    name = "long-decay"
    level_cps: float = 5000.0

    def signal(self, t: float) -> float:
        return self.level_cps * math.exp(-self.decay_constant * t)


@dataclass
class Replay(Scenario):
    """Plays back the report lines of a recorded transcript.

    Accepts the driver's raw log (``<time> << b'...'`` lines, replayed at the recorded
    pace) or a plain text session log such as PuTTY's (replayed at the report rate).
    """

    name = "replay"
    transcript: Path | None = None
    lines: list[str] = field(default_factory=list)
    delays_s: list[float | None] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.transcript is not None and not self.lines:
            self.lines, self.delays_s = load_transcript(self.transcript)


SCENARIOS: dict[str, type[Scenario]] = {
    cls.name: cls for cls in (Scenario, Bolus, CalibrationStep, LongDecay, Replay)
}


def make_scenario(name: str, isotope: Isotope | None = None, **kwargs) -> Scenario:
    """Build a scenario by name; ``kwargs`` override its parameters."""
    try:
        cls = SCENARIOS[name]
    except KeyError:
        raise KeyError(f"Unknown scenario {name!r}; known: {', '.join(SCENARIOS)}") from None
    if isotope is not None:
        kwargs["isotope"] = isotope
    return cls(**kwargs)


_RAW_LOG_LINE = re.compile(r"^(\S+) << (b(['\"]).*\3)$")


def load_transcript(path: str | Path) -> tuple[list[str], list[float | None]]:
    """Return the report lines of a transcript and the delay before each (or None)."""
    from datetime import datetime

    text = Path(path).read_text(encoding="latin-1")
    received = []
    for line in text.splitlines():
        match = _RAW_LOG_LINE.match(line)
        if match:
            received.append((datetime.fromisoformat(match.group(1)).timestamp(), ast.literal_eval(match.group(2))))
    if not received:
        # Plain session log: every line that parses, no timing.
        lines = [l.strip() for l in text.splitlines() if protocol.parse_sample(l) is not None]
        return lines, [None] * len(lines)
    lines, delays = [], []
    buffer, previous = b"", None
    for stamp, data in received:
        complete, buffer = protocol.split_lines(buffer + data)
        if protocol.ends_with_prompt(buffer):
            buffer = b""  # as the driver does before each command
        for raw in complete:
            text_line = protocol.decode(raw)
            if protocol.parse_sample(text_line) is not None:
                lines.append(text_line)
                delays.append(None if previous is None else max(0.0, stamp - previous))
                previous = stamp
    return lines, delays


@dataclass
class Counter:
    """The twilite's counters, as on Coincident Counter V3.00.

    Every printed line counts over the report period and scales to counts per second
    (so at 100 ms the values come in steps of 10), and ``[n]`` goes up by one per line
    from 0.

    Args:
        scenario: Rates to draw counts from.
        seed: Random seed.
    """

    scenario: Scenario
    seed: int = 1
    index: int = -1
    values: tuple[int, int, int] = (0, 0, 0)

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)

    def report(self, t: float, window_s: float, advance: bool = True) -> None:
        """Count over the ``window_s`` before t, as counts per second; ``[n]`` goes up by one.

        With ``advance=False`` only the values change, as for ``ccnt``.
        """
        mid = max(0.0, t - window_s / 2)
        s1, s2, c = (round(poisson(self.rng, r * window_s) / window_s) for r in self.scenario.rates(mid))
        self.values = (s1, s2, c)
        if advance:
            self.index += 1

    def line(self) -> str:
        s1, s2, c = self.values
        return f"[{self.index}] {s1} {s2} {c} 0.0 0.0"
