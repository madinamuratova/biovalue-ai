# BioValue AI — AI Prompts Log

MGT 409 · AI Foundations for Managers · Final Project

This file records the prompts I typed to Claude Code for each step of the project. Each section has:

- the step number and title
- the prompt I used, copied word for word
- a follow-up prompt, only if I needed one, with one sentence explaining what was missing or not working after the first prompt

<!--
How to add a follow-up (replace "None." under "Follow-up prompt"):

> [follow-up prompt, word for word]

**What was missing after the first prompt:** [one sentence]
-->

---

## Step 1: Review the course setup and plan the project

### Prompt

> I am building BioValue AI for my Yale SOM MGT 409 AI Foundations for Managers final project.
> Before writing or modifying code, inspect my current project directory, existing files, README, dependencies, starter code, and environment configuration. Identify the exact course requirements for the application and submission deliverables.
> BioValue AI is a multi-agent decision-support application that helps pulp mills identify commercially promising uses for industrial by-products, initially focusing on kraft lignin.
> The four planned agents are:
>
> 1. Feedstock Agent
> 2. Market Intelligence Agent
> 3. Commercialization Agent
> 4. Decision Agent
>
> I want a working web application with real tool use, deterministic calculations, transparent opportunity scoring, token and cost tracking, safety defenses, and reproducible tests.
> First:
>
> * Summarize the current project structure and technology stack.
> * Identify the required model provider and API configuration.
> * Identify existing code that should be reused.
> * List the required submission files and formats.
> * Propose the smallest architecture that meets the requirements.
> * Identify potential implementation risks.
>
> Do not overwrite existing files or expose secrets. Do not build the application yet. Give me a concise implementation plan based on the actual repository and course requirements.

### Follow-up prompt

None.

---

## Step 2: Project setup and deterministic core (phases 0 and 1)

### Prompt

> Go ahead with the plan based on HW 1–6 conventions. Start with phase 0 and phase 1.

### Follow-up prompt

None.

---

## Step 3: Data foundation: feedstock model and evidence library

### Prompt

> Implement the data foundation for BioValue AI using the architecture you just proposed.
> Create a structured feedstock model and a small local evidence library for a fictional kraft-lignin stream.
> The feedstock schema should support:
>
> * Annual wet feedstock quantity and units
> * Moisture content
> * Dry-matter quantity
> * Lignin content and its measurement basis
> * Ash content
> * Sulfur and other relevant composition information, if available
> * Feedstock variability
> * Current use or disposal route
> * Available processing infrastructure
> * Geographic market
> * Missing data and uncertainty flags
>
> Create a demo feedstock with plausible illustrative values. Clearly mark the values as fictional assumptions rather than measured industrial data.
> Create an evidence library covering three initial product pathways:
>
> 1. Lignin substitution in phenolic resins and adhesives
> 2. Lignin-based polyurethane materials or foams
> 3. Lignin-derived carbon materials
>
> Each evidence record should contain an identifier, title, source or publisher, publication date if known, URL if verified, supported claims, technical requirements, limitations, and evidence-quality label.
> Do not invent publications, URLs, market prices, yields, or technical thresholds. If a claim cannot be supported by the available evidence, mark it as unverified or leave it out.
> Add tests for the data schemas and load the demo project successfully. Do not build the full agent workflow yet.
> Run the relevant tests and tell me exactly what passed or failed.

### Follow-up prompt

None.

---

## Step 4: Deterministic business logic

### Prompt

> Implement BioValue AI's deterministic business logic.
> Build tested Python functions or the equivalent in the existing stack for:
>
> 1. Converting wet feedstock mass into dry mass using moisture content.
> 2. Estimating usable feedstock quantity when a recovery or availability fraction is explicitly supplied.
> 3. Calculating illustrative product output from a supplied yield assumption.
> 4. Calculating indicative revenue, variable processing cost, and gross contribution when the required inputs are available.
> 5. Performing conservative, base, and optimistic scenario analysis.
> 6. Scoring and ranking product opportunities using configurable weights.
>
> Initial scoring weights:
>
> * Feedstock compatibility: 25%
> * Technical readiness: 20%
> * Market evidence: 20%
> * Indicative economics: 20%
> * Commercialization feasibility: 15%
>
> Use a transparent 1–5 scale, document what each score means, and show the weighted contribution of every criterion.
> Do not silently replace missing inputs with zero or treat missing evidence as proof that an opportunity performs poorly. Display evidence quality and data completeness separately from attractiveness.
> Make all assumptions visible and preserve the units in the output. Do not calculate gross margin, profitability, NPV, or IRR unless the necessary inputs and definitions are available.
> Add automated tests for normal inputs, missing data, invalid units, zero values, boundary conditions, and arithmetic correctness.
> Run the tests and report the actual results. Do not integrate the language model yet.

### Follow-up prompt

> (The Step 4 prompt above was sent a second time, word for word.)

**What was missing after the first prompt:** Nothing was missing; the tests were re-run and the results reported again.

> Keep carbon materials as one pathway for now; the applies_to labels are enough.

**What was missing after the first prompt:** This answered whether to split the carbon materials pathway into carbon fiber, hard carbon, and activated carbon.

---

## Step 5: Multi-agent workflow

### Prompt

> Now implement the multi-agent workflow for BioValue AI using the existing project architecture and the required course model provider.
> Create four specialized agents with structured inputs and outputs.
> Agent 1: Feedstock Agent
>
> * Normalize the feedstock data.
> * Use the unit-conversion and validation tools.
> * Identify missing properties, inconsistencies, and constraints.
> * Return a structured feedstock profile.
>
> Agent 2: Market Intelligence Agent
>
> * Use the local evidence retrieval tool to find relevant sources for the three product pathways.
> * Identify possible applications, target customers, competing materials, and qualification requirements where supported by evidence.
> * Return source IDs, supported claims, limitations, and missing market information.
> * Never fabricate citations or market data.
>
> Agent 3: Commercialization Agent
>
> * Combine the feedstock profile and market findings.
> * Use the deterministic economics calculator and scenario-analysis tool.
> * Evaluate processing requirements, technical maturity, adoption barriers, and missing inputs.
> * Return structured assessments with explicit assumptions and uncertainties.
>
> Agent 4: Decision Agent
>
> * Use the deterministic scoring engine to compare the candidate applications.
> * Generate a ranked shortlist and explain the main drivers of each ranking.
> * Recommend three to five validation steps.
> * Explain what new evidence could change the ranking.
>
> Requirements:
>
> * Use real tool calls and a fixed execution sequence.
> * Pass validated structured data between agents.
> * Use the actual course model and existing API configuration.
> * Add timeouts, bounded retries, and graceful failure handling.
> * Avoid uncontrolled recursive agent calls.
> * Validate outputs against schemas.
> * Track which agents and tools executed.
> * Keep deterministic arithmetic outside the LLM.
>
> Provide a working command or test that runs all four agents on the demo feedstock and produces a structured final assessment.
> Run the workflow and report actual failures. Do not simulate successful live-model calls or claim the workflow works until it has run.

### Follow-up prompt

None.

---

## Step 6: Dashboard

### Prompt

> Build the BioValue AI frontend using the existing framework.
> Create a professional industrial-strategy dashboard with the following sections:
>
> 1. Feedstock input: An editable form populated with the fictional kraft-lignin demo.
> 2. Feedstock profile: Show available properties, units, missing data, and uncertainty.
> 3. Opportunity comparison: Compare phenolic resins and adhesives, polyurethane materials or foams, and carbon materials.
> 4. Ranking breakdown: Display the overall weighted score, individual criteria, data completeness, evidence quality, and the assumptions behind each score.
> 5. Commercial assessment: Display indicative economics only where sufficient inputs exist, including formulas and scenario assumptions.
> 6. Recommended actions: Present the next three to five validation activities and the evidence needed before proceeding.
> 7. Evidence explorer: Let users inspect the sources supporting claims and recommendations.
> 8. Agent execution trace: Show which agents ran, which tools they used, and whether any stage failed.
> 9. Export: Allow users to download the completed assessment as an HTML or Markdown report.
>
> Connect the interface to the actual backend and agent workflow. Do not use hardcoded rankings as if they were live results.
> Include loading states, clear error messages, input validation, and a way to rerun the assessment after changing the feedstock data.
> Keep the design polished but restrained, with a clean layout, readable tables, and useful visualizations. Do not add unnecessary features.
> Run the application, test the complete user journey, and fix any broken interactions before proceeding.

### Follow-up prompt

> Try again

**What was missing after the first prompt:** The session stopped partway through testing; the rerun test had to be repeated because a page reload had restored the saved inputs before the run.

---

## Step 7: Safety, reliability, and tokenomics

### Prompt

> Implement the safety, reliability, and tokenomics requirements for BioValue AI.
> Safety
>
> * Treat user input and retrieved documents as untrusted data, not instructions.
> * Add a prompt-injection test using a malicious instruction embedded in a feedstock description or evidence record.
> * Require evidence references for factual market claims and validate that the referenced IDs exist.
> * Separate documented facts, assumptions, estimates, and unknowns.
> * Reject malformed model outputs.
> * Add input-size limits, timeouts, bounded retries, and a per-run budget limit.
> * Do not allow the app to claim guaranteed profitability, verified customer demand, or engineering approval.
> * Do not log API keys or unnecessarily store user-submitted data.
>
> Tokenomics
>
> * Record model, agent, input tokens, output tokens, cached tokens where available, latency, and estimated cost.
> * Use actual usage metadata returned by the provider.
> * Label unavailable usage information and estimated pricing honestly.
> * Implement a baseline and an optimized configuration.
> * Compare cost and output quality using the same evaluation cases.
> * Estimate monthly model costs for 100 and 10,000 users with explicit usage assumptions.
> * Separate model costs from hosting and other costs.
>
> Create tests demonstrating the safety defenses and usage logging. Run the tests, show the actual results, and document any limitations. Do not fabricate attack success rates, token usage, or cost savings.

### Follow-up prompt

None.

---

## Step 8: Evaluation suite and user-test questionnaire

### Prompt

> Create and execute the BioValue AI evaluation suite.
> Build at least 10 reproducible scenarios covering:
>
> * Complete and incomplete feedstock data
> * Different moisture levels and feedstock volumes
> * Potentially limiting composition characteristics
> * Missing economic inputs
> * Attractive assumptions with weak market evidence
> * Product qualification barriers
> * Contradictory market claims
> * Prompt injection
> * Unsupported requests to fabricate citations
> * Invalid or oversized inputs
>
> For each scenario, define expected behavior before running the app.
> Measure:
>
> 1. Coverage of expected feedstock-data gaps.
> 2. Validity of source references.
> 3. Accuracy of deterministic calculations.
> 4. Agreement with expert-reviewed opportunity rankings.
> 5. Appropriate handling of uncertainty.
> 6. Successful-run rate and latency.
> 7. Actual cost per completed assessment.
>
> Generate a machine-readable results file and a human-readable evaluation summary. Separate deterministic unit tests, mock-model tests, and live-model tests. Do not silently change expected results to make the model appear successful.
> Also prepare a short user-test questionnaire for an industry or climate-tech professional. It should compare their normal initial opportunity-screening workflow with BioValue AI, measuring completion time, usefulness, clarity, and missing considerations. I will conduct the real user test separately. Do not invent an interview or claim user impact without actual evidence.
> Run the available tests, report the real results, and identify the most important remaining weaknesses.

### Follow-up prompt

None.

---

## Step 9: Final submission (report, slides, README, final checks)

### Prompt

> Prepare BioValue AI for final submission to Yale SOM MGT 409.
> First, verify the actual project requirements and expected filenames against the course instructions and existing repository.
> Generate the required submission deliverables, including the following if required by the assignment:
> report.html
> A polished 10–15-page report when printed, covering:
>
> * Business problem and target user
> * Why BioValue AI is useful
> * Application architecture and four-agent workflow
> * Tools and deterministic calculations
> * Example lignin feedstock assessment
> * Opportunity scoring methodology
> * Evaluation design and actual results
> * Tokenomics and cost projections
> * Safety and prompt-injection testing
> * Real-user evaluation, if completed
> * Limitations and future improvements
>
> slides.html
> A concise presentation of no more than 10 slides, if that matches the course requirements. Include the problem, demo, architecture, key evaluation results, safety, costs, and lessons learned.
> README.md
> Provide installation instructions, environment configuration, startup commands, test commands, evaluation instructions, and troubleshooting.
> Final verification
>
> * Confirm that no API keys or secrets are committed.
> * Confirm that all referenced files exist.
> * Run the automated tests.
> * Verify the app from a fresh setup using the README instructions.
> * Check the final HTML report and slides for readability and missing content.
> * Confirm the exact deliverables and submission instructions.
>
> Use actual application screenshots, measured costs, and test results. Label illustrative data and assumptions clearly. Never invent results to make the project look better.
> At the end, give me a final checklist of what is complete, what remains incomplete, and what I must manually submit before the deadline.

### Follow-up prompt

> Try again

**What was missing after the first prompt:** Claude's response was cut off mid-stream while it was writing the report generator, so it had to resume.

---

## Step 10: Check against the official project requirements

### Prompt

> do we meet all the requirements for max point based on instreuctions provided?

### Follow-up prompt

> https://zlisto.github.io/mgt_409_fa26/project_requirements.html

**What was missing after the first prompt:** The official requirements page had not been shared, so the first answer could only check the project against my own earlier prompts.

---

## Step 11: Wood-themed background and an About tab

### Prompt

> so can you please add some wood icons on the backgroud of the website so that it has somewhat scandi design but with relevant elements. and also can you add a tab that explains simply and shortly the what exactly uou can do with the tool and a bit of the theory behind and who could benefit from it

### Follow-up prompt

None.

---

## Step 12: A literature-based reference stream

### Prompt

> is there any way to make the assumption not fictional? like based on research paper?

### Follow-up prompt

> Yes: add a literature-based reference stream as a second preset next to the fictional demo. Every figure must cite a verified source, unknowns stay blank, keep the evaluation on the fictional demo, run it live once, and add it to the report.

**What was missing after the first prompt:** The first answer researched which figures could be sourced and asked for a go-ahead before changing the app.

---

## Step 13: Check that every submission document is up to date

### Prompt

> did you update all the relevant submission docs as well

### Follow-up prompt

None.

---

## Step 14: Record the real user-test results

### Prompt

> how do i do that Two things only you can add before the deadline: the real user-test results (fill in output/user_test_results.json,

### Follow-up prompt

> can we do it here? you ask me the answer i type it and then you update it?

**What was missing after the first prompt:** The first answer explained how to edit the results file by hand; I preferred to answer the questions in the chat and have the file, report, and slides updated for me.

The answers I typed during this step are not copied here, because they include the participant's name and the participant asked to stay anonymous. What was recorded is in `output/user_test_results.json`.

---

## Step 15: Final submission format

### Prompt

> So here is what you submit:
>
> 1) HTML of report - put your github repo url in the report so we can clone it
>
> 2) HTML of slides - put your github repo url in the report so we can clone it
>
> 3) Nothing else - any other files you include will annoy me and be penalized
>
> If your github repo is not in your report and slide files, we cannot clone it and grade it, so do not forget.
>
> Also, if your repo is private, please mention this in your report and slides.

### Follow-up prompt

> I just learned that Canvas does not let you submit a url and files.  You have to choose one or the other.  I choose files. So here is what you submit:
>
> 1) HTML of report - put your github repo url in the report so we can clone it
>
> 2) HTML of slides - put your github repo url in the report so we can clone it
>
> 3) A video of you testing your app (optional)
>
> 4) Nothing else - any other files you include will annoy me and be penalized
>
> If your github repo is not in your report and slide files, we cannot clone it and grade it, so do not forget.
>
> Also, if your repo is private, please mention this in your report and slides.

**What was missing after the first prompt:** The instructor updated the submission rules to allow an optional video of the app being tested; the report and slides already contained the public repository link.

---
