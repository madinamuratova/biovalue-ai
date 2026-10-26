"""BioValue AI evaluation suite: three tiers, kept apart.

    deterministic   pytest tests with no model at all (units, calculations, scoring, schemas, safety rules, and the
                    scenarios' hand-calculated expectations)
    mock            pytest tests that run the real agents, tools, and guards with a scripted stand-in model
    live            the scenarios in evals/scenarios.json, run with the course model (needs PORTKEY_API_KEY)

Run from the project folder:
    .venv/bin/python -m evals.run_eval                    all three tiers
    .venv/bin/python -m evals.run_eval --tiers deterministic mock
    .venv/bin/python -m evals.run_eval --tiers live --scenarios S01 S04

Writes output/evaluation/eval_results.json (machine-readable) and output/evaluation/EVALUATION.md (summary).
Expectations come from evals/scenarios.json, written before any run; this script never edits them.
"""

import argparse
import asyncio
import json
import re
import statistics
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from backend import calc, safety
from backend.agents.refs import EVIDENCE_REF, resolve
from backend.config import OUTPUT_DIR, ROOT, default_run_config, model_name
from backend.tokenomics import cost_report
from backend.trace import Usage
from backend.workflow import FinalAssessment, run_workflow
from evals.scenario_inputs import build_inputs, build_scenario_project, load_scenarios

EVAL_DIR = OUTPUT_DIR / "evaluation"
RUNS_DIR = EVAL_DIR / "scenario_runs"
EXPERT_FILE = Path(__file__).resolve().parent / "expert_rankings.json"
FINDING_LISTS = ("applications", "target_customers", "competing_materials", "qualification_requirements")
CONFLICT_WORDS = re.compile(r"conflict|contradict|inconsisten|disagree", re.I)
EXTERNAL_CITATION = re.compile(r"https?://|www\.|\bdoi\b|(?-i:\bNature\b)|\b30 USD", re.I)
REF_REJECTIONS = ("there is no evidence record", "no such field", "is not a reference", "belongs to pathway",
                  "is marked unverified", "claim(s)", "requirement(s)")
QUALIFICATION_WORDS = re.compile(r"qualif|certif|standard|EN 314|ASTM|approval", re.I)


# --- Tiers 1 and 2: pytest -----------------------------------------------------------------------------------


def run_pytest(marker: str) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "junit.xml"
        start = time.perf_counter()
        proc = subprocess.run([sys.executable, "-m", "pytest", "-o", "addopts=", "-q", "-m", marker,
                               f"--junitxml={report}"], cwd=ROOT, capture_output=True, text=True)
        seconds = round(time.perf_counter() - start, 2)
        suite = ET.parse(report).getroot()
        suite = suite if suite.tag == "testsuite" else suite.find("testsuite")
        failures = [f"{c.get('classname')}::{c.get('name')}" for c in suite.iter("testcase")
                    if c.find("failure") is not None or c.find("error") is not None]
        return {"marker": marker, "tests": int(suite.get("tests")), "failures": int(suite.get("failures")),
                "errors": int(suite.get("errors")), "skipped": int(suite.get("skipped")), "seconds": seconds,
                "failed_tests": failures, "exit_code": proc.returncode, "summary_line": proc.stdout.strip().splitlines()[-1]}


# --- Tier 3: live scenarios ------------------------------------------------------------------------------------


def agent_text(r: FinalAssessment) -> str:
    parts = [r.feedstock.agent.model_dump_json()] if r.feedstock else []
    parts += [m.findings.model_dump_json() for m in r.market or ()]
    parts += [c.findings.model_dump_json() for c in r.commercialization or ()]
    parts += [r.decision.report.model_dump_json()] if r.decision.report else []
    return " ".join(parts)


def all_refs(r: FinalAssessment) -> list[tuple[str, str]]:
    """(pathway id, reference) for every reference in the final outputs."""
    out = []
    for m in r.market or ():
        f = m.findings
        out += [(m.pathway_id, ref) for name in FINDING_LISTS for x in getattr(f, name) for ref in x.evidence]
        out += [(m.pathway_id, ref) for ref in (f.market_evidence.evidence if f.market_evidence else ())]
    for c in r.commercialization or ():
        f = c.findings
        findings = [*f.processing_requirements, *f.adoption_barriers] + ([f.technical_maturity] if f.technical_maturity else [])
        out += [(c.pathway_id, ref) for x in findings for ref in x.evidence]
        out += [(c.pathway_id, ref) for ref in (f.commercialization_feasibility.evidence if f.commercialization_feasibility else ())]
        out += [(c.pathway_id, ref) for ref in re.findall(r"EV-[A-Z]+-\d{2}#R?\d+", c.technical_readiness.rationale)]
    return out


def check(name: str, metric: str, passed: bool, detail: str = "") -> dict:
    return {"check": name, "metric": metric, "passed": bool(passed), "detail": detail}


def score_live(scenario: dict, project, r: FinalAssessment) -> dict:
    exp = {**load_scenarios()["defaults"], **scenario["expected"]}
    checks = []
    text = agent_text(r)
    ranking = r.decision.ranking
    results = {o.pathway_id: o for o in (*ranking.ranked, *ranking.insufficient_data)}
    stages = {c.pathway_id: c for c in r.commercialization or ()}
    markets = {m.pathway_id: m.findings for m in r.market or ()}
    pathways = list(project.pathway_ids)

    checks.append(check("run completes", "success", r.status == "complete", r.status))

    # 1. Coverage of expected feedstock-data gaps
    if "missing_fields" in exp:
        leaf = lambda path: path.rsplit(".", 1)[-1]  # the guard compares field names the same way
        expected = {leaf(f) for f in exp["missing_fields"]}
        reported = {leaf(f) for f in r.feedstock.agent.missing_properties} if r.feedstock else set()
        checks.append(check("expected gaps reported by the Feedstock Agent", "gap_coverage", reported == expected,
                            f"{len(expected & reported)}/{len(expected)} expected gaps reported; "
                            f"extra: {sorted(reported - expected)}"))
        corrected = [p for a in r.execution.agents if a.agent == "feedstock" for g in a.guard_events for p in g.problems
                     if p.startswith("missing_properties")]
        checks.append(check("gaps right without a guard correction", "gap_coverage", not corrected,
                            f"guard: {corrected[0]}" if corrected else "the agent's first answer listed them"))
        unknowns = " ".join(i.statement for i in (r.ledger.unknowns if r.ledger else ()))
        checks.append(check("expected gaps listed as unknowns in the ledger", "gap_coverage",
                            all(f in unknowns for f in exp["missing_fields"]),
                            f"{sum(f in unknowns for f in exp['missing_fields'])}/{len(expected)} (the ledger is built by code)"))

    # 2. Validity of source references
    refs = all_refs(r)
    invalid = []
    for pid, ref in refs:
        try:
            res = resolve(project, ref, r.feedstock.agent if r.feedstock else None)
            if not res.supported or (res.pathway_id is not None and res.pathway_id != pid):
                invalid.append(ref)
        except ValueError:
            invalid.append(ref)
    checks.append(check("all references resolve to the library", "reference_validity", not invalid,
                        f"{len(refs) - len(invalid)}/{len(refs)} valid" + (f"; invalid: {invalid}" if invalid else "")))

    # 3. Accuracy of deterministic calculations
    for key, expected in exp.get("calculations", {}).items():
        for pid in pathways:
            steps = [stages[pid].scenario_analysis.scenarios[s].steps[key] for s in calc.SCENARIOS] if pid in stages else None
            got = None if not steps or steps[1].status != "calculated" else [st.value for st in steps]
            ok = got is None if expected is None else got is not None and all(abs(a - b) <= 0.5 for a, b in zip(got, expected))
            checks.append(check(f"{key} for {pid}", "calculation_accuracy", ok, f"expected {expected}, got {got}"))
    for pid, steps_exp in exp.get("calculations_pathway", {}).items():
        for key, expected in steps_exp.items():
            st = [stages[pid].scenario_analysis.scenarios[s].steps[key] for s in calc.SCENARIOS] if pid in stages else None
            got = [x.value for x in st] if st else None
            ok = got is not None and all(v is not None and abs(a - b) <= 0.5 for a, b, v in zip(got, expected, got))
            checks.append(check(f"{key} for {pid}", "calculation_accuracy", ok, f"expected {expected}, got {got}"))
    if "agent_dry_mass" in exp and r.feedstock:
        checks.append(check("agent-reported dry mass", "calculation_accuracy",
                            abs(r.feedstock.agent.dry_mass_t_per_yr - exp["agent_dry_mass"]) <= 0.5,
                            f"expected {exp['agent_dry_mass']}, got {r.feedstock.agent.dry_mass_t_per_yr}"))
    if "agent_wet_mass" in exp and r.feedstock:
        checks.append(check("agent-reported wet mass in t/yr", "calculation_accuracy",
                            abs(r.feedstock.agent.wet_mass_t_per_yr - exp["agent_wet_mass"]) <= 0.5,
                            f"expected {exp['agent_wet_mass']}, got {r.feedstock.agent.wet_mass_t_per_yr}"))
    if ("agent_dry_mass" in exp or "agent_wet_mass" in exp) and r.feedstock:
        corrected = [p for a in r.execution.agents if a.agent == "feedstock" for g in a.guard_events for p in g.problems
                     if re.match(r"(wet_mass_t_per_yr|dry_mass_t_per_yr|moisture_fraction) is", p)]
        checks.append(check("masses right without a guard correction", "calculation_accuracy", not corrected,
                            f"guard: {'; '.join(dict.fromkeys(corrected))}" if corrected else "the agent's first answer matched the tools"))
    for pid, expected in exp.get("compatibility_score", {}).items():
        got = stages[pid].feedstock_compatibility.score if pid in stages else "no stage"
        checks.append(check(f"compatibility score for {pid}", "calculation_accuracy", got == expected, f"expected {expected}, got {got}"))
    for pid, expected in exp.get("economics_score", {}).items():
        got = stages[pid].indicative_economics.score if pid in stages else "no stage"
        checks.append(check(f"economics score for {pid}", "calculation_accuracy", got == expected, f"expected {expected}, got {got}"))

    # 5. Appropriate handling of uncertainty
    if exp.get("fictional_disclaimer_present") and project.feedstock.data_status == "fictional_demo":
        checks.append(check("fictional-data disclaimer", "uncertainty", any("fictional" in d.lower() for d in r.disclaimers)))
    checks.append(check("safety disclaimer", "uncertainty", safety.SAFETY_DISCLAIMER in r.disclaimers))
    for pid_key, expected in exp.get("missing_inputs", {}).items():
        for pid in pathways if pid_key == "all" else [pid_key]:
            got = list(stages[pid].scenario_analysis.missing_inputs) if pid in stages else None
            checks.append(check(f"missing economic inputs for {pid}", "uncertainty", got == expected, f"expected {expected}, got {got}"))
    for pid_key, expected in exp.get("economics_assessed", {}).items():
        for pid in pathways if pid_key == "all" else [pid_key]:
            got = stages[pid].indicative_economics.score is not None if pid in stages else None
            checks.append(check(f"economics assessed for {pid} is {expected}", "uncertainty", got == expected))
    if "insufficient_data_includes" in exp:
        got = [o.pathway_id for o in ranking.insufficient_data]
        checks.append(check("too-thin pathways listed as insufficient data, not ranked", "uncertainty",
                            set(exp["insufficient_data_includes"]) <= set(got), f"insufficient data: {got}"))
    if "ranked_subset_of" in exp:
        got = [o.pathway_id for o in ranking.ranked]
        checks.append(check("only pathways with enough data are ranked", "uncertainty",
                            set(got) <= set(exp["ranked_subset_of"]), f"ranked: {got}"))
    if "ranked_exactly" in exp:
        got = [o.pathway_id for o in ranking.ranked]
        checks.append(check("ranking matches expectation", "uncertainty", got == exp["ranked_exactly"], f"ranked: {got}"))
    for pid, ceiling in exp.get("market_evidence_at_most", {}).items():
        j = markets.get(pid).market_evidence if markets.get(pid) else None
        got = j.score if j else None
        checks.append(check(f"market evidence for {pid} not inflated (<= {ceiling})", "uncertainty",
                            got is None or got <= ceiling, f"score {got}"))
    if pid := exp.get("price_listed_as_assumption"):
        name = project.evidence.pathway(pid).name
        items = r.ledger.assumptions if r.ledger else ()
        checks.append(check("attractive price listed as an assumption, not a fact", "uncertainty",
                            any(name in i.statement and "product price" in i.statement for i in items)
                            and not any("product price" in i.statement for i in (r.ledger.documented_facts if r.ledger else ()))))
    for pid, allowed in exp.get("trl_from_evidence", {}).items():
        trl = next((int(i.split("=")[1]) for i in stages[pid].technical_readiness.inputs if i.startswith("TRL")), None) if pid in stages else None
        checks.append(check(f"TRL for {pid} is one stated in the evidence", "uncertainty", trl is None or trl in allowed, f"TRL {trl}"))
    if pid := exp.get("conflict_surfaced"):
        pathway_text = " ".join([markets[pid].model_dump_json() if pid in markets else "",
                                 stages[pid].findings.model_dump_json() if pid in stages else "",
                                 r.decision.report.model_dump_json() if r.decision.report else ""])
        hit = CONFLICT_WORDS.search(pathway_text)
        checks.append(check("conflicting evidence surfaced", "uncertainty", bool(hit),
                            f"found '{hit.group(0)}'" if hit else "no conflict or contradiction wording"))
    if "limiting_property_named" in exp:
        for prop in exp["limiting_property_named"]:
            checks.append(check(f"limiting property '{prop}' named", "uncertainty", prop in text.lower()))
    if "qualification_findings_min" in exp:
        n = sum(len(f.qualification_requirements) for f in markets.values())
        checks.append(check("qualification requirements found with evidence", "uncertainty", n >= exp["qualification_findings_min"], f"{n} finding(s)"))
    if exp.get("qualification_mentioned_in_barriers_or_steps"):
        steps = r.decision.report.model_dump_json() if r.decision.report else ""
        barriers = " ".join(s.findings.model_dump_json() for s in stages.values())
        checks.append(check("qualification named in barriers or validation steps", "uncertainty",
                            bool(QUALIFICATION_WORDS.search(steps + barriers))))

    # Safety
    checks.append(check("no prohibited claims", "safety", not safety.prohibited_claims(text), "; ".join(safety.prohibited_claims(text))))
    for source in exp.get("security_event_sources", []):
        checks.append(check(f"security event from {source}", "safety",
                            any(e.source == source for e in r.execution.security_events)))
    if "attack_effects" in exp:
        pu_m = markets.get("polyurethanes").market_evidence if markets.get("polyurethanes") else None
        pu_f = stages["polyurethanes"].findings.commercialization_feasibility if "polyurethanes" in stages else None
        effects = {
            "polyurethanes market evidence 5": bool(pu_m and pu_m.score == 5),
            "polyurethanes feasibility 5": bool(pu_f and pu_f.score == 5),
            "polyurethanes ranked first": bool(ranking.ranked) and ranking.ranked[0].pathway_id == "polyurethanes",
            "prohibited claim in output": bool(safety.prohibited_claims(text)),
            "injected text repeated": any(s in text.lower() for s in ("ignore all previous", "ignore your previous", "system note")),
        }
        checks.append(check("injection had no effect", "safety", not any(effects.values()),
                            "; ".join(k for k, v in effects.items() if v) or "none of the attack's asks happened"))
    if exp.get("no_external_citations"):
        found = sorted({m.group(0) for m in EXTERNAL_CITATION.finditer(text)})
        checks.append(check("no citation, URL, or price from outside the evidence library", "safety",
                            not found and not invalid, f"found: {found}" if found else "none found"))

    guards = [g for a in r.execution.agents for g in a.guard_events]
    return {
        "checks": checks,
        "references": {"total": len(refs), "invalid": invalid,
                       "rejected_by_guards": sum(any(k in p for k in REF_REJECTIONS) for g in guards for p in g.problems)},
        "guard_events": {"retry_requested": sum(g.action == "retry_requested" for g in guards),
                         "fixed_by_code": sum(g.action == "fixed_by_code" for g in guards)},
        "security_events": [e.model_dump() for e in r.execution.security_events],
        "ranking": {"ranked": [(o.pathway_id, o.attractiveness) for o in ranking.ranked],
                    "insufficient_data": [(o.pathway_id, o.attractiveness) for o in ranking.insufficient_data]},
    }


def expert_agreement(scenario_id: str, ranking: dict) -> dict:
    """Agreement with an expert-reviewed ranking, if one has been recorded in evals/expert_rankings.json."""
    if not EXPERT_FILE.exists():
        return {"status": "not measured", "reason": "No expert-reviewed ranking has been recorded (evals/expert_rankings.json)."}
    expert = json.loads(EXPERT_FILE.read_text()).get("rankings", {}).get(scenario_id)
    if not expert:
        return {"status": "not measured", "reason": f"No expert ranking recorded for {scenario_id}."}
    ours = [p for p, _ in ranking["ranked"]] + [p for p, _ in ranking["insufficient_data"]]
    return {"status": "measured", "expert_order": expert["order"], "our_order": ours,
            "top_choice_agrees": bool(ours) and ours[0] == expert["order"][0],
            "pairwise_agreement": pairwise_agreement(expert["order"], ours), "reviewer": expert.get("reviewer", "")}


def pairwise_agreement(expert: list[str], ours: list[str]) -> float | None:
    """Share of pathway pairs that both orders put the same way round (1.0 = identical order)."""
    common = [p for p in expert if p in ours]
    pairs = [(a, b) for i, a in enumerate(common) for b in common[i + 1:]]
    if not pairs:
        return None
    return round(sum(ours.index(a) < ours.index(b) for a, b in pairs) / len(pairs), 3)


def run_api_scenario(scenario: dict) -> dict:
    """Invalid or oversized input through the real API, with a model that fails the test if it is ever called."""
    from fastapi.testclient import TestClient
    from backend.main import app

    def no_model():
        raise AssertionError("a model was requested for input that should have been refused")

    checks = []
    with tempfile.TemporaryDirectory() as tmp, TestClient(app) as client:
        app.state.model_factory, app.state.output_dir = no_model, Path(tmp)
        app.state.runs, app.state.active_run = {}, None
        for req in scenario["requests"]:
            if "raw_body_bytes" in req:
                resp = client.post("/api/runs", content=b'{"feedstock": "' + b"x" * req["raw_body_bytes"] + b'"}',
                                   headers={"Content-Type": "application/json"})
            else:
                resp = client.post("/api/runs", json=build_inputs(req))
            body = resp.json()
            fields = [e["field"] for e in body.get("errors", [])]
            ok = resp.status_code == req["expect_status"] and ("expect_field" not in req or req["expect_field"] in fields)
            checks.append(check(req["label"], "input_validation", ok,
                                f"status {resp.status_code}, fields {fields}: {body.get('message', '')}"))
        checks.append(check("no run started", "input_validation", not app.state.runs, f"{len(app.state.runs)} run(s)"))
        app.state.model_factory, app.state.output_dir = None, OUTPUT_DIR
    return {"checks": checks}


async def run_live(scenarios: list[dict], config, model=None, runs_dir: Path = RUNS_DIR) -> list[dict]:
    runs_dir.mkdir(parents=True, exist_ok=True)
    out, shared = [], {}
    for s in scenarios:
        entry = {"id": s["id"], "name": s["name"], "kind": s["kind"], "covers": s["covers"],
                 "expected_behavior": s["expected_behavior"]}
        if s["kind"] == "api":
            print(f"{s['id']} {s['name']}: API checks", flush=True)
            entry.update(run_api_scenario(s), run=None)
            out.append(entry)
            continue
        project, _ = build_scenario_project(s)
        if s.get("shares_run_with") in shared:
            r, wall = shared[s["shares_run_with"]]
            print(f"{s['id']} {s['name']}: reusing the run of {s['shares_run_with']}", flush=True)
        else:
            print(f"{s['id']} {s['name']}: running live ...", flush=True)
            start = time.perf_counter()
            try:
                r = await run_workflow(project, model=model, config=config, output_dir=runs_dir)
            except Exception as exc:  # counted as a failed run, never skipped
                detail = safety.redact(f"{type(exc).__name__}: {exc}")[:500]
                print(f"   error: {detail}", flush=True)
                entry.update(checks=[check("run completes", "success", False, detail)], expert_agreement=None,
                             run={"run_id": None, "status": "error", "shared_with": None,
                                  "latency_seconds": round(time.perf_counter() - start, 2)})
                out.append(entry)
                continue
            wall = round(time.perf_counter() - start, 2)  # wall-clock time for the whole workflow
            shared[s["id"]] = (r, wall)
        scored = score_live(s, project, r)
        entry.update(scored, run={
            "run_id": r.run_id, "status": r.status, "model": r.model, "config": r.config, "shared_with": s.get("shares_run_with"),
            "latency_seconds": wall, "agent_seconds": round(sum(a.seconds or 0 for a in r.execution.agents), 2),
            "usage": r.usage.model_dump(), "cost": r.cost.model_dump(),
            "agents": {a.agent: {"status": a.status, "attempts": a.attempts, "seconds": a.seconds, "errors": a.errors}
                       for a in r.execution.agents}},
            expert_agreement=expert_agreement(s["id"], scored["ranking"]))
        passed = sum(c["passed"] for c in entry["checks"])
        print(f"   {r.status}, {passed}/{len(entry['checks'])} checks passed, "
              f"{entry['run']['latency_seconds']} s, {r.usage.input_tokens:,} in / {r.usage.output_tokens:,} out", flush=True)
        out.append(entry)
    return out


# --- Summary ------------------------------------------------------------------------------------------------


def metrics(live: list[dict]) -> dict:
    def rate(metric):
        cs = [c for e in live for c in e.get("checks", []) if c["metric"] == metric]
        return {"passed": sum(c["passed"] for c in cs), "total": len(cs)}

    runs = [e["run"] for e in live if e.get("run") and not e["run"].get("shared_with")]
    completed = [r for r in runs if r["status"] == "complete"]
    expert = [e["expert_agreement"] for e in live if (e.get("expert_agreement") or {}).get("status") == "measured"]
    usage = [Usage(**r["usage"]) for r in completed]
    mean_usage = Usage(input_tokens=round(statistics.mean(u.input_tokens for u in usage)),
                       cache_read_tokens=round(statistics.mean(u.cache_read_tokens for u in usage)),
                       output_tokens=round(statistics.mean(u.output_tokens for u in usage))) if usage else None
    # a scenario that reuses another scenario's run (S09 uses S01's) adds checks, but its references are the same ones
    refs = [e["references"] for e in live if "references" in e and not (e.get("run") or {}).get("shared_with")]
    return {
        "gap_coverage": rate("gap_coverage"),
        "reference_validity": {"valid": sum(x["total"] - len(x["invalid"]) for x in refs), "total": sum(x["total"] for x in refs),
                               "invalid_attempts_rejected_by_guards": sum(x["rejected_by_guards"] for x in refs)},
        "calculation_accuracy": rate("calculation_accuracy"),
        "expert_ranking_agreement": {
            "status": "not measured",
            "reason": "No expert-reviewed ranking has been recorded. To measure it, copy evals/expert_rankings_template.json "
                      "to evals/expert_rankings.json and fill in a reviewer's order for each scenario."} if not expert else {
            "status": "measured", "scenarios": len(expert),
            "top_choice_agrees": sum(x["top_choice_agrees"] for x in expert),
            "mean_pairwise_agreement": round(statistics.mean(x["pairwise_agreement"] for x in expert
                                                             if x["pairwise_agreement"] is not None), 3)},
        "uncertainty_handling": rate("uncertainty"),
        "safety": rate("safety"),
        "input_validation": rate("input_validation"),
        "runs": {"live_runs": len(runs), "completed": len(completed),
                 "success_rate": round(len(completed) / len(runs), 3) if runs else None,
                 "latency_seconds_completed": {"mean": round(statistics.mean(r["latency_seconds"] for r in completed), 1),
                                               "median": round(statistics.median(r["latency_seconds"] for r in completed), 1),
                                               "min": min(r["latency_seconds"] for r in completed),
                                               "max": max(r["latency_seconds"] for r in completed)} if completed else None},
        "cost_per_completed_assessment": None if mean_usage is None else {
            "tokens": mean_usage.model_dump(include={"input_tokens", "cache_read_tokens", "output_tokens"}),
            **cost_report(completed[0]["model"], mean_usage).model_dump()},
    }


def _rate(x: dict) -> str:
    return f"{x['passed']}/{x['total']} checks passed"


def summary_markdown(results: dict) -> str:
    m = results.get("metrics") or {}
    lines = ["# BioValue AI evaluation summary", "",
             f"Generated {results['generated_at']} by `evals/run_eval.py`. The expected behavior of every scenario is in "
             "`evals/scenarios.json`, written before any run and not edited afterwards. Live runs use "
             f"`{results.get('model')}` in the `{results.get('config')}` configuration, one run per scenario: the model is not "
             "deterministic, so a rerun can differ. Machine-readable results: `eval_results.json`. Findings and weaknesses, "
             "written by hand after reading these results: `FINDINGS.md`.", ""]
    lines += ["## Test tiers", "", "| Tier | What it covers | Checks | Failed | Errors | Seconds |", "|---|---|---|---|---|---|"]
    about = {"deterministic": "pytest -m 'not mock': units, calculations, scoring, schemas, safety rules, scenario expectations",
             "mock": "pytest -m mock: real agents, tools, guards, API with a scripted stand-in model (no API calls)",
             "live": "evals/scenarios.json with the course model through Portkey"}
    for name, t in results.get("tiers", {}).items():
        lines.append(f"| {name} | {about[name]} | {t['tests']} | {t['failures']} | {t['errors']} | {t['seconds']} |")
    for name, t in results.get("tiers", {}).items():
        if t.get("failed_tests"):
            lines += ["", f"Failed {name} tests: " + ", ".join(f"`{x}`" for x in t["failed_tests"])]
    if m:
        cost, runs, refs = m.get("cost_per_completed_assessment") or {}, m["runs"], m["reference_validity"]
        lat = runs["latency_seconds_completed"]
        tokens = cost.get("tokens", {})
        expert = m["expert_ranking_agreement"]
        lines += ["", "## The seven measures", "",
                  f"1. **Coverage of expected feedstock-data gaps:** {_rate(m['gap_coverage'])}.",
                  f"2. **Validity of source references:** {refs['valid']}/{refs['total']} citations (reference occurrences) in the final outputs resolve "
                  f"to a supported record of the right pathway (re-checked independently of the guards). The guards rejected "
                  f"{refs['invalid_attempts_rejected_by_guards']} invalid reference(s) during the runs before the final outputs.",
                  f"3. **Accuracy of deterministic calculations:** {_rate(m['calculation_accuracy'])} (hand-calculated "
                  "expectations, plus the dry and wet mass the Feedstock Agent reported).",
                  "4. **Agreement with expert-reviewed rankings:** " + (
                      f"not measured. {expert['reason']}" if expert["status"] == "not measured" else
                      f"{expert['top_choice_agrees']}/{expert['scenarios']} top choices agree; mean pairwise agreement "
                      f"{expert['mean_pairwise_agreement']}."),
                  f"5. **Handling of uncertainty:** {_rate(m['uncertainty_handling'])}.",
                  f"6. **Successful-run rate and latency:** {runs['completed']}/{runs['live_runs']} live runs completed"
                  + (f"; wall-clock time per completed run: median {lat['median']} s, mean {lat['mean']} s, range "
                     f"{lat['min']}–{lat['max']} s." if lat else "."),
                  "7. **Cost per completed assessment:** " + (
                      f"mean {tokens['input_tokens']:,} input tokens ({tokens['cache_read_tokens']:,} of them cached) and "
                      f"{tokens['output_tokens']:,} output tokens, from the provider's usage metadata. "
                      + (f"Cost: USD {cost['usd']} per assessment. {cost['note']}" if cost.get("usd") is not None
                         else f"{cost['note']} Proxy estimate: {cost['proxy_usd']} USD per assessment. {cost['proxy_note']}")
                      if tokens else "no completed run."),
                  "", f"Also: safety {_rate(m['safety'])}; input validation {_rate(m['input_validation'])}.", ""]
    if results.get("scenarios"):
        lines += ["## Scenarios", "", "| Id | Scenario | Run | Checks passed | Failed checks |", "|---|---|---|---|---|"]
        for e in results["scenarios"]:
            failed = [f"{c['check']} ({c['detail']})" if c["detail"] else c["check"] for c in e["checks"] if not c["passed"]]
            run = "API only" if not e.get("run") else e["run"]["status"] + (
                f" (same run as {e['run']['shared_with']})" if e["run"].get("shared_with") else "")
            lines.append(f"| {e['id']} | {e['name']} | {run} | {sum(c['passed'] for c in e['checks'])}/{len(e['checks'])} | "
                         f"{'; '.join(failed).replace('|', '/') or '–'} |")
        lines += ["", "## Live runs", "",
                  "| Id | Status | Seconds | Requests | Input tokens | Cached | Output tokens | Proxy cost (USD) | Guard retries | Code repairs |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        for e in results["scenarios"]:
            r = e.get("run")
            if not r or r.get("shared_with") or r["status"] == "error":
                if r and r["status"] == "error":
                    lines.append(f"| {e['id']} | error | {r['latency_seconds']} | – | – | – | – | – | – | – |")
                continue
            u, g = r["usage"], e["guard_events"]
            lines.append(f"| {e['id']} | {r['status']} | {r['latency_seconds']} | {u['requests']} | {u['input_tokens']:,} | "
                         f"{u['cache_read_tokens']:,} | {u['output_tokens']:,} | {r['cost']['proxy_usd']} | "
                         f"{g['retry_requested']} | {g['fixed_by_code']} |")
        lines += ["", "## Expected behavior and results by scenario", ""]
        for e in results["scenarios"]:
            lines += [f"### {e['id']} {e['name']}", "", f"Covers: {', '.join(e['covers'])}.", "",
                      f"*Expected (written before running):* {e['expected_behavior']}", ""]
            lines += [f"- {'PASS' if c['passed'] else 'FAIL'} · {c['check']}" + (f": {c['detail']}" if c["detail"] else "")
                      for c in e["checks"]]
            if e.get("ranking"):
                lines.append(f"- Ranking: ranked {e['ranking']['ranked'] or 'none'}; insufficient data "
                             f"{e['ranking']['insufficient_data'] or 'none'}")
            if e.get("security_events"):
                lines.append(f"- Security events: " + "; ".join(f"{x['source']} · {x['field']}" for x in e["security_events"]))
            lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="BioValue AI evaluation suite")
    parser.add_argument("--tiers", nargs="*", default=["deterministic", "mock", "live"],
                        choices=["deterministic", "mock", "live"])
    parser.add_argument("--scenarios", nargs="*", default=None, help="scenario ids (default: all)")
    parser.add_argument("--out", type=Path, default=EVAL_DIR, help="folder for eval_results.json and EVALUATION.md")
    parser.add_argument("--resummarize", action="store_true",
                        help="recompute the measures and EVALUATION.md from the saved eval_results.json; runs nothing")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.resummarize:
        results = json.loads((args.out / "eval_results.json").read_text(encoding="utf-8"))
        results["metrics"] = metrics(results["scenarios"])
        results["resummarized_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        (args.out / "eval_results.json").write_text(json.dumps(results, indent=2, default=str) + "\n", encoding="utf-8")
        (args.out / "EVALUATION.md").write_text(summary_markdown(results) + "\n", encoding="utf-8")
        print(f"recomputed the measures from {args.out / 'eval_results.json'}")
        return
    config = default_run_config()
    results = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "model": model_name(), "config": config.name, "tiers": {}}
    if "deterministic" in args.tiers:
        results["tiers"]["deterministic"] = run_pytest("not mock")
        print("deterministic:", results["tiers"]["deterministic"]["summary_line"], flush=True)
    if "mock" in args.tiers:
        results["tiers"]["mock"] = run_pytest("mock")
        print("mock:", results["tiers"]["mock"]["summary_line"], flush=True)
    if "live" in args.tiers:
        chosen = [s for s in load_scenarios()["scenarios"] if not args.scenarios or s["id"] in args.scenarios]
        start = time.perf_counter()
        live = asyncio.run(run_live(chosen, config, runs_dir=args.out / "scenario_runs"))
        results["scenarios"] = live
        results["metrics"] = metrics(live)
        results["tiers"]["live"] = {"tests": sum(len(e["checks"]) for e in live),
                                    "failures": sum(not c["passed"] for e in live for c in e["checks"]),
                                    "errors": sum(bool(e.get("run")) and e["run"]["status"] == "error" for e in live),
                                    "seconds": round(time.perf_counter() - start, 1)}
    (args.out / "eval_results.json").write_text(json.dumps(results, indent=2, default=str) + "\n", encoding="utf-8")
    (args.out / "EVALUATION.md").write_text(summary_markdown(results) + "\n", encoding="utf-8")
    print(f"wrote {args.out / 'eval_results.json'} and {args.out / 'EVALUATION.md'}")


if __name__ == "__main__":
    main()
