import { useEffect, useMemo, useRef, useState } from 'react'
import type { EvidenceLibrary, Quality } from '../types.ts'
import { humanize, time } from '../format.ts'
import { Empty, QualityBadge } from './ui.tsx'

export function EvidenceExplorer({ library, cited, focus }: {
  library: EvidenceLibrary
  cited: Set<string>
  focus: { ref: string; nonce: number } | null
}) {
  const [pathway, setPathway] = useState('all')
  const [quality, setQuality] = useState<'all' | Quality>('all')
  const [onlyCited, setOnlyCited] = useState(false)
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState(library.records[0]?.id ?? '')
  const [flash, setFlash] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!focus) return
    const id = focus.ref.split('#')[0]
    setPathway('all'); setQuality('all'); setOnlyCited(false); setQuery('')
    setSelected(id)
    setFlash(true)
    const t = setTimeout(() => setFlash(false), 1200)
    return () => clearTimeout(t)
  }, [focus])

  // Keep the selected record visible in the list (without scrolling the page).
  useEffect(() => {
    const list = listRef.current
    const item = list?.querySelector<HTMLElement>('[aria-selected="true"]')
    if (list && item) list.scrollTop = item.offsetTop - list.offsetTop - 8
  }, [selected, focus])

  const records = useMemo(() => {
    const q = query.trim().toLowerCase()
    return library.records.filter((r) =>
      (pathway === 'all' || r.pathway === pathway) && (quality === 'all' || r.quality === quality) && (!onlyCited || cited.has(r.id)) &&
      (!q || [r.id, r.title, r.publisher, ...r.claims.map((c) => c.text)].join(' ').toLowerCase().includes(q)))
  }, [library, pathway, quality, onlyCited, query, cited])

  const record = library.records.find((r) => r.id === selected)
  const focusRef = focus?.ref.startsWith(`${selected}#`) ? focus.ref : null
  const names = Object.fromEntries(library.pathways.map((p) => [p.id, p.name]))

  return (
    <div>
      <div className="filters">
        <input type="search" placeholder="Search titles, publishers, claims" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search evidence" />
        <select value={pathway} onChange={(e) => setPathway(e.target.value)} aria-label="Pathway">
          <option value="all">All pathways</option>
          {library.pathways.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <select value={quality} onChange={(e) => setQuality(e.target.value as 'all' | Quality)} aria-label="Quality">
          <option value="all">Any quality</option>
          {(['high', 'moderate', 'low', 'unverified'] as Quality[]).map((q) => <option key={q} value={q}>{q}</option>)}
        </select>
        <label className="small" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <input type="checkbox" checked={onlyCited} onChange={(e) => setOnlyCited(e.target.checked)} /> Cited in this assessment
        </label>
      </div>
      <div className="explorer">
        <div className="record-list" role="listbox" aria-label="Evidence records" ref={listRef}>
          {records.length === 0 && <Empty>No records match these filters.</Empty>}
          {records.map((r) => (
            <button key={r.id} type="button" role="option" className="record-item" aria-selected={r.id === selected} onClick={() => setSelected(r.id)}>
              <div className="id">{r.id} · {names[r.pathway]}</div>
              <div className="title">{r.title}</div>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                <QualityBadge quality={r.quality} />
                {cited.has(r.id) && <span className="badge accent">cited</span>}
              </div>
            </button>
          ))}
        </div>
        <div className={`record-detail${flash ? ' flash' : ''}`}>
          {!record ? <Empty>Select a record.</Empty> : (
            <>
              <div className="small muted">{record.id} · {names[record.pathway]} · {humanize(record.source_type)}</div>
              <h3 style={{ margin: '4px 0 6px' }}>{record.title}</h3>
              <p className="small ink-2">{record.authors ? `${record.authors} · ` : ''}{record.publisher}{record.published ? ` · ${record.published}` : ''}</p>
              <div style={{ margin: '10px 0', display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
                <QualityBadge quality={record.quality} />
                <span className="small muted">{library.quality_labels[record.quality]}</span>
              </div>
              {record.url && (
                <p className="small">
                  <a href={record.url} target="_blank" rel="noreferrer">Open source</a>
                  <span className="muted"> · link verified {time(record.url_verified_on)}</span>
                </p>
              )}
              <h3>Claims</h3>
              {record.claims.map((c, i) => {
                const ref = `${record.id}#${i + 1}`
                return (
                  <div key={ref} className="claim" style={focusRef === ref ? { background: 'var(--accent-soft)' } : undefined}>
                    <span className="ref">#{i + 1}</span><span className="small">{c.text}</span>
                    <div className="quote">{c.support}</div>
                  </div>
                )
              })}
              {record.technical_requirements.length > 0 && <>
                <h3>Technical requirements</h3>
                {record.technical_requirements.map((q, i) => {
                  const ref = `${record.id}#R${i + 1}`
                  return (
                    <div key={ref} className="claim" style={focusRef === ref ? { background: 'var(--accent-soft)' } : undefined}>
                      <span className="ref">#R{i + 1}</span><strong className="small">{q.parameter}</strong>
                      {q.applies_to && <span className="small muted"> · for {q.applies_to}</span>}
                      <div className="small">{q.requirement}</div>
                      <div className="quote">{q.support}</div>
                    </div>
                  )
                })}
              </>}
              <h3>Limitations</h3>
              <ul className="plain small">{record.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
