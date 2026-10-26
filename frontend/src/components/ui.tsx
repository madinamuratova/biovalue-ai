import { createContext, useContext, type ReactNode } from 'react'
import type { Quality } from '../types.ts'
import { humanize } from '../format.ts'

/** Clicking an evidence reference anywhere opens it in the Evidence explorer. */
export const EvidenceContext = createContext<(ref: string) => void>(() => {})

export function Section({ id, number, title, intro, children, stale }: {
  id: string; number: number; title: string; intro?: ReactNode; children: ReactNode; stale?: boolean
}) {
  return (
    <section id={id} className="section" aria-labelledby={`${id}-title`}>
      <div className="section-head">
        <span className="num">{number}</span>
        <h2 id={`${id}-title`}>{title}</h2>
      </div>
      {intro && <p className="section-intro">{intro}</p>}
      <div className={stale ? 'stale' : undefined}>{children}</div>
    </section>
  )
}

type Tone = 'good' | 'warning' | 'serious' | 'critical' | 'neutral' | 'accent'

const STATUS: Record<string, [Tone, string]> = {
  ok: ['good', 'Completed'], complete: ['good', 'Complete'], partial: ['warning', 'Partial'],
  failed: ['critical', 'Failed'], error: ['critical', 'Error'], skipped: ['neutral', 'Skipped'],
  running: ['accent', 'Running'], pending: ['neutral', 'Waiting'],
  ranked: ['good', 'Ranked'], insufficient_data: ['warning', 'Insufficient data'],
  rejected: ['warning', 'Rejected'], retry_requested: ['warning', 'Retry requested'], fixed_by_code: ['serious', 'Fixed by code'],
}

const TONES: Tone[] = ['good', 'warning', 'serious', 'critical', 'neutral', 'accent']

/** A status always shows a label next to its colored dot, never color alone. `status` is a known state (ok,
 * failed, ranked, ...) or a tone name with an explicit label. */
export function StatusBadge({ status, label }: { status: string; label?: string }) {
  const [tone, text] = STATUS[status] ?? (TONES.includes(status as Tone) ? [status as Tone, status] : ['neutral', humanize(status)])
  return (
    <span className={`badge ${tone}`}>
      {status === 'running' ? <span className="spinner" aria-hidden /> : <span className="dot" aria-hidden />}
      {label ?? text}
    </span>
  )
}

const QUALITY_TONE: Record<Quality, Tone> = { high: 'good', moderate: 'accent', low: 'warning', unverified: 'critical' }

export function QualityBadge({ quality }: { quality: Quality }) {
  return <StatusBadge status={QUALITY_TONE[quality]} label={`${quality} quality`} />
}

export function EvidenceRefs({ refs }: { refs: string[] }) {
  const open = useContext(EvidenceContext)
  if (!refs.length) return null
  return (
    <span>
      {refs.map((ref) =>
        ref.startsWith('feedstock:') ? (
          <span key={ref} className="chip plain" title="A field of the feedstock profile">{ref}</span>
        ) : (
          <button key={ref} type="button" className="chip" onClick={() => open(ref)} title="Open in the Evidence explorer">{ref}</button>
        ),
      )}
    </span>
  )
}

export function Pips({ score }: { score: number | null }) {
  if (score === null) return <span className="muted small">not assessed</span>
  return (
    <span className="pips" role="img" aria-label={`${score} of 5`}>
      {[1, 2, 3, 4, 5].map((i) => <i key={i} className={i <= score ? 'on' : undefined} />)}
    </span>
  )
}

export function Meter({ value, label, detail }: { value: number; label: string; detail: string }) {
  return (
    <div>
      <div className="meter-label"><span>{label}</span><span>{detail}</span></div>
      <div className="meter" role="meter" aria-valuemin={0} aria-valuemax={1} aria-valuenow={value} aria-label={label}>
        <div style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }} />
      </div>
    </div>
  )
}

export function Callout({ tone = 'info', title, children }: { tone?: 'info' | 'warning' | 'error' | 'neutral'; title?: string; children: ReactNode }) {
  return (
    <div className={`callout ${tone === 'neutral' ? '' : tone}`} role={tone === 'error' ? 'alert' : undefined}>
      {title && <strong>{title}</strong>}
      {children}
    </div>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="empty">{children}</p>
}

export function Tabs<T extends string>({ items, value, onChange }: { items: { id: T; label: string }[]; value: T; onChange: (id: T) => void }) {
  return (
    <div className="tabs" role="tablist">
      {items.map((item) => (
        <button key={item.id} type="button" role="tab" className="tab" aria-selected={item.id === value} onClick={() => onChange(item.id)}>
          {item.label}
        </button>
      ))}
    </div>
  )
}
