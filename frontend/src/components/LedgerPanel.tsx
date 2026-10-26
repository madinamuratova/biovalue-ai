import { useState } from 'react'
import type { Ledger } from '../types.ts'
import { EvidenceRefs, Tabs } from './ui.tsx'

type Kind = 'documented_facts' | 'assumptions' | 'estimates' | 'unknowns'

const KINDS: { id: Kind; label: string; intro: string }[] = [
  { id: 'documented_facts', label: 'Documented facts', intro: 'Stated in a cited evidence record, or a measured input.' },
  { id: 'assumptions', label: 'Assumptions', intro: 'Inputs nobody measured: fictional values and economic assumptions.' },
  { id: 'estimates', label: 'Estimates', intro: 'Calculated from the above, scored by a rule, or judged by an agent.' },
  { id: 'unknowns', label: 'Unknowns', intro: 'Missing inputs and data, criteria that could not be assessed, and gaps the agents reported.' },
]

const REF = /\b(EV-[A-Z]+-\d{2}#R?\d+)\b/

/** What the assessment rests on, sorted by code into the four kinds so they are never mixed up. */
export function LedgerPanel({ ledger }: { ledger: Ledger | null }) {
  const [kind, setKind] = useState<Kind>('documented_facts')
  if (!ledger) return <p className="small muted">This run was saved before the ledger existed; rerun the assessment to see it.</p>
  const current = KINDS.find((k) => k.id === kind)!
  return (
    <div>
      <Tabs items={KINDS.map((k) => ({ id: k.id, label: `${k.label} (${ledger[k.id].length})` }))} value={kind} onChange={setKind} />
      <p className="small ink-2" style={{ marginBottom: 8 }}>{current.intro}</p>
      <div className="table-wrap" style={{ maxHeight: 360, overflowY: 'auto' }}>
        <table className="compact">
          <thead><tr><th>Statement</th><th>Source</th></tr></thead>
          <tbody>
            {ledger[kind].map((item, i) => {
              const ref = item.source.match(REF)?.[1]
              return (
                <tr key={i}>
                  <td className="small">{item.statement}</td>
                  <td className="small ink-2" style={{ maxWidth: 380 }}>{ref ? <><EvidenceRefs refs={[ref]} /> {item.source.replace(ref, '').replace(/^ · /, '')}</> : item.source}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
