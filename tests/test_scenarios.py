"""Deterministic tier for the evaluation scenarios: every scenario builds a valid project, and every hand-calculated
expectation in evals/scenarios.json matches the calculation and scoring engine. No model is involved, so a failure
here means either the expectation or the code is wrong; neither is ever adjusted silently."""

import pytest

from backend import calc, data, scoring
from backend.agents import deterministic
from evals.scenario_inputs import build_scenario_project, load_scenarios

SCENARIOS = [s for s in load_scenarios()["scenarios"] if s["kind"] == "live"]
STEPS = ("dry_mass", "usable_feedstock", "product_output", "revenue", "gross_contribution", "contribution_per_t_feedstock")


def values(project, pid, key):
    a = calc.analyse(project.pathway_inputs(pid))
    steps = [a.scenarios[s].steps[key] for s in calc.SCENARIOS]
    return None if steps[1].status != "calculated" else [st.value for st in steps]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s["id"])
def test_scenario_builds_a_valid_project(scenario):
    project, _ = build_scenario_project(scenario)
    assert project.pathway_ids == ("phenolic_resins", "polyurethanes", "carbon_materials")


@pytest.mark.parametrize("scenario", [s for s in SCENARIOS if "calculations" in s["expected"]], ids=lambda s: s["id"])
def test_expected_calculations_match_the_engine(scenario):
    project, _ = build_scenario_project(scenario)
    for key, expected in scenario["expected"]["calculations"].items():
        for pid in project.pathway_ids:
            got = values(project, pid, key)
            if expected is None:
                assert got is None, (pid, key)
            else:
                assert got == pytest.approx(expected, abs=0.5), (pid, key)


@pytest.mark.parametrize("scenario", [s for s in SCENARIOS if "calculations_pathway" in s["expected"]], ids=lambda s: s["id"])
def test_expected_pathway_calculations_match_the_engine(scenario):
    project, _ = build_scenario_project(scenario)
    for pid, steps in scenario["expected"]["calculations_pathway"].items():
        for key, expected in steps.items():
            assert values(project, pid, key) == pytest.approx(expected, abs=0.5), (pid, key)


@pytest.mark.parametrize("scenario", [s for s in SCENARIOS if "missing_fields" in s["expected"]], ids=lambda s: s["id"])
def test_expected_missing_fields_match_the_profile(scenario):
    project, _ = build_scenario_project(scenario)
    assert sorted(project.feedstock.missing_fields()) == sorted(scenario["expected"]["missing_fields"])


@pytest.mark.parametrize("scenario", [s for s in SCENARIOS if "compatibility_score" in s["expected"]], ids=lambda s: s["id"])
def test_expected_compatibility_matches_the_rule(scenario):
    project, _ = build_scenario_project(scenario)
    config = data.scoring_config()
    for pid, expected in scenario["expected"]["compatibility_score"].items():
        assert deterministic.compatibility(project, pid, config).score == expected, pid


@pytest.mark.parametrize("scenario", [s for s in SCENARIOS if "compatibility_largest_gap_pct" in s["expected"]], ids=lambda s: s["id"])
def test_expected_largest_gap(scenario):
    project, _ = build_scenario_project(scenario)
    for pid, gap in scenario["expected"]["compatibility_largest_gap_pct"].items():
        a = deterministic.compatibility(project, pid, data.scoring_config())
        assert f"Largest relative gap is {gap}%" in a.rationale


@pytest.mark.parametrize("scenario", [s for s in SCENARIOS if "economics_score" in s["expected"]], ids=lambda s: s["id"])
def test_expected_economics_score(scenario):
    project, _ = build_scenario_project(scenario)
    for pid, expected in scenario["expected"]["economics_score"].items():
        a = scoring.assess_indicative_economics(calc.analyse(project.pathway_inputs(pid)), data.scoring_config())
        assert a.score == expected
