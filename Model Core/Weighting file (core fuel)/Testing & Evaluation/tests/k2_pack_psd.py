"""K2 打包：部件层 → 可编辑 PSD（人工精修工作台）。

图层结构（自底向上）：
0. 参考定稿（baseline_v5_0_raw.png，50% 不透明度，仅作描边参考）
1..7. 部件层（face/hair/mouth/eye/hand/boots/cloth，与 parts.json z 序一致）

用法：python k2_pack_psd.py
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

ZH_NAMES = {
    "face": "01_face_skin",
    "hair": "02_hair",
    "mouth": "03_mouth",
    "eye": "04_eye",
    "boots": "05_boots",
    "cloth": "06_cloth",
}


def build_psd() -> None:
    manifest = json.loads(PARTS_JSON.read_text(encoding="utf-8"))
    w, h = manifest["canvas"]
    z_layers = sorted(manifest["layers"].items(), key=lambda kv: kv[1]["z_order"])

    from psd_tools import PSDImage

    psd = PSDImage.new(mode="RGBA", size=(w, h))

    # 逆序创建（新层总在最顶）：先建最上层 cloth，最后建参考底图
    for name, info in reversed(z_layers):
        arr = Image.open(LAYERS_DIR / info["file"]).convert("RGBA")
        psd.create_pixel_layer(arr, name=ZH_NAMES.get(name, name))

    # 参考底图（半透明，最底）
    ref = Image.open(ASSET_DIR / manifest["source"]).convert("RGBA")
    ref.putalpha(ref.getchannel("A").point(lambda a: a // 2))
    psd.create_pixel_layer(ref, name="00_ref_baseline_locked")

    out = ASSET_DIR / "k2_refine_workspace.psd"
    psd.save(out)
    print(f"PSD 已生成: {out}（{w}x{h}，{len(z_layers) + 1} 层）", flush=True)
    print(f"图层（自底向上）: {['00_ref_baseline_locked'] + [ZH_NAMES.get(n, n) for n, _ in z_layers]}", flush=True)
    return 0


def main() -> int:
    return build_psd()


if __name__ == "__main__":
    sys.exit(main())
