"""Run all four BioValue AI agents on the demo project with the course model, and print the result.

Run from the project folder (needs PORTKEY_API_KEY in .env):
    .venv/bin/python scripts/run_workflow.py
    .venv/bin/python scripts/run_workflow.py --no-save        (don't write to output/)

Writes output/runs/<run id>.json and output/latest_assessment.json, and appends to output/audit_trail.json
and output/usage_log.json.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import OUTPUT_DIR  # noqa: E402
from backend.workflow import run_workflow  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-save", action="store_true", help="don't write the assessment or logs to output/")
    args = parser.parse_args()

    result = asyncio.run(run_workflow(output_dir=None if args.no_save else OUTPUT_DIR))

    print(f"\nRun {result.run_id} | model {result.model} | status: {result.status.upper()}\n")
    print(f"{'#':<3}{'Agent':<20}{'Status':<9}{'Tries':>5}{'Secs':>7}{'Reqs':>6}{'In tok':>9}{'Out tok':>9}  Tools called")
    for a in result.execution.agents:
        tools = ", ".join(f"{c.tool}{'' if c.status == 'ok' else f' [{c.status}]'}" for c in a.tool_calls) or "-"
        print(f"{a.order:<3}{a.agent:<20}{a.status:<9}{a.attempts:>5}{(a.seconds or 0):>7.1f}{a.usage.requests:>6}"
              f"{a.usage.input_tokens:>9,}{a.usage.output_tokens:>9,}  {tools}")
        for g in a.guard_events:
            print(f"   guard {g.action}: {'; '.join(g.problems)[:300]}")
        for e in a.errors:
            print(f"   error {e[:300]}")
        if a.skipped_reason:
            print(f"   {a.skipped_reason}")
    u = result.usage
    print(f"\nTotal: {u.requests} requests, {u.tool_calls} tool calls, {u.input_tokens:,} input and "
          f"{u.output_tokens:,} output tokens. Cost: {result.cost.usd if result.cost.usd is not None else result.cost.note}")

    ranking = result.decision.ranking
    print(f"\nRanking ({result.decision.ranking_source}):")
    for o in ranking.ranked:
        print(f"  {o.rank}. {o.name}: attractiveness {o.attractiveness} (range {o.attractiveness_range}), "
              f"{o.completeness.assessed_weight:.0%} of weight assessed, strongest evidence {o.evidence.strongest}")
    for o in ranking.insufficient_data:
        print(f"  -  {o.name}: insufficient data ({o.completeness.assessed_weight:.0%} of weight assessed; "
              f"not assessed: {', '.join(o.completeness.not_assessed)})")

    report = result.decision.report
    if report:
        print("\nDecision Agent summary:\n  " + report.summary)
        print("\nValidation steps:")
        for i, s in enumerate(report.validation_steps, 1):
            print(f"  {i}. {s.action}  [addresses: {', '.join(s.addresses)}]")
    if not args.no_save:
        print(f"\nSaved {OUTPUT_DIR / 'runs' / (result.run_id + '.json')}")
    return 0 if result.status == "complete" else 1


if __name__ == "__main__":
    sys.exit(main())
