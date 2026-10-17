# BwithU

A face-to-face AI companion in the browser. The user picks a face, names it, and talks; it answers with a
realistic 3D head that lip-syncs in real time.

## How it works

```
browser mic ──WebSocket──► server: Silero VAD ─► Qwen-Omni realtime (hears, thinks, speaks)
                                   └─► LAM audio2expression (52 face blendshapes / frame)
browser ◄──WebSocket── audio + face motion ── 3D Gaussian head rendered on the user's GPU
```

- **No video is streamed** and the server needs **no GPU**: the face is drawn in the browser from tiny
  motion frames. A single CPU VM should serve several calls at once (see the capacity numbers below); Qwen tokens are the only per-minute cost.
- **No WebRTC/TURN**: plain WebSockets work through any network or proxy.
- Built on [OpenAvatarChat](https://github.com/HumanAIGC-Engineering/OpenAvatarChat) (Apache-2.0) and
  [LAM](https://github.com/aigc3d/LAM), trimmed to what we use.

| Path | What |
| --- | --- |
| `server/` | Python call server (fork of OpenAvatarChat). Our code is in `src/bwithu/` (persona, call gate) |
| `server/config/bwithu.yaml` | Production pipeline: Qwen-Omni + LAM |
| `server/config/bwithu_dev.yaml` | Dev pipeline without Qwen: SenseVoice ASR + any OpenAI-compatible LLM + Edge TTS |
| `web/` | Vue app: setup screen (face, name, vibe, voice) and call screen |
| `avatars-src/` | Synthetic portraits waiting to become new faces (see its README) |
| `Dockerfile`, `deploy/` | One-container deploy behind Caddy (HTTPS) |

## Run locally (Mac)

```bash
# once
cd server && uv venv --python 3.11 .venv && VIRTUAL_ENV=.venv uv pip install \
  --index-url https://download.pytorch.org/whl/cpu torch==2.8.0 torchaudio==2.8.0 torchvision==0.23.0 \
  && VIRTUAL_ENV=.venv uv pip install -r requirements-dev.txt && PYTHON=.venv/bin/python scripts/fetch_models.sh
cd ../web && npm install && npx vite build

# every time
cd server && ./run.sh            # Qwen pipeline (needs DASHSCOPE_API_KEY in ../.env)
cd server && ./run.sh bwithu_dev # dev pipeline (LLM_* in ../.env)
open http://127.0.0.1:8282
```

For UI work, `cd web && npm run dev` serves on :5173 and proxies to the server.

## Limits and controls (env vars, no redeploy needed)

| Var | Default | Meaning |
| --- | --- | --- |
| `BWITHU_MAX_CALLS` | 10 | Simultaneous calls; extra callers see "try again in a minute" |
| `BWITHU_DAILY_SECONDS` | 600 | Free talk time per person per day (per browser id, 3× per IP) |
| `BWITHU_MAX_CALL_SECONDS` | 600 | Hard cap per call |
| `BWITHU_PAUSED=1` or file `server/PAUSED` | off | Kill switch: refuse new calls |
| `BWITHU_ADMIN_TOKEN` | unset | Enables `GET /bwithu/stats?token=…` (active calls, minutes today) |

## Deploy

1. A Linux VM with 4–8 vCPU, 8 GB RAM, Docker (e.g. Hetzner CPX41 / DigitalOcean 8 GB, ~$30–50/month).
2. DNS: `app.bwithu.live` A record → VM IP.
3. Copy the repo and `.env` (with `DASHSCOPE_API_KEY`, `BWITHU_ADMIN_TOKEN`), then
   `cd deploy && docker compose up -d --build`. Caddy gets the HTTPS certificate automatically.

## Privacy

User audio is streamed to Alibaba Cloud Model Studio (Singapore) for the reply and is never written to disk by
us. Transcripts are only logged at DEBUG level, which production does not use.
