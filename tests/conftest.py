"""Toy inputs with round numbers, so expected results can be worked out by hand in the tests.

These are not real lignin figures. The real demo data is checked separately in test_demo_project.py.
The scoring tests use the real scoring config in data/scoring_config.json, so they also check its weights.
"""

import pytest

from backend.feedstock import (
    DRY_PCT, PROPERTY_UNITS, Composition, CurrentUse, DataGap, FeedstockProfile, GeographicMarket, ProcessingAsset,
    Quantity, Variability,
)
from backend import data
from backend.scoring import ScoringConfig

TOY_PROPS = {"lignin_pct": 95, "ash_pct": 1.0, "sulfur_pct": 2.0, "carbohydrates_pct": 1.5,
             "mw_g_per_mol": 5000, "phenolic_oh_mmol_per_g": 4.0}


def q(value, unit, basis="fictional_assumption", **kw) -> Quantity:
    return Quantity(value=value, unit=unit, basis=basis, **kw)


def missing(field: str) -> DataGap:
    return DataGap(field=field, issue="missing", severity="medium", impact="toy impact", next_step="toy next step")


def make_composition(**props) -> Composition:
    values = {**TOY_PROPS, **props}
    fields = {name: q(values[name], unit) for name, unit in PROPERTY_UNITS.items()}
    fields["lignin_pct"] = q(values["lignin_pct"], DRY_PCT, method="toy method")
    return Composition(**fields)


def make_feedstock(has_plant: bool = False, props: dict | None = None, **changes) -> FeedstockProfile:
    """10,000 dry t/yr (12,500 t/yr wet at 20% moisture). No lignin plant unless has_plant=True."""
    plant = (ProcessingAsset(kind="lignin_precipitation", name="Toy precipitation plant", status="operating"),)
    fields = dict(
        id="toy_feedstock",
        name="Toy feedstock",
        data_status="fictional_demo",
        disclaimer="Fictional toy feedstock for tests.",
        feedstock_type="toy lignin cake",
        wood_type="softwood",
        annual_wet_quantity=q(12_500, "t/yr"),
        moisture_pct=q(20, "% of wet mass"),
        dry_matter=q(10_000, "t/yr", basis="calculated"),
        composition=make_composition(**(props or {})),
        variability=Variability(summary="toy", drivers=()),
        current_use=CurrentUse(route="recovery_boiler_fuel", description="toy"),
        infrastructure=plant if has_plant else (),
        geographic_market=GeographicMarket(mill_location="nowhere", target_markets=("toy market",), logistics="toy"),
    )
    fields.update(changes)
    return FeedstockProfile(**fields)


@pytest.fixture
def feedstock() -> FeedstockProfile:
    return make_feedstock()


@pytest.fixture
def config() -> ScoringConfig:
    return data.scoring_config()
