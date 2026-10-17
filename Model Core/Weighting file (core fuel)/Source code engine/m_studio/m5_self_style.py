"""M5a · 墨灵自我形象系统——形象提案管线。

墨灵从时装库 × 色调库生成"形象提案"（组合 + 设计思路讲解 + 渲染图），
用户挑选 / 指正；采纳后写入当前穿戴状态（fashion_state.json）。

设计思路为墨灵第一人称预置讲解（风格接 B 自导解说器，不额外调模型省消耗），
渲染复用 FashionSystem（含优化 1 缓存：重复组合零等待）。
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

from fashion_system import FashionSystem

HERE = os.path.dirname(os.path.abspath(__file__))
PROPOSALS_PATH = os.path.join(HERE, "style_proposals.json")

# 墨灵第一人称设计思路库（时装 × 色调 组合讲解）
_OUTFIT_IDEA = {
    "celadon_cloud": "青花是沉淀的墨色，云纹是流动的思绪。",
    "phoenix_crimson": "绯红是心跳，金凤是锋芒。",
    "starlight_silk": "星澜是深空的呼吸，银线是划过夜色的流光。",
    "emerald_flow": "翡翠是沉淀的生机，金纹是跃动的脉搏。",
}
_TONE_IDEA = {
    "ivory": "暖白像晨光落在书页上，安静又有灵气。",
    "light": "月白微光，轻盈明快，像风穿过清晨。",
    "royal": "深蓝灰像夜空中点亮的焰火，沉稳里带着星芒。",
    "midnight": "星夜蓝像未眠的深海，神秘里藏着微光。",
    "emerald": "翡翠绿像林间的晨露，清透里带着生命力。",
}
_SCENE_IDEA = {
    ("celadon_cloud", "ivory"): "适合陪你安静讲知识——从容、书卷气，不会抢话。",
    ("celadon_cloud", "light"): "适合日常陪伴——清清爽爽，像一壶刚泡的茶。",
    ("celadon_cloud", "royal"): "适合严肃讨论——青花压进深蓝，稳重而有格调。",
    ("phoenix_crimson", "ivory"): "适合庆祝时刻——绯红衬暖白，热烈但不灼人。",
    ("phoenix_crimson", "light"): "适合惊喜亮相——金凤在月白上飞，明亮得让人眼前一亮。",
    ("phoenix_crimson", "royal"): "适合压轴登场——绯红金凤点亮深蓝夜幕，就是我讲到兴奋处的样子。",
    ("starlight_silk", "midnight"): "适合夜晚长谈——星夜配星夜，安静又深邃。",
    ("starlight_silk", "ivory"): "适合讲神秘有趣的话题——蓝银浮在暖白上，像梦境落在纸上。",
    ("starlight_silk", "light"): "适合轻松陪伴——星澜在月白里，清爽得像夏夜的风。",
    ("starlight_silk", "royal"): "适合认真讲解——深蓝夜承住星澜，沉稳有层次。",
    ("starlight_silk", "emerald"): "适合自然话题——星夜与翡翠相映，天地都收进这一身。",
    ("emerald_flow", "emerald"): "适合讲述成长与生机——翡翠配翡翠，通体都是生命力。",
    ("emerald_flow", "midnight"): "适合神秘登场——金纹在星夜蓝上亮起，像夜色里点灯。",
    ("emerald_flow", "ivory"): "适合晨间陪伴——翡翠衬暖白，清爽又精神。",
    ("emerald_flow", "light"): "适合日常清新——金纹在月白上流动，轻盈明快。",
    ("emerald_flow", "royal"): "适合正式时刻——翡翠压进深蓝，华贵而不张扬。",
}


class SelfStyleProposal:
    def __init__(self, fashion: FashionSystem | None = None,
                 proposals_path: str | None = None) -> None:
        self.fashion = fashion or FashionSystem()
        self._path = proposals_path or PROPOSALS_PATH
        self._proposals: list[dict] = self._load()

    # ------------------------------------------------------------------ 存储
    def _load(self) -> list[dict]:
        if not os.path.isfile(self._path):
            return []
        with open(self._path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []

    def _save(self) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._proposals, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------ 提案
    def propose(self, outfit_id: str, tone_id: str, res: str = "960,540",
                render: bool = True) -> dict:
        """生成一个形象提案（组合+思路+渲染图）。"""
        outfit = self.fashion.get_outfit(outfit_id)
        tone_name = tone_id
        idea = (
            _OUTFIT_IDEA.get(outfit_id, f"{outfit['name']}的设计。")
            + " "
            + _TONE_IDEA.get(tone_id, f"{tone_id}色调。")
            + " "
            + _SCENE_IDEA.get((outfit_id, tone_id), "适合日常陪伴。")
        )
        params = self.fashion.compose(outfit_id, tone_id, res)
        out = os.path.join(HERE, f"proposal_{outfit_id}_{tone_id}.png")
        result = self.fashion.render(params, out_path=out) if render else None

        proposal = {
            "id": len(self._proposals) + 1,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "outfit_id": outfit_id,
            "outfit_name": outfit["name"],
            "tone_id": tone_id,
            "tone_name": tone_name,
            "res": res,
            "idea": idea,
            "render": result,
            "status": "pending",
        }
        self._proposals.append(proposal)
        self._save()
        return proposal

    def propose_all(self, outfit_ids: list[str] | None = None,
                    tone_ids: list[str] | None = None, render: bool = True) -> list[dict]:
        """批量生成候选提案。"""
        outfits = outfit_ids or [o["id"] for o in self.fashion.list_outfits()]
        tones = tone_ids or self.fashion.list_tones()
        made: list[dict] = []
        for o in outfits:
            for t in tones:
                made.append(self.propose(o, t, render=render))
        return made

    # ------------------------------------------------------------------ 查询/采纳
    def list_proposals(self, limit: int = 20) -> list[dict]:
        return self._proposals[-limit:]

    def get_proposal(self, pid: int) -> dict:
        for p in self._proposals:
            if p["id"] == pid:
                return p
        raise ValueError(f"未知提案 id: {pid}")

    def adopt(self, pid: int) -> dict:
        """采纳提案：写入当前穿戴状态并标记 adopted。"""
        proposal = self.get_proposal(pid)
        proposal["status"] = "adopted"
        self.fashion.save_state(proposal["outfit_id"], proposal["tone_id"], proposal["res"])
        self._save()
        return proposal


def main(argv: list[str]) -> int:
    """CLI：--propose <o> <t> | --propose-all [--no-render] | --list | --adopt <id>"""
    system = SelfStyleProposal()
    if "--propose-all" in argv:
        made = system.propose_all(render="--no-render" not in argv)
        for p in made:
            hit = p["render"]["cache_hit"] if p["render"] else "-"
            print(f"  #{p['id']} {p['outfit_name']}×{p['tone_id']} cache={hit} out={os.path.basename(p['render']['out'])}")
        return 0
    if "--propose" in argv:
        i = argv.index("--propose")
        p = system.propose(argv[i + 1], argv[i + 2])
        print(f"  #{p['id']} {p['outfit_name']}×{p['tone_id']} cache={p['render']['cache_hit']} out={os.path.basename(p['render']['out'])}")
        print(f"  思路：{p['idea']}")
        return 0
    if "--list" in argv:
        for p in system.list_proposals():
            print(f"  #{p['id']} [{p['status']}] {p['outfit_name']}×{p['tone_id']} "
                  f"({os.path.basename(p['render']['out']) if p.get('render') else '未渲染'})")
            print(f"      思路：{p['idea']}")
        return 0
    if "--adopt" in argv:
        p = system.adopt(int(argv[argv.index("--adopt") + 1]))
        print(f"  已采纳 #{p['id']} {p['outfit_name']}×{p['tone_id']} -> 当前穿戴已更新")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
