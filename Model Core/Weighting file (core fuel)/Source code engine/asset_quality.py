"""墨灵素材质检：透明素材的边缘白边（光晕）自动检查。

check_halo —— 检测透明 PNG 边缘半透明像素中的"近白"像素占比：
发丝等半透明边缘若接近白色，在深色/浅色背景合成时会露出白边。
- 先缩图到长边 ≤256 再检测（边缘性质保留，速度快）。
- risk 分级：halo_ratio > 15% → high；> 2% → medium；否则 low。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

_NEAR_WHITE = 240
_ALPHA_FLOOR = 8
_ALPHA_CEIL = 250
_RATIO_MEDIUM = 0.02
_RATIO_HIGH = 0.15


def check_halo(image_path: str | Path) -> dict[str, Any]:
    """检查透明素材边缘白边风险，返回可复现的量化结果。"""
    path = Path(image_path)
    if not path.exists():
        raise ValueError(f"图片不存在: {path}")
    img = Image.open(path).convert("RGBA")
    img.thumbnail((256, 256))
    pixels = list(img.getdata())
    edge = 0
    halo = 0
    for r, g, b, a in pixels:
        if _ALPHA_FLOOR < a < _ALPHA_CEIL:
            edge += 1
            if r >= _NEAR_WHITE and g >= _NEAR_WHITE and b >= _NEAR_WHITE:
                halo += 1
    ratio = halo / edge if edge else 0.0
    if ratio > _RATIO_HIGH:
        risk = "high"
    elif ratio > _RATIO_MEDIUM:
        risk = "medium"
    else:
        risk = "low"
    return {
        "status": "ok",
        "edge_pixels": edge,
        "halo_pixels": halo,
        "halo_ratio": round(ratio, 4),
        "risk": risk,
        "suggestion": "建议在合成前清理半透明白边（可用边缘去边或颜色溢出修复）"
        if risk != "low"
        else "边缘干净，可直接合成",
    }
