# BwithU launch — status and next steps

Updated Oct 18, 2026, 5 am IST. Target: live the weekend of Oct 24–25.

## Working tonight (tested in headless Chrome and WebKit on this Mac)

- **Setup → call flow**: pick a face, name the companion, optional user name, vibe, voice; full-screen call
  with live 3D face, status, timer, captions paced to speech, mute/speaker/hang-up, friendly end and error
  states, post-call feedback.
- **The companion picks up first**: "Hey Aman, good to see you. How are you doing?"
- **Interruptions**: talk over it (or tap the video) and it stops within ~0.3 s and listens; the first
  words of the interruption are kept.
- **Speed**: the face appears 0.4–0.7 s after "Start call". With the stand-in dev brain (Grok + free
  Edge voice) replies start 1.3–2.5 s after you stop talking; Qwen-Omni should be faster (one step
  instead of three) — measured automatically once the key is in.
- **Cheap to run**: no GPU, no WebRTC/TURN. One CPU VM; the lip-sync model ran 20× real time on the M2.
- **Guardrails**: 10 free minutes per person per day, max 10 simultaneous calls ("try again in a minute"),
  10-minute call cap enforced by the server, kill switch, admin stats, no audio or transcripts stored.
- **Safety**: AI disclosure everywhere, 18+ notice, crisis-response rule in the persona, Privacy and
  Terms drafts at `/ui/privacy.html` and `/ui/terms.html`.
- **iPhone/Safari**: fixed three blockers (audio unlock on tap, cross-origin isolation for the 3D
  renderer, a renderer bug on iOS < 16.4).

## Needed from you (in order of urgency)

1. **Qwen API key** → paste into `BwithU-new-speed/.env` as `DASHSCOPE_API_KEY=` (Alibaba Cloud Model
   Studio, *international*/Singapore). A watcher is running: it will test latency, the four voices, the
   greeting and the real cost per minute, then run the full call tests on the real pipeline.
2. **A server + DNS**: a 4–8 vCPU / 8 GB Linux VM with Docker (Hetzner, DigitalOcean, AWS Lightsail —
   ~$30–50/month), and an `app.bwithu.live` A record pointing at it. Then deploy is
   `cd deploy && docker compose up -d --build`.
3. **More faces (especially women)**: six synthetic portraits are ready in `avatars-src/`. Converting them
   needs either a free ModelScope access token (I automate it) or ~10 minutes of your clicks on the
   ModelScope LAM demo. See `avatars-src/README.md`.
4. **Legal**: read the Privacy/Terms drafts (not legal advice — have them checked), and create the
   `hello@bwithu.live` mailbox they mention (or tell me another address).
5. **Decisions**: open to everyone at launch, or invite-only from the waitlist? Default companion name
   "Nova" OK? Keep the "Sketch" and "Marble" faces?

## Plan for the week

| Day | Work |
| --- | --- |
| Sun 18 | Qwen key → validate latency, voices, cost; tune turn-taking on the real pipeline |
| Mon 19 | Deploy to the VM behind HTTPS; test on real phones (iPhone Safari + Android Chrome) on 4G |
| Tue 20 | New faces (women first); voice samples on the setup screen |
| Wed 21 | Load test 10 simultaneous calls on the VM; set limits from the results |
| Thu 22 | Polish from phone tests (echo on speakers, captions, mobile layout) |
| Fri 23 | Go / no-go; invite the first waitlist group or open the link |
| Sat–Sun | Launch; watch `/bwithu/stats` and feedback; fix fast |

## Known gaps

- Qwen-Omni path is wired (intl endpoint, persona, voice, greeting, interrupt cancel) but **not yet run
  against the real API**; the dev pipeline proves everything around it.
- Voice barge-in on phone *speakers* relies on the browser's echo canceller; needs a real-device check.
  Headphones are recommended on the call screen.
- The 3D renderer keeps ~480 MB of browser memory per page (+~20 MB per extra call). Fine for a few calls;
  watch older phones.
- Avatar choice is 2 realistic men + 2 stylized faces until new faces are converted.
