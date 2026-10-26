# BioValue AI · Kraft lignin opportunity finder (MGT 409 final project)

BioValue AI helps a kraft pulp mill decide what to do with the lignin it can extract from black liquor. It screens three product pathways (phenolic resins and adhesives, polyurethane materials and foams, and carbon materials), scores them on a transparent 1–5 scale, and shows separately how complete the data is and how strong the evidence is.

Four agents run in a fixed order. Every number comes from plain, tested Python that they call as tools:

1. **Feedstock Agent:** normalizes the feedstock record and flags missing data, inconsistencies, and constraints.
2. **Market Intelligence Agent:** finds applications, customers, competing materials, and qualification requirements in the local evidence library.
3. **Commercialization Agent:** runs the economics and scenario tools, and assesses processing needs, technical maturity, and adoption barriers.
4. **Decision Agent:** ranks the pathways with the scoring engine, explains the drivers, and recommends validation steps.

## Status

| Phase | What | Status |
|---|---|---|
| 0 | Project setup: `.venv`, pinned requirements, `.gitignore`, `.env.example`, prompt log | Done |
| 1 | Data foundation, deterministic business logic, evidence library (15 verified sources, 46 supported claims) | Done |
| 2 | The four agents (PydanticAI through Portkey), fixed-order workflow, output guards, execution trace, token tracking | Done; run live |
| 3 | Dashboard: FastAPI backend and a React dashboard | Done; tested in the browser |
| 4 | Safety, reliability, and tokenomics: injection screening, prohibited-claim guard, run budget, usage and cost logging, baseline vs optimized configuration | Done; compared live (`output/safety.md`, `output/tokenomics.md`) |
| 5 | Evaluation suite: 15 scenarios with expectations written before running, three test tiers, user-test questionnaire | Done; run live (`output/evaluation/EVALUATION.md`, `FINDINGS.md`) |
| 6 | Submission: `report.html`, `slides.html`, final README, fresh-setup check | Done (see "Submission files") |
| 7 | Official requirements applied: gpt-6-luna (the only model the course key covers), every live result re-measured, one-command start with the dashboard served by the API, report in the required eight sections, reveal.js slides, public repository | Done; results on gpt-6-luna; earlier gpt-5.6-luna results archived |
| 8 | Dashboard additions: About tab, wood-motif background, and a literature-based reference stream (published, cited values) as a second input preset | Done; reference run live once; the evaluation still uses the fictional demo |

## Quick start (Python only, about 5 minutes)

Tested on macOS with **Python 3.14.7**. The built dashboard is committed in `frontend/dist`, so Node is not needed to run the app.

1. Clone the repository and enter the folder.
2. Create the environment and install the dependencies:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

3. Give the app a Portkey key: put a `.env` file with `PORTKEY_API_KEY=...` either in the project folder (`cp .env.example .env` and fill it in) or in the folder one level above it. The app checks its own folder first, then the folder above.
4. Start the app:

```bash
.venv/bin/python -m uvicorn backend.main:app --port 8765
```

5. Open http://127.0.0.1:8765 in a browser. The dashboard opens with the fictional demo mill and the latest saved run; click **Rerun assessment** to run the four agents live (usually one to three minutes).

## Configuration

Put your Portkey key in `.env`. It is in `.gitignore` and is never committed. The code reads `.env` from the project folder first, then from the folder above it; a `PORTKEY_API_KEY` already exported in your shell also works and takes precedence. The tests never call the model, so they run without a key.

| Variable | Required | Default | What it does |
|---|---|---|---|
| `PORTKEY_API_KEY` | for live runs | – | Portkey key; sent as the API key and the `x-portkey-api-key` header |
| `PORTKEY_BASE_URL` | no | `https://api.portkey.ai/v1` | Gateway URL |
| `BIOVALUE_MODEL` | no | `gpt-6-luna` | Model for all four agents. The course key covers gpt-6-luna only; the app ignores a shared `OPENAI_MODEL` setting on purpose |
| `BIOVALUE_RUN_CONFIG` | no | `optimized` | `optimized` (compact context and tool results) or `baseline` (full context) |
| `BIOVALUE_STORE_INPUTS` | no | off | `1` also saves each run's dashboard inputs to `output/runs/`; by default they stay in memory |

Check the configuration without calling the model: start the app and open http://127.0.0.1:8765/api/health. It reports the model, the run configuration, and whether a key was found (never the key itself).

## The dashboard

Started as in the quick start, the API serves the dashboard at http://127.0.0.1:8765. To edit the frontend, run the development server instead (needs Node 24): keep the API running, then `npm --prefix frontend install` and `npm --prefix frontend run dev`, and open http://localhost:5173. After editing, rebuild the committed copy with `npm --prefix frontend run build`.

The dashboard has two tabs. **About the tool** explains in plain words what you can do with it, the idea behind it (with sources), and who can benefit; link to it directly with `?tab=about`. **Assessment** opens with the fictional demo feedstock and the latest saved run, in nine sections. Under the input form, **Load fictional demo** and **Load literature reference** switch between the invented demo mill and a stream described only by published, cited values; editing a published figure makes it your own estimate and removes its citation.

1. **Feedstock input:** editable form, checked as you type. A blank figure is recorded as missing data, never as zero. Optional economic assumptions are entered per pathway.
2. **Feedstock profile:** units, ranges, missing data, and uncertainty for the current inputs (deterministic, no model).
3. **Opportunity comparison:** attractiveness on the 1–5 scale with its possible range, and data completeness shown separately.
4. **Ranking breakdown:** each criterion's score, meaning, weight, weighted contribution, and basis.
5. **Commercial assessment:** scenario economics where inputs exist, with formulas and assumptions.
6. **Recommended actions:** validation steps and the evidence needed before proceeding.
7. **Evidence explorer:** every source, with the passage behind each claim; any reference on the page opens here.
8. **Agent execution trace:** agents, tool calls, guard actions, failures, and tokens. It updates live during a run.
9. **Export:** the assessment as an HTML or Markdown report.

**Run assessment** sends the current inputs to the four agents, which usually takes one to three minutes (median 77 s in the evaluation runs; the slowest run so far took about 3.3 minutes). If the inputs change after a run, sections 3–6 and the export are marked as describing the earlier run until you rerun.

## Run the workflow from the command line

```bash
.venv/bin/python scripts/run_workflow.py
```

This runs all four agents on the demo project with the course model. It prints each agent's status, tool calls, guard actions, and tokens, then the ranking and validation steps. Each run (from the dashboard or the command line):

- saves the full assessment to `output/runs/<run id>.json` and `output/latest_assessment.json`;
- appends to `output/audit_trail.json` (every agent and tool call) and `output/usage_log.json` (tokens per agent).

Cost is calculated from the measured tokens at gpt-6-luna's verified course price in `data/model_prices.json` (see `output/tokenomics.md`). A model without a verified price would show *not calculated*, with a labelled proxy estimate.

The run configuration is `optimized` by default (compact context and tool results); set `BIOVALUE_RUN_CONFIG=baseline` for the full-context version. User inputs are kept in memory only; set `BIOVALUE_STORE_INPUTS=1` to also save them next to each run.

## Run the tests

The tests are split into three tiers, so a model failure is never mixed up with a code failure:

| Tier | Command | Model | What it covers |
|---|---|---|---|
| Deterministic | `.venv/bin/python -m pytest -m "not mock"` | none | Units, calculations, scoring, schemas, safety rules, cost arithmetic, and every hand-calculated scenario expectation |
| Mock | `.venv/bin/python -m pytest -m mock` | scripted stand-in (PydanticAI `FunctionModel`) | The real agents, tools, guards, and API, with real tool calls but no API calls |
| Live | `.venv/bin/python -m evals.run_eval --tiers live` | `gpt-6-luna` through Portkey | The 15 evaluation scenarios in `evals/scenarios.json` (needs `PORTKEY_API_KEY`; about 20 minutes) |

`.venv/bin/python -m pytest` runs the first two tiers together, offline, in a few seconds.

| File | What it checks |
|---|---|
| `tests/test_units.py` | Unit conversions; rejection of unknown units, dry-basis moisture, out-of-range shares, negatives, NaN |
| `tests/test_calc.py` | Each calculation step against a hand-worked example, scenarios, missing inputs, zero values, invalid units, currency mismatches |
| `tests/test_scoring.py` | Weighted contributions, rubric meanings, missing criteria, band edges, the scoring rules, evidence summaries, ranking |
| `tests/test_feedstock.py`, `test_evidence.py`, `test_project.py`, `test_demo_project.py` | The schemas, and the real demo data and evidence library |
| `tests/test_refs.py` | Evidence references and the number check that stops agents from inventing figures |
| `tests/test_workflow.py` | All four agents in order, tool tracking, guards (fabricated references, unsupported numbers, wrong values, reordered rankings), transient and permanent API errors, timeouts, runaway tool loops, missing API key |
| `tests/test_api.py` | The dashboard API: preview, field-level validation errors, full runs, one run at a time, reports, error reporting, size limits, inputs not stored |
| `tests/test_safety.py` | Prompt injection in the feedstock and in an evidence record, a fooled agent that still can't move scores, malformed output, run budget, API key never stored, the facts/assumptions/estimates/unknowns ledger |
| `tests/test_safety_rules.py`, `tests/test_tokenomics.py` | Injection screening, prohibited claims, secret redaction; cost arithmetic, proxy labels, monthly estimates, the usage log |
| `tests/test_scenarios.py`, `tests/test_eval_runner.py` | Every evaluation scenario builds, and its hand-calculated expectations match the engine; the runner's agreement arithmetic |
| `tests/test_reference_feedstock.py` | The literature reference: every figure with a value cites a source with quotes, unpublished figures stay blank, edited figures lose their citation, sources always come from the stored file, and the evaluation still runs on the fictional demo |

## Evaluate

```bash
.venv/bin/python -m evals.run_eval
```

This runs all three tiers and writes `output/evaluation/eval_results.json` (machine-readable) and `output/evaluation/EVALUATION.md` (summary). `--tiers` picks tiers and `--scenarios S01 S04` picks scenarios.

- **Scenarios** (`evals/scenarios.json`): 15 cases, each with its expected behavior written before the first run. Expectations are never edited to fit a result; any change must be logged in `expectation_changes` with a reason, and a test checks that list.
- **Measures:** gap coverage, reference validity (re-checked independently of the guards), calculation accuracy, agreement with expert rankings, uncertainty handling, run success and latency, and tokens and proxy cost per completed assessment.
- **Expert agreement** is reported as *not measured* until a reviewer fills in `evals/expert_rankings.json` (copy `evals/expert_rankings_template.json`).
- **User test:** `output/user_test_questionnaire.md` is the instrument for comparing a professional's normal screening with BioValue AI. It was run once, on 2026-10-25, with one participant (an anonymous chemical engineer): 60 minutes with their normal approach against 20 with BioValue AI, the same top choice both times, and 5 of 5 on all eight statements. The answers are in `output/user_test_results.json`. One participant is not a general result.

`--tiers deterministic mock --merge` reruns only the pytest tiers and keeps the saved live results; `--resummarize` recomputes the measures and `EVALUATION.md` from the saved results without running anything.

`scripts/evaluate.py` is the phase-4 comparison of the baseline and optimized configurations (`output/evaluation/results.json`, `summary.md`), and `scripts/cost_estimate.py` turns it into monthly cost estimates (`output/cost_estimate.json`).

## How the agents are kept honest

- **Fixed sequence, no recursion.** The workflow runs Feedstock → Market Intelligence → Commercialization → Decision, once each. Each agent sees only its own tools, and no tool can start an agent.
- **Validated data between agents.** Each agent's answer must fit its schema (`backend/agents/schemas.py`), and the next agent receives the validated answer.
- **No arithmetic in the model.** Dry mass, economics, compatibility, readiness, and the ranking come from tools that run the tested code. The ranking always comes from `score_and_rank`.
- **Guards** (`backend/agents/guards.py`) check every answer against the data:
  - every evidence reference must exist and belong to the right pathway;
  - every number must appear in what it cites or in a tool result;
  - numbers copied from tools must match them;
  - the Decision Agent can't reorder the ranking.

  A failing answer goes back to the agent with the problems listed, up to twice. After that, code repairs it: it drops unsupported statements or bad references and never invents content. Every guard action appears in the trace.
- **Untrusted text stays data.** Feedstock text fields and evidence passages are screened for instruction-like text before any model sees them; a match replaces the whole field and is logged as a security event. Tool results that carry user or document text are labelled as untrusted data.
- **No overclaiming.** Answers that claim guaranteed profitability, verified customer demand, or engineering approval are rejected, and every run carries a disclaimer. A market-evidence score of 4–5 needs high- or moderate-quality sources.
- **Facts, assumptions, estimates, unknowns.** Code (not the model) sorts what each assessment rests on into these four groups.
- **Limits.** Requests over 100 KB, text fields over 1,000 characters, and lists over 30 items are refused before a run starts. Each run has a 400,000-token budget; later agents are skipped once it is spent.
- **Secrets.** API keys are redacted from errors, traces, and logs.
- **Timeouts and bounded retries.** Each model request has a 90-second timeout. Each agent run has a 5-minute timeout and usage limits (15 requests, 30 tool calls, 200,000 tokens). A timeout or transient API error gets one more attempt. If an agent fails, the later ones are skipped and the assessment is saved as *partial*, still with the deterministic ranking.

## How the calculations work (`backend/calc.py`)

```
dry mass            = wet mass x (1 - moisture)                  moisture on a wet basis
usable feedstock    = dry mass x availability fraction           only if the fraction is supplied
product output      = usable feedstock x yield                   t product per t usable dry feedstock
revenue             = product output x price
variable cost       = sum of cost items, each per t of product or per t of usable feedstock
gross contribution  = revenue - variable cost
contribution per t  = gross contribution / usable feedstock
```

- **Missing inputs.** A missing input stops the steps that need it; those steps are marked *not calculated*, with the reason.
- **Units.** Units are explicit, and money is never converted between currencies.
- **Assumptions.** Every input records its basis (measured, evidence, your assumption, or fictional assumption).
- **Scenarios.** Inputs have conservative, base, and optimistic values, and swapped values are rejected.
- **Not calculated.** Gross margin, NPV, and IRR are not calculated: the capital costs, fixed costs, discount rate, and definitions they need aren't available.

## How the scoring works (`backend/scoring.py`, `data/scoring_config.json`)

| Criterion | Weight | How it is scored |
|---|---|---|
| Feedstock compatibility | 25% | **Rule:** largest relative gap to the evidence's numeric requirements (within all = 5; up to 10%, 50%, 100% = 4, 3, 2; more = 1) |
| Technical readiness | 20% | **Rule:** a TRL stated in a cited claim (1–2 = 1, 3–4 = 2, 5–6 = 3, 7 = 4, 8–9 = 5) |
| Market evidence | 20% | **Agent judgment** with rationale and evidence references, against the rubric |
| Indicative economics | 20% | **Rule:** base-scenario gross contribution per tonne of usable feedstock. The bands are illustrative and need calibrating |
| Commercialization feasibility | 15% | **Agent judgment** with rationale, against the rubric |

Attractiveness is the weighted average of the criteria that were assessed. Data completeness and evidence quality are reported separately. **Missing evidence is never a low score:** an unassessed criterion lowers completeness, and pathways with less than 60% of the weight assessed are listed as *insufficient data* instead of being ranked last.

**Current demo result.** With the demo inputs, only carbon materials can be ranked (2.19, with 80% of the weight assessed, in every live run so far). Phenolic resins score higher on what was assessed (3.09–3.73 across the gpt-6-luna evaluation runs, because its market-evidence and feasibility judgments vary by a point between runs), but only 55% of the weight was assessed. That is because no source gives a numeric lignin spec for resins, and no source gives a price or yield for any pathway.

## Data

| File | Contents |
|---|---|
| `data/demo_feedstock.json` | **Fictional** kraft lignin cake at an invented mill. Mw, phenolic OH, and sodium are deliberately missing |
| `data/reference_feedstock.json`, `data/reference_project.json` | **Literature-based reference stream**: published values for BioChoice lignin (a commercial LignoBoost softwood kraft lignin) and the LignoBoost process. Every figure cites a source, and each source quotes the passages it was taken from, checked on 2026-10-25. Unpublished figures (carbohydrates, phenolic OH, sodium) are blank; no economic inputs are published. The evaluation does not use it |
| `data/demo_project.json` | The demo project; its only economic input is a fictional availability fraction (40/50/60%) |
| `data/evidence_library.json` | 15 verified evidence records (11 high quality, 4 moderate); each supported claim quotes its source |
| `data/scoring_config.json` | Weights, the 1–5 rubric, and the rule cut-offs, with notes |
| `data/model_prices.json` | Verified model prices (only `gpt-6-luna`, from HW 6) |

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| The page at http://127.0.0.1:8765 doesn't load, or the dashboard says the API is unreachable | The server isn't running. Start it with the `uvicorn` command in the quick start (from the project folder). In development mode the Vite server forwards `/api` to `127.0.0.1:8765`, so the API must run too. |
| The page says the dashboard build is missing | `frontend/dist` was deleted. Rebuild it with `npm --prefix frontend install && npm --prefix frontend run build` (needs Node), or restore it from the repository. |
| `address already in use` on 8765 or 5173 | Another copy is running. Find it with `lsof -i :8765` (or `:5173`) and stop it. |
| `/api/health` shows `"api_key_configured": false`, or a run fails with a missing-key error | `.env` is missing or has no `PORTKEY_API_KEY`. Copy `.env.example` to `.env` in the project folder (or the folder above) and restart the API. |
| `Operation not permitted` when running `.venv/bin/uvicorn` | Some sandboxes block the script wrapper. Use `.venv/bin/python -m uvicorn ...` as shown. |
| "Run … is still going" (HTTP 409) | One assessment runs at a time. Wait for it to finish (usually one to three minutes; section 8 shows progress). |
| HTTP 422 with a field name | An input failed validation (unit, range, text over 1,000 characters, list over 30 items). The dashboard highlights the field. |
| HTTP 413 | The request body is over 100 KB. |
| A run ends as *partial* | An agent failed after its retries or the run's token budget was spent. Section 8 shows which agent and why; the deterministic ranking is still shown. |
| `ModuleNotFoundError: backend` when running a script | Run commands from the project folder, as shown (`pytest.ini` puts the project on the path for tests; use `python -m evals.run_eval` for the evaluation). |
| Cost shows *not calculated* | The model set in `BIOVALUE_MODEL` has no verified price in `data/model_prices.json`; a labelled proxy estimate is shown instead. With the default gpt-6-luna the cost is calculated. |
| Old runs show no ledger or configuration | They were saved before those fields existed; they load with "not recorded". |

## Submission files

| File | What it is |
|---|---|
| `report.html` | The project report (open in a browser; prints to about 10–15 pages) |
| `slides.html` | The presentation: 10 reveal.js slides (loaded from a CDN, so it needs an internet connection); arrow keys move, F goes full screen |
| `README.md` | This file |
| `AI_prompts.md` | Every prompt used with Claude Code, word for word |
| `output/evaluation/EVALUATION.md`, `eval_results.json`, `FINDINGS.md` | Evaluation summary, machine-readable results, and findings |
| `output/safety.md`, `output/tokenomics.md`, `output/cost_estimate.json` | Safety testing; token use, configuration comparison, and cost projections |
| `output/user_test_questionnaire.md` | The user-test instrument (run once, with one participant; results in `output/user_test_results.json`) |
| `output/screenshots/` | Screenshots of the running dashboard used in the report and slides |
| `output/submission_links.json` | Repository, app, and video links shown in the report and on the first slide (fill in, then rebuild) |
| `output/user_test_results.json` | The real user test's results (one participant, 2026-10-25), entered from the test; the report and slides read them when rebuilt |

`report.html` and `slides.html` are built from the result files by `.venv/bin/python scripts/build_report.py` (self-contained files with the screenshots embedded). The screenshots come from `node scripts/capture_screenshots.mjs` with the API and dashboard running and Google Chrome installed; it only reads the page, so it shows the latest saved run (`--run <run id>` shows an earlier saved run, `--click "<button text>"` presses a button first, `section@800` keeps the top 800 pixels, and `section!` opens every expandable detail).

## Project layout

| Path | Role |
|---|---|
| `backend/units.py`, `calc.py`, `scoring.py` | Deterministic units, economics, and scoring |
| `backend/feedstock.py`, `evidence.py`, `project.py`, `data.py` | Schemas and data loading |
| `backend/agents/` | The four agents: tools, schemas, guards, evidence references |
| `backend/prompts/` | One prompt per agent |
| `backend/workflow.py` | The fixed-order workflow, retries, and the final assessment |
| `backend/trace.py` | Execution tracking |
| `backend/inputs.py` | Turning dashboard input into a validated project |
| `backend/safety.py`, `backend/tokenomics.py` | Injection screening, prohibited claims, redaction; prices, cost reports, monthly estimates |
| `backend/main.py` | FastAPI routes for the dashboard |
| `backend/report.py` | HTML and Markdown export |
| `frontend/` | React + Vite + TypeScript dashboard; `frontend/dist` is the committed build the API serves |
| `scripts/run_workflow.py` | Command-line run on the demo |
| `scripts/evaluate.py`, `scripts/cost_estimate.py` | Baseline vs optimized comparison; monthly cost estimates |
| `scripts/build_report.py`, `report_*.py`, `capture_screenshots.mjs` | Builds `report.html` and `slides.html` from the result files; captures dashboard screenshots with headless Chrome |
| `evals/` | Evaluation scenarios, their inputs, the runner, and the expert-ranking template |
| `output/` | Saved runs, audit trail, usage log, `design.md`, `safety.md`, `tokenomics.md`, `user_test_questionnaire.md`, `evaluation/` |
| `AI_prompts.md` | Every prompt used with Claude Code |
