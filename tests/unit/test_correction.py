"""Correction maths against values worked out by hand."""

import math

import pytest

from twilite import Isotope, get_isotope
from twilite.correction import (
    CorrectionSettings, apply, background_before_start, calibration_factor, correct, decay_constant, mean_in_window,
)

F18 = get_isotope("F-18")
T_HALF = 109.77 * 60  # 6586.2 s


def test_decay_constant():
    assert decay_constant(T_HALF) == pytest.approx(0.693147 / 6586.2, rel=1e-6)


def test_one_half_life_doubles():
    # (1120 - 120) * 2 / 0.967 = 2068.2523...
    t, c = correct([T_HALF], [1120.0], background=120.0, isotope=F18)
    assert t == [T_HALF]
    assert c[0] == pytest.approx(2068.2523, rel=1e-7)


def test_at_pet_start_only_background_branching_and_cf():
    # (620 - 120) / 0.5 * 3 = 3000
    iso = Isotope("test", 100.0, 0.5)
    _, c = correct([0.0], [620.0], 120.0, iso, calibration_factor=3.0)
    assert c == [pytest.approx(3000.0)]


def test_samples_before_start_are_cut():
    t, _ = correct([-2.0, -1.0, 0.0, 1.0], [1, 2, 3, 4], 0.0, F18)
    assert t == [0.0, 1.0]
    t, _ = correct([-2.0, 1.0], [1, 4], 0.0, F18, cut_before_start=False)
    assert t == [-2.0, 1.0]


def test_background_is_mean_before_start_ignoring_nan():
    assert background_before_start([-3, -2, -1, 0, 1], [100, math.nan, 140, 999, 999]) == 120


def test_mean_in_window_needs_samples():
    assert mean_in_window([0, 1, 2, 3], [1, 2, 3, 4], 1, 3) == 2.5
    with pytest.raises(ValueError):
        mean_in_window([0, 1], [1, 2], 5, 6)


def test_calibration_factor_on_decaying_plateau():
    # R = B + 1000 exp(-lambda t): the decay-corrected plateau is 1000 / BR,
    # so CF = 50 kBq/cc * 0.967 / 1000 = 0.04835.
    lam = decay_constant(F18.half_life_s)
    t = list(range(0, 600, 10))
    rate = [120 + 1000 * math.exp(-lam * ti) for ti in t]
    cf = calibration_factor(t, rate, 120.0, F18, plateau=(100, 500), activity_pet=50.0)
    assert cf == pytest.approx(0.04835, rel=1e-9)


def test_calibration_factor_rejects_flat_plateau():
    with pytest.raises(ValueError):
        calibration_factor([0, 1, 2], [120, 120, 120], 120.0, F18, (0, 3), 50.0)


def test_apply_with_measured_and_fixed_background():
    pet_start = 1_000_000.0
    t_wall = [pet_start - 20, pet_start - 10, pet_start, pet_start + T_HALF]
    rate = [110, 130, 1120, 620]
    settings = CorrectionSettings(F18, pet_start, background=None, calibration_factor=2.0)
    t, c, background = apply(settings, t_wall, rate)
    assert background == 120
    assert t == [0.0, pytest.approx(T_HALF)]
    # 2 * 1000 / 0.967 at t = 0; 2 * 500 * 2 / 0.967 one half-life later.
    assert c == [pytest.approx(2 * 1000 / 0.967), pytest.approx(2 * 500 * 2 / 0.967)]
    settings.background = 20.0
    _, c, background = apply(settings, t_wall, rate)
    assert background == 20.0
    assert c[0] == pytest.approx(2 * 1100 / 0.967)
