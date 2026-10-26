"""Output guards: code that checks every agent answer against the data after the schema check passes.

Each agent has a `check` (what's wrong with an answer) and a `fix` (a repaired answer). The pattern is the one
from HW 6: the agent gets up to OUTPUT_RETRIES chances to fix its answer with specific feedback; after that the
code repairs it (fail closed) and the trace records what was changed. A repair never invents content: it puts
in the deterministic value, drops an unsupported statement, or marks a judgment as not assessed.

What the guards enforce:
- numbers copied from tools match the deterministic results
- every evidence reference exists, is supported, and belongs to the pathway it is used for
- every number in a statement appears in what it cites or in a deterministic result
- each agent called the tools its answer depends on
- the Decision Agent's shortlist follows the deterministic ranking exactly
"""

import math
from collections.abc import Callable

from pydantic_ai import ModelRetry, RunContext

from backend.agents import deterministic
from backend.agents.deps import WorkflowDeps
from backend.agents.refs import cited_numbers, ref_problems, unsupported_numbers
from backend.agents.refs import record_ids
from backend.agents.schemas import (
    CommercializationAgentOutput, DecisionAgentOutput, EvidenceFinding, FeedstockAgentOutput, Judgment,
    MarketAgentOutput, PathwayCommercialization, PathwayMarket, ShortlistItem, ValidationStep,
)
from backend.safety import prohibited_claims
from backend.trace import short


def _close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=1e-3, abs_tol=1e-6)


def _leaf(path: str) -> str:
    return path.rsplit(".", 1)[-1]


def _text_problems(label: str, texts, allowed: set[float]) -> list[str]:
    problems = []
    for text in texts:
        if bad := unsupported_numbers(text, allowed):
            problems.append(f"{label}: '{short(text, 120)}' contains {bad}, which no tool result or evidence supports")
        for claim in prohibited_claims(text):
            problems.append(f"{label}: '{short(text, 120)}' makes a prohibited claim ({claim}). BioValue AI may not claim "
                            "guaranteed profitability, verified customer demand, or engineering approval")
    return problems


def _clean(text: str, allowed: set[float]) -> bool:
    """True when a piece of free text has no unsupported number and no prohibited claim."""
    return not unsupported_numbers(text, allowed) and not prohibited_claims(text)


def _finding_problems(deps: WorkflowDeps, pid: str, label: str, finding: EvidenceFinding, base: set[float]) -> list[str]:
    problems = [f"{pid} {label}: {p}" for p in ref_problems(deps.project, finding.evidence, pid, deps.feedstock_output)]
    allowed = base | cited_numbers(deps.project, finding.evidence, deps.feedstock_output)
    return problems + _text_problems(f"{pid} {label}", [finding.statement], allowed)


def _valid_refs(deps: WorkflowDeps, pid: str, refs) -> tuple[str, ...]:
    return tuple(r for r in refs if not ref_problems(deps.project, [r], pid, deps.feedstock_output))


def _repair_finding(deps: WorkflowDeps, pid: str, finding: EvidenceFinding, base: set[float]) -> EvidenceFinding | None:
    """Keep a finding with its invalid references removed, if valid support remains and its numbers still check out."""
    refs = _valid_refs(deps, pid, finding.evidence)
    if not refs:
        return None
    repaired = finding.model_copy(update={"evidence": refs})
    return None if _finding_problems(deps, pid, "x", repaired, base) else repaired


def _repair_findings(deps: WorkflowDeps, pid: str, findings, base: set[float]) -> tuple[EvidenceFinding, ...]:
    return tuple(f for f in (_repair_finding(deps, pid, x, base) for x in findings) if f is not None)


def _judgment_problems(deps: WorkflowDeps, pid: str, label: str, judgment: Judgment | None, base: set[float],
                       needs_evidence: bool) -> list[str]:
    if judgment is None:
        return []
    problems = [f"{pid} {label}: {p}" for p in ref_problems(deps.project, judgment.evidence, pid, deps.feedstock_output)]
    if needs_evidence and not judgment.evidence:
        problems.append(f"{pid} {label}: cite the evidence the score rests on")
    allowed = base | cited_numbers(deps.project, judgment.evidence, deps.feedstock_output)
    if label == "market_evidence" and not problems and (cap := _market_score_cap(deps, judgment)):
        problems.append(f"{pid} {label}: {cap}")
    return problems + _text_problems(f"{pid} {label} rationale", [judgment.rationale], allowed)


def _repair_judgment(deps: WorkflowDeps, pid: str, label: str, judgment: Judgment | None, base: set[float],
                     needs_evidence: bool) -> Judgment | None:
    """Keep a score with its invalid references removed; drop it (not assessed) if it still fails any check,
    including the market-evidence score cap."""
    if judgment is None:
        return None
    repaired = judgment.model_copy(update={"evidence": _valid_refs(deps, pid, judgment.evidence)})
    return None if _judgment_problems(deps, pid, label, repaired, base, needs_evidence) else repaired


def _keep_text(items, allowed: set[float]) -> tuple[str, ...]:
    return tuple(t for t in items if _clean(t, allowed))


def _market_score_cap(deps: WorkflowDeps, judgment: Judgment) -> str:
    """A high market-evidence score must rest on matching evidence: 4 or 5 needs at least one cited record of high or
    moderate quality, and 5 ("several producers sell commercially") needs at least two distinct records."""
    records = [deps.project.evidence.record(rid) for rid in record_ids(judgment.evidence)
               if rid in {r.id for r in deps.project.evidence.records}]
    if judgment.score >= 4 and not any(r.quality in ("high", "moderate") for r in records):
        return f"a market_evidence score of {judgment.score} needs at least one cited record of high or moderate quality"
    if judgment.score == 5 and len(records) < 2:
        return "a market_evidence score of 5 needs at least two distinct cited records"
    return ""


# --- Feedstock Agent ------------------------------------------------------------------------------------


def check_feedstock(deps: WorkflowDeps, out: FeedstockAgentOutput) -> list[str]:
    truth = deterministic.normalized_feedstock(deps.project)
    problems = []
    if deps.feedstock_check is None:
        problems.append("call validate_feedstock before answering")
    if not deps.dry_mass_results:
        problems.append("call calculate_dry_mass before answering")
    if out.feedstock_id != truth["feedstock_id"]:
        problems.append(f"feedstock_id must be {truth['feedstock_id']!r}")
    if out.is_fictional != truth["is_fictional"]:
        problems.append(f"is_fictional must be {truth['is_fictional']}: the record's data_status is "
                        f"{deps.project.feedstock.data_status!r}")
    for field in ("wet_mass_t_per_yr", "moisture_fraction", "dry_mass_t_per_yr"):
        if not _close(getattr(out, field), truth[field]):
            problems.append(f"{field} is {getattr(out, field)}, but the tools give {truth[field]}")
    expected = {_leaf(p) for p in deps.project.feedstock.missing_fields()}
    if {_leaf(p) for p in out.missing_properties} != expected:
        problems.append(f"missing_properties must be exactly the missing fields from validate_feedstock: "
                        f"{deps.project.feedstock.missing_fields()}")
    allowed = deterministic.allowed_numbers(deps, include_evidence=False)
    texts = [*out.inconsistencies, *out.constraints, *out.data_quality_notes, out.summary]
    return problems + _text_problems("feedstock text", texts, allowed)


def fix_feedstock(deps: WorkflowDeps, out: FeedstockAgentOutput) -> FeedstockAgentOutput:
    truth = deterministic.normalized_feedstock(deps.project)
    deps.feedstock_check = deps.feedstock_check or deterministic.feedstock_checks(deps.project)
    allowed = deterministic.allowed_numbers(deps, include_evidence=False)
    unavailable = deps.feedstock_check["infrastructure"]["not_available"]
    constraints = _keep_text(out.constraints, allowed) or tuple(f"Not available at the mill: {a}." for a in unavailable) \
        or ("No constraints could be verified from the record.",)
    summary = out.summary if _clean(out.summary, allowed) else \
        "Summary removed by the guard because it contained unsupported numbers or a prohibited claim; see the fields above."
    return out.model_copy(update={
        "feedstock_id": truth["feedstock_id"], "is_fictional": truth["is_fictional"],
        "wet_mass_t_per_yr": truth["wet_mass_t_per_yr"], "moisture_fraction": truth["moisture_fraction"],
        "dry_mass_t_per_yr": truth["dry_mass_t_per_yr"],
        "missing_properties": tuple(deps.project.feedstock.missing_fields()),
        "inconsistencies": _keep_text(out.inconsistencies, allowed), "constraints": constraints,
        "data_quality_notes": _keep_text(out.data_quality_notes, allowed), "summary": summary,
    })


# --- Market Intelligence Agent ----------------------------------------------------------------------------

MARKET_LISTS = ("applications", "target_customers", "competing_materials", "qualification_requirements")


def check_market(deps: WorkflowDeps, out: MarketAgentOutput) -> list[str]:
    expected = list(deps.project.pathway_ids)
    got = [p.pathway_id for p in out.pathways]
    problems = [] if got == expected else [f"pathways must be exactly {expected}, in that order (got {got})"]
    for pm in out.pathways:
        pid = pm.pathway_id
        if pid not in expected:
            continue
        if pid not in deps.searched_pathways:
            problems.append(f"call search_evidence for {pid} before answering")
        base = deterministic.allowed_numbers(deps, pid, include_evidence=False)
        for name in MARKET_LISTS:
            for finding in getattr(pm, name):
                problems += _finding_problems(deps, pid, name, finding, base)
        free = deterministic.allowed_numbers(deps, pid)
        problems += _text_problems(f"{pid} limitations/missing_information", [*pm.limitations, *pm.missing_information], free)
        problems += _judgment_problems(deps, pid, "market_evidence", pm.market_evidence, base, needs_evidence=True)
    return problems


def fix_market(deps: WorkflowDeps, out: MarketAgentOutput) -> MarketAgentOutput:
    by_id = {p.pathway_id: p for p in out.pathways}
    fixed = []
    for pid in deps.project.pathway_ids:
        pm = by_id.get(pid)
        if pm is None:
            fixed.append(PathwayMarket(pathway_id=pid, applications=(), target_customers=(), competing_materials=(),
                                       qualification_requirements=(), limitations=(),
                                       missing_information=("The agent returned no findings for this pathway.",),
                                       market_evidence=None))
            continue
        base = deterministic.allowed_numbers(deps, pid, include_evidence=False)
        free = deterministic.allowed_numbers(deps, pid)
        update = {name: _repair_findings(deps, pid, getattr(pm, name), base) for name in MARKET_LISTS}
        update["limitations"] = _keep_text(pm.limitations, free)
        update["missing_information"] = _keep_text(pm.missing_information, free) or ("Not reported.",)
        update["market_evidence"] = _repair_judgment(deps, pid, "market_evidence", pm.market_evidence, base, needs_evidence=True)
        fixed.append(pm.model_copy(update=update))
    return out.model_copy(update={"pathways": tuple(fixed)})


# --- Commercialization Agent --------------------------------------------------------------------------------

COMMERCIAL_LISTS = ("processing_requirements", "adoption_barriers")


def _missing_economics(deps: WorkflowDeps, pid: str, listed: tuple[str, ...]) -> list[str]:
    analysis = deps.economics.get(pid) or deterministic.economics(deps.project, pid)
    text = " ".join(listed).lower()
    return [m for m in analysis.missing_inputs if m.lower() not in text]


def check_commercialization(deps: WorkflowDeps, out: CommercializationAgentOutput) -> list[str]:
    expected = list(deps.project.pathway_ids)
    got = [p.pathway_id for p in out.pathways]
    problems = [] if got == expected else [f"pathways must be exactly {expected}, in that order (got {got})"]
    for pc in out.pathways:
        pid = pc.pathway_id
        if pid not in expected:
            continue
        if pid not in deps.compatibility:
            problems.append(f"call check_feedstock_compatibility for {pid} before answering")
        if pid not in deps.economics:
            problems.append(f"call run_scenario_analysis for {pid} before answering")
        base = deterministic.allowed_numbers(deps, pid, include_evidence=False)
        for name in COMMERCIAL_LISTS:
            for finding in getattr(pc, name):
                problems += _finding_problems(deps, pid, name, finding, base)
        if pc.technical_maturity is not None:
            problems += _finding_problems(deps, pid, "technical_maturity", pc.technical_maturity, base)
        if missing := _missing_economics(deps, pid, pc.missing_inputs):
            problems.append(f"{pid} missing_inputs must include every input run_scenario_analysis reported missing: {missing}")
        free = deterministic.allowed_numbers(deps, pid)
        problems += _text_problems(f"{pid} assumptions/uncertainties/missing_inputs",
                                   [*pc.assumptions, *pc.uncertainties, *pc.missing_inputs], free)
        problems += _judgment_problems(deps, pid, "commercialization_feasibility", pc.commercialization_feasibility,
                                       free, needs_evidence=False)
    return problems


def fix_commercialization(deps: WorkflowDeps, out: CommercializationAgentOutput) -> CommercializationAgentOutput:
    by_id = {p.pathway_id: p for p in out.pathways}
    fixed = []
    for pid in deps.project.pathway_ids:
        deps.compatibility.setdefault(pid, deterministic.compatibility(deps.project, pid, deps.scoring))
        deps.economics.setdefault(pid, deterministic.economics(deps.project, pid))
        pc = by_id.get(pid) or PathwayCommercialization(
            pathway_id=pid, processing_requirements=(), technical_maturity=None, adoption_barriers=(), missing_inputs=(),
            assumptions=(), uncertainties=("The agent returned no assessment for this pathway.",),
            commercialization_feasibility=None)
        base = deterministic.allowed_numbers(deps, pid, include_evidence=False)
        free = deterministic.allowed_numbers(deps, pid)
        update = {name: _repair_findings(deps, pid, getattr(pc, name), base) for name in COMMERCIAL_LISTS}
        if pc.technical_maturity is not None:
            update["technical_maturity"] = _repair_finding(deps, pid, pc.technical_maturity, base)
        missing = _keep_text(pc.missing_inputs, free)
        update["missing_inputs"] = missing + tuple(_missing_economics(deps, pid, missing))
        update["assumptions"] = _keep_text(pc.assumptions, free)
        update["uncertainties"] = _keep_text(pc.uncertainties, free) or ("Not reported.",)
        update["commercialization_feasibility"] = _repair_judgment(deps, pid, "commercialization_feasibility",
                                                                   pc.commercialization_feasibility, free, False)
        fixed.append(pc.model_copy(update=update))
    return out.model_copy(update={"pathways": tuple(fixed)})


# --- Decision Agent -----------------------------------------------------------------------------------------


def _expected_order(deps: WorkflowDeps) -> list[tuple[str, int | None]]:
    r = deps.ranking
    return [(o.pathway_id, o.rank) for o in r.ranked] + [(o.pathway_id, None) for o in r.insufficient_data]


def _decision_texts(out: DecisionAgentOutput) -> list[str]:
    texts = [out.summary, *out.ranking_changers, *out.caveats]
    for item in out.shortlist:
        texts += [*item.main_drivers, *item.what_could_change_it]
    for step in out.validation_steps:
        texts += [step.action, step.reason, *step.addresses]
    return texts


def check_decision(deps: WorkflowDeps, out: DecisionAgentOutput) -> list[str]:
    if deps.ranking is None:
        return ["call score_and_rank before answering"]
    problems = []
    got = [(s.pathway_id, s.rank) for s in out.shortlist]
    if got != _expected_order(deps):
        problems.append(f"the shortlist must list every pathway with the rank score_and_rank returned, in its order: "
                        f"{_expected_order(deps)} (got {got})")
    return problems + _text_problems("decision text", _decision_texts(out), deterministic.allowed_numbers(deps))


def _fallback_steps(deps: WorkflowDeps) -> list[ValidationStep]:
    """Validation steps built from the data gaps, used only if the agent's steps had to be removed."""
    steps = [ValidationStep(action=f"Measure {_leaf(p)} for the feedstock.", reason="It is missing from the profile.",
                            addresses=(p,)) for p in deps.project.feedstock.missing_fields()]
    missing = {m for o in (*deps.ranking.ranked, *deps.ranking.insufficient_data) for m in o.completeness.missing_inputs}
    steps += [ValidationStep(action=f"Obtain a sourced value for {m}.", reason="The economics can't be calculated without it.",
                             addresses=(m,)) for m in sorted(missing)]
    return steps


def fix_decision(deps: WorkflowDeps, out: DecisionAgentOutput) -> DecisionAgentOutput:
    deps.ranking = deps.ranking or deterministic.score_and_rank(deps)
    allowed = deterministic.allowed_numbers(deps)
    by_id = {s.pathway_id: s for s in out.shortlist}
    results = {o.pathway_id: o for o in (*deps.ranking.ranked, *deps.ranking.insufficient_data)}
    shortlist = []
    for pid, rank in _expected_order(deps):
        o, item = results[pid], by_id.get(pid)
        drivers = _keep_text(item.main_drivers, allowed) if item else ()
        changers = _keep_text(item.what_could_change_it, allowed) if item else ()
        shortlist.append(ShortlistItem(
            pathway_id=pid, rank=rank,
            main_drivers=drivers or (f"Attractiveness {o.attractiveness} with {o.completeness.assessed_weight:.0%} of the "
                                     "weight assessed (from score_and_rank).",),
            what_could_change_it=changers or (f"Assessing {', '.join(o.completeness.not_assessed) or 'more evidence'}.",)))
    steps = [s for s in out.validation_steps if _clean(" ".join([s.action, s.reason, *s.addresses]), allowed)]
    for extra in _fallback_steps(deps):
        if len(steps) >= 3:
            break
        steps.append(extra)
    summary = out.summary if _clean(out.summary, allowed) else \
        "Summary removed by the guard because it contained unsupported numbers or a prohibited claim; see the shortlist."
    return out.model_copy(update={
        "shortlist": tuple(shortlist), "validation_steps": tuple(steps[:5]),
        "ranking_changers": _keep_text(out.ranking_changers, allowed) or ("More evidence on the criteria not assessed.",),
        "caveats": _keep_text(out.caveats, allowed), "summary": summary,
    })


# --- Wiring -------------------------------------------------------------------------------------------------


def make_validator(check: Callable, fix: Callable):
    """An output validator: ask the agent to fix problems, then repair the answer in code and record it."""

    def validate(ctx: RunContext[WorkflowDeps], output):
        problems = check(ctx.deps, output)
        if not problems:
            return output
        if ctx.retry < ctx.max_retries:
            ctx.deps.trace.record_guard(ctx.deps.agent, "retry_requested", problems)
            raise ModelRetry("Your answer failed these checks. Fix them and answer again:\n- " + "\n- ".join(problems))
        fixed = fix(ctx.deps, output)
        if remaining := check(ctx.deps, fixed):
            raise RuntimeError(f"guard could not repair the {ctx.deps.agent} answer: {remaining}")
        ctx.deps.trace.record_guard(ctx.deps.agent, "fixed_by_code", problems)
        return fixed

    return validate


GUARDS = {
    "feedstock": (check_feedstock, fix_feedstock),
    "market": (check_market, fix_market),
    "commercialization": (check_commercialization, fix_commercialization),
    "decision": (check_decision, fix_decision),
}
