"""State shared by the agents during one workflow run: the validated inputs, the trace, the deterministic results
the tools produced, and the validated outputs of the agents that already ran."""

from dataclasses import dataclass, field

from backend.agents.schemas import CommercializationAgentOutput, FeedstockAgentOutput, MarketAgentOutput
from backend.calc import ScenarioAnalysis
from backend.config import RunConfig, default_run_config
from backend.project import Project
from backend.scoring import Assessment, Ranking, ScoringConfig
from backend.trace import Trace


@dataclass
class WorkflowDeps:
    project: Project
    scoring: ScoringConfig
    trace: Trace
    config: RunConfig = field(default_factory=default_run_config)
    agent: str = ""  # the agent currently running; tools record their calls under it

    # Deterministic results, filled in by the tools as the agents call them.
    feedstock_check: dict | None = None
    dry_mass_results: list[dict] = field(default_factory=list)
    searched_pathways: set[str] = field(default_factory=set)
    compatibility: dict[str, Assessment] = field(default_factory=dict)
    economics: dict[str, ScenarioAnalysis] = field(default_factory=dict)
    readiness: dict[str, Assessment] = field(default_factory=dict)
    ranking: Ranking | None = None

    # Validated outputs of earlier agents.
    feedstock_output: FeedstockAgentOutput | None = None
    market_output: MarketAgentOutput | None = None
    commercialization_output: CommercializationAgentOutput | None = None
