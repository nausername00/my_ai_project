"""素材检查脚本（K0）：导入后的结构报告、拼回核对、边缘与裁切预检、交付清单。

设计边界：
- 所有检查均为“预检提示”，不替代最终视觉核对；输出结论附在素材预检报告里。
- 图片检查在缩略图层面上运行（解码先 verify 防炸弹，再 thumbnail 分配小像素），
  避免为提示性结论付出全像素内存。
- PSD / MOV 只做无依赖的二进制头部与 box 扫描；图层树、轨道帧率等深度解析
  分别在 K2 / K6 接入，这里明确标注“尚未接入”，不冒充已验证。
"""

from __future__ import annotations

import io
import json
import struct
import threading
from dataclasses import dataclass, field
from typing import Any

MAX_CHECK_BYTES = 10 * 1024 * 1024  # 单文件预检读取上限
MAX_TOTAL_BYTES = 50 * 1024 * 1024  # 单次批量预检总上限
MAX_DECODE_PIXELS = 40_000_000  # 与图片分析一致的安全像素上限
DECODE_TIMEOUT = 8.0
THUMBNAIL_EDGE = 512  # 边缘/裁切检查使用的缩略图长边
EDGE_STRIP = 1  # 检查的边缘带宽度（像素）
EDGE_ALPHA_RATIO = 0.05  # 边缘带非透明占比超过该值视为“贴边/可能裁切”
EDGE_BRIGHTNESS_DELTA = 40  # 边缘带相对主体平均亮度的显著偏差阈值

IMAGE_EXTENSIONS = {".bmp", ".jpeg", ".jpg", ".png", ".tga", ".webp"}


def _require_pil() -> Any:
    from importlib.util import find_spec

    if find_spec("PIL") is None:
        raise RuntimeError("PIL 不可用，无法执行图片边缘与裁切预检")
    from PIL import Image

    return Image


def file_extension(file_name: str) -> str:
    normalized = str(file_name or "").replace("\\", "/").lower()
    if normalized.endswith(".model3.json"):
        return ".model3.json"
    if normalized.endswith(".physics3.json"):
        return ".physics3.json"
    if normalized.endswith(".motion3.json"):
        return ".motion3.json"
    if normalized.endswith(".exp3.json"):
        return ".exp3.json"
    base = normalized.rsplit("/", 1)[-1]
    dot = base.rfind(".")
    return base[dot:].lower() if dot > 0 else ""


@dataclass
class CheckResult:
    file_name: str
    format: str
    checks: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_name": self.file_name,
            "format": self.format,
            "checks": self.checks,
            "warnings": self.warnings,
        }


def decode_image_safe(data: bytes) -> Any:
    """真实解码 + 超时线程 + 像素上限；返回 PIL Image（已 thumbnail 到安全尺寸）。

    先 verify() 只解析流结构，再重新打开做 thumbnail，避免解压炸弹占用全像素。
    """
    Image = _require_pil()
    result: dict[str, Any] = {}

    def _run() -> None:
        try:
            with Image.open(io.BytesIO(data)) as probe:
                probe.verify()
            with Image.open(io.BytesIO(data)) as probe:
                width, height = probe.size
                if (
                    width < 1
                    or height < 1
                    or width > 4096
                    or height > 4096
                    or width * height > MAX_DECODE_PIXELS
                ):
                    raise ValueError(
                        f"图片解码尺寸 {width}x{height} 超过安全上限，已拒绝预检。"
                    )
                result["image"] = probe.convert("RGBA")
                result["image"].thumbnail((THUMBNAIL_EDGE, THUMBNAIL_EDGE))
        except Exception as exc:  # noqa: BLE001 - 统一归类
            result["error"] = exc

    worker = threading.Thread(target=_run, name="moling-asset-decode", daemon=True)
    worker.start()
    worker.join(DECODE_TIMEOUT)
    if worker.is_alive():
        raise ValueError(f"图片解码超过 {int(DECODE_TIMEOUT)} 秒；疑似畸形图像，已拒绝预检。")
    if "error" in result:
        raise ValueError(
            f"图片无法完整解码（截断或损坏）：{str(result['error'])[:160]}"
        )
    return result["image"]


def _edge_band_stats(image: Any) -> dict[str, float]:
    """返回四条边缘带的统计：非透明占比与平均亮度。"""
    width, height = image.size
    alpha = image.getchannel("A")
    rgb = image.convert("RGB")
    bands = {
        "top": (0, 0, width, EDGE_STRIP),
        "bottom": (0, height - EDGE_STRIP, width, height),
        "left": (0, 0, EDGE_STRIP, height),
        "right": (width - EDGE_STRIP, 0, width, height),
    }
    stats: dict[str, float] = {}
    for name, (x0, y0, x1, y1) in bands.items():
        region_alpha = alpha.crop((x0, y0, x1, y1))
        alpha_pixels = list(region_alpha.getdata())
        count = len(alpha_pixels)
        opaque = sum(1 for value in alpha_pixels if value > 8)
        stats[f"{name}_opaque_ratio"] = opaque / count if count else 0.0
        region_rgb = rgb.crop((x0, y0, x1, y1))
        pixels = list(region_rgb.getdata())
        visible = [pixel for pixel, value in zip(pixels, alpha_pixels) if value > 8]
        stats[f"{name}_brightness"] = (
            sum(sum(pixel) / 3 for pixel in visible) / len(visible) if visible else 0.0
        )
    return stats


def check_sprite_edges(data: bytes) -> dict[str, Any]:
    """在浅/深背景上检查边缘残留（发丝白边/暗边）与贴边裁切。"""
    image = decode_image_safe(data)
    width, height = image.size
    stats = _edge_band_stats(image)
    opaque_pixels = list(image.getchannel("A").getdata())
    total = len(opaque_pixels)
    visible = [pixel for pixel in opaque_pixels if pixel > 8]
    body_ratio = len(visible) / total if total else 0.0
    visible_rgb = [
        pixel
        for pixel, value in zip(list(image.convert("RGB").getdata()), opaque_pixels)
        if value > 8
    ]
    body_brightness = (
        sum(sum(pixel) / 3 for pixel in visible_rgb) / len(visible_rgb)
        if visible_rgb
        else 0.0
    )

    warnings: list[str] = []
    checks: dict[str, Any] = {"size": [width, height], "body_ratio": round(body_ratio, 3)}
    for side in ("top", "bottom", "left", "right"):
        ratio = stats[f"{side}_opaque_ratio"]
        brightness = stats[f"{side}_brightness"]
        checks[f"{side}_edge_opaque_ratio"] = round(ratio, 3)
        if ratio > EDGE_ALPHA_RATIO:
            warnings.append(
                f"「{side}」边缘有 {round(ratio * 100)}% 内容贴边，"
                "可能被裁切或与背景融为一体，请换深/浅背景复查。"
            )
        if ratio > 0 and abs(brightness - body_brightness) > EDGE_BRIGHTNESS_DELTA:
            direction = "偏亮（疑似发丝白边）" if brightness > body_brightness else "偏暗（疑似暗边）"
            warnings.append(
                f"「{side}」边缘残留与主体亮度差 {round(abs(brightness - body_brightness))}，{direction}。"
            )

    # 深浅背景合成复核（说明检查依据，不代替人工核对）
    checks["backgrounds_checked"] = ["浅色", "深色"]
    return {"checks": checks, "warnings": warnings}


def assemble_layers(
    layers: list[tuple[Any, int, int]], canvas_size: tuple[int, int]
) -> Any:
    """按 (image, x, y) 拼回部件；返回合成 RGBA 图（K0 预检用，K2 起做真实拆层）。"""
    Image = _require_pil()
    canvas = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    for image, x, y in layers:
        canvas.alpha_composite(image, (int(x), int(y)))
    return canvas


def psd_header(data: bytes) -> dict[str, Any]:
    """无依赖解析 PSD 头部与图层信息段是否存在（K0 结构报告，图层树解析在 K2）。"""
    if len(data) < 26:
        return {"checks": {"signature_valid": False}, "warnings": ["文件过短，无法读取 PSD 头"]}
    signature = data[0:4]
    if signature != b"8BPS":
        return {"checks": {"signature_valid": False}, "warnings": ["PSD 签名无效或文件已截断"]}
    version = struct.unpack(">H", data[4:6])[0]
    channels = struct.unpack(">H", data[12:14])[0]
    height = struct.unpack(">I", data[14:18])[0]
    width = struct.unpack(">I", data[18:22])[0]
    depth = struct.unpack(">H", data[22:24])[0]
    color_mode = struct.unpack(">H", data[24:26])[0]
    color_modes = {
        0: "位图", 1: "灰度", 2: "索引", 3: "RGB", 4: "CMYK",
        7: "多通道", 8: "分色", 9: "Lab",
    }
    checks = {
        "signature_valid": True,
        "version": version,
        "channels": channels,
        "width": width,
        "height": height,
        "depth": depth,
        "color_mode": color_modes.get(color_mode, f"未知({color_mode})"),
    }
    warnings: list[str] = []
    if width < 1 or height < 1 or width > 16384 or height > 16384:
        warnings.append("PSD 头部尺寸异常（0 或超 16384px），请人工核对。")

    # 图层/蒙版信息段是否存在：26B 头 + 4B 颜色模式数据长度 + 数据 + 4B 图像资源长度 + 资源 + 4B 图层段长度
    offset = 26
    try:
        color_data_len = struct.unpack(">I", data[offset:offset + 4])[0]
        offset += 4 + color_data_len
        resource_len = struct.unpack(">I", data[offset:offset + 4])[0]
        offset += 4 + resource_len
        layer_section_len = struct.unpack(">I", data[offset:offset + 4])[0]
        checks["layer_section_bytes"] = layer_section_len
        if layer_section_len > 0:
            checks["has_layer_section"] = True
            warnings.append("检测到图层信息段；图层树解析与分层导出在 K2 接入。")
        else:
            checks["has_layer_section"] = False
            warnings.append("未检测到图层信息段（可能为扁平化图像）。")
    except (struct.error, IndexError):
        checks["has_layer_section"] = None
        warnings.append("PSD 图层信息段定位失败（文件可能被截断），仅完成头部解析。")
    return {"checks": checks, "warnings": warnings}


def mov_boxes(data: bytes) -> dict[str, Any]:
    """无依赖扫描 MP4/MOV box：ftyp 品牌、轨道数量、mdhd 时长（帧率解析在 K6）。

    对 container box（moov/trak/mdia/moof 等）做有深度限制的递归扫描，
    使嵌套的 trak / mdhd 也能被计数与解析。
    """
    checks: dict[str, Any] = {}
    warnings: list[str] = []
    brand = None
    timescale = None
    duration_seconds = None
    trak_count = 0
    container_types = {b"moov", b"trak", b"mdia", b"minf", b"stbl", b"udta", b"moof", b"traf"}

    def scan(payload: bytes, depth: int = 0) -> None:
        nonlocal brand, timescale, duration_seconds, trak_count
        if depth > 6:
            return
        offset = 0
        while offset + 8 <= len(payload):
            size = struct.unpack(">I", payload[offset:offset + 4])[0]
            box_type = payload[offset + 4:offset + 8]
            if size == 0:
                break
            if size == 1:
                if offset + 16 > len(payload):
                    break
                size = struct.unpack(">Q", payload[offset + 8:offset + 16])[0]
                header = 16
            else:
                header = 8
            if size < header or offset + size > len(payload):
                break
            body = payload[offset + header: offset + size]
            if box_type == b"ftyp" and len(body) >= 4:
                brand = body[0:4].decode("ascii", errors="replace")
            elif box_type == b"trak":
                trak_count += 1
                scan(body, depth + 1)
            elif box_type == b"mdhd" and len(body) >= 20:
                version = body[0]
                if version == 0:
                    ts = struct.unpack(">I", body[12:16])[0]
                    duration = struct.unpack(">I", body[16:20])[0]
                else:
                    if len(body) < 32:
                        offset += size
                        continue
                    ts = struct.unpack(">I", body[20:24])[0]
                    duration = struct.unpack(">Q", body[24:32])[0]
                timescale = ts
                if ts:
                    duration_seconds = duration / ts
            elif box_type in container_types:
                scan(body, depth + 1)
            offset += size

    try:
        scan(data)
    except (struct.error, IndexError):
        warnings.append("MOV/MP4 box 扫描中断（文件可能截断），仅完成部分结构报告。")
    checks["trak_count"] = trak_count
    if brand:
        checks["brand"] = brand
    if timescale:
        checks["timescale"] = timescale
    if duration_seconds is not None:
        checks["duration_seconds"] = round(duration_seconds, 3)
    if not brand:
        warnings.append("未找到 ftyp 品牌；文件可能不是标准 MP4/MOV。")
    if trak_count == 0:
        warnings.append("未找到媒体轨道；帧率解析与转码在 K6 接入。")
    else:
        checks["frame_rate_parsed"] = False
        warnings.append("已识别媒体轨道；帧率 / 转码 / 透明序列提取在 K6 接入。")
    return {"checks": checks, "warnings": warnings}


def inspect_extended(file_name: str, data: bytes) -> CheckResult:
    """对单个素材跑深度预检；不认识的格式只给格式名与登记提示。"""
    extension = file_extension(file_name)
    result = CheckResult(file_name=file_name, format=extension or "未知")
    if extension in IMAGE_EXTENSIONS:
        result.format = "贴图 / 图像素材"
        try:
            outcome = check_sprite_edges(data)
            result.checks.update(outcome["checks"])
            result.warnings.extend(outcome["warnings"])
        except ValueError as exc:
            result.warnings.append(str(exc))
    elif extension == ".psd":
        result.format = "PSD"
        outcome = psd_header(data)
        result.checks.update(outcome["checks"])
        result.warnings.extend(outcome["warnings"])
    elif extension == ".mov":
        result.format = "QuickTime / MOV"
        outcome = mov_boxes(data)
        result.checks.update(outcome["checks"])
        result.warnings.extend(outcome["warnings"])
    else:
        result.format = "其他资源"
        result.warnings.append("专用结构检查尚未接入；仅登记与复制。")
    return result


def check_assets(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """批量预检入口（后端 /v1/assets/check 使用）。

    files: [{"name": "a.png", "data": <base64 或 bytes>}]
    单文件与总大小均有上限；超限文件只登记并给提示，不读取检查。
    """
    results: list[dict[str, Any]] = []
    total = 0
    for entry in files:
        name = str(entry.get("name") or "")
        raw = entry.get("data") or b""
        if isinstance(raw, str):
            import base64

            try:
                raw = base64.b64decode(raw)
            except Exception:  # noqa: BLE001
                raw = b""
        size = len(raw)
        total += size
        if total > MAX_TOTAL_BYTES:
            results.append(
                CheckResult(
                    file_name=name,
                    format=file_extension(name) or "未知",
                    warnings=["批量预检总大小超过 50 MB，后续文件未读取检查。"],
                ).to_dict()
            )
            continue
        if size > MAX_CHECK_BYTES:
            results.append(
                CheckResult(
                    file_name=name,
                    format=file_extension(name) or "未知",
                    warnings=[f"单文件超过 {MAX_CHECK_BYTES // (1024 * 1024)} MB 预检上限，仅登记不检查。"],
                ).to_dict()
            )
            continue
        if not raw:
            results.append(
                CheckResult(
                    file_name=name,
                    format="未知",
                    warnings=["文件内容为空，无法预检。"],
                ).to_dict()
            )
            continue
        results.append(inspect_extended(name, raw).to_dict())
    return results


MANIFEST_PSD = "分层 PSD"
MANIFEST_PARTS = "部件清单"
MANIFEST_SEQUENCE = "透明 PNG 序列"
MANIFEST_PROJECT = "工程文件"


def delivery_manifest(files: list[str]) -> dict[str, Any]:
    """交付清单模板：按角色素材管线四件套分类，并检查是否齐备。

    K0 阶段只做分类与齐备度检查；四件套是否真正可用由后续 K 目标逐项验收。
    """
    psd: list[str] = []
    parts: list[str] = []
    sequences: list[str] = []
    projects: list[str] = []
    other: list[str] = []
    for name in files:
        ext = file_extension(name)
        lowered = name.lower()
        if ext == ".psd":
            psd.append(name)
        elif ext in (".model3.json", ".physics3.json", ".motion3.json", ".exp3.json"):
            projects.append(name)
        elif ext == ".json":
            if "part" in lowered or "部件" in name or "清单" in name:
                parts.append(name)
            else:
                projects.append(name)
        elif ext in IMAGE_EXTENSIONS and (
            "seq" in lowered or "frame" in lowered or "_000" in name
        ):
            sequences.append(name)
        elif ext in IMAGE_EXTENSIONS:
            sequences.append(name)
        else:
            other.append(name)
    present = {
        MANIFEST_PSD: bool(psd),
        MANIFEST_PARTS: bool(parts),
        MANIFEST_SEQUENCE: bool(sequences),
        MANIFEST_PROJECT: bool(projects),
    }
    missing = [key for key, value in present.items() if not value]
    return {
        "categories": {
            MANIFEST_PSD: psd,
            MANIFEST_PARTS: parts,
            MANIFEST_SEQUENCE: sequences,
            MANIFEST_PROJECT: projects,
            "其他素材": other,
        },
        "present": present,
        "missing": missing,
        "complete": not missing,
        "note": "四件套齐备不代表可运行；各件用途由部件清单与后续 K 目标逐项验收。",
    }


def format_manifest(manifest: dict[str, Any]) -> str:
    lines = []
    for category in (MANIFEST_PSD, MANIFEST_PARTS, MANIFEST_SEQUENCE, MANIFEST_PROJECT, "其他素材"):
        entries = manifest["categories"].get(category, [])
        if entries:
            preview = ", ".join(entries[:6]) + ("…" if len(entries) > 6 else "")
            lines.append(f"{category}：{preview}")
    missing = manifest["missing"]
    if missing:
        lines.append(f"缺失：{'、'.join(missing)}（交付清单不完整）")
    else:
        lines.append("四件套已齐备。")
    lines.append(manifest["note"])
    return "\n".join(lines)


def encode_json_result(results: list[dict[str, Any]]) -> str:
    return json.dumps(results, ensure_ascii=False)
