"""The four agents: their prompts, tools, output schemas, and guards.

Each agent sees only its own tools. None of the tools can start an agent, and only the workflow runs agents, in
AGENT_ORDER, once each. So there is no delegation and no recursion.
"""

from collections.abc import Callable

from pydantic_ai import Agent
from pydantic_ai.models import Model

from backend.agents import tools
from backend.agents.deps import WorkflowDeps
from backend.agents.guards import GUARDS, make_validator
from backend.agents.schemas import (
    CommercializationAgentOutput, DecisionAgentOutput, FeedstockAgentOutput, MarketAgentOutput,
)
from backend.config import OUTPUT_RETRIES, PROMPTS_DIR, TOOL_TIMEOUT_SECONDS, RunConfig, default_run_config

AGENT_ORDER = ("feedstock", "market", "commercialization", "decision")

AGENT_TITLES = {
    "feedstock": "Feedstock Agent",
    "market": "Market Intelligence Agent",
    "commercialization": "Commercialization Agent",
    "decision": "Decision Agent",
}

AGENT_TOOLS: dict[str, tuple[Callable, ...]] = {
    "feedstock": (tools.read_feedstock_profile, tools.convert_units, tools.calculate_dry_mass, tools.validate_feedstock),
    "market": (tools.list_pathways, tools.search_evidence, tools.get_evidence_record, tools.get_scoring_rubric),
    "commercialization": (tools.get_pathway_requirements, tools.check_feedstock_compatibility,
                          tools.run_scenario_analysis, tools.assess_technical_readiness, tools.get_evidence_record,
                          tools.get_scoring_rubric),
    "decision": (tools.get_scoring_rubric, tools.score_and_rank),
}

OUTPUT_TYPES = {
    "feedstock": FeedstockAgentOutput,
    "market": MarketAgentOutput,
    "commercialization": CommercializationAgentOutput,
    "decision": DecisionAgentOutput,
}


# Extra tools in the optimized configuration (output/tokenomics.md compares the two).
OPTIMIZED_EXTRA_TOOLS: dict[str, tuple[Callable, ...]] = {"commercialization": (tools.find_trl_claims,)}

EFFICIENCY_HINTS = """

## Efficiency

- Request independent tool calls together in one step (for example the same tool for all three pathways).
- Don't call a tool again for something it already returned, and don't read whole evidence records when a search
  result already has the claim you need.
- Keep statements short. Cite references instead of repeating the evidence text."""

TRL_HINT = "\n- To confirm a TRL, call `find_trl_claims` for the pathway, then `assess_technical_readiness` with that claim."


def instructions(name: str, config: RunConfig | None = None) -> str:
    text = (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    if config and config.efficiency_hints:
        text += EFFICIENCY_HINTS + (TRL_HINT if name == "commercialization" else "")
    return text


def tools_for(name: str, config: RunConfig) -> tuple[Callable, ...]:
    extra = OPTIMIZED_EXTRA_TOOLS.get(name, ()) if config.efficiency_hints else ()
    return AGENT_TOOLS[name] + extra


def build_agent(name: str, model: Model, config: RunConfig | None = None) -> Agent:
    config = config or default_run_config()
    agent = Agent(
        model,
        name=AGENT_TITLES[name],
        instructions=instructions(name, config),
        deps_type=WorkflowDeps,
        output_type=OUTPUT_TYPES[name],
        tools=list(tools_for(name, config)),
        retries=OUTPUT_RETRIES,
        tool_timeout=TOOL_TIMEOUT_SECONDS,
    )
    agent.output_validator(make_validator(*GUARDS[name]))
    return agent


def build_agents(model: Model | Callable[[str], Model], config: RunConfig | None = None) -> dict[str, Agent]:
    """One agent per role. `model` is a model shared by all four, or a function giving each agent its own (tests)."""
    return {name: build_agent(name, model(name) if callable(model) and not isinstance(model, Model) else model, config)
            for name in AGENT_ORDER}
