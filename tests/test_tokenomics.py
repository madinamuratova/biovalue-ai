"""Usage logging and cost arithmetic (backend/tokenomics.py, backend/trace.py, the usage log)."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from backend import tokenomics
from backend.trace import Usage
from backend.workflow import run_workflow
from tests.test_workflow import models

GPT6 = tokenomics.verified_price("gpt-6-luna")


def test_verified_price_comes_from_the_price_file():
    assert GPT6 is not None and (GPT6.input_per_1m, GPT6.cached_input_per_1m, GPT6.output_per_1m) == (0.1, 0.01, 0.5)
    assert tokenomics.verified_price("gpt-5.6-luna") is None  # no verified price on file


def test_cost_splits_cached_and_uncached_input():
    usage = Usage(input_tokens=1_000_000, cache_read_tokens=400_000, output_tokens=100_000)
    # 600,000 x 0.10 + 400,000 x 0.01 + 100,000 x 0.50, per million = 0.06 + 0.004 + 0.05
    assert tokenomics.cost_usd(usage, GPT6) == pytest.approx(0.114)


def test_unpriced_model_gets_no_cost_and_a_labelled_proxy():
    report = tokenomics.cost_report("gpt-5.6-luna", Usage(input_tokens=100_000, cache_read_tokens=50_000, output_tokens=10_000))
    assert report.status == "not_calculated" and report.usd is None
    assert "No verified price for gpt-5.6-luna" in report.note
    assert report.proxy_usd == pytest.approx((50_000 * 0.1 + 50_000 * 0.01 + 10_000 * 0.5) / 1e6)
    assert report.proxy_note.startswith("Estimate only: priced as gpt-6-luna")


def test_priced_model_gets_a_cost():
    report = tokenomics.cost_report("gpt-6-luna", Usage(input_tokens=1_000_000, output_tokens=0))
    assert report.status == "calculated" and report.usd == pytest.approx(0.1)


def test_monthly_estimate_arithmetic():
    per_run = Usage(input_tokens=80_000, cache_read_tokens=40_000, output_tokens=12_000)
    est = tokenomics.monthly_estimate(per_run, users=100, assessments_per_user=4, price=GPT6)
    assert est["assessments_per_month"] == 400
    assert est["tokens"] == {"input_tokens": 32_000_000, "cache_read_tokens": 16_000_000, "output_tokens": 4_800_000}
    # per run: 40,000 x 0.1 + 40,000 x 0.01 + 12,000 x 0.5 = 10,400 per million = 0.0104 USD; x 400
    assert est["model_cost_usd"] == pytest.approx(4.16)


def test_assumptions_are_explicit_and_other_costs_are_not_estimated():
    a = tokenomics.assumptions()
    assert a["assessments_per_user_per_month"] == 4 and a["assessments_reason"]
    assert a["user_counts"] == [100, 10000]
    assert all(v is None for k, v in a["other_costs"].items() if k != "note")


def test_usage_reads_provider_metadata():
    run_usage = SimpleNamespace(requests=3, tool_calls=4, input_tokens=5000, cache_read_tokens=3000, output_tokens=700,
                                details={"reasoning_tokens": 120})
    u = Usage.from_run(run_usage)
    assert (u.input_tokens, u.cache_read_tokens, u.output_tokens, u.reasoning_tokens) == (5000, 3000, 700, 120)
    assert Usage.from_run(SimpleNamespace(**{**run_usage.__dict__, "details": {}})).reasoning_tokens is None


def test_usage_adds_and_keeps_unreported_reasoning_as_none():
    total = Usage()
    total.add(Usage(requests=1, input_tokens=10, output_tokens=2))
    total.add(Usage(requests=2, input_tokens=5, cache_read_tokens=3, output_tokens=1))
    assert (total.requests, total.input_tokens, total.cache_read_tokens, total.output_tokens) == (3, 15, 3, 3)
    assert total.reasoning_tokens is None


@pytest.mark.mock
def test_every_run_writes_a_complete_usage_record(tmp_path):
    result = asyncio.run(run_workflow(model=models(), output_dir=tmp_path))
    record = json.loads((tmp_path / "usage_log.json").read_text())[-1]
    assert record["run_id"] == result.run_id and record["config"] == result.config
    assert record["usage_source"].startswith("provider usage metadata")
    for agent in ("feedstock", "market", "commercialization", "decision"):
        a = record["agents"][agent]
        for key in ("model", "input_tokens", "cached_input_tokens", "uncached_input_tokens", "output_tokens",
                    "reasoning_tokens", "latency_seconds", "requests", "cost"):
            assert key in a, (agent, key)
        assert a["uncached_input_tokens"] == a["input_tokens"] - a["cached_input_tokens"]
        assert a["reasoning_tokens"] == "not reported"  # the scripted model reports none: labelled, not zero
        assert a["cost"]["status"] == "not_calculated" and a["cost"]["proxy_note"].startswith("Estimate only")
    assert record["total"]["input_tokens"] == sum(record["agents"][a]["input_tokens"] for a in record["agents"])
