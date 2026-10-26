"""Units for the deterministic calculations.

Every number travels with its unit, conversions are explicit, and an unknown unit is an error rather than a
guess. Money is never converted between currencies: no exchange rate is built in.
"""

import math
import re

MASS_FLOW_TO_T_PER_YR = {"kg/yr": 0.001, "t/yr": 1.0, "kt/yr": 1000.0}
SHARE_TO_FRACTION = {"%": 0.01, "fraction": 1.0}
MOISTURE_TO_FRACTION = {"%": 0.01, "% of wet mass": 0.01, "fraction": 1.0}  # wet basis only
YIELD_TO_T_PER_T = {"%": 0.01, "fraction": 1.0, "t/t": 1.0}  # tonnes of product per tonne of usable dry feedstock
PER_MASS_TO_PER_T = {"t": 1.0, "kg": 1000.0}
CURRENCIES = ("USD", "EUR")
MONEY_RATE = re.compile(r"(USD|EUR)/(t|kg)")


class UnitError(ValueError):
    """A unit that isn't recognised, or is the wrong kind for the input."""


def check_number(value: float, name: str) -> float:
    """A real, finite number (not a bool, not NaN, not infinity)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number (got {value!r})")
    return float(value)


def _factor(table: dict[str, float], unit: str, name: str, kind: str) -> float:
    if unit not in table:
        raise UnitError(f"{name}: '{unit}' is not a {kind} unit. Use one of: {', '.join(table)}")
    return table[unit]


def mass_flow_t_per_yr(value: float, unit: str, name: str = "mass") -> float:
    """A yearly mass in tonnes per year. Must not be negative."""
    t = check_number(value, name) * _factor(MASS_FLOW_TO_T_PER_YR, unit, name, "yearly mass")
    if t < 0:
        raise ValueError(f"{name} can't be negative (got {value} {unit})")
    return t


def moisture_fraction(value: float, unit: str, name: str = "moisture") -> float:
    """Moisture as a fraction of the wet mass, from 0 to 1."""
    if "dry" in unit.lower():
        raise UnitError(f"{name}: moisture must be on a wet basis (share of the wet mass); convert '{unit}' first")
    f = check_number(value, name) * _factor(MOISTURE_TO_FRACTION, unit, name, "moisture")
    if not 0 <= f <= 1:
        raise ValueError(f"{name} must be between 0 and 100% of the wet mass (got {value} {unit})")
    return f


def share_fraction(value: float, unit: str, name: str) -> float:
    """A share such as an availability or recovery fraction, from 0 to 1."""
    f = check_number(value, name) * _factor(SHARE_TO_FRACTION, unit, name, "share")
    if not 0 <= f <= 1:
        raise ValueError(f"{name} must be between 0 and 100% (got {value} {unit})")
    return f


def yield_t_per_t(value: float, unit: str, name: str = "yield") -> float:
    """Tonnes of product per tonne of usable dry feedstock. Can exceed 1 when a process adds mass."""
    y = check_number(value, name) * _factor(YIELD_TO_T_PER_T, unit, name, "yield")
    if y < 0:
        raise ValueError(f"{name} can't be negative (got {value} {unit})")
    return y


def money_per_t(value: float, unit: str, name: str) -> tuple[float, str]:
    """A price or cost rate as (amount per tonne, currency), e.g. 0.5 'USD/kg' -> (500.0, 'USD')."""
    m = MONEY_RATE.fullmatch(unit)
    if not m:
        raise UnitError(f"{name}: '{unit}' is not a money-per-mass unit. Use <currency>/<t or kg> with a currency "
                        f"from {', '.join(CURRENCIES)}, e.g. USD/t")
    amount = check_number(value, name) * PER_MASS_TO_PER_T[m.group(2)]
    if amount < 0:
        raise ValueError(f"{name} can't be negative (got {value} {unit})")
    return amount, m.group(1)
