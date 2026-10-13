"""K2 逐层预览：每层独立显示在深色背景上，便于目视检查每层实际内容。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ASSET_DIR = Path(r"D:\Coding\code program\test\This is mine\my_ai_project\Model Core\Weighting file (core fuel)\Character\K1 Portrait")
LAYERS_DIR = ASSET_DIR / "layers"


def main() -> int:
    manifest = json.loads((ASSET_DIR / "parts.json").read_text(encoding="utf-8"))
    w, h = manifest["canvas"]
    z_layers = sorted(manifest["layers"].items(), key=lambda kv: kv[1]["z_order"])

    thumb_w = 256
    thumb_h = int(h * thumb_w / w)
    cell = thumb_w + 12
    n = len(z_layers)
    canvas = Image.new("RGB", (cell * n + 8, thumb_h + 40), (30, 30, 30))

    for i, (name, info) in enumerate(z_layers):
        layer = Image.open(LAYERS_DIR / info["file"]).convert("RGBA").resize(
            (thumb_w, thumb_h), Image.LANCZOS
        )
        bg = Image.new("RGBA", layer.size, (30, 30, 30, 255))
        comp = Image.alpha_composite(bg, layer).convert("RGB")
        canvas.paste(comp, (8 + i * cell, 24))
    out = ASSET_DIR / "k2_layer_preview.png"
    canvas.save(out)
    print(f"逐层预览: {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
