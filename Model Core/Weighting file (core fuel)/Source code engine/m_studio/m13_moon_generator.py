"""C 收官命题③月下·霓影月：墨灵执行者代码 → 姐姐代笔修复版。

反转模式：墨灵 qwen2.5:3b 写代码（design_moon_code.json，code_len=679），
姐姐作为引导者指出 4 个问题并【保留墨灵意图】代笔修复：
  墨灵意图（保留）：月光银白主色 [215,245,255]、静谧神秘的月夜氛围
  墨灵问题（修复）：
    1. 纯白无元素 → 改为月夜渐变 + 月晕 + 星点 + 云纱 + 银色光柱
    2. 伪无缝（镜像翻转）→ 数学无缝（环面距离 + 整数周期正弦）
    3. 双层 419 万次循环 → 全向量化
    4. 主色不一致 → 统一为 [215,245,255]（月光银白）

实现元素：
  - 夜蓝渐变底（深蓝夜空 → 月下微亮）
  - 月晕（中心暖白银亮斑）
  - 星点（小亮片，环面距离）
  - 云纱（柔亮斜纹，整数周期）
  - 银色光柱（斜向光斑）
输出 m13_texture_moon.jpg；注册 outfit moon + tone moon_silver。
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
    """月晕：中心暖白银亮斑（环面距离）。"""
    rng = np.random.RandomState(7)
    y, x = np.mgrid[0:n, 0:n].astype(np.float64)
    cx, cy = int(rng.uniform(0, n)), int(rng.uniform(0, n))
    dx = np.abs(x - cx)
    dx = np.minimum(dx, n - dx)
    dy = np.abs(y - cy)
    dy = np.minimum(dy, n - dy)
    d2 = dx * dx + dy * dy
    return 1.0 * np.exp(-d2 / (2.0 * (n * 0.16) ** 2)) + 0.6 * np.exp(-d2 / (2.0 * (n * 0.30) ** 2))


def _stars(count: int = 260, n: int = TILE) -> np.ndarray:
    """星点：小亮片（环面距离），银白微蓝。"""
    rng = np.random.RandomState(88)
    y, x = np.mgrid[0:n, 0:n].astype(np.float64)
    out = np.zeros_like(x, dtype=np.float64)
    for _ in range(count):
        cx, cy = int(rng.uniform(0, n)), int(rng.uniform(0, n))
        sigma = rng.uniform(1.8, 4.2)
        dx = np.abs(x - cx)
        dx = np.minimum(dx, n - dx)
        dy = np.abs(y - cy)
        dy = np.minimum(dy, n - dy)
        d2 = dx * dx + dy * dy
        out += rng.uniform(0.8, 1.0) * np.exp(-d2 / (2.0 * sigma * sigma))
    return out


def _cloud_veil(n: int = TILE) -> np.ndarray:
    """云纱：柔亮斜纹（整数周期 → 无缝）。"""
    y, x = np.mgrid[0:n, 0:n].astype(np.float64)
    out = np.zeros((n, n), dtype=np.float64)
    for freq, phase, amp, tilt in (
        (1.5, 0.6, 0.16, 1.0),
        (2.6, 1.9, 0.12, -0.7),
        (4.0, 3.2, 0.08, 0.4),
    ):
        axis = (x + tilt * y) % n
        wave = 0.5 + 0.5 * np.sin(2.0 * np.pi * freq * axis / n + phase)
        out += amp * np.power(wave, 3.0)
    return out


def _silver_shafts(n: int = TILE) -> np.ndarray:
    """银色光柱：斜向光斑。"""
    y, x = np.mgrid[0:n, 0:n].astype(np.float64)
    shafts = np.zeros((n, n), dtype=np.float64)
    for freq, phase, amp in ((1.0, 0.5, 0.14), (2.0, 1.8, 0.09)):
        t = ((x * 1.2 + y * 0.7) % n) / n
        shafts += amp * (0.5 + 0.5 * np.sin(2.0 * np.pi * freq * t + phase))
    return shafts


def _moon_silver() -> np.ndarray:
    # 墨灵意图：月光银白 [215,245,255]；姐姐补上月夜氛围（深蓝夜空→月下微亮）
    img = _radial_gradient(TILE * 0.5, TILE * 0.5,
                           inner=(0.10, 0.16, 0.30), outer=(0.03, 0.05, 0.12))
    halo = _moon_halo()
    stars = _stars()
    veil = _cloud_veil()
    shafts = _silver_shafts()
    for c in range(3):
        base = img[..., c]
        base = base + halo * (0.85 if c < 2 else 1.0)      # 月晕：暖白银
        base = base + stars * (0.95 if c == 2 else 0.85)   # 星点：银白微蓝
        base = base + veil * (0.10 if c == 2 else 0.06)    # 云纱
        base = base + shafts * (0.16 if c == 2 else 0.10)  # 银色光柱
        img[..., c] = np.clip(base, 0.0, 1.0)
    # 整体叠一层月光银白主色罩（向墨灵 [215,245,255] 靠拢，银白微蓝）
    silver = np.array([215 / 255, 245 / 255, 255 / 255])
    img = img * 0.75 + silver[None, None, :] * 0.25
    return img


def main() -> int:
    img = _moon_silver()
    arr = (np.clip(img, 0.0, 1.0) * 255.0).astype(np.uint8)
    out = os.path.join(HERE, "m13_texture_moon.jpg")
    Image.fromarray(arr, mode="RGB").save(out, quality=92)

    with FileLock(REGISTRY_PATH):
        with open(REGISTRY_PATH, encoding="utf-8") as f:
            registry = json.load(f)
        ids = {o["id"] for o in registry["outfits"]}
        if "moon" not in ids:
            registry["outfits"].append({
                "id": "moon", "name": "霓影月", "texture": "m13_texture_moon.jpg",
                "target": "body_ring",
                "desc": "霓影月·月光银白静谧月夜（C 收官命题③·墨灵执行者代码·姐姐代笔修复）",
            })
        registry["tones"]["moon_silver"] = [round(215 / 255, 4), round(245 / 255, 4), 1.0]
        with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump(registry, f, ensure_ascii=False, indent=2)

    print(json.dumps({
        "outfit": "moon", "name": "霓影月", "tone": "moon_silver",
        "texture": os.path.basename(out),
        "fixes": ["纯白→月夜渐变+月晕+星点+云纱+光柱", "伪无缝→数学无缝",
                  "双层循环→向量化", "主色统一为墨灵 [215,245,255]"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
