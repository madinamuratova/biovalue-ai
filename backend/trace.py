"""Execution tracking for one workflow run.

Records which agents ran (in what order, how many attempts, how long), every tool call each agent made (with
its arguments and whether it succeeded), every guard action, and the tokens used. The trace is saved with the
final assessment and appended to output/audit_trail.json and output/usage_log.json.
"""

import json
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.safety import redact

PREVIEW_CHARS = 300


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def short(value: Any, limit: int = PREVIEW_CHARS) -> str:
    """A redacted preview: API keys never reach the trace, the audit trail, or the screen."""
    text = redact(value if isinstance(value, str) else json.dumps(value, default=str))
    return text if len(text) <= limit else text[:limit] + f"... (+{len(text) - limit} chars)"


class ToolCallRecord(BaseModel):
    agent: str
    tool: str
    arguments: dict[str, Any]
    status: Literal["ok", "rejected", "error"]  # rejected = the tool refused bad input and asked the model to retry
    result: str = ""  # short preview of the result, or the reason for rejection
    seconds: float


class GuardEvent(BaseModel):
    agent: str
    action: Literal["retry_requested", "fixed_by_code"]
    problems: list[str]


class SecurityEvent(BaseModel):
    kind: Literal["instruction_like_text_removed"]
    source: str  # "feedstock input" or the tool that returned evidence text
    field: str
    matched: list[str]  # the phrases that looked like instructions


class Usage(BaseModel):
    """Token counts as reported by the provider. cache_read_tokens is 0 both when nothing was cached and when the
    provider doesn't report caching; reasoning_tokens is None when the provider doesn't report it."""

    requests: int = 0
    tool_calls: int = 0
    input_tokens: int = 0  # all input, including cached
    cache_read_tokens: int = 0  # the part of input_tokens served from the provider's prompt cache
    output_tokens: int = 0
    reasoning_tokens: int | None = None

    def add(self, other: "Usage") -> None:
        for name in ("requests", "tool_calls", "input_tokens", "cache_read_tokens", "output_tokens"):
            setattr(self, name, getattr(self, name) + getattr(other, name))
        if other.reasoning_tokens is not None:
            self.reasoning_tokens = (self.reasoning_tokens or 0) + other.reasoning_tokens

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @classmethod
    def from_run(cls, usage: Any) -> "Usage":
        details = dict(getattr(usage, "details", None) or {})
        return cls(requests=usage.requests, tool_calls=usage.tool_calls, input_tokens=usage.input_tokens,
                   cache_read_tokens=usage.cache_read_tokens, output_tokens=usage.output_tokens,
                   reasoning_tokens=details.get("reasoning_tokens"))


class AgentRun(BaseModel):
    agent: str
    order: int
    status: Literal["pending", "running", "ok", "failed", "skipped"] = "pending"
    attempts: int = 0
    started_at: str | None = None
    finished_at: str | None = None
    seconds: float | None = None
    usage: Usage = Field(default_factory=Usage)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    guard_events: list[GuardEvent] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)  # one entry per failed attempt
    skipped_reason: str = ""


class Trace(BaseModel):
    run_id: str
    model: str
    config: str = ""
    token_budget: int | None = None
    started_at: str = Field(default_factory=now)
    finished_at: str | None = None
    agents: list[AgentRun] = Field(default_factory=list)
    security_events: list[SecurityEvent] = Field(default_factory=list)

    def record_security(self, source: str, events: list[dict]) -> None:
        for e in events:
            self.security_events.append(SecurityEvent(kind="instruction_like_text_removed", source=source,
                                                      field=e["field"], matched=e["matched"]))

    def add_agents(self, names: list[str]) -> None:
        self.agents = [AgentRun(agent=n, order=i) for i, n in enumerate(names, start=1)]

    def agent(self, name: str) -> AgentRun:
        for a in self.agents:
            if a.agent == name:
                return a
        raise KeyError(f"agent {name!r} is not part of this run")

    def record_guard(self, agent: str, action: str, problems: list[str]) -> None:
        self.agent(agent).guard_events.append(GuardEvent(agent=agent, action=action, problems=problems))

    @contextmanager
    def tool(self, agent: str, tool: str, **arguments: Any):
        """Record one tool call. Use `call.result = ...` for a preview; exceptions are recorded and re-raised."""
        from pydantic_ai import ModelRetry  # local import keeps this module free of agent code at import time

        call = ToolCallRecord(agent=agent, tool=tool, arguments=arguments, status="ok", seconds=0.0)
        start = time.perf_counter()
        try:
            yield call
        except ModelRetry as exc:
            call.status, call.result = "rejected", short(str(exc))
            raise
        except Exception as exc:
            call.status, call.result = "error", short(f"{type(exc).__name__}: {exc}")
            raise
        finally:
            call.seconds = round(time.perf_counter() - start, 4)
            self.agent(agent).tool_calls.append(call)

    @property
    def total_usage(self) -> Usage:
        total = Usage()
        for a in self.agents:
            total.add(a.usage)
        return total

    def executed(self) -> list[str]:
        """Agents that actually ran, in order."""
        return [a.agent for a in self.agents if a.status in ("ok", "failed")]


def append_json(path: Path, records: list[dict]) -> None:
    """Append records to a JSON list file. Refuses to overwrite a file that isn't a JSON list."""
    existing: list = []
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(existing, list):
            raise RuntimeError(f"{path} is not a JSON list; refusing to overwrite it")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(existing + records, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)
