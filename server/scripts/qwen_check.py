"""Smoke-test Qwen-Omni realtime with our settings, before trusting it in a call.

For each voice: connect, send a spoken question, and measure time-to-first-audio, reply length and the
token usage Qwen reports (-> real cost per minute). Also checks the greeting path (response without
user audio). Usage, from server/:

    set -a; . ../.env; set +a; .venv/bin/python scripts/qwen_check.py [model]
"""
import base64
import os
import sys
import threading
import time
import wave

import dashscope
import numpy as np
from dashscope.audio.qwen_omni import AudioFormat, MultiModality, OmniRealtimeCallback, OmniRealtimeConversation
from scipy.signal import resample_poly

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from bwithu.persona import build_greeting_instructions, build_instructions  # noqa: E402

MODEL = sys.argv[1] if len(sys.argv) > 1 else "qwen3.5-omni-flash-realtime"
URL = os.getenv("DASHSCOPE_REALTIME_URL", "wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime")
VOICES = ["Tina", "Cherry", "Ethan", "Serena"]
PRICE_IN_AUDIO, PRICE_OUT_AUDIO = 4.5e-6, 17.7e-6  # USD per token, Singapore (Oct 2026)
QUESTION = os.path.join(os.path.dirname(__file__), "..", "..", "web", "e2e", "fixtures", "question.wav")


def load_question_pcm16k() -> bytes:
    with wave.open(QUESTION) as w:
        rate, frames = w.getframerate(), w.readframes(w.getnframes())
    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32)
    audio = resample_poly(audio, 16000, rate)
    nonsilent = np.nonzero(np.abs(audio) > 300)[0]  # trim the long silences around the question
    audio = audio[max(0, nonsilent[0] - 1600): nonsilent[-1] + 8000]
    return np.clip(audio, -32768, 32767).astype(np.int16).tobytes()


class Probe(OmniRealtimeCallback):
    def __init__(self):
        self.opened, self.done = threading.Event(), threading.Event()
        self.first_audio_at = None
        self.audio_bytes = 0
        self.text = ""
        self.usage = None
        self.error = None

    def on_open(self):
        self.opened.set()

    def on_close(self, code, msg):
        self.opened.set()
        self.done.set()

    def on_event(self, event):
        kind = event.get("type")
        if kind == "response.audio.delta":
            if self.first_audio_at is None:
                self.first_audio_at = time.monotonic()
            self.audio_bytes += len(base64.b64decode(event.get("delta", "")))
        elif kind in ("response.audio_transcript.delta", "response.text.delta"):
            self.text += event.get("delta", "")
        elif kind == "response.done":
            self.usage = (event.get("response") or {}).get("usage")
            self.done.set()
        elif kind == "error":
            self.error = event.get("error")
            self.done.set()


def run(voice: str, pcm: bytes | None, instructions: str):
    probe = Probe()
    conv = OmniRealtimeConversation(model=MODEL, callback=probe, url=URL)
    conv.connect()
    if not probe.opened.wait(15):
        return {"voice": voice, "error": "connect timeout"}
    conv.update_session(
        output_modalities=[MultiModality.AUDIO, MultiModality.TEXT], voice=voice,
        input_audio_format=AudioFormat.PCM_16000HZ_MONO_16BIT, output_audio_format=AudioFormat.PCM_24000HZ_MONO_16BIT,
        enable_input_audio_transcription=False, enable_turn_detection=False, instructions=instructions)
    time.sleep(0.3)
    if pcm:
        for i in range(0, len(pcm), 3200):  # 100 ms chunks
            conv.append_audio(base64.b64encode(pcm[i:i + 3200]).decode())
        conv.commit()
        t0 = time.monotonic()
        conv.create_response()
    else:
        t0 = time.monotonic()
        conv.create_response(instructions=instructions)
    probe.done.wait(30)
    conv.close()
    out_seconds = probe.audio_bytes / 2 / 24000
    result = {"voice": voice, "first_audio_ms": round((probe.first_audio_at - t0) * 1000) if probe.first_audio_at else None,
              "reply_s": round(out_seconds, 1), "text": probe.text.strip()[:90], "usage": probe.usage, "error": probe.error}
    return result


def cost_per_minute(results, in_seconds):
    """Estimate from Qwen's reported usage, assuming a call is ~half user talk, ~half avatar talk."""
    for r in results:
        u = r.get("usage") or {}
        in_tok = (u.get("input_token_details") or {}).get("audio_tokens") or u.get("input_tokens")
        out_tok = (u.get("output_token_details") or {}).get("audio_tokens") or u.get("output_tokens")
        if in_tok and out_tok and r["reply_s"]:
            in_rate, out_rate = in_tok / in_seconds, out_tok / r["reply_s"]
            per_min = 30 * in_rate * PRICE_IN_AUDIO + 30 * out_rate * PRICE_OUT_AUDIO
            return in_rate, out_rate, per_min
    return None


if __name__ == "__main__":
    dashscope.api_key = os.getenv("DASHSCOPE_API_KEY")
    if not dashscope.api_key:
        sys.exit("DASHSCOPE_API_KEY is not set")
    pcm = load_question_pcm16k()
    in_seconds = len(pcm) / 2 / 16000
    params = {"name": "Nova", "user": "Aman", "vibe": "warm"}
    print(f"model={MODEL} url={URL} question={in_seconds:.1f}s")
    results = []
    for voice in VOICES:
        r = run(voice, pcm, build_instructions(params))
        results.append(r)
        print(r)
    print("greeting:", run(VOICES[0], None, build_greeting_instructions(params)))
    est = cost_per_minute(results, in_seconds)
    if est:
        print(f"audio tokens/s: in {est[0]:.1f}, out {est[1]:.1f} -> about ${est[2]:.3f} per call minute "
              f"(half user, half avatar speech)")
    ok = [r["voice"] for r in results if r.get("first_audio_ms") and not r.get("error")]
    print("voices that work:", ok)
