import os
import re
import time
from typing import Dict, Optional, Set, cast
from loguru import logger
from pydantic import BaseModel, Field
from abc import ABC
from openai import APIStatusError, OpenAI
from chat_engine.contexts.handler_context import HandlerContext
from chat_engine.data_models.chat_engine_config_data import ChatEngineConfigModel, HandlerBaseConfigModel
from chat_engine.common.handler_base import HandlerBase, HandlerBaseInfo, HandlerDataInfo, HandlerDetail
from chat_engine.data_models.chat_data.chat_data_model import ChatData
from chat_engine.data_models.chat_data_type import ChatDataType
from chat_engine.data_models.chat_signal import ChatSignal, SignalFilterRule
from chat_engine.data_models.chat_signal_type import ChatSignalType
from chat_engine.data_models.chat_stream import StreamKey
from chat_engine.contexts.session_context import SessionContext
from chat_engine.data_models.runtime_data.data_bundle import DataBundle, DataBundleDefinition, DataBundleEntry
from handlers.llm.openai_compatible.chat_history_manager import ChatHistory, HistoryMessage
from bwithu.persona import GREETING_CUE, build_instructions
from chat_engine.data_models.chat_stream_config import ChatStreamConfig

DEVANAGARI = re.compile(r"[\u0900-\u097F]")


class LLMConfig(HandlerBaseConfigModel, BaseModel):
    # BwithU: LLM_* env vars let the dev pipeline use any OpenAI-compatible provider.
    # The system prompt comes from src/bwithu/persona.py (name / vibe chosen in the web app).
    model_name: str = Field(default=os.getenv("LLM_MODEL", ""))
    api_key: Optional[str] = Field(default=os.getenv("LLM_API_KEY"))
    api_url: str = Field(default=os.getenv("LLM_API_URL", "https://api.groq.com/openai/v1"))
    history_length: int = Field(default=20)
    temperature: float = Field(default=0.7)
    # A spoken reply is one to three sentences; Hindi in Devanagari takes about twice the tokens of English.
    max_tokens: int = Field(default=200)
    # Provider-specific request fields, e.g. {"reasoning_effort": "none"} so a reasoning model answers at once.
    extra_body: Dict = Field(default_factory=dict)
    # BwithU: Hindi turns go to a model that writes better Hindi (empty: use model_name for everything).
    hindi_model_name: str = Field(default="")
    hindi_extra_body: Dict = Field(default_factory=dict)
    hindi_max_tokens: int = Field(default=300)
    # BwithU: if the user talks over a reply this soon after it was generated, they hadn't finished their turn
    # (a pause mid-sentence ended it early), so their next words are merged into that turn instead.
    early_interrupt_merge_s: float = Field(default=3.0)


class LLMContext(HandlerContext):
    def __init__(self, session_id: str):
        super().__init__(session_id)
        self.config = None
        self.local_session_id = 0
        self.model_name = None
        self.system_prompt = None
        self.api_key = None
        self.api_url = None
        self.client = None
        self.input_texts = ""
        self.output_texts = ""
        self.history = None
        self.active_stream_keys: Set[StreamKey] = set()
        self.early_interrupt_merge_s = 3.0
        self.last_turn = None  # (human text, time its reply finished generating)
        self.merge_next = False
        self.hindi = False  # is the conversation in Hindi right now?


class HandlerLLM(HandlerBase, ABC):
    def __init__(self):
        super().__init__()

    def get_handler_info(self) -> HandlerBaseInfo:
        return HandlerBaseInfo(
            config_model=LLMConfig,
        )

    def get_handler_detail(self, session_context: SessionContext,
                           context: HandlerContext) -> HandlerDetail:
        definition = DataBundleDefinition()
        definition.add_entry(DataBundleEntry.create_text_entry("avatar_text"))
        inputs = {
            ChatDataType.HUMAN_TEXT: HandlerDataInfo(
                type=ChatDataType.HUMAN_TEXT,
            ),
        }
        outputs = {
            ChatDataType.AVATAR_TEXT: HandlerDataInfo(
                type=ChatDataType.AVATAR_TEXT,
                definition=definition,
            )
        }
        return HandlerDetail(
            inputs=inputs, 
            outputs=outputs,
            signal_filters=[
                SignalFilterRule(ChatSignalType.STREAM_CANCEL, None, None)
            ]
        )

    def load(self, engine_config: ChatEngineConfigModel, handler_config: Optional[BaseModel] = None):
        if isinstance(handler_config, LLMConfig):
            if handler_config.api_key is None or len(handler_config.api_key) == 0:
                error_message = 'LLM_API_KEY is not set'
                logger.error(error_message)
                raise ValueError(error_message)

    def create_context(self, session_context, handler_config=None):
        if not isinstance(handler_config, LLMConfig):
            handler_config = LLMConfig()
        context = LLMContext(session_context.session_info.session_id)
        context.model_name = handler_config.model_name
        # BwithU: persona from the client's (sanitized) params.
        params = session_context.session_info.user_params or {}
        context.system_prompt = {'role': 'system', 'content': build_instructions(params)}
        context.api_key = handler_config.api_key
        context.api_url = handler_config.api_url
        context.history = ChatHistory(history_length=handler_config.history_length)
        context.early_interrupt_merge_s = handler_config.early_interrupt_merge_s
        context.config = handler_config
        context.hindi = params.get("lang") == "hi"  # the user picked Hindi: start (and greet) in Hindi
        context.client = OpenAI(
            api_key=context.api_key,
            base_url=context.api_url,
            timeout=5.0,  # so an unresponsive API can't stall the call
        )
        return context
    
    def start_context(self, session_context, handler_context):
        pass

    def handle(self, context: HandlerContext, inputs: ChatData,
               output_definitions: Dict[ChatDataType, HandlerDataInfo]):
        output_definition = output_definitions.get(ChatDataType.AVATAR_TEXT).definition
        context = cast(LLMContext, context)

        streamer = context.data_submitter.get_streamer(ChatDataType.AVATAR_TEXT)
        if inputs.type != ChatDataType.HUMAN_TEXT:
            return
        text = inputs.data.get_main_data()

        stream_key = streamer.current_stream.identity.stream_key_str if streamer.current_stream is not None else None
        if stream_key is None:
            stream = streamer.new_stream(sources=[inputs.stream_id], name="openai_compatible", config=ChatStreamConfig(cancelable=True))
            stream_key = stream.stream_key_str

        if text is not None:
            context.input_texts += text

        text_end = inputs.is_last_data
        if not text_end:
            return

        chat_text = context.input_texts
        chat_text = re.sub(r"<\|.*?\|>", "", chat_text)
        if len(chat_text) < 1:
            logger.warning("LLM got empty query, return emtpy response.")
            end_output = DataBundle(output_definition)
            end_output.set_main_data('')
            streamer.stream_data(end_output, name="openai_compatible", config=ChatStreamConfig(cancelable=True), finish_stream=True)
            return
        chat_text = self._merge_early_interrupted_turn(context, chat_text)
        model, max_tokens, extra_body = self._pick_model(context, chat_text)
        logger.debug(f'llm input {model} {chat_text} ')
        current_content = context.history.generate_next_messages(chat_text)
        if stream_key:
            context.active_stream_keys.add(stream_key)
        cancelled = False
        started = time.monotonic()
        first_token_at = None
        try:
            completion = context.client.chat.completions.create(
                model=model,
                messages=[
                    context.system_prompt,
                ] + current_content,
                stream=True,
                stream_options={"include_usage": True},
                temperature=context.config.temperature,
                max_tokens=max_tokens,
                extra_body=extra_body or None,
            )
            context.input_texts = ''
            context.output_texts = ''
            for chunk in completion:
                if stream_key and stream_key not in context.active_stream_keys:
                        cancelled = True
                        try:
                            completion.close()
                        except Exception:
                            pass
                        break
                if (chunk and chunk.choices and chunk.choices[0] and chunk.choices[0].delta.content):
                    output_text = chunk.choices[0].delta.content
                    if first_token_at is None:
                        first_token_at = time.monotonic()
                        logger.info(f"LLM first token after {round((first_token_at - started) * 1000)} ms")
                    context.output_texts += output_text
                    logger.debug(output_text)
                    output = DataBundle(output_definition)
                    output.set_main_data(output_text)
                    streamer.stream_data(output)
            if not cancelled:
                context.history.add_message(HistoryMessage(role="human", content=chat_text))
                context.history.add_message(HistoryMessage(role="avatar", content=context.output_texts))
                context.last_turn = (chat_text, time.monotonic())
        except Exception as e:
            if isinstance(e, APIStatusError):
                logger.error(f"LLM error {e.status_code}: {e.body or e}")
            else:
                logger.error(f"LLM error: {e}")
            # BwithU: the avatar speaks this, so never the provider's error message.
            output = DataBundle(output_definition)
            output.set_main_data("Sorry, I lost my train of thought for a second. Could you say that again?")
            streamer.stream_data(output, finish_stream=True)
        context.input_texts = ''
        context.output_texts = ''
        if cancelled:
            return
        if stream_key:
            context.active_stream_keys.discard(stream_key)
        end_output = DataBundle(output_definition)
        end_output.set_main_data('')
        streamer.stream_data(end_output, finish_stream=True)

    @staticmethod
    def _pick_model(context: "LLMContext", chat_text: str):
        config = context.config
        if DEVANAGARI.search(chat_text):
            context.hindi = True
        elif len(chat_text.split()) >= 4 and chat_text != GREETING_CUE:
            context.hindi = False  # a real English sentence; a short "okay" doesn't switch languages
        if context.hindi and config.hindi_model_name:
            return config.hindi_model_name, config.hindi_max_tokens, config.hindi_extra_body
        return context.model_name, config.max_tokens, config.extra_body

    @staticmethod
    def _merge_early_interrupted_turn(context: "LLMContext", chat_text: str) -> str:
        if not context.merge_next or context.last_turn is None:
            return chat_text
        previous, _ = context.last_turn
        context.merge_next = False
        context.last_turn = None
        history = context.history.message_history
        # Drop the exchange the user talked over and answer the whole sentence instead.
        if len(history) >= 2 and history[-2].role == "human" and history[-2].content == previous:
            del history[-2:]
        logger.info("LLM: merged an early-interrupted turn into the next one")
        return f"{previous} {chat_text}"

    def on_signal(self, context: HandlerContext, signal: ChatSignal):
        context = cast(LLMContext, context)
        if signal.type == ChatSignalType.STREAM_CANCEL and context.last_turn is not None:
            text, finished_at = context.last_turn
            if text != GREETING_CUE and time.monotonic() - finished_at <= context.early_interrupt_merge_s:
                context.merge_next = True
        if signal.type == ChatSignalType.STREAM_CANCEL and signal.related_stream:
            stream_key = signal.related_stream.stream_key_str
            if stream_key is not None and stream_key in context.active_stream_keys:
                context.active_stream_keys.discard(stream_key)
                logger.info(f"LLM: Removed stream {stream_key} from active set")

    def destroy_context(self, context: HandlerContext):
        context = cast(LLMContext, context)
        if context.client is not None:
            try:
                context.client.close()
            except Exception:
                pass
            context.client = None

