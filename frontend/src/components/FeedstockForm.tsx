import type { ChangeEvent } from 'react'
import type { EconomicAssumptions, Feedstock, FieldError, Pathway, Quantity, ScenarioInput } from '../types.ts'
import { COMPOSITION_FIELDS, ECONOMIC_FIELDS, errorsFor } from '../validate.ts'
import { getIn, setIn } from '../format.ts'

const USER_NOTE = 'Entered in the BioValue AI dashboard.'

function parse(e: ChangeEvent<HTMLInputElement>): number | null {
  return e.target.value === '' ? null : Number(e.target.value)
}

function NumberInput({ value, onChange, invalid, label }: { value: number | null | undefined; onChange: (v: number | null) => void; invalid?: boolean; label: string }) {
  return (
    <input type="number" step="any" inputMode="decimal" aria-label={label} className={invalid ? 'invalid' : undefined}
      value={value ?? ''} onChange={(e) => onChange(parse(e))} />
  )
}

function Errors({ messages }: { messages: string[] }) {
  return messages.length ? <span className="field-error" role="alert">{messages.join(' ')}</span> : null
}

export function FeedstockForm({ feedstock, assumptions, pathways, errors, dryMatter, onChange }: {
  feedstock: Feedstock
  assumptions: EconomicAssumptions
  pathways: Pathway[]
  errors: FieldError[]
  dryMatter: string | null
  onChange: (feedstock: Feedstock, assumptions: EconomicAssumptions) => void
}) {
  const set = (path: string, value: unknown) => {
    let next = setIn(feedstock, path, value)
    // Editing a published (literature) figure makes it the user's own estimate: drop its citation, as the server does.
    const figure = path.match(/^(.*)\.(value|low|high|unit)$/)?.[1]
    const q = figure ? (getIn(next, figure) as Quantity | undefined) : undefined
    if (figure && q?.basis === 'literature') next = setIn(setIn(next, `${figure}.basis`, 'estimated'), `${figure}.source`, '')
    onChange(next, assumptions)
  }
  const cite = (q?: Quantity) => (q?.basis === 'literature' && q.source
    ? <span className="chip plain" title="Published value; see Published sources below">{q.source}</span> : null)
  const quantityRow = (path: string, label: string, q: Quantity, unitControl?: React.ReactNode) => {
    const msgs = errorsFor(errors, `feedstock.${path}`)
    return (
      <div className="field">
        <span>{label}</span>
        <div className="inline">
          <NumberInput label={`${label} value`} value={q.value} invalid={msgs.length > 0} onChange={(v) => set(`${path}.value`, v)} />
          <NumberInput label={`${label} low`} value={q.low} invalid={msgs.length > 0} onChange={(v) => set(`${path}.low`, v)} />
          <NumberInput label={`${label} high`} value={q.high} invalid={msgs.length > 0} onChange={(v) => set(`${path}.high`, v)} />
        </div>
        <span className="hint">Value · low · high (expected range over a year){unitControl ? '' : ` · ${q.unit}`} {cite(q)}</span>
        {unitControl}
        <Errors messages={msgs} />
      </div>
    )
  }

  const setScenario = (pid: string, key: string, part: 'base' | 'conservative' | 'optimistic', value: number | null, unit: string) => {
    const current = assumptions[pid] ?? { product: pathways.find((p) => p.id === pid)?.name ?? pid }
    const existing: ScenarioInput | undefined = key === 'cost' ? current.variable_costs?.[0]?.rate : (current as unknown as Record<string, ScenarioInput | undefined>)[key]
    // A new input starts with no base (NaN), never zero: validation asks for it until it is entered.
    let next: ScenarioInput | undefined = { ...(existing ?? { base: NaN, unit }), [part]: value, unit, basis: 'analyst_assumption', note: USER_NOTE } as ScenarioInput
    const empty = (v: number | null | undefined) => v === null || v === undefined || Number.isNaN(v)
    if (part === 'base' && value === null) next = { ...next, base: NaN }
    if (empty(next.base) && empty(next.conservative) && empty(next.optimistic)) next = undefined // all blank: the input is missing
    const updated = { ...current }
    if (key === 'cost') updated.variable_costs = next ? [{ name: 'Variable processing cost', per: 'product', rate: next }] : undefined
    else (updated as unknown as Record<string, ScenarioInput | undefined>)[key] = next
    onChange(feedstock, { ...assumptions, [pid]: updated })
  }

  return (
    <form className="form-grid" onSubmit={(e) => e.preventDefault()} noValidate>
      <fieldset>
        <legend>Stream and data source</legend>
        <label className="field"><span>Name</span>
          <input value={feedstock.name} onChange={(e) => set('name', e.target.value)} className={errorsFor(errors, 'feedstock.name').length ? 'invalid' : undefined} />
          <Errors messages={errorsFor(errors, 'feedstock.name')} />
        </label>
        <label className="field"><span>Feedstock type</span>
          <textarea value={feedstock.feedstock_type} onChange={(e) => set('feedstock_type', e.target.value)} />
          <Errors messages={errorsFor(errors, 'feedstock.feedstock_type')} />
        </label>
        <div className="inline" style={{ gridTemplateColumns: '1fr 1fr', marginTop: 10 }}>
          <label className="field" style={{ marginTop: 0 }}><span>Wood type</span>
            <select value={feedstock.wood_type} onChange={(e) => set('wood_type', e.target.value)}>
              <option value="softwood">Softwood</option><option value="hardwood">Hardwood</option><option value="mixed">Mixed</option>
            </select>
          </label>
          <label className="field" style={{ marginTop: 0 }}><span>Data source</span>
            <select value={feedstock.data_status} onChange={(e) => set('data_status', e.target.value)}>
              <option value="fictional_demo">Fictional demo values</option>
              <option value="measured">Mill measurements</option>
              <option value="mixed">Mixed or estimated</option>
              <option value="literature_reference">Published literature values (cited)</option>
            </select>
          </label>
        </div>
        <p className="hint" style={{ marginTop: 8 }}>Every figure is labelled with this source in the results.</p>
      </fieldset>

      <fieldset>
        <legend>Quantity and moisture</legend>
        {quantityRow('annual_wet_quantity', 'Annual wet quantity', feedstock.annual_wet_quantity,
          <label className="field" style={{ marginTop: 6 }}><span>Unit</span>
            <select value={feedstock.annual_wet_quantity.unit} onChange={(e) => set('annual_wet_quantity.unit', e.target.value)}>
              <option value="t/yr">t/yr</option><option value="kt/yr">kt/yr</option>
            </select>
          </label>)}
        {quantityRow('moisture_pct', 'Moisture (% of wet mass)', feedstock.moisture_pct)}
        <p className="hint" style={{ marginTop: 10 }}>Dry matter is calculated by the server: {dryMatter ?? 'waiting for valid inputs'}.</p>
      </fieldset>

      <fieldset className="span-2">
        <legend>Composition (dry basis)</legend>
        <div className="table-wrap">
          <table className="compact">
            <thead><tr><th>Property</th><th>Value</th><th>Low</th><th>High</th><th>Unit</th><th>Method</th></tr></thead>
            <tbody>
              {COMPOSITION_FIELDS.map((f) => {
                const path = `composition.${f.key}`
                const q = (f.key.startsWith('other.')
                  ? (feedstock.composition.other as Record<string, Quantity>)?.[f.key.slice(6)]
                  : feedstock.composition[f.key]) as Quantity | undefined
                if (!q) return null
                const msgs = errorsFor(errors, `feedstock.${path}`)
                return (
                  <tr key={f.key}>
                    <td>{f.label}<br /><Errors messages={msgs} /></td>
                    <td><NumberInput label={`${f.label} value`} value={q.value} invalid={msgs.length > 0} onChange={(v) => set(`${path}.value`, v)} /></td>
                    <td><NumberInput label={`${f.label} low`} value={q.low} invalid={msgs.length > 0} onChange={(v) => set(`${path}.low`, v)} /></td>
                    <td><NumberInput label={`${f.label} high`} value={q.high} invalid={msgs.length > 0} onChange={(v) => set(`${path}.high`, v)} /></td>
                    <td className="ink-2 small">{f.unit}</td>
                    <td className="small ink-2">{q.value === null ? <span className="badge warning"><span className="dot" />missing</span> : (q.method || '–')} {cite(q)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        <p className="hint" style={{ marginTop: 8 }}>Leave a value blank if it hasn't been measured: it is recorded as missing data, never as zero.</p>
      </fieldset>

      <fieldset>
        <legend>Current use and infrastructure</legend>
        <label className="field"><span>Current use</span>
          <select value={feedstock.current_use.route} onChange={(e) => set('current_use.route', e.target.value)}>
            <option value="recovery_boiler_fuel">Recovery boiler fuel</option>
            <option value="internal_fuel">Internal fuel (boilers, lime kiln)</option>
            <option value="sold_as_fuel">Sold as fuel</option>
            <option value="sold_as_material">Sold as material</option>
            <option value="landfill">Landfill</option>
            <option value="other">Other</option>
          </select>
        </label>
        <label className="field"><span>Description</span>
          <textarea value={feedstock.current_use.description} onChange={(e) => set('current_use.description', e.target.value)} />
        </label>
        <table className="compact" style={{ marginTop: 12 }}>
          <thead><tr><th>Asset</th><th style={{ width: 150 }}>Status</th></tr></thead>
          <tbody>
            {feedstock.infrastructure.map((asset, i) => (
              <tr key={i}>
                <td>{asset.name}</td>
                <td>
                  <select aria-label={`${asset.name} status`} value={asset.status} onChange={(e) => set(`infrastructure.${i}.status`, e.target.value)}>
                    <option value="operating">Operating</option><option value="planned">Planned</option><option value="not_available">Not available</option>
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </fieldset>

      <fieldset>
        <legend>Geographic market</legend>
        <label className="field"><span>Mill location</span>
          <input value={feedstock.geographic_market.mill_location} onChange={(e) => set('geographic_market.mill_location', e.target.value)} />
        </label>
        <label className="field"><span>Target markets (comma-separated)</span>
          <input value={feedstock.geographic_market.target_markets.join(', ')}
            onChange={(e) => set('geographic_market.target_markets', e.target.value.split(',').map((s) => s.trim()).filter(Boolean))} />
        </label>
        <label className="field"><span>Logistics</span>
          <textarea value={feedstock.geographic_market.logistics} onChange={(e) => set('geographic_market.logistics', e.target.value)} />
        </label>
      </fieldset>

      <fieldset className="span-2">
        <legend>Economic assumptions (optional)</legend>
        <p className="hint" style={{ marginBottom: 8 }}>
          No verified source gives a price, yield, or cost for a mill's lignin in these uses, so the demo leaves them blank and the
          economics stop at usable feedstock. Enter your own values to see indicative economics; they are labelled as your assumptions.
        </p>
        {pathways.map((p) => (
          <details key={p.id} style={{ marginTop: 8 }}>
            <summary className="small"><strong>{p.name}</strong>
              <Errors messages={errors.filter((e) => e.field === `economic_assumptions.${p.id}`).map((e) => e.message)} />
            </summary>
            <table className="compact" style={{ marginTop: 6 }}>
              <thead><tr><th>Input</th><th>Conservative</th><th>Base</th><th>Optimistic</th><th>Unit</th></tr></thead>
              <tbody>
                {ECONOMIC_FIELDS.map((f) => {
                  const a = assumptions[p.id]
                  const s: ScenarioInput | undefined = f.key === 'cost' ? a?.variable_costs?.[0]?.rate : a?.[f.key]
                  const msgs = errorsFor(errors, `economic_assumptions.${p.id}.${f.key}`)
                  const cell = (part: 'base' | 'conservative' | 'optimistic') => (
                    <NumberInput label={`${p.name} ${f.label} ${part}`} invalid={msgs.length > 0}
                      value={s ? (Number.isNaN(s[part] as number) ? null : s[part]) : null}
                      onChange={(v) => setScenario(p.id, f.key, part, v, f.unit)} />
                  )
                  return (
                    <tr key={f.key}>
                      <td>{f.label}<div className="hint">{f.hint}{s?.basis === 'fictional_assumption' ? ' · fictional demo value' : ''}</div><Errors messages={msgs} /></td>
                      <td>{cell('conservative')}</td><td>{cell('base')}</td><td>{cell('optimistic')}</td>
                      <td className="ink-2 small">{f.unit}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </details>
        ))}
      </fieldset>
      {feedstock.data_status === 'literature_reference' && (feedstock.sources?.length ?? 0) > 0 && (
        <fieldset className="span-2 sources">
          <legend>Published sources</legend>
          <p className="hint">Each figure tagged with a source key is a published value. The passages below are quoted verbatim and were
            checked against each source. Figures you edit become your own estimates and lose their tag. Blank figures are not published.</p>
          <ul className="plain">
            {feedstock.sources!.map((src) => (
              <li key={src.key}>
                <span className="chip plain">{src.key}</span> {src.citation} <a href={src.url} target="_blank" rel="noreferrer">Open source</a>
                <span className="hint"> · checked {src.verified_on}</span>
                <details><summary className="small">{src.quotes.length} quoted passage(s)</summary>
                  <ul className="small ink-2">{src.quotes.map((q, i) => <li key={i}>“{q}”</li>)}</ul>
                </details>
              </li>
            ))}
          </ul>
        </fieldset>
      )}
    </form>
  )
}
