// End-to-end call tests in real Chrome (headless, Mac GPU) with a fake microphone.
// Usage: node e2e/call.test.mjs [greet|question|interrupt] [url]
// Prereqs: server running (./run.sh bwithu_dev or bwithu), `npm run build`, `e2e/make-fixtures.sh`.
import { chromium } from 'playwright-core'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const scenario = process.argv[2] || 'question'
const url = process.argv[3] || 'http://127.0.0.1:8282/'
const fixture = { greet: 'silence.wav', question: 'question.wav', interrupt: 'interrupt.wav' }[scenario]
const dir = path.dirname(fileURLToPath(import.meta.url))
const t0 = Date.now()
const ts = () => ((Date.now() - t0) / 1000).toFixed(2).padStart(6)

const browser = await chromium.launch({
  channel: 'chrome',
  headless: true,
  args: [
    '--use-fake-ui-for-media-stream',
    '--use-fake-device-for-media-stream',
    `--use-file-for-fake-audio-capture=${path.join(dir, 'fixtures', fixture)}`,
    '--autoplay-policy=no-user-gesture-required',
    '--use-angle=metal', // swiftshader (software GL) is far too slow for the splat renderer
    // e.g. E2E_CHROME_ARGS='--host-resolver-rules=MAP app.bwithu.live 104.21.21.58' to test a fresh DNS name
    ...(process.env.E2E_CHROME_ARGS ? [process.env.E2E_CHROME_ARGS] : []),
  ],
})
const page = await (await browser.newContext({ viewport: { width: 430, height: 900 }, permissions: ['microphone'] })).newPage()
let vadEnd = 0
const latencies = []
page.on('pageerror', (e) => console.log(ts(), 'PAGE ERROR', e.message))
page.on('websocket', (ws) =>
  ws.on('framereceived', (f) => {
    if (typeof f.payload !== 'string') return
    let m
    try { m = JSON.parse(f.payload) } catch { return }
    const p = m.payload || {}
    if (m.header?.name === 'EchoHumanText') {
      console.log(ts(), 'heard:', p.text)
      setTimeout(async () => {
        const you = await page.locator('.you-caption').innerText().catch(() => '(none)')
        console.log(ts(), 'you-caption:', JSON.stringify(you))
        await page.screenshot({ path: path.join(dir, `last-${scenario}-you.png`) }).catch(() => {})
      }, 800)
    }
    if (m.header?.name !== 'ChatSignal') return
    if (p.stream_type === 'human_audio' && p.type === 'stream_end') vadEnd = Date.now()
    if (p.stream_type === 'client_playback' && p.type === 'stream_begin') {
      console.log(ts(), 'avatar speaks', vadEnd ? `(${Date.now() - vadEnd} ms after user stopped)` : '')
      if (vadEnd) latencies.push(Date.now() - vadEnd)
      vadEnd = 0
    }
    if (p.type === 'stream_cancel' && p.stream_type === 'client_playback') console.log(ts(), 'avatar interrupted')
  })
)
await page.goto(url, { waitUntil: 'networkidle' })
await page.evaluate(() =>
  localStorage.setItem('bwithu.companion', JSON.stringify({ name: 'Nova', userName: 'Tester', avatar: 'james', vibe: 'warm', voice: 'Tina' }))
)
await page.reload({ waitUntil: 'networkidle' })
await page.getByRole('button', { name: /Start call/ }).click()
await page.waitForSelector('.stage.visible', { timeout: 30000 })
console.log(ts(), 'face visible')
await page.waitForTimeout(scenario === 'interrupt' ? 25000 : 15000)
console.log(ts(), 'caption:', await page.locator('.caption').innerText().catch(() => '(none)'))
await page.screenshot({ path: path.join(dir, `last-${scenario}.png`) })
await page.getByRole('button', { name: 'End call' }).click().catch(() => {})
await browser.close()
console.log('latencies_ms', JSON.stringify(latencies))
