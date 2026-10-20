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


# ------------------------------------------------------------------ M5a 自荐造型（fashion_service）
def test_style_proposal_request_triggered() -> None:
    from fashion_service import suggest_style_proposal

    result = suggest_style_proposal("给我看看你的造型推荐")
    assert result["proposed"] is True
    assert result["trigger"] == "style_request"
    assert "青花云纹" in result["text"] or "绯红金凤" in result["text"]
    assert "穿上" in result["text"]
    assert isinstance(result["proposals"], list) and result["proposals"]


def test_style_proposal_look_cue_needs_subject() -> None:
    from fashion_service import suggest_style_proposal

    # 有"看看"但无形象主题 → 不触发（有边界）
    assert suggest_style_proposal("给我看看这个文件")["proposed"] is False
    assert suggest_style_proposal("今天天气不错")["proposed"] is False


# ------------------------------------------------------------------ M5c 换装指令识别（detect_fashion_command）
def test_detect_fashion_known_aliases() -> None:
    from fashion_service import detect_fashion_command

    # 既有长词
    assert detect_fashion_command("今天穿青花云纹吧")["outfit_id"] == "celadon_cloud"
    assert detect_fashion_command("换上绯红金凤")["outfit_id"] == "phoenix_crimson"


def test_detect_fashion_new_aliases() -> None:
    from fashion_service import detect_fashion_command

    # 星澜 / 翡翠（M5 时装库扩展）
    assert detect_fashion_command("换上星澜蓝银")["outfit_id"] == "starlight_silk"
    assert detect_fashion_command("穿星澜的")["outfit_id"] == "starlight_silk"
    assert detect_fashion_command("穿上翡翠流光")["outfit_id"] == "emerald_flow"
    # 晨光 / 繁花（墨灵现场自主设计）
    assert detect_fashion_command("换装晨光")["outfit_id"] == "dawn_silk"
    assert detect_fashion_command("换上繁花")["outfit_id"] == "bloom_silk"
    # M10 时装库扩展（第三梯队 A：樱雪/青枫/极光进换装识别）
    assert detect_fashion_command("今天穿樱雪")["outfit_id"] == "sakura_snow"
    assert detect_fashion_command("换上青枫")["outfit_id"] == "maple_moss"
    assert detect_fashion_command("穿极光的")["outfit_id"] == "aurora"


def test_detect_fashion_m10_tones() -> None:
    from fashion_service import detect_fashion_command

    # M10 新增色调：樱雪粉 / 枫叶橙 / 极夜蓝
    assert detect_fashion_command("穿樱雪粉的青花云纹")["tone_id"] == "sakura"
    assert detect_fashion_command("换上枫叶橙")["tone_id"] == "maple"
    assert detect_fashion_command("穿极夜蓝")["tone_id"] == "aurora"
    # 带时装+色调的组合指令
    cmd = detect_fashion_command("换上极光的极夜蓝")
    assert cmd["outfit_id"] == "aurora"
    assert cmd["tone_id"] == "aurora"


def test_detect_fashion_single_char_fallback() -> None:
    from fashion_service import detect_fashion_command

    # 单字兜底：长词未命中才落到这里
    assert detect_fashion_command("换身蓝的")["outfit_id"] == "starlight_silk"
    assert detect_fashion_command("穿件绿的")["outfit_id"] == "emerald_flow"


def test_detect_fashion_tone_aliases() -> None:
    from fashion_service import detect_fashion_command

    assert detect_fashion_command("穿星夜蓝的青花云纹")["tone_id"] == "midnight"
    assert detect_fashion_command("穿翡翠绿")["tone_id"] == "emerald"
    assert detect_fashion_command("换上晨光金")["tone_id"] == "dawn"
    assert detect_fashion_command("穿花雾粉")["tone_id"] == "bloom"


def test_detect_fashion_long_first() -> None:
    from fashion_service import detect_fashion_command

    # 长词优先：星澜蓝银命中时装而不是单字"蓝"兜底；翡翠流光命中而不是"绿"兜底
    assert detect_fashion_command("换上星澜蓝银")["outfit_id"] == "starlight_silk"
    assert detect_fashion_command("穿上翡翠流光")["outfit_id"] == "emerald_flow"


def test_detect_fashion_not_triggered() -> None:
    from fashion_service import detect_fashion_command

    # 无命令 cue / 普通聊天不触发（简单任务直做）
    assert detect_fashion_command("青花云纹真好看") is None
    assert detect_fashion_command("今天天气不错") is None
    assert detect_fashion_command("星澜是蓝色系吗") is None
    assert detect_fashion_command(12345) is None

