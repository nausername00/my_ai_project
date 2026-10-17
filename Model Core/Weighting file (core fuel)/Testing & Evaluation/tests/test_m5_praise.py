"""M5b 深化 · 反差萌接主对话测试。

覆盖：夸奖检测、三拍演出结构、造型/设计思路注入、style idea 查找（design_log）、
普通消息不触发。style/idea 用注入隔离，不依赖真实当前造型。
"""
import pytest

from m_studio.m5_praise_service import _style_idea, praise_response
from m_studio.m5_script import PraiseScript, detect_praise


def test_detect_praise_cues() -> None:
    assert detect_praise("你穿这身真好看")
    assert detect_praise("好漂亮啊")
    assert detect_praise("墨灵真可爱")
    assert not detect_praise("今天天气不错")


def test_praise_response_structure() -> None:
    r = praise_response("你穿这身真好看", style_override="晨光", idea_override="暖金是给衣柜补的一口气")
    assert r is not None
    assert r["response_kind"] == "praise"
    assert len(r["beats"]) == 3                       # 三拍
    assert r["moods"] == ["开心", "惊喜", "害羞"]      # mood 序列
    assert r["style"] == "晨光"
    assert "暖金" in r["idea"]
    # 得意拍应注入造型名与思路，害羞拍保留原台词
    assert "晨光" in r["beats"][0]["text"]
    assert "才、才不是那样" in r["beats"][2]["text"]


def test_praise_plain_message_is_none() -> None:
    assert praise_response("帮我整理文件") is None


def test_style_idea_prefers_design_log(tmp_path) -> None:
    # design_log 有 applied 条目时优先取该现场设计思路
    import json
    log = [{"theme_id": "dawn", "outfit_id": "dawn_silk", "status": "applied",
            "idea": "晨光是给衣柜补的一口气"}]
    log_path = tmp_path / "design_log.json"
    log_path.write_text(json.dumps(log), encoding="utf-8")
    import m_studio.m5_praise_service as svc
    original = svc.DESIGN_LOG_PATH
    svc.DESIGN_LOG_PATH = str(log_path)
    try:
        assert "晨光" in _style_idea("dawn_silk", "晨光", "dawn")
    finally:
        svc.DESIGN_LOG_PATH = original


def test_praise_beats_format_with_style() -> None:
    script = PraiseScript().play(style="繁花", idea="花和叶缠在一起")
    assert "繁花" in script[0]["text"]
    assert script[0]["mood"] == "开心"
