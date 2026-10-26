"""Report sections 1 (title and links), 2 (motivation), 3 (what is new)."""

from report_data import A, LINKS, M, UT, check_totals, claim, esc, figure, live_runs, mean_usage, table

KIENBERGER = ("M. Kienberger, S. Maitz, T. Pichler, P. Demmelmayer (2021), “Systematic Review on Isolation Processes for "
              "Technical Lignin”, <em>Processes</em> 9, 804, "
              '<a href="https://doi.org/10.3390/pr9050804">doi.org/10.3390/pr9050804</a>')


def _link(url, missing):
    return f'<a href="{esc(url)}">{esc(url)}</a>' if url else f'<span class="na">{missing}</span>'


def title() -> str:
    passed, total = check_totals()
    runs = M["runs"]
    lat = runs["latency_seconds_completed"]
    u = mean_usage()
    cost = M["cost_per_completed_assessment"]
    tiles = [
        (f'{runs["completed"]}/{runs["live_runs"]}', "live evaluation runs completed"),
        (f"{passed}/{total}", "pre-written evaluation checks passed"),
        (f'{lat["median"]:.0f} s', "median time per assessment"),
        (f'{u.input_tokens / 1000:.1f}k / {u.output_tokens / 1000:.1f}k', "mean input / output tokens per assessment"),
        (f'USD {cost["usd"]:.4f}', f"model cost per assessment at {esc(A['model'])}'s course price"),
        ("pending" if not UT["conducted"] else f'{UT["biovalue_minutes"]} vs {UT["normal_workflow_minutes"]} min',
         "real-user test (BioValue AI vs normal workflow)"),
    ]
    tile_html = "".join(f'<div class="tile"><div class="big">{v}</div><div class="small">{t}</div></div>' for v, t in tiles)
    return f"""
<section class="cover">
  <p class="kicker">MGT 409 · AI Foundations for Managers · Final project</p>
  <h1>BioValue AI</h1>
  <p class="subtitle">Four AI agents that give a kraft pulp mill a first, evidence-bound screen of what to make from its lignin,
  with every number computed by tested code and every gap shown as a gap.</p>
  {table(["", ""], [
        ["Author", "Madina Muratova · Yale School of Management · October 2026"],
        ["Code repository", _link(LINKS.get("repo"), "to be added before submission")],
        ["Live app", _link(LINKS.get("app"), "not hosted; runs from a fresh clone in one command (see the README)")],
        ["Demo video", _link(LINKS.get("video"), "optional; not provided")]], cls="kv links")}
  <div class="tiles">{tile_html}</div>
  <div class="callout"><strong>How to read this report.</strong> All results come from real runs of the application with the course
  model (<strong>{esc(A["model"])}</strong> through Portkey), read from the result files listed in the appendix. The mill in the worked
  example is <strong>fictional</strong>; its figures are labelled assumptions. Market figures are quoted from sources, with their
  reference. Nothing that was not measured is reported as a result.</div>
</section>"""


def motivation() -> str:
    return f"""
<section>
  <h2><span class="sec">2</span>Motivation</h2>
  <p><strong>Who has the problem.</strong> Strategy and business-development leads at kraft pulp mills, and the climate-tech investors
  and bioeconomy programs that work with them. In the kraft process, lignin dissolves into the black liquor that a mill burns in its
  recovery boiler. A mill can take part of it out as a solid, and then has to decide what to do with it.</p>
  <p><strong>The scale of the missed opportunity.</strong> A systematic review puts lignin output at 50–70 million tonnes a year, of
  which “just 1–2% are used for the production of added-value products”, and notes that most mills isolate lignin to relieve the
  recovery boiler rather than to sell it ({KIENBERGER}). The markets lignin could enter are large:</p>
  <ul>
    <li><em>{esc(claim("EV-PF-01#4"))}</em> (EV-PF-01, IEA Bioenergy, high-quality source)</li>
    <li><em>{esc(claim("EV-PU-04#4"))}</em> <em>{esc(claim("EV-PU-04#3"))}</em> (EV-PU-04, IEA Bioenergy)</li>
    <li><em>{esc(claim("EV-PF-02#4"))}</em> (EV-PF-02, UPM, company publication)</li>
  </ul>
  <p><strong>What it costs today.</strong> Deciding which of these uses deserves lab work or a partner conversation is a first screen
  assembled by hand from papers, reports, and calls. Three things make it slow and error-prone:</p>
  <ul>
    <li><strong>Missing data.</strong> A mill rarely has every property a buyer asks for (molecular weight, phenolic hydroxyl, sodium).
    A screen that quietly fills gaps, or treats missing evidence as a bad score, ranks on noise.</li>
    <li><strong>Units and basis.</strong> Wet versus dry tonnes and the moisture basis change the volume on offer by tens of percent.</li>
    <li><strong>Untraceable claims.</strong> Numbers in a slide deck are hard to trace to a source, and general AI chat can produce
    confident figures and citations that do not exist.</li>
  </ul>
  <p>We found no published figure for the time or money a first screen costs; the user test (Section 7) measures it directly.</p>
</section>"""


def whats_new() -> str:
    costs = [e["run"]["cost"]["usd"] for e in live_runs() if e["run"]["status"] == "complete"]
    lo, hi = min(costs), max(costs)
    rows = [
        ["General AI assistants (ChatGPT, Claude, Gemini)", "Fast, broad, can draft a screen in minutes",
         "Nothing ties each number to tested code or each claim to a vetted source; a missing input is easily filled with a plausible guess; answers are not structured or auditable"],
        ["AI research search (Perplexity, Elicit, Consensus)", "Find and cite real papers and web sources",
         "Do not compute a mill-specific mass balance, check its lignin against product specifications, or rank pathways with explicit weights"],
        ["Consultant studies and market reports", "Expert judgment, depth, real market contacts",
         "Commissioned per question; not rerunnable when one input changes; assumptions often hard to separate from facts"],
        ["In-house spreadsheet models", "Deterministic and transparent arithmetic",
         "Someone still has to find the evidence, judge the market, and keep the sources attached to each number"],
    ]
    return f"""
<section>
  <h2><span class="sec">3</span>What is new</h2>
  {table(["Existing alternative", "What it does well", "What it misses for this decision"], rows)}
  <p><strong>What BioValue AI does differently</strong> is combine four things none of these gives together:</p>
  <ol>
    <li><strong>Agents for judgment, code for numbers.</strong> Four agents decide what to look up and how to interpret it; every
    number (dry mass, scenarios, compatibility gaps, TRL score, the ranking) comes from tested Python they call as tools.</li>
    <li><strong>Evidence-bound claims.</strong> Market statements may only cite a curated library of verified sources; each reference is
    checked to exist, to be supported, and to belong to the right pathway before the answer is accepted.</li>
    <li><strong>Gaps are answers, not zeros.</strong> Attractiveness, data completeness, and evidence quality are reported separately;
    a pathway with too little data is listed as <em>insufficient data</em> with its possible range, never ranked last.</li>
    <li><strong>Auditable and cheap to rerun.</strong> Every run saves the full trace of agents, tool calls, guard actions, tokens,
    and cost, and costs under one US cent (USD {lo:.4f}–{hi:.4f} per run in the evaluation), so a mill can rerun the screen
    whenever a lab result arrives.</li>
  </ol>
  {figure("about_page", "The dashboard's About tab explains in plain words what the tool does, the idea behind it (with sources), and who can benefit. The faint wood motifs in the background are part of the Scandinavian-inspired design; the content sits on solid cards.", width="50%")}
</section>"""
