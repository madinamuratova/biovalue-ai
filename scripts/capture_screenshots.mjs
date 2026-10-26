// Capture real screenshots of the running dashboard, one PNG per section, for the report and slides.
//
// Needs the API (port 8765) and the dashboard (port 5173) running, and Google Chrome installed. It only reads the page:
// it never starts an assessment, so the screenshots show the latest saved run (or, with --run, an earlier saved run:
// the page's request for the latest run is answered with that run from the same API).
//
//   node scripts/capture_screenshots.mjs                       all sections -> output/screenshots/
//   node scripts/capture_screenshots.mjs --prefix injection --run <run id> trace   section 8 of that run -> injection_trace.png
//   node scripts/capture_screenshots.mjs --prefix reference --click "Load literature reference" input profile   after pressing a button

import { spawn } from 'node:child_process'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const OUT = join(ROOT, 'output', 'screenshots')
const CHROME = process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const URL = process.env.DASHBOARD_URL || 'http://localhost:5173/'
const PORT = 9333
const WIDTH = 1280

const args = process.argv.slice(2)
const prefixAt = args.indexOf('--prefix')
const prefix = prefixAt >= 0 ? args.splice(prefixAt, 2)[1] + '_' : ''
const clickAt = args.indexOf('--click')
const CLICK = clickAt >= 0 ? args.splice(clickAt, 2)[1] : null  // press a button (by its text) before capturing
const runAt = args.indexOf('--run')
const RUN_ID = runAt >= 0 ? args.splice(runAt, 2)[1] : null
const API = process.env.API_URL || 'http://127.0.0.1:8765'
const SECTIONS = args.length ? args : ['header', 'input', 'profile', 'comparison', 'ranking', 'commercial', 'actions', 'evidence', 'trace', 'export']

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function main() {
  mkdirSync(OUT, { recursive: true })
  const profile = mkdtempSync(join(tmpdir(), 'biovalue-shots-'))
  const chrome = spawn(CHROME, ['--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`,
    `--window-size=${WIDTH},1000`, '--hide-scrollbars', '--force-device-scale-factor=2', 'about:blank'], { stdio: 'ignore' })
  try {
    let targets
    for (let i = 0; i < 50 && !targets; i++) {
      try { targets = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json() } catch { await sleep(200) }
    }
    const page = targets.find((t) => t.type === 'page')
    const ws = new WebSocket(page.webSocketDebuggerUrl)
    await new Promise((r) => ws.addEventListener('open', r, { once: true }))
    let id = 0
    const pending = new Map()
    ws.addEventListener('message', (e) => {
      const msg = JSON.parse(e.data)
      if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id) }
      if (msg.method === 'Fetch.requestPaused') serveRun(msg.params.requestId)
    })
    const send = (method, params = {}) => new Promise((resolve, reject) => {
      const n = ++id
      pending.set(n, (msg) => (msg.error ? reject(new Error(`${method}: ${msg.error.message}`)) : resolve(msg.result)))
      ws.send(JSON.stringify({ id: n, method, params }))
    })
    const evaluate = async (expression) => (await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })).result.value

    async function serveRun(requestId) {
      const body = await (await fetch(`${API}/api/runs/${encodeURIComponent(RUN_ID)}`)).text()
      await send('Fetch.fulfillRequest', { requestId, responseCode: 200, body: Buffer.from(body).toString('base64'),
        responseHeaders: [{ name: 'Content-Type', value: 'application/json' }] })
    }
    if (RUN_ID) await send('Fetch.enable', { patterns: [{ urlPattern: '*/api/runs/latest*', requestStage: 'Request' }] })
    await send('Page.enable')
    await send('Emulation.setDeviceMetricsOverride', { width: WIDTH, height: 1000, deviceScaleFactor: 2, mobile: false })
    await send('Page.navigate', { url: URL })
    // wait until the latest run has rendered (section 3 shows the opportunity chart or a "no assessment" note)
    for (let i = 0; i < 60; i++) {
      await sleep(500)
      if (await evaluate(`!!document.querySelector('#comparison') && !document.body.innerText.includes('Loading')`)) break
    }
    await sleep(1500)
    if (CLICK) {
      const clicked = await evaluate(`(() => { const b = [...document.querySelectorAll('button')].find((x) => x.textContent.trim() === ${JSON.stringify(CLICK)}); if (!b) return false; b.click(); return true })()`)
      if (!clicked) throw new Error(`no button labelled "${CLICK}"`)
      await sleep(3000) // let the preview of the new inputs come back from the API
    }

    // A spec is a section id, "header", "page" (the first screen), "ledger" (the facts/assumptions/estimates/unknowns
    // panel), "<id>!" (with every <details> opened), or any of these with "@<height>" to keep only the top <height> CSS pixels (saved as <name>_top.png).
    for (const spec of SECTIONS) {
      const [raw, maxHeight] = spec.split('@')
      const open = raw.endsWith('!')  // "trace!" opens every <details> in the section first
      const name = raw.replace(/!$/, '')
      let box
      if (name === 'page') {
        box = { x: 0, y: 0, width: WIDTH, height: 860 }
      } else if (name === 'ledger') {
        box = await evaluate(`(() => { const h = Array.from(document.querySelectorAll('#actions h3')).find((e) => e.textContent.includes('What this assessment rests on'));
          const s = document.querySelector('#actions'); if (!h || !s) return null; const a = h.getBoundingClientRect(), b = s.getBoundingClientRect();
          return { x: b.left + window.scrollX + 24, y: a.top + window.scrollY - 8, width: b.width - 48, height: b.bottom - a.top - 8 } })()`)
      } else {
        const selector = name === 'header' ? 'header' : `#${name}`
        box = await evaluate(`(() => { const el = document.querySelector(${JSON.stringify(selector)}); if (!el) return null;
          if (${JSON.stringify(open)}) el.querySelectorAll('details').forEach((d) => { d.open = true })
          el.scrollIntoView(); const r = el.getBoundingClientRect();
          return { x: r.left + window.scrollX, y: r.top + window.scrollY, width: r.width, height: r.height } })()`)
      }
      if (!box) { console.log(`skipped ${spec}: not on the page`); continue }
      if (maxHeight) box.height = Math.min(box.height, Number(maxHeight))
      const pad = name === 'page' ? 0 : 12
      const clip = { x: Math.max(0, box.x - pad), y: Math.max(0, box.y - pad), width: box.width + 2 * pad, height: box.height + 2 * pad, scale: 1 }
      const shot = await send('Page.captureScreenshot', { format: 'png', clip, captureBeyondViewport: true })
      const file = join(OUT, `${prefix}${name}${open ? '_open' : ''}${maxHeight ? '_top' : ''}.png`)
      writeFileSync(file, Buffer.from(shot.data, 'base64'))
      console.log(`saved ${file} (${Math.round(box.width)} x ${Math.round(box.height)} css px)`)
    }
    ws.close()
  } finally {
    chrome.kill()
    await sleep(300)
    rmSync(profile, { recursive: true, force: true })
  }
}

main().catch((err) => { console.error(err); process.exit(1) })
