import pytest

from twilite import ISOTOPES, Isotope, get_isotope


def test_table_has_the_plan_isotopes():
    assert set(ISOTOPES) == {"F-18", "Ga-68", "C-11", "N-13", "O-15", "Cu-64"}


def test_values_from_the_manual():
    assert get_isotope("Ga-68").branching_ratio == 0.891
    assert get_isotope("Cu-64").branching_ratio == 0.174


def test_half_lives_in_seconds():
    assert get_isotope("F-18").half_life_s == pytest.approx(6586.2)
    assert get_isotope("O-15").half_life_s == pytest.approx(122.2)
    assert get_isotope("Cu-64").half_life_s == pytest.approx(45720)


@pytest.mark.parametrize("name", ["F-18", "f18", "F 18", "f-18"])
def test_lookup_is_forgiving(name):
    assert get_isotope(name).name == "F-18"


def test_unknown_isotope():
    with pytest.raises(KeyError):
        get_isotope("Tc-99m")


@pytest.mark.parametrize("half_life, br", [(0, 0.5), (10, 0), (10, 1.5)])
def test_custom_isotope_is_validated(half_life, br):
    with pytest.raises(ValueError):
        Isotope("custom", half_life, br)
