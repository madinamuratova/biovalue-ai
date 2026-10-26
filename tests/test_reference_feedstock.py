"""The literature-based reference stream (data/reference_feedstock.json): every figure with a value cites a published
source, unpublished figures stay blank, edits in the dashboard lose their citation, and the evaluation still runs on
the fictional demo. No model is involved."""

import copy

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend import data
from backend.agents import deterministic
from backend.feedstock import FeedstockProfile
from backend.inputs import build_project
from backend.main import app
from evals.scenario_inputs import build_scenario_project, load_scenarios

REF = data.project(data.REFERENCE_PROJECT_FILE)


def raw_reference() -> dict:
    return data.raw("reference_feedstock.json")


def test_reference_project_loads_with_literature_status():
    f = REF.feedstock
    assert f.data_status == "literature_reference"
    assert "literature" in f.disclaimer.lower() and "not a measured profile" in f.disclaimer
    assert REF.economic_assumptions == {}  # no published availability, yield, price, or cost


def test_every_figure_with_a_value_cites_a_source_with_quotes():
    f = REF.feedstock
    keys = {s.key for s in f.sources}
    for path, q in f.quantities():
        if q.value is None or q.basis == "calculated":
            continue
        assert q.basis == "literature", path
        assert q.source in keys, path
    for s in f.sources:
        assert s.url.startswith("https://") and s.quotes and s.verified_on


def test_unpublished_figures_stay_blank():
    assert sorted(REF.feedstock.missing_fields()) == ["composition.carbohydrates_pct", "composition.other.sodium_pct",
                                                      "composition.phenolic_oh_mmol_per_g"]


def test_dry_matter_follows_published_capacity_and_moisture():
    assert REF.feedstock.dry_matter_t_per_year == pytest.approx(25_000 * 0.65)


def test_quoted_figures_appear_in_the_quotes():
    """The key numbers are taken from the quoted passages, not typed in separately."""
    quotes = {s.key: " ".join(s.quotes) for s in REF.feedstock.sources}
    c = REF.feedstock.composition
    assert "25,000 MT per year" in quotes["valmet2015"] and "about 65%" in quotes["valmet2015"]
    assert f"{c.lignin_pct.value} wt %" in quotes["yan2018"]
    assert f"({c.ash_pct.value} wt %)" in quotes["yan2018"] and "S 0.8 ± 0.2" in quotes["yan2018"]
    assert "Mw 6000 ± 283" in quotes["hararak2023"] and "1.20 ± 0.02%" in quotes["hararak2023"]
    assert "2.8% in LF" in quotes["wu2024"]


def test_carbon_fiber_compatibility_is_checked_against_published_values():
    a = deterministic.compatibility(REF, "carbon_materials", data.scoring_config())
    assert a.score == 1 and any(i.startswith("ash_pct = 1.65") for i in a.inputs)


def test_literature_figure_without_a_source_is_rejected():
    d = raw_reference()
    d["composition"]["ash_pct"]["source"] = ""
    with pytest.raises(ValidationError, match="needs a source"):
        FeedstockProfile.model_validate(d)


def test_unknown_source_key_is_rejected():
    d = raw_reference()
    d["composition"]["ash_pct"]["source"] = "nobody2099"
    with pytest.raises(ValidationError, match="not in the profile's sources"):
        FeedstockProfile.model_validate(d)


def test_literature_profile_cannot_hold_fictional_figures_or_a_vague_disclaimer():
    d = raw_reference()
    d["composition"]["sulfur_pct"]["basis"] = "fictional_assumption"
    with pytest.raises(ValidationError, match="can't contain fictional or measured"):
        FeedstockProfile.model_validate(d)
    d = raw_reference()
    d["disclaimer"] = "Reference values."
    with pytest.raises(ValidationError, match="must say it is literature-based"):
        FeedstockProfile.model_validate(d)


def test_unedited_figures_keep_their_citation_in_the_dashboard_path():
    f = build_project({"feedstock": raw_reference(), "economic_assumptions": {}}).feedstock
    q = dict(f.quantities())
    assert (q["composition.lignin_pct"].basis, q["composition.lignin_pct"].source) == ("literature", "yan2018")
    assert "Some figures were edited" not in f.disclaimer


def test_edited_figure_becomes_an_estimate_and_sources_come_from_the_stored_file():
    d = raw_reference()
    d["composition"]["ash_pct"].update(value=0.5, low=0.5)
    d["sources"] = [{"key": "fake", "citation": "x", "url": "https://example.com", "verified_on": "x", "quotes": ["x"]}]
    f = build_project({"feedstock": d, "economic_assumptions": {}}).feedstock
    ash = dict(f.quantities())["composition.ash_pct"]
    assert (ash.basis, ash.source) == ("estimated", "")
    assert [s.key for s in f.sources] == [s.key for s in REF.feedstock.sources]
    assert "Some figures were edited in the dashboard" in f.disclaimer


def test_other_data_sources_drop_citations():
    d = copy.deepcopy(raw_reference())
    d["data_status"] = "mixed"
    f = build_project({"feedstock": d, "economic_assumptions": {}}).feedstock
    assert f.sources == () and all(q.source == "" for _, q in f.quantities())


def test_normalized_profile_carries_the_citation():
    n = deterministic.normalized_feedstock(REF)
    assert n["composition"]["lignin_pct"]["source"] == "yan2018"


def test_api_offers_both_presets():
    presets = TestClient(app).get("/api/project").json()["presets"]
    assert [p["id"] for p in presets] == ["fictional_demo", "literature_reference"]
    assert presets[1]["feedstock"]["data_status"] == "literature_reference"


def test_evaluation_still_runs_on_the_fictional_demo():
    for s in load_scenarios()["scenarios"]:
        if s["kind"] == "live":
            project, _ = build_scenario_project(s)
            assert project.feedstock.id == "demo_pinecrest_kraft_lignin", s["id"]
