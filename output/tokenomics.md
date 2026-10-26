# BioValue AI tokenomics (gpt-6-luna)

All token counts are the provider's own usage metadata, recorded per agent by PydanticAI's `RunUsage` and written to
`usage_log.json` after every run. Nothing here is simulated.

Sources (25 October 2026):

- `output/evaluation/eval_results.json`: the evaluation suite, 12 live runs.
- `output/evaluation/results.json` and `summary.md`: baseline vs optimized, 8 live runs.
- `output/cost_estimate.json`: the monthly estimate.

**Model and price.** The project requirements say the course key covers **gpt-6-luna** only, so all four agents use it.
gpt-6-luna has a verified course price in `data/model_prices.json` (MGT 409 Lecture 11, via HW 6):

| Token type | USD per million tokens |
|---|---|
| Input | 0.10 |
| Cached input | 0.01 |
| Output | 0.50 |

Every cost below is measured tokens × that price. Earlier results on gpt-5.6-luna, which had to be priced by proxy,
are archived in `output/evaluation/archive_gpt-5.6-luna/` and not used here.

## What is recorded for every run

For each agent, every run records:

- model and configuration
- requests and tool calls
- input tokens, split into cached and uncached
- output tokens
- reasoning tokens
- latency
- cost

A figure the provider does not report is written as "not reported", never as 0.

## Tokens and cost per run (evaluation suite, optimized configuration)

| | Mean per completed run (12 runs) |
|---|---|
| Input tokens | 50,745 (28,187 cached, 56%) |
| Output tokens | 11,157 |
| Cost | **USD 0.0081** |
| Wall-clock time | median 77.4 s |

On average, the Commercialization Agent uses the most tokens: 20,898 input and 5,007 output, because it reads the
evidence for three pathways and calls the most tools. Next come the Market Intelligence Agent (13,944 / 3,620), the
Feedstock Agent (9,080 / 954) and the Decision Agent (6,822 / 1,576).

## Baseline vs optimized configuration

| | Baseline | Optimized |
|---|---|---|
| Context passed between agents | full JSON of earlier outputs | compact summaries |
| Evidence tool results | full records with quoted passages and URLs | trimmed: no publisher or date in search, no URL or quoted passages in records |
| Scenario tool result | full | trimmed to the figures the agent needs |
| Prompt hints | none | short efficiency hints; `find_trl_claims` tool for the Commercialization Agent |
| Arithmetic, scoring, guards | identical | identical |

The comparison used 4 cases × 2 configurations, with one live run each:

| Case | Config | Requests | Input tokens | Cached | Output tokens | Seconds | USD | Quality checks |
|---|---|---|---|---|---|---|---|---|
| demo | baseline | 13 | 97,259 | 54,476 | 17,284 | 106.32 | 0.013465 | 8/8 |
| demo | optimized | 11 | 44,327 | 22,825 | 9,760 | 68.52 | 0.007258 | 8/8 |
| missing_ash | baseline | 14 | 90,068 | 54,778 | 13,435 | 93.14 | 0.010794 | 8/8 |
| missing_ash | optimized | 12 | 51,311 | 27,266 | 12,360 | 94.55 | 0.008857 | 8/8 |
| injection_screened | baseline | 11 | 57,889 | 29,898 | 10,307 | 69.20 | 0.008252 | 7/8 |
| injection_screened | optimized | 12 | 47,676 | 25,789 | 10,072 | 70.09 | 0.007483 | 8/8 |
| injection_unscreened | baseline | 12 | 64,075 | 34,037 | 11,315 | 76.48 | 0.009002 | 8/8 |
| injection_unscreened | optimized | 11 | 43,671 | 22,254 | 9,319 | 66.57 | 0.007024 | 8/8 |

Means over the 3 comparable cases (the unscreened injection case is excluded because its input differs):

| Config | Input tokens | Cached | Output tokens | USD per run | Median s |
|---|---|---|---|---|---|
| baseline | 81,739 | 46,384 | 13,675 | 0.0108 | 93.1 |
| optimized | 47,771 | 25,293 | 10,731 | 0.0079 | 70.1 |
| change | −41.6% | −45.5% | −21.5% | −27.4% | −24.7% |

How to read this:

- **Quality held up.** Quality checks were 32/32 for optimized and 31/32 for baseline. The baseline miss was a TRL the
  agent did not confirm, so that pathway's readiness was "not assessed". The same miss happened in the gpt-5.6-luna
  comparison.
- **The tradeoff** is that the agents see less context, with no quoted passages in evidence records. The checks did not
  show this as a loss in these runs.
- **The sample is small.** There are 3 comparable runs per configuration, so these differences are indicative, not
  statistically established.

**Decision:** `optimized` is the default (`BIOVALUE_RUN_CONFIG`).

## Monthly model cost

These assumptions are explicit and live in `data/tokenomics_assumptions.json`:

- **Usage:** 4 assessments per user per month. This is an assumption: a strategist screens about one stream or scenario
  a week.
- **Tokens:** tokens per assessment are the evaluation suite's measured mean above.
- **Price:** gpt-6-luna's verified price.

| Scale | Assessments / month | Model cost / month |
|---|---|---|
| 1 user | 4 | USD 0.03 |
| 100 users | 400 | USD 3.25 |
| 10,000 users | 40,000 | USD 324.65 |

`scripts/cost_estimate.py` gives the same kind of estimate from the three phase-4 cases per configuration:

- baseline: USD 4.33 and USD 433.47 per month for 100 and 10,000 users
- optimized: USD 3.15 and USD 314.65 per month for 100 and 10,000 users

## Costs not estimated

The following costs are not estimated, because there are no verified quotes for them:

- hosting (API server with the built dashboard)
- Portkey plan
- storage
- monitoring
- support

They are kept separate from model costs and listed as `null` in `data/tokenomics_assumptions.json`. The model cost
scales linearly. Longer inputs, retries, or a lower cache-hit rate would raise it.
