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
    return FashionSystem(registry_path=str(reg_path), state_dir=str(tmp_path),
                         cache_dir=str(tmp_path / "cache"))


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


# ---------------------------------------------------------------------------
# 优化 1/3/4：渲染缓存 / 操作日志 / 异步句柄
# ---------------------------------------------------------------------------

def test_cache_key_deterministic(fs_tmp: FashionSystem) -> None:
    params = fs_tmp.compose("a", "ivory")
    assert fs_tmp.cache_key(params) == fs_tmp.cache_key(params)
    params2 = dict(params, base_color="0.5,0.5,0.5")
    assert fs_tmp.cache_key(params) != fs_tmp.cache_key(params2)


def test_cache_miss_then_hit(fs_tmp: FashionSystem, tmp_path, monkeypatch) -> None:
    params = fs_tmp.compose("a", "ivory")
    out = str(tmp_path / "out.png")

    calls = []

    def fake_blender(args):
        calls.append(args)
        with open(out, "w", encoding="utf-8") as f:
            f.write("fake-png")
        return type("P", (), {"returncode": 0, "stdout": "[ok]", "stderr": ""})()

    monkeypatch.setattr(fs_tmp, "_run_blender", fake_blender)

    first = fs_tmp.render(params, out_path=out)
    assert first["cache_hit"] is False
    assert len(calls) == 1
    assert fs_tmp.cache_hit(params) is not None

    second = fs_tmp.render(params, out_path=out)
    assert second["cache_hit"] is True
    assert second["cost"] == "轻"
    assert len(calls) == 1  # 第二次未再调 blender


def test_render_no_cache_force(fs_tmp: FashionSystem, tmp_path, monkeypatch) -> None:
    params = fs_tmp.compose("a", "ivory")
    out = str(tmp_path / "out.png")
    calls = []

    def fake_blender(args):
        calls.append(1)
        with open(out, "w", encoding="utf-8") as f:
            f.write("fake-png")
        return type("P", (), {"returncode": 0, "stdout": "[ok]", "stderr": ""})()

    monkeypatch.setattr(fs_tmp, "_run_blender", fake_blender)
    fs_tmp.render(params, out_path=out)
    fs_tmp.render(params, out_path=out, use_cache=False)
    assert len(calls) == 2  # use_cache=False 强制重渲


def test_ops_log_written(fs_tmp: FashionSystem, tmp_path, monkeypatch) -> None:
    params = fs_tmp.compose("a", "ivory")
    out = str(tmp_path / "out.png")

    def fake_blender(args):
        with open(out, "w", encoding="utf-8") as f:
            f.write("fake-png")
        return type("P", (), {"returncode": 0, "stdout": "[ok]", "stderr": ""})()

    monkeypatch.setattr(fs_tmp, "_run_blender", fake_blender)
    fs_tmp.render(params, out_path=out)
    fs_tmp.render(params, out_path=out)  # 第二次命中缓存

    log = fs_tmp.ops_log(limit=10)
    assert len(log) >= 2
    assert log[-1]["cache_hit"] is True
    assert log[-2]["cache_hit"] is False
    assert log[-1]["cost"] == "轻"
    assert log[-2]["cost"] == "重"


def test_wait_render_with_fake_proc(fs_tmp: FashionSystem) -> None:
    class FakeProc:
        returncode = 0

        def communicate(self, timeout=None):
            return "[async ok]", ""

    task = {"proc": FakeProc(), "out": "x.png"}
    result = FashionSystem.wait_render(task, timeout=5)
    assert result["rc"] == 0
    assert result["cost"] == "重"
    assert result["out"] == "x.png"
