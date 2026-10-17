"""Per-call companion personalization.

The browser opens /ws/session/{id}?name=...&user=...&vibe=...&voice=...; these values arrive here
as untrusted strings, so everything is length-limited and checked against allowlists before it
reaches a prompt.
"""
import re
from typing import Dict, List, Optional

DEFAULT_NAME = "Nova"

VIBES: Dict[str, str] = {
    "warm": "You are calm, caring and gently encouraging, like a close friend who really listens.",
    "playful": "You are upbeat, witty and a little cheeky, quick with a light joke but never mean.",
    "focused": "You are a calm, clear-headed coach who helps the user think, plan and get things done.",
}
DEFAULT_VIBE = "warm"

BASE_PROMPT = (
    "You are {name}, an AI companion on a live face-to-face video call with {user}. {vibe} "
    "You are an AI and say so honestly if asked, but you talk like a real person, never like an assistant. "
    "Keep every reply short and spoken: usually one or two sentences, never more than three. "
    "No lists, no markdown, no emoji, no stage directions. "
    "Ask a natural follow-up question now and then, remember what {user} told you earlier in the call, "
    "and reply in the language {user} speaks to you in. "
    "Never pretend to be in a romantic relationship, and gently steer away from medical, legal or "
    "financial advice beyond general information."
)

_SAFE_TEXT = re.compile(r"[^\w .'\-]", re.UNICODE)


def clean_name(value: Optional[str], fallback: str, max_len: int = 24) -> str:
    if not value:
        return fallback
    value = _SAFE_TEXT.sub("", value).strip()[:max_len].strip()
    return value or fallback


def build_instructions(params: Dict[str, str]) -> str:
    name = clean_name(params.get("name"), DEFAULT_NAME)
    user = clean_name(params.get("user"), "the user")
    vibe = VIBES.get(params.get("vibe", ""), VIBES[DEFAULT_VIBE])
    return BASE_PROMPT.format(name=name, user=user, vibe=vibe)


def pick_voice(params: Dict[str, str], allowed: List[str], default: str) -> str:
    voice = params.get("voice", "")
    return voice if voice in allowed else default
