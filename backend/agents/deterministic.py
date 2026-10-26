"""The deterministic facts behind the agents. Plain Python on validated data, no model calls.

The tools hand these facts to the agents, the guards check agent answers against them, and the workflow puts
them in the final assessment. If an agent skips a tool, the workflow computes the same facts here, so no result
depends on the model having called a tool correctly.
"""

import json

from backend import calc, scoring, units
from backend.agents.deps import WorkflowDeps
from backend.agents.refs import number_values, record_ids, ref_problems, resolve
from backend.calc import ScenarioAnalysis
from backend.feedstock import DRY_MATTER_TOLERANCE, PROPERTY_UNITS
from backend.project import Project
from backend.scoring import Assessment, Ranking, ScoringConfig, analyst_assessment, not_assessed


def _quantity(q) -> dict:
    return {"value": q.value, "unit": q.unit, "basis": q.basis, "low": q.low, "high": q.high, "method": q.method}


def normalized_feedstock(project: Project) -> dict:
    """The feedstock in canonical units: t/yr for mass, a fraction for moisture."""
    f = project.feedstock
    wet, moisture = f.annual_wet_quantity, f.moisture_pct
    dry = calc.dry_mass(wet.value, wet.unit, moisture.value, moisture.unit)
    lignin = f.composition.lignin_pct.value
    return {
        "feedstock_id": f.id,
        "is_fictional": f.data_status != "measured",
        "wet_mass_t_per_yr": units.mass_flow_t_per_yr(wet.value, wet.unit, "wet feedstock mass"),
        "moisture_fraction": units.moisture_fraction(moisture.value, moisture.unit),
        "dry_mass_t_per_yr": round(dry, 6),
        "dry_lignin_t_per_yr": None if lignin is None else round(dry * lignin / 100, 6),
        "composition": {name: _quantity(getattr(f.composition, name)) for name in PROPERTY_UNITS},
        "other_composition": {name: _quantity(q) for name, q in f.composition.other.items()},
    }


def feedstock_checks(project: Project) -> dict:
    """The validation report the Feedstock Agent's validate_feedstock tool returns."""
    f = project.feedstock
    norm = normalized_feedstock(project)
    computed, recorded = norm["dry_mass_t_per_yr"], f.dry_matter_t_per_year
    gap = abs(recorded - computed) / computed if computed else 0.0
    parts = [f.composition.lignin_pct.value, f.composition.ash_pct.value, f.composition.carbohydrates_pct.value]
    total = sum(parts) if all(v is not None for v in parts) else None
    checks = [
        {"check": "dry matter balance", "passed": gap <= DRY_MATTER_TOLERANCE,
         "detail": f"recorded dry matter {recorded:,.0f} t/yr; wet quantity x (1 - moisture) = {computed:,.0f} t/yr"},
        {"check": "composition total", "passed": total is None or total <= 101,
         "detail": "not checked: a component is missing" if total is None
         else f"lignin + ash + carbohydrates = {total:g}% of dry matter"},
        {"check": "missing figures have data gaps", "passed": True,
         "detail": f"{len(f.missing_fields())} missing figure(s), each with a data-gap entry"},
    ]
    by_status: dict[str, list[str]] = {"operating": [], "planned": [], "not_available": []}
    for asset in f.infrastructure:
        by_status[asset.status].append(f"{asset.name} ({asset.kind})")
    return {
        "schema_valid": True,
        "checks": checks,
        "inconsistencies": [c["detail"] for c in checks if not c["passed"]],
        "missing_fields": f.missing_fields(),
        "data_gaps": [g.model_dump() for g in f.data_gaps],
        "data_status": f.data_status,
        "disclaimer": f.disclaimer,
        "infrastructure": by_status,
        "current_use": f.current_use.model_dump(),
        "geographic_market": f.geographic_market.model_dump(),
        "ranges": {path: {"low": q.low, "high": q.high, "unit": q.unit}
                   for path, q in f.quantities() if q.low is not None or q.high is not None},
    }


def compatibility(project: Project, pathway_id: str, config: ScoringConfig) -> Assessment:
    return scoring.assess_feedstock_compatibility(project.feedstock, project.evidence.requirements_for(pathway_id), config)


def economics(project: Project, pathway_id: str) -> ScenarioAnalysis:
    return calc.analyse(project.pathway_inputs(pathway_id))


def readiness(project: Project, pathway_id: str, trl: int, refs: list[str], config: ScoringConfig) -> Assessment:
    """A TRL is accepted only when a cited, supported claim for this pathway states it. Raises ValueError otherwise."""
    problems = ref_problems(project, refs, pathway_id)
    if not refs:
        problems.append("cite at least one evidence claim that states the TRL")
    if any(ref.startswith("feedstock:") for ref in refs):
        problems.append("a TRL must come from an evidence record, not the feedstock profile")
    if not problems:
        texts = [resolve(project, ref).text for ref in refs]
        if not any("TRL" in t and float(trl) in number_values(t) for t in texts):
            problems.append(f"none of the cited evidence states TRL {trl}")
    if problems:
        raise ValueError("; ".join(problems))
    return scoring.assess_technical_readiness(trl, record_ids(refs), config, basis=f"Stated in {', '.join(refs)}.")


def _judgment_assessment(criterion, judgment, missing_reason: str) -> Assessment:
    if judgment is None:
        return not_assessed(criterion, missing_reason)
    return analyst_assessment(criterion, judgment.score, judgment.rationale, record_ids(judgment.evidence))


def assessments_for(deps: WorkflowDeps, pathway_id: str) -> tuple[list[Assessment], ScenarioAnalysis]:
    """The five criterion assessments for one pathway, from the tools' results and the agents' judgments."""
    analysis = deps.economics.get(pathway_id) or economics(deps.project, pathway_id)
    market = next((p for p in deps.market_output.pathways if p.pathway_id == pathway_id), None) if deps.market_output else None
    commercial = (next((p for p in deps.commercialization_output.pathways if p.pathway_id == pathway_id), None)
                  if deps.commercialization_output else None)
    assessments = [
        deps.compatibility.get(pathway_id) or compatibility(deps.project, pathway_id, deps.scoring),
        deps.readiness.get(pathway_id) or not_assessed("technical_readiness", "No TRL was confirmed from the evidence."),
        _judgment_assessment("market_evidence", market.market_evidence if market else None,
                             "The Market Intelligence Agent did not score market evidence for this pathway."),
        scoring.assess_indicative_economics(analysis, deps.scoring),
        _judgment_assessment("commercialization_feasibility",
                             commercial.commercialization_feasibility if commercial else None,
                             "The Commercialization Agent did not score feasibility for this pathway."),
    ]
    return assessments, analysis


def score_and_rank(deps: WorkflowDeps) -> Ranking:
    project = deps.project
    results = []
    for pid in project.pathway_ids:
        assessments, analysis = assessments_for(deps, pid)
        results.append(scoring.score_opportunity(pid, project.evidence.pathway(pid).name, assessments, deps.scoring,
                                                 project.evidence, missing_inputs=analysis.missing_inputs))
    return scoring.rank(results, deps.scoring)


def allowed_numbers(deps: WorkflowDeps, pathway_id: str | None = None, include_evidence: bool = True) -> set[float]:
    """Numbers an agent may repeat: from the feedstock, the deterministic results, the scoring settings, and (for
    free text) the pathway's evidence."""
    project = deps.project
    blobs: list = [normalized_feedstock(project), feedstock_checks(project), deps.scoring.model_dump()]
    for pid in [pathway_id] if pathway_id else project.pathway_ids:
        blobs += [economics(project, pid).model_dump(), compatibility(project, pid, deps.scoring).model_dump()]
        if pid in deps.readiness:
            blobs.append(deps.readiness[pid].model_dump())
        if include_evidence:
            blobs += [r.model_dump() for r in project.evidence.records_for(pid)]
    if deps.ranking is not None:
        blobs.append(deps.ranking.model_dump())
    values: set[float] = set()
    for blob in blobs:
        values |= number_values(json.dumps(blob, default=str))
    return values
