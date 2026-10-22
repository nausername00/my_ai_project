"""M6 · 双端同步：图鉴收集 + 互动计数（电脑/手机共享的权威存储）。

手机端养成的图鉴（collected 时装 id 列表）与互动计数（interact_bonus）
以本模块为双端权威状态；手机端启动/变化时与后端合并（并集 + 取大），
换手机/重装不丢，电脑端换装历史也可反哺手机图鉴。

设计意图：
- 摸头计数权威在后端 m5_headpat.headpat_state.json（/v1/generate 已累计）；
  本模块把图鉴 + 互动计数补上，一次 GET 返回完整养成画像。
- 合并规则：collected 取并集；interact_bonus 取 max；不删除任何已收集项。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from m_studio.lock_utils import FileLock

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(HERE, "collection_state.json")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_state() -> dict[str, Any]:
    if not os.path.isfile(STATE_PATH):
        return {"collected": [], "interact_bonus": 0, "updated_at": ""}
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {"collected": [], "interact_bonus": 0, "updated_at": ""}
    if not isinstance(data, dict):
        return {"collected": [], "interact_bonus": 0, "updated_at": ""}
    collected = data.get("collected", [])
    if not isinstance(collected, list):
        collected = []
    bonus = data.get("interact_bonus", 0)
    if not isinstance(bonus, (int, float)):
        bonus = 0
    return {
        "collected": [str(c) for c in collected if isinstance(c, str)],
        "interact_bonus": int(bonus),
        "updated_at": str(data.get("updated_at", "")),
    }


def _save_state(state: dict[str, Any]) -> None:
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_PATH)


def get_collection() -> dict[str, Any]:
    """读取当前养成画像（含摸头计数，方便一次拉齐）。"""
    from m_studio.m5_headpat import _load_state as _load_headpat

    with FileLock(STATE_PATH):
        state = _load_state()
    hp = _load_headpat()
    return {
        "collected": list(state["collected"]),
        "interact_bonus": state["interact_bonus"],
        "headpat_count": int(hp.get("count", 0)),
        "updated_at": state["updated_at"],
    }


def merge_collection(
    collected: Any, interact_bonus: Any, headpat_count: Any = None
) -> dict[str, Any]:
    """合并客户端上报状态：collected 并集、interact_bonus 取大；写回并返回合并结果。

    headpat_count 仅供返回展示，摸头计数权威仍由 /v1/generate 维护，
    此处不写 headpat 状态，避免与 m5_headpat 双写冲突。
    """
    if not isinstance(collected, list):
        collected = []
    incoming = {str(c) for c in collected if isinstance(c, str)}
    if not isinstance(interact_bonus, (int, float)) or interact_bonus < 0:
        interact_bonus = 0

    with FileLock(STATE_PATH):
        state = _load_state()
        merged = sorted(set(state["collected"]) | incoming)
        bonus = max(state["interact_bonus"], int(interact_bonus))
        state["collected"] = merged
        state["interact_bonus"] = bonus
        state["updated_at"] = _utc_now_iso()
        _save_state(state)

    result = {
        "collected": list(merged),
        "interact_bonus": bonus,
        "updated_at": state["updated_at"],
    }
    if headpat_count is not None:
        result["headpat_count"] = int(headpat_count)
    return result


def main(argv: list[str] | None = None) -> int:
    """CLI：python m6_collection.py status | sync <collected...> --bonus N"""
    argv = list(argv or sys.argv[1:])
    if not argv:
        print(json.dumps(get_collection(), ensure_ascii=False, indent=2))
        return 0
    if argv[0] == "status":
        print(json.dumps(get_collection(), ensure_ascii=False, indent=2))
        return 0
    if argv[0] == "sync":
        bonus = 0
        items: list[str] = []
        args = argv[1:]
        if "--bonus" in args:
            i = args.index("--bonus")
            try:
                bonus = int(args[i + 1])
            except (IndexError, ValueError):
                bonus = 0
            args = args[:i]
        items = [a for a in args if a.strip()]
        result = merge_collection(items, bonus)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
