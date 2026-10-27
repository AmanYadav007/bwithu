import asyncio
import io
import queue
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, cast

import edge_tts
import librosa
import numpy as np
import soundfile as sf
from loguru import logger
from pydantic import BaseModel, Field
from abc import ABC
from chat_engine.contexts.handler_context import HandlerContext
from chat_engine.data_models.chat_engine_config_data import ChatEngineConfigModel, HandlerBaseConfigModel
from chat_engine.common.handler_base import HandlerBase, HandlerBaseInfo, HandlerDataInfo, HandlerDetail
from chat_engine.data_models.chat_data.chat_data_model import ChatData
from chat_engine.data_models.chat_data_type import ChatDataType
from chat_engine.data_models.chat_signal import ChatSignal, SignalFilterRule
from chat_engine.data_models.chat_signal_type import ChatSignalType
from chat_engine.contexts.session_context import SessionContext
from chat_engine.data_models.runtime_data.data_bundle import DataBundle, DataBundleDefinition, DataBundleEntry
from bwithu.persona import pick_voice
from engine_utils.text_utils import speakable_text

# Longest we wait for one chunk of speech before retrying.
SYNTH_TIMEOUT_S = 15
# Edge streams MP3 in 720-byte pieces (0.12 s); decode and pass audio on about every quarter second.
DECODE_EVERY_BYTES = 1440
# The last two MP3 frames of a partial stream can still change once the next bytes arrive.
UNSETTLED_SAMPLES = 1152
DEVANAGARI = re.compile(r"[\u0900-\u097F]")
# Chunk boundaries: the end of a sentence, or of a clause; only once the next character has arrived.
SENTENCE_END = re.compile(r"[.!?।](?=\s)")
CLAUSE_END = re.compile(r"[,;:.!?।](?=\s)")
# Edge's Multilingual and US English voices don't stream: they render the whole chunk before the first byte, so a
# chunk starts in about 0.6 s at 13 characters, 2-2.6 s at 45 and 4.5 s at 90 (the Indian and Hindi voices stream and
# start in ~0.6 s at any length). So the first chunk of a reply ends at its first clause of at least
# FIRST_CHUNK_MIN_CHARS (shorter than that, like "Hey!", it would barely play before the next one); later chunks are
# sentences, split at a clause past LONG_CHUNK_CHARS, so each is ready before the audio ahead of it has played.
FIRST_CHUNK_MIN_CHARS = 12
LONG_CHUNK_CHARS = 50

# Edge usually starts a chunk in 0.6-0.9 s and finishes it in under a second, but about one connection in five
# stalls for 3-7 s, before the first audio or partway through. So a chunk is requested again (at these seconds after
# the first request) while no copy has delivered, and the first to deliver is used:
# - the first chunk of a reply is what the user waits for: it streams, two copies at once, and the first to start
#   sending audio wins;
# - later chunks play only after the audio before them, so they don't stream: the first copy to finish wins, which
#   also beats a connection that starts on time and then trickles.
FIRST_CHUNK_HEDGES = (0.0, 0.0, 1.0)
LATER_CHUNK_HEDGES = (0.0, 1.0, 2.0)

# Edge pads every chunk with 0.15-0.25 s of silence before and 0.35-0.95 s after, so back-to-back sentences had over a
# second of dead air between them. That padding is cut (audio quieter than this, -48 dBFS, at either end; pauses
# inside a chunk stay), and the gap before the next chunk is set by the punctuation that ended the last one, the way
# people pause: short after a comma, longer after a sentence, a bit longer after a question, never exactly the same.
SILENCE_LEVEL = 0.004
EDGE_MARGIN_S = 0.04
FADE_S = 0.008
PAUSES_S = {",": 0.18, ";": 0.25, ":": 0.25, ".": 0.38, "!": 0.38, "।": 0.38, "?": 0.45}
DEFAULT_PAUSE_S = 0.3
PAUSE_JITTER = (0.85, 1.2)

# Edge requests run here, so all sentences of a reply are synthesized at once.
_synth_pool = ThreadPoolExecutor(max_workers=16, thread_name_prefix="edge-tts")


class TTSConfig(HandlerBaseConfigModel, BaseModel):
    ref_audio_path: str = Field(default=None)
    ref_audio_text: str = Field(default=None)
    voice: str = Field(default=None)
    # BwithU: client voice id -> Edge voice name; anything else falls back to `voice`.
    voices: Dict[str, str] = Field(default_factory=dict)
    # Client voice id -> Edge voice for Hindi (Devanagari) replies; the English voices can't read it.
    hindi_voices: Dict[str, str] = Field(default_factory=dict)
    hindi_voice: str = Field(default="hi-IN-SwaraNeural")
    sample_rate: int = Field(default=24000)


class _SynthJob:
    """One chunk of text being synthesized; its audio arrives in `pieces`, then None."""

    def __init__(self, text: str, voice: str, first: bool):
        self.text = text
        self.voice = voice
        self.stream = first
        self.hedges = FIRST_CHUNK_HEDGES if first else LATER_CHUNK_HEDGES
        self.owner: Optional[int] = None  # which of the copies delivers the audio
        self.delivered = False  # has any audio been passed on?
        self.emitted = 0  # samples of the decoded chunk passed on (or skipped as padding) so far
        self.pause_before = 0.0  # seconds of silence before this chunk
        self.pieces: "queue.Queue[Optional[np.ndarray]]" = queue.Queue()
        self.cancelled = threading.Event()
        self.started = time.monotonic()


class TTSContext(HandlerContext):
    def __init__(self, session_id: str):
        super().__init__(session_id)
        self.config = None
        self.input_text = ''
        # BwithU: text streams cancelled by an interrupt; their remaining audio is dropped.
        self.cancelled_keys = set()
        self.current_input_key = None
        self.voice = None
        self.hindi_voice = None
        self.jobs: List[_SynthJob] = []
        self.jobs_lock = threading.Lock()
        self.reply_started = False  # has the current reply had its first chunk?
        self.reply_hindi = False  # has the current reply had Devanagari? Then it stays in the Hindi voice.
        self.reply_jobs_started = False
        self.last_chunk_text = ''
        self.first_audio_logged = False


class HandlerTTS(HandlerBase, ABC):
    def __init__(self):
        super().__init__()
        self.voice = None
        self.sample_rate = None

    def get_handler_info(self) -> HandlerBaseInfo:
        return HandlerBaseInfo(
            config_model=TTSConfig,
        )

    def get_handler_detail(self, session_context: SessionContext,
                           context: HandlerContext) -> HandlerDetail:
        definition = DataBundleDefinition()
        definition.add_entry(DataBundleEntry.create_audio_entry("avatar_audio", 1, self.sample_rate))
        inputs = {
            ChatDataType.AVATAR_TEXT: HandlerDataInfo(
                type=ChatDataType.AVATAR_TEXT,
            )
        }
        outputs = {
            ChatDataType.AVATAR_AUDIO: HandlerDataInfo(
                type=ChatDataType.AVATAR_AUDIO,
                definition=definition,
            )
        }
        return HandlerDetail(
            inputs=inputs, outputs=outputs,
            signal_filters=[SignalFilterRule(ChatSignalType.STREAM_CANCEL, None, ChatDataType.AVATAR_TEXT),
                            SignalFilterRule(ChatSignalType.STREAM_CANCEL, None, ChatDataType.AVATAR_AUDIO)],
        )

    def load(self, engine_config: ChatEngineConfigModel, handler_config: Optional[BaseModel] = None):
        config = cast(TTSConfig, handler_config)
        self.voice = config.voice
        self.sample_rate = config.sample_rate

    def create_context(self, session_context, handler_config=None):
        if not isinstance(handler_config, TTSConfig):
            handler_config = TTSConfig()
        context = TTSContext(session_context.session_info.session_id)
        # BwithU: the voice picked in the web app for this call, and its Hindi counterpart.
        params = session_context.session_info.user_params or {}
        context.voice = pick_voice(params, handler_config.voices, handler_config.voice or self.voice)
        context.hindi_voice = pick_voice(params, handler_config.hindi_voices, handler_config.hindi_voice)
        logger.info(f"tts voice {context.voice} / {context.hindi_voice} for session {context.session_id}")
        return context

    def start_context(self, session_context, context: HandlerContext):
        pass

    # ------------------------------------------------------------------
    # Synthesis (runs in _synth_pool)
    # ------------------------------------------------------------------

    @staticmethod
    def _pass_on(job: _SynthJob, samples: np.ndarray, upto: int, final: bool):
        """Pass on samples[job.emitted:upto] minus Edge's padding: silence before the first sound is dropped,
        silence at the end is held back (it is passed on if more sound follows, dropped if the chunk ends)."""
        segment = samples[job.emitted:upto]
        loud = np.flatnonzero(np.abs(segment) > SILENCE_LEVEL)
        if loud.size == 0:
            return
        sr = 24000
        margin = round(EDGE_MARGIN_S * sr)
        start = job.emitted if job.delivered else job.emitted + max(0, loud[0] - margin)
        end = job.emitted + min(len(segment), loud[-1] + margin + 1)
        piece = samples[start:end].copy()
        fade = min(round(FADE_S * sr), len(piece))
        if not job.delivered:
            piece[:fade] *= np.linspace(0.0, 1.0, fade, dtype=np.float32)
        if final:
            piece[len(piece) - fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)
        job.delivered = True
        job.emitted = end
        job.pieces.put(piece)

    @staticmethod
    async def _stream_audio(job: _SynthJob, copy: int, claimed: asyncio.Event) -> bool:
        """Get one chunk from Edge. A streaming job claims the chunk at its first audio and passes the audio on as it
        decodes; otherwise the copy claims it when complete. Returns whether this copy delivered audio."""
        mp3 = b''
        decoded_upto = 0
        incremental = True
        async for chunk in edge_tts.Communicate(job.text, job.voice, connect_timeout=5, receive_timeout=10).stream():
            if job.cancelled.is_set():
                return True
            if chunk['type'] != 'audio':
                continue
            if job.stream and job.owner is None:
                job.owner = copy
                claimed.set()
            if job.owner is not None and job.owner != copy:
                return False
            mp3 += chunk['data']
            if job.stream and incremental and len(mp3) - decoded_upto >= DECODE_EVERY_BYTES:
                decoded_upto = len(mp3)
                try:
                    samples, _ = sf.read(io.BytesIO(mp3), dtype='float32')
                except Exception:
                    incremental = False  # no MP3 support in this libsndfile: decode once at the end
                    continue
                HandlerTTS._pass_on(job, samples, len(samples) - UNSETTLED_SAMPLES, final=False)
        if not mp3:
            return False
        if not job.stream:
            if job.owner is not None:
                return False
            job.owner = copy
            claimed.set()
        if incremental:
            samples, _ = sf.read(io.BytesIO(mp3), dtype='float32')
        else:
            samples = librosa.load(io.BytesIO(mp3), sr=None)[0]
        HandlerTTS._pass_on(job, samples, len(samples), final=True)
        return True

    @classmethod
    async def _race(cls, job: _SynthJob) -> bool:
        """Request the chunk at each of job.hedges (seconds) while nobody delivered yet; keep the first to deliver."""
        job.owner = None
        if not job.delivered:
            job.emitted = 0
        claimed = asyncio.Event()

        async def copy(i: int, delay: float) -> bool:
            if delay:
                await asyncio.sleep(delay)
            if job.owner is not None:
                return False
            return await cls._stream_audio(job, i, claimed)

        tasks = [asyncio.create_task(copy(i, delay)) for i, delay in enumerate(job.hedges)]
        waiter = asyncio.create_task(claimed.wait())
        remaining = set(tasks)
        try:
            while remaining and job.owner is None:
                done, _ = await asyncio.wait(remaining | {waiter}, return_when=asyncio.FIRST_COMPLETED)
                remaining -= done
            if job.owner is None:  # every copy failed; _run_job logs why and retries
                errors = [t.exception() for t in tasks if t.done() and not t.cancelled() and t.exception()]
                if errors:
                    raise errors[0]
                return False
            for i, task in enumerate(tasks):
                if i != job.owner:
                    task.cancel()
            return await tasks[job.owner]
        finally:
            waiter.cancel()
            for task in tasks:
                task.cancel()

    @classmethod
    def _run_job(cls, job: _SynthJob):
        # BwithU: Edge now and then returns no audio, or stops answering mid-sentence; give each attempt a hard
        # deadline (edge_tts can otherwise block forever) and retry while nothing has been played yet.
        try:
            for attempt in range(3):
                if job.cancelled.is_set():
                    return
                try:
                    if asyncio.run(asyncio.wait_for(cls._race(job), SYNTH_TIMEOUT_S)) or job.cancelled.is_set():
                        return
                    problem = 'no audio'
                except asyncio.TimeoutError:
                    problem = f'timed out after {SYNTH_TIMEOUT_S}s'
                except Exception as e:  # NoAudioReceived, network errors
                    problem = repr(e)
                logger.warning(f"edge tts: {problem} (attempt {attempt + 1}, voice {job.voice})")
                if job.delivered:
                    return  # part of the chunk is already out; don't repeat it
        finally:
            job.pieces.put(None)

    # ------------------------------------------------------------------
    # Text -> chunks -> jobs -> audio out
    # ------------------------------------------------------------------

    @staticmethod
    def _take_chunks(context: TTSContext, final: bool) -> List[str]:
        chunks = []
        while True:
            text = context.input_text
            cut = None
            if not context.reply_started:
                cut = next((m.end() for m in CLAUSE_END.finditer(text) if m.end() >= FIRST_CHUNK_MIN_CHARS), None)
            else:
                m = SENTENCE_END.search(text)
                cut = m.end() if m else None
                if cut is None and len(text) > LONG_CHUNK_CHARS:
                    clauses = [m.end() for m in CLAUSE_END.finditer(text)]
                    if clauses:
                        cut = clauses[-1]
            if cut is None:
                break
            chunks.append(text[:cut])
            context.input_text = text[cut:]
            context.reply_started = True
        if final and context.input_text.strip():
            chunks.append(context.input_text)
            context.input_text = ''
        return [c.strip() for c in chunks if c.strip()]

    def _start_job(self, context: TTSContext, text: str):
        if DEVANAGARI.search(text):
            context.reply_hindi = True
        voice = context.hindi_voice if context.reply_hindi else context.voice
        with context.jobs_lock:
            first = not context.reply_jobs_started
            context.reply_jobs_started = True
        job = _SynthJob(text, voice, first)
        if not first:
            last = context.last_chunk_text.rstrip()[-1:]
            job.pause_before = PAUSES_S.get(last, DEFAULT_PAUSE_S) * random.uniform(*PAUSE_JITTER)
        context.last_chunk_text = text
        with context.jobs_lock:
            context.jobs.append(job)
        _synth_pool.submit(self._run_job, job)

    def _cancel_jobs(self, context: TTSContext):
        with context.jobs_lock:
            for job in context.jobs:
                job.cancelled.set()
            context.jobs.clear()

    def _emit_audio(self, context: TTSContext, output_definition, stream_key, wait: bool) -> bool:
        """Pass on synthesized audio in order. With wait, until every job is done. False if interrupted."""
        while True:
            if stream_key in context.cancelled_keys:
                self._cancel_jobs(context)
                return False
            with context.jobs_lock:
                job = context.jobs[0] if context.jobs else None
            if job is None:
                return True
            try:
                piece = job.pieces.get(timeout=0.05) if wait else job.pieces.get_nowait()
            except queue.Empty:
                if wait:
                    continue
                return True
            if piece is None:
                with context.jobs_lock:
                    if context.jobs and context.jobs[0] is job:
                        context.jobs.pop(0)
                logger.info(f"TTS {round((time.monotonic() - job.started) * 1000)} ms for {len(job.text)} chars "
                            f"({job.voice})")
                continue
            if stream_key in context.cancelled_keys:
                continue  # dropped at the top of the loop
            if not context.first_audio_logged:
                context.first_audio_logged = True
                logger.info(f"TTS first audio after {round((time.monotonic() - job.started) * 1000)} ms")
            if job.pause_before:
                piece = np.concatenate([np.zeros(round(job.pause_before * self.sample_rate), np.float32), piece])
                job.pause_before = 0.0
            output = DataBundle(output_definition)
            output.set_main_data(piece[np.newaxis, ...])
            context.submit_data(output)

    def handle(self, context: HandlerContext, inputs: ChatData,
               output_definitions: Dict[ChatDataType, HandlerDataInfo]):
        output_definition = output_definitions.get(ChatDataType.AVATAR_AUDIO).definition
        context = cast(TTSContext, context)
        if inputs.type != ChatDataType.AVATAR_TEXT:
            return
        text = inputs.data.get_main_data()
        stream_key = inputs.stream_id.stream_key_str if inputs.stream_id else None
        if stream_key != context.current_input_key:
            # A new reply: forget the old one's leftovers.
            self._cancel_jobs(context)
            context.input_text = ''
            context.reply_started = False
            context.reply_hindi = False
            context.reply_jobs_started = False
            context.first_audio_logged = False
        context.current_input_key = stream_key
        if stream_key in context.cancelled_keys:
            context.input_text = ''
            return
        if text is not None:
            text = re.sub(r"<\|.*?\|>", "", text)
            context.input_text += speakable_text(text)

        # The LLM ends a reply with an empty, last chunk.
        text_end = inputs.is_last_data or inputs.data.get_meta("avatar_text_end", False)
        for chunk in self._take_chunks(context, final=text_end):
            self._start_job(context, chunk)
        if not self._emit_audio(context, output_definition, stream_key, wait=text_end):
            context.input_text = ''
            return
        if text_end:
            output = DataBundle(output_definition)
            output.set_main_data(np.zeros(shape=(1, 240), dtype=np.float32))
            context.submit_data(output, finish_stream=True)
            logger.info("speech end")

    def on_signal(self, context: HandlerContext, signal: ChatSignal):
        context = cast(TTSContext, context)
        if signal.type == ChatSignalType.STREAM_CANCEL and signal.related_stream:
            # Our own audio output was cancelled (text may have finished already): stop the text we're reading.
            context.cancelled_keys.add(signal.related_stream.stream_key_str)
            if context.current_input_key:
                context.cancelled_keys.add(context.current_input_key)
            context.input_text = ''
            self._cancel_jobs(context)

    def destroy_context(self, context: HandlerContext):
        context = cast(TTSContext, context)
        self._cancel_jobs(context)
        logger.info('destroy context')
