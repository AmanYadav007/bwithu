"""Admission control for calls: concurrency cap, free daily minutes, kill switch.

State is in memory and snapshotted to a JSON file, which is enough for a single server.
All limits come from env vars so they can be changed without a code deploy:

  BWITHU_MAX_CALLS        simultaneous calls (default 10)
  BWITHU_DAILY_SECONDS    free talk time per user per UTC day (default 600)
  BWITHU_MAX_CALL_SECONDS hard cap for one call (default 600)
  BWITHU_IP_MULTIPLIER    an IP may use this many users' worth of time (default 10; mobile carriers
                          put many people behind one IP, e.g. Jio/Airtel CGNAT in India)
  BWITHU_PAUSED=1         or a file named PAUSED in the server dir: refuse new calls
  BWITHU_TRUST_PROXY=1    take the client IP from X-Forwarded-For (only behind our proxy)
"""
import json
import os
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from loguru import logger

# Close codes the web app understands (4000-4999 are free for applications).
CLOSE_BUSY = 4001
CLOSE_DAILY_LIMIT = 4002
CLOSE_PAUSED = 4003
CLOSE_CALL_LIMIT = 4004

_SERVER_DIR = Path(__file__).resolve().parents[2]
_STATE_FILE = _SERVER_DIR / "temp" / "usage.json"
_PAUSE_FILE = _SERVER_DIR / "PAUSED"
_ID_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


@dataclass
class Ticket:
    allowed_seconds: int
    keys: tuple
    started_at: float


class CallGate:
    def __init__(self):
        self._lock = threading.Lock()
        self._active = 0
        self._day = ""
        self._used: Dict[str, float] = {}
        self._dirty = False
        self._load()

    # -- config -------------------------------------------------------------
    @property
    def max_calls(self) -> int:
        return _env_int("BWITHU_MAX_CALLS", 10)

    @property
    def daily_seconds(self) -> int:
        return _env_int("BWITHU_DAILY_SECONDS", 600)

    @property
    def max_call_seconds(self) -> int:
        return _env_int("BWITHU_MAX_CALL_SECONDS", 600)

    @staticmethod
    def paused() -> bool:
        return os.getenv("BWITHU_PAUSED") == "1" or _PAUSE_FILE.exists()

    # -- admission ----------------------------------------------------------
    @staticmethod
    def client_ip(headers, peer: Optional[str]) -> str:
        if os.getenv("BWITHU_TRUST_PROXY") == "1":
            forwarded = headers.get("x-forwarded-for", "")
            if forwarded:
                return forwarded.split(",")[0].strip()
        return peer or "unknown"

    def admit(self, client_id: str, ip: str):
        """Returns (Ticket, None) or (None, close_code)."""
        if self.paused():
            return None, CLOSE_PAUSED
        cid = client_id if _ID_RE.match(client_id or "") else ""
        with self._lock:
            self._roll_day()
            if self._active >= self.max_calls:
                return None, CLOSE_BUSY
            ip_key = f"ip:{ip}"
            id_key = f"id:{cid}" if cid else None
            ip_left = self.daily_seconds * _env_int("BWITHU_IP_MULTIPLIER", 10) - self._used.get(ip_key, 0)
            id_left = self.daily_seconds - self._used.get(id_key, 0) if id_key else self.daily_seconds
            allowed = int(min(ip_left, id_left, self.max_call_seconds))
            if allowed < 15:
                return None, CLOSE_DAILY_LIMIT
            self._active += 1
            keys = (ip_key,) + ((id_key,) if id_key else ())
            return Ticket(allowed_seconds=allowed, keys=keys, started_at=time.time()), None

    def release(self, ticket: Ticket):
        seconds = max(0.0, time.time() - ticket.started_at)
        with self._lock:
            self._active = max(0, self._active - 1)
            self._roll_day()
            for key in ticket.keys:
                self._used[key] = self._used.get(key, 0) + seconds
            self._dirty = True
        self._save()
        logger.info(f"Call ended after {seconds:.0f}s; active calls: {self._active}")

    def stats(self) -> dict:
        with self._lock:
            return {"active_calls": self._active, "max_calls": self.max_calls, "paused": self.paused(),
                    "users_today": sum(1 for k in self._used if k.startswith("id:")),
                    "minutes_today": round(sum(v for k, v in self._used.items() if k.startswith("ip:")) / 60, 1)}

    # -- persistence --------------------------------------------------------
    def _roll_day(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != self._day:
            self._day, self._used, self._dirty = today, {}, True

    def _load(self):
        try:
            data = json.loads(_STATE_FILE.read_text())
            self._day, self._used = data.get("day", ""), data.get("used", {})
        except (OSError, ValueError):
            pass

    def _save(self):
        with self._lock:
            if not self._dirty:
                return
            payload = json.dumps({"day": self._day, "used": self._used})
            self._dirty = False
        try:
            _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = _STATE_FILE.with_suffix(".tmp")
            tmp.write_text(payload)
            tmp.replace(_STATE_FILE)
        except OSError as e:
            logger.warning(f"Could not save usage state: {e}")


gate = CallGate()
