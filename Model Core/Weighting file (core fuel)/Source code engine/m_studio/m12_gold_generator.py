"""C 收官命题②鎏金·鎏金幻影 v1：执行者按墨灵设计稿实现贴图。

墨灵设计稿（design_gold_meng.json）：
  name=鎏金幻影 · tone=鎏金[233,136,11]（0-255 → 归一化 0.91,0.53,0.04）
  style=熔金流纹+金箔碎屑+浮雕暗纹+古器质感
  expect=鎏金渐变底+熔金流纹+金箔碎屑+浮雕暗纹+琥珀暖光

程序化元素（全无缝：环面距离 + 整数周期正弦）：
  - 鎏金渐变底（内亮金→外深琥珀）
  - 熔金流纹（多向金色亮纹）
  - 金箔碎屑（小亮片，暖白金）
  - 浮雕暗纹（暗红棕低频网格纹）
  - 琥珀暖光（径向暖光 + 斜向光柱）
输出 m12_texture_gold.jpg；注册 outfit gold + tone molten_gold。
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
_RS = np.random.RandomState(202610221)


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
    """熔金流纹：多向暖白金亮纹（整数周期 → 无缝）。"""
    y, x = np.mgrid[0:n, 0:n].astype(np.float64)
    out = np.zeros((n, n), dtype=np.float64)
    for freq, phase, amp, tilt in (
        (2.0, 0.4, 0.34, 1.0),
        (3.0, 1.6, 0.24, -0.8),
        (4.5, 2.8, 0.16, 0.5),
    ):
        axis = (x + tilt * y) % n
        wave = 0.5 + 0.5 * np.sin(2.0 * np.pi * freq * axis / n + phase)
        out += amp * np.power(wave, 2.6)
    return out


def _gold_flakes(count: int = 170, n: int = TILE) -> np.ndarray:
    """金箔碎屑：小亮片，暖白金（高亮）。"""
    rng = np.random.RandomState(52)
    y, x = np.mgrid[0:n, 0:n].astype(np.float64)
    out = np.zeros_like(x, dtype=np.float64)
    for _ in range(count):
        cx, cy = int(rng.uniform(0, n)), int(rng.uniform(0, n))
        sigma = rng.uniform(2.2, 4.6)
        dx = np.abs(x - cx)
        dx = np.minimum(dx, n - dx)
        dy = np.abs(y - cy)
        dy = np.minimum(dy, n - dy)
        d2 = dx * dx + dy * dy
        out += rng.uniform(0.8, 1.0) * np.exp(-d2 / (2.0 * sigma * sigma))
    return out


def _relief_dark_lines(n: int = TILE) -> np.ndarray:
    """浮雕暗纹：低频暗红棕网格纹（减色用，取 0~1 表示暗纹强度）。"""
    y, x = np.mgrid[0:n, 0:n].astype(np.float64)
    grid = np.zeros((n, n), dtype=np.float64)
    for freq, phase, amp in ((3.0, 0.8, 0.16), (5.0, 2.2, 0.12), (7.0, 4.1, 0.09)):
        t = ((x * 0.8 + y * 1.2) % n) / n
        grid += amp * np.power(0.5 + 0.5 * np.sin(2.0 * np.pi * freq * t + phase), 6.0)
    return grid


def _amber_glow(n: int = TILE) -> np.ndarray:
    """琥珀暖光：径向暖光 + 斜向光柱。"""
    y, x = np.mgrid[0:n, 0:n].astype(np.float64)
    glow = _radial_gradient(TILE * 0.5, TILE * 0.5, (0.0, 0.0, 0.0), (0.42, 0.30, 0.10))
    shafts = np.zeros((n, n), dtype=np.float64)
    for freq, phase, amp in ((1.0, 0.5, 0.16), (2.0, 1.8, 0.10)):
        t = ((x * 1.3 + y * 0.6) % n) / n
        shafts += amp * (0.5 + 0.5 * np.sin(2.0 * np.pi * freq * t + phase))
    return glow + shafts[..., None]


def _molten_gold_v1() -> np.ndarray:
    img = _radial_gradient(TILE * 0.5, TILE * 0.5,
                           inner=(0.80, 0.60, 0.22), outer=(0.30, 0.18, 0.05))
    streams = _molten_streams()
    flakes = _gold_flakes()
    relief = _relief_dark_lines()
    amber = _amber_glow()[..., 0]
    for c in range(3):
        base = img[..., c]
        base = base + streams * (0.34 if c < 2 else 0.18)      # 熔金流纹：暖白金
        base = base + flakes * (0.95 if c == 0 else 0.88 if c == 1 else 0.55)  # 金箔：金亮
        base = base + amber * (0.10 if c == 2 else 0.05)       # 琥珀暖光
        base = base - relief * (0.30 if c == 2 else 0.22)      # 浮雕暗纹：暗红棕减色
        img[..., c] = np.clip(base, 0.0, 1.0)
    return img


def main() -> int:
    img = _molten_gold_v1()
    arr = (np.clip(img, 0.0, 1.0) * 255.0).astype(np.uint8)
    out = os.path.join(HERE, "m12_texture_gold.jpg")
    Image.fromarray(arr, mode="RGB").save(out, quality=92)

    with FileLock(REGISTRY_PATH):
        with open(REGISTRY_PATH, encoding="utf-8") as f:
            registry = json.load(f)
        ids = {o["id"] for o in registry["outfits"]}
        if "gold" not in ids:
            registry["outfits"].append({
                "id": "gold", "name": "鎏金幻影", "texture": "m12_texture_gold.jpg",
                "target": "body_ring",
                "desc": "鎏金幻影·晚霞镀金幻化成蝶（C 收官命题②·墨灵原创设计 v1）",
            })
        else:
            for o in registry["outfits"]:
                if o["id"] == "gold":
                    o["texture"] = "m12_texture_gold.jpg"
                    o["desc"] = "鎏金幻影·晚霞镀金幻化成蝶（C 收官命题②·墨灵原创设计 v1）"
        # 归一化墨灵给的 0-255 主色（233,136,11）→ 0-1
        registry["tones"]["molten_gold"] = [round(233 / 255, 4), round(136 / 255, 4), round(11 / 255, 4)]
        with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump(registry, f, ensure_ascii=False, indent=2)

    print(json.dumps({
        "outfit": "gold", "name": "鎏金幻影", "tone": "molten_gold",
        "tone_rgb_01": [round(233 / 255, 4), round(136 / 255, 4), round(11 / 255, 4)],
        "texture": os.path.basename(out),
        "elements": ["鎏金渐变底", "熔金流纹", "金箔碎屑", "浮雕暗纹", "琥珀暖光"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
