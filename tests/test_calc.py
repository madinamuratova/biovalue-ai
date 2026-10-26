"""The calculation chain in backend/calc.py, against numbers worked out by hand.

Worked example (base scenario):
  dry mass            40,000 t/yr wet x (1 - 0.35)          = 26,000 t/yr
  usable feedstock    26,000 x 50%                          = 13,000 t/yr
  product output      13,000 x 0.9 t/t                      = 11,700 t/yr
  revenue             11,700 t x 800 USD/t                  = 9,360,000 USD/yr
  variable cost       11,700 t x 120 USD/t product          = 1,404,000
                    + 13,000 t x  30 USD/t usable feedstock =   390,000   -> 1,794,000 USD/yr
  gross contribution  9,360,000 - 1,794,000                 = 7,566,000 USD/yr
  per tonne           7,566,000 / 13,000                    = 582 USD/t usable dry feedstock
"""

import pytest
from pydantic import ValidationError

from backend import calc
from backend.calc import CostItem, PathwayInputs, ScenarioInput
from backend.units import UnitError
from tests.conftest import make_feedstock, q


def inp(base, unit, conservative=None, optimistic=None, basis="analyst_assumption", **kw) -> ScenarioInput:
    note = kw.pop("note", "test assumption")
    return ScenarioInput(base=base, conservative=conservative, optimistic=optimistic, unit=unit, basis=basis,
                         note=note, **kw)


def costs(*items) -> tuple[CostItem, ...]:
    return tuple(CostItem(name=name, rate=rate, per=per) for name, rate, per in items)


CHEMICALS = ("chemicals", inp(120, "USD/t"), "product")
DRYING = ("drying", inp(30, "USD/t"), "usable_feedstock")


def make_inputs(**changes) -> PathwayInputs:
    fields = dict(
        pathway_id="toy_pathway", product="toy product",
        wet_mass=inp(40_000, "t/yr"), moisture=inp(35, "%"), availability=inp(50, "%"),
        product_yield=inp(0.9, "t/t"), price=inp(800, "USD/t"), variable_costs=costs(CHEMICALS, DRYING),
    )
    fields.update(changes)
    return PathwayInputs(**fields)


def steps(inputs: PathwayInputs, scenario="base") -> dict:
    return calc.run_scenario(inputs, scenario).steps


def values(inputs: PathwayInputs, scenario="base") -> dict:
    return {k: s.value for k, s in steps(inputs, scenario).items()}


# --- Arithmetic, one function at a time ----------------------------------------------------------


def test_dry_mass():
    assert calc.dry_mass(40_000, "t/yr", 35, "%") == pytest.approx(26_000)
    assert calc.dry_mass(40, "kt/yr", 0.35, "fraction") == pytest.approx(26_000)


@pytest.mark.parametrize("moisture, expected", [(0, 40_000), (100, 0)])
def test_dry_mass_at_moisture_boundaries(moisture, expected):
    assert calc.dry_mass(40_000, "t/yr", moisture, "%") == pytest.approx(expected)


def test_dry_mass_of_zero_wet_mass_is_zero():
    assert calc.dry_mass(0, "t/yr", 35, "%") == 0


def test_usable_feedstock():
    assert calc.usable_feedstock(26_000, 50, "%") == pytest.approx(13_000)
    assert calc.usable_feedstock(26_000, 100, "%") == pytest.approx(26_000)
    assert calc.usable_feedstock(26_000, 0, "fraction") == 0


def test_usable_feedstock_rejects_a_fraction_above_one():
    with pytest.raises(ValueError, match="between 0 and 100%"):
        calc.usable_feedstock(26_000, 120, "%")


def test_product_output():
    assert calc.product_output(13_000, 0.9, "t/t") == pytest.approx(11_700)
    assert calc.product_output(13_000, 90, "%") == pytest.approx(11_700)
    assert calc.product_output(13_000, 1, "t/t") == pytest.approx(13_000)
    assert calc.product_output(13_000, 0, "t/t") == 0


def test_revenue_converts_price_units():
    assert calc.revenue(11_700, 800, "USD/t") == (pytest.approx(9_360_000), "USD")
    assert calc.revenue(11_700, 0.8, "USD/kg") == (pytest.approx(9_360_000), "USD")


def test_variable_cost_per_product_and_per_feedstock():
    total, currency = calc.variable_cost(11_700, 13_000, [("chemicals", 120, "USD/t", "product"),
                                                          ("drying", 30, "USD/t", "usable_feedstock")])
    assert (total, currency) == (pytest.approx(1_794_000), "USD")


def test_variable_cost_needs_items_and_matching_currencies():
    with pytest.raises(ValueError, match="at least one cost item"):
        calc.variable_cost(11_700, 13_000, [])
    with pytest.raises(UnitError, match="different currencies"):
        calc.variable_cost(11_700, 13_000, [("a", 1, "USD/t", "product"), ("b", 1, "EUR/t", "product")])
    with pytest.raises(ValueError, match="isn't available"):
        calc.variable_cost(None, 13_000, [("chemicals", 120, "USD/t", "product")])


def test_gross_contribution():
    assert calc.gross_contribution(9_360_000, "USD", 1_794_000, "USD") == (7_566_000, "USD")
    assert calc.gross_contribution(100, "USD", 150, "USD") == (-50, "USD")
    with pytest.raises(UnitError, match="different|EUR"):
        calc.gross_contribution(100, "USD", 50, "EUR")


# --- The full chain ---------------------------------------------------------------------------------


def test_worked_example_base_scenario():
    v = values(make_inputs())
    assert v["dry_mass"] == pytest.approx(26_000)
    assert v["usable_feedstock"] == pytest.approx(13_000)
    assert v["product_output"] == pytest.approx(11_700)
    assert v["revenue"] == pytest.approx(9_360_000)
    assert v["variable_cost"] == pytest.approx(1_794_000)
    assert v["gross_contribution"] == pytest.approx(7_566_000)
    assert v["contribution_per_t_feedstock"] == pytest.approx(582)


def test_every_step_keeps_its_unit():
    units = {k: s.unit for k, s in steps(make_inputs()).items()}
    assert units == {
        "dry_mass": "t/yr dry",
        "usable_feedstock": "t/yr usable dry feedstock",
        "product_output": "t/yr product",
        "revenue": "USD/yr",
        "variable_cost": "USD/yr",
        "gross_contribution": "USD/yr",
        "contribution_per_t_feedstock": "USD/t usable dry feedstock",
    }


def test_every_step_shows_its_formula_and_inputs():
    for step in steps(make_inputs()).values():
        assert step.status == "calculated"
        assert step.formula and step.inputs
    assert steps(make_inputs())["dry_mass"].inputs == ("wet mass = 40,000 t/yr", "moisture = 35 %")


def test_price_in_usd_per_kg_gives_the_same_answer():
    assert values(make_inputs(price=inp(0.8, "USD/kg")))["revenue"] == pytest.approx(9_360_000)


def test_no_profitability_metrics_are_calculated():
    analysis = calc.analyse(make_inputs())
    keys = set(analysis.scenarios["base"].steps)
    assert not keys & {"gross_margin", "npv", "irr", "profit", "payback"}
    assert "NPV" in analysis.not_calculated_metrics and "IRR" in analysis.not_calculated_metrics


# --- Scenarios ---------------------------------------------------------------------------------------


def test_scenarios_use_their_own_values():
    inputs = make_inputs(price=inp(800, "USD/t", conservative=600, optimistic=1000),
                         availability=inp(50, "%", conservative=40, optimistic=60))
    a = calc.analyse(inputs)
    get = lambda s, k: a.scenarios[s].steps[k].value  # noqa: E731
    assert get("conservative", "usable_feedstock") == pytest.approx(10_400)
    assert get("optimistic", "usable_feedstock") == pytest.approx(15_600)
    # conservative: 10,400 x 0.9 = 9,360 t product x 600 = 5,616,000 revenue
    assert get("conservative", "revenue") == pytest.approx(5_616_000)
    # optimistic: 15,600 x 0.9 = 14,040 t x 1,000 = 14,040,000 revenue
    assert get("optimistic", "revenue") == pytest.approx(14_040_000)
    assert get("conservative", "gross_contribution") < get("base", "gross_contribution") < get("optimistic", "gross_contribution")


def test_inputs_without_a_range_are_held_constant_and_say_so():
    a = calc.analyse(make_inputs(price=inp(800, "USD/t", conservative=600, optimistic=1000)))
    lines = {line.input: line for line in a.assumptions}
    assert lines["product price"].held_constant is False
    assert lines["product yield"].held_constant is True
    assert a.scenarios["conservative"].steps["product_output"].value == a.scenarios["base"].steps["product_output"].value


def test_assumptions_list_every_input_with_basis_and_evidence():
    a = calc.analyse(make_inputs(price=inp(800, "USD/t", basis="evidence", evidence_ids=("EV-PF-01",))))
    lines = {line.input: line for line in a.assumptions}
    assert set(lines) == {"wet feedstock mass", "moisture", "availability fraction", "product yield", "product price",
                          "variable cost: chemicals (per t product)", "variable cost: drying (per t usable feedstock)"}
    assert lines["product price"].basis == "evidence" and lines["product price"].evidence_ids == ("EV-PF-01",)
    assert lines["moisture"].unit == "%" and lines["moisture"].note == "test assumption"


@pytest.mark.parametrize("field, value", [
    ("price", inp(800, "USD/t", conservative=1000, optimistic=600)),  # higher price is better
    ("moisture", inp(35, "%", conservative=30, optimistic=40)),  # lower moisture is better
    ("availability", inp(50, "%", conservative=60, optimistic=40)),
])
def test_swapped_scenarios_are_rejected(field, value):
    with pytest.raises(ValidationError, match="worse to better"):
        make_inputs(**{field: value})


def test_swapped_cost_scenarios_are_rejected():
    with pytest.raises(ValidationError, match="worse to better"):
        make_inputs(variable_costs=costs(("chemicals", inp(120, "USD/t", conservative=100, optimistic=140), "product")))


# --- Missing data: never treated as zero ------------------------------------------------------------


def test_missing_availability_stops_the_chain_after_dry_mass():
    s = steps(make_inputs(availability=None))
    assert s["dry_mass"].status == "calculated"
    for key in ("usable_feedstock", "product_output", "revenue", "variable_cost", "gross_contribution",
                "contribution_per_t_feedstock"):
        assert s[key].status == "not_calculated" and s[key].value is None
    assert s["usable_feedstock"].reason == "Not calculated: availability fraction not supplied (no default is assumed)."
    assert "usable feedstock" in s["product_output"].reason


def test_missing_price_stops_revenue_but_not_costs():
    s = steps(make_inputs(price=None))
    assert s["product_output"].status == "calculated"
    assert s["variable_cost"].status == "calculated"
    assert s["revenue"].value is None and s["revenue"].reason == "Not calculated: product price not supplied."
    assert s["gross_contribution"].status == "not_calculated"
    assert s["gross_contribution"].unit == "USD/yr"  # the currency is still known from the costs


def test_missing_costs_stop_contribution_but_not_revenue():
    s = steps(make_inputs(variable_costs=None))
    assert s["revenue"].value == pytest.approx(9_360_000)
    assert s["variable_cost"].status == "not_calculated"
    assert "no default is assumed" in s["variable_cost"].reason
    assert s["gross_contribution"].value is None


def test_missing_wet_mass_and_moisture_are_both_named():
    s = steps(make_inputs(wet_mass=None, moisture=None))
    assert s["dry_mass"].reason == "Not calculated: wet feedstock mass and moisture not supplied."


def test_missing_inputs_are_listed():
    inputs = make_inputs(product_yield=None, price=None)
    assert calc.analyse(inputs).missing_inputs == ("product yield", "product price")


def test_currency_unknown_when_no_money_inputs():
    s = steps(make_inputs(price=None, variable_costs=None))
    assert s["revenue"].unit == "(currency unknown)/yr"


def test_empty_cost_list_is_rejected():
    with pytest.raises(ValidationError):
        make_inputs(variable_costs=())


# --- Zero values ------------------------------------------------------------------------------------


def test_zero_wet_mass_flows_through_as_zero_with_warnings():
    s = steps(make_inputs(wet_mass=inp(0, "t/yr")))
    assert s["dry_mass"].value == 0 and s["dry_mass"].warnings
    assert s["revenue"].value == 0
    assert s["contribution_per_t_feedstock"].status == "not_calculated"
    assert "nothing to divide by" in s["contribution_per_t_feedstock"].reason


def test_zero_availability_gives_zero_usable_feedstock():
    s = steps(make_inputs(availability=inp(0, "%")))
    assert s["usable_feedstock"].value == 0 and s["usable_feedstock"].warnings == ("Usable feedstock is zero.",)


def test_zero_price_gives_zero_revenue_and_negative_contribution():
    s = steps(make_inputs(price=inp(0, "USD/t")))
    assert s["revenue"].value == 0 and "Price is zero" in s["revenue"].warnings[0]
    assert s["gross_contribution"].value == pytest.approx(-1_794_000)
    assert "negative" in s["gross_contribution"].warnings[0]


def test_explicit_zero_cost_is_allowed():
    s = steps(make_inputs(variable_costs=costs(("none", inp(0, "USD/t", note="no variable cost"), "product"))))
    assert s["gross_contribution"].value == pytest.approx(9_360_000)


def test_yield_above_one_is_allowed_with_a_warning():
    s = steps(make_inputs(product_yield=inp(1.4, "t/t")))
    assert s["product_output"].value == pytest.approx(18_200)
    assert "added reagents" in s["product_output"].warnings[0]


# --- Invalid inputs ---------------------------------------------------------------------------------


@pytest.mark.parametrize("field, value, message", [
    ("wet_mass", inp(40_000, "lb/yr"), "not a yearly mass unit"),
    ("moisture", inp(35, "% dry basis"), "wet basis"),
    ("availability", inp(50, "percent"), "not a share unit"),
    ("product_yield", inp(0.9, "kg/kg"), "not a yield unit"),
    ("price", inp(800, "$/t"), "not a money-per-mass unit"),
    ("availability", inp(150, "%"), "between 0 and 100%"),
    ("wet_mass", inp(-5, "t/yr"), "can't be negative"),
])
def test_invalid_inputs_are_rejected(field, value, message):
    with pytest.raises(ValidationError, match=message):
        make_inputs(**{field: value})


def test_price_and_costs_must_share_a_currency():
    with pytest.raises(ValidationError, match="different currencies"):
        make_inputs(price=inp(700, "EUR/t"))


def test_scenario_input_rules():
    with pytest.raises(ValidationError, match="both conservative and optimistic"):
        ScenarioInput(base=1, conservative=0.5, unit="t/t", basis="analyst_assumption", note="n")
    with pytest.raises(ValidationError, match="needs at least one evidence id"):
        ScenarioInput(base=1, unit="t/t", basis="evidence")
    with pytest.raises(ValidationError, match="needs a note"):
        ScenarioInput(base=1, unit="t/t", basis="fictional_assumption")
    with pytest.raises(ValidationError, match="finite number"):
        ScenarioInput(base=float("nan"), unit="t/t", basis="measured")


# --- From a feedstock profile, and determinism --------------------------------------------------------


def test_feedstock_ranges_become_scenarios():
    f = make_feedstock(annual_wet_quantity=q(12_500, "t/yr", low=11_000, high=13_000),
                       moisture_pct=q(20, "% of wet mass", low=15, high=25))
    got = calc.feedstock_inputs(f)
    wet, moisture = got["wet_mass"], got["moisture"]
    assert (wet.conservative, wet.base, wet.optimistic) == (11_000, 12_500, 13_000)
    assert (moisture.conservative, moisture.base, moisture.optimistic) == (25, 20, 15)  # wetter is worse
    assert wet.basis == "fictional_assumption" and "toy_feedstock" in wet.note
    a = calc.analyse(make_inputs(**got))
    assert a.scenarios["base"].steps["dry_mass"].value == pytest.approx(10_000)
    assert a.scenarios["conservative"].steps["dry_mass"].value == pytest.approx(11_000 * 0.75)


def test_feedstock_without_a_range_is_held_constant():
    got = calc.feedstock_inputs(make_feedstock())
    assert got["wet_mass"].varies is False and got["moisture"].varies is False


def test_analysis_is_deterministic():
    assert calc.analyse(make_inputs()) == calc.analyse(make_inputs())
