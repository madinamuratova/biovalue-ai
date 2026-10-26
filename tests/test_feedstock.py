"""The feedstock schema: units, the dry-matter balance, data gaps, and the fictional/measured labels."""

import pytest
from pydantic import ValidationError

from backend.feedstock import DRY_PCT, Composition, DataGap, ProcessingAsset, Quantity, _path_exists
from tests.conftest import make_composition, make_feedstock, missing, q


def gap(field: str, issue: str = "uncertain") -> DataGap:
    return DataGap(field=field, issue=issue, severity="low", impact="toy impact", next_step="toy next step")


# --- Quantities and derived figures ----------------------------------------------------------


def test_toy_feedstock_derived_figures():
    f = make_feedstock()
    assert f.dry_matter_t_per_year == 10_000
    assert f.dry_lignin_t_per_year == 9_500
    assert f.property_value("ash_pct") == 1.0
    assert f.missing_fields() == []


def test_only_operating_assets_count():
    assert make_feedstock(has_plant=True).has_operating("lignin_precipitation")
    assert not make_feedstock().has_operating("lignin_precipitation")
    planned = (ProcessingAsset(kind="drying", name="Dryer", status="planned"),)
    assert not make_feedstock(infrastructure=planned).has_operating("drying")


def test_kilotonne_units_are_converted():
    f = make_feedstock(annual_wet_quantity=q(12.5, "kt/yr"), dry_matter=q(10, "kt/yr", basis="calculated"))
    assert f.dry_matter_t_per_year == 10_000


def test_unknown_mass_unit_is_rejected():
    with pytest.raises(ValidationError, match="annual_wet_quantity must be in one of"):
        make_feedstock(annual_wet_quantity=q(12_500, "lb/yr"))


def test_missing_value_cannot_have_a_range():
    with pytest.raises(ValidationError, match="can't have a range"):
        Quantity(value=None, low=1, unit="x", basis="estimated")


def test_range_must_contain_the_value():
    with pytest.raises(ValidationError, match="low <= value <= high"):
        Quantity(value=5, high=4, unit="x", basis="estimated")


# --- Dry-matter balance and moisture -----------------------------------------------------------


def test_dry_matter_must_match_wet_quantity_and_moisture():
    with pytest.raises(ValidationError, match="doesn't match wet quantity"):
        make_feedstock(dry_matter=q(11_000, "t/yr", basis="calculated"))


def test_small_rounding_in_dry_matter_is_accepted():
    assert make_feedstock(dry_matter=q(10_040, "t/yr", basis="calculated")).dry_matter_t_per_year == 10_040


@pytest.mark.parametrize("moisture", [-1, 100, 120])
def test_moisture_must_be_a_real_share(moisture):
    with pytest.raises(ValidationError, match="moisture must be"):
        make_feedstock(moisture_pct=q(moisture, "% of wet mass"))


def test_moisture_is_required():
    with pytest.raises(ValidationError, match="moisture_pct is required"):
        make_feedstock(moisture_pct=q(None, "% of wet mass"), data_gaps=(missing("moisture_pct"),))


# --- Composition -----------------------------------------------------------------------------


def test_lignin_content_needs_its_measurement_basis():
    with pytest.raises(ValidationError, match="measurement basis"):
        Composition(**{**dict(make_composition()), "lignin_pct": q(95, DRY_PCT)})


def test_composition_units_are_fixed():
    with pytest.raises(ValidationError, match="must be in '% of dry matter'"):
        Composition(**{**dict(make_composition()), "ash_pct": q(1.0, "% of wet mass")})


def test_percentages_stay_between_0_and_100():
    with pytest.raises(ValidationError, match="between 0 and 100"):
        make_composition(ash_pct=-1)


def test_composition_cannot_exceed_the_whole():
    with pytest.raises(ValidationError, match="more than the whole"):
        make_composition(lignin_pct=95, ash_pct=5, carbohydrates_pct=3)


# --- Missing data and uncertainty --------------------------------------------------------------


def test_missing_figure_needs_a_data_gap():
    with pytest.raises(ValidationError, match="missing figures need a data gap"):
        make_feedstock(props={"phenolic_oh_mmol_per_g": None})


def test_missing_figure_with_a_data_gap_is_accepted():
    f = make_feedstock(props={"phenolic_oh_mmol_per_g": None}, data_gaps=(missing("composition.phenolic_oh_mmol_per_g"),))
    assert f.missing_fields() == ["composition.phenolic_oh_mmol_per_g"]
    assert f.property_value("phenolic_oh_mmol_per_g") is None


def test_missing_gap_on_a_reported_figure_is_rejected():
    with pytest.raises(ValidationError, match="point at figures that have values"):
        make_feedstock(data_gaps=(missing("composition.ash_pct"),))


def test_uncertainty_gap_can_point_at_a_reported_figure():
    g = gap("composition.sulfur_pct")
    assert make_feedstock(data_gaps=(g,)).data_gaps == (g,)


def test_data_gap_must_point_at_a_real_field():
    with pytest.raises(ValidationError, match="fields that don't exist"):
        make_feedstock(data_gaps=(gap("composition.colour"),))


SODIUM = Composition(**{**dict(make_composition()), "other": {"sodium_pct": q(0.1, DRY_PCT)}})


@pytest.mark.parametrize("path, exists", [
    ("composition.ash_pct", True),
    ("composition.other.sodium_pct", True),
    ("infrastructure[0].name", True),
    ("infrastructure[1]", False),
    ("composition.colour", False),
    ("not a path", False),
])
def test_data_gap_paths_resolve(path, exists):
    assert _path_exists(make_feedstock(has_plant=True, composition=SODIUM), path) is exists


def test_every_figure_has_a_path():
    paths = [p for p, _ in make_feedstock(composition=SODIUM).quantities()]
    assert paths[:3] == ["annual_wet_quantity", "moisture_pct", "dry_matter"]
    assert "composition.lignin_pct" in paths and "composition.other.sodium_pct" in paths


# --- Fictional versus measured -------------------------------------------------------------------


def test_fictional_profile_cannot_claim_measured_data():
    with pytest.raises(ValidationError, match="can't contain measured figures"):
        make_feedstock(moisture_pct=q(20, "% of wet mass", basis="measured"))


def test_fictional_profile_must_say_so():
    with pytest.raises(ValidationError, match="must say it is fictional"):
        make_feedstock(disclaimer="Demo data.")


def test_measured_profile_cannot_contain_fictional_figures():
    with pytest.raises(ValidationError, match="can't contain fictional assumptions"):
        make_feedstock(data_status="measured")
