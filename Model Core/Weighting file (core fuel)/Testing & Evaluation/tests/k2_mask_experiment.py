"""实验 v2：isnet 蒙版种子 + 有限扩张构建人物蒙版。

组合策略：
1. isnet 蒙版为核心种子（覆盖人物主体）
2. 有限迭代扩张：吸收与蒙版 8-邻域相邻、且不是"纯白/灰白背景"和"高红装饰"的像素
3. 背景装饰（灰白、红线）归 bg 层，人物层不吸收
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image
from rembg import new_session, remove
from scipy import ndimage

ASSET_DIR = Path(r"D:\Coding\code program\test\This is mine\my_ai_project\Model Core\Weighting file (core fuel)\Character\K1 Portrait")
RAW = ASSET_DIR / "baseline_v5_0_raw.png"

FACE_BAND_X = (0.28, 0.72)
FACE_BAND_Y = (0.16, 0.50)
MAX_EXPAND_ITER = 12


def build_mask(rgb: np.ndarray, person_mask: np.ndarray) -> np.ndarray:
    h, w = rgb.shape[:2]
    r, g, b = rgb[..., 0].astype(np.int16), rgb[..., 1].astype(np.int16), rgb[..., 2].astype(np.int16)
    gray = rgb.mean(axis=2).astype(np.int16)

    high_red = (r > g + 50) & (r > b + 50)
    face_band = np.zeros((h, w), dtype=bool)
    face_band[int(h * FACE_BAND_Y[0]) : int(h * FACE_BAND_Y[1]), int(w * FACE_BAND_X[0]) : int(w * FACE_BAND_X[1])] = True
    decoration = high_red & ~face_band

    # 近白背景（纯白或灰白）：不吸收
    whitish = (gray > 175) & (abs(r - g) < 30) & (abs(g - b) < 30) & (abs(r - b) < 30)

    seed = person_mask.astype(bool)
    mask = seed.copy()
    absorbable = ~decoration & ~whitish
    structure = np.ones((3, 3), dtype=bool)
    for _ in range(MAX_EXPAND_ITER):
        grown = ndimage.binary_dilation(mask, structure=structure) & absorbable
        mask |= grown
    return mask.astype(np.uint8)


def main() -> int:
    image = Image.open(RAW).convert("RGB")
    rgb = np.asarray(image)
    h, w = rgb.shape[:2]

    out = remove(image.convert("RGBA"), session=new_session("isnet-general-use"))
    alpha = np.asarray(out.getchannel("A"), dtype=np.float32) / 255.0
    isnet_coverage = int(np.count_nonzero(alpha > 0.5)) / (h * w) * 100
    print(f"isnet 蒙版: {int(np.count_nonzero(alpha > 0.5))} px ({isnet_coverage:.1f}%)", flush=True)

    mask = build_mask(rgb, alpha > 0.5)
    coverage = int(np.count_nonzero(mask)) / (h * w) * 100
    print(f"扩张后人物蒙版: {int(np.count_nonzero(mask))} px ({coverage:.1f}%)", flush=True)

    preview = np.zeros((h, w, 4), dtype=np.uint8)
    preview[..., :3] = rgb
    preview[..., 3] = mask * 255
    Image.fromarray(preview, "RGBA").save(ASSET_DIR / "_exp_mask_isnet.png")
    print(f"蒙版预览: {ASSET_DIR / '_exp_mask_isnet.png'}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
