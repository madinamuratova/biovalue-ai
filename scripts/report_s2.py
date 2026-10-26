"""Report section 4: the agents (organization, models, tools and calculations, scoring, one real run step by step)."""

from collections import Counter
from datetime import datetime

from report_data import A, AGENT_ORDER, AGENT_TITLES, AGENT_TOOLS, E, SC, agent_diagram, esc, figure, n, ranking_rows, table

ROLES = {
    "feedstock": ("Normalizes the feedstock record, converts units, calculates dry mass, and lists missing properties, inconsistencies, and constraints.",
                  "Values must match the tools; the missing-property list must match the validator exactly."),
    "market": ("Finds applications, customers, competing materials, and qualification requirements in the evidence library, and scores market evidence.",
               "Every finding cites an existing, supported record of the same pathway; a score of 4–5 needs high- or moderate-quality sources."),
    "commercialization": ("Checks compatibility, runs the scenario economics, confirms a TRL from cited evidence, and judges commercialization feasibility.",
                          "A TRL is accepted only if a cited claim states it; every number must appear in the cited evidence or a tool result."),
    "decision": ("Calls the scoring engine, explains the drivers, recommends 3–5 validation steps, and says what would change the ranking.",
                 "Cannot reorder the engine's ranking; no claims of guaranteed profit, verified demand, or engineering approval."),
}


def _agent(name):
    return next(a for a in A["execution"]["agents"] if a["agent"] == name)


def _tools(name):
    counts = Counter(t["tool"] for t in _agent(name)["tool_calls"])
    return " → ".join(f"<code>{t}</code>" + (f" ×{c}" if c > 1 else "") for t, c in counts.items())


def _run_steps():
    fs = A["feedstock"]["agent"]
    market = {m["pathway_id"]: m["findings"] for m in A["market"]}
    comm = {c["pathway_id"]: c for c in A["commercialization"]}
    names = {o["pathway_id"]: o["name"] for o in ranking_rows(A)}
    trl = lambda c: next((i.split("=")[1].strip() for i in c["technical_readiness"]["inputs"] if i.startswith("TRL")), "not confirmed")
    score = lambda j: j["score"] if j else "not scored"
    rk = A["decision"]["ranking"]
    steps = []
    a = _agent("feedstock")
    steps.append(["1", "Feedstock Agent", _tools("feedstock"),
                  f'Wet {n(fs["wet_mass_t_per_yr"])} t/yr at {fs["moisture_fraction"]:.0%} moisture → dry {n(fs["dry_mass_t_per_yr"])} t/yr; '
                  f'{len(fs["missing_properties"])} missing properties ({esc(", ".join(p.rsplit(".", 1)[-1] for p in fs["missing_properties"]))}); '
                  f'{len(fs["constraints"])} constraints, e.g. “{esc(fs["constraints"][0])}”',
                  f'{a["seconds"]:.0f} s · {a["usage"]["requests"]} requests'])
    a = _agent("market")
    steps.append(["2", "Market Intelligence Agent", _tools("market"),
                  "; ".join(f'{esc(names[p])}: market evidence {score(f["market_evidence"])}, {len(f["applications"])} applications, '
                            f'{len(f["qualification_requirements"])} qualification requirements' for p, f in market.items()),
                  f'{a["seconds"]:.0f} s · {a["usage"]["requests"]} requests'])
    a = _agent("commercialization")
    steps.append(["3", "Commercialization Agent", _tools("commercialization"),
                  "; ".join(f'{esc(names[p])}: TRL {trl(c)}, compatibility {c["feedstock_compatibility"]["score"] or "not assessable"}, '
                            f'feasibility {score(c["findings"]["commercialization_feasibility"])}' for p, c in comm.items()),
                  f'{a["seconds"]:.0f} s · {a["usage"]["requests"]} requests'])
    a = _agent("decision")
    ranked = ", ".join(f'{esc(o["name"])} #{o["rank"]} ({o["attractiveness"]:.2f})' for o in rk["ranked"]) or "none"
    insuff = ", ".join(f'{esc(o["name"])} ({o["attractiveness"]:.2f})' for o in rk["insufficient_data"]) or "none"
    steps.append(["4", "Decision Agent", _tools("decision"),
                  f'Ranked: {ranked}. Insufficient data: {insuff}. {len(A["decision"]["report"]["validation_steps"])} validation steps.',
                  f'{a["seconds"]:.0f} s · {a["usage"]["requests"]} requests'])
    return steps


def _guard_note() -> str:
    """What the guards did in this run, from its own trace."""
    events = [(ag["agent"], g) for ag in A["execution"]["agents"] for g in ag["guard_events"]]
    if not events:
        return "<p>No guard had to intervene in this run.</p>"
    parts = []
    for agent, g in events:
        verb = "sent the answer back" if g["action"] == "retry_requested" else "repaired the answer in code"
        probs = "; ".join(esc(x) for x in dict.fromkeys(p.split(": ", 1)[-1] for p in g["problems"]))
        parts.append(f"the guard {verb} to the {esc(AGENT_TITLES[agent])}, which had cited a reference that does not exist ({probs})"
                     if "claim(s)" in probs or "no evidence record" in probs else
                     f"the guard {verb} to the {esc(AGENT_TITLES[agent])} ({probs})")
    return ("<p><strong>A guard at work in this run:</strong> " + "; ".join(parts) +
            ". The agent corrected it on its next request, so the final output contains only references that exist.</p>")


def agents() -> str:
    rows = [[str(i), f"<strong>{esc(AGENT_TITLES[a])}</strong>", ROLES[a][0], ROLES[a][1]] for i, a in enumerate(AGENT_ORDER, 1)]
    weights = [[c.replace("_", " ").capitalize(), f"{w:.0%}",
                {"feedstock_compatibility": "rule: largest gap to the evidence's numeric specs",
                 "technical_readiness": "rule: TRL stated in a cited claim (1–2→1 … 8–9→5)",
                 "market_evidence": "agent judgment against the rubric, with evidence",
                 "indicative_economics": "rule: gross contribution per tonne (illustrative bands)",
                 "commercialization_feasibility": "agent judgment against the rubric"}[c]] for c, w in SC["weights"].items()]
    cm = next(c for c in A["commercialization"] if c["pathway_id"] == "carbon_materials")
    base = cm["scenario_analysis"]["scenarios"]["base"]["steps"]
    started = datetime.fromisoformat(A["execution"]["started_at"])
    secs = (datetime.fromisoformat(A["execution"]["finished_at"]) - started).total_seconds()
    u = A["usage"]
    return f"""
<section>
  <h2><span class="sec">4</span>The agents</h2>
  <h3>Organization</h3>
  <p>Four specialized agents run once each in a fixed order and pass <em>validated</em> structured outputs forward. No agent can call
  another, so there is no recursion. A React dashboard sends the inputs to a FastAPI server, which runs the workflow and streams the
  live trace back.</p>
  {agent_diagram()}
  {table(["#", "Agent", "Role", "What code checks before its answer is accepted"], rows)}
  <p>A failing answer goes back to the agent with the problems listed, up to twice; after that, code repairs it by dropping what it
  cannot support, never by inventing content. Each request has a 90-second timeout, each agent a 5-minute timeout and usage limits
  (15 requests, 30 tool calls, 200,000 tokens), and each run a 400,000-token budget.</p>
  <h3>Models and why</h3>
  <p>All four agents use <strong>{esc(A["model"])}</strong> through Portkey (PydanticAI, OpenAI Responses API). It is the model the course
  key covers, it has a verified price, and it is enough for this design: the agents choose tools, read evidence, and write judgments,
  while every number is computed by code. One model for all four keeps behavior and cost easy to compare. (Development started on
  gpt-5.6-luna; after reading the project requirements the app was switched and every result in this report was re-measured on
  {esc(A["model"])}. The earlier results are archived, not mixed in.)</p>
  <h3>Tools, calculations, and scoring</h3>
  <p>The agents have 13 tools between them. Each wraps tested functions; the model decides <em>which</em> tool to call, never what the
  arithmetic returns.</p>
<pre class="formula">dry mass            = wet mass × (1 − moisture)            usable feedstock = dry mass × availability fraction
product output      = usable feedstock × yield              revenue          = product output × price
gross contribution  = revenue − variable cost               per tonne        = gross contribution ÷ usable feedstock</pre>
  <p>A missing input stops only the steps that need it (marked <em>not calculated</em>, never zero); units are explicit and unknown units
  are refused; gross margin, NPV, and IRR are not calculated because their inputs and definitions are not available in a first screen.
  Each pathway is scored 1–5 on five weighted criteria:</p>
  {table(["Criterion", "Weight", "How it is scored"], weights, num_cols=(1,))}
  <p>Attractiveness is the weighted mean of the criteria that <em>were</em> assessed. A pathway is ranked only if at least
  {SC["min_completeness"]:.0%} of the weight was assessed; otherwise it is listed as <em>insufficient data</em> with its possible range.
  Evidence quality is reported separately. The deterministic core is covered by {E["tiers"]["deterministic"]["tests"]} tests.</p>
  <h3>One real run, step by step</h3>
  <p>The fictional Pinecrest Mill demo (40,000 t/yr of wet lignin cake, 35% moisture, ash 1.0%; molecular weight, phenolic OH, and
  sodium deliberately missing) was run from the dashboard as run <code>{esc(A["run_id"])}</code>: {secs:.0f} s end to end,
  {u["requests"]} model requests, {u["tool_calls"]} tool calls, {n(u["input_tokens"])} input and {n(u["output_tokens"])} output tokens.</p>
  {figure("input_top", "Step 0: the inputs in section 1 of the dashboard. Every figure carries its source (here: fictional demo values); blank fields are recorded as missing, never as zero.", width="50%")}
  {table(["Step", "Agent", "Tool calls, in order", "What it produced", "Time"], _run_steps())}
  {_guard_note()}
  {figure("trace_open_top", "The execution trace for this run with every agent opened: each tool call with its arguments, status, and result, and any guard action.", width="54%")}
  {figure("comparison", "The result: carbon materials is the only pathway with enough assessed weight to rank; the other two are shown as insufficient data with their possible ranges (hollow dots), and completeness is shown separately.", width="54%")}
  <p>Why: the stream's ash is far above the carbon-fiber precursor specification in the evidence
  ({esc("; ".join(i for i in cm["feedstock_compatibility"]["inputs"] if i.startswith("ash")))}), so compatibility scores 1; and the economics
  stop at usable feedstock ({n(base["usable_feedstock"]["value"])} t/yr in the base scenario) because no yield, price, or cost was given.</p>
  {figure("ranking_top", "Ranking breakdown for carbon materials: each criterion's score, meaning, weight, contribution, and whether it came from a deterministic rule or an agent judgment, with its evidence.", width="52%")}
  {figure("actions_top", "Recommended actions: the disclaimers every run carries, the Decision Agent's summary, and the validation steps with the gaps each resolves.", width="52%")}
</section>"""
