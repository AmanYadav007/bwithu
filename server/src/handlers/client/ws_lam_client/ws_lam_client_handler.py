"""
LAM WebSocket Client Handler

Audio, text, motion data and signals all travel over a single ``/ws/session/{session_id}`` connection.
Also serves the avatar asset zips and the BwithU stats/feedback routes.
"""
from __future__ import annotations

import asyncio
import os
import re
from typing import Dict, Optional, cast

from fastapi import FastAPI, Request, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from loguru import logger
from pydantic import BaseModel, Field
from starlette.websockets import WebSocket, WebSocketState

from chat_engine.common.client_handler_base import ClientHandlerBase, ClientSessionDelegate
from chat_engine.common.handler_base import HandlerDataInfo, HandlerDetail, HandlerBaseInfo
from chat_engine.contexts.handler_context import HandlerContext
from chat_engine.contexts.session_context import SessionContext
from chat_engine.data_models.chat_data.chat_data_model import ChatData
from chat_engine.data_models.chat_data_type import ChatDataType
from chat_engine.data_models.chat_engine_config_data import HandlerBaseConfigModel, ChatEngineConfigModel
from chat_engine.data_models.chat_stream_config import ChatStreamConfig
from chat_engine.data_models.chat_signal import ChatSignal
from chat_engine.data_models.engine_channel_type import EngineChannelType
from chat_engine.data_models.runtime_data.data_bundle import DataBundleDefinition, DataBundleEntry
from bwithu import feedback
from bwithu.gate import CLOSE_CALL_LIMIT, CLOSE_DAILY_LIMIT, gate
from engine_utils.directory_info import DirectoryInfo
from service.frontend_service import register_frontend

from handlers.client.ws_client.ws_input_delegate import WsInputSessionDelegate


# ============================================================================
# Config
# ============================================================================

class WsLamClientConfigModel(HandlerBaseConfigModel, BaseModel):
    """LAM handler config: asset path + WS heartbeat."""
    asset_path: Optional[str] = Field(default=None, description="LAM asset zip path")
    heartbeat_timeout: int = Field(default=30, description="WS heartbeat timeout (seconds)")


# ============================================================================
# Context
# ============================================================================

class WsLamClientContext(HandlerContext):
    def __init__(self, session_id: str):
        super().__init__(session_id)
        self.config: Optional[WsLamClientConfigModel] = None
        self.client_session_delegate: Optional[WsInputSessionDelegate] = None


# ============================================================================
# Handler
# ============================================================================

class WsLamClientHandler(ClientHandlerBase):
    """
    LAM Client Handler

      - Upstream (audio/text): /ws/session via ws_client protocol
      - Downstream (motion, audio, text, signals): same /ws/session connection

    Asset download: /download/lam_asset/{file_name}
    """

    asset_route: str = "/download/lam_asset"

    def __init__(self):
        super().__init__()
        self.engine_config: Optional[ChatEngineConfigModel] = None
        self.handler_config: Optional[WsLamClientConfigModel] = None
        self.output_bundle_definitions: Dict[EngineChannelType, DataBundleDefinition] = {}
        self.asset_dir: Optional[str] = None
        self.asset_name: Optional[str] = None

    # ------------------------------------------------------------------
    # Handler info
    # ------------------------------------------------------------------

    def get_handler_info(self) -> HandlerBaseInfo:
        return HandlerBaseInfo(
            config_model=WsLamClientConfigModel,
            client_session_delegate_class=WsInputSessionDelegate,
        )

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def load(self, engine_config: ChatEngineConfigModel,
             handler_config: Optional[HandlerBaseConfigModel] = None):
        self.engine_config = engine_config
        if handler_config is None or not isinstance(handler_config, WsLamClientConfigModel):
            handler_config = WsLamClientConfigModel()
        self.handler_config = handler_config
        self._prepare_ws_definitions()
        self._resolve_asset(handler_config)
        logger.info("WsLamClientHandler loaded")

    def _prepare_ws_definitions(self):
        """Prepare the data definitions of what the client sends in."""
        audio_def = DataBundleDefinition()
        audio_def.add_entry(DataBundleEntry.create_audio_entry("mic_audio", 1, 16000))
        audio_def.lockdown()
        self.output_bundle_definitions[EngineChannelType.AUDIO] = audio_def

        text_def = DataBundleDefinition()
        text_def.add_entry(DataBundleEntry.create_text_entry("human_text"))
        text_def.lockdown()
        self.output_bundle_definitions[EngineChannelType.TEXT] = text_def

    def _resolve_asset(self, handler_config: WsLamClientConfigModel):
        asset_path = handler_config.asset_path
        if not asset_path:
            raise ValueError("WsLamClient asset_path is required.")

        candidate_paths = []
        if os.path.isabs(asset_path):
            candidate_paths.append(asset_path)
        else:
            candidate_paths.append(os.path.abspath(asset_path))
            candidate_paths.append(os.path.join(self.handler_root, asset_path))
            candidate_paths.append(os.path.join(DirectoryInfo.get_project_dir(), asset_path))

        for path in candidate_paths:
            if os.path.isfile(path):
                self.asset_dir, self.asset_name = os.path.split(path)
                break

        if self.asset_dir is None or self.asset_name is None:
            raise ValueError(f"Asset file {asset_path} not found.")

    # ------------------------------------------------------------------
    # App setup: register WS endpoint + asset route + web app
    # ------------------------------------------------------------------

    def on_setup_app(self, app: FastAPI):
        self._register_ws_session_endpoint(app)
        self._register_asset_route(app)

        avatar_config = {
            "avatar_type": "lam",
            "avatar_assets_path": f"{self.asset_route}/{self.asset_name}",
            "ws_session_route": "/ws/session",
        }

        def init_config_provider():
            return {
                "chat_mode": "ws",
                "avatar_config": avatar_config,
                "ws_session_route": "/ws/session",
                "track_constraints": {
                    "audio": {
                        "sampleRate": 16000,
                        "channelCount": 1,
                        "autoGainControl": False,
                        "noiseSuppression": False,
                        "echoCancellation": True,
                    }
                },
            }
        register_frontend(app=app, init_config=init_config_provider)
        logger.info("WsLamClientHandler: WS + asset routes registered")

    def _register_ws_session_endpoint(self, app: FastAPI):
        @app.websocket("/ws/session/{session_id}")
        async def ws_session_endpoint(websocket: WebSocket, session_id: str):
            await websocket.accept()
            logger.info(f"Session WebSocket connected: session_id={session_id}")

            should_stop = False
            ticket = None
            try:
                session_delegate = self.handler_delegate.find_session_delegate(session_id)
                if session_delegate is None:
                    # BwithU: admission control (concurrency, free minutes, kill switch) for new calls.
                    ip = gate.client_ip(websocket.headers, websocket.client.host if websocket.client else None)
                    ticket, refuse_code = gate.admit(websocket.query_params.get("cid", ""), ip)
                    if ticket is None:
                        logger.info(f"Call refused with code {refuse_code}: session_id={session_id}")
                        await websocket.close(code=refuse_code)
                        return
                    logger.info(f"Creating new session: {session_id} (allowed {ticket.allowed_seconds}s)")
                    user_params = {k: v[:200] for k, v in list(websocket.query_params.items())[:10]}
                    session_delegate = self.handler_delegate.start_session(session_id, user_params=user_params)

                if not isinstance(session_delegate, WsInputSessionDelegate):
                    logger.error(f"Invalid session delegate type: {type(session_delegate)}")
                    await websocket.close(code=1003, reason="Invalid session")
                    return

                deadline = None
                if ticket is not None:
                    # Close with a code the web app understands; serve_websocket then ends on its own.
                    async def close_at_deadline(allowed=ticket.allowed_seconds):
                        await asyncio.sleep(allowed)
                        logger.info(f"Call time limit reached: session_id={session_id}")
                        await websocket.close(code=CLOSE_CALL_LIMIT if allowed >= gate.max_call_seconds
                                              else CLOSE_DAILY_LIMIT)
                    deadline = asyncio.create_task(close_at_deadline())
                try:
                    should_stop = await session_delegate.serve_websocket(websocket)
                finally:
                    if deadline is not None:
                        deadline.cancel()

            except WebSocketDisconnect:
                logger.info(f"Session WebSocket disconnected: session_id={session_id}")
            except Exception as e:
                logger.error(f"Error in session WebSocket: {e}")
            finally:
                if ticket is not None:
                    should_stop = True
                    gate.release(ticket)
                if should_stop:
                    try:
                        # BwithU: off the event loop, so a slow shutdown can't freeze every other request.
                        await asyncio.to_thread(self.handler_delegate.stop_session, session_id)
                        logger.info(f"Session stopped: {session_id}")
                    except Exception as e:
                        logger.error(f"Error stopping session: {e}")
                try:
                    if websocket.client_state != WebSocketState.DISCONNECTED:
                        await websocket.close()
                except Exception:
                    pass

        def is_admin(token: str) -> bool:
            expected = os.getenv("BWITHU_ADMIN_TOKEN", "")
            return bool(expected) and token == expected

        @app.get("/bwithu/stats")
        async def bwithu_stats(token: str = ""):
            if not is_admin(token):
                return JSONResponse(status_code=404, content={"detail": "Not Found"})
            return gate.stats()

        @app.post("/bwithu/feedback")
        async def bwithu_feedback_post(request: Request):
            try:
                body = await request.json()
            except Exception:
                return JSONResponse(status_code=400, content={"ok": False})
            ok = isinstance(body, dict) and feedback.save(body)
            return JSONResponse(status_code=200 if ok else 400, content={"ok": ok})

        @app.get("/bwithu/feedback")
        async def bwithu_feedback_get(token: str = ""):
            if not is_admin(token):
                return JSONResponse(status_code=404, content={"detail": "Not Found"})
            return feedback.latest()

    def _register_asset_route(self, app: FastAPI):
        asset_route = self.asset_route

        @app.get(asset_route + "/{file_name}")
        async def get_asset(file_name: str):
            if not re.match(r'^[a-zA-Z0-9._-]+$', file_name):
                logger.error(f"Invalid file name: {file_name}")
                return JSONResponse(status_code=400, content={"message": "Invalid file name"})

            if self.asset_dir is None:
                logger.error("LAM asset directory not resolved.")
                return JSONResponse(status_code=500, content={"message": "Asset directory unavailable"})

            file_path = os.path.join(self.asset_dir, file_name)
            if not os.path.commonprefix(
                    [os.path.abspath(file_path), os.path.abspath(self.asset_dir)]
            ) == os.path.abspath(self.asset_dir):
                logger.error(f"Path traversal attempt: {file_name}")
                return JSONResponse(status_code=403, content={"message": "Access denied"})

            if not os.path.isfile(file_path):
                logger.error(f"Failed to get lam asset file: {file_name}")
                return JSONResponse(status_code=404, content={"message": "File not found"})

            logger.info(f"Return lam asset file: {file_name}")
            return FileResponse(file_path)

    # ------------------------------------------------------------------
    # Context lifecycle
    # ------------------------------------------------------------------

    def create_context(self, session_context: SessionContext,
                       handler_config: Optional[HandlerBaseConfigModel] = None) -> HandlerContext:
        if not isinstance(handler_config, WsLamClientConfigModel):
            handler_config = WsLamClientConfigModel()
        context = WsLamClientContext(session_context.session_info.session_id)
        context.config = handler_config
        return context

    def start_context(self, session_context: SessionContext, handler_context: HandlerContext):
        pass

    def on_setup_session_delegate(self, session_context: SessionContext,
                                  handler_context: HandlerContext,
                                  session_delegate: ClientSessionDelegate):
        handler_context = cast(WsLamClientContext, handler_context)
        session_delegate = cast(WsInputSessionDelegate, session_delegate)

        session_delegate.clock = session_context.get_clock()
        session_delegate.data_submitter = handler_context.data_submitter
        session_delegate.input_data_definitions = self.output_bundle_definitions
        session_delegate.shared_states = session_context.shared_states
        handler_context.client_session_delegate = session_delegate

        session_delegate.session_id = session_context.session_info.session_id
        session_delegate.signal_emitter = handler_context.signal_emitter
        session_delegate.heartbeat_timeout = self.handler_config.heartbeat_timeout
        session_delegate.session_history = session_context.session_history
        session_delegate.stream_manager = handler_context.stream_manager

        logger.info(f"WsLam session delegate setup completed for session {session_context.session_info.session_id}")

    # ------------------------------------------------------------------
    # Handler detail: include AVATAR_MOTION_DATA input
    # ------------------------------------------------------------------

    def get_handler_detail(self, session_context: SessionContext,
                           context: HandlerContext) -> HandlerDetail:
        inputs = {
            data_type: HandlerDataInfo(type=data_type, input_priority=-1)
            for data_type in (ChatDataType.AVATAR_AUDIO, ChatDataType.AVATAR_TEXT, ChatDataType.HUMAN_TEXT,
                              ChatDataType.AVATAR_MOTION_DATA)
        }
        _no_link = ChatStreamConfig(cancelable=False, auto_link_input=False)
        outputs = {
            ChatDataType.MIC_AUDIO: HandlerDataInfo(
                type=ChatDataType.MIC_AUDIO,
                definition=self.output_bundle_definitions[EngineChannelType.AUDIO],
                output_stream_config=_no_link,
            ),
            ChatDataType.HUMAN_TEXT: HandlerDataInfo(
                type=ChatDataType.HUMAN_TEXT,
                definition=self.output_bundle_definitions[EngineChannelType.TEXT],
                output_stream_config=_no_link,
            ),
        }
        return HandlerDetail(inputs=inputs, outputs=outputs)

    # ------------------------------------------------------------------
    # Data routing: engine -> delegate output queues
    # ------------------------------------------------------------------

    def handle(self, context: HandlerContext, inputs: ChatData,
               output_definitions: Dict[ChatDataType, HandlerDataInfo]):
        context = cast(WsLamClientContext, context)
        delegate = context.client_session_delegate
        if delegate is None:
            return

        data_queue = delegate.output_queues.get(inputs.type.channel_type)
        if data_queue is not None:
            data_queue.put_nowait(inputs)
            logger.debug(f"Routed {inputs.type} to {inputs.type.channel_type} queue")

    # ------------------------------------------------------------------
    # Signal routing: engine -> delegate signal queue
    # ------------------------------------------------------------------

    def on_signal(self, context: HandlerContext, signal: ChatSignal):
        logger.info(f"Received signal: {signal.type} from {signal.source_type} on stream {signal.related_stream}")
        context = cast(WsLamClientContext, context)
        if context.client_session_delegate is None:
            return
        context.client_session_delegate.signal_to_client_queue.put_nowait(signal)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def destroy_context(self, context: HandlerContext):
        context = cast(WsLamClientContext, context)
        if context.client_session_delegate is not None:
            context.client_session_delegate.quit.set()
            context.client_session_delegate.clear_data()
        logger.info(f"Context destroyed for session {context.session_id}")
