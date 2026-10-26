import type { RunResponse } from '../types.ts'
import { num, time } from '../format.ts'
import { Callout, StatusBadge } from './ui.tsx'

export function ExecutionTrace({ run, titles }: { run: RunResponse; titles: Record<string, string> }) {
  const t = run.trace
  const total = t.agents.reduce((s, a) => ({ in: s.in + a.usage.input_tokens, cached: s.cached + a.usage.cache_read_tokens, out: s.out + a.usage.output_tokens, req: s.req + a.usage.requests, tools: s.tools + a.tool_calls.length }), { in: 0, cached: 0, out: 0, req: 0, tools: 0 })
  const security = t.security_events ?? []
  const cost = run.result?.cost
  return (
    <div>
      <p className="small ink-2" style={{ marginBottom: 12 }}>
        Run <code>{t.run_id}</code> · model {t.model}{t.config ? ` · ${t.config} configuration` : ''}{t.token_budget ? ` · budget ${num(t.token_budget)} tokens` : ''} · started {time(t.started_at)}{t.finished_at ? ` · finished ${time(t.finished_at)}` : ''} · <StatusBadge status={run.status} />
      </p>
      {run.error && <Callout tone="error" title="The run stopped with an error">{run.error}</Callout>}
      {security.length > 0 && (
        <Callout tone="warning" title={`${security.length} piece(s) of text read like instructions to the AI and were replaced before the agents saw them`}>
          <ul className="plain small">{security.map((e, i) => <li key={i}>{e.source}: <code>{e.field}</code> (matched: {e.matched.join('; ')})</li>)}</ul>
        </Callout>
      )}
      <div className="table-wrap">
        <table className="trace-table">
          <thead>
            <tr><th>#</th><th>Agent</th><th>Status</th><th className="num">Attempts</th><th className="num">Seconds</th><th className="num">Requests</th>
              <th className="num">Input tokens</th><th className="num">Cached</th><th className="num">Output tokens</th><th className="num">Tool calls</th><th>Guards</th></tr>
          </thead>
          <tbody>
            {t.agents.map((a) => (
              <tr key={a.agent}>
                <td className="num">{a.order}</td>
                <td>{titles[a.agent] ?? a.agent}</td>
                <td><StatusBadge status={a.status} /></td>
                <td className="num">{a.attempts || '–'}</td>
                <td className="num">{num(a.seconds, 1)}</td>
                <td className="num">{a.usage.requests || '–'}</td>
                <td className="num">{a.usage.input_tokens ? num(a.usage.input_tokens) : '–'}</td>
                <td className="num">{a.usage.input_tokens ? num(a.usage.cache_read_tokens) : '–'}</td>
                <td className="num">{a.usage.output_tokens ? num(a.usage.output_tokens) : '–'}</td>
                <td className="num">{a.tool_calls.length || '–'}</td>
                <td className="small">{a.guard_events.length ? a.guard_events.map((g, i) => <StatusBadge key={i} status={g.action} />) : '–'}</td>
              </tr>
            ))}
            <tr>
              <td /><td><strong>Total</strong></td><td /><td /><td /><td className="num">{total.req}</td>
              <td className="num">{num(total.in)}</td><td className="num">{num(total.cached)}</td><td className="num">{num(total.out)}</td><td className="num">{total.tools}</td><td />
            </tr>
          </tbody>
        </table>
      </div>
      <p className="hint" style={{ marginTop: 6 }}>
        Token counts are the provider's usage metadata. Seconds are each agent's wall-clock latency.
        {cost && (cost.usd !== null
          ? <> Cost: {cost.usd} USD ({cost.note})</>
          : <> Cost: {cost.note}{cost.proxy_usd != null && <> Proxy estimate: {cost.proxy_usd} USD ({cost.proxy_note})</>}</>)}
      </p>

      <h3>Details</h3>
      {t.agents.map((a) => (
        <details key={a.agent} style={{ borderTop: '1px solid var(--line)', padding: '8px 0' }} open={a.status === 'failed' || a.status === 'running'}>
          <summary className="small"><strong>{a.order}. {titles[a.agent] ?? a.agent}</strong> · {a.tool_calls.length} tool call(s)
            {a.errors.length ? ` · ${a.errors.length} error(s)` : ''}{a.skipped_reason ? ` · ${a.skipped_reason}` : ''}</summary>
          {a.errors.map((e, i) => <Callout key={i} tone="error">{e}</Callout>)}
          {a.guard_events.map((g, i) => (
            <div key={i} className="callout warning" style={{ marginTop: 8 }}>
              <strong>Guard: {g.action === 'retry_requested' ? 'answer sent back to the agent' : 'answer repaired by code'}</strong>
              <ul className="plain small">{g.problems.map((p, i) => <li key={i}>{p}</li>)}</ul>
            </div>
          ))}
          {a.tool_calls.length > 0 && (
            <table className="compact" style={{ marginTop: 8 }}>
              <thead><tr><th>Tool</th><th>Arguments</th><th>Status</th><th>Result</th></tr></thead>
              <tbody>
                {a.tool_calls.map((c, i) => (
                  <tr key={i}>
                    <td className="small"><code>{c.tool}</code></td>
                    <td className="small ink-2" style={{ maxWidth: 260, wordBreak: 'break-word' }}>{Object.keys(c.arguments).length ? JSON.stringify(c.arguments) : '–'}</td>
                    <td><StatusBadge status={c.status === 'ok' ? 'good' : c.status} label={c.status} /></td>
                    <td className="small ink-2" style={{ maxWidth: 420, wordBreak: 'break-word' }}>{c.result}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </details>
      ))}
    </div>
  )
}
