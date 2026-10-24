"""BwithU: speech-to-text with Whisper on Groq (free, ~200 ms, more accurate than SenseVoice on accents and names),
falling back to the local SenseVoice model when Groq is unreachable or slow, so a call never goes deaf.
"""
import io
import os
from typing import Optional

import numpy as np
import soundfile as sf
from loguru import logger
from openai import OpenAI
from pydantic import BaseModel, Field

# Module import, not class names: the handler loader takes the first HandlerBase subclass in this module's
# namespace (alphabetically), which would otherwise be SenseVoice's HandlerASR.
import asr.sensevoice.asr_handler_sensevoice as sensevoice
from chat_engine.common.handler_base import HandlerBaseInfo
from chat_engine.data_models.chat_engine_config_data import ChatEngineConfigModel


class GroqWhisperConfig(sensevoice.ASRConfig):
    api_url: str = Field(default="https://api.groq.com/openai/v1")
    api_key: Optional[str] = Field(default=os.getenv("GROQ_API_KEY") or os.getenv("LLM_API_KEY"))
    whisper_model: str = Field(default="whisper-large-v3-turbo")
    timeout_s: float = Field(default=4.0)
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

    def transcribe(self, audio: np.ndarray) -> str:
        if self.client is not None:
            try:
                return self._transcribe_groq(audio)
            except Exception as e:
                logger.warning(f"Groq Whisper failed ({e!r}); using SenseVoice for this turn")
        return super().transcribe(audio)

    def _transcribe_groq(self, audio: np.ndarray) -> str:
        wav = io.BytesIO()
        sf.write(wav, audio.astype(np.float32), 16000, format="WAV", subtype="PCM_16")
        result = self.client.audio.transcriptions.create(
            model=self.config.whisper_model,
            file=("speech.wav", wav.getvalue()),
            response_format="verbose_json",
        )
        segments = getattr(result, "segments", None) or []
        if not segments:
            return (result.text or "").strip()
        kept = [s for s in segments if _get(s, "no_speech_prob", 0.0) <= self.config.max_no_speech_prob]
        return " ".join(_get(s, "text", "").strip() for s in kept).strip()


def _get(segment, key, default):
    return segment.get(key, default) if isinstance(segment, dict) else getattr(segment, key, default)
