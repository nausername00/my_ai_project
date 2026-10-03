"""L4 execution – creative / visual rendering (SVG + Pillow fallback).

The module provides three rendering strategies:

* :class:`SVGRenderer` – pure-stdlib SVG generator, always works (no dep).
* :class:`PillowRenderer` – optional Pillow-based PNG / JPEG rasterizer.
* :class:`Creator` – façade that takes a text prompt and returns either an
  SVG document or a stub image summary; never calls remote image models
  (that's the responsibility of :mod:`inference` if a caller wants it).

Permission gates are only present for file-system *side effects* (``save``),
not in-memory string generation.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path
import textwrap
from typing import Any, Iterable, Mapping, Sequence
import xml.sax.saxutils

from utils import PermissionDenied, SingletonLock, safe_filename, truncate_text, utc_now_iso

__all__ = [
    "Creator",
    "ImagePayload",
    "PillowRenderer",
    "RenderError",
    "SVGRenderer",
    "render_avatar_svg",
    "render_cover_svg",
]


class RenderError(RuntimeError):
    pass


@dataclass(frozen=True)
class ImagePayload:
    kind: str            # "svg" | "png" | "jpeg" | "placeholder"
    width: int
    height: int
    bytes_length: int
    content: Any         # str for SVG, bytes for raster, dict for placeholder
    path: str | None = None
    prompt: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        content_preview: Any
        if isinstance(self.content, (bytes, bytearray)):
            content_preview = f"<bytes len={len(self.content)}>"
        else:
            content_preview = truncate_text(str(self.content), 400, "")
        return {
            "kind": self.kind,
            "width": int(self.width),
            "height": int(self.height),
            "bytes_length": int(self.bytes_length),
            "content_preview": content_preview,
            "path": self.path,
            "prompt": self.prompt,
            "created_at": self.created_at,
        }


# ---------------------------------------------------------------------------
# Pure-stdlib SVG renderer
# ---------------------------------------------------------------------------

_PALETTES: dict[str, tuple[str, ...]] = {
    "sunrise": ("#FFB88C", "#DE6262", "#8E2DE2", "#4A00E0"),
    "ocean":   ("#2193B0", "#6DD5ED", "#134E5E", "#71B280"),
    "forest":  ("#134E5E", "#71B280", "#ACC3A6", "#F5F5DC"),
    "candy":   ("#FFAFBD", "#FFC3A0", "#FF5F6D", "#FFC371"),
    "midnight":("#0F2027", "#203A43", "#2C5364", "#636363"),
    "mono":    ("#000000", "#333333", "#777777", "#CCCCCC"),
}


def _palette(name: str | None) -> tuple[str, ...]:
    name = (name or "sunrise").lower()
    return _PALETTES.get(name, _PALETTES["sunrise"])


class SVGRenderer:
    def __init__(self, width: int = 1024, height: int = 768, palette: str | None = None) -> None:
        if width < 32 or height < 32 or width > 8192 or height > 8192:
            raise RenderError("invalid canvas size (32..8192)")
        self.width = int(width)
        self.height = int(height)
        self.palette = _palette(palette)

    # ------------------------------------------------------------------
    def _wrap(self, body: str, *, title: str | None = None) -> str:
        esc_title = (
            f"<title>{xml.sax.saxutils.escape(title or '')}</title>" if title else ""
        )
        return (
            f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width} {self.height}" '
            f'width="{self.width}" height="{self.height}">\n'
            f"{esc_title}\n{body}\n</svg>\n"
        )

    # ------------------------------------------------------------------
    def gradient(self, *, id: str, colors: Sequence[str], vertical: bool = True) -> str:
        stops = "".join(
            f'<stop offset="{i / max(1, len(colors)-1):.3f}" stop-color="{c}" />'
            for i, c in enumerate(colors)
        )
        x1, y1, x2, y2 = ("0", "0", "0", "1") if vertical else ("0", "0", "1", "0")
        return (
            f'<defs><linearGradient id="{id}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}">'
            f"{stops}</linearGradient></defs>\n"
        )

    # ------------------------------------------------------------------
    def cover(self, title: str, subtitle: str = "", *, palette: str | None = None) -> ImagePayload:
        pal = _palette(palette) if palette else self.palette
        W, H = self.width, self.height
        title = truncate_text(title, 120, "")
        subtitle = truncate_text(subtitle, 240, "")
        escaped_title = xml.sax.saxutils.escape(title)
        escaped_sub = xml.sax.saxutils.escape(subtitle)
        lines_title = textwrap.wrap(escaped_title, width=18, max_lines=3, replace_whitespace=False)
        lines_sub = textwrap.wrap(escaped_sub, width=36, max_lines=2, replace_whitespace=False)
        body = (
            self.gradient(id="g", colors=pal[:4])
            + f'<rect width="{W}" height="{H}" fill="url(#g)" rx="32"/>\n'
            + f'<circle cx="{W*0.85}" cy="{H*0.18}" r="{min(W,H)*0.08}" fill="white" opacity="0.12"/>\n'
            + f'<circle cx="{W*0.15}" cy="{H*0.85}" r="{min(W,H)*0.11}" fill="white" opacity="0.08"/>\n'
        )
        base_y = H / 2 - (len(lines_title) * 48 + len(lines_sub) * 30) / 2
        for i, line in enumerate(lines_title):
            body += (
                f'<text x="{W/2}" y="{base_y + i*56}" text-anchor="middle" '
                f'fill="white" font-family="system-ui, -apple-system, Segoe UI, sans-serif" '
                f'font-size="56" font-weight="700">{line}</text>\n'
            )
        base_y += len(lines_title) * 56 + 30
        for i, line in enumerate(lines_sub):
            body += (
                f'<text x="{W/2}" y="{base_y + i*34}" text-anchor="middle" '
                f'fill="rgba(255,255,255,0.9)" font-family="system-ui, -apple-system, Segoe UI, sans-serif" '
                f'font-size="26">{line}</text>\n'
            )
        body += f'<text x="{W/2}" y="{H*0.92}" text-anchor="middle" fill="white" opacity="0.7" font-size="18">Moling 墨灵 · Generated</text>\n'
        svg = self._wrap(body, title=title or "cover")
        return ImagePayload(
            kind="svg", width=W, height=H, bytes_length=len(svg.encode("utf-8")),
            content=svg, prompt=title, created_at=utc_now_iso(),
        )

    # ------------------------------------------------------------------
    def avatar(self, name: str, *, palette: str | None = None, size: int = 512) -> ImagePayload:
        pal = _palette(palette) if palette else self.palette
        size = max(32, min(2048, int(size)))
        name = truncate_text(name.strip() or "?", 6, "")
        letter = (name[:1] or "?").upper()
        esc = xml.sax.saxutils.escape(letter)
        W = H = size
        body = (
            self.gradient(id="g2", colors=pal[:3])
            + f'<rect width="{W}" height="{H}" fill="url(#g2)" rx="{W/2}"/>\n'
            + f'<text x="{W/2}" y="{H/2 + size*0.12}" text-anchor="middle" '
            f'fill="white" font-family="system-ui, -apple-system, Segoe UI, sans-serif" '
            f'font-size="{int(size*0.5)}" font-weight="700">{esc}</text>\n'
        )
        svg = self._wrap(body, title=name)
        return ImagePayload(
            kind="svg", width=W, height=H, bytes_length=len(svg.encode("utf-8")),
            content=svg, prompt=name, created_at=utc_now_iso(),
        )

    # ------------------------------------------------------------------
    def chart(self, title: str, values: Sequence[float], *, palette: str | None = None) -> ImagePayload:
        if not values:
            raise RenderError("chart requires at least one value")
        pal = _palette(palette) if palette else self.palette
        W, H = self.width, self.height
        pad_l, pad_r, pad_t, pad_b = 80, 40, 100, 80
        cw = W - pad_l - pad_r
        ch = H - pad_t - pad_b
        vmax = max(1.0e-9, float(max(values)))
        vmin = min(0.0, float(min(values)))
        span = max(1.0e-9, vmax - vmin)
        bar_w = cw / len(values) * 0.72
        step = cw / len(values)
        body = (
            self.gradient(id="g3", colors=("white", "#F7F8FF"))
            + f'<rect width="{W}" height="{H}" fill="url(#g3)" rx="24"/>\n'
            + f'<text x="{W/2}" y="56" text-anchor="middle" font-size="28" font-weight="700" '
            f'fill="#1E293B">{xml.sax.saxutils.escape(truncate_text(title, 80, ""))}</text>\n'
        )
        for i, v in enumerate(values):
            v_norm = (float(v) - vmin) / span
            bar_h = max(2.0, ch * v_norm)
            x = pad_l + i * step + (step - bar_w) / 2
            y = pad_t + ch - bar_h
            color = pal[i % len(pal)]
            body += (
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" '
                f'fill="{color}" rx="8"/>\n'
            )
        svg = self._wrap(body, title=title or "chart")
        return ImagePayload(
            kind="svg", width=W, height=H, bytes_length=len(svg.encode("utf-8")),
            content=svg, prompt=title, created_at=utc_now_iso(),
        )

    # ------------------------------------------------------------------
    def save(self, payload: ImagePayload, directory: str | Path, *,
             approved: bool = False, purpose: str | None = None) -> ImagePayload:
        if not approved:
            detail = purpose and f"（目的：{purpose}）" or ""
            raise PermissionDenied(
                f"尚未授权 SVGRenderer.save 写入磁盘{detail}。显式 approved=True。"
            )
        if payload.kind != "svg":
            raise RenderError("SVGRenderer.save only writes SVG payloads; use PillowRenderer for raster")
        target_dir = Path(directory).expanduser().resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
        name = safe_filename(
            f"svg_{utc_now_iso().replace(':','-')}_{truncate_text(payload.prompt or 'image', 24, '')}.svg"
        )
        path = target_dir / name
        path.write_text(str(payload.content), encoding="utf-8")
        return ImagePayload(
            kind=payload.kind, width=payload.width, height=payload.height,
            bytes_length=payload.bytes_length, content=payload.content,
            path=path.as_posix(), prompt=payload.prompt, created_at=utc_now_iso(),
        )


def render_cover_svg(title: str, subtitle: str = "", **kw) -> ImagePayload:
    return SVGRenderer(**{k:v for k,v in kw.items() if k in {"width","height","palette"}}).cover(title, subtitle)


def render_avatar_svg(name: str, **kw) -> ImagePayload:
    r = SVGRenderer(**{k:v for k,v in kw.items() if k in {"palette"}})
    return r.avatar(name, size=int(kw.get("size", 512)))


# ---------------------------------------------------------------------------
# Optional Pillow raster adapter
# ---------------------------------------------------------------------------

class PillowRenderer:
    def __init__(self, width: int = 1024, height: int = 768) -> None:
        self.width = int(width)
        self.height = int(height)

    # ------------------------------------------------------------------
    def _pil(self):
        if find_spec("PIL") is None:
            raise ModuleUnavailableError(
                "PillowRenderer 需要 Pillow；请安装 execution extra:  pip install .[execution]"
            )
        import importlib
        return importlib.import_module("PIL.Image"), importlib.import_module("PIL.ImageDraw"), importlib.import_module("PIL.ImageFont")

    # ------------------------------------------------------------------
    def rasterize_svg(self, svg: ImagePayload, *, fmt: str = "PNG",
                      approved: bool = False, purpose: str | None = None) -> ImagePayload:
        # Permission gate because rasterising via Cairo/cairosvg is an
        # optional dep and often triggers heavy native code.
        if not approved:
            raise PermissionDenied("尚未授权 PillowRenderer.rasterize_svg。请显式 approved=True。")
        if find_spec("cairosvg") is None:
            raise ModuleUnavailableError(
                "rasterize_svg 需要 cairosvg；请安装 execution extra。"
            )
        import importlib, io
        cairosvg = importlib.import_module("cairosvg")
        svg_bytes = str(svg.content).encode("utf-8")
        try:
            png_bytes = cairosvg.svg2png(bytestring=svg_bytes, output_width=self.width, output_height=self.height)
        except Exception as exc:
            raise RenderError(f"rasterize_svg failed: {exc}") from exc
        Image, _Draw, _Font = self._pil()
        bio = io.BytesIO(png_bytes)
        img = Image.open(bio).convert("RGBA")
        out = io.BytesIO()
        fmt_up = str(fmt).upper()
        if fmt_up == "JPEG":
            img = img.convert("RGB")
            img.save(out, format="JPEG", quality=90)
            kind = "jpeg"
        else:
            img.save(out, format="PNG")
            kind = "png"
        data = out.getvalue()
        return ImagePayload(
            kind=kind, width=self.width, height=self.height, bytes_length=len(data),
            content=data, prompt=svg.prompt, created_at=utc_now_iso(),
        )

    # ------------------------------------------------------------------
    def save(self, payload: ImagePayload, directory: str | Path, *,
             approved: bool = False, purpose: str | None = None) -> ImagePayload:
        if not approved:
            detail = purpose and f"（目的：{purpose}）" or ""
            raise PermissionDenied(f"尚未授权 PillowRenderer.save 写入磁盘{detail}。")
        if payload.kind not in {"png", "jpeg"}:
            raise RenderError("PillowRenderer.save 只支持 png/jpeg；请先 rasterize_svg")
        target_dir = Path(directory).expanduser().resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
        ext = {"png": "png", "jpeg": "jpg"}[payload.kind]
        name = safe_filename(
            f"img_{utc_now_iso().replace(':','-')}_{truncate_text(payload.prompt or 'image', 24, '')}.{ext}"
        )
        path = target_dir / name
        path.write_bytes(bytes(payload.content))
        return ImagePayload(
            kind=payload.kind, width=payload.width, height=payload.height,
            bytes_length=payload.bytes_length, content=payload.content,
            path=path.as_posix(), prompt=payload.prompt, created_at=utc_now_iso(),
        )


# ---------------------------------------------------------------------------
# Creator façade – one entry point for L4 创作 channel
# ---------------------------------------------------------------------------

class Creator:
    """Prompt-driven creative helper (no network access).

    ``create(prompt, kind=...)`` routes to SVGRenderer / PillowRenderer
    automatically and never blocks on remote models.  For true generative
    image synthesis callers should pass an :class:`InferenceEngine` into a
    higher-level helper that owns its own permission gate.
    """

    def __init__(self, *, default_palette: str | None = None, width: int = 1024, height: int = 768) -> None:
        self.svg = SVGRenderer(width=width, height=height, palette=default_palette)
        self.raster = PillowRenderer(width=width, height=height)
        self._lock = SingletonLock()

    def create(
        self,
        prompt: str,
        *,
        kind: str = "cover",
        **kwargs: Any,
    ) -> ImagePayload:
        kind = (kind or "cover").lower()
        with self._lock:
            if kind in {"cover", "poster", "banner"}:
                return self.svg.cover(prompt, subtitle=kwargs.get("subtitle", "") or "", palette=kwargs.get("palette"))
            if kind in {"avatar", "icon"}:
                return self.svg.avatar(kwargs.get("name") or prompt, palette=kwargs.get("palette"), size=int(kwargs.get("size", 512)))
            if kind in {"chart", "bar"}:
                values = list(kwargs.get("values") or [])
                if not values:
                    raise RenderError("kind=chart 需要参数 values=[...]")
                return self.svg.chart(prompt, values, palette=kwargs.get("palette"))
            if kind == "placeholder":
                summary = {
                    "prompt": prompt,
                    "kind": kwargs.get("target_kind", "remote_generation"),
                    "note": "Creator placeholder：如需真实网络生图请在 controller 里调用带权限闸门的 inference engine。",
                }
                body = repr(summary)
                return ImagePayload(
                    kind="placeholder", width=self.svg.width, height=self.svg.height,
                    bytes_length=len(body.encode("utf-8")), content=summary,
                    prompt=prompt, created_at=utc_now_iso(),
                )
        raise RenderError(f"未知 kind: {kind!r}。支持：cover / avatar / chart / placeholder。")
