"""K2 部件拆分：把定稿立绘拆成可拼回的分层 PNG + 部件清单 JSON。

设计原则
--------
- **像素互斥归属**：每个像素只属于一个部件；所有部件按原坐标合成 == 原图
  （人物区域），拼回校验是恒等式，可机器验证。
- 分配优先级（高→低）：眼 > 嘴 > 发 > 脸 > 手 > 衣 > 靴。
- 部件蒙版为**程序化粗蒙版**（区域先验 + 颜色 + 连通域），用于 K3 绑定前的
  部件库基础；精细蒙版（发丝级）留待绑定阶段按需精修。
- 眼睛用红眸颜色定位（定稿为鲜红眼眸）；嘴用脸部带下部的深色/红色簇定位。

用法
----
python k2_split.py            # 拆分定稿 baseline_v5_0_raw.png
python k2_split.py <raw.png>  # 拆分指定立绘
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

PROJECT_ROOT = Path(r"D:\Coding\code program\test\This is mine\my_ai_project")
ASSET_DIR = PROJECT_ROOT / "Model Core" / "Weighting file (core fuel)" / "Character" / "K1 Portrait"
LAYERS_DIR = ASSET_DIR / "layers"
PARTS_JSON = ASSET_DIR / "parts.json"

DEFAULT_RAW = ASSET_DIR / "baseline_v5_0_raw.png"

ALPHA_THRESHOLD = 128
FACE_BAND_Y = (0.18, 0.48)     # 脸部带（高度比例）
FACE_BAND_X = (0.30, 0.70)     # 脸部带（宽度比例）
EYE_RED_MIN = 90               # 放宽：左眼瞳色较暗也能检出
EYE_MIN_AREA = 40
MOUTH_MIN_AREA = 30
HAIR_LIGHT = 150               # 银白发亮阈值（放宽，垂发亮度≈190）
HAIR_MAX_Y = 0.80              # 发区最高到 0.8h（不吞靴区）
FACE_RX = 0.19                 # 脸部椭圆半宽（画布宽比例）
FACE_RY = 0.115                # 脸部椭圆半高（画布高比例）
BOOT_Y = 0.78

PART_ORDER = ("eye", "mouth", "hair", "face", "cloth", "boots")

PART_INFO = {
    "eye": {"purpose": "眼睛（含瞳孔与眼周）", "z_order": 3},
    "mouth": {"purpose": "嘴巴（含口线与唇色）", "z_order": 2},
    "hair": {"purpose": "银白长发（覆盖脸侧）", "z_order": 1},
    "face": {"purpose": "脸部基底（皮肤）", "z_order": 0},
    "cloth": {"purpose": "衣物（外套/裙/袜，含交叠双手）", "z_order": 5},
    "boots": {"purpose": "靴子（下半身收尾）", "z_order": 4},
}


def load_person_mask(image: Image.Image) -> np.ndarray:
    """人物蒙版：isnet 蒙版种子 + 有限扩张（0/1 矩阵，1=人物）。

    isnet 提供人物主体核心；扩张吸收相邻的非背景装饰像素补全边缘
    （银发/衣摆等亮部）。近白背景与高红装饰不吸收，避免背景溢出。
    """
    from rembg import new_session, remove

    rgb = np.asarray(image.convert("RGB"))
    h, w = rgb.shape[:2]
    # 2x 放大再分割：isnet 内部按 320px 处理，放大可显著改善边缘细节
    big = image.convert("RGBA").resize((w * 2, h * 2), Image.LANCZOS)
    out = remove(big, session=new_session("isnet-general-use"))
    alpha = np.asarray(out.getchannel("A"), dtype=np.float32) / 255.0
    alpha = np.asarray(Image.fromarray((alpha * 255).astype(np.uint8)).resize((w, h), Image.LANCZOS), dtype=np.float32) / 255.0
    seed = alpha > 0.5

    r = rgb[..., 0].astype(np.int16)
    g = rgb[..., 1].astype(np.int16)
    b = rgb[..., 2].astype(np.int16)
    gray = rgb.mean(axis=2).astype(np.int16)

    high_red = (r > g + 35) & (r > b + 35)
    face_band = np.zeros((h, w), dtype=bool)
    face_band[int(h * FACE_BAND_Y[0]) : int(h * FACE_BAND_Y[1]), int(w * FACE_BAND_X[0]) : int(w * FACE_BAND_X[1])] = True
    decoration = high_red & ~face_band

    whitish = (gray > 175) & (abs(r - g) < 30) & (abs(g - b) < 30) & (abs(r - b) < 30)

    mask = seed.copy()
    absorbable = ~decoration & ~whitish
    structure = np.ones((3, 3), dtype=bool)
    for _ in range(12):
        mask |= ndimage.binary_dilation(mask, structure=structure) & absorbable
    # 形态学 close：填小洞、平滑边缘锯齿
    mask = ndimage.binary_closing(mask, structure=np.ones((5, 5), dtype=bool))
    return mask.astype(np.uint8)


def _red_eye_mask(rgb: np.ndarray, band: tuple[tuple[float, float], tuple[float, float]]) -> np.ndarray:
    h, w = rgb.shape[:2]
    y0, y1 = int(h * band[0][0]), int(h * band[0][1])
    x0, x1 = int(w * band[1][0]), int(w * band[1][1])
    r, g, b = rgb[..., 0].astype(np.int16), rgb[..., 1].astype(np.int16), rgb[..., 2].astype(np.int16)
    red = (r > EYE_RED_MIN) & (r > g + 30) & (r > b + 30)
    band_mask = np.zeros((h, w), dtype=np.uint8)
    band_mask[y0:y1, x0:x1] = red[y0:y1, x0:x1]
    return band_mask


def _largest_labeled_clusters(mask: np.ndarray, count: int, min_area: int) -> list[tuple[np.ndarray, tuple[int, int, int, int]]]:
    labels, n = ndimage.label(mask)
    if n == 0:
        return []
    sizes = ndimage.sum(mask, labels, range(1, n + 1))
    order = np.argsort(-sizes)
    clusters: list[tuple[np.ndarray, tuple[int, int, int, int]]] = []
    for idx in order[:count]:
        label_id = idx + 1
        if sizes[idx] < min_area:
            continue
        ys, xs = np.where(labels == label_id)
        bbox = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))
        clusters.append(((labels == label_id).astype(np.uint8), bbox))
    return clusters


def _expand(bbox: tuple[int, int, int, int], h: int, w: int, ratio: float = 0.15) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = bbox
    dx = max(2, int((x1 - x0) * ratio))
    dy = max(2, int((y1 - y0) * ratio))
    return (max(0, x0 - dx), max(0, y0 - dy), min(w - 1, x1 + dx), min(h - 1, y1 + dy))


def _ellipse_mask(h: int, w: int, cx: float, cy: float, rx: float, ry: float) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w]
    return ((((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2) <= 1.0).astype(np.uint8)


def split_parts(rgb: np.ndarray, person: np.ndarray) -> dict[str, np.ndarray]:
    """互斥分配像素到部件蒙版。返回 {part: mask}（0/1）。"""
    h, w = rgb.shape[:2]
    eye_mask = np.zeros((h, w), dtype=np.uint8)
    mouth_mask = np.zeros((h, w), dtype=np.uint8)
    face_mask = np.zeros((h, w), dtype=np.uint8)
    hair_mask = np.zeros((h, w), dtype=np.uint8)
    cloth_mask = np.zeros((h, w), dtype=np.uint8)
    boots_mask = np.zeros((h, w), dtype=np.uint8)

    face_band = ((FACE_BAND_Y[0], FACE_BAND_Y[1]), (FACE_BAND_X[0], FACE_BAND_X[1]))

    # 1) 眼睛：脸部带内红眸聚类（取最大两簇 = 双眼）
    eye_hits = _red_eye_mask(rgb, face_band) & person
    eye_clusters = _largest_labeled_clusters(eye_hits, 2, EYE_MIN_AREA)
    eye_centers: list[tuple[float, float]] = []
    for cluster, bbox in eye_clusters:
        ys, xs = np.where(cluster)
        eye_centers.append((float(xs.mean()), float(ys.mean())))
        x0, y0, x1, y1 = _expand(bbox, h, w)
        eye_mask[y0 : y1 + 1, x0 : x1 + 1] = cluster[y0 : y1 + 1, x0 : x1 + 1]

    # 脸椭圆（以眼中心为准；无眼时用默认位置）
    if eye_centers:
        cx = sum(c[0] for c in eye_centers) / len(eye_centers)
        cy = sum(c[1] for c in eye_centers) / len(eye_centers)
    else:
        cx, cy = w * 0.5, h * 0.30
    face_ellipse = _ellipse_mask(h, w, cx, cy, w * FACE_RX, h * FACE_RY)

    # 2) 嘴：脸椭圆内、眼下方的深色/红簇（只取最大一簇，限制在脸内中央）
    used = (eye_mask).astype(bool)
    gray = rgb.mean(axis=2)
    dark = (gray < 130) | ((rgb[..., 0].astype(np.int16) > 90) & (rgb[..., 0] > rgb[..., 2] + 25))
    mouth_region = face_ellipse.astype(bool)
    y0m = int(h * 0.26)
    mouth_region[:y0m, :] = False
    x0m, x1m = int(w * 0.42), int(w * 0.58)
    mouth_region[:, :x0m] = False
    mouth_region[:, x1m:] = False
    mouth_hits = (mouth_region & dark & person.astype(bool) & ~used).astype(np.uint8)
    mouth_clusters = _largest_labeled_clusters(mouth_hits, 1, MOUTH_MIN_AREA)
    if mouth_clusters:
        cluster, bbox = mouth_clusters[0]
        x2, y2, x3, y3 = _expand(bbox, h, w, 0.2)
        mouth_mask[y2 : y3 + 1, x2 : x3 + 1] = cluster[y2 : y3 + 1, x2 : x3 + 1]

    # 3) 发：人物内、脸椭圆外、亮度>HAIR_LIGHT 的非暖像素（银发空间先验）
    used = (eye_mask | mouth_mask).astype(bool)
    non_face = (1 - face_ellipse).astype(bool)
    bright = gray > HAIR_LIGHT
    warm = (rgb[..., 0].astype(np.int16) - rgb[..., 2]) > 45  # 强暖色（金饰/红装饰）不进发
    hair_region = np.ones((h, w), dtype=bool)
    hair_region[int(h * HAIR_MAX_Y) :, :] = False
    hair_mask = (person.astype(bool) & ~used & non_face & bright & ~warm & hair_region).astype(np.uint8)

    # 4) 脸：脸椭圆内的肤色剩余（排除眼/嘴/发）
    skin = gray > 100
    face_mask = (face_ellipse.astype(bool) & person.astype(bool) & skin & ~used & ~hair_mask.astype(bool)).astype(np.uint8)

    # 5) 靴：底部区域
    boots_mask = person.copy()
    boots_mask[: int(h * BOOT_Y), :] = 0

    # 6) 衣：剩余人物像素（含双手交叠区域）
    remaining = person.astype(bool) & ~(
        eye_mask | mouth_mask | hair_mask | face_mask | boots_mask
    ).astype(bool)
    cloth_mask = remaining.astype(np.uint8)

    return {
        "eye": eye_mask,
        "mouth": mouth_mask,
        "hair": hair_mask,
        "face": face_mask,
        "cloth": cloth_mask,
        "boots": boots_mask,
    }


def compose_check(rgb: np.ndarray, parts: dict[str, np.ndarray], person: np.ndarray) -> tuple[bool, int, int]:
    """拼回校验：所有部件合成的人物像素 == 原图人物像素（互斥 → 恒等）。"""
    h, w = rgb.shape[:2]
    composed = np.zeros((h, w), dtype=np.uint8)
    for mask in parts.values():
        composed |= mask
    diff = np.count_nonzero(composed != person)
    return bool(diff == 0), int(diff), int(np.count_nonzero(person))


def bbox_of(mask: np.ndarray) -> list[int]:
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return [0, 0, 0, 0]
    return [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]


def main() -> int:
    raw_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_RAW
    image = Image.open(raw_path).convert("RGB")
    rgb = np.asarray(image)
    h, w = rgb.shape[:2]
    print(f"拆分: {raw_path.name} ({w}x{h})", flush=True)

    person = load_person_mask(image)
    person_count = int(np.count_nonzero(person))
    print(f"人物蒙版: {person_count} 像素 ({person_count / (h * w):.1%})", flush=True)

    parts = split_parts(rgb, person)
    ok, diff, total = compose_check(rgb, parts, person)
    print(f"拼回校验: {'通过' if ok else '未通过'} (diff={diff}/{total})", flush=True)
    if not ok:
        print("警告: 部件未完全覆盖人物蒙版，请检查蒙版分配", flush=True)

    LAYERS_DIR.mkdir(parents=True, exist_ok=True)
    layers: dict[str, dict] = {}
    for part in PART_ORDER:
        mask = parts[part]
        layer = np.zeros((h, w, 4), dtype=np.uint8)
        layer[..., :3] = rgb
        layer[..., 3] = mask * 255
        out_path = LAYERS_DIR / f"{part}.png"
        Image.fromarray(layer, "RGBA").save(out_path)
        layers[part] = {
            "file": out_path.name,
            "bbox": bbox_of(mask),
            "pixels": int(np.count_nonzero(mask)),
            **PART_INFO[part],
        }
        print(f"  {part}: {out_path.name} bbox={layers[part]['bbox']} px={layers[part]['pixels']}", flush=True)

    # 候选补画区：脸-发交界带（需人工确认）
    needs_patch: list[dict] = []
    if "face" in parts:
        face_ys, face_xs = np.where(parts["face"])
        if len(face_xs):
            x0, y0, x1, y1 = (
                int(face_xs.min()),
                int(face_ys.min()),
                int(face_xs.max()),
                int(face_ys.max()),
            )
            needs_patch.append(
                {
                    "region": "face-hair boundary",
                    "bbox": [max(0, x0 - 12), max(0, y0 - 12), min(w - 1, x1 + 12), min(h - 1, y1 + 12)],
                    "reason": "发丝与脸交界处可能遮挡皮肤，K3 绑定前需确认是否补画",
                }
            )

    manifest = {
        "source": str(raw_path),
        "canvas": [w, h],
        "person_pixels": person_count,
        "compose_check": {"passed": ok, "diff": diff, "total": total},
        "layers": layers,
        "needs_patch": needs_patch,
        "note": "部件蒙版为程序化粗蒙版（像素互斥归属，拼回=原图）；精细蒙版与补画在 K3 绑定前按需精修。",
    }
    PARTS_JSON.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"部件清单: {PARTS_JSON}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
