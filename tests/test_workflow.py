"""The four-agent workflow, run offline with a scripted model (PydanticAI's FunctionModel) in place of the LLM.

The scripted model makes real tool calls through PydanticAI, so these tests exercise the actual agents, tools,
guards, retries, timeouts, and failure handling. They make no API calls. The live run is scripts/run_workflow.py.
"""

import asyncio
import json

import pytest
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from backend import config
from backend.agents import AGENT_ORDER, AGENT_TOOLS
from backend.workflow import run_workflow

PF, PU, CM = "phenolic_resins", "polyurethanes", "carbon_materials"
PATHWAYS = (PF, PU, CM)
WET = {"wet_value": 40000, "wet_unit": "t/yr", "moisture_value": 35, "moisture_unit": "% of wet mass"}

pytestmark = pytest.mark.mock


def scripted(steps) -> FunctionModel:
    """A model that plays back `steps`: each step is a list of (tool, args) calls, or ("final", answer).
    After the last step it repeats it, so a rejected answer is resubmitted unchanged."""

    def respond(messages, info: AgentInfo) -> ModelResponse:
        step = steps[min(sum(isinstance(m, ModelResponse) for m in messages), len(steps) - 1)]
        if isinstance(step, tuple) and step[0] == "final":
            answer = step[1](messages) if callable(step[1]) else step[1]
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, answer)])
        return ModelResponse(parts=[ToolCallPart(name, args) for name, args in step])

    return FunctionModel(respond, model_name="scripted")


def failing(exc_factory, delay: float = 0.0) -> FunctionModel:
    async def respond(messages, info):
        if delay:
            await asyncio.sleep(delay)
        raise exc_factory()

    return FunctionModel(respond, model_name="failing")


def finding(statement, *refs):
    return {"statement": statement, "evidence": list(refs)}


# --- Scripts for a run where every agent behaves --------------------------------------------------------------

FEEDSTOCK_ANSWER = {
    "feedstock_id": "demo_pinecrest_kraft_lignin", "is_fictional": True, "wet_mass_t_per_yr": 40000,
    "moisture_fraction": 0.35, "dry_mass_t_per_yr": 26000,
    "missing_properties": ["composition.mw_g_per_mol", "composition.phenolic_oh_mmol_per_g", "composition.other.sodium_pct"],
    "inconsistencies": [], "constraints": ["No dryer is available, so the lignin leaves the mill as wet cake."],
    "data_quality_notes": ["Every figure is a fictional assumption."], "summary": "A fictional softwood kraft lignin cake.",
}
FEEDSTOCK = [
    [("read_feedstock_profile", {})],
    [("convert_units", {"field": "annual_wet_quantity", "value": 40000, "unit": "t/yr", "kind": "mass_flow"}),
     ("convert_units", {"field": "moisture_pct", "value": 35, "unit": "% of wet mass", "kind": "moisture"}),
     ("calculate_dry_mass", WET), ("validate_feedstock", {})],
    ("final", FEEDSTOCK_ANSWER),
]


def market_pathway(pid, applications, competing, qualification, judgment, customers=()):
    return {"pathway_id": pid, "applications": applications, "target_customers": list(customers),
            "competing_materials": competing, "qualification_requirements": qualification,
            "limitations": ["Some sources are vendor claims."], "missing_information": ["No lignin price is given."],
            "market_evidence": judgment}


MARKET_ANSWER = {"pathways": [
    market_pathway(PF, [finding("UPM states its lignin can replace up to 80% of the phenol in LPF resin.", "EV-PF-02#1")],
                   [finding("Phenol, at around 1,000 USD per tonne.", "EV-PF-03#3")],
                   [finding("Plywood bonded with LPF resin must meet EN 314-2 Bonding Class 3.", "EV-PF-02#2")],
                   {"score": 4, "rationale": "UPM documents an industrially proven LPF resin.", "evidence": ["EV-PF-02#2"]},
                   customers=[finding("Plywood producers.", "EV-PF-02#2")]),
    market_pathway(PU, [finding("Rigid PUR/PIR foam with 30 wt% of the polyol replaced by lignin.", "EV-PU-01#1")],
                   [finding("Petroleum-based polyol.", "EV-PU-01#1")],
                   [finding("ASTM C1029-15 type 1 specifications for rigid insulation foam.", "EV-PU-01#1")],
                   {"score": 2, "rationale": "Evidence is from lab studies; commercialization is limited.", "evidence": ["EV-PU-05#1"]}),
    market_pathway(CM, [finding("Hard carbon for sodium-ion battery anodes.", "EV-CM-04#1")],
                   [finding("PAN-based carbon fiber.", "EV-CM-03#2")],
                   [finding("Qualification with battery makers can take 3 years.", "EV-CM-06#1")],
                   {"score": 3, "rationale": "Pilot-scale activity is documented.", "evidence": ["EV-CM-06#2"]}),
]}
MARKET = [
    [("list_pathways", {})],
    [("search_evidence", {"pathway_id": p}) for p in PATHWAYS],
    [("get_scoring_rubric", {"criterion": "market_evidence"})],
    ("final", MARKET_ANSWER),
]


def commercial_pathway(pid, processing, maturity):
    return {"pathway_id": pid, "processing_requirements": [processing], "technical_maturity": maturity,
            "adoption_barriers": [finding("There is no dryer at the mill.", "feedstock:infrastructure[2]")],
            "missing_inputs": ["product yield", "product price", "variable costs"],
            "assumptions": ["The 50% availability is a fictional assumption."],
            "uncertainties": ["The feedstock data is fictional."],
            "commercialization_feasibility": {"score": 3, "rationale": "Needs a dryer and a partner.",
                                              "evidence": ["feedstock:infrastructure[2]"]}}


COMMERCIAL_ANSWER = {"pathways": [
    commercial_pathway(PF, finding("Kraft lignin needs activation or depolymerization.", "EV-PF-01#R1"),
                       finding("A cited report puts biobased phenolic resins at TRL 8.", "EV-PF-01#3")),
    commercial_pathway(PU, finding("Kraft lignin needs significant treatment, such as oxypropylation.", "EV-PU-04#R1"),
                       finding("The IEA rates polyurethane uses at TRL 6.", "EV-PU-04#1")),
    commercial_pathway(CM, finding("Carbon fiber precursors need ash below 0.1%.", "EV-CM-01#R2"),
                       finding("Precursor fiber production reached TRL 5.", "EV-CM-03#1")),
]}
COMMERCIAL = [
    [call for p in PATHWAYS for call in (("get_pathway_requirements", {"pathway_id": p}),
                                         ("check_feedstock_compatibility", {"pathway_id": p}),
                                         ("run_scenario_analysis", {"pathway_id": p}))],
    [("assess_technical_readiness", {"pathway_id": PF, "trl": 8, "evidence": ["EV-PF-01#3"]}),
     ("assess_technical_readiness", {"pathway_id": PU, "trl": 6, "evidence": ["EV-PU-04#1"]}),
     ("assess_technical_readiness", {"pathway_id": CM, "trl": 5, "evidence": ["EV-CM-03#1"]})],
    [("get_scoring_rubric", {"criterion": "commercialization_feasibility"})],
    ("final", COMMERCIAL_ANSWER),
]


def ranking_returned(messages) -> dict:
    return next(p.content for m in messages if isinstance(m, ModelRequest) for p in m.parts
                if isinstance(p, ToolReturnPart) and p.tool_name == "score_and_rank")


def decision_answer(messages, reverse=False):
    r = ranking_returned(messages)
    order = [(o["pathway_id"], o["rank"]) for o in r["ranked"]] + [(o["pathway_id"], None) for o in r["insufficient_data"]]
    if reverse:
        order = order[::-1]
    step = lambda a, x: {"action": a, "reason": "It is missing.", "addresses": [x]}  # noqa: E731
    return {
        "shortlist": [{"pathway_id": pid, "rank": rank, "main_drivers": ["Feedstock compatibility weighs most."],
                       "what_could_change_it": ["A measured molecular weight."]} for pid, rank in order],
        "validation_steps": [step("Measure molecular weight.", "composition.mw_g_per_mol"),
                             step("Measure phenolic OH.", "composition.phenolic_oh_mmol_per_g"),
                             step("Get a sourced lignin price.", "product price")],
        "ranking_changers": ["A sourced lignin price and yield."], "caveats": ["The feedstock is fictional."],
        "summary": "Only one pathway has enough assessed weight to be ranked.",
    }


DECISION = [[("score_and_rank", {})], ("final", decision_answer)]
SCRIPTS = {"feedstock": FEEDSTOCK, "market": MARKET, "commercialization": COMMERCIAL, "decision": DECISION}


def models(**overrides):
    chosen = {name: overrides.get(name) or scripted(SCRIPTS[name]) for name in AGENT_ORDER}
    return lambda name: chosen[name]


def run(tmp_path=None, **kwargs):
    return asyncio.run(run_workflow(output_dir=tmp_path, **kwargs))


# --- The happy path ------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def complete(tmp_path_factory):
    out = tmp_path_factory.mktemp("output")
    return run(out, model=models()), out


def test_all_four_agents_run_once_in_order(complete):
    result, _ = complete
    assert result.status == "complete"
    assert [(a.agent, a.status, a.attempts) for a in result.execution.agents] == [
        ("feedstock", "ok", 1), ("market", "ok", 1), ("commercialization", "ok", 1), ("decision", "ok", 1)]
    assert result.execution.executed() == list(AGENT_ORDER)


def test_tool_calls_are_tracked_per_agent(complete):
    result, _ = complete
    called = {a.agent: [c.tool for c in a.tool_calls] for a in result.execution.agents}
    # Tools requested in one model response run concurrently, so the trace records them in the order they finish.
    assert called["feedstock"][0] == "read_feedstock_profile"
    assert sorted(called["feedstock"][1:]) == ["calculate_dry_mass", "convert_units", "convert_units", "validate_feedstock"]
    assert called["market"].count("search_evidence") == 3
    assert called["commercialization"].count("run_scenario_analysis") == 3
    assert called["decision"] == ["score_and_rank"]
    assert all(c.status == "ok" for a in result.execution.agents for c in a.tool_calls)
    assert not any(a.guard_events for a in result.execution.agents)


def test_each_agent_only_has_its_own_tools():
    names = {agent: {t.__name__ for t in tools} for agent, tools in AGENT_TOOLS.items()}
    assert "score_and_rank" in names["decision"] and "score_and_rank" not in names["market"]
    assert not any("agent" in tool or "delegate" in tool for tools in names.values() for tool in tools)


def test_deterministic_results_reach_the_final_assessment(complete):
    result, _ = complete
    assert result.feedstock.normalized["dry_mass_t_per_yr"] == pytest.approx(26_000)
    stages = {s.pathway_id: s for s in result.commercialization}
    assert stages[CM].feedstock_compatibility.score == 1  # ash 1.0% vs < 0.1% for carbon fiber precursors
    assert stages[PF].feedstock_compatibility.score is None  # no numeric requirement on file
    assert stages[PF].technical_readiness.score == 5  # TRL 8, confirmed from EV-PF-01#3
    assert stages[PF].indicative_economics.score is None  # no price or yield supplied
    base = stages[PF].scenario_analysis.scenarios["base"].steps
    assert base["usable_feedstock"].value == pytest.approx(13_000)
    assert base["product_output"].status == "not_calculated"


def test_ranking_keeps_missing_evidence_out_of_the_score(complete):
    ranking = complete[0].decision.ranking
    assert [o.pathway_id for o in ranking.ranked] == [CM]
    assert [o.pathway_id for o in ranking.insufficient_data] == [PF, PU]
    cm = ranking.ranked[0]
    # compatibility 1, readiness 3 (TRL 5), market 3, feasibility 3 over 0.80 of the weight = 1.90 / 0.80
    assert cm.attractiveness == pytest.approx(2.38, abs=0.005)
    assert cm.completeness.not_assessed == ("indicative_economics",)


def test_market_stage_lists_sources_and_claims(complete):
    pf = next(s for s in complete[0].market if s.pathway_id == PF)
    assert pf.source_ids == ("EV-PF-02", "EV-PF-03")
    assert pf.supported_claims["EV-PF-02#1"].startswith("UPM states that its lignin can replace up to 80%")


def test_decision_report_follows_the_ranking(complete):
    report = complete[0].decision.report
    assert [(s.pathway_id, s.rank) for s in report.shortlist] == [(CM, 1), (PF, None), (PU, None)]
    assert 3 <= len(report.validation_steps) <= 5


def test_outputs_and_logs_are_saved(complete):
    result, out = complete
    saved = json.loads((out / "runs" / f"{result.run_id}.json").read_text())
    assert saved["status"] == "complete" and saved["run_id"] == result.run_id
    assert json.loads((out / "latest_assessment.json").read_text())["run_id"] == result.run_id
    events = [r["event"] for r in json.loads((out / "audit_trail.json").read_text()) if r["run_id"] == result.run_id]
    assert events == ["run_start"] + ["agent_finished"] * 4 + ["run_end"]
    usage = json.loads((out / "usage_log.json").read_text())[-1]
    assert set(usage["agents"]) == set(AGENT_ORDER)
    assert result.cost.status == "not_calculated"  # no verified price for this model


# --- Guards -------------------------------------------------------------------------------------------------


def with_final(script, answer):
    return [*script[:-1], ("final", answer)]


def test_fabricated_reference_is_dropped_after_retries():
    bad = json.loads(json.dumps(MARKET_ANSWER))
    bad["pathways"][0]["applications"].append(finding("Lignin is used in car tyres.", "EV-PF-99#1"))
    result = run(model=models(market=scripted(with_final(MARKET, bad))))
    market = result.execution.agent("market")
    assert [g.action for g in market.guard_events] == ["retry_requested", "retry_requested", "fixed_by_code"]
    assert "no evidence record EV-PF-99" in market.guard_events[0].problems[0]
    apps = next(s for s in result.market if s.pathway_id == PF).findings.applications
    assert [f.evidence for f in apps] == [("EV-PF-02#1",)]  # the fabricated finding was removed
    assert result.status == "complete"


def test_commercialization_can_cite_the_feedstock_agent_findings():
    answer = json.loads(json.dumps(COMMERCIAL_ANSWER))
    answer["pathways"][0]["adoption_barriers"].append(finding("Without a dryer the lignin stays as wet cake.", "feedstock:constraints[0]"))
    result = run(model=models(commercialization=scripted(with_final(COMMERCIAL, answer))))
    assert result.execution.agent("commercialization").guard_events == []
    barriers = next(s for s in result.commercialization if s.pathway_id == PF).findings.adoption_barriers
    assert ("feedstock:constraints[0]",) in [f.evidence for f in barriers]


def test_repair_removes_bad_references_but_keeps_a_supported_score():
    answer = json.loads(json.dumps(COMMERCIAL_ANSWER))
    answer["pathways"][0]["commercialization_feasibility"]["evidence"] = ["feedstock:infrastructure[2]", "feedstock:nonsense[1]"]
    result = run(model=models(commercialization=scripted(with_final(COMMERCIAL, answer))))
    assert result.execution.agent("commercialization").guard_events[-1].action == "fixed_by_code"
    judgment = next(s for s in result.commercialization if s.pathway_id == PF).findings.commercialization_feasibility
    assert judgment is not None and judgment.score == 3
    assert judgment.evidence == ("feedstock:infrastructure[2]",)


def test_number_not_in_the_evidence_is_sent_back_once():
    bad = json.loads(json.dumps(MARKET_ANSWER))
    bad["pathways"][0]["applications"][0]["statement"] = "UPM says lignin can replace up to 95% of phenol."
    script = [*MARKET[:-1], ("final", bad), ("final", MARKET_ANSWER)]
    result = run(model=models(market=scripted(script)))
    events = result.execution.agent("market").guard_events
    assert [g.action for g in events] == ["retry_requested"]
    assert "['95']" in events[0].problems[0]


def test_wrong_dry_mass_is_corrected():
    wrong = {**FEEDSTOCK_ANSWER, "dry_mass_t_per_yr": 25000}
    result = run(model=models(feedstock=scripted(with_final(FEEDSTOCK, wrong))))
    events = result.execution.agent("feedstock").guard_events
    assert events[-1].action == "fixed_by_code"
    assert result.feedstock.agent.dry_mass_t_per_yr == pytest.approx(26_000)


def test_decision_cannot_reorder_the_ranking():
    result = run(model=models(decision=scripted([[("score_and_rank", {})], ("final", lambda m: decision_answer(m, reverse=True))])))
    assert result.execution.agent("decision").guard_events[-1].action == "fixed_by_code"
    assert [(s.pathway_id, s.rank) for s in result.decision.report.shortlist] == [(CM, 1), (PF, None), (PU, None)]


def test_tool_rejects_a_trl_the_evidence_does_not_state():
    script = [COMMERCIAL[0],
              [("assess_technical_readiness", {"pathway_id": PF, "trl": 9, "evidence": ["EV-PF-01#3"]})],
              *COMMERCIAL[1:]]
    result = run(model=models(commercialization=scripted(script)))
    calls = [(c.tool, c.status) for c in result.execution.agent("commercialization").tool_calls
             if c.tool == "assess_technical_readiness"]
    assert calls[0] == ("assess_technical_readiness", "rejected")
    assert "none of the cited evidence states TRL 9" in result.execution.agent("commercialization").tool_calls[9].result
    assert {s.pathway_id: s.technical_readiness.score for s in result.commercialization}[PF] == 5  # TRL 8 accepted later


# --- Failures -------------------------------------------------------------------------------------------------


def test_transient_error_is_retried_once_then_reported():
    result = run(model=models(market=failing(lambda: ModelHTTPError(503, "scripted", "service unavailable"))))
    market = result.execution.agent("market")
    assert (market.status, market.attempts, len(market.errors)) == ("failed", 2, 2)
    assert "ModelHTTPError" in market.errors[0]
    later = [(a.agent, a.status) for a in result.execution.agents][2:]
    assert later == [("commercialization", "skipped"), ("decision", "skipped")]
    assert result.status == "partial"
    assert result.market is None and result.commercialization is None and result.decision.report is None
    # The deterministic ranking is still produced, with the judgment criteria marked not assessed.
    assert result.decision.ranking_source.startswith("computed by the workflow")
    all_results = (*result.decision.ranking.ranked, *result.decision.ranking.insufficient_data)
    assert all("market_evidence" in o.completeness.not_assessed for o in all_results)


def test_permanent_error_is_not_retried():
    result = run(model=models(feedstock=failing(lambda: ModelHTTPError(400, "scripted", "bad request"))))
    first = result.execution.agent("feedstock")
    assert (first.status, first.attempts) == ("failed", 1)
    assert result.status == "failed"
    assert [a.status for a in result.execution.agents] == ["failed", "skipped", "skipped", "skipped"]


def test_agent_timeout():
    result = run(model=models(market=failing(lambda: RuntimeError("never reached"), delay=5)), agent_timeout=0.2)
    market = result.execution.agent("market")
    assert (market.status, market.attempts) == ("failed", 2)
    assert all("TimeoutError" in e for e in market.errors)


def test_runaway_tool_loop_hits_the_usage_limit():
    loop = scripted([[("list_pathways", {})]])  # never answers
    result = run(model=models(market=loop))
    market = result.execution.agent("market")
    assert (market.status, market.attempts) == ("failed", 1)
    assert "UsageLimitExceeded" in market.errors[0]
    assert len(market.tool_calls) <= config.AGENT_USAGE_LIMITS.tool_calls_limit


def test_missing_api_key_fails_clearly(monkeypatch):
    monkeypatch.delenv("PORTKEY_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="PORTKEY_API_KEY is not set"):
        config.build_model()
