"""Post-call feedback, appended to temp/feedback.jsonl (one JSON object per line)."""
import json
import threading
import time
from pathlib import Path
from typing import List

_FILE = Path(__file__).resolve().parents[2] / "temp" / "feedback.jsonl"
_MAX_BYTES = 20 * 1024 * 1024
_lock = threading.Lock()


def save(payload: dict) -> bool:
    rating = payload.get("rating")
    if rating not in ("good", "bad"):
        return False
    entry = {
        "t": int(time.time()),
        "rating": rating,
        "text": str(payload.get("text") or "")[:1000],
        "seconds": int(payload.get("seconds") or 0),
        "avatar": str(payload.get("avatar") or "")[:32],
        "vibe": str(payload.get("vibe") or "")[:16],
        "voice": str(payload.get("voice") or "")[:16],
    }
    with _lock:
        _FILE.parent.mkdir(parents=True, exist_ok=True)
        if _FILE.exists() and _FILE.stat().st_size > _MAX_BYTES:
            return False
        with _FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return True


def latest(limit: int = 200) -> List[dict]:
    try:
        lines = _FILE.read_text(encoding="utf-8").splitlines()[-limit:]
    except OSError:
        return []
    return [json.loads(line) for line in reversed(lines) if line.strip()]
