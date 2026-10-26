"""Deterministic business logic: from wet feedstock to indicative gross contribution.

The chain, per year:

    dry mass             = wet mass x (1 - moisture)
    usable feedstock     = dry mass x availability fraction          (only when the fraction is supplied)
    product output       = usable feedstock x yield                  (only when the yield is supplied)
    revenue              = product output x price
    variable cost        = sum of cost items, each per tonne of product or per tonne of usable feedstock
    gross contribution   = revenue - variable cost
    contribution per t   = gross contribution / usable feedstock

Rules:
- a missing input is never treated as zero: the step that needs it, and every step after it, is reported as
  'not calculated' with the reason
- units are checked and converted explicitly, money is never converted between currencies, and every result
  carries its unit
- every input carries its basis (measured, evidence, or assumption) and is listed in the output
- gross margin, profitability, NPV, and IRR are not calculated: they need capital and fixed costs, a discount
  rate, a time horizon, and agreed definitions that BioValue AI doesn't have yet

No model calls. In phase 2 the agents call these functions as tools.
"""

from typing import Literal

from pydantic import Field, model_validator

from backend import units
from backend.feedstock import FeedstockProfile, Quantity
from backend.models import Frozen

ScenarioName = Literal["conservative", "base", "optimistic"]
SCENARIOS: tuple[ScenarioName, ...] = ("conservative", "base", "optimistic")
InputBasis = Literal["measured", "evidence", "analyst_assumption", "fictional_assumption"]
CostPer = Literal["product", "usable_feedstock"]

NOT_CALCULATED_METRICS = (
    "Gross margin, profitability, NPV, and IRR are not calculated. They need capital costs, fixed costs, a discount "
    "rate, a time horizon, and agreed definitions, none of which are available yet. Gross contribution excludes "
    "capital costs, fixed costs, and the value of the feedstock in its current use."
)


# --- Inputs ---------------------------------------------------------------------------------


class ScenarioInput(Frozen):
    """One input with its unit and provenance. Give `base` alone (held constant across all three scenarios) or
    give conservative, base, and optimistic together."""

    base: float
    conservative: float | None = None
    optimistic: float | None = None
    unit: str
    basis: InputBasis
    evidence_ids: tuple[str, ...] = ()
    note: str = ""

    @model_validator(mode="after")
    def _check(self):
        for name in ("base", "conservative", "optimistic"):
            value = getattr(self, name)
            if value is not None:
                units.check_number(value, name)
        if (self.conservative is None) != (self.optimistic is None):
            raise ValueError("give both conservative and optimistic values, or neither (base only = held constant)")
        if self.basis == "evidence" and not self.evidence_ids:
            raise ValueError("an input based on evidence needs at least one evidence id")
        if self.basis in ("analyst_assumption", "fictional_assumption") and not self.note.strip():
            raise ValueError("an assumption needs a note explaining it")
        return self

    @property
    def varies(self) -> bool:
        return self.conservative is not None

    def at(self, scenario: ScenarioName) -> float:
        if scenario == "conservative" and self.conservative is not None:
            return self.conservative
        if scenario == "optimistic" and self.optimistic is not None:
            return self.optimistic
        return self.base


class CostItem(Frozen):
    name: str
    rate: ScenarioInput  # money per mass, e.g. USD/t
    per: CostPer  # whether the rate is per tonne of product or per tonne of usable dry feedstock


# How each input is checked, and which direction is better (conservative must be the worse end).
INPUT_RULES: dict[str, tuple[str, bool]] = {
    "wet_mass": ("wet feedstock mass", True),
    "moisture": ("moisture", False),
    "availability": ("availability fraction", True),
    "product_yield": ("product yield", True),
    "price": ("product price", True),
}


def _validate(field: str, label: str, value: float, unit: str) -> None:
    if field == "wet_mass":
        units.mass_flow_t_per_yr(value, unit, label)
    elif field == "moisture":
        units.moisture_fraction(value, unit, label)
    elif field == "availability":
        units.share_fraction(value, unit, label)
    elif field == "product_yield":
        units.yield_t_per_t(value, unit, label)
    else:
        units.money_per_t(value, unit, label)


def _check_direction(label: str, inp: ScenarioInput, higher_is_better: bool) -> None:
    if not inp.varies:
        return
    c, b, o = inp.conservative, inp.base, inp.optimistic
    if not (c <= b <= o if higher_is_better else c >= b >= o):
        order = "low to high" if higher_is_better else "high to low"
        raise ValueError(f"{label}: conservative, base, and optimistic must run from worse to better ({order} "
                         f"for this input); got {c:g}, {b:g}, {o:g}")


class PathwayInputs(Frozen):
    """Everything the economics need for one product pathway. Any input may be missing (None)."""

    pathway_id: str
    product: str  # what the mill would sell, e.g. "lignin polyol"
    wet_mass: ScenarioInput | None = None
    moisture: ScenarioInput | None = None
    availability: ScenarioInput | None = None  # explicitly supplied recovery or availability fraction
    product_yield: ScenarioInput | None = None  # t product per t usable dry feedstock
    price: ScenarioInput | None = None  # money per mass of product
    variable_costs: tuple[CostItem, ...] | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _check(self):
        for field, (label, higher_is_better) in INPUT_RULES.items():
            inp = getattr(self, field)
            if inp is None:
                continue
            for scenario in SCENARIOS:
                _validate(field, label, inp.at(scenario), inp.unit)
            _check_direction(label, inp, higher_is_better)
        currencies = set()
        if self.price is not None:
            currencies.add(units.money_per_t(self.price.base, self.price.unit, "product price")[1])
        for item in self.variable_costs or ():
            for scenario in SCENARIOS:
                currencies.add(units.money_per_t(item.rate.at(scenario), item.rate.unit, item.name)[1])
            _check_direction(item.name, item.rate, higher_is_better=False)
        if len(currencies) > 1:
            raise ValueError(f"price and costs use different currencies ({', '.join(sorted(currencies))}); "
                             "no exchange rate is applied, so convert them to one currency first")
        return self

    @property
    def currency(self) -> str | None:
        if self.price is not None:
            return units.money_per_t(self.price.base, self.price.unit, "product price")[1]
        if self.variable_costs:
            return units.money_per_t(self.variable_costs[0].rate.base, self.variable_costs[0].rate.unit, "cost")[1]
        return None

    def missing_inputs(self) -> list[str]:
        labels = {**{f: label for f, (label, _) in INPUT_RULES.items()}, "variable_costs": "variable costs"}
        return [label for field, label in labels.items() if getattr(self, field) is None]


class PathwayAssumptions(Frozen):
    """Economic inputs supplied for one pathway in a project. Anything left out is reported as missing."""

    product: str
    availability: ScenarioInput | None = None
    product_yield: ScenarioInput | None = None
    price: ScenarioInput | None = None
    variable_costs: tuple[CostItem, ...] | None = Field(default=None, min_length=1)


def build_pathway_inputs(pathway_id: str, feedstock: FeedstockProfile, assumptions: PathwayAssumptions | None,
                         default_product: str) -> PathwayInputs:
    """Wet mass and moisture from the feedstock profile, plus whatever the project supplies for this pathway."""
    supplied = assumptions.model_dump(exclude={"product"}, exclude_none=True) if assumptions else {}
    product = assumptions.product if assumptions else default_product
    return PathwayInputs(pathway_id=pathway_id, product=product, **feedstock_inputs(feedstock), **supplied)


# --- Results --------------------------------------------------------------------------------


class Step(Frozen):
    key: str
    label: str
    status: Literal["calculated", "not_calculated"]
    value: float | None  # None when not calculated
    unit: str
    formula: str
    inputs: tuple[str, ...] = ()  # the values used, with units
    reason: str = ""  # why it wasn't calculated
    warnings: tuple[str, ...] = ()


class ScenarioResult(Frozen):
    scenario: ScenarioName
    steps: dict[str, Step]


class AssumptionLine(Frozen):
    input: str
    conservative: float | None
    base: float
    optimistic: float | None
    unit: str
    held_constant: bool  # True when only a base value was supplied
    basis: InputBasis
    evidence_ids: tuple[str, ...]
    note: str


class ScenarioAnalysis(Frozen):
    pathway_id: str
    product: str
    scenarios: dict[ScenarioName, ScenarioResult]
    assumptions: tuple[AssumptionLine, ...]
    missing_inputs: tuple[str, ...]
    not_calculated_metrics: str = NOT_CALCULATED_METRICS


# --- Arithmetic (each function checks and converts its own units) -----------------------------


def dry_mass(wet_value: float, wet_unit: str, moisture_value: float, moisture_unit: str) -> float:
    """Dry mass in t/yr: wet mass x (1 - moisture), with moisture on a wet basis."""
    wet = units.mass_flow_t_per_yr(wet_value, wet_unit, "wet feedstock mass")
    return wet * (1 - units.moisture_fraction(moisture_value, moisture_unit))


def usable_feedstock(dry_t_per_yr: float, fraction_value: float, fraction_unit: str) -> float:
    """Usable dry feedstock in t/yr: dry mass x the supplied availability (or recovery) fraction."""
    dry = units.mass_flow_t_per_yr(dry_t_per_yr, "t/yr", "dry mass")
    return dry * units.share_fraction(fraction_value, fraction_unit, "availability fraction")


def product_output(usable_t_per_yr: float, yield_value: float, yield_unit: str) -> float:
    """Product in t/yr: usable dry feedstock x yield (t product per t usable dry feedstock)."""
    usable = units.mass_flow_t_per_yr(usable_t_per_yr, "t/yr", "usable feedstock")
    return usable * units.yield_t_per_t(yield_value, yield_unit)


def revenue(product_t_per_yr: float, price_value: float, price_unit: str) -> tuple[float, str]:
    """(revenue per year, currency): product output x price."""
    product = units.mass_flow_t_per_yr(product_t_per_yr, "t/yr", "product output")
    price, currency = units.money_per_t(price_value, price_unit, "product price")
    return product * price, currency


def variable_cost(product_t_per_yr: float | None, usable_t_per_yr: float | None,
                  items: list[tuple[str, float, str, CostPer]]) -> tuple[float, str]:
    """(variable cost per year, currency): the sum of (name, rate, unit, per) items. A per-product item needs the
    product output and a per-feedstock item needs the usable feedstock; all items must share one currency."""
    if not items:
        raise ValueError("at least one cost item is needed; give an explicit zero-cost item if there is no cost")
    total, currencies = 0.0, set()
    for name, rate_value, rate_unit, per in items:
        rate, currency = units.money_per_t(rate_value, rate_unit, name)
        basis = product_t_per_yr if per == "product" else usable_t_per_yr
        if basis is None:
            raise ValueError(f"{name} is charged per tonne of {per.replace('_', ' ')}, which isn't available")
        total += rate * units.mass_flow_t_per_yr(basis, "t/yr", per)
        currencies.add(currency)
    if len(currencies) > 1:
        raise units.UnitError(f"cost items use different currencies ({', '.join(sorted(currencies))})")
    return total, currencies.pop()


def gross_contribution(revenue_amount: float, revenue_currency: str,
                       cost_amount: float, cost_currency: str) -> tuple[float, str]:
    """(revenue - variable cost, currency). Refuses to subtract amounts in different currencies."""
    if revenue_currency != cost_currency:
        raise units.UnitError(f"revenue is in {revenue_currency} but variable cost is in {cost_currency}")
    return units.check_number(revenue_amount, "revenue") - units.check_number(cost_amount, "variable cost"), revenue_currency


# --- Scenario analysis ------------------------------------------------------------------------


def _fmt(value: float, unit: str) -> str:
    return f"{value:,.4g} {unit}" if abs(value) < 1000 else f"{value:,.0f} {unit}"


def _calculated(key: str, label: str, value: float, unit: str, formula: str, inputs: list[str],
                warnings: list[str] | None = None) -> Step:
    # Rounded to 6 decimals so float noise (25999.999999999996) doesn't reach reports; far below any unit shown.
    return Step(key=key, label=label, status="calculated", value=round(value, 6), unit=unit, formula=formula,
                inputs=tuple(inputs), warnings=tuple(warnings or ()))


def _not_calculated(key: str, label: str, unit: str, formula: str, reason: str) -> Step:
    return Step(key=key, label=label, status="not_calculated", value=None, unit=unit, formula=formula,
                reason=f"Not calculated: {reason}.")


def _needs(steps: dict[str, Step], *keys: str) -> str:
    """A reason naming earlier steps that weren't calculated, or '' when all of them were."""
    missing = [steps[k].label.lower() for k in keys if steps[k].status != "calculated"]
    return f"needs {' and '.join(missing)}, which could not be calculated" if missing else ""


def run_scenario(inputs: PathwayInputs, scenario: ScenarioName) -> ScenarioResult:
    """All steps of the chain for one scenario. Missing inputs stop the steps that need them, nothing more."""
    s: dict[str, Step] = {}
    money = f"{inputs.currency or '(currency unknown)'}"

    key, label, unit, formula = "dry_mass", "Dry mass", "t/yr dry", "wet mass x (1 - moisture)"
    if inputs.wet_mass is None or inputs.moisture is None:
        absent = [n for n, v in (("wet feedstock mass", inputs.wet_mass), ("moisture", inputs.moisture)) if v is None]
        s[key] = _not_calculated(key, label, unit, formula, f"{' and '.join(absent)} not supplied")
    else:
        w, m = inputs.wet_mass, inputs.moisture
        value = dry_mass(w.at(scenario), w.unit, m.at(scenario), m.unit)
        warnings = ["Dry mass is zero: no dry matter to work with."] if value == 0 else []
        s[key] = _calculated(key, label, value, unit, formula,
                             [f"wet mass = {_fmt(w.at(scenario), w.unit)}", f"moisture = {_fmt(m.at(scenario), m.unit)}"],
                             warnings)

    key, label, unit, formula = "usable_feedstock", "Usable feedstock", "t/yr usable dry feedstock", "dry mass x availability fraction"
    if reason := _needs(s, "dry_mass"):
        s[key] = _not_calculated(key, label, unit, formula, reason)
    elif inputs.availability is None:
        s[key] = _not_calculated(key, label, unit, formula, "availability fraction not supplied (no default is assumed)")
    else:
        a = inputs.availability
        value = usable_feedstock(s["dry_mass"].value, a.at(scenario), a.unit)
        warnings = ["Usable feedstock is zero."] if value == 0 else []
        s[key] = _calculated(key, label, value, unit, formula,
                             [f"dry mass = {_fmt(s['dry_mass'].value, 't/yr')}", f"availability = {_fmt(a.at(scenario), a.unit)}"],
                             warnings)

    key, label, unit, formula = "product_output", "Product output", "t/yr product", "usable feedstock x yield"
    if reason := _needs(s, "usable_feedstock"):
        s[key] = _not_calculated(key, label, unit, formula, reason)
    elif inputs.product_yield is None:
        s[key] = _not_calculated(key, label, unit, formula, "product yield not supplied")
    else:
        y = inputs.product_yield
        value = product_output(s["usable_feedstock"].value, y.at(scenario), y.unit)
        warnings = []
        if units.yield_t_per_t(y.at(scenario), y.unit) > 1:
            warnings.append("Yield is above 1 t/t: product mass exceeds feedstock mass. Check that added reagents are intended.")
        if value == 0:
            warnings.append("Product output is zero.")
        s[key] = _calculated(key, label, value, unit, formula,
                             [f"usable feedstock = {_fmt(s['usable_feedstock'].value, 't/yr')}",
                              f"yield = {_fmt(y.at(scenario), y.unit)}"], warnings)

    key, label, unit, formula = "revenue", "Revenue", f"{money}/yr", "product output x price"
    if reason := _needs(s, "product_output"):
        s[key] = _not_calculated(key, label, unit, formula, reason)
    elif inputs.price is None:
        s[key] = _not_calculated(key, label, unit, formula, "product price not supplied")
    else:
        p = inputs.price
        value, _ = revenue(s["product_output"].value, p.at(scenario), p.unit)
        s[key] = _calculated(key, label, value, unit, formula,
                             [f"product output = {_fmt(s['product_output'].value, 't/yr')}",
                              f"price = {_fmt(p.at(scenario), p.unit)}"],
                             ["Price is zero, so revenue is zero."] if p.at(scenario) == 0 else [])

    key, label, unit, formula = "variable_cost", "Variable processing cost", f"{money}/yr", "sum of cost rate x tonnes it applies to"
    if inputs.variable_costs is None:
        s[key] = _not_calculated(key, label, unit, formula, "variable costs not supplied (no default is assumed)")
    else:
        needed = {"product_output" if c.per == "product" else "usable_feedstock" for c in inputs.variable_costs}
        if reason := _needs(s, *sorted(needed)):
            s[key] = _not_calculated(key, label, unit, formula, reason)
        else:
            items = [(c.name, c.rate.at(scenario), c.rate.unit, c.per) for c in inputs.variable_costs]
            value, _ = variable_cost(s["product_output"].value, s["usable_feedstock"].value, items)
            s[key] = _calculated(key, label, value, unit, formula,
                                 [f"{c.name} = {_fmt(c.rate.at(scenario), c.rate.unit)} per t {c.per.replace('_', ' ')}"
                                  for c in inputs.variable_costs])

    key, label, unit, formula = "gross_contribution", "Gross contribution", f"{money}/yr", "revenue - variable processing cost"
    if reason := _needs(s, "revenue", "variable_cost"):
        s[key] = _not_calculated(key, label, unit, formula, reason)
    else:
        value, _ = gross_contribution(s["revenue"].value, inputs.currency, s["variable_cost"].value, inputs.currency)
        s[key] = _calculated(key, label, value, unit, formula,
                             [f"revenue = {_fmt(s['revenue'].value, unit)}",
                              f"variable cost = {_fmt(s['variable_cost'].value, unit)}"],
                             ["Gross contribution is negative: variable costs exceed revenue."] if value < 0 else [])

    key, label = "contribution_per_t_feedstock", "Gross contribution per tonne of usable feedstock"
    unit, formula = f"{money}/t usable dry feedstock", "gross contribution / usable feedstock"
    if reason := _needs(s, "gross_contribution"):
        s[key] = _not_calculated(key, label, unit, formula, reason)
    elif s["usable_feedstock"].value == 0:
        s[key] = _not_calculated(key, label, unit, formula, "usable feedstock is zero, so there is nothing to divide by")
    else:
        value = s["gross_contribution"].value / s["usable_feedstock"].value
        s[key] = _calculated(key, label, value, unit, formula,
                             [f"gross contribution = {_fmt(s['gross_contribution'].value, f'{money}/yr')}",
                              f"usable feedstock = {_fmt(s['usable_feedstock'].value, 't/yr')}"])

    return ScenarioResult(scenario=scenario, steps=s)


def _assumption_lines(inputs: PathwayInputs) -> list[AssumptionLine]:
    named = [(label, getattr(inputs, field)) for field, (label, _) in INPUT_RULES.items()]
    named += [(f"variable cost: {c.name} (per t {c.per.replace('_', ' ')})", c.rate) for c in inputs.variable_costs or ()]
    return [
        AssumptionLine(input=label, conservative=inp.conservative, base=inp.base, optimistic=inp.optimistic,
                       unit=inp.unit, held_constant=not inp.varies, basis=inp.basis, evidence_ids=inp.evidence_ids,
                       note=inp.note)
        for label, inp in named if inp is not None
    ]


def analyse(inputs: PathwayInputs) -> ScenarioAnalysis:
    """Conservative, base, and optimistic results, with every assumption and missing input listed."""
    return ScenarioAnalysis(
        pathway_id=inputs.pathway_id,
        product=inputs.product,
        scenarios={s: run_scenario(inputs, s) for s in SCENARIOS},
        assumptions=tuple(_assumption_lines(inputs)),
        missing_inputs=tuple(inputs.missing_inputs()),
    )


# --- From a feedstock profile -------------------------------------------------------------------


def _from_quantity(q: Quantity, higher_is_better: bool, source: str) -> ScenarioInput | None:
    if q.value is None:
        return None
    lo, hi = q.bounds()
    basis: InputBasis = {"measured": "measured", "fictional_assumption": "fictional_assumption"}.get(q.basis, "analyst_assumption")
    ranged = (lo, hi) != (q.value, q.value)
    worse, better = (lo, hi) if higher_is_better else (hi, lo)
    note = f"From feedstock profile {source} ({q.basis.replace('_', ' ')})."
    if ranged:
        note += f" Conservative and optimistic use the {'low and high' if higher_is_better else 'high and low'} ends of its range."
    return ScenarioInput(base=q.value, conservative=worse if ranged else None, optimistic=better if ranged else None,
                         unit=q.unit, basis=basis, note=note)


def feedstock_inputs(feedstock: FeedstockProfile) -> dict[str, ScenarioInput | None]:
    """Wet mass and moisture from a feedstock profile, ready for PathwayInputs. Ranges become scenarios: more wet
    mass and less moisture are the better ends."""
    return {
        "wet_mass": _from_quantity(feedstock.annual_wet_quantity, True, feedstock.id),
        "moisture": _from_quantity(feedstock.moisture_pct, False, feedstock.id),
    }
