"""Evidence references and the number check (backend/agents/refs.py), on the real demo project."""

import re

import pytest

from backend import data
from backend.agents.refs import cited_numbers, numbers_in, record_ids, ref_problems, resolve, unsupported_numbers


@pytest.fixture(scope="module")
def project():
    return data.project()


def test_resolve_claim_requirement_and_feedstock(project):
    claim = resolve(project, "EV-PF-02#1")
    assert (claim.kind, claim.record_id, claim.pathway_id, claim.supported) == ("claim", "EV-PF-02", "phenolic_resins", True)
    assert "80%" in claim.text
    req = resolve(project, "EV-CM-01#R2")
    assert req.kind == "requirement" and "0.1%" in req.text
    fs = resolve(project, "feedstock:composition.ash_pct")
    assert fs.kind == "feedstock" and fs.pathway_id is None and '"value": 1.0' in fs.text


@pytest.mark.parametrize("ref, message", [
    ("EV-PF-99#1", "no evidence record EV-PF-99"),
    ("EV-PF-01#9", "has 4 claim(s)"),
    ("EV-PF-01#R5", "has 1 requirement(s)"),
    ("PF-01 claim 2", "is not a reference"),
    ("feedstock:composition.colour", "no such field"),
])
def test_bad_references_are_explained(project, ref, message):
    with pytest.raises(ValueError, match=re.escape(message)):
        resolve(project, ref)


def test_references_must_belong_to_the_pathway(project):
    assert ref_problems(project, ["EV-PF-02#1", "feedstock:moisture_pct"], "phenolic_resins") == []
    assert ref_problems(project, ["EV-PF-02#1"], "polyurethanes") == ["EV-PF-02#1 belongs to pathway phenolic_resins, not polyurethanes"]


def test_record_ids_skip_feedstock_references():
    assert record_ids(["EV-PF-02#1", "EV-PF-02#2", "feedstock:moisture_pct", "EV-PF-01#R1"]) == ("EV-PF-02", "EV-PF-01")


def test_numbers_in_ignores_ids_dates_and_chemistry():
    text = "EV-PF-01#3 says (2026-10-24) H2SO4 and CO2 matter, PF2 too; 1,000 USD and 0.25 and 12 mm"
    assert numbers_in(text) == ["1,000", "0.25", "12"]


@pytest.mark.parametrize("text, ok", [
    ("Phenol is around 1,000 USD per tonne.", True),
    ("Phenol is around 1000 USD per tonne.", True),
    ("Lignin replaces up to 80% of phenol.", True),
    ("Lignin replaces up to 95% of phenol.", False),
])
def test_unsupported_numbers(project, text, ok):
    allowed = cited_numbers(project, ["EV-PF-02#1", "EV-PF-03#3"])
    assert (unsupported_numbers(text, allowed) == []) is ok


def test_rounding_and_fraction_to_percent_are_allowed():
    allowed = {2.375, 0.8, 26000.0}
    assert unsupported_numbers("Attractiveness 2.38 with 80% of the weight on 26,000 t/yr", allowed) == []
    assert unsupported_numbers("Attractiveness 2.5", allowed) == ["2.5"]


def test_feedstock_references_reach_the_feedstock_agent_findings(project):
    from backend.agents.schemas import FeedstockAgentOutput
    findings = FeedstockAgentOutput(
        feedstock_id="demo_pinecrest_kraft_lignin", is_fictional=True, wet_mass_t_per_yr=40000, moisture_fraction=0.35,
        dry_mass_t_per_yr=26000, missing_properties=["composition.mw_g_per_mol"], inconsistencies=[],
        constraints=["No dryer is available, so the cake stays at 35% moisture."], data_quality_notes=[], summary="s")
    with pytest.raises(ValueError, match="no such field in the feedstock record"):
        resolve(project, "feedstock:constraints[0]")  # without the findings: only the record is searched
    r = resolve(project, "feedstock:constraints[0]", findings)
    assert r.kind == "feedstock" and "No dryer" in r.text
    assert resolve(project, "feedstock:composition.ash_pct", findings).text.startswith('{"value": 1.0')  # record first
    assert 35.0 in cited_numbers(project, ["feedstock:constraints[0]"], findings)
    with pytest.raises(ValueError, match="record or the Feedstock Agent's findings"):
        resolve(project, "feedstock:constraints[9]", findings)
