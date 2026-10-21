"""C 收官命题①深海 v2：执行者按墨灵自评意见迭代贴图。

墨灵自评意见（design_deep_sea_review.json）：
  1. 增加颜色对比度，提高元素细节辨识度
  2. 更亮的材质/贴图，改善整体观感
  3. 元素添加反光/高光效果，增加细节可见性

v2 改动：
  - 底色提亮（内 0.06,0.16,0.32 / 外 0.03,0.08,0.18）
  - 海浪亮纹更宽更亮（pow 指数 3.0→2.4，amp 增大）
  - 鱼群剪影淡蓝白化、更清晰（amp 提高）
  - 气泡/珍珠更亮（珍珠 0.65→0.85）
  - 新增银色流苏亮线（整数周期对角细亮线，呼应墨灵"银色流苏"设计）
  - 全局提亮 1.10
输出新文件名 m11_texture_deep_sea_v2.jpg（避免命中旧渲染缓存），并更新注册表指向 v2。
"""
from __future__ import annotations

import json
import os

import numpy as np
from PIL import Image

from m_studio.lock_utils import FileLock

HERE = os.path.dirname(os.path.abspath(__file__))
REGISTRY_PATH = os.path.join(HERE, "fashion_registry.json")
TILE = 2048
_RS = np.random.RandomState(202610212)  # v2 新种子：图案位置变化


def _tile_distance(x: np.ndarray, y: np.ndarray, centers: list[tuple[int, int]],
                   sigma: float, amp: float, n: int = TILE) -> np.ndarray:
    out = np.zeros_like(x, dtype=np.float64)
    for cx, cy in centers:
        dx = np.abs(x - cx)
        dx = np.minimum(dx, n - dx)
        dy = np.abs(y - cy)
        dy = np.minimum(dy, n - dy)
        d2 = dx * dx + dy * dy
        out += amp * np.exp(-d2 / (2.0 * sigma * sigma))
    return out


def _radial_gradient(cx: float, cy: float, inner: tuple[float, float, float],
                     outer: tuple[float, float, float], n: int = TILE) -> np.ndarray:
    y, x = np.mgrid[0:n, 0:n].astype(np.float64)
    dx = np.abs(x - cx)
    dx = np.minimum(dx, n - dx)
    dy = np.abs(y - cy)
    dy = np.minimum(dy, n - dy)
    dist = np.sqrt(dx * dx + dy * dy) / (n * 0.5)
    dist = np.clip(dist, 0.0, 1.0)
    img = np.zeros((n, n, 3), dtype=np.float64)
    for c in range(3):
        img[..., c] = inner[c] * (1.0 - dist) + outer[c] * dist
    return img


def _wave_bands(n: int = TILE) -> np.ndarray:
    """海浪亮纹 v2：亮线更宽更亮（pow 2.4 + 更大 amp）。"""
    y, x = np.mgrid[0:n, 0:n].astype(np.float64)
    bands = np.zeros((n, n), dtype=np.float64)
    for freq, phase, amp, tilt in (
        (1.6, 0.0, 0.42, 1.0),
        (2.4, 1.1, 0.30, -0.7),
        (3.8, 2.3, 0.22, 0.4),
    ):
        axis = (x + tilt * y) % n
        wave = 0.5 + 0.5 * np.sin(2.0 * np.pi * freq * axis / n + phase)
        bands += amp * np.power(wave, 2.4)
    return bands


def _silver_fringes(n: int = TILE) -> np.ndarray:
    """银色流苏亮线：多组斜向细亮线（整数周期对角 → 无缝），呼应墨灵设计。"""
    y, x = np.mgrid[0:n, 0:n].astype(np.float64)
    out = np.zeros((n, n), dtype=np.float64)
    for freq, phase, amp in ((6.0, 0.3, 0.20), (9.0, 1.7, 0.16), (13.0, 3.1, 0.12)):
        t = ((x * 0.9 + y * 1.1) % n) / n
        out += amp * np.power(0.5 + 0.5 * np.sin(2.0 * np.pi * freq * t + phase), 5.0)
    return out


def _fish_silhouettes(count: int = 20, n: int = TILE) -> np.ndarray:
    """鱼群剪影 v2：淡蓝白化（对比度更高），数量更多。"""
    rng = np.random.RandomState(9)
    y, x = np.mgrid[0:n, 0:n].astype(np.float64)
    out = np.zeros_like(x, dtype=np.float64)
    for _ in range(count):
        cx, cy = int(rng.uniform(0, n)), int(rng.uniform(0, n))
        ang = rng.uniform(0, 2 * np.pi)
        length = rng.uniform(100, 230)
        width = rng.uniform(32, 62)
        ca, sa = np.cos(ang), np.sin(ang)
        dx = (x - cx) * ca + (y - cy) * sa
        dy = -(x - cx) * sa + (y - cy) * ca
        dx = np.minimum(np.abs(dx), n - np.abs(dx))
        dy = np.minimum(np.abs(dy), n - np.abs(dy))
        d2 = (dx / length) ** 2 + (dy / width) ** 2
        out += np.clip(1.0 - d2, 0.0, 1.0) ** 2 * 0.62
    return out


def _bubbles_pearls(n: int = TILE) -> tuple[np.ndarray, np.ndarray]:
    """气泡 + 珍珠 v2：更亮。"""
    rng = np.random.RandomState(21)
    y, x = np.mgrid[0:n, 0:n].astype(np.float64)
    bubbles = _tile_distance(x, y,
                             [(int(rng.uniform(0, n)), int(rng.uniform(0, n))) for _ in range(80)],
                             sigma=11.0, amp=0.72)
    pearls = _tile_distance(x, y,
                            [(int(rng.uniform(0, n)), int(rng.uniform(0, n))) for _ in range(180)],
                            sigma=3.4, amp=0.92)
    return bubbles, pearls


def _light_shafts(n: int = TILE) -> np.ndarray:
    """海底光斑 v2：更亮。"""
    y, x = np.mgrid[0:n, 0:n].astype(np.float64)
    glow = _radial_gradient(TILE * 0.5, TILE * 0.5, (0.0, 0.0, 0.0), (0.24, 0.30, 0.16))
    shafts = np.zeros((n, n), dtype=np.float64)
    for freq, phase, amp in ((1.0, 0.5, 0.14), (2.0, 1.8, 0.09)):
        t = ((x * 1.3 + y * 0.6) % n) / n
        shafts += amp * (0.5 + 0.5 * np.sin(2.0 * np.pi * freq * t + phase))
    return glow + shafts[..., None]


def _deep_sea_v2() -> np.ndarray:
    img = _radial_gradient(TILE * 0.5, TILE * 0.5,
                           inner=(0.06, 0.16, 0.32), outer=(0.03, 0.08, 0.18))
    waves = _wave_bands()
    fringes = _silver_fringes()
    fish = _fish_silhouettes()
    bubbles, pearls = _bubbles_pearls()
    light = _light_shafts()[..., 0]
    for c in range(3):
        base = img[..., c]
        base = base + waves * (0.13 + 0.07 * c)
        base = base + fringes * (0.30 if c == 2 else 0.20)   # 银色流苏：蓝白亮线
        base = base + light * (0.13 if c == 2 else 0.07)
        base = base + fish * (0.16 if c == 2 else 0.08)
        base = base + bubbles * (0.38 if c == 2 else 0.28)
        base = base + pearls * 0.85
        img[..., c] = np.clip(base * 1.10, 0.0, 1.0)          # 全局提亮
    return img


def main() -> int:
    img = _deep_sea_v2()
    arr = (np.clip(img, 0.0, 1.0) * 255.0).astype(np.uint8)
    out = os.path.join(HERE, "m11_texture_deep_sea_v2.jpg")
    Image.fromarray(arr, mode="RGB").save(out, quality=92)

    with FileLock(REGISTRY_PATH):
        with open(REGISTRY_PATH, encoding="utf-8") as f:
            registry = json.load(f)
        for o in registry["outfits"]:
            if o["id"] == "deep_sea":
                o["texture"] = "m11_texture_deep_sea_v2.jpg"
                o["desc"] = "幽冥舞·深海的幽灵舞者（C 收官命题①·墨灵原创设计 v2 提亮）"
        with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump(registry, f, ensure_ascii=False, indent=2)

    print(json.dumps({
        "v2": True, "outfit": "deep_sea", "texture": os.path.basename(out),
        "changes": ["底色提亮", "海浪亮纹加宽", "鱼群剪影淡蓝白化",
                    "气泡珍珠更亮", "新增银色流苏亮线", "全局提亮 1.10"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
