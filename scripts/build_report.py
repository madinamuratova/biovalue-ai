"""Build report.html and slides.html in the project folder from the measured result files.

    .venv/bin/python scripts/build_report.py

Needs the screenshots in output/screenshots/ (node scripts/capture_screenshots.mjs). Both outputs are single,
self-contained HTML files (images embedded). Data sources are listed in scripts/report_data.py.
"""

from report_data import BASE_CSS, ROOT
from report_s1 import motivation, title, whats_new
from report_s2 import agents
from report_s2b import reference_stream
from report_s3 import safety, tokenomics
from report_s4 import appendix, impact, limits
from report_slides import slides_html

REPORT_CSS = """
body { background: var(--bg); }
main { max-width: 900px; margin: 32px auto; background: var(--paper); padding: 56px 64px; border: 1px solid var(--line); border-radius: 12px; }
h1 { font-size: 2.6em; margin: 6px 0 4px; letter-spacing: -0.01em; }
h2 { font-size: 1.45em; margin: 34px 0 10px; padding-bottom: 6px; border-bottom: 1px solid var(--line); }
h2 .sec { display: inline-block; min-width: 1.6em; color: var(--accent); }
h3 { font-size: 1.05em; margin: 22px 0 6px; }
p { margin: 8px 0; }
.kicker { color: var(--muted); text-transform: uppercase; letter-spacing: .08em; font-size: .8em; margin: 0; }
.subtitle { font-size: 1.2em; color: var(--ink-2); max-width: 640px; }
.byline { color: var(--muted); }
.tiles { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 22px 0; }
.tile { border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; background: #fff; }
.tile .big { font-size: 1.5em; font-weight: 650; font-variant-numeric: tabular-nums; }
.tile .small { color: var(--muted); font-size: .84em; line-height: 1.35; }
.callout { border-left: 3px solid var(--accent); background: var(--accent-soft); padding: 12px 16px; border-radius: 0 8px 8px 0; font-size: .92em; }
.toc { margin-top: 18px; font-size: .92em; color: var(--ink-2); }
.toc ol { columns: 2; margin: 6px 0 8px; padding-left: 20px; }
figure { margin: 14px 0 18px; text-align: center; }
figure img { border: 1px solid var(--line); border-radius: 8px; max-width: 100%; }
figcaption, .caption { font-size: .82em; color: var(--muted); text-align: left; margin-top: 6px; }
.muted { color: var(--muted); font-size: .9em; }
.formula { background: var(--soft); border-radius: 8px; padding: 10px 14px; font-size: .8em; overflow-x: auto; }
table.kv td:first-child { width: 34%; color: var(--ink-2); }
table.links thead { display: none; }
blockquote { border-left: 3px solid var(--accent); margin: 10px 0; padding: 6px 14px; color: var(--ink-2); }
table.plain td { border-bottom: 1px solid var(--line); }
table.plain td:first-child { width: 32%; }
ol.steps li { margin: 4px 0; }
@page { size: Letter; margin: 0.6in 0.65in; }
@media print {
  body { background: #fff; font-size: 9.4pt; }
  table { font-size: 0.8em; } th, td { padding: 4px 6px; }
  figcaption, .caption { font-size: .78em; }
  main { margin: 0; padding: 0; border: none; max-width: none; }
  .page-break { break-before: page; }
  h2 { margin-top: 18px; }
  h2, h3 { break-after: avoid; }
  figure, .diagram, .tiles, svg { break-inside: avoid; }
  table { break-inside: auto; } thead { display: table-header-group; }
  tr { break-inside: avoid; }
  a { color: inherit; text-decoration: none; }
}
"""


def report_html() -> str:
    # The eight sections required by the project page, in its order.
    body = "".join(f() for f in (title, motivation, whats_new, agents, reference_stream, tokenomics, safety, impact, limits, appendix))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>BioValue AI · MGT 409 final project report</title>
<style>{BASE_CSS}{REPORT_CSS}</style></head>
<body><main>{body}</main></body></html>
"""


def main() -> None:
    (ROOT / "report.html").write_text(report_html(), encoding="utf-8")
    (ROOT / "slides.html").write_text(slides_html(), encoding="utf-8")
    for name in ("report.html", "slides.html"):
        print(f"wrote {ROOT / name} ({(ROOT / name).stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
