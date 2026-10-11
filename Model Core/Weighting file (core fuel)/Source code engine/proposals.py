"""J5: bounded proactive proposals & shared goals.

Rules live here so they can be tested without a GUI or a background loop:
proposals are only checked *after* a chat reply is produced (no resident
timer), and only when the user has opted in.  Nothing here calls external
services or writes without consent.

Data model
----------
- settings: enabled(False), frequency_minutes(180), quiet_hours(list of
  {"start": "23:00", "end": "07:00"}), paused(False), last_proposed_at(iso).
- goals: user-owned shared goals; progress notes are only stored when the
  user consented to keeping them (consented=True).
- proposal memory: a small per-goal state so a declined / redirected topic is
  not re-proposed every reply.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
import json
from pathlib import Path
import re
import uuid
from typing import Any, Iterable

from utils import SingletonLock, utc_now_iso

__all__ = [
    "ProposalStore",
    "DEFAULT_SETTINGS",
    "is_within_quiet_hours",
    "GOAL_STATUSES",
]

GOAL_STATUSES = {"active", "paused", "completed", "ended"}

DEFAULT_SETTINGS: dict[str, Any] = {
    "enabled": False,
    "frequency_minutes": 180,
    "quiet_hours": [{"start": "23:00", "end": "07:00"}],
    "paused": False,
}

_MAX_TITLE = 200
_MAX_DESCRIPTION = 2000
_MAX_PROGRESS = 500


def _as_str(value: Any, field_name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    value = value.strip()
    if not value and not allow_empty:
        raise ValueError(f"{field_name} must not be empty")
    return value


def _as_bool(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a boolean")
    return value


def _parse_clock(text: Any, field_name: str) -> str:
    if not isinstance(text, str) or not re.fullmatch(r"\d{2}:\d{2}", text):
        raise ValueError(f"{field_name} must be HH:MM")
    hour, minute = (int(part) for part in text.split(":"))
    if hour > 23 or minute > 59:
        raise ValueError(f"{field_name} must be a valid HH:MM time")
    return f"{hour:02d}:{minute:02d}"


def is_within_quiet_hours(
    now: datetime, quiet_hours: Iterable[dict[str, str]] | None = None
) -> bool:
    """True when `now` falls inside any quiet window (windows may wrap midnight)."""
    current = now.time().replace(second=0, microsecond=0)
    for window in quiet_hours or []:
        try:
            start = time.fromisoformat(_parse_clock(window.get("start"), "start"))
            end = time.fromisoformat(_parse_clock(window.get("end"), "end"))
        except (ValueError, AttributeError):
            continue
        if start == end:
            continue
        if start < end:
            if start <= current < end:
                return True
        else:  # wraps midnight, e.g. 23:00 -> 07:00
            if current >= start or current < end:
                return True
    return False


@dataclass
class SharedGoal:
    id: str
    title: str
    description: str
    status: str = "active"
    created_at: str = ""
    progress_note: str = ""
    consented: bool = True  # progress persisted only when the user agreed

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "created_at": self.created_at,
            "progress_note": self.progress_note,
            "consented": self.consented,
        }

    @classmethod
    def from_dict(cls, payload: Any) -> "SharedGoal":
        if not isinstance(payload, dict):
            raise TypeError("goal must be a dict")
        title = _as_str(payload.get("title"), "title")
        if len(title) > _MAX_TITLE:
            raise ValueError(f"title must not exceed {_MAX_TITLE} characters")
        description = _as_str(payload.get("description", ""), "description", allow_empty=True)
        if len(description) > _MAX_DESCRIPTION:
            raise ValueError(f"description must not exceed {_MAX_DESCRIPTION} characters")
        status = payload.get("status", "active")
        if status not in GOAL_STATUSES:
            raise ValueError("status must be active/paused/completed/ended")
        goal_id = payload.get("id")
        if goal_id is None:
            goal_id = uuid.uuid4().hex
        elif not isinstance(goal_id, str) or not goal_id.strip():
            raise ValueError("id must be a non-empty string when provided")
        created_at = payload.get("created_at") or utc_now_iso()
        progress_note = payload.get("progress_note", "")
        if not isinstance(progress_note, str):
            raise ValueError("progress_note must be a string")
        progress_note = progress_note.strip()[: _MAX_PROGRESS]
        consented = payload.get("consented", True)
        if not isinstance(consented, bool):
            raise ValueError("consented must be a boolean")
        return cls(
            id=str(goal_id).strip(),
            title=title,
            description=description,
            status=status,
            created_at=str(created_at).strip() or utc_now_iso(),
            progress_note=progress_note,
            consented=consented,
        )


class ProposalStore:
    """JSON-backed store for proposal settings, shared goals and per-goal
    proposal state.  All mutations are serialised via SingletonLock."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = SingletonLock()
        self._settings: dict[str, Any] = dict(DEFAULT_SETTINGS)
        self._goals: dict[str, SharedGoal] = {}
        self._last_action_at: dict[str, str] = {}  # goal_id -> iso of last decline/later
        self._dirty = False
        self._load()

    # ---------- persistence ----------
    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot read proposal store: {exc}") from exc
        if not isinstance(raw, dict):
            raise ValueError("proposal store must contain a JSON object")
        settings = raw.get("settings")
        if isinstance(settings, dict):
            merged = dict(DEFAULT_SETTINGS)
            for key in ("enabled", "frequency_minutes", "paused"):
                if key in settings:
                    merged[key] = settings[key]
            if "quiet_hours" in settings and isinstance(settings["quiet_hours"], list):
                merged["quiet_hours"] = [
                    {
                        "start": _parse_clock(q.get("start"), "quiet start"),
                        "end": _parse_clock(q.get("end"), "quiet end"),
                    }
                    for q in settings["quiet_hours"]
                    if isinstance(q, dict)
                ]
            if "last_proposed_at" in settings:
                merged["last_proposed_at"] = settings["last_proposed_at"]
            self._settings = merged
        goals = raw.get("goals")
        if isinstance(goals, list):
            for index, item in enumerate(goals):
                try:
                    goal = SharedGoal.from_dict(item)
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"invalid shared goal #{index}: {exc}") from exc
                self._goals[goal.id] = goal
        actions = raw.get("last_action_at")
        if isinstance(actions, dict):
            self._last_action_at = {
                str(k): str(v) for k, v in actions.items() if isinstance(v, str)
            }

    def save(self) -> None:
        if not self._dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "settings": self._settings,
            "goals": [g.to_dict() for g in self._goals.values()],
            "last_action_at": self._last_action_at,
        }
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        tmp.replace(self.path)
        self._dirty = False

    # ---------- settings ----------
    def get_settings(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._settings)

    def update_settings(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise TypeError("settings must be a dict")
        with self._lock:
            current = dict(self._settings)
            if "enabled" in payload:
                current["enabled"] = _as_bool(payload["enabled"], "enabled")
            if "frequency_minutes" in payload:
                freq = payload["frequency_minutes"]
                if not isinstance(freq, int) or freq < 5 or freq > 10080:
                    raise ValueError("frequency_minutes must be between 5 and 10080")
                current["frequency_minutes"] = freq
            if "paused" in payload:
                current["paused"] = _as_bool(payload["paused"], "paused")
            if "quiet_hours" in payload:
                hours = payload["quiet_hours"]
                if not isinstance(hours, list) or len(hours) > 8:
                    raise ValueError("quiet_hours must be a list of at most 8 windows")
                current["quiet_hours"] = [
                    {
                        "start": _parse_clock(q.get("start"), "quiet start"),
                        "end": _parse_clock(q.get("end"), "quiet end"),
                    }
                    for q in hours
                    if isinstance(q, dict)
                ]
            self._settings = current
            self._dirty = True
            return dict(self._settings)

    def set_last_proposed(self, iso: str) -> None:
        with self._lock:
            self._settings["last_proposed_at"] = iso
            self._dirty = True

    # ---------- goals ----------
    def list_goals(self) -> list[dict[str, Any]]:
        with self._lock:
            goals = sorted(
                self._goals.values(),
                key=lambda g: (g.created_at, g.id),
                reverse=True,
            )
            return [g.to_dict() for g in goals]

    def add_goal(self, title: str, description: str = "", consented: bool = True) -> dict[str, Any]:
        with self._lock:
            goal = SharedGoal.from_dict(
                {
                    "title": title,
                    "description": description,
                    "status": "active",
                    "consented": consented,
                }
            )
            self._goals[goal.id] = goal
            self._dirty = True
            return goal.to_dict()

    def update_goal(self, goal_id: str, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise TypeError("goal update must be a dict")
        with self._lock:
            goal = self._goals.get(goal_id)
            if goal is None:
                raise LookupError(f"goal not found: {goal_id}")
            merged = goal.to_dict()
            if "title" in payload:
                merged["title"] = _as_str(payload["title"], "title")[:_MAX_TITLE]
            if "description" in payload:
                merged["description"] = _as_str(
                    payload["description"], "description", allow_empty=True
                )[:_MAX_DESCRIPTION]
            if "status" in payload:
                status = payload["status"]
                if status not in GOAL_STATUSES:
                    raise ValueError("status must be active/paused/completed/ended")
                merged["status"] = status
            if "progress_note" in payload:
                note = payload["progress_note"]
                if not isinstance(note, str):
                    raise ValueError("progress_note must be a string")
                # 只保存用户同意保留的进展
                merged["progress_note"] = note.strip()[:_MAX_PROGRESS] if goal.consented else ""
            if "consented" in payload:
                merged["consented"] = _as_bool(payload["consented"], "consented")
            updated = SharedGoal.from_dict(merged)
            self._goals[updated.id] = updated
            self._dirty = True
            return updated.to_dict()

    def delete_goal(self, goal_id: str) -> None:
        with self._lock:
            if goal_id not in self._goals:
                raise LookupError(f"goal not found: {goal_id}")
            del self._goals[goal_id]
            self._last_action_at.pop(goal_id, None)
            self._dirty = True

    # ---------- proposal decision (pure rules, no background loop) ----------
    def pending_proposal(
        self,
        candidates: Iterable[dict[str, Any]] | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Called after a chat reply.  Returns one proposal card or None.

        Boundaries enforced here: opt-in only, paused halts everything,
        frequency gate, quiet hours, and a goal already declined/redirected
        is not re-proposed until 6 hours later.
        """
        now = now or datetime.now().astimezone()
        with self._lock:
            settings = dict(self._settings)
            if not settings["enabled"] or settings["paused"]:
                return None
            if is_within_quiet_hours(now, settings["quiet_hours"]):
                return None
            last = settings.get("last_proposed_at")
            if last:
                try:
                    last_dt = datetime.fromisoformat(last)
                    if (now - last_dt).total_seconds() < settings["frequency_minutes"] * 60:
                        return None
                except ValueError:
                    pass
            # 候选默认来自共享目标库（用户创建/确认过的共同目标）。
            if candidates is None:
                goal_pool = [goal for goal in self._goals.values()]
            else:
                goal_pool = []
                for candidate in candidates:
                    if not isinstance(candidate, dict):
                        continue
                    goal_id = candidate.get("id")
                    if not isinstance(goal_id, str) or goal_id not in self._goals:
                        continue
                    goal_pool.append(self._goals[goal_id])
            for goal in goal_pool:
                if goal.status not in {"active", "paused"}:
                    continue
                action_at = self._last_action_at.get(goal.id)
                if action_at:
                    try:
                        if (now - datetime.fromisoformat(action_at)).total_seconds() < 6 * 3600:
                            continue
                    except ValueError:
                        pass
                return {
                    "goal_id": goal.id,
                    "title": goal.title,
                    "description": goal.description,
                    "basis": "来自你确认的共同目标" if goal.consented else "来自对话线索（未经确认，仅提议）",
                }
            return None

    def respond(self, goal_id: str, action: str) -> dict[str, Any]:
        """accept / redirect / later / decline / stop.

        - accept: goal becomes active (user confirmed), proposal clock resets.
        - redirect: pause the goal until the user edits it; no re-proposal.
        - later:   same goal may be proposed again after the cooldown.
        - decline: mark last action; goal stays paused for re-proposal cooldown.
        - stop:    pause all proposals (settings.paused = True).
        """
        if action not in {"accept", "redirect", "later", "decline", "stop"}:
            raise ValueError("action must be accept/redirect/later/decline/stop")
        with self._lock:
            if action == "stop":
                self._settings["paused"] = True
                self._dirty = True
                return {
                    "action": action,
                    "paused": True,
                    "message": "主动提议已暂停；可在设置中恢复。",
                }
            goal = self._goals.get(goal_id)
            if goal is None:
                raise LookupError(f"goal not found: {goal_id}")
            if action == "accept":
                goal.status = "active"
                goal.consented = True
                self._settings["last_proposed_at"] = utc_now_iso()
            elif action == "redirect":
                goal.status = "paused"
                goal.consented = False
                self._last_action_at[goal.id] = utc_now_iso()
            elif action in {"later", "decline"}:
                self._last_action_at[goal.id] = utc_now_iso()
            self._dirty = True
            return {
                "action": action,
                "goal": goal.to_dict(),
                "message": {
                    "accept": "已确认目标并继续推进。",
                    "redirect": "目标已暂停，等你改方向后恢复。",
                    "later": "稍后再提醒你。",
                    "decline": "已记下，暂时不再提议。",
                }[action],
            }
