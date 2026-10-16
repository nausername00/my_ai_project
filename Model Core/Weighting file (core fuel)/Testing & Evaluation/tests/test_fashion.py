"""A · 时装/换装系统纯逻辑测试（不依赖 Blender 渲染）。

覆盖：库读取 / 组合解析 / 状态保存加载 / 错误处理。
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "Source code engine", "m_studio"))

from fashion_system import FashionError, FashionSystem  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ENG = os.path.join(os.path.dirname(os.path.dirname(HERE)), "Source code engine")
M_STUDIO = os.path.join(ENG, "m_studio")


@pytest.fixture()
def fs() -> FashionSystem:
    return FashionSystem(registry_path=os.path.join(M_STUDIO, "fashion_registry.json"),
                         state_dir=M_STUDIO)


@pytest.fixture()
def fs_tmp(tmp_path) -> FashionSystem:
    """用临时注册表 + 临时状态目录隔离测试。"""
    registry = {
        "version": 1,
        "outfits": [
            {"id": "a", "name": "甲", "texture": "m1_texture_organic.jpg", "target": "body_ring", "desc": ""}
        ],
        "tones": {"ivory": [0.95, 0.90, 0.82], "royal": [0.22, 0.28, 0.42]},
        "state_path": "state.json",
    }
    reg_path = tmp_path / "registry.json"
    reg_path.write_text(json.dumps(registry), encoding="utf-8")
    return FashionSystem(registry_path=str(reg_path), state_dir=str(tmp_path))


def test_list_outfits(fs: FashionSystem) -> None:
    outfits = fs.list_outfits()
    ids = {o["id"] for o in outfits}
    assert {"celadon_cloud", "phoenix_crimson"} <= ids
    assert all("texture" in o and "target" in o for o in outfits)


def test_list_tones(fs: FashionSystem) -> None:
    assert {"ivory", "light", "royal"} <= set(fs.list_tones())


def test_unknown_outfit_raises(fs: FashionSystem) -> None:
    with pytest.raises(FashionError):
        fs.get_outfit("no_such_outfit")


def test_unknown_tone_raises(fs: FashionSystem) -> None:
    with pytest.raises(FashionError):
        fs.get_tone("no_such_tone")


def test_compose_maps_params(fs: FashionSystem) -> None:
    params = fs.compose("phoenix_crimson", "royal")
    assert params["target"] == "body_ring"
    assert params["texture"].endswith("m3_texture_outfit.jpg")
    assert params["base_color"] == "0.22,0.28,0.42"
    assert params["res"] == "960,540"


def test_compose_custom_res(fs: FashionSystem) -> None:
    params = fs.compose("celadon_cloud", "ivory", res="1280,720")
    assert params["res"] == "1280,720"


def test_compose_missing_texture_raises(fs_tmp: FashionSystem, tmp_path) -> None:
    registry = {
        "version": 1,
        "outfits": [
            {"id": "ghost", "name": "幽灵衣", "texture": "not_exist.jpg", "target": "ring", "desc": ""}
        ],
        "tones": {"ivory": [0.9, 0.9, 0.9]},
        "state_path": "state.json",
    }
    reg = tmp_path / "ghost.json"
    reg.write_text(json.dumps(registry), encoding="utf-8")
    ghost = FashionSystem(registry_path=str(reg), state_dir=str(tmp_path))
    with pytest.raises(FashionError):
        ghost.compose("ghost", "ivory")


def test_state_roundtrip(fs_tmp: FashionSystem, tmp_path) -> None:
    fs_tmp.save_state("a", "royal", res="960,540")
    state = fs_tmp.current()
    assert state == {"outfit_id": "a", "tone_id": "royal", "res": "960,540"}
    # 新实例应能从磁盘恢复
    reloaded = FashionSystem(registry_path=fs_tmp._registry_path, state_dir=str(tmp_path))
    assert reloaded.current() == {"outfit_id": "a", "tone_id": "royal", "res": "960,540"}


def test_current_default_empty(fs_tmp: FashionSystem) -> None:
    assert fs_tmp.current() == {}


def test_bad_registry_raises(tmp_path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text('{"outfits": [], "nope": 1}', encoding="utf-8")
    with pytest.raises(FashionError):
        FashionSystem(registry_path=str(bad), state_dir=str(tmp_path))
