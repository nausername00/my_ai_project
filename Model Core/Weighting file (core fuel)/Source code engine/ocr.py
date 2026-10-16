"""T2 OCR 与结构化抽取（第 5 层缺口）。

- 本地 OCR：优先探测 tesseract（subprocess 参数化调用，shell=False）；
  未安装时明确报错并给出提示，绝不静默。
- 结构化抽取：纯规则键值解析（金额 / 日期 / 供应商 / 单号等），无外部依赖、可测试。
- 边界：只读本地图片，无网络；图片大小上限；结果如实返回，不编造字段。
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8MB 上限，避免超大图拖垮本地 OCR
OCR_TIMEOUT_SECONDS = 120

# 常见标签 → 字段名（中文 / 英文）
_FIELD_LABELS: dict[str, tuple[str, ...]] = {
    "amount": ("金额", "总额", "合计", "小计", "付款", "amount", "total", "subtotal"),
    "date": ("日期", "开票日期", "时间", "date", "invoice date"),
    "supplier": (
        "供应商",
        "卖方",
        "公司",
        "单位名称",
        "收款人",
        "supplier",
        "vendor",
        "seller",
        "from",
    ),
    "invoice_no": ("编号", "单号", "号码", "发票号", "invoice", "no.", "number"),
    "currency": ("币种", "货币", "currency"),
}

_AMOUNT_RE = re.compile(r"[\$￥¥€]?\s?\d{1,3}(?:,\d{3})*(?:\.\d{2})?\b")
_DATE_RE = re.compile(
    r"(?:19|20)\d{2}[-/年]\d{1,2}[-/月]\d{1,2}日?"
    r"|\d{1,2}[-/]\d{1,2}[-/](?:19|20)\d{2}"
)
_LINE_LABEL_RE = re.compile(r"^([^:：\n]{1,20})[：:]\s*(.+)$")


def detect_ocr_engine() -> dict[str, Any]:
    """探测本地 OCR 引擎：当前仅 tesseract；无则如实报告不可用与安装提示。"""
    exe = shutil.which("tesseract")
    if exe:
        return {
            "available": True,
            "engine": "tesseract",
            "path": exe,
            "hint": "",
        }
    return {
        "available": False,
        "engine": None,
        "path": "",
        "hint": "未检测到本地 OCR 引擎。可安装 Tesseract OCR 后重试"
        "（例如 choco install tesseract / 官方安装包）；本功能不依赖网络。",
    }


def ocr_text(image_path: str, *, max_chars: int = 4000) -> dict[str, Any]:
    """对本地图片做 OCR 提取文字。

    未安装 tesseract 时抛 ValueError（明确报错，不静默）；
    返回 {engine, text, chars, source}。
    """
    path = Path(image_path).expanduser()
    if not path.is_file():
        raise ValueError(f"图片不存在: {path}")
    if path.stat().st_size > MAX_IMAGE_BYTES:
        raise ValueError(f"图片超过 {MAX_IMAGE_BYTES // (1024 * 1024)}MB 上限")

    engine = detect_ocr_engine()
    if not engine["available"]:
        raise ValueError(engine["hint"])

    try:
        proc = subprocess.run(
            [engine["path"], str(path), "stdout"],
            capture_output=True,
            timeout=OCR_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise ValueError(f"OCR 超时（>{OCR_TIMEOUT_SECONDS}s）：{error}") from error
    if proc.returncode != 0:
        raise ValueError(
            f"OCR 失败（退出码 {proc.returncode}）："
            + proc.stderr.decode("utf-8", errors="replace")[:300]
        )
    text = proc.stdout.decode("utf-8", errors="replace").strip()
    if len(text) > max_chars:
        text = text[:max_chars]
    return {
        "engine": engine["engine"],
        "text": text,
        "chars": len(text),
        "source": str(path),
    }


def extract_fields(text: str) -> dict[str, Any]:
    """从文本中按规则抽取字段：金额 / 日期 / 供应商 / 单号 / 币种。

    只返回文本中真实出现的信息；没有匹配的字段不编造。
    """
    fields: dict[str, Any] = {}
    matched: list[str] = []

    # 标签：值 行优先（如「供应商：某某公司」「金额：¥1,200.00」）
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        label_match = _LINE_LABEL_RE.match(line)
        if not label_match:
            continue
        label = label_match.group(1).strip()
        value = label_match.group(2).strip()
        for field_name, labels in _FIELD_LABELS.items():
            if any(label.casefold().startswith(item.casefold()) for item in labels):
                fields.setdefault(field_name, value)
                matched.append(field_name)
                break

    # 全文本兜底：金额 / 日期（未命中标签行时）
    if "amount" not in fields:
        amounts = [
            m.strip() for m in _AMOUNT_RE.findall(text)
            if any(ch.isdigit() for ch in m) and m.strip()
        ]
        if amounts:
            fields["amount"] = amounts[-1]
            matched.append("amount")
    if "date" not in fields:
        dates = _DATE_RE.findall(text)
        if dates:
            fields["date"] = dates[-1]
            matched.append("date")

    return {
        "fields": fields,
        "matched": sorted(set(matched)),
        "source_text_len": len(text),
    }
