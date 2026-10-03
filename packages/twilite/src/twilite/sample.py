"""Data types the driver hands to its callers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Sample:
    """One report line of the twilite, in counts per second.

    Attributes:
        index: The ``[n]`` counter at the start of the line: it goes up by one per line
            printed since power-up. -1 for a ``ccnt`` reply, which has none.
        singles1: Singles of detector 1.
        singles2: Singles of detector 2.
        coincidences: Coincidences.
        raw_extra: Every further value on the line, in order (two analog fields, always
            ``0.0`` on V3.00).
        raw: The line as received, without the line ending.
        t_wall: PC clock when the line arrived, seconds since the epoch.
        t_mono: Monotonic clock when the line arrived, seconds.
    """

    index: int
    singles1: float
    singles2: float
    coincidences: float
    raw_extra: tuple[float, ...] = ()
    raw: str = ""
    t_wall: float = 0.0
    t_mono: float = 0.0

