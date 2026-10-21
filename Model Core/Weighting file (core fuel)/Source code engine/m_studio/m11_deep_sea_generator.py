"""C 收官命题①深海：执行者（主 AI）按墨灵设计稿实现贴图 + 注册时装库。

墨灵设计（design_deep_sea_meng.json）：
  name=幽冥舞  tone=墨黑[0.15,0.15,0.2]
  style=螺旋裙摆模仿深海珊瑚，珍珠+银色流苏
  expect=深蓝渐变底+海浪波纹+鱼群剪影+海底光斑+气泡与小珍珠

无缝实现：全部图案基于环面距离 / 整数周期正弦 / 环形角度分布，
任意中心点跨 tile 边界连续；输出 2048×2048 RGB JPEG。
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
_RS = np.random.RandomState(20261021)  # 固定种子：确定性生成

# 墨灵设计稿（来源 design_deep_sea_meng.json）
NAME = "幽冥舞"
TONE_ID = "abyss"          # 深渊
TONE_LABEL = "墨黑"
TONE_RGB = [0.15, 0.15, 0.2]
DESC = "幽冥舞·深海的幽灵舞者（C 收官命题①·墨灵原创设计）"
IDEA = "这是一场深海的梦幻独舞，我用细腻的笔触描绘了幽暗与神秘的海底世界。"
EXPECT = "深蓝渐变底上叠加细密海浪波纹、鱼群剪影、海底光斑、气泡与小珍珠，神秘而梦幻。"


# ---------------------------------------------------------------- 无缝基元
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
    """多层整数周期正弦波纹（海浪）：对角轴方向，跨边界连续，带亮峰。"""
    y, x = np.mgrid[0:n, 0:n].astype(np.float64)
    bands = np.zeros((n, n), dtype=np.float64)
    # 多层不同频率/相位/方向的浪带
    for freq, phase, amp, tilt in (
        (1.6, 0.0, 0.30, 1.0),
        (2.4, 1.1, 0.22, -0.7),
        (3.8, 2.3, 0.16, 0.4),
    ):
        axis = (x + tilt * y) % n
        wave = 0.5 + 0.5 * np.sin(2.0 * np.pi * freq * axis / n + phase)
        # 波峰提亮（pow 凸出亮线）
        bands += amp * np.power(wave, 3.0)
    return bands


def _fish_silhouettes(count: int = 16, n: int = TILE) -> np.ndarray:
    """鱼群剪影：小椭圆簇（环面），深底上的淡蓝剪影。"""
    rng = np.random.RandomState(9)
    y, x = np.mgrid[0:n, 0:n].astype(np.float64)
    out = np.zeros_like(x, dtype=np.float64)
    for _ in range(count):
        cx, cy = int(rng.uniform(0, n)), int(rng.uniform(0, n))
        ang = rng.uniform(0, 2 * np.pi)
        length = rng.uniform(90, 200)   # 鱼身长
        width = rng.uniform(28, 55)     # 鱼身宽
        ca, sa = np.cos(ang), np.sin(ang)
        dx = (x - cx) * ca + (y - cy) * sa
        dy = -(x - cx) * sa + (y - cy) * ca
        dx = np.minimum(np.abs(dx), n - np.abs(dx))
        dy = np.minimum(np.abs(dy), n - np.abs(dy))
        d2 = (dx / length) ** 2 + (dy / width) ** 2
        out += np.clip(1.0 - d2, 0.0, 1.0) ** 2 * 0.5
    return out


def _bubbles_pearls(count_b: int = 70, count_p: int = 160, n: int = TILE) -> np.ndarray:
    """气泡（中亮蓝点）+ 小珍珠（微小亮白点）。"""
    rng = np.random.RandomState(21)
    y, x = np.mgrid[0:n, 0:n].astype(np.float64)
    bubbles = _tile_distance(x, y,
                             [(int(rng.uniform(0, n)), int(rng.uniform(0, n))) for _ in range(count_b)],
                             sigma=10.0, amp=0.55)
    pearls = _tile_distance(x, y,
                            [(int(rng.uniform(0, n)), int(rng.uniform(0, n))) for _ in range(count_p)],
                            sigma=3.2, amp=0.9)
    return bubbles, pearls


def _light_shafts(n: int = TILE) -> np.ndarray:
    """海底光斑：大尺度低频径向光 + 斜向光柱（整数周期对角）。"""
    y, x = np.mgrid[0:n, 0:n].astype(np.float64)
    glow = _radial_gradient(TILE * 0.5, TILE * 0.5, (0.0, 0.0, 0.0), (0.16, 0.20, 0.10))
    shafts = np.zeros((n, n), dtype=np.float64)
    for freq, phase, amp in ((1.0, 0.5, 0.10), (2.0, 1.8, 0.06)):
        t = ((x * 1.3 + y * 0.6) % n) / n
        shafts += amp * (0.5 + 0.5 * np.sin(2.0 * np.pi * freq * t + phase))
    return glow + shafts[..., None]


def _deep_sea() -> np.ndarray:
    """深海无缝纹理：深蓝渐变底 + 海浪亮纹 + 鱼群剪影 + 光斑 + 气泡珍珠。"""
    img = _radial_gradient(TILE * 0.5, TILE * 0.5,
                           inner=(0.035, 0.10, 0.22), outer=(0.015, 0.045, 0.11))
    y, x = np.mgrid[0:TILE, 0:TILE].astype(np.float64)
    waves = _wave_bands()
    fish = _fish_silhouettes()
    bubbles, pearls = _bubbles_pearls()
    light = _light_shafts()[..., 0]  # 光斑取单通道灰度（底光泛蓝处理在循环内按通道加权）
    for c in range(3):
        base = img[..., c]
        # 海浪：波峰处泛蓝白微光
        base = base + waves * (0.10 + 0.05 * c)
        # 光斑：底部柔光（蓝调为主）
        base = base + light * (0.10 if c == 2 else 0.05)
        # 鱼群剪影：淡蓝（与底区分）
        base = base + fish * (0.10 if c == 2 else 0.04)
        # 气泡：中亮青白
        base = base + bubbles * (0.30 if c == 2 else 0.22)
        # 珍珠：亮白微点
        base = base + pearls * 0.65
        img[..., c] = np.clip(base, 0.0, 1.0)
    return img


def main() -> int:
    img = _deep_sea()
    arr = (np.clip(img, 0.0, 1.0) * 255.0).astype(np.uint8)
    out = os.path.join(HERE, "m11_texture_deep_sea.jpg")
    Image.fromarray(arr, mode="RGB").save(out, quality=92)

    with FileLock(REGISTRY_PATH):
        with open(REGISTRY_PATH, encoding="utf-8") as f:
            registry = json.load(f)
        changed = False
        if not any(o["id"] == "deep_sea" for o in registry["outfits"]):
            registry["outfits"].append({
                "id": "deep_sea",
                "name": NAME,
                "texture": "m11_texture_deep_sea.jpg",
                "target": "body_ring",
                "desc": DESC,
            })
            changed = True
        if TONE_ID not in registry["tones"]:
            registry["tones"][TONE_ID] = TONE_RGB
            changed = True
        if changed:
            with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
                json.dump(registry, f, ensure_ascii=False, indent=2)

    print(json.dumps({
        "outfit": "deep_sea", "name": NAME, "tone": TONE_ID,
        "texture": os.path.basename(out), "registered": changed,
        "idea": IDEA, "expect": EXPECT,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
