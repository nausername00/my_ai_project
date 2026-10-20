"""C · 时装库扩展（M10 程序化生成器）测试。

覆盖：主题完整性 / 贴图生成尺寸 / 注册幂等 / 时装库可见与可组合 / 无缝性粗测。
不依赖 Blender 渲染（渲染链路已由 FashionSystem 既有测试覆盖）。
"""

import json
import os
import sys

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "Source code engine", "m_studio"))

import m10_fashion_generator as gen  # noqa: E402
from fashion_system import FashionSystem  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ENG = os.path.join(os.path.dirname(os.path.dirname(HERE)), "Source code engine")
M_STUDIO = os.path.join(ENG, "m_studio")


def test_theme_definitions_complete() -> None:
    """每个主题都有生成器、注册字段与讲解。"""
    for tid, theme in gen.THEMES.items():
        assert tid in gen._GENERATORS, f"missing generator: {tid}"
        assert theme["name"]
        assert theme["tone_id"]
        assert len(theme["tone_rgb"]) == 3
        assert theme["name"] in theme["desc"]
        assert theme["idea"]
        assert theme["expect"]


def test_generate_outputs_2048_texture(tmp_path) -> None:
    """生成贴图存在且 2048×2048 RGB JPEG。"""
    theme_id = "sakura_snow"
    out = os.path.join(M_STUDIO, gen.texture_path(theme_id))
    assert os.path.isfile(out), f"texture missing: {out}"
    im = Image.open(out)
    assert im.size == (gen.TILE, gen.TILE)
    assert im.mode == "RGB"
    # 内容非空白
    arr = np.asarray(im)
    assert arr.std() > 8.0, "texture looks blank"


def test_all_themes_generate_textures() -> None:
    for tid in gen.THEMES:
        out = os.path.join(M_STUDIO, gen.texture_path(tid))
        assert os.path.isfile(out), f"texture missing: {out}"


def test_registration_idempotent_and_visible() -> None:
    """注册幂等；新时装对 FashionSystem 可见且可组合。"""
    registry_path = os.path.join(M_STUDIO, "fashion_registry.json")
    with open(registry_path, encoding="utf-8") as f:
        registry = json.load(f)
    ids = {o["id"] for o in registry["outfits"]}
    tones = set(registry["tones"])
    for tid, theme in gen.THEMES.items():
        assert tid in ids, f"outfit not registered: {tid}"
        assert theme["tone_id"] in tones, f"tone not registered: {theme['tone_id']}"

    # 二次注册不重复
    changed = gen._register("sakura_snow", gen.texture_path("sakura_snow"))
    assert changed is False

    fs = FashionSystem(registry_path=registry_path, state_dir=M_STUDIO)
    outfit_ids = {o["id"] for o in fs.list_outfits()}
    assert {"sakura_snow", "maple_moss", "aurora"} <= outfit_ids
    for tid in gen.THEMES:
        params = fs.compose(tid, gen.THEMES[tid]["tone_id"])
        assert os.path.isfile(params["texture"])
        assert params["target"] == "body_ring"


def test_texture_seam_continuity() -> None:
    """无缝性粗测：左右边界相邻像素差 ≈ 内部相邻像素差（环面拼接连续）。"""
    theme_id = "maple_moss"
    im = np.asarray(Image.open(os.path.join(M_STUDIO, gen.texture_path(theme_id)))).astype(np.float64)
    # 边界缝合处（左列0 vs 右列N-1）与内部相邻列对比
    seam = np.abs(im[:, 0, :] - im[:, -1, :]).mean()
    internal = np.abs(im[:, -2, :] - im[:, -1, :]).mean()
    # JPEG 压缩引入少量噪声，阈值放宽：边界缝不应显著高于内部相邻差
    assert seam < internal * 4.0 + 6.0, f"seam discontinuity: seam={seam:.2f} internal={internal:.2f}"
