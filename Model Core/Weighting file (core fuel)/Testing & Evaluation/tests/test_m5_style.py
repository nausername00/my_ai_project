"""M5 自我形象系统测试：a 形象提案（propose/adopt）+ b 反差萌剧本（三拍/情绪/触发）。"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "Source code engine", "m_studio"))

from m5_script import PraiseScript, detect_praise  # noqa: E402
from m5_self_style import SelfStyleProposal  # noqa: E402


class FakeFashion:
    """注入时装系统假实现：不调 Blender。"""

    def get_outfit(self, outfit_id: str) -> dict:
        return {"id": outfit_id, "name": "青花云纹", "texture": "x.jpg", "target": "body_ring", "desc": ""}

    def compose(self, outfit_id: str, tone_id: str, res: str = "960,540") -> dict:
        return {"outfit_id": outfit_id, "tone_id": tone_id, "target": "body_ring",
                "texture": "x.jpg", "base_color": "0.90,0.90,0.90", "res": res}

    def render(self, params: dict, out_path: str | None = None) -> dict:
        return {"rc": 0, "cache_hit": True, "render_ms": 0,
                "out": out_path or "fake.png", "log_tail": "", "cost": "轻"}

    def save_state(self, outfit_id: str, tone_id: str, res: str = "960,540") -> None:
        return None

    def list_outfits(self) -> list[dict]:
        return [self.get_outfit("a")]

    def list_tones(self) -> list[str]:
        return ["ivory", "royal"]


# ------------------------------------------------------------------ M5a
def test_propose_creates_proposal(tmp_path) -> None:
    p = SelfStyleProposal(fashion=FakeFashion(), proposals_path=str(tmp_path / "props.json"))
    proposal = p.propose("a", "ivory", render=False)
    assert proposal["outfit_id"] == "a"
    assert proposal["tone_id"] == "ivory"
    assert proposal["status"] == "pending"
    assert "思路" in proposal["idea"] or proposal["idea"]
    assert p.list_proposals()[-1]["id"] == proposal["id"]


def test_adopt_updates_state(tmp_path) -> None:
    p = SelfStyleProposal(fashion=FakeFashion(), proposals_path=str(tmp_path / "props.json"))
    p.propose("a", "royal", render=False)
    adopted = p.adopt(1)
    assert adopted["status"] == "adopted"
    assert p.list_proposals()[-1]["status"] == "adopted"


def test_get_unknown_proposal_raises(tmp_path) -> None:
    p = SelfStyleProposal(fashion=FakeFashion(), proposals_path=str(tmp_path / "props.json"))
    with pytest.raises(ValueError):
        p.get_proposal(99)


# ------------------------------------------------------------------ M5b
def test_play_three_beats_order() -> None:
    script = PraiseScript().play(style="绯红金凤")
    assert [b["beat"] for b in script] == ["proud", "slip", "shy"]
    assert script[0]["mood"] == "开心"
    assert script[1]["mood"] == "惊喜"
    assert script[2]["mood"] == "害羞"


def test_play_injects_style_and_idea() -> None:
    script = PraiseScript().play(style="青花云纹", idea="适合陪你安静讲知识。")
    assert "青花云纹" in script[0]["text"]
    assert "适合陪你安静讲知识" in script[0]["text"]
    assert "诱惑" in script[1]["text"]
    assert "狡辩" in script[2]["text"] or "手舞足蹈" in script[2]["text"]


def test_play_beat_out_of_range() -> None:
    with pytest.raises(IndexError):
        PraiseScript().play_beat(5)


def test_mood_sequence() -> None:
    assert PraiseScript().mood_sequence() == ["开心", "惊喜", "害羞"]


def test_detect_praise_cues() -> None:
    assert detect_praise("这套造型真好看！")
    assert detect_praise("你太厉害了")
    assert not detect_praise("今天天气不错")
