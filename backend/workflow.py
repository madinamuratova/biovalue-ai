"""The BioValue AI workflow: four agents in a fixed order, with validated data passed between them.

    1. Feedstock Agent            -> FeedstockAgentOutput
    2. Market Intelligence Agent  -> MarketAgentOutput            (given the feedstock profile)
    3. Commercialization Agent    -> CommercializationAgentOutput (given both)
    4. Decision Agent             -> DecisionAgentOutput          (given summaries of all three)

Safety and reliability:
- the feedstock's free text is screened before any agent sees it; instruction-like text is replaced and logged
- each agent runs once, under a timeout and usage limits, inside a per-run token budget; a timeout or transient API
  error (429, 5xx, connection) gets one more attempt, anything else fails at once
- if an agent fails, the later agents are skipped and the workflow still returns a structured, partial assessment,
  including the deterministic ranking, which never depends on the model
- the result separates documented facts, assumptions, estimates, and unknowns (the ledger), and every run's tokens
  and latency are logged per agent from the provider's usage metadata

Run it with: .venv/bin/python scripts/run_workflow.py
"""

import asyncio
import json
import time
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Literal

from openai import APIConnectionError, APITimeoutError
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError
from pydantic_ai.models import Model
from pydantic_ai.usage import RunUsage, UsageLimits

from backend import data, tokenomics
from backend.agents import AGENT_ORDER, AGENT_TITLES, build_agents
from backend.agents import deterministic
from backend.agents.deps import WorkflowDeps
from backend.agents.refs import EVIDENCE_REF, record_ids, resolve
from backend.agents.schemas import DecisionAgentOutput, FeedstockAgentOutput, PathwayCommercialization, PathwayMarket
from backend.calc import NOT_CALCULATED_METRICS, SCENARIOS, ScenarioAnalysis
from backend.config import (
    AGENT_ATTEMPTS, AGENT_TIMEOUT_SECONDS, AGENT_USAGE_LIMITS, OUTPUT_DIR, RunConfig, build_model, default_run_config,
    model_name,
)
from backend.feedstock import FeedstockProfile
from backend.models import Frozen
from backend.project import Project
from backend.safety import SAFETY_DISCLAIMER, neutralize_tree, redact
from backend.scoring import Assessment, Ranking, ScoringConfig, not_assessed
from backend.tokenomics import CostReport
from backend.trace import AgentRun, Trace, Usage, append_json, now, short

FINDING_LISTS = ("applications", "target_customers", "competing_materials", "qualification_requirements")


# --- The final assessment -------------------------------------------------------------------------------


class FeedstockStage(Frozen):
    agent: FeedstockAgentOutput
    normalized: dict  # deterministic: the profile in canonical units
    checks: dict  # deterministic: the validation report


class MarketPathwayStage(Frozen):
    pathway_id: str
    source_ids: tuple[str, ...]  # every evidence record the findings cite
    supported_claims: dict[str, str]  # reference -> the claim or requirement text it points to
    findings: PathwayMarket


class CommercializationPathwayStage(Frozen):
    pathway_id: str
    findings: PathwayCommercialization
    feedstock_compatibility: Assessment  # deterministic rule
    technical_readiness: Assessment  # deterministic mapping of a TRL confirmed from the evidence
    indicative_economics: Assessment  # deterministic rule
    scenario_analysis: ScenarioAnalysis  # deterministic, three scenarios


class DecisionStage(Frozen):
    ranking: Ranking  # deterministic scoring engine
    ranking_source: str
    report: DecisionAgentOutput | None


class LedgerItem(Frozen):
    statement: str
    source: str


class Ledger(Frozen):
    """What the assessment rests on, kept apart so a reader never mistakes one kind for another."""

    documented_facts: tuple[LedgerItem, ...]  # stated in a cited evidence record, or a measured input
    assumptions: tuple[LedgerItem, ...]  # inputs nobody measured: fictional values and economic assumptions
    estimates: tuple[LedgerItem, ...]  # calculated from the above, scored by a rule, or judged by an agent
    unknowns: tuple[LedgerItem, ...]  # missing inputs and data, unassessed criteria, gaps the agents reported


class FinalAssessment(Frozen):
    run_id: str
    created_at: str
    model: str
    config: str = "not recorded"  # runs saved before configurations existed don't have one
    project_id: str
    project_name: str
    status: Literal["complete", "partial", "failed"]
    disclaimers: tuple[str, ...]
    feedstock: FeedstockStage | None
    market: tuple[MarketPathwayStage, ...] | None
    commercialization: tuple[CommercializationPathwayStage, ...] | None
    decision: DecisionStage
    ledger: Ledger | None = None  # runs saved before the ledger existed don't have one
    execution: Trace
    usage: Usage
    cost: CostReport


# --- Prompts: validated data passed from one agent to the next ---------------------------------------------


def _json(obj, compact: bool = False) -> str:
    if hasattr(obj, "model_dump"):
        obj = obj.model_dump(mode="json")
    return json.dumps(obj, separators=(",", ":"), default=str) if compact else json.dumps(obj, indent=1, default=str)


def _feedstock_summary(deps: WorkflowDeps) -> dict:
    f, record = deps.feedstock_output, deps.project.feedstock
    return {"is_fictional": f.is_fictional, "dry_mass_t_per_yr": f.dry_mass_t_per_yr,
            "missing_properties": f.missing_properties, "constraints": f.constraints,
            "geographic_market": record.geographic_market.model_dump(mode="json")}


def _market_summary(deps: WorkflowDeps) -> list[dict]:
    return [{"pathway_id": pm.pathway_id,
             "findings": [{"type": name, "statement": f.statement, "evidence": f.evidence}
                          for name in FINDING_LISTS for f in getattr(pm, name)],
             "market_evidence": pm.market_evidence and {"score": pm.market_evidence.score,
                                                        "evidence": pm.market_evidence.evidence},
             "missing_information": pm.missing_information} for pm in deps.market_output.pathways]


def prompt_for(name: str, deps: WorkflowDeps) -> str:
    """The user prompt for one agent. The optimized configuration sends only the fields the agent needs, as compact
    JSON; the baseline sends the earlier agents' full validated answers."""
    p, compact = deps.project, deps.config.compact_context
    pathways = ", ".join(p.pathway_ids)
    if name == "feedstock":
        return f"Project: {p.name}.\nAssess the feedstock record {p.feedstock.id} and return the validated profile."
    feedstock = _feedstock_summary(deps) if compact else deps.feedstock_output
    if name == "market":
        return (f"Project: {p.name}.\nPathways in scope, in this order: {pathways}.\n\n"
                f"Feedstock profile from the Feedstock Agent (validated):\n{_json(feedstock, compact)}\n\n"
                "Return your market findings for each pathway.")
    if name == "commercialization":
        market = _market_summary(deps) if compact else deps.market_output
        return (f"Project: {p.name}.\nPathways in scope, in this order: {pathways}.\n\n"
                f"Feedstock profile from the Feedstock Agent (validated):\n{_json(feedstock, compact)}\n\n"
                f"Market findings from the Market Intelligence Agent (validated; references checked):\n"
                f"{_json(market, compact)}\n\nReturn your assessment for each pathway.")
    f, m, c = deps.feedstock_output, deps.market_output, deps.commercialization_output
    summary = {
        "feedstock": {"is_fictional": f.is_fictional, "dry_mass_t_per_yr": f.dry_mass_t_per_yr,
                      "missing_properties": f.missing_properties, "constraints": f.constraints},
        "market": [{"pathway_id": x.pathway_id, "market_evidence": x.market_evidence and x.market_evidence.model_dump(),
                    "missing_information": x.missing_information} for x in m.pathways],
        "commercialization": [{"pathway_id": x.pathway_id,
                               "technical_maturity": x.technical_maturity and x.technical_maturity.statement,
                               "commercialization_feasibility": x.commercialization_feasibility
                               and x.commercialization_feasibility.model_dump(),
                               "missing_inputs": x.missing_inputs, "uncertainties": x.uncertainties}
                              for x in c.pathways],
    }
    return (f"Project: {p.name}.\nPathways in scope: {pathways}.\n\nSummaries from the earlier agents (validated):\n"
            f"{_json(summary, compact)}\n\nCall score_and_rank, then return the shortlist, validation steps, and what "
            "could change the ranking.")


# --- Running one agent ---------------------------------------------------------------------------------------


def is_transient(exc: BaseException) -> bool:
    """Worth one more attempt: timeouts, rate limits, server errors, and lost connections."""
    if isinstance(exc, (TimeoutError, APITimeoutError, APIConnectionError)):
        return True
    if isinstance(exc, ModelHTTPError):
        return exc.status_code == 429 or exc.status_code >= 500
    return isinstance(exc, ModelAPIError)


async def run_agent(agent, prompt: str, deps: WorkflowDeps, run: AgentRun, timeout: float, attempts: int,
                    limits: UsageLimits = AGENT_USAGE_LIMITS):
    """Run one agent with a timeout and bounded attempts. Returns its validated output, or None if it failed.
    Malformed answers are rejected by the schema and the guards; after the allowed retries the agent fails."""
    run.started_at = now()
    for attempt in range(1, attempts + 1):
        run.attempts, run.status = attempt, "running"
        usage, start = RunUsage(), time.perf_counter()
        try:
            result = await asyncio.wait_for(agent.run(prompt, deps=deps, usage=usage, usage_limits=limits), timeout)
        except Exception as exc:  # recorded and handled: the workflow never crashes on one agent
            run.errors.append(f"attempt {attempt}: {type(exc).__name__}: {short(str(exc) or repr(exc), 500)}")
            if attempt < attempts and is_transient(exc):
                continue
            run.status = "failed"
            return None
        else:
            run.status = "ok"
            return result.output
        finally:
            run.usage.add(Usage.from_run(usage))
            run.seconds = round((run.seconds or 0) + time.perf_counter() - start, 2)
            run.finished_at = now()
    return None


def screen_feedstock(project: Project, trace: Trace) -> Project:
    """Replace instruction-like text in the feedstock's free-text fields before any agent sees it."""
    cleaned, events = neutralize_tree(project.feedstock.model_dump(mode="json"))
    if not events:
        return project
    trace.record_security("feedstock input", events)
    if project.feedstock.data_status == "fictional_demo" and "fictional" not in cleaned["disclaimer"].lower():
        cleaned["disclaimer"] = "Fictional demo data. " + cleaned["disclaimer"]
    return project.model_copy(update={"feedstock": FeedstockProfile.model_validate(cleaned)})


# --- Assembling the result -------------------------------------------------------------------------------------


def _market_stage(deps: WorkflowDeps) -> tuple[MarketPathwayStage, ...]:
    stages = []
    for pm in deps.market_output.pathways:
        refs = [r for name in FINDING_LISTS for f in getattr(pm, name) for r in f.evidence]
        if pm.market_evidence:
            refs += list(pm.market_evidence.evidence)
        refs = list(dict.fromkeys(refs))
        stages.append(MarketPathwayStage(
            pathway_id=pm.pathway_id, source_ids=tuple(sorted(record_ids(refs))),
            supported_claims={r: _claim_text(deps, r) for r in refs},
            findings=pm))
    return tuple(stages)


def _claim_text(deps: WorkflowDeps, ref: str) -> str:
    """The claim or requirement a reference points to, without its supporting quote."""
    r = resolve(deps.project, ref, deps.feedstock_output)
    if r.kind == "feedstock":
        return r.text
    record = deps.project.evidence.record(r.record_id)
    index = int(ref.split("#")[1].lstrip("R"))
    if r.kind == "requirement":
        q = record.technical_requirements[index - 1]
        return f"{q.parameter}: {q.requirement}"
    return record.claims[index - 1].text


def _commercialization_stage(deps: WorkflowDeps) -> tuple[CommercializationPathwayStage, ...]:
    stages = []
    for pc in deps.commercialization_output.pathways:
        pid = pc.pathway_id
        analysis = deps.economics.get(pid) or deterministic.economics(deps.project, pid)
        assessments, _ = deterministic.assessments_for(deps, pid)
        stages.append(CommercializationPathwayStage(
            pathway_id=pid, findings=pc,
            feedstock_compatibility=assessments[0],
            technical_readiness=deps.readiness.get(pid) or not_assessed("technical_readiness", "No TRL was confirmed from the evidence."),
            indicative_economics=assessments[3], scenario_analysis=analysis))
    return tuple(stages)


def _cited_refs(deps: WorkflowDeps) -> list[str]:
    refs = []
    for pm in deps.market_output.pathways if deps.market_output else ():
        refs += [r for name in FINDING_LISTS for f in getattr(pm, name) for r in f.evidence]
        refs += list(pm.market_evidence.evidence) if pm.market_evidence else []
    for pc in deps.commercialization_output.pathways if deps.commercialization_output else ():
        findings = [*pc.processing_requirements, *pc.adoption_barriers] + ([pc.technical_maturity] if pc.technical_maturity else [])
        refs += [r for f in findings for r in f.evidence]
        refs += list(pc.commercialization_feasibility.evidence) if pc.commercialization_feasibility else []
    for a in deps.readiness.values():
        refs += [r for line in a.rationale.split() if (r := line.strip(".,")) and EVIDENCE_REF.fullmatch(r)]
    return [r for r in dict.fromkeys(refs) if EVIDENCE_REF.fullmatch(r)]


def build_ledger(deps: WorkflowDeps, ranking: Ranking) -> Ledger:
    """Sort what the assessment rests on into documented facts, assumptions, estimates, and unknowns. Built by code
    from the validated results, so the categories can't be blurred by the model."""
    p = deps.project
    names = {pid: p.evidence.pathway(pid).name for pid in p.pathway_ids}
    facts, assumptions, estimates, unknowns = [], [], [], []

    for ref in _cited_refs(deps):
        record = p.evidence.record(EVIDENCE_REF.fullmatch(ref).group(1))
        facts.append(LedgerItem(statement=_claim_text(deps, ref), source=f"{ref} · {record.quality} quality evidence"))
    for path, q in p.feedstock.quantities():
        if q.value is None or q.basis == "calculated":
            continue
        line = LedgerItem(statement=f"{path} = {q.value:g} {q.unit}", source=f"feedstock input, {q.basis.replace('_', ' ')}")
        (facts if q.basis == "measured" else assumptions).append(line)
    for pid in p.pathway_ids:
        analysis = deps.economics.get(pid) or deterministic.economics(p, pid)
        for a in analysis.assumptions:
            if a.input in ("wet feedstock mass", "moisture"):
                continue  # already listed with the feedstock inputs
            values = f"{a.base:g} {a.unit}" if a.held_constant else f"{a.conservative:g} / {a.base:g} / {a.optimistic:g} {a.unit}"
            assumptions.append(LedgerItem(statement=f"{names[pid]}: {a.input} = {values}",
                                          source=f"economic input, {a.basis.replace('_', ' ')}"))
        for key in ("dry_mass", "usable_feedstock", "product_output", "revenue", "gross_contribution"):
            steps = [analysis.scenarios[s].steps[key] for s in SCENARIOS]
            if steps[1].status == "calculated":
                estimates.append(LedgerItem(
                    statement=f"{names[pid]}: {steps[1].label.lower()} {steps[0].value:,.0f} / {steps[1].value:,.0f} / "
                              f"{steps[2].value:,.0f} {steps[1].unit} (conservative / base / optimistic)",
                    source=f"calculated: {steps[1].formula}"))
        for m in analysis.missing_inputs:
            unknowns.append(LedgerItem(statement=f"{names[pid]}: {m}", source="economic input not supplied"))
    for o in (*ranking.ranked, *ranking.insufficient_data):
        for c in o.criteria:
            if c.score is None:
                unknowns.append(LedgerItem(statement=f"{o.name}: {c.label.lower()} not assessed", source=c.rationale))
            else:
                kind = "rule" if c.method == "rule" else "agent judgment"
                estimates.append(LedgerItem(statement=f"{o.name}: {c.label.lower()} scored {c.score} of 5",
                                            source=f"{kind}: {c.rationale}"))
        if o.attractiveness is not None:
            estimates.append(LedgerItem(statement=f"{o.name}: attractiveness {o.attractiveness} of 5 "
                                                  f"({o.completeness.assessed_weight:.0%} of the weight assessed)",
                                        source="scoring engine"))
    for path in p.feedstock.missing_fields():
        unknowns.append(LedgerItem(statement=f"feedstock {path}", source="not measured (data gap)"))
    for pm in deps.market_output.pathways if deps.market_output else ():
        unknowns += [LedgerItem(statement=f"{names[pm.pathway_id]}: {x}", source="reported missing by the Market Intelligence Agent")
                     for x in pm.missing_information]
    return Ledger(documented_facts=tuple(facts), assumptions=tuple(assumptions), estimates=tuple(estimates),
                  unknowns=tuple(unknowns))


def _usage_record(a: AgentRun, model: str) -> dict:
    u = a.usage
    return {"model": model, "status": a.status, "requests": u.requests, "tool_calls": u.tool_calls,
            "input_tokens": u.input_tokens, "cached_input_tokens": u.cache_read_tokens,
            "uncached_input_tokens": u.input_tokens - u.cache_read_tokens, "output_tokens": u.output_tokens,
            "reasoning_tokens": u.reasoning_tokens if u.reasoning_tokens is not None else "not reported",
            "latency_seconds": a.seconds, "cost": tokenomics.cost_report(model, u).model_dump()}


def _save(result: FinalAssessment, output_dir: Path) -> Path:
    runs = output_dir / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    path = runs / f"{result.run_id}.json"
    text = redact(result.model_dump_json(indent=2))
    path.write_text(text + "\n", encoding="utf-8")
    (output_dir / "latest_assessment.json").write_text(text + "\n", encoding="utf-8")
    base = {"run_id": result.run_id, "source": "biovalue_workflow"}
    records = [{"timestamp": result.execution.started_at, **base, "event": "run_start", "model": result.model,
                "config": result.config, "project_id": result.project_id,
                "security_events": [e.model_dump() for e in result.execution.security_events]}]
    for a in result.execution.agents:
        records.append({"timestamp": a.finished_at or now(), **base, "event": "agent_finished", "agent": a.agent,
                        "order": a.order, "status": a.status, "attempts": a.attempts, "seconds": a.seconds,
                        "usage": a.usage.model_dump(), "errors": a.errors, "skipped_reason": a.skipped_reason,
                        "tool_calls": [c.model_dump() for c in a.tool_calls],
                        "guard_events": [g.model_dump() for g in a.guard_events]})
    records.append({"timestamp": result.execution.finished_at, **base, "event": "run_end", "status": result.status,
                    "ranked": [o.pathway_id for o in result.decision.ranking.ranked],
                    "insufficient_data": [o.pathway_id for o in result.decision.ranking.insufficient_data]})
    append_json(output_dir / "audit_trail.json", json.loads(redact(json.dumps(records, default=str))))
    total = result.usage
    append_json(output_dir / "usage_log.json", [{
        "timestamp": result.created_at, **base, "model": result.model, "config": result.config, "status": result.status,
        "usage_source": "provider usage metadata (OpenAI Responses API through Portkey), aggregated by PydanticAI",
        "agents": {a.agent: _usage_record(a, result.model) for a in result.execution.agents},
        "total": {"requests": total.requests, "tool_calls": total.tool_calls, "input_tokens": total.input_tokens,
                  "cached_input_tokens": total.cache_read_tokens,
                  "uncached_input_tokens": total.input_tokens - total.cache_read_tokens,
                  "output_tokens": total.output_tokens,
                  "reasoning_tokens": total.reasoning_tokens if total.reasoning_tokens is not None else "not reported",
                  "latency_seconds": round(sum(a.seconds or 0 for a in result.execution.agents), 2)},
        "cost": result.cost.model_dump()}])
    return path


# --- The workflow -------------------------------------------------------------------------------------------------


def new_run_id() -> str:
    return f"run-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"


async def run_workflow(project: Project | None = None, *, model: Model | Callable[[str], Model] | None = None,
                       scoring_config: ScoringConfig | None = None, run_id: str | None = None,
                       config: RunConfig | None = None,
                       agent_timeout: float = AGENT_TIMEOUT_SECONDS, attempts: int = AGENT_ATTEMPTS,
                       output_dir: Path | None = OUTPUT_DIR, trace: Trace | None = None,
                       screen_inputs: bool = True) -> FinalAssessment:
    """Run the four agents in order on a project (the demo project by default) and return the final assessment.
    With output_dir set, the assessment is saved under output_dir/runs/ and the logs are appended. Pass a `trace`
    to watch progress while the run is going (the API does this). `screen_inputs=False` exists only so the safety
    evaluation can measure the other defenses on their own; the app and the API never turn screening off."""
    config = config or default_run_config()
    project = project or data.project()
    scoring_config = scoring_config or data.scoring_config()
    label = model_name() if model is None else getattr(model, "model_name", "per-agent models")
    model = model or build_model()
    trace = trace or Trace(run_id=run_id or new_run_id(), model=label)
    trace.model, trace.config, trace.token_budget = label, config.name, config.run_token_budget
    trace.add_agents(list(AGENT_ORDER))
    if screen_inputs:
        project = screen_feedstock(project, trace)
    deps = WorkflowDeps(project=project, scoring=scoring_config, trace=trace, config=config)
    agents = build_agents(model, config)

    stop, decision_report = "", None
    for name in AGENT_ORDER:
        run = trace.agent(name)
        if stop:
            run.status, run.skipped_reason = "skipped", stop
            continue
        remaining = config.run_token_budget - trace.total_usage.total_tokens
        if remaining <= 0:
            run.status = "failed"
            run.errors.append(f"Run token budget of {config.run_token_budget:,} tokens was used up before this agent started.")
            stop = f"Skipped because the run token budget of {config.run_token_budget:,} tokens was used up."
            continue
        limits = UsageLimits(request_limit=AGENT_USAGE_LIMITS.request_limit,
                             tool_calls_limit=AGENT_USAGE_LIMITS.tool_calls_limit,
                             total_tokens_limit=min(AGENT_USAGE_LIMITS.total_tokens_limit, remaining))
        deps.agent = name
        output = await run_agent(agents[name], prompt_for(name, deps), deps, run, agent_timeout, attempts, limits)
        if output is None:
            stop = f"Skipped because the {AGENT_TITLES[name]} failed."
        elif name != "decision":
            setattr(deps, f"{name}_output", output)
        else:
            decision_report = output
    trace.finished_at = now()

    decided = trace.agent("decision").status == "ok"
    ranking = deps.ranking if decided and deps.ranking else deterministic.score_and_rank(deps)
    statuses = [a.status for a in trace.agents]
    status = "complete" if all(s == "ok" for s in statuses) else "partial" if "ok" in statuses else "failed"
    disclaimers = [SAFETY_DISCLAIMER, NOT_CALCULATED_METRICS,
                   "Scores use a 1-5 scale. A criterion that was not assessed lowers data completeness; it is never "
                   "counted as a low score."]
    if project.feedstock.data_status != "measured":
        disclaimers.insert(0, project.feedstock.disclaimer)
    if trace.security_events:
        disclaimers.append(f"{len(trace.security_events)} piece(s) of input or evidence text read like instructions to "
                           "the AI and were replaced before the agents saw them (see the execution trace).")

    result = FinalAssessment(
        run_id=trace.run_id, created_at=now(), model=label, config=config.name, project_id=project.id,
        project_name=project.name, status=status, disclaimers=tuple(disclaimers),
        feedstock=FeedstockStage(agent=deps.feedstock_output, normalized=deterministic.normalized_feedstock(project),
                                 checks=deps.feedstock_check or deterministic.feedstock_checks(project))
        if deps.feedstock_output else None,
        market=_market_stage(deps) if deps.market_output else None,
        commercialization=_commercialization_stage(deps) if deps.commercialization_output else None,
        decision=DecisionStage(
            ranking=ranking,
            ranking_source="score_and_rank, called by the Decision Agent" if decided
            else "computed by the workflow, because the Decision Agent did not finish",
            report=decision_report if decided else None),
        ledger=build_ledger(deps, ranking),
        execution=trace, usage=trace.total_usage, cost=tokenomics.cost_report(label, trace.total_usage),
    )
    if output_dir is not None:
        _save(result, output_dir)
    return result
