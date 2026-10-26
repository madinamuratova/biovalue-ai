"""What each agent must return. PydanticAI validates every answer against these models and asks the agent to fix
anything that doesn't fit; the guards (backend/agents/guards.py) then check the content against the data.

Agents return judgments and references, not arithmetic: every number they mention must come from a tool result
or from the evidence they cite.
"""

from pydantic import Field

from backend.models import Frozen

REFS = ("Evidence references: 'EV-PF-01#2' is claim 2 of record EV-PF-01, 'EV-PF-01#R1' is its technical "
        "requirement 1, and 'feedstock:<field path>' is a field of the feedstock profile.")


class EvidenceFinding(Frozen):
    statement: str = Field(min_length=1, description="One sentence in your own words. Any number in it must appear in the cited evidence or a tool result.")
    evidence: tuple[str, ...] = Field(min_length=1, description=REFS)


class Judgment(Frozen):
    score: int = Field(ge=1, le=5, description="Score on the rubric's 1-5 scale.")
    rationale: str = Field(min_length=1, description="Why this score, in one or two sentences, against the rubric levels.")
    evidence: tuple[str, ...] = Field(default=(), description=REFS)


# --- Feedstock Agent -----------------------------------------------------------------------------


class FeedstockAgentOutput(Frozen):
    feedstock_id: str
    is_fictional: bool = Field(description="True when the feedstock record says its data is fictional or not measured.")
    wet_mass_t_per_yr: float = Field(description="From convert_units, in t/yr.")
    moisture_fraction: float = Field(ge=0, le=1, description="From convert_units, as a fraction of wet mass.")
    dry_mass_t_per_yr: float = Field(description="From calculate_dry_mass, in t/yr.")
    missing_properties: tuple[str, ...] = Field(description="Exactly the missing fields reported by validate_feedstock.")
    inconsistencies: tuple[str, ...] = Field(description="Contradictions or failed checks; empty if none were found.")
    constraints: tuple[str, ...] = Field(min_length=1, description="Practical limits on using this lignin, from the record (infrastructure, current use, moisture, data gaps). One sentence each.")
    data_quality_notes: tuple[str, ...] = Field(description="What a reader must know before trusting the data.")
    summary: str = Field(min_length=1)


# --- Market Intelligence Agent -----------------------------------------------------------------------


class PathwayMarket(Frozen):
    pathway_id: str
    applications: tuple[EvidenceFinding, ...] = Field(description="Products or uses the evidence supports.")
    target_customers: tuple[EvidenceFinding, ...] = Field(description="Customer types the evidence names or clearly implies. Empty if none.")
    competing_materials: tuple[EvidenceFinding, ...] = Field(description="Incumbent or competing materials the evidence names.")
    qualification_requirements: tuple[EvidenceFinding, ...] = Field(description="Standards, tests, or approvals the evidence names.")
    limitations: tuple[str, ...] = Field(description="Limitations of the evidence itself.")
    missing_information: tuple[str, ...] = Field(min_length=1, description="Market information the evidence does not provide (e.g. prices, volumes, named buyers).")
    market_evidence: Judgment | None = Field(description="Score against the market_evidence rubric, citing evidence; null if the evidence is too thin to judge.")


class MarketAgentOutput(Frozen):
    pathways: tuple[PathwayMarket, ...] = Field(description="One entry per pathway in scope, in the order given.")


# --- Commercialization Agent -------------------------------------------------------------------------


class PathwayCommercialization(Frozen):
    pathway_id: str
    processing_requirements: tuple[EvidenceFinding, ...] = Field(description="Processing the mill's lignin would need for this pathway.")
    technical_maturity: EvidenceFinding | None = Field(description="How mature the technology is, citing the evidence behind the TRL you confirmed; null if none.")
    adoption_barriers: tuple[EvidenceFinding, ...]
    missing_inputs: tuple[str, ...] = Field(description="Every input the economics tool reported missing, plus other missing information.")
    assumptions: tuple[str, ...] = Field(description="Assumptions behind this assessment, including those the economics tool listed.")
    uncertainties: tuple[str, ...] = Field(min_length=1)
    commercialization_feasibility: Judgment | None = Field(description="Score against the commercialization_feasibility rubric; null if you can't judge.")


class CommercializationAgentOutput(Frozen):
    pathways: tuple[PathwayCommercialization, ...] = Field(description="One entry per pathway in scope, in the order given.")


# --- Decision Agent ------------------------------------------------------------------------------------


class ShortlistItem(Frozen):
    pathway_id: str
    rank: int | None = Field(description="The rank from score_and_rank; null for pathways listed as insufficient data.")
    main_drivers: tuple[str, ...] = Field(min_length=1, description="The criteria and facts that put it where it is.")
    what_could_change_it: tuple[str, ...] = Field(min_length=1, description="New evidence or data that could move it up or down.")


class ValidationStep(Frozen):
    action: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    addresses: tuple[str, ...] = Field(min_length=1, description="Criteria, missing inputs, or data gaps this step resolves.")


class DecisionAgentOutput(Frozen):
    shortlist: tuple[ShortlistItem, ...] = Field(description="Every pathway, in the order score_and_rank returned: ranked ones first, then insufficient-data ones.")
    validation_steps: tuple[ValidationStep, ...] = Field(min_length=3, max_length=5)
    ranking_changers: tuple[str, ...] = Field(min_length=1, description="Evidence that would most change the overall ranking.")
    caveats: tuple[str, ...]
    summary: str = Field(min_length=1)
