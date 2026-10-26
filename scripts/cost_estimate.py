"""Monthly model-cost estimates for 100 and 10,000 users, from measured token usage and stated assumptions.

Run after scripts/evaluate.py:
    .venv/bin/python scripts/cost_estimate.py

Inputs:
- tokens per assessment: the mean of the completed evaluation runs per configuration (output/evaluation/results.json),
  excluding the unscreened injection case, which is a test, not normal use
- users and assessments per user: data/tokenomics_assumptions.json
- price: the run model's verified price in data/model_prices.json (gpt-6-luna has one); a model without a verified
  price is costed at the proxy model's price and labelled as an estimate

Hosting and other costs are listed separately and are not estimated (no verified quotes).
Writes output/cost_estimate.json and prints a table.
"""

import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import tokenomics  # noqa: E402
from backend.config import OUTPUT_DIR, model_name  # noqa: E402
from backend.trace import Usage  # noqa: E402


def main() -> None:
    results = json.loads((OUTPUT_DIR / "evaluation" / "results.json").read_text())
    a = tokenomics.assumptions()
    model = model_name()
    verified = tokenomics.verified_price(model)
    proxy = verified or tokenomics.proxy_price()
    per_config = {}
    for config in sorted({r["config"] for r in results}):
        runs = [r for r in results if r["config"] == config and r["status"] == "complete"
                and r["case"] != "injection_unscreened"]
        if not runs:
            continue
        mean = lambda k: statistics.mean(r["total"][k] for r in runs)  # noqa: E731
        per_run = Usage(input_tokens=round(mean("input_tokens")), cache_read_tokens=round(mean("cache_read_tokens")),
                        output_tokens=round(mean("output_tokens")))
        per_config[config] = {
            "runs_measured": len(runs), "cases": sorted({r["case"] for r in runs}),
            "tokens_per_assessment": per_run.model_dump(include={"input_tokens", "cache_read_tokens", "output_tokens"}),
            "latency_seconds_per_assessment": round(mean("latency_seconds"), 1),
            "cost_per_assessment_usd": round(tokenomics.cost_usd(per_run, proxy), 6),
            "monthly": [tokenomics.monthly_estimate(per_run, users, a["assessments_per_user_per_month"], proxy)
                        for users in a["user_counts"]],
        }
    out = {
        "model": model,
        "pricing": {"status": "verified price" if verified else "proxy estimate", "price_model": proxy.model,
                    "source": proxy.source, "rates_per_1m_usd": {"input": proxy.input_per_1m,
                                                                 "cached_input": proxy.cached_input_per_1m,
                                                                 "output": proxy.output_per_1m},
                    **({} if verified else {"reason": a["proxy_reason"]})},
        "assumptions": {"assessments_per_user_per_month": a["assessments_per_user_per_month"],
                        "reason": a["assessments_reason"], "user_counts": a["user_counts"]},
        "model_costs": per_config,
        "other_costs": a["other_costs"],
    }
    (OUTPUT_DIR / "cost_estimate.json").write_text(json.dumps(out, indent=2) + "\n")
    print(f"Model costs for {model} at {proxy.model} prices" + ("" if verified else f" (proxy estimate; {model} has no verified price)"))
    print(f"Assumption: {a['assessments_per_user_per_month']} assessments per user per month\n")
    print(f"{'Config':<10}{'Runs':>5}{'In tok/run':>12}{'Cached':>10}{'Out tok/run':>12}{'USD/run':>10}"
          + "".join(f"{f'USD/mo @{u:,}':>16}" for u in a["user_counts"]))
    for name, c in per_config.items():
        t = c["tokens_per_assessment"]
        print(f"{name:<10}{c['runs_measured']:>5}{t['input_tokens']:>12,}{t['cache_read_tokens']:>10,}{t['output_tokens']:>12,}"
              f"{c['cost_per_assessment_usd']:>10.4f}" + "".join(f"{m['model_cost_usd']:>16,.2f}" for m in c["monthly"]))
    print("\nHosting, Portkey plan, storage, and support: not estimated (no verified quotes); see data/tokenomics_assumptions.json")


if __name__ == "__main__":
    main()
