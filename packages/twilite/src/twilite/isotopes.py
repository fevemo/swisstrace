"""Half-lives and positron branching ratios of the isotopes used with the twilite.

TO VERIFY: the Ga-68 and Cu-64 branching ratios come from the PSAMPLE manual; the
other values are standard figures that still have to be checked against a nuclear
data table (the manual points to Turku PET Centre) before clinical use.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Isotope:
    """A positron emitter.

    Attributes:
        name: Display name, such as ``"F-18"``.
        half_life_s: Physical half-life in seconds.
        branching_ratio: Fraction of decays that emit a positron.
    """

    name: str
    half_life_s: float
    branching_ratio: float

    def __post_init__(self) -> None:
        if self.half_life_s <= 0:
            raise ValueError(f"Half-life must be positive, not {self.half_life_s}")
        if not 0 < self.branching_ratio <= 1:
            raise ValueError(f"Branching ratio must be in (0, 1], not {self.branching_ratio}")


_MIN = 60.0
_HOUR = 3600.0

ISOTOPES: dict[str, Isotope] = {
    iso.name: iso
    for iso in (
        Isotope("F-18", 109.77 * _MIN, 0.967),
        Isotope("Ga-68", 67.71 * _MIN, 0.891),
        Isotope("C-11", 20.36 * _MIN, 0.998),
        Isotope("N-13", 9.97 * _MIN, 0.998),
        Isotope("O-15", 122.2, 0.999),
        Isotope("Cu-64", 12.70 * _HOUR, 0.174),
    )
}


def get_isotope(name: str) -> Isotope:
    """Return a tabulated isotope by name (case and dashes ignored, so ``f18`` works)."""
    key = name.replace("-", "").replace(" ", "").lower()
    for isotope in ISOTOPES.values():
        if isotope.name.replace("-", "").lower() == key:
            return isotope
    raise KeyError(f"Unknown isotope {name!r}; known: {', '.join(ISOTOPES)}")
