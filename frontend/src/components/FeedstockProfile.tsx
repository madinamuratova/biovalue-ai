import type { FeedstockAgentOutput, Preview, Quantity } from '../types.ts'
import { humanize, num, pct } from '../format.ts'
import { Callout, Empty, StatusBadge } from './ui.tsx'

const SEVERITY_TONE: Record<string, string> = { high: 'critical', medium: 'warning', low: 'neutral' }

function range(q: Quantity): string {
  if (q.low === null && q.high === null) return '–'
  if (q.low === undefined && q.high === undefined) return '–'
  return `${num(q.low ?? q.value)} – ${num(q.high ?? q.value)}`
}

export function FeedstockProfile({ preview, updating, agent, agentRunId }: {
  preview: Preview | null
  updating: boolean
  agent: FeedstockAgentOutput | null
  agentRunId: string | null
}) {
  if (!preview) return <Empty>{updating ? 'Checking the inputs…' : 'Fix the highlighted inputs to see the profile.'}</Empty>
  const { normalized: n, checks, profile } = preview.feedstock
  const rows = [...Object.entries(n.composition), ...Object.entries(n.other_composition)]
  const dry = profile.dry_matter
  return (
    <div style={{ opacity: updating ? 0.6 : 1, transition: 'opacity .2s' }}>
      {n.is_fictional && (
        <Callout tone="warning" title={({ literature_reference: 'Published literature values, not one mill\u2019s measurements',
          mixed: 'Estimated or mixed data', fictional_demo: 'Fictional data' } as Record<string, string>)[profile.data_status] ?? 'Not measured data'}>
          {checks.disclaimer}
        </Callout>
      )}
      <div className="kpis" style={{ marginTop: 14 }}>
        <div className="kpi"><div className="label">Wet quantity</div><div className="value">{num(n.wet_mass_t_per_yr)}</div><div className="sub">t/yr</div></div>
        <div className="kpi"><div className="label">Moisture</div><div className="value">{pct(n.moisture_fraction)}</div><div className="sub">of wet mass</div></div>
        <div className="kpi"><div className="label">Dry matter</div><div className="value">{num(n.dry_mass_t_per_yr)}</div>
          <div className="sub">t/yr{dry.low != null && dry.high != null ? ` · range ${num(dry.low)}–${num(dry.high)}` : ''}</div></div>
        <div className="kpi"><div className="label">Dry lignin</div><div className="value">{num(n.dry_lignin_t_per_yr)}</div><div className="sub">t/yr (dry matter × lignin content)</div></div>
      </div>

      <div className="two-col">
        <div>
          <h3>Properties</h3>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Property</th><th className="num">Value</th><th>Unit</th><th className="num">Range</th><th>Basis</th></tr></thead>
              <tbody>
                {rows.map(([key, q]) => (
                  <tr key={key} className={q.value === null ? 'muted' : undefined}>
                    <td title={q.method || undefined}>{humanize(key)}</td>
                    <td className="num">{q.value === null ? <StatusBadge status="warning" label="missing" /> : num(q.value)}</td>
                    <td className="small">{q.unit}</td>
                    <td className="num">{range(q)}</td>
                    <td className="small">{humanize(q.basis)}{q.source ? <div className="hint" title="Published source; see Published sources in section 1">{q.source}</div> : null}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="hint" style={{ marginTop: 6 }}>Ranges are the expected variation over a year. Hover a property to see its measurement method.</p>
        </div>
        <div>
          <h3>Missing data and uncertainty</h3>
          <table className="compact">
            <tbody>
              {checks.data_gaps.map((g) => (
                <tr key={`${g.field}-${g.issue}`}>
                  <td style={{ width: 110 }}><StatusBadge status={SEVERITY_TONE[g.severity]} label={`${g.severity} · ${humanize(g.issue)}`} /></td>
                  <td><strong className="small">{humanize(g.field)}</strong><div className="small ink-2">{g.impact}</div><div className="small muted">Next: {g.next_step}</div></td>
                </tr>
              ))}
            </tbody>
          </table>
          <h3>Checks</h3>
          <ul className="plain small">
            {checks.checks.map((c) => (
              <li key={c.check}><StatusBadge status={c.passed ? 'good' : 'critical'} label={c.passed ? 'passed' : 'failed'} /> {c.check}: {c.detail}</li>
            ))}
          </ul>
          <h3>Infrastructure</h3>
          <p className="small"><strong>Operating:</strong> {checks.infrastructure.operating.join(', ') || 'none'}</p>
          <p className="small"><strong>Not available:</strong> {checks.infrastructure.not_available.join(', ') || 'none'}</p>
          {checks.infrastructure.planned.length > 0 && <p className="small"><strong>Planned:</strong> {checks.infrastructure.planned.join(', ')}</p>}
        </div>
      </div>

      <h3>Feedstock Agent findings</h3>
      {agent ? (
        <div className="two-col">
          <div>
            <p className="small ink-2" style={{ marginBottom: 6 }}>From run {agentRunId}.</p>
            <p className="small" style={{ marginBottom: 8 }}>{agent.summary}</p>
            <strong className="small">Constraints</strong>
            <ul className="plain small">{agent.constraints.map((c, i) => <li key={i}>{c}</li>)}</ul>
          </div>
          <div>
            <strong className="small">Inconsistencies</strong>
            {agent.inconsistencies.length ? <ul className="plain small">{agent.inconsistencies.map((c, i) => <li key={i}>{c}</li>)}</ul> : <p className="small muted">None found.</p>}
            <strong className="small">Data quality notes</strong>
            <ul className="plain small">{agent.data_quality_notes.map((c, i) => <li key={i}>{c}</li>)}</ul>
          </div>
        </div>
      ) : <Empty>Run the assessment to add the Feedstock Agent's constraints and notes.</Empty>}
    </div>
  )
}
