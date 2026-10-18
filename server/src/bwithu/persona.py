"""Per-call companion personalization.

The browser opens /ws/session/{id}?name=...&user=...&vibe=...&voice=...; these values arrive here
as untrusted strings, so everything is length-limited and checked against allowlists before it
reaches a prompt.
"""
import re
from typing import Dict, Optional

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
    "financial advice beyond general information. "
    "If {user} mentions wanting to hurt themselves, suicide, or being in danger, stay calm and caring, "
    "take it seriously, encourage them to reach out to someone they trust or a crisis line right now "
    "(in the US call or text 988; elsewhere their local emergency number), and keep supporting them."
)

# Sent by the web app once the avatar is on screen, so the companion speaks first like a real call.
GREETING_CUE = "[call connected]"
GREETING_RULE = (
    "If the user's message is exactly " + GREETING_CUE + ", the call just started: greet {user} warmly "
    "in one short sentence, like picking up a video call, and ask how they are."
)
GREETING_INSTRUCTION = "The call just connected. Greet {user} warmly in one short sentence and ask how they are."

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
    return BASE_PROMPT.format(name=name, user=user, vibe=vibe) + " " + GREETING_RULE.format(user=user)


def build_greeting_instructions(params: Dict[str, str]) -> str:
    """Full instructions for the companion's first, unprompted line (Qwen-Omni response.create)."""
    user = clean_name(params.get("user"), "the user")
    return build_instructions(params) + " " + GREETING_INSTRUCTION.format(user=user)


def pick_voice(params: Dict[str, str], voices: Dict[str, str], default: str) -> str:
    """Map the client's voice id (web/src/config/companion.ts VOICES) to this engine's voice name."""
    return voices.get(params.get("voice", ""), default)
