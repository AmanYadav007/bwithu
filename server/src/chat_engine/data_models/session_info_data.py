import asyncio
import queue
from typing import Union

from pydantic import BaseModel, Field

IOQueueType = Union[queue.Queue, asyncio.Queue]

class SessionInfoData(BaseModel):
    session_id: str
    timestamp_base: int = Field(default=16000)
    # BwithU: untrusted per-call options from the client (companion name, voice, ...).
    user_params: dict = Field(default_factory=dict)
