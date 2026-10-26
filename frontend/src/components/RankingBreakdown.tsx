import { useState } from 'react'
import type { OpportunityResult, Ranking, ScoringConfig } from '../types.ts'
import { num, pct } from '../format.ts'
import { EvidenceRefs, Pips, StatusBadge, Tabs } from './ui.tsx'

export function RankingBreakdown({ ranking, scoring }: { ranking: Ranking; scoring: ScoringConfig }) {
  const all: OpportunityResult[] = [...ranking.ranked, ...ranking.insufficient_data]
  const [selected, setSelected] = useState(all[0]?.pathway_id ?? '')
  const o = all.find((x) => x.pathway_id === selected) ?? all[0]
  if (!o) return null
  const weighted = o.criteria.reduce((sum, c) => sum + (c.weighted_contribution ?? 0), 0)
  return (
    <div>
      <Tabs items={all.map((x) => ({ id: x.pathway_id, label: x.name }))} value={o.pathway_id} onChange={setSelected} />
      <div className="kpis">
        <div className="kpi"><div className="label">Attractiveness</div><div className="value">{num(o.attractiveness)} <span className="small muted">of 5</span></div>
          <div className="sub">weighted average of the assessed criteria</div></div>
        <div className="kpi"><div className="label">Weighted score so far</div><div className="value">{num(weighted)}</div>
          <div className="sub">sum of contributions; range {num(o.attractiveness_range[0])}–{num(o.attractiveness_range[1])}</div></div>
        <div className="kpi"><div className="label">Data completeness</div><div className="value">{pct(o.completeness.assessed_weight)}</div>
          <div className="sub">of the weight assessed (minimum {pct(ranking.min_completeness)} to rank)</div></div>
        <div className="kpi"><div className="label">Evidence quality</div><div className="value" style={{ fontSize: 18 }}>{o.evidence.strongest ? `${o.evidence.strongest} at best` : 'none cited'}</div>
          <div className="sub">{o.evidence.by_quality.high} high · {o.evidence.by_quality.moderate} moderate · {o.evidence.by_quality.low} low · {o.evidence.by_quality.unverified} unverified</div></div>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>Criterion</th><th className="num">Weight</th><th>Score</th><th>Weighted contribution</th><th>What the score means</th><th>Basis and assumptions</th></tr>
          </thead>
          <tbody>
            {o.criteria.map((c) => {
              const max = c.weight * 5
              return (
                <tr key={c.criterion} className={c.score === null ? 'muted' : undefined}>
                  <td><strong>{c.label}</strong><div className="small muted">{scoring.rubric[c.criterion]?.question}</div></td>
                  <td className="num">{pct(c.weight)}</td>
                  <td style={{ whiteSpace: 'nowrap' }}><Pips score={c.score} /> {c.score ?? ''}</td>
                  <td>
                    {c.weighted_contribution === null ? <span className="small">–</span> : (
                      <div className="bar-cell" title={`${num(c.weighted_contribution)} of a possible ${num(max)}`}>
                        <div className="bar-track"><div className="bar-fill" style={{ width: `${(c.weighted_contribution / max) * 100}%` }} /></div>
                        <span className="small" style={{ fontVariantNumeric: 'tabular-nums' }}>{num(c.weighted_contribution)} / {num(max)}</span>
                      </div>
                    )}
                  </td>
                  <td className="small">{c.meaning}</td>
                  <td className="small">
                    <StatusBadge status={c.method === 'rule' ? 'accent' : c.method === 'analyst' ? 'neutral' : 'warning'}
                      label={c.method === 'rule' ? 'deterministic rule' : c.method === 'analyst' ? 'agent judgment' : 'not assessed'} />
                    <div style={{ marginTop: 4 }}>{c.rationale}</div>
                    {c.inputs.length > 0 && (
                      <details style={{ marginTop: 4 }}><summary className="small muted">Inputs ({c.inputs.length})</summary>
                        <ul className="plain">{c.inputs.map((i) => <li key={i}>{i}</li>)}</ul></details>
                    )}
                    <div style={{ marginTop: 4 }}><EvidenceRefs refs={c.evidence_ids} /></div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {o.completeness.missing_inputs.length > 0 && (
        <p className="small ink-2" style={{ marginTop: 10 }}>Missing economic inputs: {o.completeness.missing_inputs.join(', ')}.</p>
      )}
    </div>
  )
}
