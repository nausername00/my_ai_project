"""L0 perception – screen / image capture with a strict permission gate.

Placeholder-first design
------------------------
All side-effect helpers (*capture*, *ocr*, *analyze*) share the same hard
permission pattern: their *first* keyword argument is ``approved`` with a
default of ``False``; the function body raises
:class:`utils.PermissionDenied` *before* importing any optional dependency.
This means the module always imports and type-checks with zero third-party
packages.  Real image / OCR / ML capabilities are gated behind the
``perception`` extra from :data:`pyproject.toml` and surfaced here through
``importlib`` lazy loading that raises
:class:`utils.ModuleUnavailableError` with a helpful hint when the extra
hasn't been installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path
from typing import Any, Iterable, Mapping

from utils import (
    ModuleUnavailableError,
    PermissionDenied,
    SingletonLock,
    safe_filename,
    utc_now_iso,
)

__all__ = [
    "CapturedFrame",
    "OCRLine",
    "ScreenReader",
    "VisionError",
    "analyze_image",
    "capture_screen",
    "describe_screen_context",
    "run_ocr",
]


class VisionError(RuntimeError):
    """Raised for any L0 perception failure that isn't a permission or
    missing-dependency error."""


@dataclass(frozen=True)
class CapturedFrame:
    """Single screen frame captured from the desktop."""

    width: int
    height: int
    bytes_length: int
    format: str = "png"
    path: str | None = None
    captured_at: str = ""
    sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "width": int(self.width),
            "height": int(self.height),
            "bytes_length": int(self.bytes_length),
            "format": self.format,
            "path": self.path,
            "captured_at": self.captured_at,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class OCRLine:
    text: str
    confidence: float
    bbox: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "confidence": round(float(self.confidence), 4),
            "bbox": [round(float(v), 3) for v in self.bbox],
        }


# ---------------------------------------------------------------------------
# Internal helpers – import or raise
# ---------------------------------------------------------------------------

def _require_pil(operation: str) -> Any:
    if find_spec("PIL") is None:
        raise ModuleUnavailableError(
            f"{operation} requires the Pillow library; install the "
            "'perception' extra (pip install .[perception])"
        )
    import importlib
    return importlib.import_module("PIL.ImageGrab")


def _require_mss(operation: str) -> Any:
    if find_spec("mss") is None:
        raise ModuleUnavailableError(
            f"{operation} requires mss; install the 'perception' extra"
        )
    import importlib
    return importlib.import_module("mss")


def _require_easyocr(operation: str) -> Any:
    if find_spec("easyocr") is None:
        raise ModuleUnavailableError(
            f"{operation} requires easyocr; install the 'perception' extra"
        )
    import importlib
    return importlib.import_module("easyocr")


def _permission_check(operation: str, approved: bool, *, purpose: str | None = None) -> None:
    if not approved:
        detail = purpose and f" 目的：{purpose}" or ""
        raise PermissionDenied(
            f"用户尚未授权屏幕感知操作 '{operation}'。{detail}\n"
            "请通过权限对话框显式确认 approved=True 后重试。"
        )


# ---------------------------------------------------------------------------
# Public API – functions
# ---------------------------------------------------------------------------

def capture_screen(
    *,
    approved: bool = False,
    purpose: str | None = None,
    region: tuple[int, int, int, int] | None = None,
    save_dir: str | Path | None = None,
    monitor: int = 0,
) -> CapturedFrame:
    """Capture the primary (or given) monitor.

    Parameters
    ----------
    approved:
        Hard permission gate – the default ``False`` aborts immediately.
    purpose:
        Short human-readable justification; surfaced in the permission
        error so callers *and* end-users understand why the capture was
        attempted.
    region:
        Optional ``(left, top, width, height)`` crop.  ``None`` captures
        the full monitor.
    save_dir:
        When provided the PNG bytes are additionally written under this
        directory (filename is sanitised); this also sets the returned
        :attr:`CapturedFrame.path`.
    monitor:
        ``mss`` monitor index – 0 means "all monitors combined".
    """
    _permission_check("capture_screen", approved, purpose=purpose)
    mss_mod = _require_mss("capture_screen")
    pil_grab = _require_pil("capture_screen")
    from utils import sha256_hex, truncate_text

    captured_at = utc_now_iso()
    image_bytes: bytes | None = None
    try:
        with mss_mod.mss() as sct:
            monitors = sct.monitors or [{}]
            mon = monitors[min(monitor, max(0, len(monitors) - 1))] or monitors[0]
            shot = sct.grab(mon)
            # Convert to a PIL image so downstream code has a uniform payload
            Image = _require_pil("capture_screen").Image
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            if region:
                x, y, w, h = (int(v) for v in region)
                img = img.crop((x, y, x + w, y + h))
            import io
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            image_bytes = buf.getvalue()
            w, h = img.size
    except VisionError:
        raise
    except Exception as exc:  # pragma: no cover - library-specific
        raise VisionError(f"screen capture failed: {exc}") from exc

    digest = sha256_hex(image_bytes)
    path: str | None = None
    if save_dir is not None:
        save_path = Path(save_dir).expanduser().resolve()
        save_path.mkdir(parents=True, exist_ok=True)
        file_name = safe_filename(
            f"screen_{truncate_text(captured_at.replace(':','-'), 40, '')}_{digest[:10]}.png"
        )
        target = save_path / file_name
        target.write_bytes(image_bytes)
        path = target.as_posix()
    return CapturedFrame(
        width=w,
        height=h,
        bytes_length=len(image_bytes),
        format="png",
        path=path,
        captured_at=captured_at,
        sha256=digest,
    )


def run_ocr(
    image_path: str | Path,
    *,
    approved: bool = False,
    purpose: str | None = None,
    languages: Iterable[str] = ("ch_sim", "en"),
) -> list[OCRLine]:
    """Run easyocr against a local image file.

    This call is intentionally *stateless*: the caller is responsible for
    passing an already-captured path (so the permission trail for *what*
    is OCR'd is explicit in the file-system history).
    """
    _permission_check("run_ocr", approved, purpose=purpose)
    p = Path(image_path).expanduser().resolve()
    if not p.is_file():
        raise VisionError(f"ocr input file not found: {p.as_posix()}")
    reader_cls = _require_easyocr("run_ocr").Reader
    try:
        reader = reader_cls(list(languages), gpu=False, verbose=False)
        raw = reader.readtext(p.as_posix())
    except Exception as exc:  # pragma: no cover - lib-specific
        raise VisionError(f"ocr failed: {exc}") from exc
    out: list[OCRLine] = []
    for bbox, text, conf in raw or ():
        try:
            xs = [float(p[0]) for p in bbox]
            ys = [float(p[1]) for p in bbox]
            x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
        except Exception:
            x0 = y0 = x1 = y1 = 0.0
        out.append(
            OCRLine(
                text=str(text).strip(),
                confidence=float(conf or 0.0),
                bbox=(x0, y0, x1, y1),
            )
        )
    out.sort(key=lambda ln: (ln.bbox[1], ln.bbox[0]))
    return out


def analyze_image(
    image: str | Path | bytes,
    engine: Any = None,
    *,
    approved: bool = False,
    purpose: str | None = None,
    max_tokens: int = 220,
) -> dict[str, Any]:
    """Ask an optional pluggable ``engine`` to describe an image.

    The function is a *thin* adapter – it does not itself load vision
    models.  When no real engine is supplied (the default) the description
    is a short, safe, structural stub so the rest of the pipeline can
    always reason *about* vision without waiting for heavy deps.
    """
    _permission_check("analyze_image", approved, purpose=purpose)
    import io, hashlib, os
    data: bytes
    if isinstance(image, (str, Path)):
        p = Path(image).expanduser().resolve()
        if not p.is_file():
            raise VisionError(f"image file not found: {p.as_posix()}")
        if p.stat().st_size > 10 * 1024 * 1024:
            raise VisionError("image exceeds the 10 MB analysis limit")
        data = p.read_bytes()
        source = p.as_posix()
    else:
        data = bytes(image)
        source = "bytes"
    if not data:
        raise VisionError("image is empty")
    if len(data) > 10 * 1024 * 1024:
        raise VisionError("image exceeds the 10 MB analysis limit")

    sha = hashlib.sha256(data).hexdigest()
    size_kb = round(len(data) / 1024.0, 2)
    base = {
        "source": source,
        "bytes": len(data),
        "size_kb": size_kb,
        "sha256": sha,
        "analyzed_at": utc_now_iso(),
    }
    model_name = getattr(engine, "model_name", "placeholder") if engine else "placeholder"
    if engine is None or model_name == "placeholder":
        return {
            **base,
            "engine": "placeholder",
            "summary": (
                "[视觉分析占位] 已收到图片（未启用视觉模型）。"
                "若需要真实内容描述，请传入支持多模态的 inference engine "
                "并确保已批准 analyze_image 权限。"
            ),
            "labels": [],
            "has_text": None,
        }
    try:
        from inference import GenerationRequest
    except Exception as exc:  # pragma: no cover - optional dep
        return {
            **base,
            "engine": model_name,
            "summary": f"[未完成] 无法构造 GenerationRequest: {exc}",
            "labels": [],
            "has_text": None,
        }
    req = GenerationRequest(
        prompt=(
            "请用 2-4 句中文描述这张图的内容、主角、布局、显眼文字或 UI；"
            "最后输出三行短标签。格式：\nsummary: ...\nlabels: tag1,tag2,tag3\nhas_text: yes/no"
        ),
        max_tokens=max_tokens,
        temperature=0.1,
        system_prompt="你是保守的视觉分析师，禁止编造看不到的细节。",
    )
    try:
        raw = engine.generate(req, image=data).strip()
    except Exception as exc:
        return {
            **base,
            "engine": model_name,
            "summary": f"[模型调用失败] {exc}",
            "labels": [],
            "has_text": None,
            "error": str(exc),
        }
    summary = ""
    labels: list[str] = []
    has_text: bool | None = None
    for line in raw.splitlines():
        if line.lower().startswith("summary:"):
            summary = line.split(":", 1)[1].strip()
        elif line.lower().startswith("labels:"):
            labels = [s.strip() for s in line.split(":", 1)[1].split(",") if s.strip()]
        elif line.lower().startswith("has_text:"):
            tail = line.split(":", 1)[1].strip().lower()
            has_text = tail in {"yes", "true", "1", "y"}
    if not summary:
        summary = raw[:400]
    return {
        **base,
        "engine": model_name,
        "summary": summary,
        "labels": labels[:10],
        "has_text": has_text,
    }


# ---------------------------------------------------------------------------
# Public API – convenience facade
# ---------------------------------------------------------------------------

def describe_screen_context(
    *,
    approved: bool = False,
    purpose: str | None = None,
    run_ocr_flag: bool = False,
    save_dir: str | Path | None = None,
) -> dict[str, Any]:
    """One-shot helper that captures the screen and (optionally) OCRs it
    before returning a text-friendly summary for L1 scene classification.
    """
    frame = capture_screen(approved=approved, purpose=purpose, save_dir=save_dir)
    context: dict[str, Any] = {"frame": frame.to_dict()}
    ocr_lines: list[OCRLine] = []
    if run_ocr_flag and frame.path:
        ocr_lines = run_ocr(
            frame.path,
            approved=approved,
            purpose=purpose,
        )
        joined = "\n".join(l.text for l in ocr_lines if l.confidence >= 0.45)
        context["ocr_text"] = joined[:3000]
        context["ocr_lines"] = [l.to_dict() for l in ocr_lines[:60]]
    else:
        context["ocr_text"] = ""
        context["ocr_lines"] = []
    return context


class ScreenReader:
    """Reusable facade with a thread-safe cache for the (expensive) easyocr
    reader instance.

    The class exists for long-lived processes (a companion app loop) that
    want to amortise reader load time.  Permission checks are *still* done
    per-call via the ``approved=`` flag on every public method.
    """

    def __init__(self, *, languages: Iterable[str] = ("ch_sim", "en")) -> None:
        self.languages = tuple(languages)
        self._reader: Any = None
        self._lock = SingletonLock()

    # ------------------------------------------------------------------
    def capture(
        self,
        *,
        approved: bool = False,
        purpose: str | None = None,
        **kwargs: Any,
    ) -> CapturedFrame:
        return capture_screen(approved=approved, purpose=purpose, **kwargs)

    def ocr(
        self,
        image_path: str | Path,
        *,
        approved: bool = False,
        purpose: str | None = None,
    ) -> list[OCRLine]:
        _permission_check("ScreenReader.ocr", approved, purpose=purpose)
        easyocr_mod = _require_easyocr("ScreenReader.ocr")
        with self._lock:
            if self._reader is None:
                self._reader = easyocr_mod.Reader(
                    list(self.languages), gpu=False, verbose=False
                )
            reader = self._reader
        p = Path(image_path).expanduser().resolve()
        if not p.is_file():
            raise VisionError(f"ocr input file not found: {p.as_posix()}")
        try:
            raw = reader.readtext(p.as_posix())
        except Exception as exc:  # pragma: no cover - lib-specific
            raise VisionError(f"ocr failed: {exc}") from exc
        out: list[OCRLine] = []
        for bbox, text, conf in raw or ():
            try:
                xs = [float(pt[0]) for pt in bbox]
                ys = [float(pt[1]) for pt in bbox]
                box = (min(xs), min(ys), max(xs), max(ys))
            except Exception:
                box = (0.0, 0.0, 0.0, 0.0)
            out.append(OCRLine(text=str(text).strip(), confidence=float(conf or 0.0), bbox=box))
        out.sort(key=lambda ln: (ln.bbox[1], ln.bbox[0]))
        return out
