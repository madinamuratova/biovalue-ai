"""Export a final assessment as a Markdown or standalone HTML report.

Both come from the same Markdown, so they always agree. Everything in the report is taken from the saved
assessment; nothing is recalculated or re-worded here.
"""

import html
import re

from backend.calc import SCENARIOS
from backend.workflow import FinalAssessment

STEP_ORDER = ("dry_mass", "usable_feedstock", "product_output", "revenue", "variable_cost", "gross_contribution",
              "contribution_per_t_feedstock")


def _cell(value) -> str:
    text = "–" if value is None or value == "" else str(value)
    return text.replace("|", "/").replace("\n", " ")


def _row(*cells) -> str:
    return "| " + " | ".join(_cell(c) for c in cells) + " |"


def _table(header: list[str], rows: list[list]) -> list[str]:
    return [_row(*header), "|" + "---|" * len(header), *[_row(*r) for r in rows], ""]


def _num(value, digits: int = 2) -> str:
    if value is None:
        return "–"
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    return f"{value:,.{digits}f}".rstrip("0").rstrip(".") if "." in f"{value:.{digits}f}" else f"{value:,}"


def _findings(title: str, findings) -> list[str]:
    if not findings:
        return [f"*{title}:* none supported by the evidence.", ""]
    return [f"*{title}:*", *[f"- {f.statement} ({', '.join(f.evidence)})" for f in findings], ""]


def render_markdown(r: FinalAssessment) -> str:
    lines = [f"# BioValue AI assessment: {r.project_name}", "",
             f"Run `{r.run_id}` · {r.created_at} · model {r.model} ({r.config} configuration) · status **{r.status}**", ""]
    lines += [f"> {d}" for d in r.disclaimers] + [""]
    ranking = r.decision.ranking
    names = {o.pathway_id: o.name for o in (*ranking.ranked, *ranking.insufficient_data)}

    # 1. Ranking
    lines += ["## 1. Ranking", "",
              f"Scores are on a 1–5 scale and come from the deterministic scoring engine ({r.decision.ranking_source}). "
              f"A pathway is ranked only when criteria carrying at least {ranking.min_completeness:.0%} of the weight "
              "were assessed; the rest are listed as insufficient data, not ranked last.", ""]
    rows = []
    for o in (*ranking.ranked, *ranking.insufficient_data):
        q = o.evidence.by_quality
        rows.append([o.rank or "insufficient data", o.name, _num(o.attractiveness),
                     f"{_num(o.attractiveness_range[0])}–{_num(o.attractiveness_range[1])}",
                     f"{o.completeness.assessed_weight:.0%}",
                     f"{q['high']} / {q['moderate']} / {q['low']} / {q['unverified']}"])
    lines += _table(["Rank", "Pathway", "Attractiveness", "Range if unassessed scored 1–5", "Data completeness",
                     "Evidence high / moderate / low / unverified"], rows)
    for o in (*ranking.ranked, *ranking.insufficient_data):
        lines += [f"### Score breakdown: {o.name}", ""]
        lines += _table(["Criterion", "Weight", "Score", "Weighted contribution", "Meaning", "How it was scored"],
                        [[c.label, f"{c.weight:.0%}", c.score or "not assessed", _num(c.weighted_contribution),
                          c.meaning, c.rationale] for c in o.criteria])

    # 2. Feedstock
    lines += ["## 2. Feedstock profile", ""]
    if r.feedstock:
        n = r.feedstock.normalized
        lines += [f"Wet quantity {_num(n['wet_mass_t_per_yr'])} t/yr at {n['moisture_fraction']:.0%} moisture gives "
                  f"**{_num(n['dry_mass_t_per_yr'])} t/yr dry matter**.", ""]
        comp_rows = []
        for name, q in {**n["composition"], **n["other_composition"]}.items():
            rng = f"{_num(q['low'])}–{_num(q['high'])}" if q["low"] is not None or q["high"] is not None else "–"
            comp_rows.append([name, _num(q["value"]) if q["value"] is not None else "missing", q["unit"], rng,
                              q["basis"], q["method"]])
        lines += _table(["Property", "Value", "Unit", "Range", "Basis", "Method"], comp_rows)
        lines += ["**Data gaps:**", *[f"- {g['field']} ({g['issue']}, {g['severity']}): {g['impact']}"
                                      for g in r.feedstock.checks["data_gaps"]], ""]
        a = r.feedstock.agent
        lines += ["**Feedstock Agent constraints:**", *[f"- {c}" for c in a.constraints], ""]
        if a.inconsistencies:
            lines += ["**Inconsistencies:**", *[f"- {c}" for c in a.inconsistencies], ""]
    else:
        lines += ["The Feedstock Agent did not finish, so no agent profile is available.", ""]

    # 3. Commercial assessment
    lines += ["## 3. Commercial assessment", ""]
    if r.commercialization:
        for s in r.commercialization:
            a = s.scenario_analysis
            lines += [f"### {names.get(s.pathway_id, s.pathway_id)}", "", f"Product: {a.product}", ""]
            rows = []
            for key in STEP_ORDER:
                steps = [a.scenarios[sc].steps[key] for sc in SCENARIOS]
                rows.append([steps[1].label, steps[1].formula,
                             *[_num(st.value) if st.status == "calculated" else "not calculated" for st in steps],
                             steps[1].unit])
            lines += _table(["Step", "Formula", "Conservative", "Base", "Optimistic", "Unit"], rows)
            reasons = sorted({st.reason for st in a.scenarios["base"].steps.values() if st.reason})
            if a.missing_inputs:
                lines += [f"Missing inputs: {', '.join(a.missing_inputs)}.", ""]
            lines += [*[f"- {x}" for x in reasons], ""] if reasons else []
            lines += ["**Assumptions:**", ""]
            lines += _table(["Input", "Conservative", "Base", "Optimistic", "Unit", "Basis", "Note"],
                            [[x.input, _num(x.conservative), _num(x.base), _num(x.optimistic), x.unit, x.basis, x.note]
                             for x in a.assumptions])
            f = s.findings
            lines += _findings("Processing requirements", f.processing_requirements)
            if f.technical_maturity:
                lines += [f"*Technical maturity:* {f.technical_maturity.statement} ({', '.join(f.technical_maturity.evidence)})", ""]
            lines += _findings("Adoption barriers", f.adoption_barriers)
            lines += ["*Uncertainties:*", *[f"- {u}" for u in f.uncertainties], ""]
        lines += [f"*{r.commercialization[0].scenario_analysis.not_calculated_metrics}*", ""]
    else:
        lines += ["The Commercialization Agent did not finish.", ""]

    # 4. Market evidence
    lines += ["## 4. Market evidence", ""]
    if r.market:
        for m in r.market:
            f = m.findings
            lines += [f"### {names.get(m.pathway_id, m.pathway_id)}", "", f"Sources: {', '.join(m.source_ids) or 'none'}", ""]
            for title, items in (("Applications", f.applications), ("Target customers", f.target_customers),
                                 ("Competing materials", f.competing_materials),
                                 ("Qualification requirements", f.qualification_requirements)):
                lines += _findings(title, items)
            lines += ["*Missing market information:*", *[f"- {x}" for x in f.missing_information], ""]
            if f.market_evidence:
                lines += [f"*Market evidence score:* {f.market_evidence.score} – {f.market_evidence.rationale}", ""]
    else:
        lines += ["The Market Intelligence Agent did not finish.", ""]

    # 5. Recommended actions
    lines += ["## 5. Recommended actions", ""]
    report = r.decision.report
    if report:
        lines += [f"{report.summary}", ""]
        lines += [f"{i}. **{s.action}** {s.reason} *(addresses: {', '.join(s.addresses)})*"
                  for i, s in enumerate(report.validation_steps, 1)] + [""]
        lines += ["**What could change the ranking:**", *[f"- {x}" for x in report.ranking_changers], ""]
        for item in report.shortlist:
            lines += [f"**{names.get(item.pathway_id, item.pathway_id)}** – drivers: {' '.join(item.main_drivers)} "
                      f"Could change with: {' '.join(item.what_could_change_it)}", ""]
        if report.caveats:
            lines += ["**Caveats:**", *[f"- {x}" for x in report.caveats], ""]
    else:
        lines += ["The Decision Agent did not finish, so there are no recommendations. The ranking above was computed "
                  "by the workflow.", ""]

    # What the assessment rests on
    lines += ["## What the assessment rests on", "",
              "Built by code from the validated results, so documented facts, assumptions, estimates, and unknowns stay apart.", ""]
    if r.ledger is None:
        lines += ["This run was saved before the ledger existed; rerun the assessment to see it.", ""]
    else:
        for title, items in (("Documented facts", r.ledger.documented_facts), ("Assumptions", r.ledger.assumptions),
                             ("Estimates", r.ledger.estimates), ("Unknowns", r.ledger.unknowns)):
            lines += [f"### {title} ({len(items)})", "", *[f"- {i.statement} *({i.source})*" for i in items], ""]

    # 6. Sources
    cited = sorted({rid for o in (*ranking.ranked, *ranking.insufficient_data) for rid in o.evidence.cited_records}
                   | {rid for m in (r.market or ()) for rid in m.source_ids})
    lines += ["## 6. Sources cited", ""]
    if cited:
        from backend import data
        lib = data.project().evidence
        lines += _table(["Id", "Title", "Publisher", "Published", "Quality", "Link"],
                        [[rid, lib.record(rid).title, lib.record(rid).publisher, lib.record(rid).published,
                          lib.record(rid).quality, f"[link]({lib.record(rid).url})" if lib.record(rid).url else "–"]
                         for rid in cited])
    else:
        lines += ["No sources were cited.", ""]

    # 7. Execution trace
    lines += ["## 7. Agent execution trace", ""]
    lines += _table(["#", "Agent", "Status", "Attempts", "Latency (s)", "Requests", "Input tokens", "Cached input",
                     "Output tokens", "Tools called"],
                    [[a.order, a.agent, a.status, a.attempts, a.seconds, a.usage.requests, f"{a.usage.input_tokens:,}",
                      f"{a.usage.cache_read_tokens:,}", f"{a.usage.output_tokens:,}",
                      ", ".join(c.tool for c in a.tool_calls) or a.skipped_reason or "–"]
                     for a in r.execution.agents])
    for e in r.execution.security_events:
        lines.append(f"- Security: text in {e.source} field {e.field} read like instructions to the AI and was replaced "
                     f"(matched: {', '.join(e.matched)})")
    for a in r.execution.agents:
        lines += [f"- {a.agent}: guard {g.action}: {'; '.join(g.problems)}" for g in a.guard_events]
        lines += [f"- {a.agent}: error {e}" for e in a.errors]
    cost = f"{r.cost.usd} USD" if r.cost.usd is not None else r.cost.note
    proxy = (f" Proxy estimate: {r.cost.proxy_usd} USD. {r.cost.proxy_note}" if r.cost.usd is None and r.cost.proxy_usd is not None
             else f" ({r.cost.note})" if r.cost.usd is not None else "")
    lines += ["", f"Total: {r.usage.requests} requests, {r.usage.tool_calls} tool calls, {r.usage.input_tokens:,} input "
              f"tokens ({r.usage.cache_read_tokens:,} cached) and {r.usage.output_tokens:,} output tokens, as reported by "
              f"the provider. Cost: {cost}{proxy}", ""]
    return "\n".join(lines)


# --- Markdown -> HTML (only the subset render_markdown writes) ------------------------------------------------

CSS = """
body{font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif;color:#1d1f21;background:#f6f5f2;margin:0}
main{max-width:1040px;margin:0 auto;padding:40px 32px 80px;background:#fcfcfb}
h1{font-size:26px;font-weight:600;margin:0 0 6px}h2{font-size:20px;font-weight:600;margin:40px 0 12px;
padding-top:16px;border-top:1px solid #e1e0d9}h3{font-size:16px;font-weight:600;margin:28px 0 8px}
p,li{color:#2b2d30}blockquote{margin:8px 0;padding:8px 14px;background:#f3f1ec;border-left:3px solid #c3c2b7;color:#52514e}
table{border-collapse:collapse;width:100%;margin:8px 0 16px;font-size:13.5px}th,td{text-align:left;
padding:6px 8px;border-bottom:1px solid #e1e0d9;vertical-align:top}th{color:#52514e;font-weight:600;
background:#f6f5f2}td{font-variant-numeric:tabular-nums}code{font-size:13px;background:#f0efec;padding:1px 4px;border-radius:3px}
a{color:#2e6ea0}
"""


def _inline(text: str) -> str:
    out = html.escape(text, quote=False)
    out = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", lambda m: f'<a href="{html.escape(m.group(2))}">{m.group(1)}</a>', out)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", out)
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", out)


def markdown_to_html(markdown: str, title: str) -> str:
    body, i, lines = [], 0, markdown.split("\n")
    while i < len(lines):
        line = lines[i]
        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            body.append(f"<h{level}>{_inline(line[level:].strip())}</h{level}>")
        elif line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(lines[i])
                i += 1
            cells = [[c.strip() for c in row.strip().strip("|").split("|")] for row in rows if not re.fullmatch(r"\|(---\|)+", row)]
            head, *rest = cells
            body.append("<table><thead><tr>" + "".join(f"<th>{_inline(c)}</th>" for c in head) + "</tr></thead><tbody>"
                        + "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>" for r in rest)
                        + "</tbody></table>")
            continue
        elif line.startswith("- ") or re.match(r"\d+\. ", line):
            ordered = not line.startswith("- ")
            items = []
            while i < len(lines) and (lines[i].startswith("- ") if not ordered else re.match(r"\d+\. ", lines[i])):
                items.append(re.sub(r"^(- |\d+\. )", "", lines[i]))
                i += 1
            tag = "ol" if ordered else "ul"
            body.append(f"<{tag}>" + "".join(f"<li>{_inline(x)}</li>" for x in items) + f"</{tag}>")
            continue
        elif line.startswith("> "):
            body.append(f"<blockquote>{_inline(line[2:])}</blockquote>")
        elif line.strip():
            body.append(f"<p>{_inline(line)}</p>")
        i += 1
    return (f"<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><title>{html.escape(title)}</title>"
            f"<style>{CSS}</style></head><body><main>{''.join(body)}</main></body></html>\n")


def render_html(r: FinalAssessment) -> str:
    return markdown_to_html(render_markdown(r), f"BioValue AI assessment {r.run_id}")
