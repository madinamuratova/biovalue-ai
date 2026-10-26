"""The real demo project in data/: it loads, it is labelled honestly, and it works with the calculations and scoring."""

import pytest

from backend import data, scoring
from backend.calc import PathwayInputs, analyse, feedstock_inputs


@pytest.fixture(scope="module")
def project():
    return data.project()


def test_demo_project_loads(project):
    assert project.id == "demo"
    assert project.pathway_ids == ("phenolic_resins", "polyurethanes", "carbon_materials")


def test_demo_feedstock_is_clearly_fictional(project):
    f = project.feedstock
    assert f.data_status == "fictional_demo"
    assert "fictional" in f.disclaimer.lower() and "not measurements" in f.disclaimer.lower()
    assert {q.basis for _, q in f.quantities()} <= {"fictional_assumption", "calculated"}


def test_demo_feedstock_uses_every_part_of_the_schema(project):
    f = project.feedstock
    assert f.dry_matter_t_per_year == 26_000
    assert f.composition.lignin_pct.method
    assert f.annual_wet_quantity.low is not None and f.variability.drivers
    assert f.current_use.route == "internal_fuel"
    statuses = {a.status for a in f.infrastructure}
    assert {"operating", "not_available"} <= statuses
    assert f.geographic_market.target_markets
    assert f.missing_fields() == ["composition.mw_g_per_mol", "composition.phenolic_oh_mmol_per_g",
                                  "composition.other.sodium_pct"]
    assert {g.issue for g in f.data_gaps} == {"fictional", "missing", "method_unclear", "uncertain"}


def test_every_pathway_has_high_quality_evidence(project):
    for pid in project.pathway_ids:
        records = project.evidence.records_for(pid)
        assert len(records) >= 3, pid
        assert any(r.quality == "high" for r in records), pid


def test_every_record_is_verified_and_quotes_its_support(project):
    for r in project.evidence.records:
        assert r.url.startswith("https://") and r.url_verified_on, r.id
        assert r.quality != "unverified", r.id
        assert r.limitations, r.id
        for item in (*r.claims, *r.technical_requirements):
            assert item.status == "supported" and item.support.strip(), r.id


def test_numeric_thresholds_appear_only_where_a_source_states_them(project):
    numeric = [(pid, rid, req.property, req.min, req.max, req.applies_to)
               for pid in project.pathway_ids for rid, req in project.evidence.requirements_for(pid)
               if req.min is not None or req.max is not None]
    assert numeric == [
        ("carbon_materials", "EV-CM-01", "lignin_pct", 99, None, "carbon fiber precursor"),
        ("carbon_materials", "EV-CM-01", "ash_pct", None, 0.1, "carbon fiber precursor"),
    ]


def test_demo_feedstock_compatibility(project, config):
    f = project.feedstock
    resins = scoring.assess_feedstock_compatibility(f, project.evidence.requirements_for("phenolic_resins"), config)
    assert resins.score is None  # no numeric requirement on file: not assessed, rather than scored low
    carbon = scoring.assess_feedstock_compatibility(f, project.evidence.requirements_for("carbon_materials"), config)
    assert carbon.score == 1  # ash 1.0% against below 0.1% for carbon fiber precursors is a 900% gap
    assert "carbon fiber precursor" in carbon.rationale


def test_demo_economics_stop_at_the_missing_inputs(project, config):
    inputs = PathwayInputs(pathway_id="phenolic_resins", product="lignin for PF resins",
                           **feedstock_inputs(project.feedstock))
    analysis = analyse(inputs)
    assert analysis.scenarios["base"].steps["dry_mass"].value == pytest.approx(26_000)
    assert analysis.missing_inputs == ("availability fraction", "product yield", "product price", "variable costs")
    assert scoring.assess_indicative_economics(analysis, config).score is None


def test_demo_uncertainty_flags(project):
    flags = project.uncertainty_flags()
    assert flags[0].startswith("Feedstock data is fictional demo")
    assert any("composition.mw_g_per_mol" in f for f in flags)
    assert not any("no verified evidence" in f for f in flags)
