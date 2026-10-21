"""C 收官命题③月下·霓影月 v3：按墨灵第二轮意见迭代。

墨灵第二轮（design_moon_final.json）：satisfied=false，"增加星点密度到 800 颗"。
v3 改动：星点 520→800（墨灵明示数值），其余保持 v2（月晕三层、云纱四组、银光细线）。
输出 m13_texture_moon_v3.jpg，注册表指向 v3。
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


def _moon_halo(n: int = TILE) -> np.ndarray:
    rng = np.random.RandomState(7)
    y, x = np.mgrid[0:n, 0:n].astype(np.float64)
    cx, cy = int(rng.uniform(0, n)), int(rng.uniform(0, n))
    dx = np.abs(x - cx)
    dx = np.minimum(dx, n - dx)
    dy = np.abs(y - cy)
    dy = np.minimum(dy, n - dy)
    d2 = dx * dx + dy * dy
    return (1.15 * np.exp(-d2 / (2.0 * (n * 0.10) ** 2))
            + 0.85 * np.exp(-d2 / (2.0 * (n * 0.22) ** 2))
            + 0.45 * np.exp(-d2 / (2.0 * (n * 0.38) ** 2)))


def _stars_v3(n: int = TILE) -> np.ndarray:
    """星点 v3：800 颗（墨灵明示数值），混合大小。"""
    rng = np.random.RandomState(883)
    y, x = np.mgrid[0:n, 0:n].astype(np.float64)
    out = np.zeros_like(x, dtype=np.float64)
    for _ in range(800):
        cx, cy = int(rng.uniform(0, n)), int(rng.uniform(0, n))
        if rng.uniform() < 0.05:
            sigma = rng.uniform(7.0, 12.0)
            amp = 0.9
        else:
            sigma = rng.uniform(1.6, 3.6)
            amp = rng.uniform(0.75, 1.0)
        dx = np.abs(x - cx)
        dx = np.minimum(dx, n - dx)
        dy = np.abs(y - cy)
        dy = np.minimum(dy, n - dy)
        d2 = dx * dx + dy * dy
        out += amp * np.exp(-d2 / (2.0 * sigma * sigma))
    return out


def _cloud_veil(n: int = TILE) -> np.ndarray:
    y, x = np.mgrid[0:n, 0:n].astype(np.float64)
    out = np.zeros((n, n), dtype=np.float64)
    for freq, phase, amp, tilt in (
        (1.5, 0.6, 0.18, 1.0),
        (2.6, 1.9, 0.13, -0.7),
        (4.0, 3.2, 0.09, 0.4),
        (6.0, 4.4, 0.06, -0.3),
    ):
        axis = (x + tilt * y) % n
        wave = 0.5 + 0.5 * np.sin(2.0 * np.pi * freq * axis / n + phase)
        out += amp * np.power(wave, 3.0)
    return out


def _silver_fine(n: int = TILE) -> np.ndarray:
    y, x = np.mgrid[0:n, 0:n].astype(np.float64)
    out = np.zeros((n, n), dtype=np.float64)
    for freq, phase, amp in ((9.0, 0.3, 0.12), (13.0, 1.9, 0.09)):
        t = ((x * 0.9 + y * 1.1) % n) / n
        out += amp * np.power(0.5 + 0.5 * np.sin(2.0 * np.pi * freq * t + phase), 5.0)
    return out


def _moon_silver_v3() -> np.ndarray:
    img = _radial_gradient(TILE * 0.5, TILE * 0.5,
                           inner=(0.06, 0.10, 0.22), outer=(0.02, 0.03, 0.08))
    halo = _moon_halo()
    stars = _stars_v3()
    veil = _cloud_veil()
    fine = _silver_fine()
    for c in range(3):
        base = img[..., c]
        base = base + halo * (1.05 if c < 2 else 1.2)
        base = base + stars * (0.95 if c == 2 else 0.85)
        base = base + veil * (0.10 if c == 2 else 0.06)
        base = base + fine * (0.30 if c == 2 else 0.22)
        img[..., c] = np.clip(base, 0.0, 1.0)
    silver = np.array([215 / 255, 245 / 255, 255 / 255])
    img = img * 0.72 + silver[None, None, :] * 0.28
    return img


def main() -> int:
    img = _moon_silver_v3()
    arr = (np.clip(img, 0.0, 1.0) * 255.0).astype(np.uint8)
    out = os.path.join(HERE, "m13_texture_moon_v3.jpg")
    Image.fromarray(arr, mode="RGB").save(out, quality=92)

    with FileLock(REGISTRY_PATH):
        with open(REGISTRY_PATH, encoding="utf-8") as f:
            registry = json.load(f)
        for o in registry["outfits"]:
            if o["id"] == "moon":
                o["texture"] = "m13_texture_moon_v3.jpg"
                o["desc"] = "霓影月·月光银白静谧月夜（C 收官命题③·墨灵执行者代码·v3 星点 800）"
        with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump(registry, f, ensure_ascii=False, indent=2)

    print(json.dumps({
        "v3": True, "outfit": "moon", "texture": os.path.basename(out),
        "changes": ["星点 520→800（墨灵明示数值）"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
