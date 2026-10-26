import { useState } from 'react'
import type { Assessment, EvidenceFinding, FinalAssessment, Judgment, ScenarioName } from '../types.ts'
import { SCENARIOS } from '../types.ts'
import { humanize, num } from '../format.ts'
import { Callout, EvidenceRefs, Pips, StatusBadge, Tabs } from './ui.tsx'

const STEPS = ['dry_mass', 'usable_feedstock', 'product_output', 'revenue', 'variable_cost', 'gross_contribution', 'contribution_per_t_feedstock']

function Findings({ title, items }: { title: string; items: EvidenceFinding[] }) {
  return (
    <div>
      <strong className="small">{title}</strong>
      {items.length ? (
        <ul className="plain small">{items.map((f, i) => <li key={i}>{f.statement} <EvidenceRefs refs={f.evidence} /></li>)}</ul>
      ) : <p className="small muted">None supported by the evidence.</p>}
    </div>
  )
}

function RuleScore({ title, a }: { title: string; a: Assessment }) {
  return (
    <div className="kpi">
      <div className="label">{title}</div>
      <div style={{ margin: '4px 0' }}><Pips score={a.score} /> <strong>{a.score ?? ''}</strong></div>
      <div className="small ink-2">{a.rationale}</div>
    </div>
  )
}

function JudgmentView({ title, j }: { title: string; j: Judgment | null }) {
  return (
    <div className="kpi">
      <div className="label">{title} (agent judgment)</div>
      {j ? <>
        <div style={{ margin: '4px 0' }}><Pips score={j.score} /> <strong>{j.score}</strong></div>
        <div className="small ink-2">{j.rationale}</div>
        <div><EvidenceRefs refs={j.evidence} /></div>
      </> : <div className="small muted">Not assessed.</div>}
    </div>
  )
}

export function CommercialAssessment({ result, names }: { result: FinalAssessment; names: Record<string, string> }) {
  const stages = result.commercialization ?? []
  const [selected, setSelected] = useState(stages[0]?.pathway_id ?? '')
  if (!stages.length) {
    return <Callout tone="warning" title="No commercial assessment">The Commercialization Agent did not finish in this run. See the execution trace.</Callout>
  }
  const s = stages.find((x) => x.pathway_id === selected) ?? stages[0]
  const a = s.scenario_analysis
  const base = a.scenarios.base.steps
  const reasons = [...new Set(Object.values(base).map((st) => st.reason).filter(Boolean))]
  const calculated = STEPS.filter((k) => SCENARIOS.some((sc) => a.scenarios[sc].steps[k].status === 'calculated'))
  const f = s.findings
  return (
    <div>
      <Tabs items={stages.map((x) => ({ id: x.pathway_id, label: names[x.pathway_id] ?? x.pathway_id }))} value={s.pathway_id} onChange={setSelected} />
      <p className="small ink-2" style={{ marginBottom: 12 }}>Product: {a.product}</p>
      {a.missing_inputs.length > 0 && (
        <Callout tone="warning" title="Indicative economics stop here">
          Missing inputs: {a.missing_inputs.join(', ')}. Steps that need them are not calculated, and nothing is filled in with zero.
          Add your own values under Economic assumptions in section 1 to see the rest of the chain.
        </Callout>
      )}
      <h3>Scenario analysis</h3>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Step</th><th>Formula</th>{SCENARIOS.map((sc) => <th key={sc} className="num">{humanize(sc)}</th>)}<th>Unit</th></tr></thead>
          <tbody>
            {STEPS.map((key) => {
              const st = base[key]
              const shown = calculated.includes(key)
              return (
                <tr key={key} className={shown ? undefined : 'muted'}>
                  <td>{st.label}</td>
                  <td className="small">{st.formula}</td>
                  {SCENARIOS.map((sc: ScenarioName) => {
                    const step = a.scenarios[sc].steps[key]
                    return <td key={sc} className="num" title={step.reason || step.inputs.join('; ')}>{step.status === 'calculated' ? num(step.value) : 'not calculated'}</td>
                  })}
                  <td className="small">{st.unit}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {reasons.length > 0 && <ul className="plain small ink-2" style={{ marginTop: 8 }}>{reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>}

      <h3>Scenario assumptions</h3>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Input</th>{SCENARIOS.map((sc) => <th key={sc} className="num">{humanize(sc)}</th>)}<th>Unit</th><th>Basis</th><th>Note</th></tr></thead>
          <tbody>
            {a.assumptions.map((x) => (
              <tr key={x.input}>
                <td>{x.input}{x.held_constant && <div className="hint">held constant across scenarios</div>}</td>
                <td className="num">{num(x.conservative ?? x.base)}</td><td className="num">{num(x.base)}</td><td className="num">{num(x.optimistic ?? x.base)}</td>
                <td className="small">{x.unit}</td>
                <td className="small">{humanize(x.basis)} <EvidenceRefs refs={x.evidence_ids} /></td>
                <td className="small ink-2">{x.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="hint" style={{ marginTop: 8 }}>{a.not_calculated_metrics}</p>

      <h3>Deterministic scores</h3>
      <div className="kpis" style={{ gridTemplateColumns: 'repeat(3, minmax(0, 1fr))' }}>
        <RuleScore title="Feedstock compatibility" a={s.feedstock_compatibility} />
        <RuleScore title="Technical readiness" a={s.technical_readiness} />
        <RuleScore title="Indicative economics" a={s.indicative_economics} />
      </div>

      <h3>Commercialization Agent assessment</h3>
      <div className="two-col">
        <div>
          <Findings title="Processing requirements" items={f.processing_requirements} />
          <div style={{ marginTop: 10 }}>
            <strong className="small">Technical maturity</strong>
            {f.technical_maturity ? <p className="small">{f.technical_maturity.statement} <EvidenceRefs refs={f.technical_maturity.evidence} /></p>
              : <p className="small muted">No TRL was confirmed from the evidence.</p>}
          </div>
          <div style={{ marginTop: 10 }}><Findings title="Adoption barriers" items={f.adoption_barriers} /></div>
        </div>
        <div>
          <JudgmentView title="Commercialization feasibility" j={f.commercialization_feasibility} />
          <div style={{ marginTop: 10 }}>
            <strong className="small">Uncertainties</strong>
            <ul className="plain small">{f.uncertainties.map((u, i) => <li key={i}>{u}</li>)}</ul>
          </div>
          {f.assumptions.length > 0 && <div style={{ marginTop: 10 }}>
            <strong className="small">Assumptions noted by the agent</strong>
            <ul className="plain small">{f.assumptions.map((u, i) => <li key={i}>{u}</li>)}</ul>
          </div>}
          <p className="small" style={{ marginTop: 10 }}><StatusBadge status={a.missing_inputs.length ? 'warning' : 'good'}
            label={a.missing_inputs.length ? `${a.missing_inputs.length} economic input(s) missing` : 'all economic inputs supplied'} /></p>
        </div>
      </div>
    </div>
  )
}
