import type { FinalAssessment } from '../types.ts'
import { humanize } from '../format.ts'
import { Callout } from './ui.tsx'
import { LedgerPanel } from './LedgerPanel.tsx'

export function RecommendedActions({ result, names }: { result: FinalAssessment; names: Record<string, string> }) {
  const report = result.decision.report
  if (!report) {
    return (
      <Callout tone="warning" title="No recommendations in this run">
        The Decision Agent did not finish, so there are no validation steps. The ranking shown was computed by the workflow
        ({result.decision.ranking_source}).
      </Callout>
    )
  }
  return (
    <div>
      <Callout tone="neutral" title="Read this first">
        <ul className="plain small">{result.disclaimers.map((d, i) => <li key={i}>{d}</li>)}</ul>
      </Callout>
      <p style={{ maxWidth: 820, margin: '16px 0 18px' }}>{report.summary}</p>
      <h3>Validation steps</h3>
      <ol className="steps">
        {report.validation_steps.map((s) => (
          <li key={s.action}>
            <div>
              <div className="action">{s.action}</div>
              <div className="small ink-2" style={{ margin: '2px 0 6px' }}>{s.reason}</div>
              <div className="small">Resolves: {s.addresses.map((a, i) => <span key={i} className="chip plain">{humanize(a)}</span>)}</div>
            </div>
          </li>
        ))}
      </ol>
      <h3>Evidence needed before proceeding</h3>
      <div className="two-col">
        <div>
          <strong className="small">What would most change the ranking</strong>
          <ul className="plain small">{report.ranking_changers.map((c, i) => <li key={i}>{c}</li>)}</ul>
          {report.caveats.length > 0 && <>
            <strong className="small" style={{ display: 'block', marginTop: 12 }}>Caveats</strong>
            <ul className="plain small">{report.caveats.map((c, i) => <li key={i}>{c}</li>)}</ul>
          </>}
        </div>
        <div>
          {report.shortlist.map((s) => (
            <div key={s.pathway_id} style={{ marginBottom: 12 }}>
              <strong className="small">{names[s.pathway_id] ?? s.pathway_id} {s.rank ? `(#${s.rank})` : '(insufficient data)'}</strong>
              <ul className="plain small">
                {s.main_drivers.map((d, i) => <li key={i}><span className="muted">Driver:</span> {d}</li>)}
                {s.what_could_change_it.map((d, i) => <li key={i}><span className="muted">Would change with:</span> {d}</li>)}
              </ul>
            </div>
          ))}
        </div>
      </div>
      <h3>What this assessment rests on</h3>
      <LedgerPanel ledger={result.ledger} />
    </div>
  )
}
