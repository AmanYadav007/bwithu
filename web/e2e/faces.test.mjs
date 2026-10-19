// Every face in the setup list loads in a real call and greets; saves a screenshot of each.
// Usage: node e2e/faces.test.mjs [outDir] [url]
// Prereqs: server running, `npm run build`, `e2e/make-fixtures.sh`.
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright-core'

const dir = path.dirname(fileURLToPath(import.meta.url))
const outDir = process.argv[2] || dir
const url = process.argv[3] || 'http://127.0.0.1:8282/'
const ids = [...readFileSync(path.join(dir, '..', 'src', 'config', 'companion.ts'), 'utf8').matchAll(/\{ id: '([^']+)', label: '[^']+', preview/g)].map((m) => m[1])

const browser = await chromium.launch({
  channel: 'chrome',
  headless: true,
  args: [
    '--use-fake-ui-for-media-stream',
    '--use-fake-device-for-media-stream',
    `--use-file-for-fake-audio-capture=${path.join(dir, 'fixtures', 'silence.wav')}`,
    '--autoplay-policy=no-user-gesture-required',
    '--use-angle=metal',
  ],
})
let failed = 0
for (const id of ids) {
  const page = await (await browser.newContext({ viewport: { width: 430, height: 900 }, permissions: ['microphone'] })).newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  let spoke = 0
  page.on('websocket', (ws) =>
    ws.on('framereceived', (f) => {
      if (typeof f.payload === 'string' && f.payload.includes('client_playback') && f.payload.includes('stream_begin')) spoke ||= Date.now()
    })
  )
  await page.goto(url, { waitUntil: 'networkidle' })
  await page.evaluate((avatar) =>
    localStorage.setItem('bwithu.companion', JSON.stringify({ name: 'Nova', userName: 'Tester', avatar, vibe: 'warm', voice: 'ava' })),
    id
  )
  await page.reload({ waitUntil: 'networkidle' })
  const t0 = Date.now()
  await page.getByRole('button', { name: /Start call/ }).click()
  try {
    await page.waitForSelector('.stage.visible', { timeout: 30000 })
    const faceMs = Date.now() - t0
    await page.waitForFunction(() => document.querySelector('.caption'), null, { timeout: 20000 }).catch(() => {})
    await page.waitForTimeout(1500)
    await page.locator('.frame').screenshot({ path: path.join(outDir, `face-${id}.png`) })
    const ok = spoke > 0 && errors.length === 0
    if (!ok) failed++
    console.log(`${ok ? 'OK  ' : 'FAIL'} ${id.padEnd(10)} face ${faceMs} ms, greeting ${spoke ? 'spoken' : 'MISSING'}${errors.length ? ', errors: ' + errors.join(' | ') : ''}`)
  } catch (e) {
    failed++
    console.log(`FAIL ${id.padEnd(10)} ${e.message.split('\n')[0]}${errors.length ? ', errors: ' + errors.join(' | ') : ''}`)
  }
  await page.getByRole('button', { name: 'End call' }).click().catch(() => {})
  await page.context().close()
}
await browser.close()
console.log(failed ? `${failed} face(s) failed` : `all ${ids.length} faces OK`)
process.exit(failed ? 1 : 0)
