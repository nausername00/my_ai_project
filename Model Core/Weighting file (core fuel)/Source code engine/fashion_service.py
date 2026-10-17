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
    return {
        "current": fs.current(),
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
