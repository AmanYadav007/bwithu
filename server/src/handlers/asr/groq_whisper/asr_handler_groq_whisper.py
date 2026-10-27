"""BwithU: speech-to-text with Whisper on Groq (free, ~200 ms, more accurate than SenseVoice on accents and names),
falling back to the local SenseVoice model when Groq is unreachable or slow, so a call never goes deaf.

In English calls Whisper detects the language itself, but it mistakes very short words ("हाँ") for Japanese and
Hindi for Urdu; those turns are transcribed again in the language the user has been speaking.
Real Hindi speech with an Indian accent and English words mixed in is mostly detected as English (and written as an
English translation), so in calls where the user chose Hindi every turn is transcribed as Hindi, with
whisper-large-v3: unlike turbo, it keeps English words and even whole English sentences intact when told "Hindi".
"""
import io
import os
import time
from typing import Optional, Tuple

import numpy as np
import soundfile as sf
from loguru import logger
from openai import OpenAI
from pydantic import BaseModel, Field

# Module import, not class names: the handler loader takes the first HandlerBase subclass in this module's
# namespace (alphabetically), which would otherwise be SenseVoice's HandlerASR.
import asr.sensevoice.asr_handler_sensevoice as sensevoice
from bwithu.persona import DEFAULT_NAME, clean_name
from chat_engine.common.handler_base import HandlerBaseInfo
from chat_engine.data_models.chat_engine_config_data import ChatEngineConfigModel

# Whisper's language names -> the languages a call runs in. Urdu speech is Hindustani; we write it as Hindi.
LANGUAGES = {"english": "en", "hindi": "hi", "urdu": "hi"}


class GroqWhisperConfig(sensevoice.ASRConfig):
    api_url: str = Field(default="https://api.groq.com/openai/v1")
    api_key: Optional[str] = Field(default=os.getenv("GROQ_API_KEY") or os.getenv("LLM_API_KEY"))
    whisper_model: str = Field(default="whisper-large-v3-turbo")
    # For Hindi calls and the second pass on short or misdetected turns: slower than turbo, but right on short Hindi
    # words and on English inside Hindi.
    retry_model: str = Field(default="whisper-large-v3")
    # Turns shorter than this that come back in another language are transcribed again.
    short_turn_s: float = Field(default=2.5)
    timeout_s: float = Field(default=3.0)
    # Whisper "hears" words in noise ("Thank you."); drop segments it rates as probably not speech.
    max_no_speech_prob: float = Field(default=0.6)


class HandlerGroqWhisper(sensevoice.HandlerASR):
    def __init__(self):
        super().__init__()
        self.client: Optional[OpenAI] = None
        self.config = GroqWhisperConfig()

    def get_handler_info(self) -> HandlerBaseInfo:
        return HandlerBaseInfo(name="ASR_GroqWhisper", config_model=GroqWhisperConfig)

    def load(self, engine_config: ChatEngineConfigModel, handler_config: Optional[BaseModel] = None):
        if isinstance(handler_config, GroqWhisperConfig):
            self.config = handler_config
        super().load(engine_config, handler_config)  # SenseVoice, the fallback
        if self.config.api_key:
            self.client = OpenAI(api_key=self.config.api_key, base_url=self.config.api_url,
                                 timeout=self.config.timeout_s, max_retries=1)
        else:
            logger.warning("No Groq API key: speech-to-text uses local SenseVoice only")

    def create_context(self, session_context, handler_config=None):
        context = super().create_context(session_context, handler_config)
        params = session_context.session_info.user_params or {}
        # The names come up a lot and are easy to mishear; Whisper spells them right when it's told them.
        names = [clean_name(params.get("name"), DEFAULT_NAME)]
        if params.get("user"):
            names.append(clean_name(params.get("user"), ""))
        context.prompt = ", ".join(n for n in names if n) + "."
        context.forced_language = "hi" if params.get("lang") == "hi" else None
        context.language = context.forced_language or "en"  # what the user has been speaking
        return context

    def transcribe(self, audio: np.ndarray, context=None) -> str:
        language = getattr(context, "language", "en")
        if self.client is not None:
            try:
                text, detected = self._transcribe_groq(audio, getattr(context, "prompt", None), language,
                                                       getattr(context, "forced_language", None))
                if detected and context is not None:
                    context.language = detected
                return text
            except Exception as e:
                logger.warning(f"Groq Whisper failed ({e!r})")
        if language == "hi":
            logger.warning("SenseVoice can't transcribe Hindi; skipping this turn")
            return ""
        logger.warning("Using SenseVoice for this turn")
        return super().transcribe(audio)

    def _request(self, wav: bytes, model: str, prompt: Optional[str], language: Optional[str] = None):
        kwargs = {"prompt": prompt} if prompt else {}
        if language:
            kwargs["language"] = language
        return self.client.audio.transcriptions.create(
            model=model, file=("speech.wav", wav), response_format="verbose_json", **kwargs)

    def _transcribe_groq(self, audio: np.ndarray, prompt: Optional[str], language: str,
                         forced_language: Optional[str] = None) -> Tuple[str, Optional[str]]:
        buffer = io.BytesIO()
        sf.write(buffer, audio.astype(np.float32), 16000, format="WAV", subtype="PCM_16")
        wav = buffer.getvalue()
        started = time.monotonic()
        seconds = len(audio) / 16000
        if forced_language:
            result = self._request(wav, self.config.retry_model, prompt, forced_language)
            heard, detected = forced_language, forced_language
        else:
            result = self._request(wav, self.config.whisper_model, prompt)
            heard = (getattr(result, "language", None) or "").lower()
            detected = LANGUAGES.get(heard)
        if not forced_language and (heard == "urdu" or (detected is None and seconds < self.config.short_turn_s)):
            retry_language = detected or language
            logger.info(f"ASR heard {heard or 'no language'} in {seconds:.1f} s; transcribing again as {retry_language}")
            result = self._request(wav, self.config.retry_model, prompt, retry_language)
            detected = retry_language
        segments = getattr(result, "segments", None) or []
        no_speech = max((_get(seg, "no_speech_prob", 0.0) for seg in segments), default=0.0)
        logger.info(f"ASR {round((time.monotonic() - started) * 1000)} ms for {seconds:.1f} s of speech, "
                    f"language={heard}, no_speech={no_speech:.2f}")
        if not segments:
            return (result.text or "").strip(), detected
        kept = [s for s in segments if _get(s, "no_speech_prob", 0.0) <= self.config.max_no_speech_prob]
        return " ".join(_get(s, "text", "").strip() for s in kept).strip(), detected


def _get(segment, key, default):
    return segment.get(key, default) if isinstance(segment, dict) else getattr(segment, key, default)
