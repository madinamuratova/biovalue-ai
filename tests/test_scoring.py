"""1-5 scoring in backend/scoring.py: the rubric, weighted contributions, missing criteria, rules, and ranking.

With the configured weights (0.25, 0.20, 0.20, 0.20, 0.15), scores 5, 4, 3, 2, 1 contribute
1.25 + 0.80 + 0.60 + 0.40 + 0.15 = 3.20.
"""

import pytest
from pydantic import ValidationError

from backend import calc, scoring
from backend.evidence import TechnicalRequirement
from backend.scoring import CRITERIA, Assessment, analyst_assessment, not_assessed
from tests.conftest import make_feedstock, missing
from tests.test_calc import costs, inp, make_inputs
from tests.test_evidence import UNVERIFIED, library, pathway, record


def full(scores: dict[str, int]) -> list[Assessment]:
    return [analyst_assessment(c, s, f"toy rationale for {c}") for c, s in scores.items()]


FIVE_TO_ONE = dict(zip(CRITERIA, (5, 4, 3, 2, 1)))


def criteria_of(result) -> dict:
    return {c.criterion: c for c in result.criteria}


# --- Configuration ------------------------------------------------------------------------------


def test_configured_weights_match_the_brief(config):
    assert config.weights == {"feedstock_compatibility": 0.25, "technical_readiness": 0.20, "market_evidence": 0.20,
                              "indicative_economics": 0.20, "commercialization_feasibility": 0.15}


def test_every_score_on_every_criterion_has_a_meaning(config):
    for rubric in config.rubric.values():
        assert sorted(rubric.levels) == [1, 2, 3, 4, 5]
        assert all(text.strip() for text in rubric.levels.values())
        assert rubric.question and rubric.how_scored


@pytest.mark.parametrize("weights", [
    {"feedstock_compatibility": 1.0},  # missing criteria
    {**dict.fromkeys(CRITERIA, 0.2), "market_evidence": 0.3},  # sums to 1.1
    {**dict.fromkeys(CRITERIA, 0.2), "risk": 0.0},  # unknown criterion
    {"feedstock_compatibility": 1.2, "technical_readiness": -0.2, "market_evidence": 0, "indicative_economics": 0,
     "commercialization_feasibility": 0},  # negative weight
])
def test_bad_weights_are_rejected(config, weights):
    with pytest.raises(ValidationError):
        scoring.with_weights(config, weights)


# --- Weighted contributions --------------------------------------------------------------------------


def test_weighted_contribution_of_every_criterion(config):
    result = scoring.score_opportunity("p", "P", full(FIVE_TO_ONE), config)
    contributions = {c.criterion: c.weighted_contribution for c in result.criteria}
    assert contributions == pytest.approx({"feedstock_compatibility": 1.25, "technical_readiness": 0.80,
                                           "market_evidence": 0.60, "indicative_economics": 0.40,
                                           "commercialization_feasibility": 0.15})
    assert result.attractiveness == 3.2
    assert result.attractiveness_range == (3.2, 3.2)
    assert result.completeness.assessed_weight == 1.0


def test_each_score_shows_its_rubric_meaning(config):
    c = criteria_of(scoring.score_opportunity("p", "P", full(FIVE_TO_ONE), config))
    assert c["technical_readiness"].meaning == config.rubric["technical_readiness"].levels[4]
    assert c["commercialization_feasibility"].meaning.startswith("No identifiable route")


def test_exact_halves_round_up(config):
    """0.25x1 + 0.20x3 + 0.20x3 + 0.15x3 = 1.90 over 0.80 of the weight = 2.375 exactly, which must report 2.38."""
    scores = {"feedstock_compatibility": 1, "technical_readiness": 3, "market_evidence": 3,
              "commercialization_feasibility": 3}
    assert scoring.score_opportunity("p", "P", full(scores), config).attractiveness == 2.38


@pytest.mark.parametrize("score, expected", [(1, 1.0), (5, 5.0)])
def test_uniform_scores_at_the_ends_of_the_scale(config, score, expected):
    result = scoring.score_opportunity("p", "P", full(dict.fromkeys(CRITERIA, score)), config)
    assert result.attractiveness == expected


# --- Missing criteria are not scored as poor -----------------------------------------------------------


def test_missing_criteria_lower_completeness_not_attractiveness(config):
    partial = {c: s for c, s in FIVE_TO_ONE.items() if c not in ("market_evidence", "indicative_economics")}
    result = scoring.score_opportunity("p", "P", full(partial), config)
    c = criteria_of(result)
    assert c["market_evidence"].status == "not_assessed"
    assert c["market_evidence"].score is None and c["market_evidence"].weighted_contribution is None
    assert c["market_evidence"].meaning == "Not assessed"
    assert c["market_evidence"].rationale == "No assessment supplied."
    assert result.completeness.assessed_weight == pytest.approx(0.6)
    assert result.completeness.not_assessed == ("market_evidence", "indicative_economics")
    # (1.25 + 0.80 + 0.15) / 0.6 = 3.67; range: 2.20 + 0.4 x 1 = 2.6 up to 2.20 + 0.4 x 5 = 4.2
    assert result.attractiveness == 3.67
    assert result.attractiveness_range == (2.6, 4.2)


def test_a_missing_criterion_does_not_drag_the_score_down(config):
    complete = scoring.score_opportunity("a", "A", full(dict.fromkeys(CRITERIA, 4)), config)
    gap = scoring.score_opportunity("b", "B", full({c: 4 for c in CRITERIA if c != "market_evidence"}), config)
    assert complete.attractiveness == gap.attractiveness == 4.0
    assert gap.completeness.assessed_weight < complete.completeness.assessed_weight


def test_exactly_minimum_completeness_is_ranked(config):
    at_minimum = {c: 3 for c in ("feedstock_compatibility", "technical_readiness", "commercialization_feasibility")}
    assert scoring.score_opportunity("p", "P", full(at_minimum), config).status == "ranked"  # 0.25 + 0.20 + 0.15 = 0.60


def test_below_minimum_completeness_is_not_ranked(config):
    below = {c: 5 for c in ("feedstock_compatibility", "technical_readiness")}  # 0.45 of the weight
    result = scoring.score_opportunity("p", "P", full(below), config)
    assert result.status == "insufficient_data"
    assert result.attractiveness == 5.0  # still shown, just not ranked


def test_nothing_assessed(config):
    result = scoring.score_opportunity("p", "P", [], config)
    assert result.attractiveness is None
    assert result.attractiveness_range == (1.0, 5.0)
    assert result.status == "insufficient_data"


def test_missing_inputs_are_carried_into_completeness(config):
    result = scoring.score_opportunity("p", "P", [], config, missing_inputs=("product price",))
    assert result.completeness.missing_inputs == ("product price",)


# --- Assessment validation --------------------------------------------------------------------------


@pytest.mark.parametrize("score", [0, 6, -1])
def test_scores_stay_on_the_1_to_5_scale(score):
    with pytest.raises(ValidationError):
        analyst_assessment("market_evidence", score, "r")


def test_assessment_rules():
    with pytest.raises(ValidationError, match="needs a rationale"):
        analyst_assessment("market_evidence", 3, " ")
    with pytest.raises(ValidationError, match="method 'none'"):
        Assessment(criterion="market_evidence", score=3, method="none", rationale="r")
    with pytest.raises(ValidationError, match="method 'none'"):
        Assessment(criterion="market_evidence", score=None, method="analyst", rationale="r")


def test_a_criterion_cannot_be_assessed_twice(config):
    with pytest.raises(ValueError, match="assessed twice"):
        scoring.score_opportunity("p", "P", full({"market_evidence": 3}) + full({"market_evidence": 4}), config)


# --- Evidence quality, kept apart from attractiveness ------------------------------------------------


LIB = library(
    pathways=(pathway(),),
    records=(record(), record(id="EV-PF-02", source_type="trade_press", quality="low"),
             record(id="EV-PF-03", **UNVERIFIED)),
)


def test_evidence_summary_counts_quality_labels(config):
    assessments = [analyst_assessment("market_evidence", 4, "r", ("EV-PF-01", "EV-PF-02")),
                   analyst_assessment("technical_readiness", 5, "r", ("EV-PF-03",)),
                   analyst_assessment("commercialization_feasibility", 3, "r")]
    ev = scoring.score_opportunity("p", "P", assessments, config, library=LIB).evidence
    assert ev.cited_records == ("EV-PF-01", "EV-PF-02", "EV-PF-03")
    assert ev.by_quality == {"high": 1, "moderate": 0, "low": 1, "unverified": 1}
    assert ev.strongest == "high"
    assert ev.criteria_without_evidence == ("commercialization_feasibility",)


def test_evidence_quality_does_not_change_attractiveness(config):
    strong = scoring.score_opportunity("p", "P", [analyst_assessment("market_evidence", 4, "r", ("EV-PF-01",))], config, LIB)
    weak = scoring.score_opportunity("p", "P", [analyst_assessment("market_evidence", 4, "r", ("EV-PF-03",))], config, LIB)
    assert strong.attractiveness == weak.attractiveness
    assert strong.evidence.strongest == "high" and weak.evidence.strongest == "unverified"


def test_unknown_evidence_id_is_an_error(config):
    with pytest.raises(KeyError):
        scoring.score_opportunity("p", "P", [analyst_assessment("market_evidence", 4, "r", ("EV-PF-99",))], config, LIB)


# --- Rule: feedstock compatibility --------------------------------------------------------------------


def req(prop="ash_pct", max=None, min=None, rid="EV-PF-01") -> tuple[str, TechnicalRequirement]:
    return rid, TechnicalRequirement(parameter=prop, requirement="toy", property=prop, max=max, min=min,
                                     status="supported", support="toy")


@pytest.mark.parametrize("ash_max, expected", [
    (2.0, 5),     # ash 1.0 is within the limit
    (0.95, 4),    # 5% over
    (1 / 1.1, 4),  # exactly 10% over (boundary)
    (0.8, 3),     # 25% over
    (1 / 1.5, 3),  # exactly 50% over (boundary)
    (0.6, 2),     # 67% over
    (0.5, 2),     # exactly 100% over (boundary)
    (0.25, 1),    # 300% over
])
def test_compatibility_bands(config, ash_max, expected):
    a = scoring.assess_feedstock_compatibility(make_feedstock(), [req(max=ash_max)], config)
    assert a.score == expected and a.method == "rule"


@pytest.mark.parametrize("ash, ash_max, expected", [(0.55, 0.5, 4), (0.75, 0.5, 3), (0.3, 0.2, 3), (0.2, 0.1, 2)])
def test_band_edges_survive_floating_point(config, ash, ash_max, expected):
    """(0.55 - 0.5) / 0.5 is 0.10000000000000009 in floating point; it must still count as exactly 10%."""
    a = scoring.assess_feedstock_compatibility(make_feedstock(props={"ash_pct": ash}), [req(max=ash_max)], config)
    assert a.score == expected


def test_product_specific_requirements_are_labelled(config):
    rid, r = req(max=2.0)
    labelled = r.model_copy(update={"applies_to": "carbon fiber precursor"})
    a = scoring.assess_feedstock_compatibility(make_feedstock(), [(rid, labelled)], config)
    assert a.inputs[0] == "ash_pct = 1 vs max 2 (EV-PF-01, for carbon fiber precursor): met"
    assert "apply to: carbon fiber precursor" in a.rationale


def test_compatibility_uses_the_largest_gap_and_minimums(config):
    reqs = [req(max=2.0), req("lignin_pct", min=97)]  # lignin 95 vs min 97: 2% short
    a = scoring.assess_feedstock_compatibility(make_feedstock(), reqs, config)
    assert a.score == 4
    assert "lignin_pct = 95 vs min 97 (EV-PF-01): outside by 2% of the limit" in a.inputs


def test_unchecked_requirements_are_listed_not_failed(config):
    f = make_feedstock(props={"mw_g_per_mol": None}, data_gaps=(missing("composition.mw_g_per_mol"),))
    a = scoring.assess_feedstock_compatibility(f, [req(max=2.0), req("mw_g_per_mol", max=3000, rid="EV-PF-02")], config)
    assert a.score == 5  # the one requirement that could be checked is met
    assert "1 more could not be checked" in a.rationale
    assert "mw_g_per_mol: not checked, not reported in the feedstock profile (EV-PF-02)" in a.inputs
    assert a.evidence_ids == ("EV-PF-01",)


def test_compatibility_not_assessed_without_checkable_requirements(config):
    f = make_feedstock(props={"mw_g_per_mol": None}, data_gaps=(missing("composition.mw_g_per_mol"),))
    a = scoring.assess_feedstock_compatibility(f, [req("mw_g_per_mol", max=3000)], config)
    assert a.score is None and "doesn't report them" in a.rationale
    b = scoring.assess_feedstock_compatibility(make_feedstock(), [], config)
    assert b.score is None and "no numeric requirements" in b.rationale


# --- Rule: technical readiness -------------------------------------------------------------------------


@pytest.mark.parametrize("trl, expected", [(1, 1), (2, 1), (3, 2), (4, 2), (5, 3), (6, 3), (7, 4), (8, 5), (9, 5)])
def test_trl_mapping(config, trl, expected):
    assert scoring.assess_technical_readiness(trl, ("EV-PF-01",), config).score == expected


def test_trl_missing_is_not_assessed(config):
    assert scoring.assess_technical_readiness(None, (), config).method == "none"


@pytest.mark.parametrize("trl", [0, 10, 6.5, True, "7"])
def test_invalid_trl_is_rejected(config, trl):
    with pytest.raises(ValueError, match="whole number from 1 to 9"):
        scoring.assess_technical_readiness(trl, (), config)


# --- Rule: indicative economics ------------------------------------------------------------------------


def per_tonne(price: float, cost: float = 0, unit: str = "USD/t"):
    """An analysis where gross contribution per tonne of usable feedstock equals price - cost."""
    return calc.analyse(make_inputs(wet_mass=inp(1000, "t/yr"), moisture=inp(0, "%"), availability=inp(100, "%"),
                                    product_yield=inp(1, "t/t"), price=inp(price, unit),
                                    variable_costs=costs(("c", inp(cost, unit), "product"))))


@pytest.mark.parametrize("price, cost, expected", [
    (0, 50, 1),      # -50: negative
    (0, 0, 1),       # exactly 0
    (100, 0, 2),     # exactly 100
    (100.5, 0, 3),
    (250, 0, 3),     # exactly 250
    (500, 0, 4),     # exactly 500
    (500.5, 0, 5),
])
def test_economics_bands(config, price, cost, expected):
    assert scoring.assess_indicative_economics(per_tonne(price, cost), config).score == expected


def test_economics_shows_all_three_scenarios(config):
    a = scoring.assess_indicative_economics(calc.analyse(make_inputs(price=inp(800, "USD/t", conservative=200, optimistic=900))), config)
    # base 582 -> 5; conservative (200 x 11,700 - 1,794,000) / 13,000 = 42 -> 2; optimistic 672 -> 5
    assert a.score == 5
    assert "(conservative 2, optimistic 5)" in a.rationale
    assert len(a.inputs) == 3 and a.inputs[1].startswith("base: 582.00 USD/t usable dry feedstock")


def test_economics_not_assessed_when_inputs_are_missing(config):
    a = scoring.assess_indicative_economics(calc.analyse(make_inputs(price=None)), config)
    assert a.score is None
    assert "Missing inputs: product price." in a.rationale and "could not be calculated" in a.rationale


def test_economics_not_assessed_in_another_currency(config):
    a = scoring.assess_indicative_economics(per_tonne(300, 0, unit="EUR/t"), config)
    assert a.score is None and "no exchange rate" in a.rationale


def test_economics_cites_the_evidence_behind_its_inputs(config):
    analysis = calc.analyse(make_inputs(price=inp(800, "USD/t", basis="evidence", evidence_ids=("EV-PF-01",))))
    assert scoring.assess_indicative_economics(analysis, config).evidence_ids == ("EV-PF-01",)


# --- Ranking -------------------------------------------------------------------------------------------


def test_ranking_order_and_tie_breaks(config):
    opps = [
        scoring.score_opportunity("b_low", "B", full(dict.fromkeys(CRITERIA, 2)), config),
        scoring.score_opportunity("c_tie_partial", "C", full({c: 4 for c in CRITERIA if c != "market_evidence"}), config),
        scoring.score_opportunity("d_tie_full", "D", full(dict.fromkeys(CRITERIA, 4)), config),
        scoring.score_opportunity("a_tie_full", "A", full(dict.fromkeys(CRITERIA, 4)), config),
        scoring.score_opportunity("e_thin", "E", full({"technical_readiness": 5}), config),
    ]
    ranking = scoring.rank(opps, config)
    # equal attractiveness: more complete first, then by id
    assert [o.pathway_id for o in ranking.ranked] == ["a_tie_full", "d_tie_full", "c_tie_partial", "b_low"]
    assert [o.rank for o in ranking.ranked] == [1, 2, 3, 4]
    assert [o.pathway_id for o in ranking.insufficient_data] == ["e_thin"]
    assert ranking.insufficient_data[0].rank is None


def test_weights_can_change_the_ranking(config):
    ready = full({**dict.fromkeys(CRITERIA, 3), "technical_readiness": 5})
    lucrative = full({**dict.fromkeys(CRITERIA, 3), "indicative_economics": 5})
    readiness_first = scoring.with_weights(config, {**dict.fromkeys(CRITERIA, 0.1), "technical_readiness": 0.6})
    economics_first = scoring.with_weights(config, {**dict.fromkeys(CRITERIA, 0.1), "indicative_economics": 0.6})
    for cfg, winner in ((readiness_first, "ready"), (economics_first, "lucrative")):
        opps = [scoring.score_opportunity("ready", "R", ready, cfg), scoring.score_opportunity("lucrative", "L", lucrative, cfg)]
        assert scoring.rank(opps, cfg).ranked[0].pathway_id == winner


def test_a_pathway_appears_once(config):
    o = scoring.score_opportunity("p", "P", [], config)
    with pytest.raises(ValueError, match="only once"):
        scoring.rank([o, o], config)


def test_ranking_is_deterministic(config):
    opps = [scoring.score_opportunity(p, p, full(dict.fromkeys(CRITERIA, s)), config) for p, s in (("x", 3), ("y", 4))]
    assert scoring.rank(opps, config) == scoring.rank(list(reversed(opps)), config)


# --- End to end: rules + judgments -> ranking -------------------------------------------------------------


def test_end_to_end(config):
    analysis = calc.analyse(make_inputs())
    assessments = [
        scoring.assess_feedstock_compatibility(make_feedstock(), [req(max=2.0)], config),
        scoring.assess_technical_readiness(8, ("EV-PF-01",), config),
        scoring.assess_indicative_economics(analysis, config),
        analyst_assessment("market_evidence", 4, "Commercial sales documented.", ("EV-PF-01",)),
        not_assessed("commercialization_feasibility", "Partner search not done yet."),
    ]
    result = scoring.score_opportunity("toy", "Toy", assessments, config, library=LIB, missing_inputs=analysis.missing_inputs)
    # 0.25x5 + 0.20x5 + 0.20x4 + 0.20x5 = 4.05 over 0.85 of the weight = 4.76; range 4.05 + 0.15 x (1..5)
    assert result.attractiveness == 4.76
    assert result.attractiveness_range == (4.2, 4.8)
    assert result.completeness.not_assessed == ("commercialization_feasibility",)
    assert result.status == "ranked"
    assert scoring.rank([result], config).ranked[0].rank == 1
