"""Opportunity scoring on a transparent 1-5 scale.

Five criteria, each scored 1-5 against the rubric in data/scoring_config.json, combined with configurable
weights. Every result shows each criterion's score, what that score means, its weight, and its weighted
contribution (weight x score).

Three things are kept apart:
- attractiveness: the weighted average score of the criteria that were assessed (1-5)
- data completeness: the share of the total weight that was assessed, and what is missing
- evidence quality: the quality labels of the evidence records behind the scores

A criterion without an assessment is 'not assessed'. It never counts as a 1: it lowers completeness, widens the
attractiveness range (the total if every missing criterion scored 1, or 5), and an opportunity below the minimum
completeness is listed as 'insufficient data' instead of being ranked last.

Three criteria have deterministic rules here (feedstock compatibility, technical readiness, indicative
economics). Market evidence and commercialization feasibility are judgments: an analyst (later, an agent)
supplies the score with a rationale and the evidence it rests on. No model calls.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from pydantic import Field, model_validator

from backend.calc import SCENARIOS, ScenarioAnalysis
from backend.evidence import QUALITY_LABELS, EvidenceLibrary, EvidenceQuality, TechnicalRequirement
from backend.feedstock import FeedstockProfile
from backend.models import Frozen

Criterion = Literal[
    "feedstock_compatibility", "technical_readiness", "market_evidence", "indicative_economics",
    "commercialization_feasibility",
]
CRITERIA: tuple[Criterion, ...] = (
    "feedstock_compatibility", "technical_readiness", "market_evidence", "indicative_economics",
    "commercialization_feasibility",
)
SCALE = (1, 2, 3, 4, 5)


# --- Configuration ------------------------------------------------------------------------------


class CriterionRubric(Frozen):
    label: str
    question: str
    levels: dict[int, str]  # what each score from 1 to 5 means
    how_scored: str

    @model_validator(mode="after")
    def _check(self):
        if set(self.levels) != set(SCALE):
            raise ValueError(f"rubric for {self.label!r} must describe every score from 1 to 5")
        return self


class EconomicsBands(Frozen):
    """Upper bounds (inclusive) of contribution per tonne of usable feedstock for scores 1 to 4; above the last is 5."""

    currency: str
    upper_bounds: tuple[float, float, float, float]

    @model_validator(mode="after")
    def _check(self):
        if list(self.upper_bounds) != sorted(set(self.upper_bounds)):
            raise ValueError("economics band bounds must be strictly increasing")
        return self


class ScoringConfig(Frozen):
    weights: dict[Criterion, float]
    min_completeness: float = Field(ge=0, le=1)  # share of total weight that must be assessed to be ranked
    rubric: dict[Criterion, CriterionRubric]
    compatibility_gap_bands: tuple[float, float, float]  # largest relative gap allowed for scores 4, 3, and 2
    trl_to_score: dict[int, int]
    economics_bands: EconomicsBands
    notes: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check(self):
        if set(self.weights) != set(CRITERIA):
            raise ValueError(f"weights must cover exactly {list(CRITERIA)}")
        if any(w < 0 for w in self.weights.values()):
            raise ValueError("weights cannot be negative")
        if abs(sum(self.weights.values()) - 1) > 1e-9:
            raise ValueError(f"weights must sum to 1 (got {sum(self.weights.values()):g})")
        if set(self.rubric) != set(CRITERIA):
            raise ValueError(f"the rubric must cover exactly {list(CRITERIA)}")
        b = self.compatibility_gap_bands
        if not 0 < b[0] < b[1] < b[2]:
            raise ValueError("compatibility gap bands must be positive and strictly increasing")
        if set(self.trl_to_score) != set(range(1, 10)) or not set(self.trl_to_score.values()) <= set(SCALE):
            raise ValueError("trl_to_score must map every TRL from 1 to 9 to a score from 1 to 5")
        mapped = [self.trl_to_score[t] for t in range(1, 10)]
        if mapped != sorted(mapped):
            raise ValueError("a higher TRL can't map to a lower score")
        return self


def with_weights(config: ScoringConfig, weights: dict[Criterion, float]) -> ScoringConfig:
    """A copy of the config with new weights, validated (all five criteria, none negative, summing to 1)."""
    return ScoringConfig.model_validate({**config.model_dump(), "weights": weights})


# --- Assessments ----------------------------------------------------------------------------------


class Assessment(Frozen):
    """One criterion's score (or the reason it couldn't be scored), with its rationale and evidence."""

    criterion: Criterion
    score: int | None = Field(default=None, ge=1, le=5)  # None = not assessed
    method: Literal["rule", "analyst", "none"]
    rationale: str
    evidence_ids: tuple[str, ...] = ()
    inputs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _check(self):
        if not self.rationale.strip():
            raise ValueError(f"{self.criterion}: an assessment needs a rationale (or the reason it's missing)")
        if (self.score is None) != (self.method == "none"):
            raise ValueError(f"{self.criterion}: use method 'none' exactly when there is no score")
        return self


def not_assessed(criterion: Criterion, reason: str) -> Assessment:
    return Assessment(criterion=criterion, score=None, method="none", rationale=reason)


def analyst_assessment(criterion: Criterion, score: int, rationale: str, evidence_ids: tuple[str, ...] = ()) -> Assessment:
    return Assessment(criterion=criterion, score=score, method="analyst", rationale=rationale, evidence_ids=evidence_ids)


BAND_PRECISION = 9  # decimals kept before comparing with a band edge, so float noise can't cross it


def _relative_gap(value: float, req: TechnicalRequirement) -> float:
    """Rounded so a gap that is exactly on a band edge (e.g. 0.55 vs a 0.5 maximum = 10%) stays on it; in raw
    floating point (0.55 - 0.5) / 0.5 is 0.10000000000000009."""
    if req.max is not None and value > req.max:
        return round((value - req.max) / req.max, BAND_PRECISION)
    if req.min is not None and value < req.min:
        return round((req.min - value) / req.min, BAND_PRECISION)
    return 0.0


def assess_feedstock_compatibility(feedstock: FeedstockProfile, requirements: list[tuple[str, TechnicalRequirement]],
                                   config: ScoringConfig) -> Assessment:
    """Score from the largest relative gap between the feedstock and the numeric requirements in the evidence.
    The relative gap is how far outside a limit the feedstock is, as a share of that limit (0 = within it)."""
    criterion: Criterion = "feedstock_compatibility"
    numeric = [(rid, r) for rid, r in requirements if r.property and (r.min is not None or r.max is not None)]
    if not numeric:
        return not_assessed(criterion, "The evidence library has no numeric requirements for this pathway to check against.")
    checked, unchecked = [], []
    for rid, req in numeric:
        value = feedstock.property_value(req.property)
        if value is None:
            unchecked.append((rid, req))
        else:
            checked.append((rid, req, value, _relative_gap(value, req)))
    if not checked:
        props = sorted({req.property for _, req in unchecked})
        return not_assessed(criterion, f"Requirements exist for {', '.join(props)}, but the feedstock profile doesn't report them.")

    worst = max(gap for *_, gap in checked)
    b4, b3, b2 = config.compatibility_gap_bands
    score = 5 if worst == 0 else 4 if worst <= b4 else 3 if worst <= b3 else 2 if worst <= b2 else 1
    lines = []
    for rid, req, value, gap in checked:
        limit = " and ".join(x for x in (f"min {req.min:g}" if req.min is not None else "",
                                         f"max {req.max:g}" if req.max is not None else "") if x)
        verdict = "met" if gap == 0 else f"outside by {gap:.0%} of the limit"
        scope = f", for {req.applies_to}" if req.applies_to else ""
        lines.append(f"{req.property} = {value:g} vs {limit} ({rid}{scope}): {verdict}")
    lines += [f"{req.property}: not checked, not reported in the feedstock profile ({rid})" for rid, req in unchecked]
    rationale = f"Largest relative gap is {worst:.0%} across {len(checked)} checked requirement(s)."
    if unchecked:
        rationale += f" {len(unchecked)} more could not be checked because the feedstock data is missing."
    products = sorted({req.applies_to for _, req, *_ in checked if req.applies_to})
    if products:
        rationale += (f" The checked requirements apply to: {', '.join(products)}; other products in this pathway "
                      "may have different requirements.")
    return Assessment(criterion=criterion, score=score, method="rule", rationale=rationale,
                      evidence_ids=tuple(dict.fromkeys(rid for rid, *_ in checked)), inputs=tuple(lines))


def assess_technical_readiness(trl: int | None, evidence_ids: tuple[str, ...], config: ScoringConfig,
                               basis: str = "") -> Assessment:
    """Score from the technology readiness level (TRL 1-9) via the configured mapping."""
    criterion: Criterion = "technical_readiness"
    if trl is None:
        return not_assessed(criterion, "No TRL supplied.")
    if isinstance(trl, bool) or not isinstance(trl, int) or not 1 <= trl <= 9:
        raise ValueError(f"TRL must be a whole number from 1 to 9 (got {trl!r})")
    score = config.trl_to_score[trl]
    rationale = f"TRL {trl} maps to {score}." + (f" {basis}" if basis else "")
    return Assessment(criterion=criterion, score=score, method="rule", rationale=rationale,
                      evidence_ids=evidence_ids, inputs=(f"TRL = {trl}",))


def _economics_band(value: float, bands: EconomicsBands) -> int:
    value = round(value, BAND_PRECISION)
    for score, bound in enumerate(bands.upper_bounds, start=1):
        if value <= bound:
            return score
    return 5


def assess_indicative_economics(analysis: ScenarioAnalysis, config: ScoringConfig) -> Assessment:
    """Score from the base-scenario gross contribution per tonne of usable feedstock."""
    criterion: Criterion = "indicative_economics"
    bands = config.economics_bands
    steps = {s: analysis.scenarios[s].steps["contribution_per_t_feedstock"] for s in SCENARIOS}
    base = steps["base"]
    if base.status != "calculated":
        if analysis.missing_inputs:
            return not_assessed(criterion, "Gross contribution per tonne could not be calculated. Missing inputs: "
                                           f"{', '.join(analysis.missing_inputs)}.")
        return not_assessed(criterion, f"Gross contribution per tonne could not be calculated. {base.reason}")
    currency = base.unit.split("/")[0]
    if currency != bands.currency:
        return not_assessed(criterion, f"The score bands are in {bands.currency} but the contribution is in {currency}; "
                                       "no exchange rate is applied.")
    scores = {s: _economics_band(step.value, bands) for s, step in steps.items() if step.status == "calculated"}
    inputs = tuple(f"{s}: {step.value:,.2f} {step.unit} (band score {scores[s]})"
                   for s, step in steps.items() if step.status == "calculated")
    evidence = tuple(dict.fromkeys(i for line in analysis.assumptions for i in line.evidence_ids))
    spread = ", ".join(f"{s} {scores[s]}" for s in ("conservative", "optimistic") if s in scores)
    rationale = (f"Base-scenario gross contribution is {base.value:,.2f} {base.unit}, which scores {scores['base']}"
                 f"{f' ({spread})' if spread else ''}. Excludes capital costs, fixed costs, and the feedstock's value "
                 "in its current use.")
    return Assessment(criterion=criterion, score=scores["base"], method="rule", rationale=rationale,
                      evidence_ids=evidence, inputs=inputs)


# --- Results ---------------------------------------------------------------------------------------


class CriterionResult(Frozen):
    criterion: Criterion
    label: str
    weight: float
    status: Literal["assessed", "not_assessed"]
    score: int | None
    meaning: str  # the rubric's text for this score
    weighted_contribution: float | None  # weight x score
    method: Literal["rule", "analyst", "none"]
    rationale: str
    evidence_ids: tuple[str, ...]
    inputs: tuple[str, ...]


class EvidenceSummary(Frozen):
    cited_records: tuple[str, ...]
    by_quality: dict[EvidenceQuality, int]
    strongest: EvidenceQuality | None
    criteria_without_evidence: tuple[Criterion, ...]  # assessed, but no evidence cited


class Completeness(Frozen):
    assessed_weight: float  # share of the total weight that was assessed, 0-1
    assessed: tuple[Criterion, ...]
    not_assessed: tuple[Criterion, ...]
    missing_inputs: tuple[str, ...]


class OpportunityResult(Frozen):
    pathway_id: str
    name: str
    criteria: tuple[CriterionResult, ...]
    attractiveness: float | None  # 1-5 weighted average of the assessed criteria; None if none were assessed
    attractiveness_range: tuple[float, float]  # if every unassessed criterion scored 1, or 5
    completeness: Completeness
    evidence: EvidenceSummary
    status: Literal["ranked", "insufficient_data"]
    rank: int | None = None


class Ranking(Frozen):
    weights: dict[Criterion, float]
    min_completeness: float
    ranked: tuple[OpportunityResult, ...]  # best first
    insufficient_data: tuple[OpportunityResult, ...]


def _round2(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _evidence_summary(assessments: dict[Criterion, Assessment], library: EvidenceLibrary | None) -> EvidenceSummary:
    cited = tuple(dict.fromkeys(i for a in assessments.values() for i in a.evidence_ids))
    counts = {label: 0 for label in QUALITY_LABELS}
    if library is not None:
        for rid in cited:
            counts[library.record(rid).quality] += 1  # KeyError for an id that isn't in the library
    strongest = next((label for label in QUALITY_LABELS if counts[label]), None)
    no_evidence = tuple(c for c, a in assessments.items() if a.score is not None and not a.evidence_ids)
    return EvidenceSummary(cited_records=cited, by_quality=counts, strongest=strongest, criteria_without_evidence=no_evidence)


def score_opportunity(pathway_id: str, name: str, assessments: list[Assessment], config: ScoringConfig,
                      library: EvidenceLibrary | None = None, missing_inputs: tuple[str, ...] = ()) -> OpportunityResult:
    """Combine one opportunity's assessments. A criterion without an assessment is recorded as not assessed."""
    by_criterion: dict[Criterion, Assessment] = {}
    for a in assessments:
        if a.criterion in by_criterion:
            raise ValueError(f"{pathway_id}: {a.criterion} was assessed twice")
        by_criterion[a.criterion] = a
    for c in CRITERIA:
        by_criterion.setdefault(c, not_assessed(c, "No assessment supplied."))

    results = []
    for c in CRITERIA:
        a, w, rubric = by_criterion[c], config.weights[c], config.rubric[c]
        results.append(CriterionResult(
            criterion=c, label=rubric.label, weight=w, status="not_assessed" if a.score is None else "assessed",
            score=a.score, meaning="Not assessed" if a.score is None else rubric.levels[a.score],
            weighted_contribution=None if a.score is None else round(w * a.score, 4),
            method=a.method, rationale=a.rationale, evidence_ids=a.evidence_ids, inputs=a.inputs,
        ))

    # Exact decimal arithmetic, so 1.90 / 0.80 = 2.375 reports as 2.38 (in floats it is 2.3749999... and rounds to 2.37).
    assessed = [r for r in results if r.status == "assessed"]
    weight = sum((Decimal(str(r.weight)) for r in assessed), Decimal(0))
    partial = sum((Decimal(str(r.weighted_contribution)) for r in assessed), Decimal(0))
    missing_weight = Decimal(1) - weight
    attractiveness = _round2(partial / weight) if weight > 0 else None
    enough = attractiveness is not None and float(weight) >= config.min_completeness - 1e-9
    return OpportunityResult(
        pathway_id=pathway_id, name=name, criteria=tuple(results), attractiveness=attractiveness,
        attractiveness_range=(_round2(partial + missing_weight * 1), _round2(partial + missing_weight * 5)),
        completeness=Completeness(
            assessed_weight=float(weight),
            assessed=tuple(r.criterion for r in assessed),
            not_assessed=tuple(r.criterion for r in results if r.status == "not_assessed"),
            missing_inputs=tuple(missing_inputs),
        ),
        evidence=_evidence_summary(by_criterion, library),
        status="ranked" if enough else "insufficient_data",
    )


def rank(opportunities: list[OpportunityResult], config: ScoringConfig) -> Ranking:
    """Rank opportunities with enough data by attractiveness (ties: more complete first, then by id). The rest are
    listed separately as insufficient data, never ranked below the others."""
    ids = [o.pathway_id for o in opportunities]
    if len(ids) != len(set(ids)):
        raise ValueError("each pathway can appear only once in a ranking")
    ranked = sorted((o for o in opportunities if o.status == "ranked"),
                    key=lambda o: (-o.attractiveness, -o.completeness.assessed_weight, o.pathway_id))
    return Ranking(
        weights=dict(config.weights),
        min_completeness=config.min_completeness,
        ranked=tuple(o.model_copy(update={"rank": i}) for i, o in enumerate(ranked, start=1)),
        insufficient_data=tuple(sorted((o for o in opportunities if o.status != "ranked"), key=lambda o: o.pathway_id)),
    )
