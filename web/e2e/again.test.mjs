// Three calls in a row in one page: End call -> Call again must bring the face back each time.
import { chromium } from 'playwright-core'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
const dir = path.dirname(fileURLToPath(import.meta.url))
const url = process.argv[2] || 'http://127.0.0.1:8282/'
const browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--js-flags=--expose-gc', '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', `--use-file-for-fake-audio-capture=${path.join(dir, 'fixtures/silence.wav')}`, '--use-angle=metal', '--autoplay-policy=no-user-gesture-required'] })
const page = await (await browser.newContext({ viewport: { width: 430, height: 900 }, permissions: ['microphone'] })).newPage()
page.on('pageerror', (e) => console.log('PAGE ERROR', e.message))
page.on('console', (m) => m.text().startsWith('[bwithu]') && console.log('  ', m.text()))
await page.goto(url, { waitUntil: 'networkidle' })
await page.evaluate(() => localStorage.setItem('bwithu.companion', JSON.stringify({ name: 'Nova', userName: '', avatar: 'james', vibe: 'warm', voice: 'Tina' })))
await page.reload({ waitUntil: 'networkidle' })
for (let i = 1; i <= Number(process.argv[3] || 3); i++) {
  const t = Date.now()
  await page.getByRole('button', { name: i === 1 ? /Start call/ : /Call again/ }).click()
  await page.waitForSelector('.stage.visible', { timeout: 30000 })
  const canvases = await page.locator('.stage canvas').count()
  await page.waitForTimeout(4000)
  const caption = await page.locator('.caption').innerText().catch(() => '')
  console.log(`call ${i}: done in ${Date.now() - t} ms (incl. 4 s listen), canvases=${canvases}, greeting="${caption.slice(0, 60)}"`)
  await page.getByRole('button', { name: 'End call' }).click()
  await page.waitForSelector('.cover-body h2')
  await page.waitForTimeout(500)
  const mb = await page.evaluate(() => { globalThis.gc?.(); return Math.round(performance.memory.usedJSHeapSize / 1e6) })
  console.log(`  heap after call ${i} (post-GC): ${mb} MB`)
}
const heap = await page.evaluate(() => performance.memory ? Math.round(performance.memory.usedJSHeapSize / 1e6) : -1)
console.log('js heap MB after 3 calls:', heap)
await browser.close()
