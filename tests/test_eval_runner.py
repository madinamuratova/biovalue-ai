"""Deterministic tests for the evaluation runner's own arithmetic (evals/run_eval.py). No model is involved."""

import json

from evals import run_eval


def test_pairwise_agreement_identical_and_reversed():
    order = ["a", "b", "c"]
    assert run_eval.pairwise_agreement(order, order) == 1.0
    assert run_eval.pairwise_agreement(order, list(reversed(order))) == 0.0


def test_pairwise_agreement_counts_pairs():
    # pairs (a,b) (a,c) (b,c); ours = b, a, c keeps (a,c) and (b,c) the same way round: 2 of 3
    assert run_eval.pairwise_agreement(["a", "b", "c"], ["b", "a", "c"]) == round(2 / 3, 3)


def test_pairwise_agreement_needs_two_common_pathways():
    assert run_eval.pairwise_agreement(["a"], ["a", "b"]) is None


def test_expert_agreement_is_not_measured_without_a_review(tmp_path, monkeypatch):
    monkeypatch.setattr(run_eval, "EXPERT_FILE", tmp_path / "expert_rankings.json")
    result = run_eval.expert_agreement("S01", {"ranked": [["carbon_materials", 2.1]], "insufficient_data": []})
    assert result["status"] == "not measured"


def test_expert_agreement_is_measured_when_recorded(tmp_path, monkeypatch):
    path = tmp_path / "expert_rankings.json"
    path.write_text(json.dumps({"rankings": {"S01": {"reviewer": "test", "order": ["polyurethanes", "carbon_materials",
                                                                                   "phenolic_resins"]}}}))
    monkeypatch.setattr(run_eval, "EXPERT_FILE", path)
    ranking = {"ranked": [["carbon_materials", 2.1]], "insufficient_data": [["phenolic_resins", 3.0], ["polyurethanes", 2.5]]}
    result = run_eval.expert_agreement("S01", ranking)
    assert result["status"] == "measured" and result["top_choice_agrees"] is False
    assert result["pairwise_agreement"] == round(1 / 3, 3)


def test_template_is_unfilled():
    template = json.loads((run_eval.EXPERT_FILE.parent / "expert_rankings_template.json").read_text())
    assert all(not r["order"] and not r["reviewer"] for r in template["rankings"].values())


def test_scenario_expectations_have_not_been_edited():
    from evals.scenario_inputs import load_scenarios
    scenarios = load_scenarios()
    assert scenarios["expectation_changes"] == []  # any change must be logged here with a reason
    assert len(scenarios["scenarios"]) >= 10
    assert all(s.get("expected_behavior") for s in scenarios["scenarios"])
