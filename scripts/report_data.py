"""Data, formatting helpers, and shared pieces for build_report.py.

Everything numeric in the report and slides is read here from files the application and the evaluation wrote:
    output/evaluation/eval_results.json   evaluation suite (phase 5)
    output/evaluation/results.json        baseline vs optimized comparison (phase 4)
    output/cost_estimate.json             monthly estimates from the phase-4 runs
    output/latest_assessment.json         the dashboard's demo run shown in the screenshots
    output/runs/<id>.json                 the dashboard's latest prompt-injection run (found automatically)
    output/submission_links.json          repo / app / video links (filled in by hand)
    output/user_test_results.json         the real user test (filled in by hand; "pending" until then)
    data/*.json                           demo feedstock, scoring configuration, evidence library
Nothing is typed in by hand except the prose.
"""

import base64
import html
import json
import shutil
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import data as app_data, tokenomics  # noqa: E402
from backend.agents import AGENT_ORDER, AGENT_TITLES, AGENT_TOOLS  # noqa: E402
from backend.agents.agents import OPTIMIZED_EXTRA_TOOLS  # noqa: E402
from backend.agents.refs import resolve  # noqa: E402
from backend.trace import Usage  # noqa: E402

OUT = ROOT / "output"
SHOTS = OUT / "screenshots"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


E = load(OUT / "evaluation" / "eval_results.json")
P4 = load(OUT / "evaluation" / "results.json")
COST = load(OUT / "cost_estimate.json")
A = load(OUT / "latest_assessment.json")
LINKS = load(OUT / "submission_links.json")
UT = load(OUT / "user_test_results.json")


def _latest_injection_run() -> dict:
    """The newest saved dashboard run with the report's model in which the feedstock screen removed injected text."""
    for f in sorted((OUT / "runs").glob("run-*.json"), reverse=True):
        if f.name.endswith(".inputs.json"):
            continue
        r = load(f)
        if r.get("model") == A["model"] and any(e["source"] == "feedstock input" for e in r["execution"].get("security_events", [])):
            return r
    raise FileNotFoundError("no dashboard run with a feedstock-input security event; run the injection demo first")


INJ = _latest_injection_run()
INJECTION_RUN = INJ["run_id"]
SC = load(ROOT / "data" / "scoring_config.json")
FS = load(ROOT / "data" / "demo_feedstock.json")
LIB = load(ROOT / "data" / "evidence_library.json")
SCN = load(ROOT / "evals" / "scenarios.json")
PROJECT = app_data.project()
M = E["metrics"]


# --- formatting -------------------------------------------------------------------------------------------------

def esc(x) -> str:
    return html.escape(str(x), quote=True)


def n(x, digits=0) -> str:
    if x is None:
        return "–"
    return f"{x:,.{digits}f}"


def pct(x, digits=0) -> str:
    return f"{x * 100:.{digits}f}%"


def usd(x, digits=4) -> str:
    return f"USD {x:,.{digits}f}"


def claim(ref: str) -> str:
    """The library's wording for a claim or requirement, without its quoted support."""
    r = resolve(PROJECT, ref)
    rec = PROJECT.evidence.record(r.record_id)
    if r.kind == "requirement":
        idx = int(ref.split("#R")[1]) - 1
        item = rec.technical_requirements[idx]
        return f"{item.parameter}: {item.requirement}"
    return rec.claims[int(ref.split("#")[1]) - 1].text


def table(headers, rows, cls="", num_cols=()) -> str:
    th = "".join(f'<th class="{"num" if i in num_cols else ""}">{h}</th>' for i, h in enumerate(headers))
    body = "".join("<tr>" + "".join(f'<td class="{"num" if i in num_cols else ""}">{c}</td>' for i, c in enumerate(r)) + "</tr>"
                   for r in rows)
    return f'<table class="{cls}"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>'


# --- images -------------------------------------------------------------------------------------------------------

_TMP = Path(tempfile.mkdtemp(prefix="biovalue-report-"))


def img_uri(name: str, quality: int = 82) -> str:
    """A screenshot as a data URI, so report.html and slides.html are single self-contained files. JPEG keeps the
    files small; PNG is used if the macOS `sips` tool isn't available."""
    src = SHOTS / f"{name}.png"
    if not src.exists():
        raise FileNotFoundError(f"missing screenshot {src}; run: node scripts/capture_screenshots.mjs")
    if shutil.which("sips"):
        dst = _TMP / f"{name}.jpg"
        if not dst.exists():
            subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", str(quality), str(src), "--out", str(dst)],
                           check=True, capture_output=True)
        return "data:image/jpeg;base64," + base64.b64encode(dst.read_bytes()).decode()
    return "data:image/png;base64," + base64.b64encode(src.read_bytes()).decode()


def figure(name: str, caption: str, width: str = "100%", cls: str = "") -> str:
    return (f'<figure class="{cls}"><img src="{img_uri(name)}" alt="{esc(caption)}" style="width:{width}">'
            f"<figcaption>{caption}</figcaption></figure>")


# --- derived figures ----------------------------------------------------------------------------------------------

def scenarios():
    return E["scenarios"]


def live_runs():
    return [e for e in scenarios() if e.get("run") and not e["run"].get("shared_with")]


def check_totals():
    cs = [c for e in scenarios() for c in e["checks"]]
    return sum(c["passed"] for c in cs), len(cs)


def mean_usage() -> Usage:
    us = [Usage(**e["run"]["usage"]) for e in live_runs() if e["run"]["status"] == "complete"]
    return Usage(input_tokens=round(statistics.mean(u.input_tokens for u in us)),
                 cache_read_tokens=round(statistics.mean(u.cache_read_tokens for u in us)),
                 output_tokens=round(statistics.mean(u.output_tokens for u in us)))


def monthly_from_suite():
    """Monthly model-cost projection from the evaluation suite's mean tokens, at the labelled proxy price."""
    a = tokenomics.assumptions()
    price = tokenomics.proxy_price()
    per = mean_usage()
    return a, price, per, [tokenomics.monthly_estimate(per, users, a["assessments_per_user_per_month"], price)
                           for users in a["user_counts"]]


def p4_means():
    """Phase-4 means per configuration over the three comparable cases (the unscreened injection case excluded)."""
    out = {}
    for cfg in ("baseline", "optimized"):
        rows = [r for r in P4 if r["config"] == cfg and r["case"] != "injection_unscreened" and r["status"] == "complete"]
        out[cfg] = {k: statistics.mean(r["total"][k] for r in rows) for k in ("input_tokens", "cache_read_tokens", "output_tokens")}
        out[cfg]["proxy_usd"] = statistics.mean(r["proxy_cost_usd"] for r in rows)
        out[cfg]["median_latency"] = statistics.median(r["total"]["latency_seconds"] for r in rows)
        out[cfg]["runs"] = len(rows)
    return out


def ranking_rows(assessment):
    r = assessment["decision"]["ranking"]
    return [*r["ranked"], *r["insufficient_data"]]


def judgment_spread():
    """Distinct analyst scores per pathway and criterion across the suite's live runs."""
    spread = {}
    for e in live_runs():
        a = load(OUT / "evaluation" / "scenario_runs" / "runs" / f"{e['run']['run_id']}.json")
        for o in ranking_rows(a):
            for c in o["criteria"]:
                if c["method"] == "analyst":
                    spread.setdefault((o["name"], c["label"]), {}).setdefault(c["score"], []).append(e["id"])
    return spread


# --- shared visuals -------------------------------------------------------------------------------------------------

def agent_diagram() -> str:
    """The fixed four-agent sequence with each agent's tools, from the code's own tool lists."""
    boxes = []
    for i, a in enumerate(AGENT_ORDER, 1):
        tools = [t.__name__ for t in AGENT_TOOLS[a]] + [t.__name__ + "*" for t in OPTIMIZED_EXTRA_TOOLS.get(a, ())]
        boxes.append(f'<div class="agent"><div class="agent-num">{i}</div><div class="agent-name">{esc(AGENT_TITLES[a])}</div>'
                     f'<div class="agent-tools">{"".join(f"<code>{esc(t)}</code>" for t in tools)}</div></div>')
    flow = '<div class="arrow">→</div>'.join(boxes)
    return f"""<div class="diagram">
  <div class="layer"><div class="layer-label">Dashboard</div><div class="pill">React + Vite · nine sections · input validation</div>
    <div class="arrow-down">↓ JSON over HTTP</div><div class="pill">FastAPI · size limits · one run at a time · HTML/Markdown export</div></div>
  <div class="arrow-down">↓ validated project (feedstock, economic assumptions, evidence library)</div>
  <div class="flow">{flow}</div>
  <div class="arrow-down">↑ every tool call runs tested Python; every answer passes schema validation and guards ↑</div>
  <div class="core">
    <div><strong>Deterministic core</strong><br>units · dry mass · scenarios · economics · compatibility · TRL mapping · scoring and ranking</div>
    <div><strong>Evidence library</strong><br>{len(LIB["records"])} verified records · {sum(len(r["claims"]) for r in LIB["records"])} supported claims · quality labels</div>
    <div><strong>Guards and trace</strong><br>references · numbers · prohibited claims · injection screen · budget · audit and usage logs</div>
  </div>
  <p class="note">* only in the optimized configuration. Model: {esc(A["model"])} through Portkey (PydanticAI).</p>
</div>"""


def token_chart(width=640) -> str:
    """Input tokens per run, baseline vs optimized, for each phase-4 case. Emphasis encoding: optimized in the accent
    hue, baseline in neutral gray; a legend and direct value labels, so identity never rests on color alone."""
    cases = list(dict.fromkeys(r["case"] for r in P4))
    vals = {(r["case"], r["config"]): r["total"]["input_tokens"] for r in P4}
    top = 120_000
    left, right, row_h, bar_h, gap = 150, 70, 34, 11, 3
    plot_w = width - left - right
    height = 40 + len(cases) * row_h + 26
    x = lambda v: left + v / top * plot_w
    parts = [f'<svg viewBox="0 0 {width} {height}" class="chart" role="img" aria-label="Input tokens per run by case and configuration">']
    parts.append(f'<g class="legend"><rect x="{left}" y="6" width="10" height="10" rx="2" class="c-base"/><text x="{left + 16}" y="15">baseline</text>'
                 f'<rect x="{left + 90}" y="6" width="10" height="10" rx="2" class="c-opt"/><text x="{left + 106}" y="15">optimized</text></g>')
    for t in range(0, top + 1, 30_000):
        parts.append(f'<line x1="{x(t):.1f}" x2="{x(t):.1f}" y1="30" y2="{height - 22}" class="grid"/>'
                     f'<text x="{x(t):.1f}" y="{height - 6}" class="tick" text-anchor="middle">{t // 1000}k</text>')
    for i, case in enumerate(cases):
        y0 = 36 + i * row_h
        parts.append(f'<text x="{left - 10}" y="{y0 + bar_h + 2}" class="label" text-anchor="end">{esc(case.replace("_", " "))}</text>')
        for j, cfg in enumerate(("baseline", "optimized")):
            v = vals[(case, cfg)]
            y = y0 + j * (bar_h + gap)
            w = x(v) - left
            r = min(4, w / 2)
            path = (f"M{left},{y} h{w - r:.1f} a{r},{r} 0 0 1 {r},{r} v{bar_h - 2 * r} a{r},{r} 0 0 1 {-r},{r} h{-(w - r):.1f} z")
            parts.append(f'<path d="{path}" class="{"c-base" if cfg == "baseline" else "c-opt"}"><title>{esc(case)} · {cfg}: {v:,} input tokens</title></path>'
                         f'<text x="{x(v) + 5:.1f}" y="{y + bar_h - 1}" class="value">{v / 1000:.1f}k</text>')
    parts.append(f'<line x1="{left}" x2="{left}" y1="30" y2="{height - 22}" class="axis"/></svg>')
    return "".join(parts)


BASE_CSS = """
:root { --bg:#f7f6f3; --paper:#fdfcfa; --ink:#1f2328; --ink-2:#3d434b; --muted:#6b7280; --line:#e4e1db; --soft:#efede8;
  --accent:#2e6ea0; --accent-soft:#e6eef5; --good:#2f7d4f; --warn:#a86b12; --bad:#a63d32; }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font: 15px/1.6 -apple-system, "Segoe UI", "Helvetica Neue", Helvetica, Arial, sans-serif; }
code { font: 0.86em/1.4 ui-monospace, "SF Mono", Menlo, Consolas, monospace; background: var(--soft); padding: 1px 4px; border-radius: 3px; }
table { border-collapse: collapse; width: 100%; font-size: 0.86em; margin: 10px 0 16px; }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--line); vertical-align: top; }
th { font-weight: 600; color: var(--ink-2); background: var(--soft); }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.pass { color: var(--good); font-weight: 600; } .fail { color: var(--bad); font-weight: 600; } .na { color: var(--warn); font-weight: 600; }
.diagram { border: 1px solid var(--line); border-radius: 10px; padding: 14px; background: var(--paper); font-size: 0.82em; }
.layer { text-align: center; } .pill { display:inline-block; border:1px solid var(--line); border-radius: 999px; padding: 4px 12px; background:#fff; }
.layer-label { font-weight: 600; color: var(--muted); font-size: 0.85em; text-transform: uppercase; letter-spacing: .06em; margin-bottom: 4px; }
.arrow-down { text-align:center; color: var(--muted); margin: 6px 0; font-size: 0.92em; }
.flow { display: flex; align-items: stretch; gap: 4px; }
.flow .arrow { align-self: center; color: var(--accent); font-size: 1.3em; }
.agent { flex: 1; border: 1px solid var(--accent); border-radius: 8px; padding: 8px; background: #fff; }
.agent-num { display:inline-block; width: 20px; height: 20px; border-radius: 50%; background: var(--accent); color:#fff; text-align:center; font-size: 0.8em; line-height: 20px; }
.agent-name { font-weight: 600; margin: 4px 0; }
.agent-tools code { display: block; margin: 2px 0; font-size: 0.78em; background: var(--accent-soft); }
.core { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.core > div { border: 1px solid var(--line); border-radius: 8px; padding: 8px; background: var(--soft); }
.diagram .note { color: var(--muted); font-size: 0.9em; margin: 8px 0 0; }
svg.chart { width: 100%; height: auto; font-size: 11px; }
svg.chart .c-opt { fill: var(--accent); } svg.chart .c-base { fill: #a3a7ad; }
svg.chart .grid { stroke: var(--line); stroke-width: 1; } svg.chart .axis { stroke: #b9b5ad; stroke-width: 1; }
svg.chart text { fill: var(--ink-2); } svg.chart .tick, svg.chart .value { fill: var(--muted); }
svg.chart path:hover { opacity: .8; }
"""


def agent_means() -> dict:
    """Mean input and output tokens per agent across the evaluation suite's completed live runs."""
    totals = {}
    for e in live_runs():
        if e["run"]["status"] != "complete":
            continue
        a = load(OUT / "evaluation" / "scenario_runs" / "runs" / f"{e['run']['run_id']}.json")
        for ag in a["execution"]["agents"]:
            totals.setdefault(ag["agent"], []).append((ag["usage"]["input_tokens"], ag["usage"]["output_tokens"]))
    return {k: (statistics.mean(x for x, _ in v), statistics.mean(y for _, y in v)) for k, v in totals.items()}
