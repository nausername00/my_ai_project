"""M6 · 双端同步（图鉴收集 + 互动计数）测试。

覆盖：并集合并（不丢任何已收集项）、interact_bonus 取大、
状态写回持久化、get_collection 返回完整画像、空/非法输入防御。
STATE_PATH 用 tmp_path 替换，不污染真实收集状态。
"""
import json
import os

import pytest

import m_studio.m6_collection as m6


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    """把 m6 的状态文件重定向到临时路径，测试互不干扰。"""
    state_path = str(tmp_path / "collection.json")
    monkeypatch.setattr(m6, "STATE_PATH", state_path)
    if os.path.exists(state_path):
        os.remove(state_path)
    return state_path


def test_merge_takes_union_of_collected(tmp_path) -> None:
    # 先有后端收集项，客户端上报不同项 → 并集，不丢旧的
    m6.merge_collection(["deep_sea"], 0)
    result = m6.merge_collection(["moon", "gold"], 0)
    assert set(result["collected"]) == {"deep_sea", "moon", "gold"}
    # 再上报重复项 → 幂等
    result2 = m6.merge_collection(["gold", "deep_sea"], 0)
    assert sorted(result2["collected"]) == ["deep_sea", "gold", "moon"]


def test_merge_takes_max_interact_bonus(tmp_path) -> None:
    m6.merge_collection([], 3)
    result = m6.merge_collection([], 5)
    assert result["interact_bonus"] == 5
    # 客户端落后不上报旧值 → 不会回退
    result2 = m6.merge_collection([], 1)
    assert result2["interact_bonus"] == 5


def test_merge_persists_and_reads_back(tmp_path) -> None:
    m6.merge_collection(["aurora"], 7)
    state = m6.get_collection()
    assert state["collected"] == ["aurora"]
    assert state["interact_bonus"] == 7
    assert "headpat_count" in state  # 完整画像含摸头计数
    # 磁盘文件真实存在
    with open(m6.STATE_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    assert raw["interact_bonus"] == 7


def test_merge_guards_bad_input(tmp_path) -> None:
    # 非法类型不炸、不写入
    result = m6.merge_collection("not-a-list", -5)
    assert result["collected"] == []
    assert result["interact_bonus"] == 0
    result2 = m6.merge_collection([1, 2, None], "x")
    assert result2["collected"] == []  # 非字符串项被过滤


def test_merge_includes_optional_headpat_count(tmp_path) -> None:
    result = m6.merge_collection([], 0, headpat_count=42)
    assert result.get("headpat_count") == 42
