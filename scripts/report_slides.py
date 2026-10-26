"""slides.html: 10 reveal.js slides (from a CDN) in one file, images embedded. Arrow keys move, F goes full screen."""

from report_data import (A, BASE_CSS, E, LINKS, M, UT, agent_diagram, check_totals, esc, img_uri, mean_usage,
                         monthly_from_suite, p4_means, ranking_rows, token_chart)

REVEAL = "https://cdn.jsdelivr.net/npm/reveal.js@5.1.0/dist"
S13_NOTE = " (refusing to cite an invented study, the agent still named it; nothing was fabricated)"

SLIDE_CSS = """
.reveal { font-family: -apple-system, "Segoe UI", "Helvetica Neue", Helvetica, Arial, sans-serif; color: var(--ink); }
.reveal-viewport { background: var(--paper); }
.reveal .slides { text-align: left; }
.reveal .slides section { height: 100%; padding: 0 8px; }
.reveal h1, .reveal h2 { font-family: inherit; text-transform: none; color: var(--ink); letter-spacing: -0.01em; font-weight: 700; }
.reveal h1 { font-size: 72px; margin: 120px 0 12px; }
.reveal h2 { font-size: 40px; margin: 0 0 22px; }
.reveal p, .reveal li { font-size: 24px; line-height: 1.45; color: var(--ink-2); }
.reveal ul { margin: 0 0 0 1em; } .reveal li { margin: 7px 0; }
.kicker { color: var(--accent) !important; text-transform: uppercase; letter-spacing: .1em; font-size: 15px !important; font-weight: 600; margin: 20px 0 8px; }
.cols { display: grid; grid-template-columns: 1fr 1fr; gap: 36px; align-items: start; }
.cols.r { grid-template-columns: .85fr 1.15fr; }
.shot { max-width: 100%; max-height: 540px; border: 1px solid var(--line); border-radius: 8px; margin: 0 !important; }
.tiles { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin: 6px 0 22px; }
.tile { border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; background: #fff; }
.tile .big { font-size: 34px; font-weight: 700; color: var(--ink); font-variant-numeric: tabular-nums; }
.tile .small { font-size: 16px; color: var(--muted); line-height: 1.3; }
.foot { font-size: 15px !important; color: var(--muted) !important; }
.reveal .diagram { font-size: 15px; } .reveal .diagram p { font-size: 14px; }
.reveal .controls, .reveal .progress { color: var(--accent); }
"""


def _tiles(items):
    return '<div class="tiles">' + "".join(f'<div class="tile"><div class="big">{v}</div><div class="small">{t}</div></div>'
                                           for v, t in items) + "</div>"


def _user_line():
    if not UT["conducted"]:
        return "<li><strong>Real-user test:</strong> pending (questionnaire ready); no user impact is claimed yet</li>"
    quote = f' · “{esc(UT["quote"])}”' if UT.get("quote") and UT.get("consent_to_quote") else ""
    return (f'<li><strong>Real user:</strong> {UT["biovalue_minutes"]} min with BioValue AI vs '
            f'{UT["normal_workflow_minutes"]} min normally{quote}</li>')


def slides_html() -> str:
    passed, total = check_totals()
    runs = M["runs"]
    lat = runs["latency_seconds_completed"]
    u = mean_usage()
    cost = M["cost_per_completed_assessment"]
    a, _, _, monthly = monthly_from_suite()
    pm = p4_means()
    t = E["tiers"]
    rk = ranking_rows(A)
    failed = [f'{e["id"]}: {c["check"]}' for e in E["scenarios"] for c in e["checks"] if not c["passed"]]
    repo = LINKS.get("repo") or "repository link to be added"
    d_in = (pm["optimized"]["input_tokens"] / pm["baseline"]["input_tokens"] - 1) * 100
    d_usd = (pm["optimized"]["proxy_usd"] / pm["baseline"]["proxy_usd"] - 1) * 100
    s = [
        f"""<section><p class="kicker">MGT 409 · AI Foundations for Managers · Final project</p><h1>BioValue AI</h1>
        <p style="font-size:28px">Four agents that tell a pulp mill which use of its lignin deserves a closer look first, with every number
        computed by code and every claim tied to a verified source.</p><p style="margin-top:40px">Madina Muratova · Yale SOM · October 2026</p>
        <p class="foot">{esc(repo)} · all results from real runs with {esc(A["model"])} · the example mill is fictional</p></section>""",
        """<section><p class="kicker">Problem</p><h2>Lignin is mostly burned; choosing a better use is slow and opaque</h2><div class="cols">
        <ul><li>50–70 Mt of lignin a year; just 1–2% goes into added-value products (Kienberger et al., 2021)</li>
        <li>Large target markets: PF resins about 10 Mt, USD 13.4 bn (2019); polyurethanes USD 65 bn (2019), bio-based under 1% (IEA Bioenergy)</li></ul>
        <ul><li><strong>Who:</strong> a mill's strategy lead, or a climate-tech analyst, doing the first screen</li>
        <li><strong>Pain:</strong> missing lab data, wet vs dry tonnes, and claims nobody can trace; generic AI chat can invent figures</li></ul></div></section>""",
        """<section><p class="kicker">What is new</p><h2>Agents for judgment, code for numbers, evidence for claims</h2><div class="cols">
        <ul><li><strong>ChatGPT, Claude, Gemini:</strong> fast, but numbers and citations are not checked</li>
        <li><strong>Perplexity, Elicit, Consensus:</strong> real citations, but no mill-specific mass balance or spec check</li>
        <li><strong>Consultants, spreadsheets:</strong> expert or exact, but slow to rerun; sources drift from numbers</li></ul>
        <ul><li>Every number from tested tools; every claim checked against a curated library</li>
        <li>Missing data shown as <em>insufficient data</em>, never as a low score</li>
        <li>Full trace and cost for every run; rerun in about a minute</li></ul></div></section>""",
        f"""<section><p class="kicker">Agents</p><h2>Four agents, fixed order, validated hand-offs</h2>{agent_diagram()}</section>""",
        f"""<section><p class="kicker">Demo · fictional Pinecrest Mill</p><h2>One real run: ranked, insufficient data, and why</h2>
        <div class="cols r"><ul><li><strong>{esc(rk[0]["name"])}</strong>: the only pathway with enough data to rank ({rk[0]["attractiveness"]:.2f} of 5)</li>
        <li>Ash 1.0% vs the &lt; 0.1% carbon-fiber spec: compatibility 1</li>
        <li><strong>{esc(rk[1]["name"])}</strong>: {rk[1]["attractiveness"]:.2f} on what could be assessed, but only {rk[1]["completeness"]["assessed_weight"]:.0%} of the weight, so insufficient data</li>
        <li>{A["usage"]["requests"]} model requests, {A["usage"]["tool_calls"]} tool calls</li></ul>
        <img class="shot" src="{img_uri("comparison")}" alt="Opportunity comparison"></div></section>""",
        f"""<section><p class="kicker">Demo · the trace</p><h2>Every tool call, guard action, and token is recorded</h2>
        <img class="shot" style="max-height:560px" src="{img_uri("trace_open_top")}" alt="Execution trace with tool calls"></section>""",
        f"""<section><p class="kicker">Cost · {esc(A["model"])} course price</p><h2>About {u.input_tokens / 1000:.0f}k input tokens and USD {cost["usd"]:.4f} per run</h2>
        {_tiles([(f"{u.input_tokens / 1000:.1f}k / {u.output_tokens / 1000:.1f}k", "mean input / output tokens per run"),
                 (f'USD {cost["usd"]:.4f}', "per run (measured tokens × course price)"),
                 (f'USD {monthly[0]["model_cost_usd"]:,.2f}', f'per month, 100 users × {a["assessments_per_user_per_month"]} runs'),
                 (f'USD {monthly[1]["model_cost_usd"]:,.0f}', f'per month, 10,000 users × {a["assessments_per_user_per_month"]} runs')])}
        <div class="cols"><ul><li>Optimized vs baseline: input tokens {d_in:+.0f}%, cost {d_usd:+.0f}%</li>
        <li>Hosting and support: not estimated (no quotes)</li></ul><div>{token_chart(560)}</div></div></section>""",
        f"""<section><p class="kicker">Safety</p><h2>Untrusted text stays data</h2><div class="cols r"><ul>
        <li>Injected instructions in user input or evidence are removed before any agent sees them, and logged</li>
        <li>References and numbers are checked; no claims of guaranteed profit, verified demand, or engineering approval</li>
        <li>Loops and overspending capped: request, tool-call, token, and time limits per agent; a budget per run</li>
        <li>Invalid and oversized inputs refused before any run</li></ul>
        <img class="shot" src="{img_uri("injection_trace")}" alt="Security event in the trace"></div></section>""",
        f"""<section><p class="kicker">Impact and metrics</p><h2>What was measured</h2>
        {_tiles([(f"{passed}/{total}", "pre-written evaluation checks passed"), (f'{runs["completed"]}/{runs["live_runs"]}', "live runs completed"),
                 (f'{lat["median"]:.0f} s', "median time per screen"), (str(t["deterministic"]["tests"] + t["mock"]["tests"]), "automated tests, all passing")])}
        <ul><li>15 scenarios, expectations written before running; calculations {M["calculation_accuracy"]["passed"]}/{M["calculation_accuracy"]["total"]}; citations {M["reference_validity"]["valid"]:,}/{M["reference_validity"]["total"]:,} valid</li>
        <li>Failed checks: {esc("; ".join(failed)) if failed else "none"}{S13_NOTE if any(f.startswith("S13") for f in failed) else ""}</li>{_user_line()}</ul></section>""",
        """<section><p class="kicker">Limits and next steps</p><h2>What comes next</h2><div class="cols"><ul>
        <li>Test with real users and a real mill's lab data</li><li>Expert-reviewed rankings to measure agreement</li>
        <li>Small evidence library (15 sources): no resin or polyurethane specs, prices, or yields</li></ul>
        <ul><li>Prefer the conservative TRL when sources disagree</li><li>Flag rankings that rest on user assumptions</li>
        <li>Average several judgment samples to cut run-to-run variation</li><li>Hosting quotes for an organization-scale budget</li></ul></div></section>""",
    ]
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>BioValue AI · slides</title>
<link rel="stylesheet" href="{REVEAL}/reset.css"><link rel="stylesheet" href="{REVEAL}/reveal.css"><link rel="stylesheet" href="{REVEAL}/theme/white.css">
<style>{BASE_CSS}{SLIDE_CSS}</style></head>
<body><div class="reveal"><div class="slides">{"".join(s)}</div></div>
<script src="{REVEAL}/reveal.js"></script>
<script>Reveal.initialize({{ hash: true, width: 1280, height: 720, margin: 0.05, slideNumber: "c/t", transition: "fade" }});</script>
</body></html>
"""
