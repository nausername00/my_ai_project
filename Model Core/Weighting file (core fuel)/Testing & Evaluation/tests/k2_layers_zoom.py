"""K2 逐层大图：每层按 bbox 裁剪放大到 400px 宽，单独输出便于目视。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

ASSET_DIR = Path(r"D:\Coding\code program\test\This is mine\my_ai_project\Model Core\Weighting file (core fuel)\Character\K1 Portrait")
LAYERS_DIR = ASSET_DIR / "layers"
OUT_DIR = ASSET_DIR / "layer_zoom"


def main() -> int:
    manifest = json.loads((ASSET_DIR / "parts.json").read_text(encoding="utf-8"))
    OUT_DIR.mkdir(exist_ok=True)
    for name, info in manifest["layers"].items():
        layer = Image.open(LAYERS_DIR / info["file"]).convert("RGBA")
        x0, y0, x1, y1 = info["bbox"]
        crop = layer.crop((x0, y0, x1 + 1, y1 + 1))
        target_w = 400
        ratio = target_w / crop.width
        crop = crop.resize((target_w, max(1, int(crop.height * ratio))), Image.LANCZOS)
        crop.save(OUT_DIR / f"{name}_zoom.png")
        print(f"{name}: bbox={info['bbox']} px={info['pixels']} -> zoom {crop.size}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
