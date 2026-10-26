# BioValue AI user test: questionnaire and recording sheet

**Status: conducted once**, on 2026-10-25, with one participant (an anonymous chemical engineer). The answers are recorded
in `output/user_test_results.json`; this file stays the blank instrument that was used, and nothing in it is a result.

| | |
|---|---|
| **Purpose** | Compare a professional's normal initial screening of by-product opportunities with the same screening done in BioValue AI. Measure completion time, usefulness, clarity, and missing considerations. |
| **Participant** | One industry or climate-tech professional, e.g. pulp-and-paper strategy, biorefining, materials sourcing, or climate-tech investing. |
| **Time** | About 45 minutes. |
| **Materials** | The fictional demo feedstock and a second fictional variant (see below), the running app, a timer, and this sheet. |

## Before you start (read to the participant)

- **About the data:** the two task feedstocks are fictional. Please do not enter confidential data about a real mill.
- **What is being tested:** we are testing the tool, not you. There are no right answers.
- **What we record:** we record times, ratings, and your answers. We quote you only if you agree. Your name is not put in
  the project report unless you agree.
- **Stopping:** you can stop at any time.

Consent to take part (yes / no): ____ Consent to quote anonymously (yes / no): ____

## A. Background

1. Current role and organisation type (no company name needed):
2. Years of experience with pulp, biorefining, chemicals, materials, or climate-tech investment:
3. How often do you screen commercial uses for a by-product or side stream?
   - never
   - once a year or less
   - a few times a year
   - monthly or more
4. When you do, what do you normally use? Tick all that apply.
   - literature or patent search
   - market reports
   - supplier or customer calls
   - internal experts
   - spreadsheets
   - general AI chat tools
   - other: ____
5. What does your output usually look like? For example: a ranked list, a memo, a slide, a go/no-go call.

## B. Two timed tasks

There are two comparable fictional feedstocks. Give a different one for each task, so the second task is not just a
repeat. Alternate the order if you test more than one person.

- **Feedstock 1:** the demo, Pinecrest Mill. 40,000 t/yr wet, 35% moisture, ash 1.0%.
- **Feedstock 2:** a high-moisture, low-volume variant. 5,000 t/yr wet, 60% moisture (evaluation scenario S04).

The pathways are the same in both tasks: phenolic resins and adhesives, polyurethanes, and carbon materials.

**The task, in the participant's words:**

> "Give me your initial view of which of these three uses deserves a closer look first, why, and what you would need
> to check next. Stop when you would be comfortable sending that view to a colleague."

| | Task 1 | Task 2 |
|---|---|---|
| Method (your normal way / BioValue AI) | | |
| Feedstock (1 / 2) | | |
| Start time | | |
| Stop time | | |
| Minutes to a view they would send | | |
| BioValue AI only: minutes waiting for the run | | |
| Their top choice | | |
| Their confidence in it (1 = none, 5 = high) | | |
| Sources or features they used | | |

For the BioValue AI task:

- Time from entering the data to the participant's stated view, including the time spent reading the result, not just
  the run.
- Note which dashboard sections they open: ranking breakdown, commercial assessment, evidence explorer, execution
  trace, report export.

## C. Ratings after the BioValue AI task

Scale: 1 = strongly disagree, 5 = strongly agree.

| # | Statement | 1–5 | Comment |
|---|---|---|---|
| C1 | The result was useful for deciding what to look at next. | | |
| C2 | I understood why the pathways were ranked the way they were. | | |
| C3 | It was clear which statements were documented facts, assumptions, estimates, or unknowns. | | |
| C4 | I could check the sources behind the market statements. | | |
| C5 | The tool was honest about what it could not assess (missing data, missing economics). | | |
| C6 | The recommended validation steps are ones I would actually take. | | |
| C7 | I would trust this output as a first screen, before my own checks. | | |
| C8 | Compared with my normal approach, this saved me time. | | |

## D. Comparison and missing considerations (open questions)

1. Compared with your normal screening, what did BioValue AI do better, and what did it do worse?
2. What important considerations were missing? Prompts, if needed:
   - capital cost
   - logistics and offtake contracts
   - permits
   - mill integration
   - competing internal uses of the lignin
   - customer qualification time
   - carbon accounting
   - policy incentives
3. Did anything look wrong, overstated, or misleading? Point to the screen or report section.
4. Was anything confusing, such as terms, scores, the completeness threshold, or "insufficient data"?
5. What would you need to see before acting on a result like this?
6. Would you use it again for a first screen? Why or why not?

## E. Facilitator notes

- Ask the participant to think aloud. Do not explain the tool's reasoning during the timed tasks.
- Optional, after the timed tasks: show the *Load literature reference* preset (published, cited values for a real
  commercial lignin) and ask whether it changes how much they trust the result. Record the answer separately from the
  timed tasks.
- Record the times as they happen. Do not reconstruct them afterwards.
- Write answers in the participant's words. Mark your own interpretation separately.
- With one participant, report results as one person's experience, not as evidence of general user impact.
- Store the completed sheet outside the repository if it contains anything identifying.

## F. Results summary (fill in after the test)

| Measure | Normal workflow | BioValue AI |
|---|---|---|
| Minutes to a view they would send | | |
| Confidence in the top choice (1–5) | | |
| Usefulness (C1) | n/a | |
| Clarity (C2, C3) | n/a | |
| Missing considerations named | | |
| Errors or overstatements the participant found | | |

Date conducted: ____ Facilitator: ____ Participant ID: ____
