# BwithU

A face-to-face AI companion in the browser. The user picks a face, names it, and talks; it answers with a
realistic 3D head that lip-syncs in real time.

## How it works

```
browser mic ──WebSocket──► server: Silero VAD ─► Groq Whisper (speech to text; local SenseVoice fallback)
                                   ─► OpenAI-compatible LLM (Groq) ─► Edge TTS (voice)
                                   ─► LAM audio2expression (52 face blendshapes / frame)
browser ◄──WebSocket── audio + face motion ── 3D Gaussian head rendered on the user's GPU
```

- **No video is streamed** and the server needs **no GPU**: the face is drawn in the browser from tiny
  motion frames. A single CPU VM should serve several calls at once (see the capacity numbers below).
- **No WebRTC/TURN**: plain WebSockets work through any network or proxy.
- Built on [OpenAvatarChat](https://github.com/HumanAIGC-Engineering/OpenAvatarChat) (Apache-2.0) and
  [LAM](https://github.com/aigc3d/LAM), trimmed to what we use.

| Path | What |
| --- | --- |
| `server/` | Python call server (trimmed fork of OpenAvatarChat). Our code is in `src/bwithu/` (persona, call gate, feedback) |
| `server/config/bwithu.yaml` | The pipeline: Silero VAD, Groq Whisper, LLM, Edge TTS, LAM |
| `web/` | Vue app: setup screen (face, name, vibe, voice) and call screen |
| `avatars-src/` | Source portraits and the Colab notebook that turns them into faces (see its README) |
| `deploy/container/` | One container with the Cloudflare tunnel, deployed to the Oracle VM by `deploy.sh` |

## Run locally (Mac)

```bash
# once
cd server && uv venv --python 3.11 .venv && VIRTUAL_ENV=.venv uv pip install \
  --index-url https://download.pytorch.org/whl/cpu torch==2.8.0 torchaudio==2.8.0 torchvision==0.23.0 \
  && VIRTUAL_ENV=.venv uv pip install -r requirements-dev.txt && PYTHON=.venv/bin/python scripts/fetch_models.sh
cd ../web && npm install && npx vite build

# every time
cd server && ./run.sh            # needs LLM_API_URL / LLM_MODEL / LLM_API_KEY in ../.env (see .env.example)
open http://127.0.0.1:8282
```

For UI work, `cd web && npm run dev` serves on :5173 and proxies to the server.

## Languages and speed

The user picks English or हिंदी · Hinglish on the setup screen (sent as `lang`):

- **Hearing:** in Hindi calls every turn is transcribed as Hindi with whisper-large-v3. Real Indian-accented Hindi
  is mostly auto-detected as English and written as an English translation, and turbo garbles English when told
  "Hindi". In English calls Whisper (turbo) detects the language itself. Very short words ("हाँ") that come back as
  another language, and Hindi heard as Urdu, are transcribed again in the language the user has been speaking. The
  companion's and user's names are passed as a hint.
- **Replying:** English turns go to `model_name` (qwen3.8-27b, ~140 ms to the first word). Hindi turns go to
  `hindi_model_name` (gpt-oss-20b), because qwen's Hindi is often ungrammatical. The persona asks for casual spoken
  Hindi in Devanagari, in the companion's gender (taken from the chosen voice).
- **Speaking:** a reply with Devanagari switches to the Hindi voice of the same gender (Swara or Madhur). The
  English voices can't read Devanagari: Neerja and Prabhat return no audio at all.

**Pauses:** Edge pads every chunk with up to 1.2 s of silence between sentences; that is trimmed, and a gap set by
the punctuation (0.18 s after a comma, 0.38 s after a sentence, 0.45 s after a question, ±15 %) is inserted. While
the user is still talking (they paused, the turn ended, they went on), the server keeps listening even after the
reply starts, and the two turns are merged.

Edge TTS is the slowest step: it usually starts in 0.6–0.9 s, but now and then stalls for 2–7 s. The TTS handler
speaks the reply sentence by sentence, all sentences requested at once. The first sentence streams, sent twice at
once with a third request after 1 s, and the first to deliver is used. Later sentences are re-requested if not done
after 1 s and 2 s. An interrupt drops everything not yet played. Each stage logs its time (`ASR … ms`,
`LLM first token after …`, `TTS first audio after …`).

## Browser support

Chrome, Edge and Safari (macOS and iOS 15+) on desktop and mobile. Two things make Safari work:

- The server sends cross-origin isolation headers (COOP/COEP), because the avatar renderer's sort worker
  uses shared WebAssembly memory. Load nothing cross-origin (fonts are self-hosted in `web/public/fonts`).
- `web/scripts/patch-lam-renderer.mjs` (postinstall) fixes a LinkError on iOS < 16.4 in
  `gaussian-splat-renderer-for-lam`.

Tests: `cd web && e2e/make-fixtures.sh` once, then `npm run e2e -- greet|question|interrupt|hindi`,
`node e2e/again.test.mjs`, `node e2e/safari.test.mjs`.

## Limits and controls (env vars, no redeploy needed)

| Var | Default | Meaning |
| --- | --- | --- |
| `BWITHU_MAX_CALLS` | 10 | Simultaneous calls; extra callers see "try again in a minute" |
| `BWITHU_DAILY_SECONDS` | 600 | Free talk time per person per day (per browser id) |
| `BWITHU_IP_MULTIPLIER` | 10 | One IP may use this many people's worth of time (mobile carriers share IPs) |
| `BWITHU_MAX_CALL_SECONDS` | 600 | Hard cap per call |
| `BWITHU_PAUSED=1` or file `server/PAUSED` | off | Kill switch: refuse new calls |
| `BWITHU_ADMIN_TOKEN` | unset | Enables `GET /bwithu/stats?token=…` (active calls, minutes today) |

## Capacity

The only heavy server work is LAM lip-sync (wav2vec2 on CPU). Measured on an Apple M2 (Oct 18, 2026):
82 ms of CPU per 1 s of avatar speech on one core; 8 parallel speakers ran at 20× real time. Cloud vCPUs
are slower, but a 4-vCPU VM should still handle 10+ simultaneous calls; confirm with a load test on
the real VM before raising `BWITHU_MAX_CALLS`.

## Deploy

`deploy/container/deploy.sh ubuntu@<vm-ip>` builds the web app, copies the committed `server/` files, the built
`web/dist` and a trimmed `.env` to the VM, and runs `docker compose up -d --build` there. The container runs the
server under a freeze watchdog plus the Cloudflare tunnel (`CLOUDFLARE_TUNNEL_TOKEN`) that serves
app.bwithu.live, so the VM needs no open ports. Commit server changes first; `deploy.sh` refuses otherwise.

## Privacy

User audio is sent to Groq (speech to text and the reply) and the reply text to Microsoft Edge TTS (voice); we
never write audio to disk. Transcripts are only logged at DEBUG level, which production does not use.
