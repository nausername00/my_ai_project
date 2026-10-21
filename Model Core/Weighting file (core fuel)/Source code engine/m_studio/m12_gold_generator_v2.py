"""C 收官命题②鎏金 v2：执行者按墨灵自评意见迭代贴图。

墨灵自评意见（design_gold_review.json）：
  1. 古铜色偏暖一点，更贴近鎏金
  2. 增加鎏金饱和度和明度，更亮眼
  3. 金箔均匀分布在所有鎏金区域

v2 改动：
  - 底色偏暖饱和（内 0.90,0.65,0.18 / 外 0.40,0.24,0.06）
  - 熔金流纹更宽更亮（pow 2.6→2.2，amp 提高）
  - 金箔改为网格化均匀采样（每格 2-3 片，全域均匀）
  - 浮雕暗纹减量（避免压暗）
  - 全局提亮 1.15
输出 m12_texture_gold_v2.jpg，注册表指向 v2。
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


def _molten_streams(n: int = TILE) -> np.ndarray:
    y, x = np.mgrid[0:n, 0:n].astype(np.float64)
    out = np.zeros((n, n), dtype=np.float64)
    for freq, phase, amp, tilt in (
        (2.0, 0.4, 0.44, 1.0),
        (3.0, 1.6, 0.32, -0.8),
        (4.5, 2.8, 0.22, 0.5),
    ):
        axis = (x + tilt * y) % n
        wave = 0.5 + 0.5 * np.sin(2.0 * np.pi * freq * axis / n + phase)
        out += amp * np.power(wave, 2.2)
    return out


def _gold_flakes_uniform(n: int = TILE) -> np.ndarray:
    """金箔 v2：网格化均匀采样（每 256px 格内 2-3 片 → 全域均匀分布）。"""
    rng = np.random.RandomState(520)
    y, x = np.mgrid[0:n, 0:n].astype(np.float64)
    out = np.zeros_like(x, dtype=np.float64)
    cell = 256
    for gx in range(0, n, cell):
        for gy in range(0, n, cell):
            count = int(rng.uniform(2, 4))
            for _ in range(count):
                cx = (gx + rng.uniform(20, cell - 20)) % n
                cy = (gy + rng.uniform(20, cell - 20)) % n
                sigma = rng.uniform(2.4, 5.0)
                dx = np.abs(x - cx)
                dx = np.minimum(dx, n - dx)
                dy = np.abs(y - cy)
                dy = np.minimum(dy, n - dy)
                d2 = dx * dx + dy * dy
                out += rng.uniform(0.85, 1.0) * np.exp(-d2 / (2.0 * sigma * sigma))
    return out


def _relief_dark_lines(n: int = TILE) -> np.ndarray:
    y, x = np.mgrid[0:n, 0:n].astype(np.float64)
    grid = np.zeros((n, n), dtype=np.float64)
    for freq, phase, amp in ((3.0, 0.8, 0.12), (5.0, 2.2, 0.09), (7.0, 4.1, 0.07)):
        t = ((x * 0.8 + y * 1.2) % n) / n
        grid += amp * np.power(0.5 + 0.5 * np.sin(2.0 * np.pi * freq * t + phase), 6.0)
    return grid


def _amber_glow(n: int = TILE) -> np.ndarray:
    y, x = np.mgrid[0:n, 0:n].astype(np.float64)
    glow = _radial_gradient(TILE * 0.5, TILE * 0.5, (0.0, 0.0, 0.0), (0.50, 0.36, 0.12))
    shafts = np.zeros((n, n), dtype=np.float64)
    for freq, phase, amp in ((1.0, 0.5, 0.20), (2.0, 1.8, 0.12)):
        t = ((x * 1.3 + y * 0.6) % n) / n
        shafts += amp * (0.5 + 0.5 * np.sin(2.0 * np.pi * freq * t + phase))
    return glow + shafts[..., None]


def _molten_gold_v2() -> np.ndarray:
    img = _radial_gradient(TILE * 0.5, TILE * 0.5,
                           inner=(0.90, 0.65, 0.18), outer=(0.40, 0.24, 0.06))
    streams = _molten_streams()
    flakes = _gold_flakes_uniform()
    relief = _relief_dark_lines()
    amber = _amber_glow()[..., 0]
    for c in range(3):
        base = img[..., c]
        base = base + streams * (0.42 if c < 2 else 0.22)
        base = base + flakes * (1.0 if c == 0 else 0.92 if c == 1 else 0.58)
        base = base + amber * (0.13 if c == 2 else 0.07)
        base = base - relief * (0.24 if c == 2 else 0.16)
        base = base * 1.15
        img[..., c] = np.clip(base, 0.0, 1.0)
    return img


def main() -> int:
    img = _molten_gold_v2()
    arr = (np.clip(img, 0.0, 1.0) * 255.0).astype(np.uint8)
    out = os.path.join(HERE, "m12_texture_gold_v2.jpg")
    Image.fromarray(arr, mode="RGB").save(out, quality=92)

    with FileLock(REGISTRY_PATH):
        with open(REGISTRY_PATH, encoding="utf-8") as f:
            registry = json.load(f)
        for o in registry["outfits"]:
            if o["id"] == "gold":
                o["texture"] = "m12_texture_gold_v2.jpg"
                o["desc"] = "鎏金幻影·晚霞镀金幻化成蝶（C 收官命题②·墨灵原创设计 v2 暖亮均匀）"
        with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump(registry, f, ensure_ascii=False, indent=2)

    print(json.dumps({
        "v2": True, "outfit": "gold", "texture": os.path.basename(out),
        "changes": ["底色偏暖饱和", "熔金流纹更宽亮", "金箔网格化均匀分布",
                    "浮雕暗纹减量", "全局提亮 1.15"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
