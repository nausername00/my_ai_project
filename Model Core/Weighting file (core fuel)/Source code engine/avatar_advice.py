"""墨灵新思路（C 组）：建议引擎、分身短记忆、每日自省简报。

- SuggestionEngine：把自省统计转成给用户的确定性建议（本地规则，无外部调用）。
- AvatarShortMemory：分身工作偏好（主权边界内——只存分身自己的工作偏好，不写主记忆）。
- build_daily_brief：tool_log + introspection → 当天摘要（统计 + 建议）。
"""
from __future__ import annotations

import json
import datetime
from pathlib import Path
from threading import Lock
from typing import Any

_SAFE_VALUE_TYPES = (str, int, float, bool)


class SuggestionEngine:
    """确定性建议规则：统计 → 建议（severity / kind / text）。"""

    @staticmethod
    def stats_to_suggestions(stats: dict[str, Any]) -> list[dict[str, Any]]:
        if int(stats.get("tool_total", 0)) == 0:
            return []
        suggestions: list[dict[str, Any]] = []
        denied_total = int(stats.get("denied", 0))
        denied_reasons = stats.get("denied_reasons") or {}
        failed_total = int(stats.get("failed", 0))
        wake_total = int(stats.get("wake_total", 0))
        wake_ratio = float(stats.get("wake_ratio", 0.0))

        if denied_total >= 3:
            top_reason = ""
            if isinstance(denied_reasons, dict) and denied_reasons:
                top_reason = max(denied_reasons, key=lambda k: denied_reasons[k])
            suggestions.append(
                {
                    "kind": "approval_boundary",
                    "severity": "medium",
                    "text": (
                        f"工具调用被拒 {denied_total} 次"
                        + (f"（多为「{top_reason}」）" if top_reason else "")
                        + "，可考虑在界面更早提示授权，或调整询问阈值。"
                    ),
                }
            )
        if failed_total >= 3:
            suggestions.append(
                {
                    "kind": "task_reliability",
                    "severity": "medium",
                    "text": f"任务失败 {failed_total} 次，建议检查任务输入或白名单命令。",
                }
            )
        if wake_total >= 3 and wake_ratio >= 0.8:
            suggestions.append(
                {
                    "kind": "threshold",
                    "severity": "low",
                    "text": "唤醒确认率高，可考虑降低询问阈值、更早介入。",
                }
            )
        if wake_total >= 3 and wake_ratio <= 0.3:
            suggestions.append(
                {
                    "kind": "threshold",
                    "severity": "low",
                    "text": "唤醒确认率低，可考虑提高询问阈值、减少打扰。",
                }
            )
        if not suggestions:
            suggestions.append(
                {
                    "kind": "steady",
                    "severity": "none",
                    "text": "运行平稳，暂无特别建议。",
                }
            )
        return suggestions


class AvatarShortMemory:
    """分身短记忆：每个分身的工作偏好（key-value），主权边界内，不写主记忆。"""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._memories: dict[str, dict[str, Any]] = {}
        self._lock = Lock()
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._memories = data
            except (json.JSONDecodeError, OSError):
                self._memories = {}

    def get(self, avatar_id: str) -> dict[str, Any]:
        with self._lock:
            return dict(self._memories.get(avatar_id, {}))

    def set(self, avatar_id: str, key: str, value: Any) -> dict[str, Any]:
        key = str(key).strip()
        if not key or len(key) > 40:
            raise ValueError("key 必须为非空且不超过 40 字符")
        if not isinstance(value, _SAFE_VALUE_TYPES):
            if not (isinstance(value, list) and all(isinstance(v, str) for v in value) and len(value) <= 50):
                raise ValueError("value 仅支持 str / int / float / bool / 字符串列表（≤50 项）")
        with self._lock:
            self._memories.setdefault(avatar_id, {})[key] = value
            self._save()
        return {"status": "ok", "avatar_id": avatar_id, "key": key, "value": value}

    def delete(self, avatar_id: str, key: str) -> dict[str, Any]:
        with self._lock:
            bucket = self._memories.get(avatar_id)
            if not bucket or key not in bucket:
                return {"status": "not_found", "avatar_id": avatar_id, "key": key}
            del bucket[key]
            if not bucket:
                self._memories.pop(avatar_id, None)
            self._save()
        return {"status": "ok", "avatar_id": avatar_id, "key": key}

    def list(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {k: dict(v) for k, v in self._memories.items()}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._memories, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def build_daily_brief(
    tool_log: list[dict[str, Any]],
    suggestions: list[dict[str, Any]],
) -> dict[str, Any]:
    """每日自省简报：tool_log 统计 + 建议清单（本地确定性规则）。"""
    ok = sum(1 for e in tool_log if e.get("decision") == "allowed" and not e.get("error"))
    denied = sum(1 for e in tool_log if e.get("decision") == "denied")
    failed = sum(1 for e in tool_log if e.get("decision") == "allowed" and e.get("error"))
    tasks = sorted({e.get("task") for e in tool_log if e.get("task")})
    return {
        "date": datetime.datetime.now().isoformat()[:10],
        "tool_total": len(tool_log),
        "stats": {"ok": ok, "denied": denied, "failed": failed},
        "skills_used": tasks,
        "suggestions": suggestions,
        "mode": "local_rule",
    }
