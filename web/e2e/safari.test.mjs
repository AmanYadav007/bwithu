// iPhone Safari check with Playwright WebKit (install once: npx playwright@1.48.2 install webkit).
// UA=... overrides the iOS version (the default iPhone 13 profile reports iOS 15). Playwright WebKit's
// fake microphone is slow or sometimes hangs, so a "face NOT visible" run can be a test artifact.
import { webkit, devices } from 'playwright-core';
const t0 = Date.now(); const ts = () => ((Date.now() - t0) / 1000).toFixed(2);
const browser = await webkit.launch({ headless: true });
const ctx = await browser.newContext({ ...devices['iPhone 13'], userAgent: process.env.UA || devices['iPhone 13'].userAgent });
const page = await ctx.newPage();
page.on('console', m => console.log(ts(), `[${m.type()}]`, m.text().slice(0, 160)));
page.on('pageerror', e => console.log(ts(), '[pageerror]', e.message));
page.on('websocket', ws => { console.log(ts(), 'WS', ws.url().split('?')[0]); ws.on('framereceived', f => { if (typeof f.payload === 'string' && /client_playback.*stream_begin|stream_begin.*client_playback/.test(f.payload)) console.log(ts(), 'avatar speaks'); }); });
await page.goto(process.argv[2] || 'http://127.0.0.1:8282/', { waitUntil: 'networkidle' });
await page.evaluate(() => localStorage.setItem('bwithu.companion', JSON.stringify({ name: 'Nova', userName: 'Aman', avatar: 'james', vibe: 'warm', voice: 'Tina' })));
await page.reload({ waitUntil: 'networkidle' });
await page.getByRole('button', { name: /Start call/ }).click(); console.log(ts(), 'tapped Start call');
try { await page.waitForSelector('.stage.visible', { timeout: 40000 }); console.log(ts(), 'face visible'); } catch { console.log(ts(), 'face NOT visible'); }
await page.waitForTimeout(8000);
console.log(ts(), 'status text:', (await page.locator('.name-tag, .cover-body').first().innerText().catch(() => '')).replace(/\s+/g, ' '));
await page.screenshot({ path: new URL('last-safari.png', import.meta.url).pathname });
await browser.close();
