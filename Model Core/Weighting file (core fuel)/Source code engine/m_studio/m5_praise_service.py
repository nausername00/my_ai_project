"""M5b 深化 · 反差萌接入主对话。

被夸奖时墨灵三拍演出（得意炫耀 → 说漏嘴 → 害羞狡辩），
并顺势注入"当前穿的造型 + 设计思路"——炫耀内容真实指向此刻形象，
与摸头奖励同属纯表现层：不改变执行/授权逻辑，仅显式夸奖触发不抢话。
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from fashion_service import current_outfit
from m_studio.m5_script import PraiseScript, detect_praise

HERE = os.path.dirname(os.path.abspath(__file__))
DESIGN_LOG_PATH = os.path.join(HERE, "design_log.json")
STYLE_PROPOSALS_PATH = os.path.join(HERE, "style_proposals.json")


def _load_json(path: str) -> Any:
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _current_style() -> tuple[str, str, str]:
    """返回 (造型名, 造型id, 色调id)；取不到时回退 (青花云纹, celadon_cloud, royal)。"""
    try:
        state = current_outfit().get("current") or {}
        outfit_id = state.get("outfit_id") or "celadon_cloud"
        tone_id = state.get("tone_id") or "royal"
        name = outfit_id
        data = _load_json(os.path.join(HERE, "fashion_registry.json"))
        if data:
            for o in data.get("outfits", []):
                if o.get("id") == outfit_id:
                    name = o.get("name", outfit_id)
                    break
        return name, outfit_id, tone_id
    except Exception:
        return "青花云纹", "celadon_cloud", "royal"


def _style_idea(outfit_id: str, outfit_name: str, tone_id: str) -> str:
    """查当前造型的设计思路：现场设计（design_log）优先，其次自荐提案库。"""
    log = _load_json(DESIGN_LOG_PATH)
    if isinstance(log, list):
        for entry in log:
            if entry.get("outfit_id") == outfit_id and entry.get("status") == "applied":
                return entry.get("idea", "")
    props = _load_json(STYLE_PROPOSALS_PATH)
    if isinstance(props, dict):
        props = props.get("proposals", [])
    if isinstance(props, list):
        for p in props:
            if (p.get("outfit_id") == outfit_id and p.get("tone_id") == tone_id
                    and p.get("idea")):
                return p["idea"]
    return ""


def praise_response(prompt: str, style_override: str | None = None,
                    idea_override: str | None = None) -> dict[str, Any] | None:
    """聊天入口：命中夸奖返回三拍演出（含当前造型思路），未命中返回 None。"""
    if not detect_praise(prompt):
        return None
    style, outfit_id, tone_id = _current_style()
    idea = idea_override if idea_override is not None else _style_idea(outfit_id, style, tone_id)
    beats = PraiseScript().play(style=style_override or style, idea=idea)
    return {
        "text": "\n".join(b["text"] for b in beats),
        "beats": beats,
        "style": style_override or style,
        "idea": idea,
        "moods": [b["mood"] for b in beats],
        "response_kind": "praise",
    }


def main(argv: list[str]) -> int:
    """CLI：--detect <消息> | --play [--style 造型名] [--idea 思路] | --current"""
    if "--detect" in argv:
        msg = argv[argv.index("--detect") + 1]
        print(f"detect_praise={detect_praise(msg)}")
        return 0
    if "--current" in argv:
        name, oid, tid = _current_style()
        print(f"current={name} ({oid} × {tid}) idea={_style_idea(oid, name, tid)[:30] or '（无）'}")
        return 0
    if "--play" in argv:
        style = argv[argv.index("--style") + 1] if "--style" in argv else None
        idea = argv[argv.index("--idea") + 1] if "--idea" in argv else None
        resp = praise_response("你穿这身真好看", style_override=style, idea_override=idea)
        print(json.dumps(resp, ensure_ascii=False, indent=2))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
