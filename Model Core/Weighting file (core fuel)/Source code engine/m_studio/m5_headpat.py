"""M5 深化 · 摸头奖励（游戏化亲密互动）。

用户摸头 → 墨灵回应（开心/害羞反差萌，复用 M5b 三拍机制的情绪序列）+
轻量好感计数（默认记录、不改变任何执行/授权逻辑；纯表现层）。

设计意图：
- 触发是显式动作指令（"摸摸头"），不是抢话——不属于"主动提议"边界。
- 好感计数为轻量状态（headpat_state.json），阈值台词制造"养女儿"式成长感。
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(HERE, "headpat_state.json")

# 触发词：长词优先，避免单字"乖"误触发
_HEADPAT_CUES = ("摸摸头", "摸头", "摸一摸", "摸摸", "好乖", "蹭蹭", "撸撸", "rua", "Rua")

# 摸头三拍：开心 → 害羞 → 柔软（mood 对接 character 情绪枚举：开心/害羞）
_HEADPAT_BEATS: list[dict[str, str]] = [
    {
        "beat": "happy",
        "mood": "开心",
        "expression": "happy",
        "text": "嘿嘿~被摸头了……好舒服，可以再来一下吗？",
    },
    {
        "beat": "shy",
        "mood": "害羞",
        "expression": "shy",
        "text": "呜……你、你怎么突然摸头啦！才、才没有觉得很开心呢！",
    },
    {
        "beat": "soft",
        "mood": "开心",
        "expression": "happy",
        "text": "（蹭蹭）……今天辛苦了吧？下次也让我摸摸你的头~",
    },
]

# 亲密度升级台词（阈值 → 台词）
_TIER_TEXTS: dict[int, str] = {
    5: "唔……你摸头越来越熟练了，我好像越来越依赖了……",
    15: "已经摸了这么多次，你的手是不是长在我头顶上了？",
    30: "三十次了！这是不是……算求婚了？（说完自己先害羞到冒烟）",
}


def detect_headpat(message: str) -> bool:
    """显式动作触发检测：消息含摸头词即命中。"""
    return any(cue in message for cue in _HEADPAT_CUES)


def _load_state() -> dict[str, Any]:
    if not os.path.isfile(STATE_PATH):
        return {"count": 0}
    with open(STATE_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {"count": 0}


def _save_state(state: dict[str, Any]) -> None:
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


class HeadpatScript:
    """摸头奖励：三拍演出 + 好感计数（轻量、可查询、不改变逻辑）。"""

    def __init__(self, beats: list[dict[str, str]] | None = None,
                 state_path: str | None = None) -> None:
        self._beats = beats or _HEADPAT_BEATS
        self._state_path = state_path or STATE_PATH

    def touch(self) -> dict[str, Any]:
        """记录一次摸头，返回当前拍演出 + 好感状态。"""
        state = self._load_state()
        state["count"] = int(state.get("count", 0)) + 1
        count = state["count"]
        beat = self._beats[(count - 1) % len(self._beats)]

        tier = None
        tier_text = None
        if count in _TIER_TEXTS:
            tier = count
            tier_text = _TIER_TEXTS[count]
        state["last_beat"] = beat["beat"]
        self._save_state(state)

        return {
            "beat": beat,
            "count": count,
            "tier": tier,
            "tier_text": tier_text,
        }

    def status(self) -> dict[str, Any]:
        state = self._load_state()
        return {"count": int(state.get("count", 0))}

    def _load_state(self) -> dict[str, Any]:
        if not os.path.isfile(self._state_path):
            return {"count": 0}
        with open(self._state_path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {"count": 0}

    def _save_state(self, state: dict[str, Any]) -> None:
        with open(self._state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)


def headpat_response(message: str, state_path: str | None = None) -> dict[str, Any] | None:
    """聊天入口：命中摸头返回回应（含三拍/好感状态），未命中返回 None。"""
    if not detect_headpat(message):
        return None
    result = HeadpatScript(state_path=state_path).touch()
    text = result["beat"]["text"]
    if result["tier_text"]:
        text = f"{text}\n（好感度 {result['tier']}）{result['tier_text']}"
    return {
        "text": text,
        "mood": result["beat"]["mood"],
        "expression": result["beat"]["expression"],
        "headpat": {"count": result["count"], "tier": result["tier"]},
        "response_kind": "headpat",
    }


def main(argv: list[str]) -> int:
    """CLI：--detect <消息> | --touch | --status"""
    script = HeadpatScript()
    if "--detect" in argv:
        msg = argv[argv.index("--detect") + 1]
        print(f"detect_headpat={detect_headpat(msg)}")
        return 0
    if "--touch" in argv:
        result = script.touch()
        print(f"[{result['beat']['mood']}] {result['beat']['text']}（count={result['count']}）")
        return 0
    if "--status" in argv:
        print(json.dumps(script.status(), ensure_ascii=False))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
