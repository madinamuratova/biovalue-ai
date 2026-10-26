"""Report section 4, continued: the same agents on a literature-based reference stream (published, cited figures)."""

import re
from datetime import datetime

from report_data import A, REF_FEEDSTOCK, REF_RUN, esc, n, table


def _short(citation: str) -> str:
    """'Yan, Q., Li, J., … (2018). Title' -> 'Yan et al. (2018)'; 'Valmet (22 Dec 2015). …' -> 'Valmet (2015)'."""
    year = re.search(r"\((?:[^)]*?)(\d{4})\)", citation)
    first = citation.split(",")[0].split(" (")[0]
    many = citation.count("., ") >= 1
    return f"{first}{' et al.' if many else ''} ({year.group(1) if year else 'n.d.'})"


def reference_stream() -> str:
    f = REF_FEEDSTOCK
    src = {s["key"]: s for s in f["sources"]}
    c = f["composition"]
    cite = lambda *keys: "; ".join(f'<a href="{esc(src[k]["url"])}">{esc(_short(src[k]["citation"]))}</a>' for k in keys)
    rows = [
        ["Lignin output", f'{n(f["annual_wet_quantity"]["value"])} t/yr', "plant capacity; dry or moist basis not stated", cite("valmet2015", "kienberger2021")],
        ["Moisture", f'{n(f["moisture_pct"]["value"])}%', "100 − 65% dry solids of LignoBoost cake (measured at another LignoBoost plant)", cite("valmet2015")],
        ["Lignin content", f'{c["lignin_pct"]["value"]}%', "per Domtar's specification, as quoted", cite("yan2018")],
        ["Ash", f'{c["ash_pct"]["value"]}%', f'{c["ash_pct"]["low"]}–{c["ash_pct"]["high"]}% across three studies and methods', cite("yan2018", "hararak2023", "wu2024")],
        ["Sulfur", f'{c["sulfur_pct"]["value"]}%', "measured table value; the same paper's text says below 0.1%", cite("yan2018")],
        ["Molecular weight", f'{n(c["mw_g_per_mol"]["value"])} g/mol', "5,200–6,700 in a literature table; 19,200 by another method", cite("hararak2023", "wu2024")],
        ["Current use", "sold as BioChoice lignin", "plant built to relieve the recovery boiler", cite("valmet2015")],
        ["Carbohydrates, phenolic OH, sodium", "blank", "no published figure found; recorded as missing", "–"],
    ]
    r = REF_RUN
    rk = r["decision"]["ranking"]
    secs = (datetime.fromisoformat(r["execution"]["finished_at"]) - datetime.fromisoformat(r["execution"]["started_at"])).total_seconds()
    ranked = ", ".join(f'{esc(o["name"])} ({o["attractiveness"]:.2f})' for o in rk["ranked"]) or "none"
    insuff = ", ".join(f'{esc(o["name"])} ({o["attractiveness"]:.2f}, {o["completeness"]["assessed_weight"]:.0%} assessed)' for o in rk["insufficient_data"]) or "none"
    same = [o["pathway_id"] for o in rk["ranked"]] == [o["pathway_id"] for o in A["decision"]["ranking"]["ranked"]]
    cm = next(x for x in r["commercialization"] if x["pathway_id"] == "carbon_materials")
    ash_gap = next((i for i in cm["feedstock_compatibility"]["inputs"] if i.startswith("ash")), "")
    step = r["decision"]["report"]["validation_steps"][0]["action"]
    return f"""
<section>
  <h3>The same agents on published data: a literature-based reference stream</h3>
  <p>The demo mill is fictional. To show the tool on real-world figures, a second preset (dashboard: <em>Load literature reference</em>)
  describes a softwood kraft lignin using <strong>only published, cited values</strong>: BioChoice lignin, made with the LignoBoost process
  at Domtar's Plymouth, North Carolina mill. Each figure stores its source key, and each source stores the passages it was taken from,
  quoted verbatim and checked against the source on {esc(src["valmet2015"]["verified_on"])}. Figures no source reports stay blank, and
  any figure edited in the dashboard loses its citation and becomes the user's estimate.</p>
  {table(["Figure", "Value used", "Note", "Source"], rows)}
  <p><strong>Live result</strong> (run <code>{esc(r["run_id"])}</code>, {esc(r["model"])}, {secs:.0f} s, {n(r["usage"]["input_tokens"])} input and
  {n(r["usage"]["output_tokens"])} output tokens, USD {r["cost"]["usd"]:.4f}): ranked {ranked}; insufficient data: {insuff}.
  {"The pattern matches the fictional demo, for the same reasons: " if same else "Reasons: "}the published ash is far above the carbon-fiber
  precursor specification ({esc(ash_gap)}), and the library has no numeric resin or polyurethane specifications and no prices or yields. The
  agents' first validation step was to “{esc(step[:150])}{"…" if len(step) > 150 else ""}”.</p>
  <p class="muted">Caveats: the values come from different studies and samples of a commercial product, not one mill's records or data
  supplied by Domtar; the capacity's dry or moist basis is not stated; no economic inputs are published, so the economics stop at dry mass.
  The evaluation suite still runs on the fictional demo, because its expectations were written for it before the first run.</p>
</section>"""
