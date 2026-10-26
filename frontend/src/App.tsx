import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, ApiError } from './api.ts'
import type {
  EconomicAssumptions, EvidenceLibrary, Feedstock, FieldError, FinalAssessment, Health, Preview, ProjectInfo, RunWithInputs,
} from './types.ts'
import { num, pct, time } from './format.ts'
import { validateInputs } from './validate.ts'
import { Callout, Empty, EvidenceContext, Section, StatusBadge } from './components/ui.tsx'
import { FeedstockForm } from './components/FeedstockForm.tsx'
import { FeedstockProfile } from './components/FeedstockProfile.tsx'
import { OpportunityComparison } from './components/OpportunityComparison.tsx'
import { RankingBreakdown } from './components/RankingBreakdown.tsx'
import { CommercialAssessment } from './components/CommercialAssessment.tsx'
import { RecommendedActions } from './components/RecommendedActions.tsx'
import { EvidenceExplorer } from './components/EvidenceExplorer.tsx'
import { ExecutionTrace } from './components/ExecutionTrace.tsx'

const SECTIONS = [
  ['input', 'Feedstock input'], ['profile', 'Feedstock profile'], ['comparison', 'Opportunity comparison'],
  ['ranking', 'Ranking breakdown'], ['commercial', 'Commercial assessment'], ['actions', 'Recommended actions'],
  ['evidence', 'Evidence explorer'], ['trace', 'Agent execution trace'], ['export', 'Export'],
] as const

const POLL_MS = 1500
const keyOf = (feedstock: Feedstock | null, assumptions: EconomicAssumptions) => JSON.stringify({ feedstock, economic_assumptions: assumptions })
const scrollTo = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [project, setProject] = useState<ProjectInfo | null>(null)
  const [library, setLibrary] = useState<EvidenceLibrary | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [feedstock, setFeedstock] = useState<Feedstock | null>(null)
  const [assumptions, setAssumptions] = useState<EconomicAssumptions>({})
  const [serverErrors, setServerErrors] = useState<FieldError[]>([])
  const [preview, setPreview] = useState<Preview | null>(null)
  const [previewing, setPreviewing] = useState(false)
  const [previewError, setPreviewError] = useState<string | null>(null)

  const [run, setRun] = useState<RunWithInputs | null>(null)
  const [result, setResult] = useState<FinalAssessment | null>(null) // the last finished result, kept while a new run works
  const [resultKey, setResultKey] = useState<string | null>(null) // the inputs that result used
  const [runError, setRunError] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)
  const [focus, setFocus] = useState<{ ref: string; nonce: number } | null>(null)
  const previewRequest = useRef(0)

  // --- Initial load ---------------------------------------------------------------------------------
  const load = useCallback(async () => {
    setLoadError(null)
    try {
      const [h, p, lib] = await Promise.all([api.health(), api.project(), api.evidence()])
      setHealth(h); setProject(p); setLibrary(lib)
      setRunError(null); setPreviewError(null) // errors from before a successful reload no longer apply
      let fs: Feedstock = p.feedstock
      let ea: EconomicAssumptions = p.economic_assumptions
      try {
        const latest = await api.latest()
        if (latest.inputs?.feedstock) fs = latest.inputs.feedstock
        if (latest.inputs?.economic_assumptions) ea = latest.inputs.economic_assumptions
        setRun(latest)
        setResult(latest.result)
        setResultKey(keyOf(fs, ea)) // the saved run used these inputs (or the demo inputs, for command-line runs)
      } catch (e) {
        if (!(e instanceof ApiError && e.status === 404)) throw e
      }
      setFeedstock(fs); setAssumptions(ea)
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : String(e))
    }
  }, [])
  useEffect(() => { void load() }, [load])

  const clientErrors = useMemo(() => (feedstock ? validateInputs(feedstock, assumptions) : []), [feedstock, assumptions])
  const errors = useMemo(() => [...clientErrors, ...serverErrors], [clientErrors, serverErrors])
  const inputsKey = keyOf(feedstock, assumptions)

  // --- Deterministic preview (no model), refreshed as the form changes ---------------------------------
  useEffect(() => {
    if (!feedstock) return
    setServerErrors([])
    if (clientErrors.length) return
    const id = ++previewRequest.current
    const timer = setTimeout(async () => {
      setPreviewing(true)
      try {
        const p = await api.preview({ feedstock, economic_assumptions: assumptions })
        if (id === previewRequest.current) {
          setPreview(p); setPreviewError(null)
          setRunError((prev) => (prev?.startsWith('Cannot reach') ? null : prev)) // the server is back
        }
      } catch (e) {
        if (id !== previewRequest.current) return
        if (e instanceof ApiError && e.status === 422) setServerErrors(e.fieldErrors)
        else setPreviewError(e instanceof Error ? e.message : String(e))
      } finally {
        if (id === previewRequest.current) setPreviewing(false)
      }
    }, 400)
    return () => clearTimeout(timer)
  }, [inputsKey])

  // --- Live run ------------------------------------------------------------------------------------------
  const running = run?.status === 'running'
  useEffect(() => {
    if (!run || run.status !== 'running') return
    const timer = setInterval(async () => {
      try {
        const next = await api.run(run.run_id)
        setRun(next)
        if (next.status !== 'running') {
          if (next.result) { setResult(next.result); setResultKey(next.inputs ? keyOf(next.inputs.feedstock, next.inputs.economic_assumptions ?? {}) : null) }
          if (next.status === 'error') setRunError(next.error)
        }
      } catch (e) {
        setRunError(`Lost contact with the run: ${e instanceof Error ? e.message : String(e)}`)
      }
    }, POLL_MS)
    return () => clearInterval(timer)
  }, [run])

  async function startRun() {
    if (!feedstock) return
    setRunError(null)
    if (clientErrors.length || serverErrors.length) {
      setRunError('Fix the highlighted inputs in section 1 before running the assessment.')
      scrollTo('input')
      return
    }
    setStarting(true)
    try {
      const { run_id } = await api.startRun({ feedstock, economic_assumptions: assumptions })
      setRun(await api.run(run_id))
      scrollTo('run-status')
    } catch (e) {
      if (e instanceof ApiError && e.status === 422) { setServerErrors(e.fieldErrors); scrollTo('input') }
      setRunError(e instanceof Error ? e.message : String(e))
    } finally {
      setStarting(false)
    }
  }

  function resetToDemo() {
    if (!project) return
    setFeedstock(project.feedstock); setAssumptions(project.economic_assumptions)
  }

  const openEvidence = useCallback((ref: string) => {
    setFocus({ ref, nonce: Date.now() })
    scrollTo('evidence')
  }, [])

  // --- Render ---------------------------------------------------------------------------------------------
  if (loadError) {
    return (
      <main style={{ maxWidth: 720, margin: '80px auto', padding: '0 24px' }}>
        <Callout tone="error" title="The dashboard couldn't load">{loadError}</Callout>
        <div className="btn-row" style={{ marginTop: 16 }}><button className="btn" onClick={() => void load()}>Try again</button></div>
      </main>
    )
  }
  if (!project || !library || !feedstock || !health) {
    return <main style={{ maxWidth: 720, margin: '80px auto', padding: '0 24px' }}><p className="ink-2"><span className="spinner" /> Loading BioValue AI…</p></main>
  }

  const names = Object.fromEntries(project.pathways.map((p) => [p.id, p.name]))
  const titles = Object.fromEntries(project.agents.map((a) => [a.id, a.title]))
  const stale = Boolean(result) && (running || resultKey !== inputsKey)
  const cited = new Set<string>()
  if (result) {
    for (const o of [...result.decision.ranking.ranked, ...result.decision.ranking.insufficient_data]) o.evidence.cited_records.forEach((id) => cited.add(id))
    result.market?.forEach((m) => m.source_ids.forEach((id) => cited.add(id)))
  }
  const noResult = <Empty>No assessment yet. Run the assessment to call the four agents.</Empty>

  return (
    <EvidenceContext.Provider value={openEvidence}>
      <header className="topbar">
        <div className="brand">
          <h1>BioValue AI</h1>
          <p>Kraft lignin opportunity assessment · {project.name}</p>
        </div>
        <div className="spacer" />
        <div className="meta">
          Model {health.model} via Portkey<br />
          {health.api_key_configured ? <StatusBadge status="good" label="API key configured" /> : <StatusBadge status="critical" label="No API key" />}
        </div>
        <button className="btn primary" onClick={() => void startRun()} disabled={running || starting}>
          {running || starting ? <><span className="spinner" /> Running…</> : result ? 'Rerun assessment' : 'Run assessment'}
        </button>
      </header>

      <div className="layout">
        <nav className="toc" aria-label="Sections">
          <ol>{SECTIONS.map(([id, title], i) => <li key={id}><a href={`#${id}`}><span>{i + 1}</span>{title}</a></li>)}</ol>
        </nav>

        <div className="content">
          <div id="run-status">
            {!health.api_key_configured && (
              <Callout tone="error" title="PORTKEY_API_KEY is not set">The form and the deterministic profile work, but running the agents will fail until the key is added to .env.</Callout>
            )}
            {runError && <Callout tone="error" title="Assessment problem">{runError}</Callout>}
            <RunStatus run={run} result={result} stale={stale} running={running} titles={titles} />
          </div>

          <Section id="input" number={1} title="Feedstock input"
            intro="Edit the stream below. It starts with the fictional kraft lignin demo. Every change is checked and the profile below updates; run the assessment to send the inputs to the four agents.">
            <FeedstockForm feedstock={feedstock} assumptions={assumptions} pathways={project.pathways} errors={errors}
              dryMatter={preview ? `${num(preview.feedstock.normalized.dry_mass_t_per_yr)} t/yr` : null}
              onChange={(f, a) => { setFeedstock(f); setAssumptions(a) }} />
            <div className="btn-row" style={{ marginTop: 18 }}>
              <button className="btn primary" onClick={() => void startRun()} disabled={running || starting}>
                {running ? 'Assessment running…' : result ? 'Rerun assessment with these inputs' : 'Run assessment'}
              </button>
              <button className="btn" onClick={resetToDemo} disabled={running}>Reset to demo values</button>
              {errors.length > 0 && <span className="field-error">{errors.length} input problem(s) to fix</span>}
              {previewing && <span className="hint"><span className="spinner" /> checking…</span>}
            </div>
          </Section>

          <Section id="profile" number={2} title="Feedstock profile"
            intro="The current inputs in canonical units, with missing data and uncertainty. Calculated by the deterministic code as you edit; no model involved.">
            {previewError && <Callout tone="error" title="Couldn't check the inputs">{previewError}</Callout>}
            <FeedstockProfile preview={preview} updating={previewing}
              agent={result?.feedstock?.agent ?? null} agentRunId={result?.run_id ?? null} />
          </Section>

          <Section id="comparison" number={3} title="Opportunity comparison" stale={stale}
            intro="Attractiveness on the 1–5 scale for the three pathways, from the deterministic scoring engine, with data completeness shown separately.">
            {result ? <OpportunityComparison ranking={result.decision.ranking} report={result.decision.report} /> : noResult}
          </Section>

          <Section id="ranking" number={4} title="Ranking breakdown" stale={stale}
            intro="Each criterion's score, what it means, its weight, and its weighted contribution, with the basis behind it. Unassessed criteria count toward neither the score nor the ranking order.">
            {result ? <RankingBreakdown ranking={result.decision.ranking} scoring={project.scoring} /> : noResult}
          </Section>

          <Section id="commercial" number={5} title="Commercial assessment" stale={stale}
            intro="Indicative economics in three scenarios, shown only where the inputs exist, with formulas and assumptions; plus the Commercialization Agent's assessment.">
            {result ? <CommercialAssessment result={result} names={names} /> : noResult}
          </Section>

          <Section id="actions" number={6} title="Recommended actions" stale={stale}
            intro="The Decision Agent's next validation steps and the evidence needed before proceeding.">
            {result ? <RecommendedActions result={result} names={names} /> : noResult}
          </Section>

          <Section id="evidence" number={7} title="Evidence explorer"
            intro="Every source in the local library, with the claims it supports, the passage behind each claim, and its limitations. Click any reference elsewhere on the page to open it here.">
            <EvidenceExplorer library={library} cited={cited} focus={focus} />
          </Section>

          <Section id="trace" number={8} title="Agent execution trace"
            intro="Which agents ran, in order, which tools they called, what the guards did, and whether any stage failed.">
            {run ? <ExecutionTrace run={run} titles={titles} /> : noResult}
          </Section>

          <Section id="export" number={9} title="Export"
            intro="Download the completed assessment. The report is built from the saved run, so it matches what is shown above.">
            {result ? (
              <div>
                {stale && !running && <Callout tone="warning" title="The inputs have changed since this run">The report describes run {result.run_id}. Rerun the assessment to export the current inputs.</Callout>}
                <div className="btn-row" style={{ marginTop: 12 }}>
                  <a className="btn primary" href={api.reportUrl(result.run_id, 'html')} download>Download HTML report</a>
                  <a className="btn" href={api.reportUrl(result.run_id, 'md')} download>Download Markdown report</a>
                  <span className="hint">Run {result.run_id} · {time(result.created_at)}</span>
                </div>
              </div>
            ) : <Empty>Run the assessment first; there is nothing to export yet.</Empty>}
          </Section>
        </div>
      </div>
    </EvidenceContext.Provider>
  )
}

function RunStatus({ run, result, stale, running, titles }: {
  run: RunWithInputs | null; result: FinalAssessment | null; stale: boolean; running: boolean; titles: Record<string, string>
}) {
  if (!run) return <Callout tone="neutral" title="No assessment yet">The sections below fill in after the first run. Running calls the course model four times in sequence and takes about two minutes.</Callout>
  if (running) {
    return (
      <div className="callout info">
        <strong><span className="spinner" /> Assessment running · {run.run_id}</strong>
        <p className="small" style={{ margin: '4px 0 10px' }}>The agents run one after another. Results below are from the previous run until this one finishes.</p>
        <div className="progress">
          {run.trace.agents.map((a) => (
            <div key={a.agent} className={`stage ${a.status}`}>
              <div><StatusBadge status={a.status} /></div>
              <div style={{ marginTop: 4 }}>{titles[a.agent] ?? a.agent}</div>
              <div className="sub">{a.tool_calls.length} tool call(s){a.attempts > 1 ? ` · attempt ${a.attempts}` : ''}</div>
            </div>
          ))}
        </div>
      </div>
    )
  }
  if (!result) return null
  const failed = result.execution.agents.filter((a) => a.status !== 'ok')
  return (
    <div>
      <Callout tone={result.status === 'complete' ? 'neutral' : 'warning'}
        title={`Showing run ${result.run_id} · ${result.status}`}>
        Finished {time(result.created_at)} with {result.model}: {result.usage.requests} model requests, {num(result.usage.input_tokens)} input and {num(result.usage.output_tokens)} output tokens.
        {failed.length > 0 && <> Not completed: {failed.map((a) => `${titles[a.agent]} (${a.status})`).join(', ')}. See section 8.</>}
        {result.decision.ranking.insufficient_data.length > 0 && <> {result.decision.ranking.insufficient_data.length} pathway(s) have too little assessed weight to rank (minimum {pct(result.decision.ranking.min_completeness)}).</>}
      </Callout>
      {stale && <Callout tone="warning" title="Inputs changed since this run">Sections 3–6 and the export describe the inputs used in run {result.run_id}. Rerun the assessment to update them.</Callout>}
    </div>
  )
}
