r"""Correction of the coincidence rate into activity concentration, as PSAMPLE does it.

With R(t) the coincidence rate, t in seconds from the PET scan start, B the
background, BR the branching ratio, CF the calibration factor and
lambda = ln 2 / T_half:

    C(t) = CF * (R(t) - B) * exp(lambda * t) / BR

Output before t = 0 is cut off. The calibration factor comes from a phantom run:

    CF = A_PET / mean over the plateau of [(R(t) - B) * exp(lambda * t) / BR]

All functions take plain sequences, so they work on lists and numpy arrays alike, and
skip NaN values (gaps) when they average.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from twilite.isotopes import Isotope


@dataclass(slots=True)
class CorrectionSettings:
    """What :func:`apply` needs to turn raw rates into activity concentration.

    Attributes:
        isotope: The tracer's isotope.
        pet_start: PET scan start, seconds since the epoch (PC clock).
        background: Fixed background rate, or ``None`` to average every sample before
            the PET start.
        calibration_factor: kBq/cc per unit of corrected rate.
    """

    isotope: Isotope
    pet_start: float
    background: float | None = None
    calibration_factor: float = 1.0


def decay_constant(half_life_s: float) -> float:
    """Return lambda = ln 2 / T_half, per second."""
    return math.log(2) / half_life_s


def mean_in_window(t: Sequence[float], values: Sequence[float], start: float, end: float) -> float:
    """Mean of ``values`` where ``start <= t < end``, ignoring NaN.

    Raises:
        ValueError: No sample falls in the window.
    """
    selected = [v for ti, v in zip(t, values) if start <= ti < end and not math.isnan(v)]
    if not selected:
        raise ValueError(f"No samples between {start:g} s and {end:g} s")
    return sum(selected) / len(selected)


def background_before_start(t_rel: Sequence[float], rate: Sequence[float]) -> float:
    """Mean rate of every sample before the PET start (t < 0)."""
    return mean_in_window(t_rel, rate, -math.inf, 0.0)


def decay_corrected(t_rel: Sequence[float], rate: Sequence[float], background: float,
                    isotope: Isotope) -> list[float]:
    """Return (R - B) * exp(lambda t) / BR for every sample, not cut at t = 0."""
    lam = decay_constant(isotope.half_life_s)
    return [(r - background) * math.exp(lam * ti) / isotope.branching_ratio for ti, r in zip(t_rel, rate)]


def correct(t_rel: Sequence[float], rate: Sequence[float], background: float, isotope: Isotope,
            calibration_factor: float = 1.0, cut_before_start: bool = True) -> tuple[list[float], list[float]]:
    """Return ``(t, C)`` with C the activity concentration of every sample.

    Args:
        t_rel: Sample times in seconds from the PET scan start.
        rate: Coincidence rate of every sample.
        background: Background rate B.
        isotope: The tracer's isotope.
        calibration_factor: CF.
        cut_before_start: Drop the samples before t = 0, as PSAMPLE does.
    """
    corrected = decay_corrected(t_rel, rate, background, isotope)
    pairs = [(ti, calibration_factor * c) for ti, c in zip(t_rel, corrected)
             if not cut_before_start or ti >= 0]
    return [p[0] for p in pairs], [p[1] for p in pairs]


def calibration_factor(t_rel: Sequence[float], rate: Sequence[float], background: float, isotope: Isotope,
                       plateau: tuple[float, float], activity_pet: float) -> float:
    """Return CF = A_PET / mean of the decay-corrected rate over the plateau window.

    Args:
        t_rel: Sample times in seconds from the reference time of ``activity_pet``.
        rate: Coincidence rate of every sample.
        background: Background rate B, averaged over a window before the step.
        isotope: The phantom's isotope.
        plateau: ``(start, end)`` of the plateau window, in the units of ``t_rel``.
        activity_pet: Phantom activity concentration from the PET, kBq/cc.
    """
    corrected = decay_corrected(t_rel, rate, background, isotope)
    plateau_mean = mean_in_window(t_rel, corrected, *plateau)
    if plateau_mean <= 0:
        raise ValueError("The plateau is not above the background")
    return activity_pet / plateau_mean


def apply(settings: CorrectionSettings, t_wall: Sequence[float],
          rate: Sequence[float]) -> tuple[list[float], list[float], float]:
    """Correct a whole acquisition; return ``(t_rel, C, background_used)``."""
    t_rel = [t - settings.pet_start for t in t_wall]
    if settings.background is None:
        background = background_before_start(t_rel, rate)
    else:
        background = settings.background
    t_out, c_out = correct(t_rel, rate, background, settings.isotope, settings.calibration_factor)
    return t_out, c_out, background
