// Client-side checks on the form, so obvious mistakes are caught before a request. The server checks everything
// again with the real schemas; its messages use the same field paths, so both show next to the right input.
import type { EconomicAssumptions, Feedstock, FieldError, Quantity, ScenarioInput } from './types.ts'

export const COMPOSITION_FIELDS: { key: string; label: string; unit: string; max?: number }[] = [
  { key: 'lignin_pct', label: 'Lignin content', unit: '% of dry matter', max: 100 },
  { key: 'ash_pct', label: 'Ash', unit: '% of dry matter', max: 100 },
  { key: 'sulfur_pct', label: 'Sulfur', unit: '% of dry matter', max: 100 },
  { key: 'carbohydrates_pct', label: 'Carbohydrates', unit: '% of dry matter', max: 100 },
  { key: 'mw_g_per_mol', label: 'Molecular weight (Mw)', unit: 'g/mol' },
  { key: 'phenolic_oh_mmol_per_g', label: 'Phenolic OH', unit: 'mmol/g' },
  { key: 'other.sodium_pct', label: 'Sodium', unit: '% of dry matter', max: 100 },
]

export const ECONOMIC_FIELDS: { key: 'availability' | 'product_yield' | 'price' | 'cost'; label: string; unit: string; higherIsBetter: boolean; max?: number; hint: string }[] = [
  { key: 'availability', label: 'Availability', unit: '%', higherIsBetter: true, max: 100, hint: 'Share of dry lignin committed to this pathway' },
  { key: 'product_yield', label: 'Product yield', unit: 't/t', higherIsBetter: true, hint: 't product per t usable dry feedstock' },
  { key: 'price', label: 'Product price', unit: 'USD/t', higherIsBetter: true, hint: 'Per tonne of product' },
  { key: 'cost', label: 'Variable processing cost', unit: 'USD/t', higherIsBetter: false, hint: 'Per tonne of product' },
]

const finite = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)

function checkQuantity(path: string, q: Quantity | undefined, opts: { required?: boolean; min?: number; max?: number; maxExclusive?: boolean }): FieldError[] {
  const errors: FieldError[] = []
  if (!q) return errors
  const add = (message: string) => errors.push({ field: path, message })
  if (q.value === null || q.value === undefined) {
    if (opts.required) add('Required.')
    if (finite(q.low) || finite(q.high)) add('Leave the range blank when the value is blank.')
    return errors
  }
  for (const [name, v] of [['value', q.value], ['low', q.low], ['high', q.high]] as const) {
    if (v === null || v === undefined) continue
    if (!finite(v)) add(`The ${name} must be a number.`)
    else if (opts.min !== undefined && v < opts.min) add(`The ${name} can't be below ${opts.min}.`)
    else if (opts.max !== undefined && (opts.maxExclusive ? v >= opts.max : v > opts.max)) add(`The ${name} must be ${opts.maxExclusive ? 'below' : 'at most'} ${opts.max}.`)
  }
  if (finite(q.low) && q.low > q.value) add('Low must not be above the value.')
  if (finite(q.high) && q.high < q.value) add('High must not be below the value.')
  return errors
}

function checkScenario(path: string, s: ScenarioInput | undefined, higherIsBetter: boolean, max?: number): FieldError[] {
  if (!s) return []
  const errors: FieldError[] = []
  const add = (message: string) => errors.push({ field: path, message })
  if (!finite(s.base)) add('Enter a base value: conservative and optimistic values need one.')
  for (const [name, v] of [['base', s.base], ['conservative', s.conservative], ['optimistic', s.optimistic]] as const) {
    if (v === null || v === undefined || Number.isNaN(v)) continue
    if (!finite(v)) add(`The ${name} value must be a number.`)
    else if (v < 0) add(`The ${name} value can't be negative.`)
    else if (max !== undefined && v > max) add(`The ${name} value must be at most ${max}.`)
  }
  const hasC = finite(s.conservative), hasO = finite(s.optimistic)
  if (hasC !== hasO) add('Give both conservative and optimistic, or neither.')
  if (hasC && hasO && finite(s.base)) {
    const [c, b, o] = [s.conservative as number, s.base, s.optimistic as number]
    const ordered = higherIsBetter ? c <= b && b <= o : c >= b && b >= o
    if (!ordered) add(higherIsBetter ? 'Conservative ≤ base ≤ optimistic (higher is better).' : 'Conservative ≥ base ≥ optimistic (lower cost is better).')
  }
  return errors
}

export function validateInputs(feedstock: Feedstock, assumptions: EconomicAssumptions): FieldError[] {
  const errors: FieldError[] = []
  if (!feedstock.name.trim()) errors.push({ field: 'feedstock.name', message: 'Required.' })
  if (!feedstock.feedstock_type.trim()) errors.push({ field: 'feedstock.feedstock_type', message: 'Required.' })
  errors.push(...checkQuantity('feedstock.annual_wet_quantity', feedstock.annual_wet_quantity, { required: true, min: 0 }))
  if (feedstock.annual_wet_quantity.value === 0) errors.push({ field: 'feedstock.annual_wet_quantity', message: 'Must be above zero.' })
  errors.push(...checkQuantity('feedstock.moisture_pct', feedstock.moisture_pct, { required: true, min: 0, max: 100, maxExclusive: true }))
  for (const f of COMPOSITION_FIELDS) {
    const q = f.key.startsWith('other.')
      ? (feedstock.composition.other as Record<string, Quantity> | undefined)?.[f.key.slice(6)]
      : (feedstock.composition[f.key] as Quantity | undefined)
    errors.push(...checkQuantity(`feedstock.composition.${f.key}`, q, { min: 0, max: f.max }))
  }
  for (const [pid, a] of Object.entries(assumptions)) {
    for (const f of ECONOMIC_FIELDS) {
      const s = f.key === 'cost' ? a.variable_costs?.[0]?.rate : a[f.key]
      errors.push(...checkScenario(`economic_assumptions.${pid}.${f.key}`, s, f.higherIsBetter, f.max))
    }
  }
  return errors
}

export function errorsFor(errors: FieldError[], path: string): string[] {
  return errors.filter((e) => e.field === path || e.field.startsWith(`${path}.`)).map((e) => e.message)
}
