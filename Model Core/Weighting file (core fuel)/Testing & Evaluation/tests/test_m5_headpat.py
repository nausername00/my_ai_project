"""M5 深化 · 摸头奖励测试。

覆盖：触发检测（不误触发）、三拍循环、好感计数、阈值升级台词、
API 返回结构（response_kind=headpat）、普通消息不触发、状态持久化。
state 用 tmp_path 隔离，不污染真实好感计数。
"""
import json
import os

import pytest

from m_studio.m5_headpat import HeadpatScript, detect_headpat, headpat_response


def test_detect_matches_headpat_cues() -> None:
    assert detect_headpat("摸摸头")
    assert detect_headpat("乖，让我摸摸")
    assert detect_headpat("好乖，蹭蹭你")
    assert detect_headpat("rua 一下")


def test_detect_avoids_single_kuai() -> None:
    # 单字"乖"不作触发词，避免"乖，帮我做X"误触发
    assert not detect_headpat("乖，帮我整理一下文件")


def test_touch_cycles_three_beats(tmp_path) -> None:
    state_path = str(tmp_path / "headpat.json")
    script = HeadpatScript(state_path=state_path)
    moods = []
    for _ in range(3):
        r = script.touch()
        moods.append(r["beat"]["mood"])
    # 三拍：开心 → 害羞 → 开心（柔软）
    assert moods[0] == "开心"
    assert moods[1] == "害羞"


def test_count_persists_and_tier_fires(tmp_path) -> None:
    state_path = str(tmp_path / "headpat.json")
    script = HeadpatScript(state_path=state_path)
    for _ in range(5):
        r = script.touch()
    assert r["count"] == 5
    assert r["tier"] == 5
    assert r["tier_text"]                              # 亲密度升级台词触发
    assert script.status()["count"] == 5


def test_headpat_response_structure(tmp_path) -> None:
    state_path = str(tmp_path / "headpat.json")
    r = headpat_response("摸摸头", state_path=state_path)
    assert r is not None
    assert r["response_kind"] == "headpat"
    assert r["mood"] in ("开心", "害羞")
    assert r["expression"]
    assert r["headpat"]["count"] == 1
    assert r["text"]


def test_headpat_response_plain_message_is_none(tmp_path) -> None:
    assert headpat_response("今天天气不错", str(tmp_path / "h.json")) is None
