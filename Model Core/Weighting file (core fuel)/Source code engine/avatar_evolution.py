"""墨灵分身系统 S4：自我进化（"新思路"的来源）。

两部分：
1. 自省回路（IntrospectionLoop）：定期回放工具痕迹与唤醒确认记录，
   本地复盘"做了什么、效果如何"，产出一条可验证的策略调整并应用；
   调整记录可追溯、可撤销（延续安全边界）。
2. 技能沉淀（SkillCardRegistry）：把已验证能力（K 系列渲染 / 立绘 /
   时间线，S 系列领域任务）封装成墨灵可调用的技能卡；技能卡可查询、
   可登记，并与分身任务绑定（被分身实际调用）。
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from time import time
from typing import Any
from uuid import uuid4


# ── 技能卡（K / S 系列已验证能力沉淀）────────────────────────────
DEFAULT_SKILL_CARDS: list[dict[str, Any]] = [
    {
        "id": "live2d_render",
        "name": "Live2D 渲染与演出",
        "description": "沐莹 Live2D 模型渲染、表情 / 口型 / 时间线演出（K3–K6 运行时）",
        "capability": "live2d_stage",
        "invoke": None,
        "source": "K6",
        "status": "available",
    },
    {
        "id": "portrait_draft",
        "name": "立绘草稿",
        "description": "本地 ComfyUI 生成一张立绘草稿（K1 特征管线）",
        "capability": "portrait",
        "invoke": "draw_portrait",
        "source": "K1",
        "status": "available",
    },
    {
        "id": "video_timeline",
        "name": "时间线演出合成",
        "description": "timeline 驱动帧输出与 mp4 合成（K6 三件套）",
        "capability": "video_script",
        "invoke": None,
        "source": "K6",
        "status": "available",
    },
    {
        "id": "document_retrieve",
        "name": "本地文档检索",
        "description": "本地目录关键词检索与要点归纳（学习分身）",
        "capability": "search",
        "invoke": "local_retrieve",
        "source": "S2",
        "status": "available",
    },
    {
        "id": "script_draft",
        "name": "演出脚本骨架",
        "description": "讲解 / 演出脚本模板生成（创作分身）",
        "capability": "writing",
        "invoke": "script_draft",
        "source": "S2",
        "status": "available",
    },
    {
        "id": "mood_echo",
        "name": "情绪回映",
        "description": "情绪识别与陪伴回映文案（陪伴分身）",
        "capability": "dialogue",
        "invoke": "mood_echo",
        "source": "S2",
        "status": "available",
    },
]

_REQUIRED_SKILL_FIELDS = ("id", "name", "description", "capability")


class SkillCardRegistry:
    """技能卡注册表：K / S 系列已验证能力，可查询、可登记。"""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()
        self._cards: dict[str, dict[str, Any]] = {}
        self._load_or_seed()

    def _load_or_seed(self) -> None:
        if self._path.is_file():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                for card in data.get("cards", []):
                    if isinstance(card, dict) and card.get("id"):
                        self._cards[str(card["id"])] = card
            except (OSError, ValueError, TypeError):
                self._cards = {}
        for template in DEFAULT_SKILL_CARDS:
            if template["id"] not in self._cards:
                self._cards[template["id"]] = dict(template)
        # 不在此落盘：仅实例化不写用户目录；登记 / 变更时才保存

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(
                {"version": 1, "cards": list(self._cards.values())},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(c) for c in self._cards.values()]

    def get(self, skill_id: str) -> dict[str, Any] | None:
        with self._lock:
            card = self._cards.get(skill_id)
            return dict(card) if card else None

    def register(self, card: dict[str, Any]) -> dict[str, Any]:
        """登记技能卡：必填字段校验 + id 唯一（配置而非硬编码）。"""
        if not isinstance(card, dict):
            raise ValueError("技能卡必须是对象")
        missing = [k for k in _REQUIRED_SKILL_FIELDS if not card.get(k)]
        if missing:
            raise ValueError(f"技能卡缺少必填字段: {', '.join(missing)}")
        skill_id = str(card["id"])
        if not skill_id.strip():
            raise ValueError("技能卡 id 不能为空")
        with self._lock:
            if skill_id in self._cards:
                raise ValueError(f"技能卡已存在: {skill_id}")
            normalized = {
                "id": skill_id,
                "name": str(card["name"]),
                "description": str(card.get("description", "")),
                "capability": str(card["capability"]),
                "invoke": card.get("invoke"),
                "source": str(card.get("source", "custom")),
                "status": "available",
                "created_at": time(),
            }
            self._cards[skill_id] = normalized
            self._save()
            return dict(normalized)

    def by_invoke(self, task: str) -> dict[str, Any] | None:
        """按分身任务名找技能卡（验证技能卡被分身实际调用）。"""
        with self._lock:
            for card in self._cards.values():
                if card.get("invoke") == task:
                    return dict(card)
        return None


# ── 自省回路 ────────────────────────────────────────────────────
_MIN_SAMPLE = 3  # 样本不足不调整（避免噪声）
_ASK_STEP = 20
_ASK_MIN_LOWER = 40
_ASK_MIN_UPPER = 160


class IntrospectionLoop:
    """回放工具痕迹 + 唤醒确认记录 → 统计 → 策略调整（可应用 / 可撤销）。"""

    def __init__(
        self,
        router: Any,
        tool_log: Any,
        awaken_log: Any,
        log_path: str | Path,
    ) -> None:
        self._router = router
        self._tool_log = tool_log
        self._awaken_log = awaken_log
        self._path = Path(log_path)
        self._lock = threading.Lock()
        self._entries: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        if self._path.is_file():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                self._entries = list(data.get("entries", []))[-200:]
            except (OSError, ValueError, TypeError):
                self._entries = []

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps({"entries": self._entries}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def run(self, apply: bool = False) -> dict[str, Any]:
        """回放最近记录，产出统计与策略调整；apply=True 时应用调整。"""
        with self._lock:
            tool_entries = self._tool_log.list(limit=100)
            wake_entries = self._awaken_log.list(limit=10)

        ok_count = sum(1 for e in tool_entries if e.get("result_status") == "ok")
        denied_count = sum(1 for e in tool_entries if e.get("decision") == "denied")
        failed_count = sum(
            1 for e in tool_entries if e.get("result_status") == "failed"
        )
        denied_reasons: dict[str, int] = {}
        for e in tool_entries:
            if e.get("decision") == "denied":
                reason = str(e.get("reason", "未知"))[:40]
                denied_reasons[reason] = denied_reasons.get(reason, 0) + 1

        wake_confirmed = sum(1 for e in wake_entries if e.get("confirmed"))
        wake_total = len(wake_entries)

        stats: dict[str, Any] = {
            "tool_total": len(tool_entries),
            "ok": ok_count,
            "denied": denied_count,
            "failed": failed_count,
            "denied_reasons": denied_reasons,
            "wake_total": wake_total,
            "wake_confirmed": wake_confirmed,
            "wake_ratio": round(wake_confirmed / wake_total, 2) if wake_total else 0.0,
        }

        proposed: list[dict[str, Any]] = []
        applied: list[dict[str, Any]] = []
        if wake_total >= _MIN_SAMPLE:
            ratio = stats["wake_ratio"]
            current = int(self._router.get_settings().get("ask_min_length", 80))
            if ratio >= 0.8 and current > _ASK_MIN_LOWER:
                new_value = max(current - _ASK_STEP, _ASK_MIN_LOWER)
                proposed.append(
                    {
                        "key": "ask_min_length",
                        "old": current,
                        "new": new_value,
                        "reason": f"唤醒确认率高（{ratio:.0%}），适当提前询问减少用户等待",
                    }
                )
            elif ratio <= 0.3 and current < _ASK_MIN_UPPER:
                new_value = min(current + _ASK_STEP, _ASK_MIN_UPPER)
                proposed.append(
                    {
                        "key": "ask_min_length",
                        "old": current,
                        "new": new_value,
                        "reason": f"唤醒确认率低（{ratio:.0%}），减少打扰",
                    }
                )
            if proposed and apply:
                adjustment = proposed[0]
                adjustment = {**adjustment, "id": make_adjustment_id()}
                self._router.update_settings(
                    {adjustment["key"]: adjustment["new"]}
                )
                applied.append(adjustment)

        entry = {
            "id": uuid4().hex[:12],
            "at": time(),
            "stats": stats,
            "proposed": proposed,
            "applied": applied,
        }
        with self._lock:
            self._entries.append(entry)
            if len(self._entries) > 200:
                self._entries = self._entries[-200:]
            self._save()

        return {
            "id": entry["id"],
            "stats": stats,
            "proposed": proposed,
            "applied": applied,
        }

    def revert(self, adjustment_id: str) -> dict[str, Any]:
        """撤销最近一次已应用的策略调整（恢复旧值，记录撤销）。"""
        with self._lock:
            for entry in reversed(self._entries):
                for adj in entry.get("applied", []):
                    if adj.get("id") == adjustment_id:
                        self._router.update_settings(
                            {adj["key"]: adj["old"]}
                        )
                        entry.setdefault("reverted", []).append(adjustment_id)
                        self._save()
                        return {
                            "status": "ok",
                            "reverted": adjustment_id,
                            "key": adj["key"],
                            "restored": adj["old"],
                        }
        return {"status": "not_found", "reverted": None}

    def list(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(e) for e in self._entries[-limit:]]


def make_adjustment_id() -> str:
    return uuid4().hex[:12]
