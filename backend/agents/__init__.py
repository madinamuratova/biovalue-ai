"""BioValue AI's four agents. The workflow (backend/workflow.py) runs them in a fixed order:

    Feedstock -> Market Intelligence -> Commercialization -> Decision

Agents never call each other: each has only its own tools, and only the workflow starts an agent.
"""

from backend.agents.agents import AGENT_ORDER, AGENT_TITLES, AGENT_TOOLS, build_agents

__all__ = ["AGENT_ORDER", "AGENT_TITLES", "AGENT_TOOLS", "build_agents"]
