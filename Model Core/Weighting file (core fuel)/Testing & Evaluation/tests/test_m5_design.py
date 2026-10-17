"""M5 深化 · 墨灵现场自主设计时装测试。

覆盖：自主命题决策链、apply 注册幂等、自评判定、日志状态流转。
用 FakeFashion 注入避免真实渲染；registry/log 用 tmp_path 隔离。
"""
import json
import os

import pytest

from m_studio.m5_design import SelfDesigner

# 基础注册表：与真实 fashion_registry 同构（青花云纹 + 三色调）
BASE_REGISTRY = {
    "outfits": [
        {"id": "celadon_cloud", "name": "青花云纹", "texture": "m1_texture_organic.jpg",
         "target": "body_ring", "desc": "base"},
    ],
    "tones": {"ivory": [0.95, 0.90, 0.82], "light": [0.92, 0.94, 0.97],
              "royal": [0.22, 0.28, 0.42]},
}


class FakeFashion:
    """不触 Blender 的假时装系统（compose 返回固定参数、render 返回成功）。"""

    def compose(self, outfit_id: str, tone_id: str, res: str) -> dict:
        return {"target": "body_ring", "outfit_id": outfit_id, "tone_id": tone_id, "res": res}

    def render(self, params: dict, out_path: str) -> dict:
        return {"rc": 0, "cache_hit": False, "render_ms": 1, "cost": 0.001, "out": out_path}

    def list_outfits(self) -> list[dict]:
        return [{"id": "celadon_cloud", "texture": "m1_texture_organic.jpg", "target": "body_ring"}]


@pytest.fixture
def designer(tmp_path):
    reg = tmp_path / "registry.json"
    reg.write_text(json.dumps(BASE_REGISTRY), encoding="utf-8")
    log = tmp_path / "design_log.json"
    return SelfDesigner(fashion=FakeFashion(), registry_path=str(reg), design_log_path=str(log))


def test_plan_selects_unused_theme_and_builds_chain(designer) -> None:
    entry = designer.plan(None)
    assert entry["status"] == "planned"
    assert len(entry["decision_chain"]) >= 3            # 理由链完整
    assert entry["texture_prompt"]                       # 生成贴图的方向已给出
    assert entry["tone"]["rgb"]                          # 现场定义色调


def test_plan_unknown_theme_raises(designer) -> None:
    with pytest.raises(ValueError):
        designer.plan("no_such_theme")


def test_apply_registers_outfit_tone_and_reviews(designer, tmp_path) -> None:
    entry = designer.plan("dawn")
    texture = tmp_path / "m7_texture_dawn.jpg"
    texture.write_bytes(b"fake")
    applied = designer.apply("dawn", str(texture))

    assert applied["status"] == "applied"
    assert applied["review"]["verdict"] == "入库"
    assert applied["render"]["rc"] == 0

    reg = json.loads((tmp_path / "registry.json").read_text(encoding="utf-8"))
    assert any(o["id"] == "dawn_silk" for o in reg["outfits"])
    assert "dawn" in reg["tones"]


def test_apply_is_idempotent(designer, tmp_path) -> None:
    texture = tmp_path / "t.jpg"
    texture.write_bytes(b"fake")
    designer.plan("dawn")
    designer.apply("dawn", str(texture))
    designer.apply("dawn", str(texture))                 # 第二次 apply 不重复注册

    reg = json.loads((tmp_path / "registry.json").read_text(encoding="utf-8"))
    dawn_outfits = [o for o in reg["outfits"] if o["id"] == "dawn_silk"]
    assert len(dawn_outfits) == 1


def test_log_persists_planned_then_applied(designer, tmp_path) -> None:
    designer.plan("dawn")
    texture = tmp_path / "t.jpg"
    texture.write_bytes(b"fake")
    designer.apply("dawn", str(texture))

    log = json.loads((tmp_path / "design_log.json").read_text(encoding="utf-8"))
    assert any(e["theme_id"] == "dawn" and e["status"] == "applied" for e in log)
