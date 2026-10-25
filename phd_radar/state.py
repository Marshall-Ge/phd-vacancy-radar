"""状态持久化。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .timeutil import iso, parse_dt

MAX_SEEN = 1200


@dataclass
class State:
    version: int = 1
    created_at: datetime | None = None
    last_check_at: datetime | None = None
    last_success_at: datetime | None = None
    last_digest_at: datetime | None = None
    last_alert_at: dict[str, datetime | None] = field(default_factory=dict)
    stats: dict[str, int] = field(default_factory=lambda: {"runs": 0, "digests": 0, "alerts": 0, "failures": 0})
    seen_positions: dict[str, str] = field(default_factory=dict)
    seen_awards: dict[str, str] = field(default_factory=dict)
    alerted: dict[str, str] = field(default_factory=dict)
    first_run_done: bool = False
    last_snapshot: dict[str, Any] = field(default_factory=dict)

    def remember(self, kind: str, key: str, when: datetime) -> bool:
        bucket = self.seen_positions if kind == "position" else self.seen_awards
        if key in bucket:
            return False
        bucket[key] = iso(when) or ""
        if len(bucket) > MAX_SEEN:
            items = sorted(bucket.items(), key=lambda kv: kv[1])
            trimmed = dict(items[-MAX_SEEN:])
            if kind == "position":
                self.seen_positions = trimmed
            else:
                self.seen_awards = trimmed
        return True

    def mark_alert(self, kind: str, when: datetime) -> None:
        self.last_alert_at[kind] = when
        self.stats["alerts"] = self.stats.get("alerts", 0) + 1

    def last_alert(self, kind: str) -> datetime | None:
        return self.last_alert_at.get(kind)

    def first_seen(self, kind: str, key: str) -> datetime | None:
        bucket = self.seen_positions if kind == "position" else self.seen_awards
        return parse_dt(bucket.get(key))

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "created_at": iso(self.created_at),
            "last_check_at": iso(self.last_check_at),
            "last_success_at": iso(self.last_success_at),
            "last_digest_at": iso(self.last_digest_at),
            "last_alert_at": {k: iso(v) for k, v in self.last_alert_at.items()},
            "stats": self.stats,
            "seen_positions": self.seen_positions,
            "seen_awards": self.seen_awards,
            "alerted": self.alerted,
            "first_run_done": self.first_run_done,
            "last_snapshot": self.last_snapshot,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "State":
        state = cls()
        state.created_at = parse_dt(raw.get("created_at"))
        state.last_check_at = parse_dt(raw.get("last_check_at"))
        state.last_success_at = parse_dt(raw.get("last_success_at"))
        state.last_digest_at = parse_dt(raw.get("last_digest_at"))
        state.last_alert_at = {k: parse_dt(v) for k, v in (raw.get("last_alert_at") or {}).items()}
        state.stats = {k: int(v) for k, v in (raw.get("stats") or {}).items()}
        for key in ("runs", "digests", "alerts", "failures"):
            state.stats.setdefault(key, 0)
        state.seen_positions = dict(raw.get("seen_positions") or {})
        state.seen_awards = dict(raw.get("seen_awards") or {})
        state.alerted = dict(raw.get("alerted") or {})
        state.first_run_done = bool(raw.get("first_run_done", False))
        state.last_snapshot = dict(raw.get("last_snapshot") or {})
        return state


def load_state(path: Path) -> tuple[State, bool]:
    if not path.exists():
        return State(), True
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return State.from_dict(raw), False
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return State(), True


def save_state(path: Path, state: State) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
