"""Units: explicit conversions, and clear errors for anything unrecognised, out of range, or not a number."""

import math

import pytest

from backend import units
from backend.units import UnitError


@pytest.mark.parametrize("value, unit, expected", [(40_000, "t/yr", 40_000), (40, "kt/yr", 40_000),
                                                   (40_000_000, "kg/yr", 40_000), (0, "t/yr", 0)])
def test_mass_flow_conversion(value, unit, expected):
    assert units.mass_flow_t_per_yr(value, unit) == pytest.approx(expected)


@pytest.mark.parametrize("unit", ["lb/yr", "t", "tonnes/yr", "T/yr", ""])
def test_unknown_mass_unit_is_rejected(unit):
    with pytest.raises(UnitError, match="not a yearly mass unit"):
        units.mass_flow_t_per_yr(1, unit)


def test_negative_mass_is_rejected():
    with pytest.raises(ValueError, match="can't be negative"):
        units.mass_flow_t_per_yr(-1, "t/yr")


@pytest.mark.parametrize("value, unit, expected", [(35, "%", 0.35), (35, "% of wet mass", 0.35), (0.35, "fraction", 0.35),
                                                   (0, "%", 0.0), (100, "%", 1.0)])
def test_moisture_conversion_and_boundaries(value, unit, expected):
    assert units.moisture_fraction(value, unit) == pytest.approx(expected)


@pytest.mark.parametrize("unit", ["% dry basis", "% of dry mass", "fraction (dry basis)"])
def test_dry_basis_moisture_is_rejected(unit):
    with pytest.raises(UnitError, match="wet basis"):
        units.moisture_fraction(50, unit)


@pytest.mark.parametrize("value, unit", [(100.1, "%"), (-0.1, "%"), (1.2, "fraction")])
def test_moisture_out_of_range(value, unit):
    with pytest.raises(ValueError, match="between 0 and 100%"):
        units.moisture_fraction(value, unit)


@pytest.mark.parametrize("value, unit, expected", [(50, "%", 0.5), (0.5, "fraction", 0.5), (0, "%", 0), (100, "%", 1)])
def test_share_conversion_and_boundaries(value, unit, expected):
    assert units.share_fraction(value, unit, "availability") == pytest.approx(expected)


def test_share_rejects_unknown_unit_and_out_of_range():
    with pytest.raises(UnitError, match="not a share unit"):
        units.share_fraction(50, "percent", "availability")
    with pytest.raises(ValueError, match="between 0 and 100%"):
        units.share_fraction(101, "%", "availability")


@pytest.mark.parametrize("value, unit, expected", [(90, "%", 0.9), (0.9, "fraction", 0.9), (1.4, "t/t", 1.4), (0, "t/t", 0)])
def test_yield_conversion(value, unit, expected):
    assert units.yield_t_per_t(value, unit) == pytest.approx(expected)


def test_yield_rejects_negative_and_unknown_unit():
    with pytest.raises(ValueError, match="can't be negative"):
        units.yield_t_per_t(-0.1, "t/t")
    with pytest.raises(UnitError, match="not a yield unit"):
        units.yield_t_per_t(0.5, "kg/kg")


@pytest.mark.parametrize("value, unit, expected", [(800, "USD/t", (800, "USD")), (0.8, "USD/kg", (800, "USD")),
                                                   (700, "EUR/t", (700, "EUR")), (0, "USD/t", (0, "USD"))])
def test_money_rates(value, unit, expected):
    amount, currency = units.money_per_t(value, unit, "price")
    assert (amount, currency) == (pytest.approx(expected[0]), expected[1])


@pytest.mark.parametrize("unit", ["$/t", "USD per t", "GBP/t", "USD/lb", "USD", "usd/t"])
def test_unknown_money_unit_is_rejected(unit):
    with pytest.raises(UnitError, match="not a money-per-mass unit"):
        units.money_per_t(1, unit, "price")


def test_negative_money_is_rejected():
    with pytest.raises(ValueError, match="can't be negative"):
        units.money_per_t(-5, "USD/t", "price")


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, True, "40", None])
def test_numbers_must_be_finite(bad):
    with pytest.raises(ValueError, match="finite number"):
        units.check_number(bad, "x")
