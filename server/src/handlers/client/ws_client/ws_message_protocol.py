"""
WebSocket message protocol
Pydantic models for every JSON message
"""
import time
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from enum import Enum
from loguru import logger


# ============================================================================
# Base structures
# ============================================================================

class MessageType(str, Enum):
    """Message types"""
    # Input port - client messages
    INITIALIZE_AVATAR_SESSION = "InitializeAvatarSession"
    SEND_HUMAN_AUDIO = "SendHumanAudio"
    SEND_HUMAN_TEXT = "SendHumanText"
    TRIGGER_HEARTBEAT = "TriggerHeartbeat"
    INTERRUPT = "Interrupt"
    
    # Input port - server messages
    AVATAR_SESSION_INITIALIZED = "AvatarSessionInitialized"
    ECHO_HUMAN_TEXT = "EchoHumanText"
    ECHO_AVATAR_TEXT = "EchoAvatarText"
    ECHO_AVATAR_AUDIO = "EchoAvatarAudio"
    AVATAR_HEARTBEAT = "AvatarHeartbeat"
    INTERRUPT_ACCEPTED = "InterruptAccepted"
    INTERRUPT_NOTIFICATION = "InterruptNotification"  # Server-initiated interrupt (for non-MotionData mode)
    CHAT_SIGNAL = "ChatSignal"
    ERROR = "Error"
    
    # Output port - server messages
    MOTION_DATA = "MotionData"
    MOTION_DATA_WELCOME = "MotionDataWelcome"
    
    # Input port - renderer messages
    END_SPEECH = "EndSpeech"

class MessageHeader(BaseModel):
    """Message header"""
    name: MessageType
    request_id: str = Field(..., description="Request ID")


class BaseMessage(BaseModel):
    """Base message"""
    header: MessageHeader
    payload: Optional[Dict[str, Any]] = Field(default=None)


# ============================================================================
# Input port - client -> server messages
# ============================================================================

class AudioConfig(BaseModel):
    """Audio config"""
    format: str = Field(default="PCM", description="Audio format (only PCM)")
    sample_rate: int = Field(default=16000, description="Sample rate")
    channels: int = Field(default=1, description="Channel count")


class InitializeAvatarSessionPayload(BaseModel):
    """InitializeAvatarSession payload"""
    audio: AudioConfig
    subscriptions: Optional[List[str]] = Field(default=None, description="Downstream content to subscribe to")


class InitializeAvatarSession(BaseModel):
    """Initialize the avatar session"""
    header: MessageHeader
    payload: InitializeAvatarSessionPayload


class BinaryDataInfo(BaseModel):
    """Binary data info"""
    binary_size: int = Field(..., description="Total binary size")
    segment_num: int = Field(..., description="Number of segments")


class SendHumanAudioPayload(BaseModel):
    """SendHumanAudio payload"""
    transport: str = Field(default="binary", description="Transport: binary/base64")
    binary_size: Optional[int] = Field(default=None, description="Total binary size (binary transport)")
    segment_num: Optional[int] = Field(default=None, description="Number of binary frames (binary transport)")
    data_base64: Optional[str] = Field(default=None, description="base64 data")


class SendHumanAudio(BaseModel):
    """User audio"""
    header: MessageHeader
    payload: SendHumanAudioPayload


class SendHumanTextPayload(BaseModel):
    """SendHumanText payload"""
    stream_key: str = Field(..., description="Unique stream key: stream_{builder_id}_{stream_id}")
    mode: str = Field(default="increment", description="Text mode: increment/full_text")
    text: str = Field(..., description="Text")
    end_of_speech: bool = Field(..., description="Is this the end?")


class SendHumanText(BaseModel):
    """User text"""
    header: MessageHeader
    payload: SendHumanTextPayload


class TriggerHeartbeat(BaseModel):
    """Heartbeat"""
    header: MessageHeader


class Interrupt(BaseModel):
    """Interrupt"""
    header: MessageHeader


# ============================================================================
# Input port - server -> client messages
# ============================================================================

class AvatarSessionInitialized(BaseModel):
    """Session initialized"""
    header: MessageHeader


class EchoTextPayload(BaseModel):
    """Text echo payload"""
    stream_key: Optional[str] = Field(default=None, description="Unique stream key: stream_{builder_id}_{stream_id}")
    mode: str = Field(default="increment", description="Text mode: increment/full_text")
    text: str = Field(..., description="Text")
    end_of_speech: bool = Field(..., description="Is this the end?")
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Extra metadata added by handlers (e.g. task_id)"
    )


class EchoHumanText(BaseModel):
    """Echo of the user's text (ASR result)"""
    header: MessageHeader
    payload: EchoTextPayload


class EchoAvatarText(BaseModel):
    """Echo of the avatar's text (LLM result)"""
    header: MessageHeader
    payload: EchoTextPayload


class EchoAvatarAudioPayload(BaseModel):
    """Avatar audio payload"""
    stream_key: Optional[str] = Field(default=None, description="Unique stream key: stream_{builder_id}_{stream_id}")
    transport: str = Field(default="binary", description="Transport: binary/base64")
    binary_size: Optional[int] = Field(default=None, description="Total binary size (binary transport)")
    segment_num: Optional[int] = Field(default=None, description="Number of binary frames (binary transport)")
    format: str = Field(default="PCM", description="Audio format (only PCM)")
    sample_rate: int = Field(default=24000, description="Audio sample rate")
    channels: int = Field(default=1, description="Audio channel count")
    data_base64: Optional[str] = Field(default=None, description="base64 data")
    end_of_speech: bool = Field(default=False, description="Is this the end of the audio segment?")
    
    # Extra metadata (e.g. task_id)
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Extra metadata added by handlers (e.g. task_id)"
    )


class EchoAvatarAudio(BaseModel):
    """Avatar audio (TTS result)"""
    header: MessageHeader
    payload: EchoAvatarAudioPayload


class AvatarHeartbeat(BaseModel):
    """Heartbeat response"""
    header: MessageHeader


class InterruptAcceptedPayload(BaseModel):
    """InterruptAccepted payload"""
    target_stream_id: Optional[str] = Field(default=None, description="ID of the interrupted AVATAR_AUDIO stream")
    stream_key: Optional[str] = Field(default=None, description="Unique stream key: stream_{builder_id}_{stream_id}")


class InterruptAccepted(BaseModel):
    """Interrupt accepted"""
    header: MessageHeader
    payload: Optional[InterruptAcceptedPayload] = Field(default=None)


class InterruptNotificationPayload(BaseModel):
    """Server-side interrupt notification payload (when there is no motion data)"""
    target_stream_id: str = Field(..., description="ID of the interrupted AVATAR_AUDIO stream (deprecated: use stream_key)")
    stream_key: Optional[str] = Field(default=None, description="Unique stream key: stream_{builder_id}_{stream_id}")
    reason: str = Field(default="user_interrupt", description="Reason: user_interrupt | semantic_interrupt")
    interrupted_at: float = Field(default_factory=time.time, description="Interrupt timestamp")


class InterruptNotification(BaseModel):
    """Server-side interrupt notification (when there is no motion data)"""
    header: MessageHeader
    payload: InterruptNotificationPayload


class ChatSignalPayload(BaseModel):
    timestamp: float = Field(default_factory=time.time)
    type: str
    source_type: str
    stream_type: Optional[str] = Field(default=None, description="Stream type")
    stream_producer: Optional[str] = Field(default=None, description="Stream producer")
    stream_key: Optional[str] = Field(default=None, description="Unique stream key: stream_{builder_id}_{stream_id}")
    parent_stream_keys: Optional[List[str]] = Field(default=None, description="stream_keys of the direct parent streams (STREAM_BEGIN only; no grandparents)")
    signal_data: Optional[Dict] = Field(default=None, description="Signal data")


class ChatSignalMessage(BaseModel):
    """A signal forwarded to the client"""
    header: MessageHeader
    payload: ChatSignalPayload



class ErrorCode(str, Enum):
    """Error codes"""
    INVALID_SESSION = "INVALID_SESSION"
    AUDIO_FORMAT_ERROR = "AUDIO_FORMAT_ERROR"
    HEARTBEAT_TIMEOUT = "HEARTBEAT_TIMEOUT"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    RATE_LIMIT = "RATE_LIMIT"
    INVALID_MESSAGE = "INVALID_MESSAGE"
    BINARY_DATA_ERROR = "BINARY_DATA_ERROR"


class ErrorPayload(BaseModel):
    """Error payload"""
    code: str = Field(..., description="Error code")
    message: str = Field(..., description="Error message")


class Error(BaseModel):
    """Error"""
    header: MessageHeader
    payload: ErrorPayload


# ============================================================================
# Output port - server -> renderer messages
# ============================================================================

class MotionDataPayload(BaseModel):
    """Motion data payload"""
    stream_key: Optional[str] = Field(default=None, description="Unique stream key: stream_{builder_id}_{stream_id}")
    motion_data: BinaryDataInfo
    end_of_speech: bool = Field(..., description="Is this the end?")


class MotionDataMessage(BaseModel):
    """Motion data"""
    header: MessageHeader
    payload: MotionDataPayload


# ============================================================================
# Input port - renderer -> server messages
# ============================================================================

class EndSpeechPayload(BaseModel):
    """EndSpeech payload"""
    stream_key: str = Field(..., description="Unique stream key: stream_{builder_id}_{stream_id}")


class EndSpeech(BaseModel):
    """The renderer finished playing"""
    header: MessageHeader
    payload: EndSpeechPayload


# ============================================================================
# Helpers
# ============================================================================

def parse_message(json_data: dict) -> Optional[BaseMessage]:
    """
    Parse a JSON message
    
    Args:
        json_data: JSON dict
        
    Returns:
        The parsed message, or None if parsing fails
    """
    try:
        if "header" not in json_data:
            logger.warning("JSON message has no header")
            return None
        
        message_name = json_data["header"].get("name")
        if not message_name:
            logger.warning("JSON message header has no name")
            return None
        
        # Look the message type up in the enum
        try:
            message_type = MessageType(message_name)
        except ValueError:
            logger.warning(f"Unknown message type: {message_name}")
            return None
        
        # Get the class for the message type
        message_class_map = {
            MessageType.INITIALIZE_AVATAR_SESSION: InitializeAvatarSession,
            MessageType.SEND_HUMAN_AUDIO: SendHumanAudio,
            MessageType.SEND_HUMAN_TEXT: SendHumanText,
            MessageType.TRIGGER_HEARTBEAT: TriggerHeartbeat,
            MessageType.INTERRUPT: Interrupt,
            MessageType.AVATAR_SESSION_INITIALIZED: AvatarSessionInitialized,
            MessageType.ECHO_HUMAN_TEXT: EchoHumanText,
            MessageType.ECHO_AVATAR_TEXT: EchoAvatarText,
            MessageType.ECHO_AVATAR_AUDIO: EchoAvatarAudio,
            MessageType.AVATAR_HEARTBEAT: AvatarHeartbeat,
            MessageType.INTERRUPT_ACCEPTED: InterruptAccepted,
            MessageType.ERROR: Error,
            MessageType.MOTION_DATA: MotionDataMessage,
            MessageType.MOTION_DATA_WELCOME: MotionDataMessage,
            MessageType.END_SPEECH: EndSpeech,
        }
        
        message_class = message_class_map.get(message_type)
        if message_class is None:
            logger.error(f"No class for message type {message_type}")
            return None
        
        return message_class.model_validate(json_data)
    except Exception as e:
        logger.error(f"Error parsing JSON message: {e}", exc_info=True)
        return None


def serialize_message(message: BaseMessage) -> dict:
    """
    Serialize a message to a JSON dict
    
    Args:
        message: the message
        
    Returns:
        JSON dict
    """
    return message.model_dump(exclude_none=True)

