import type { DecisionReport, OpportunityResult, Ranking } from '../types.ts'
import { humanize, num, pct } from '../format.ts'
import { Meter, StatusBadge } from './ui.tsx'

const x = (score: number) => `${((score - 1) / 4) * 100}%`

/** One row per pathway on a shared 1-5 scale: the dot is attractiveness (filled when ranked, hollow when the
 * pathway has too little data to rank), the band is the range it could take once unassessed criteria are scored. */
export function OpportunityComparison({ ranking, report }: { ranking: Ranking; report: DecisionReport | null }) {
  const all: OpportunityResult[] = [...ranking.ranked, ...ranking.insufficient_data]
  const driver = (id: string) => report?.shortlist.find((s) => s.pathway_id === id)?.main_drivers[0]
  return (
    <div>
      <div className="legend" aria-hidden>
        <span className="key"><span className="swatch-dot" />Attractiveness, ranked</span>
        <span className="key"><span className="swatch-ring" />Attractiveness, not ranked (too little data)</span>
        <span className="key"><span className="swatch-range" />Range if every unassessed criterion scored 1 to 5</span>
      </div>
      <div className="dotplot" role="img" aria-label="Attractiveness of each pathway on a 1 to 5 scale; values are in the table below">
        <div className="scale-axis">
          <span /><div className="ticks">{[1, 2, 3, 4, 5].map((t) => <span key={t} style={{ left: x(t) }}>{t}</span>)}</div><span>Data completeness</span>
        </div>
        {all.map((o) => (
          <div className="row" key={o.pathway_id}>
            <div className="name">
              {o.name}
              <div><StatusBadge status={o.status} label={o.rank ? `Ranked #${o.rank}` : 'Insufficient data'} /></div>
            </div>
            <div className="scale">
              {[1, 2, 3, 4, 5].map((t) => <span key={t} className="grid" style={{ left: x(t) }} />)}
              <span className="range" style={{ left: x(o.attractiveness_range[0]), width: `calc(${x(o.attractiveness_range[1])} - ${x(o.attractiveness_range[0])})` }}
                title={`Possible range ${num(o.attractiveness_range[0])}–${num(o.attractiveness_range[1])}`} />
              {o.attractiveness !== null && (
                <span className={`point${o.status === 'ranked' ? '' : ' provisional'}`} style={{ left: x(o.attractiveness) }} tabIndex={0}
                  title={`${o.name}: attractiveness ${num(o.attractiveness)} of 5 (${pct(o.completeness.assessed_weight)} of the weight assessed)`} />
              )}
            </div>
            <Meter value={o.completeness.assessed_weight} label="Assessed" detail={pct(o.completeness.assessed_weight)} />
          </div>
        ))}
      </div>
      <p className="hint" style={{ marginTop: 8 }}>
        Pathways are ranked only when criteria carrying at least {pct(ranking.min_completeness)} of the weight were assessed.
        A hollow dot is not a low score: it means the evidence or inputs to score the remaining criteria are missing.
      </p>

      <h3>Comparison table</h3>
      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>Pathway</th><th>Status</th><th className="num">Attractiveness</th><th className="num">Possible range</th>
              <th className="num">Completeness</th><th>Evidence cited</th><th>Not assessed</th></tr>
          </thead>
          <tbody>
            {all.map((o) => (
              <tr key={o.pathway_id} title={driver(o.pathway_id)}>
                <td style={{ minWidth: 180 }}>{o.name}</td>
                <td><StatusBadge status={o.status} label={o.rank ? `#${o.rank}` : 'Insufficient data'} /></td>
                <td className="num">{num(o.attractiveness)}</td>
                <td className="num">{num(o.attractiveness_range[0])}–{num(o.attractiveness_range[1])}</td>
                <td className="num">{pct(o.completeness.assessed_weight)}</td>
                <td className="small">{(['high', 'moderate', 'low', 'unverified'] as const)
                  .filter((q) => o.evidence.by_quality[q] > 0).map((q) => `${o.evidence.by_quality[q]} ${q}`).join(' · ') || 'none'}</td>
                <td className="small">{o.completeness.not_assessed.map(humanize).join(', ') || '–'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
