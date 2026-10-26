# BioValue AI dashboard: design notes

## Purpose

The dashboard lets a mill strategist edit a lignin stream, run the four agents on it, and see why each pathway ranks where it does, without mistaking missing evidence for a weak opportunity.

## Layout

One page in nine numbered sections, with a sticky section list on wide screens and a sticky header holding the run button. The order follows the decision: inputs, profile, comparison, breakdown, economics, actions, then the supporting material (evidence, trace, export). Every section reads from the live API. Nothing on the page is hardcoded: before the first run, sections 3–6 say there is no assessment yet.

## Visual style

- Scandinavian-inspired, as the course `AGENTS.md` asks: warm off-white page, calm white cards, hairline borders, generous spacing, the system sans, and tabular figures only in table columns.
- **One accent color, `#2e6ea0`,** for data marks and the primary action. It was chosen with the dataviz palette validator: two muted blues failed its chroma floor (they read as gray), and this one passes the chroma and 3:1 contrast checks on the card surface.
- Status always pairs a colored dot with a text label (Ranked #1, Insufficient data, Completed, Failed), so it never relies on color alone.

## Visualizations

- **Opportunity comparison:** one row per pathway on a shared 1–5 axis. A filled dot is a ranked pathway's attractiveness; a hollow dot is attractiveness for a pathway with too little data to rank; a pale band is the range the score could take once unassessed criteria are scored. Data completeness is a separate meter, so a thin evidence base never looks like a low score. A comparison table gives the same values without the chart.
- **Ranking breakdown:** a table with score pips and a single-hue contribution bar per criterion (contribution out of the most it could add), next to the rubric meaning and the basis.
- Everything else is a table. Economics with "not calculated" cells and the missing inputs listed are clearer in a table than in a chart.

## Interaction

- **Form checks:** the form is checked as you type. Field-level errors from the browser and from the server appear next to the right input, and the run is blocked until they are fixed.
- **Preview:** the deterministic profile (section 2) refreshes about half a second after each change. It needs no model call.
- **During a run:** the progress panel shows each agent's status and tool-call count, polled every 1.5 seconds. The previous result stays visible at reduced opacity, with no layout jump.
- **Stale results:** when the inputs no longer match the run on screen, a banner says so and the export warns before downloading.
- **Evidence links:** clicking any evidence reference opens and highlights that record and claim in the evidence explorer.
- **Errors:** when the server is unreachable, the page names the problem and the command to start the server, then clears the message when the server is back.

## Deliberately left out

There are no accounts, saved projects, or side-by-side run comparison, and no dark mode. They weren't needed for the decision the dashboard supports.
