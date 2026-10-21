"""C 收官命题①深海 v3：执行者按墨灵第二轮意见再迭代。

墨灵第二轮（design_deep_sea_final.json）：
  satisfied=false，原因"深蓝色仍稍显暗淡"，要求提高颜色对比度、增强视觉冲击。

v3 改动：
  - 底色再提亮（内 0.10,0.24,0.44 / 外 0.05,0.12,0.26）
  - 海浪亮纹 amp 再提、更白亮
  - 鱼群剪影白亮化（B 通道 amp 0.16→0.30）
  - 气泡珍珠更大更亮（气泡 sigma 12 amp 0.85 / 珍珠 sigma 3.8 amp 1.0）
  - 银色流苏 amp 提高
  - 全局提亮 1.18 + 对比度拉伸（白点上限更亮）
输出 m11_texture_deep_sea_v3.jpg，注册表指向 v3。
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
_RS = np.random.RandomState(202610213)


def _tile_distance(x, y, centers, sigma, amp, n: int = TILE) -> np.ndarray:
    out = np.zeros_like(x, dtype=np.float64)
    for cx, cy in centers:
        dx = np.abs(x - cx)
        dx = np.minimum(dx, n - dx)
        dy = np.abs(y - cy)
        dy = np.minimum(dy, n - dy)
        d2 = dx * dx + dy * dy
        out += amp * np.exp(-d2 / (2.0 * sigma * sigma))
    return out


def _radial_gradient(cx, cy, inner, outer, n: int = TILE) -> np.ndarray:
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
    y, x = np.mgrid[0:n, 0:n].astype(np.float64)
    bands = np.zeros((n, n), dtype=np.float64)
    for freq, phase, amp, tilt in (
        (1.6, 0.0, 0.50, 1.0),
        (2.4, 1.1, 0.36, -0.7),
        (3.8, 2.3, 0.26, 0.4),
    ):
        axis = (x + tilt * y) % n
        wave = 0.5 + 0.5 * np.sin(2.0 * np.pi * freq * axis / n + phase)
        bands += amp * np.power(wave, 2.2)
    return bands


def _silver_fringes(n: int = TILE) -> np.ndarray:
    y, x = np.mgrid[0:n, 0:n].astype(np.float64)
    out = np.zeros((n, n), dtype=np.float64)
    for freq, phase, amp in ((6.0, 0.3, 0.30), (9.0, 1.7, 0.24), (13.0, 3.1, 0.18)):
        t = ((x * 0.9 + y * 1.1) % n) / n
        out += amp * np.power(0.5 + 0.5 * np.sin(2.0 * np.pi * freq * t + phase), 4.5)
    return out


def _fish_silhouettes(count: int = 22, n: int = TILE) -> np.ndarray:
    rng = np.random.RandomState(9)
    y, x = np.mgrid[0:n, 0:n].astype(np.float64)
    out = np.zeros_like(x, dtype=np.float64)
    for _ in range(count):
        cx, cy = int(rng.uniform(0, n)), int(rng.uniform(0, n))
        ang = rng.uniform(0, 2 * np.pi)
        length = rng.uniform(110, 240)
        width = rng.uniform(34, 66)
        ca, sa = np.cos(ang), np.sin(ang)
        dx = (x - cx) * ca + (y - cy) * sa
        dy = -(x - cx) * sa + (y - cy) * ca
        dx = np.minimum(np.abs(dx), n - np.abs(dx))
        dy = np.minimum(np.abs(dy), n - np.abs(dy))
        d2 = (dx / length) ** 2 + (dy / width) ** 2
        out += np.clip(1.0 - d2, 0.0, 1.0) ** 2 * 0.72
    return out


def _bubbles_pearls(n: int = TILE) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.RandomState(21)
    y, x = np.mgrid[0:n, 0:n].astype(np.float64)
    bubbles = _tile_distance(x, y,
                             [(int(rng.uniform(0, n)), int(rng.uniform(0, n))) for _ in range(85)],
                             sigma=12.0, amp=0.85)
    pearls = _tile_distance(x, y,
                            [(int(rng.uniform(0, n)), int(rng.uniform(0, n))) for _ in range(190)],
                            sigma=3.8, amp=1.0)
    return bubbles, pearls


def _light_shafts(n: int = TILE) -> np.ndarray:
    y, x = np.mgrid[0:n, 0:n].astype(np.float64)
    glow = _radial_gradient(TILE * 0.5, TILE * 0.5, (0.0, 0.0, 0.0), (0.30, 0.36, 0.20))
    shafts = np.zeros((n, n), dtype=np.float64)
    for freq, phase, amp in ((1.0, 0.5, 0.18), (2.0, 1.8, 0.12)):
        t = ((x * 1.3 + y * 0.6) % n) / n
        shafts += amp * (0.5 + 0.5 * np.sin(2.0 * np.pi * freq * t + phase))
    return glow + shafts[..., None]


def _deep_sea_v3() -> np.ndarray:
    img = _radial_gradient(TILE * 0.5, TILE * 0.5,
                           inner=(0.10, 0.24, 0.44), outer=(0.05, 0.12, 0.26))
    waves = _wave_bands()
    fringes = _silver_fringes()
    fish = _fish_silhouettes()
    bubbles, pearls = _bubbles_pearls()
    light = _light_shafts()[..., 0]
    for c in range(3):
        base = img[..., c]
        base = base + waves * (0.16 + 0.09 * c)
        base = base + fringes * (0.42 if c == 2 else 0.28)
        base = base + light * (0.16 if c == 2 else 0.09)
        base = base + fish * (0.30 if c == 2 else 0.14)
        base = base + bubbles * (0.48 if c == 2 else 0.34)
        base = base + pearls * 1.0
        # 对比度拉伸：亮部更亮
        base = base * 1.18
        img[..., c] = np.clip(base, 0.0, 1.0)
    return img


def main() -> int:
    img = _deep_sea_v3()
    arr = (np.clip(img, 0.0, 1.0) * 255.0).astype(np.uint8)
    out = os.path.join(HERE, "m11_texture_deep_sea_v3.jpg")
    Image.fromarray(arr, mode="RGB").save(out, quality=92)

    with FileLock(REGISTRY_PATH):
        with open(REGISTRY_PATH, encoding="utf-8") as f:
            registry = json.load(f)
        for o in registry["outfits"]:
            if o["id"] == "deep_sea":
                o["texture"] = "m11_texture_deep_sea_v3.jpg"
                o["desc"] = "幽冥舞·深海的幽灵舞者（C 收官命题①·墨灵原创设计 v3 强对比）"
        with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump(registry, f, ensure_ascii=False, indent=2)

    print(json.dumps({
        "v3": True, "outfit": "deep_sea", "texture": os.path.basename(out),
        "changes": ["底色再提亮", "海浪/流苏/鱼群更强", "气泡珍珠更大更亮",
                    "对比度拉伸 1.18"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
