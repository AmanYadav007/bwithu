from collections import namedtuple
from typing import Optional, Dict

from pydantic import BaseModel, Field

from chat_engine.data_models.chat_signal_type import ChatSignalType, ChatSignalSourceType
from chat_engine.data_models.chat_stream import ChatStreamIdentity


SignalFilterRule = namedtuple("SignalFilter",
                              ["signal_type", "source_type", "stream_type"],
                              defaults=[None, None, None])


class ChatSignal(BaseModel):
    type: Optional[ChatSignalType] = Field(default=None)
    source_type: Optional[ChatSignalSourceType] = Field(default=None)
    related_stream: Optional[ChatStreamIdentity] = Field(default=None)
    signal_data: Optional[Dict] = Field(default=None)
    source_name: Optional[str] = Field(default=None)

    @property
    def is_candidate(self) -> bool:
        """
        Is this a candidate (advisory) signal?
        It is one if it does not come from the stream's owner;
        the owner may choose whether to follow it.
        """
        if self.related_stream is None or self.source_name is None:
            return True  # owner unknown: treat as a candidate
        return self.source_name != self.related_stream.producer_name
