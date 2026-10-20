"""M5c · 换装服务：聊天 / API 统一入口。

detect_fashion_command()：从聊天消息识别"今天穿青花云纹 / 换上绯红金凤"等指令；
change_outfit()：换装（compose + render + save_state，带缓存与消耗统计）；
current_outfit()：当前穿戴 + 形象提案列表。

关键词 → 时装库映射用长词优先（青花云纹 > 青花 > 云纹），未指定项沿用当前穿戴。
"""

from __future__ import annotations

import os
import sys
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "m_studio"))

from fashion_system import FashionSystem  # noqa: E402
from m5_self_style import SelfStyleProposal  # noqa: E402

# 长词优先
_OUTFIT_ALIAS = (
    ("青花云纹", "celadon_cloud"),
    ("青花", "celadon_cloud"),
    ("云纹", "celadon_cloud"),
    ("绯红金凤", "phoenix_crimson"),
    ("绯红", "phoenix_crimson"),
    ("金凤", "phoenix_crimson"),
    ("凤凰", "phoenix_crimson"),
    ("星澜蓝银", "starlight_silk"),
    ("星澜", "starlight_silk"),
    ("蓝银", "starlight_silk"),
    ("翡翠流光", "emerald_flow"),
    ("翡翠", "emerald_flow"),
    ("晨光", "dawn_silk"),
    ("繁花", "bloom_silk"),
    # M10 时装库扩展（第三梯队 A：新时装进换装识别）
    ("樱雪", "sakura_snow"),
    ("樱花", "sakura_snow"),
    ("青枫", "maple_moss"),
    ("枫叶", "maple_moss"),
    ("秋枫", "maple_moss"),
    ("极光", "aurora"),
    # 单字兜底（长词已在前，只有未命中长词时才会到这里）
    ("蓝", "starlight_silk"),
    ("绿", "emerald_flow"),
    ("枫", "maple_moss"),
    ("樱", "sakura_snow"),
)
_TONE_ALIAS = (
    ("深蓝灰", "royal"),
    ("深蓝", "royal"),
    ("蓝灰", "royal"),
    ("夜幕", "royal"),
    ("月白", "light"),
    ("暖白", "ivory"),
    ("象牙", "ivory"),
    ("浅", "light"),
    ("星夜蓝", "midnight"),
    ("星夜", "midnight"),
    ("翡翠绿", "emerald"),
    ("晨光金", "dawn"),
    ("花雾粉", "bloom"),
    # M10 时装库扩展色调（第三梯队 A）
    ("樱雪粉", "sakura"),
    ("樱粉", "sakura"),
    ("雪粉", "sakura"),
    ("枫叶橙", "maple"),
    ("枫橙", "maple"),
    ("极夜蓝", "aurora"),
    ("极光蓝", "aurora"),
    ("极夜", "aurora"),
)
_COMMAND_CUES = ("穿", "换装", "换上", "换身", "造型")


def detect_fashion_command(message: str) -> dict[str, str] | None:
    """识别聊天换装指令；非换装消息返回 None（简单任务直做，不惊动推理）。"""
    if not isinstance(message, str) or not any(cue in message for cue in _COMMAND_CUES):
        return None
    outfit_id = next((oid for k, oid in _OUTFIT_ALIAS if k in message), None)
    tone_id = next((tid for k, tid in _TONE_ALIAS if k in message), None)
    if outfit_id is None and tone_id is None:
        return None
    return {"outfit_id": outfit_id, "tone_id": tone_id}


# M5a 自荐造型：明确请求才触发（有边界，不抢话）
_PROPOSAL_WANT_CUES = ("造型", "新衣服", "新装", "推荐", "展示", "换风格", "打扮", "设计")
_PROPOSAL_LOOK_CUES = ("看看", "给我看", "瞧瞧", "欣赏", "挑")


def suggest_style_proposal(message: str) -> dict:
    """识别"给我看看造型/有什么推荐"等请求 → 返回提案列表+推荐语。

    与 explore_proposal 同构的"有边界主动提议"：仅明确请求时 proposed=True，
    普通聊天不触发（默认关）。返回 {proposed, text, proposals, trigger}。
    """
    if not isinstance(message, str):
        return {"proposed": False}
    wants = any(c in message for c in _PROPOSAL_WANT_CUES)
    looks = any(c in message for c in _PROPOSAL_LOOK_CUES)
    subject = any(c in message for c in ("造型", "衣服", "风格", "形象", "服装"))
    if not (wants or (looks and subject)):
        return {"proposed": False}

    proposals = current_outfit()["proposals"]
    pending = [p for p in proposals if p["status"] == "pending"][:6]
    if not pending:
        return {"proposed": False, "text": "我的造型提案还在赶工中，回头一定补给你看！"}

    lines = []
    for p in pending:
        idea_head = (p["idea"] or "").split("。")[0]
        lines.append(f"{p['id']}. {p['outfit_name']}×{p['tone_id']}——{idea_head}。")
    text = (
        "哼哼~正好，我最近设计了几套造型，给你看看：\n"
        + "\n".join(lines)
        + "\n想试哪套，直接说『穿上青花云纹』或『换上绯红金凤』就行~"
    )
    return {"proposed": True, "text": text, "proposals": pending, "trigger": "style_request"}


def change_outfit(outfit_id: str | None, tone_id: str | None) -> dict[str, Any]:
    """换装：解析最终参数（未指定项沿用当前穿戴）→ 渲染（带缓存）→ 保存状态。"""
    fs = FashionSystem()
    current = fs.current()
    final_outfit = outfit_id or current.get("outfit_id") or fs.list_outfits()[0]["id"]
    final_tone = tone_id or current.get("tone_id") or fs.list_tones()[0]
    params = fs.compose(final_outfit, final_tone)
    result = fs.render(params)
    fs.save_state(final_outfit, final_tone)
    outfit = fs.get_outfit(final_outfit)
    return {
        "outfit_id": final_outfit,
        "outfit_name": outfit["name"],
        "tone_id": final_tone,
        "cache_hit": result["cache_hit"],
        "render_ms": result["render_ms"],
        "cost": result["cost"],
        "image": result["out"],
    }


def current_outfit() -> dict[str, Any]:
    fs = FashionSystem()
    proposals = SelfStyleProposal()
    current = fs.current()
    return {
        "current": current,
        "outfits": fs.list_outfits(),
        "tones": fs.list_tones(),
        "proposals": [
            {
                "id": p["id"],
                "status": p["status"],
                "outfit_name": p["outfit_name"],
                "tone_id": p["tone_id"],
                "idea": p["idea"],
                "image": (p.get("render") or {}).get("out"),
            }
            for p in proposals.list_proposals()
        ],
    }


def main(argv: list[str]) -> int:
    """CLI：--detect <消息> | --change <outfit_id> [tone_id] | --status"""
    if "--detect" in argv:
        msg = argv[argv.index("--detect") + 1]
        print(detect_fashion_command(msg))
        return 0
    if "--change" in argv:
        i = argv.index("--change")
        outfit_id = argv[i + 1] if i + 1 < len(argv) else None
        tone_id = argv[i + 2] if i + 2 < len(argv) else None
        result = change_outfit(outfit_id, tone_id)
        for k, v in result.items():
            print(f"  {k}: {v}")
        return 0
    if "--status" in argv:
        import json
        print(json.dumps(current_outfit(), ensure_ascii=False, indent=2))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
