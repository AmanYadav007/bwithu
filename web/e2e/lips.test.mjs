// Captures the mouth area while the companion greets, to check lips move with the voice.
import { chromium } from 'playwright-core'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
const dir = path.dirname(fileURLToPath(import.meta.url))
const browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', `--use-file-for-fake-audio-capture=${path.join(dir, 'fixtures/silence.wav')}`, '--use-angle=metal', '--autoplay-policy=no-user-gesture-required'] })
const page = await (await browser.newContext({ viewport: { width: 430, height: 900 }, deviceScaleFactor: 2, permissions: ['microphone'] })).newPage()
await page.goto(process.argv[2] || 'http://127.0.0.1:8282/', { waitUntil: 'networkidle' })
await page.evaluate(() => localStorage.setItem('bwithu.companion', JSON.stringify({ name: 'Nova', userName: 'Aman', avatar: 'james', vibe: 'warm', voice: 'Tina' })))
await page.reload({ waitUntil: 'networkidle' })
await page.getByRole('button', { name: /Start call/ }).click()
await page.waitForSelector('.frame.speaking', { timeout: 20000 })
const box = await page.locator('.stage').boundingBox()
const mouth = { x: box.x + box.width * 0.35, y: box.y + box.height * 0.42, width: box.width * 0.3, height: box.height * 0.12 }
for (let i = 0; i < 8; i++) { await page.screenshot({ path: path.join(dir, `lips-${i}.png`), clip: mouth }); await page.waitForTimeout(120) }
await browser.close()
