"""Paths, model settings, and limits for BioValue AI.

The model is reached through Portkey with PORTKEY_API_KEY, as in the course AGENTS.md. The project requirements say the
course key is for gpt-6-luna only, so that is the default. BIOVALUE_MODEL overrides it; the app deliberately ignores the
shared OPENAI_MODEL setting so a course-wide .env can't switch it to a model the course key doesn't cover.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
PROMPTS_DIR = ROOT / "backend" / "prompts"

# Project .env first (graders), then the course .env one folder up (local development).
load_dotenv(ROOT / ".env")
load_dotenv(ROOT.parent / ".env")

DEFAULT_MODEL = "gpt-6-luna"
DEFAULT_PORTKEY_BASE_URL = "https://api.portkey.ai/v1"

# Timeouts and bounded retries.
REQUEST_TIMEOUT_SECONDS = 90  # one model request; a stuck call fails instead of hanging
REQUEST_MAX_RETRIES = 2  # transport-level retries inside the OpenAI client (connection errors, 429, 5xx)
AGENT_TIMEOUT_SECONDS = 300  # one whole agent run, including its tool calls
AGENT_ATTEMPTS = 2  # an agent run that times out or hits a transient API error is tried at most twice
OUTPUT_RETRIES = 2  # how many times an agent may fix a tool call or answer that failed validation
TOOL_TIMEOUT_SECONDS = 30  # one tool call (all tools are local and fast)

# Per-agent limits, so one agent can't loop or run up cost.
AGENT_USAGE_LIMITS = UsageLimits(request_limit=15, tool_calls_limit=30, total_tokens_limit=200_000)
# Per-run budget across all four agents (input + output tokens). Measured runs used 83k-154k; an agent that would
# start with the budget already spent fails instead. PydanticAI checks the limit after each model response, so a
# run can overshoot by at most one request.
RUN_TOKEN_BUDGET = 400_000

# Input-size limits for dashboard requests.
MAX_REQUEST_BYTES = 100_000  # whole request body
MAX_TEXT_CHARS = 1_000  # any one text field
MAX_LIST_ITEMS = 30  # any one list (infrastructure, data gaps, markets, cost items, ...)

# User-submitted inputs are not written to disk unless this is set (the saved assessment keeps what the report needs).
STORE_RUN_INPUTS = os.getenv("BIOVALUE_STORE_INPUTS", "").strip() == "1"


@dataclass(frozen=True)
class RunConfig:
    """How a workflow run spends tokens. The two configurations are compared in output/tokenomics.md."""

    name: str
    compact_context: bool  # pass agents only the fields they need from earlier agents, as compact JSON
    compact_tools: bool  # trim tool results (no supporting quotes, base scenario in full, other scenarios as values)
    efficiency_hints: bool  # prompt appendix: batch independent tool calls, don't re-read records, use find_trl_claims
    run_token_budget: int = RUN_TOKEN_BUDGET


BASELINE = RunConfig("baseline", compact_context=False, compact_tools=False, efficiency_hints=False)
OPTIMIZED = RunConfig("optimized", compact_context=True, compact_tools=True, efficiency_hints=True)
RUN_CONFIGS = {c.name: c for c in (BASELINE, OPTIMIZED)}


def default_run_config() -> RunConfig:
    return RUN_CONFIGS.get(os.getenv("BIOVALUE_RUN_CONFIG", "optimized").strip(), OPTIMIZED)


def model_name() -> str:
    return os.getenv("BIOVALUE_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def build_model() -> OpenAIResponsesModel:
    """The course model through Portkey, using PORTKEY_API_KEY from .env."""
    api_key = os.getenv("PORTKEY_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("PORTKEY_API_KEY is not set. Copy .env.example to .env and add your Portkey key.")
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=os.getenv("PORTKEY_BASE_URL", DEFAULT_PORTKEY_BASE_URL).rstrip("/"),
        default_headers={
            "x-portkey-api-key": api_key,
            # Portkey can replay a stored response for a repeated request (found in HW 6).
            # Force a real model call so every run's answers and token counts are real.
            "x-portkey-cache-force-refresh": "true",
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
        max_retries=REQUEST_MAX_RETRIES,
    )
    return OpenAIResponsesModel(model_name(), provider=OpenAIProvider(openai_client=client))
