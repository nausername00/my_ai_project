"""M10 · 时装库扩展：程序化无缝纹理生成器（C 目标）。

在 M5 时装系统底座上批量扩展时装库：不依赖 image_gen 外部服务，
纯 numpy/PIL 确定性生成无缝（tileable）纹理贴图 → 注册进 fashion_registry.json
→ 复用 FashionSystem 渲染验证。离线可复现、零 API 消耗、一次批量多套。

本批新增主题（避开深海/鎏金/月下——保留为墨灵收官命题）：
  - sakura_snow 樱雪：樱粉花瓣落在雪白底，春日轻盈
  - maple_moss  青枫：秋枫红橙×青苔墨绿，季节交替
  - aurora      极光：夜空蓝紫底上的绿紫极光色带 + 星光

无缝实现：所有图案基于"环面距离"（wrap-around）或整数周期正弦波，
任意中心点跨 tile 边界连续；输出与既有贴图一致（2048×2048 RGB JPEG）。
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

import numpy as np
from PIL import Image

from m_studio.lock_utils import FileLock

HERE = os.path.dirname(os.path.abspath(__file__))
REGISTRY_PATH = os.path.join(HERE, "fashion_registry.json")
TILE = 2048  # 与既有贴图一致
_RS = np.random.RandomState(20261020)  # 固定种子：确定性生成

# 主题定义：生成参数 + 注册字段 + 墨灵第一人称讲解（接 B 自导解说器风格）
THEMES = {
    "sakura_snow": {
        "name": "樱雪",
        "desc": "樱雪·樱粉花瓣落在雪白底（M10 时装库扩展·程序化生成）",
        "tone_id": "sakura",
        "tone_label": "樱雪粉",
        "tone_rgb": [0.92, 0.82, 0.86],
        "idea": "春天尾巴上的一场雪——花瓣和雪花一起落，粉得很干净，是轻盈日子里穿的颜色。",
        "expect": "樱粉花瓣×雪白底，春日轻盈。",
    },
    "maple_moss": {
        "name": "青枫",
        "desc": "青枫·秋枫红橙×青苔墨绿（M10 时装库扩展·程序化生成）",
        "tone_id": "maple",
        "tone_label": "枫叶橙",
        "tone_rgb": [0.72, 0.42, 0.26],
        "idea": "枫叶红透的时候，苔藓还是绿的——两个季节撞在一件衣服上，热闹又安静。",
        "expect": "枫红×苔绿渐变，季节交错感。",
    },
    "aurora": {
        "name": "极光",
        "desc": "极光·夜空蓝紫底上的绿紫极光（M10 时装库扩展·程序化生成）",
        "tone_id": "aurora",
        "tone_label": "极夜蓝",
        "tone_rgb": [0.12, 0.16, 0.30],
        "idea": "把极夜天空穿在身上——极光在蓝紫夜里流动，是最安静也最亮眼的一件。",
        "expect": "绿紫极光带×极夜蓝底，神秘流动。",
    },
}


# ------------------------------------------------------------------ 无缝基元
def _tile_distance(x: np.ndarray, y: np.ndarray, centers: list[tuple[int, int]],
                   sigma: float, amp: float, n: int = TILE) -> np.ndarray:
    """多个中心的环面高斯叠加（跨 tile 边界连续）。"""
    out = np.zeros_like(x, dtype=np.float64)
    for cx, cy in centers:
        dx = np.abs(x - cx)
        dx = np.minimum(dx, n - dx)
        dy = np.abs(y - cy)
        dy = np.minimum(dy, n - dy)
        d2 = dx * dx + dy * dy
        out += amp * np.exp(-d2 / (2.0 * sigma * sigma))
    return out


def _spiral_centers(count: int, radius: float, petals: int = 5,
                    jitter: float = 0.0, seed: int = 0) -> list[tuple[int, int]]:
    """生成 petal 瓣梅花簇（每簇绕半径 radius 的圆均匀分布）并抖动。"""
    rng = np.random.RandomState(seed)
    centers: list[tuple[int, int]] = []
    for i in range(count):
        cx = int(rng.uniform(0, TILE))
        cy = int(rng.uniform(0, TILE))
        for k in range(petals):
            ang = 2.0 * np.pi * k / petals + rng.uniform(0, 0.6)
            ox = radius * np.cos(ang) + rng.uniform(-jitter, jitter)
            oy = radius * np.sin(ang) + rng.uniform(-jitter, jitter)
            centers.append((int((cx + ox) % TILE), int((cy + oy) % TILE)))
    return centers


def _radial_gradient(cx: float, cy: float, inner: tuple[float, float, float],
                     outer: tuple[float, float, float], n: int = TILE) -> np.ndarray:
    """环面径向渐变：距 (cx,cy) 近处 inner 色，远处 outer 色。"""
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


def _linear_gradient(color_a: tuple[float, float, float],
                     color_b: tuple[float, float, float], n: int = TILE) -> np.ndarray:
    """对角线性渐变：t = ((x+y) % n)/n，对角轴环面周期 → 四边跨界连续。"""
    y, x = np.mgrid[0:n, 0:n].astype(np.float64)
    t = ((x + y) % n) / n
    img = np.zeros((n, n, 3), dtype=np.float64)
    for c in range(3):
        img[..., c] = color_a[c] * (1.0 - t) + color_b[c] * t
    return img


def _starlight(count: int, amp: float = 0.6, sigma: float = 1.6,
               seed: int = 7) -> np.ndarray:
    rng = np.random.RandomState(seed)
    centers = [(int(rng.uniform(0, TILE)), int(rng.uniform(0, TILE))) for _ in range(count)]
    y, x = np.mgrid[0:TILE, 0:TILE].astype(np.float64)
    return _tile_distance(x, y, centers, sigma, amp)


# ------------------------------------------------------------------ 各主题生成
def _sakura_snow() -> np.ndarray:
    """雪白→樱粉径向渐变 + 五瓣梅花簇（多层明暗）。"""
    img = _radial_gradient(TILE * 0.5, TILE * 0.5,
                           inner=(0.98, 0.94, 0.96), outer=(0.86, 0.72, 0.78))
    y, x = np.mgrid[0:TILE, 0:TILE].astype(np.float64)
    dark = _tile_distance(x, y, _spiral_centers(26, 26.0, petals=5, jitter=14.0, seed=1),
                          sigma=16.0, amp=0.20)
    bright = _tile_distance(x, y, _spiral_centers(20, 18.0, petals=5, jitter=10.0, seed=2),
                            sigma=9.0, amp=0.24)
    snow = _tile_distance(x, y, [(int(_RS.uniform(0, TILE)), int(_RS.uniform(0, TILE))) for _ in range(90)],
                          sigma=7.0, amp=0.30)
    for c in range(3):
        img[..., c] = np.clip(img[..., c] - dark * 0.55 + bright * 0.45 + snow, 0.0, 1.0)
    return img


def _maple_moss() -> np.ndarray:
    """青苔墨绿→枫红橙对角渐变 + 枫叶椭圆簇 + 叶脉线。"""
    img = _linear_gradient(color_a=(0.30, 0.38, 0.26), color_b=(0.78, 0.42, 0.28))
    y, x = np.mgrid[0:TILE, 0:TILE].astype(np.float64)
    leaves = _tile_distance(x, y, _spiral_centers(34, 34.0, petals=6, jitter=18.0, seed=3),
                            sigma=26.0, amp=0.55)
    leaf_vein = _tile_distance(x, y, _spiral_centers(34, 34.0, petals=6, jitter=18.0, seed=3),
                               sigma=4.5, amp=0.30)
    moss = _tile_distance(x, y, [(int(_RS.uniform(0, TILE)), int(_RS.uniform(0, TILE))) for _ in range(70)],
                          sigma=20.0, amp=0.25)
    for c in range(3):
        img[..., c] = np.clip(img[..., c] + leaves * 0.5 + leaf_vein * 0.2 + moss * 0.35, 0.0, 1.0)
    return img


def _aurora() -> np.ndarray:
    """极夜蓝紫底 + 多层正弦极光色带 + 星光。"""
    y, x = np.mgrid[0:TILE, 0:TILE].astype(np.float64)
    img = _radial_gradient(TILE * 0.5, TILE * 0.5,
                           inner=(0.10, 0.14, 0.30), outer=(0.05, 0.08, 0.18))
    # 多层水平极光带（整数周期 → 无缝）
    for freq, phase, amp, rgb in (
        (2.0, 0.0, 0.34, (0.38, 0.96, 0.62)),   # 青绿主带（提亮加宽）
        (3.0, 0.9, 0.26, (0.60, 0.72, 1.00)),  # 蓝紫副带
        (1.0, 0.4, 0.22, (0.98, 0.58, 0.98)),  # 粉紫尾带
    ):
        band = 0.5 + 0.5 * np.sin(2.0 * np.pi * freq * y / TILE + phase)
        for c in range(3):
            img[..., c] += rgb[c] * band * amp
    stars = _starlight(150, amp=0.45, sigma=1.8, seed=11)
    for c in range(3):
        img[..., c] = np.clip(img[..., c] + stars, 0.0, 1.0)
    return img


_GENERATORS = {
    "sakura_snow": _sakura_snow,
    "maple_moss": _maple_moss,
    "aurora": _aurora,
}


def texture_path(theme_id: str) -> str:
    return os.path.join(HERE, f"m10_texture_{theme_id}.jpg")


# ------------------------------------------------------------------ 生成 + 注册
def generate(theme_id: str, register: bool = True) -> dict:
    """生成贴图 → （可选）注册进时装库 → 返回贴图路径与注册信息。"""
    theme = THEMES.get(theme_id)
    if theme is None:
        raise ValueError(f"未知主题: {theme_id}（可选：{', '.join(THEMES)}）")
    if theme_id not in _GENERATORS:
        raise ValueError(f"主题 {theme_id} 尚无生成器实现")

    img = _GENERATORS[theme_id]()
    arr = (np.clip(img, 0.0, 1.0) * 255.0).astype(np.uint8)
    out = texture_path(theme_id)
    Image.fromarray(arr, mode="RGB").save(out, quality=92)

    registered = False
    if register:
        registered = _register(theme_id, out)
    return {
        "theme_id": theme_id,
        "name": theme["name"],
        "texture": os.path.basename(out),
        "texture_path": out,
        "registered": registered,
    }


def _register(theme_id: str, texture_local: str) -> bool:
    """幂等注册时装 + 色调；已存在返回 False。"""
    theme = THEMES[theme_id]
    outfit_id = theme_id
    tone_id = theme["tone_id"]
    with FileLock(REGISTRY_PATH):
        with open(REGISTRY_PATH, encoding="utf-8") as f:
            registry = json.load(f)
        changed = False
        if not any(o["id"] == outfit_id for o in registry["outfits"]):
            registry["outfits"].append({
                "id": outfit_id,
                "name": theme["name"],
                "texture": os.path.basename(texture_local),
                "target": "body_ring",
                "desc": theme["desc"],
            })
            changed = True
        if tone_id not in registry["tones"]:
            registry["tones"][tone_id] = theme["tone_rgb"]
            changed = True
        if changed:
            with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
                json.dump(registry, f, ensure_ascii=False, indent=2)
    return changed


def generate_all(register: bool = True) -> list[dict]:
    return [generate(tid, register=register) for tid in THEMES]


# ------------------------------------------------------------------ CLI
def main(argv: list[str]) -> int:
    """CLI：--themes | --generate [id] | --generate-all [--no-register] | --render <o> <t>"""
    from fashion_system import FashionSystem

    if "--themes" in argv:
        for tid, t in THEMES.items():
            print(f"  {tid}: {t['name']}——{t['idea'][:28]}……")
        return 0
    if "--generate" in argv:
        i = argv.index("--generate")
        theme_id = argv[i + 1] if len(argv) > i + 1 else next(iter(THEMES))
        result = generate(theme_id, register="--no-register" not in argv)
        print(f"[gen] {result['name']} -> {result['texture']} registered={result['registered']}")
        return 0
    if "--generate-all" in argv:
        for result in generate_all(register="--no-register" not in argv):
            print(f"[gen] {result['name']} -> {result['texture']} registered={result['registered']}")
        return 0
    if "--render" in argv:
        i = argv.index("--render")
        fs = FashionSystem()
        params = fs.compose(argv[i + 1], argv[i + 2])
        result = fs.render(params)
        print(f"[render] {argv[i + 1]}×{argv[i + 2]} rc={result['rc']} cache={result['cache_hit']} "
              f"{result['render_ms']}ms cost={result['cost']} out={result['out']}")
        return result["rc"]
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
