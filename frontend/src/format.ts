// Display helpers. Formatting only: every number shown comes from the API.

export function num(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '–'
  if (Math.abs(value) >= 1000) return value.toLocaleString('en-US', { maximumFractionDigits: 0 })
  return value.toLocaleString('en-US', { maximumFractionDigits: digits })
}

export function pct(fraction: number | null | undefined, digits = 0): string {
  if (fraction === null || fraction === undefined) return '–'
  return `${(fraction * 100).toFixed(digits)}%`
}

export function humanize(id: string): string {
  const labels: Record<string, string> = {
    lignin_pct: 'Lignin content', ash_pct: 'Ash', sulfur_pct: 'Sulfur', carbohydrates_pct: 'Carbohydrates',
    mw_g_per_mol: 'Molecular weight (Mw)', phenolic_oh_mmol_per_g: 'Phenolic OH', sodium_pct: 'Sodium',
    fictional_assumption: 'fictional assumption', analyst_assumption: 'your assumption',
    not_available: 'not available', fictional_demo: 'fictional demo', usable_feedstock: 'usable feedstock',
    insufficient_data: 'insufficient data',
  }
  const leaf = id.split('.').pop() ?? id
  return labels[id] ?? labels[leaf] ?? id.replace(/_/g, ' ')
}

export function time(iso: string | null | undefined): string {
  if (!iso) return '–'
  // A bare date (2026-10-24) has no time zone: show it as that calendar day, not converted from UTC midnight.
  if (/^\d{4}-\d{2}-\d{2}$/.test(iso)) return new Date(`${iso}T00:00:00Z`).toLocaleDateString('en-US', { dateStyle: 'medium', timeZone: 'UTC' })
  return new Date(iso).toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' })
}

/** Read a value at a dotted path such as "composition.ash_pct". */
export function getIn(obj: unknown, path: string): unknown {
  return path.split('.').reduce<unknown>((o, k) => (o == null ? undefined : (o as Record<string, unknown>)[k]), obj)
}

/** Set a value at a dotted path such as "composition.ash_pct.value", returning a new object. */
export function setIn<T>(obj: T, path: string, value: unknown): T {
  const [head, ...rest] = path.split('.')
  const source = (obj ?? {}) as Record<string, unknown>
  const copy: Record<string, unknown> = Array.isArray(source) ? ([...source] as unknown as Record<string, unknown>) : { ...source }
  copy[head] = rest.length ? setIn(source[head], rest.join('.'), value) : value
  return copy as T
}
