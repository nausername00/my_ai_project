"""K2 验收演示：部件层按 z 序拼回 + 深浅背景边缘检查。

输出三张演示图（256px 网格排布，便于查看）：
1. 原图对照
2. 拼回（浅色背景上）：所有层按 z_order 叠加
3. 拼回（深色背景上）：检查边缘残留/白边

用法：python k2_preview.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

PROJECT_ROOT = Path(r"D:\Coding\code program\test\This is mine\my_ai_project")
ASSET_DIR = PROJECT_ROOT / "Model Core" / "Weighting file (core fuel)" / "Character" / "K1 Portrait"
LAYERS_DIR = ASSET_DIR / "layers"
PARTS_JSON = ASSET_DIR / "parts.json"


def main() -> int:
    manifest = json.loads(PARTS_JSON.read_text(encoding="utf-8"))
    w, h = manifest["canvas"]
    z_layers = sorted(
        manifest["layers"].items(),
        key=lambda kv: kv[1]["z_order"],
    )

    composed = np.zeros((h, w, 4), dtype=np.uint8)
    for name, info in z_layers:
        layer = np.asarray(Image.open(LAYERS_DIR / info["file"]).convert("RGBA"))
        # 半透明叠加（z 序在前的覆盖）
        alpha = layer[..., 3:4].astype(np.float32) / 255.0
        composed[..., :3] = (
            layer[..., :3] * alpha + composed[..., :3] * (1 - alpha)
        ).astype(np.uint8)
        composed[..., 3:] = np.maximum(composed[..., 3:], layer[..., 3:])

    light_bg = composed.copy()
    light_bg[..., 3] = 255
    dark_bg = composed.copy()
    dark_bg[..., 3] = 255
    dark_bg[..., :3] = (dark_bg[..., :3].astype(np.float32) * (dark_bg[..., 3:4] / 255.0) + 30 * (1 - dark_bg[..., 3:4] / 255.0)).astype(np.uint8)
    dark_bg[..., 3] = 255

    # 缩略到 480 宽便于拼图
    def shrink(img: Image.Image, width: int = 480) -> Image.Image:
        ratio = width / img.width
        return img.resize((width, int(img.height * ratio)), Image.LANCZOS)

    src_img = shrink(Image.open(ASSET_DIR / manifest["source"]).convert("RGB"))
    light_img = shrink(Image.fromarray(light_bg, "RGBA").convert("RGB"))
    dark_img = shrink(Image.fromarray(dark_bg, "RGBA").convert("RGB"))

    canvas = Image.new("RGB", (src_img.width * 3 + 24, src_img.height + 8), (240, 240, 240))
    canvas.paste(src_img, (0, 0))
    canvas.paste(light_img, (src_img.width + 12, 0))
    canvas.paste(dark_img, (src_img.width * 2 + 24, 0))
    out = ASSET_DIR / "k2_compose_preview.png"
    canvas.save(out)
    print(f"验收演示: {out}", flush=True)
    print(f"z 序: {[(n, i['z_order']) for n, i in z_layers]}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
