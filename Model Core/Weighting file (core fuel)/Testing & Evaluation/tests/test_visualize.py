"""D 层测试补全 · visualize：SVG 封面/头像/图表渲染、保存（需授权）、Creator 入口、色板回落（PIL 分支按环境跳过）。"""

import os
import tempfile
import unittest

from visualize import (
    Creator,
    ImagePayload,
    PermissionDenied,
    RenderError,
    SVGRenderer,
    _palette,
    render_avatar_svg,
    render_cover_svg,
)


class ImagePayloadTest(unittest.TestCase):
    def test_to_dict(self) -> None:
        payload = ImagePayload(
            kind="svg", width=1024, height=768, bytes_length=7,
            content="<svg/>", path=None, prompt="标题", created_at="2026-10-16T00:00:00Z",
        )
        data = payload.to_dict()
        self.assertEqual(data["kind"], "svg")
        self.assertEqual(data["width"], 1024)
        self.assertEqual(data["bytes_length"], 7)
        self.assertIn("content_preview", data)
        self.assertEqual(data["prompt"], "标题")

    def test_bytes_content_preview(self) -> None:
        payload = ImagePayload(kind="png", width=1, height=1, bytes_length=3, content=b"\x89PNG")
        data = payload.to_dict()
        self.assertIn("bytes", data["content_preview"])


class PaletteTest(unittest.TestCase):
    def test_known_palette(self) -> None:
        self.assertEqual(_palette("ocean")[0], "#2193B0")

    def test_unknown_palette_falls_back(self) -> None:
        self.assertEqual(_palette("not-a-palette"), _palette("sunrise"))

    def test_none_falls_back(self) -> None:
        self.assertEqual(_palette(None), _palette("sunrise"))


class SVGRendererTest(unittest.TestCase):
    def setUp(self) -> None:
        self.renderer = SVGRenderer(width=800, height=600)

    def _svg_text(self, payload: ImagePayload) -> str:
        self.assertEqual(payload.kind, "svg")
        self.assertIsInstance(payload.content, str)
        return payload.content

    def test_cover_svg(self) -> None:
        payload = self.renderer.cover("墨灵伙伴系统", subtitle="本地 AI 生态")
        text = self._svg_text(payload)
        self.assertIn("<svg", text)
        self.assertIn("墨灵伙伴系统", text)
        self.assertIn("本地 AI 生态", text)
        self.assertIn(f'width="{800}"', text)

    def test_avatar_svg(self) -> None:
        payload = self.renderer.avatar("墨灵", size=256)
        text = self._svg_text(payload)
        self.assertIn("<svg", text)
        self.assertIn("墨灵", text)

    def test_chart_svg(self) -> None:
        payload = self.renderer.chart("本月对话", [3.0, 5.0, 2.0])
        text = self._svg_text(payload)
        self.assertIn("<svg", text)
        self.assertIn("本月对话", text)

    def test_chart_rejects_empty_values(self) -> None:
        with self.assertRaises(RenderError):
            self.renderer.chart("空", [])

    def test_constructor_rejects_tiny_canvas(self) -> None:
        with self.assertRaises(RenderError):
            SVGRenderer(width=8, height=8)

    def test_save_requires_approval(self) -> None:
        payload = self.renderer.cover("授权测试")
        with self.assertRaises(PermissionDenied):
            self.renderer.save(payload, tempfile.gettempdir())

    def test_save_writes_file_when_approved(self) -> None:
        payload = self.renderer.cover("保存测试")
        with tempfile.TemporaryDirectory() as tmp:
            saved = self.renderer.save(payload, tmp, approved=True)
            self.assertEqual(saved.kind, "svg")
            self.assertIsNotNone(saved.path)
            self.assertTrue(os.path.isfile(saved.path))
            with open(saved.path, "rb") as f:
                content = f.read()
        self.assertIn(b"<svg", content)


class HelperFunctionsTest(unittest.TestCase):
    def test_render_cover_svg(self) -> None:
        payload = render_cover_svg("快捷封面", subtitle="函数入口")
        self.assertEqual(payload.kind, "svg")
        self.assertIn("快捷封面", payload.content)

    def test_render_avatar_svg(self) -> None:
        payload = render_avatar_svg("快捷头像", size=128)
        self.assertEqual(payload.kind, "svg")
        self.assertIn("快捷头像", payload.content)


class CreatorTest(unittest.TestCase):
    def test_create_cover(self) -> None:
        creator = Creator()
        payload = creator.create("封面标题", kind="cover", subtitle="副标题")
        self.assertEqual(payload.kind, "svg")
        self.assertIn("封面标题", payload.content)

    def test_create_avatar(self) -> None:
        creator = Creator()
        payload = creator.create("伙伴名", kind="avatar", name="墨灵", size=128)
        self.assertEqual(payload.kind, "svg")

    def test_create_chart(self) -> None:
        creator = Creator()
        payload = creator.create("图表", kind="chart", values=[1.0, 2.0, 3.0])
        self.assertEqual(payload.kind, "svg")
        self.assertIn("图表", payload.content)

    def test_create_chart_missing_values(self) -> None:
        creator = Creator()
        with self.assertRaises(RenderError):
            creator.create("图表", kind="chart")

    def test_create_placeholder(self) -> None:
        creator = Creator()
        payload = creator.create("未来生图", kind="placeholder", target_kind="remote")
        self.assertEqual(payload.kind, "placeholder")
        self.assertIsInstance(payload.content, dict)

    def test_create_unknown_kind_rejected(self) -> None:
        creator = Creator()
        with self.assertRaises(RenderError):
            creator.create("x", kind="unknown")


class PillowRendererTest(unittest.TestCase):
    def test_pil_unavailable_skips_or_rasterizes(self) -> None:
        """PIL 可选：可用则 PNG 头校验，不可用则明确 ModuleUnavailableError/skip。"""
        from visualize import PillowRenderer

        renderer = PillowRenderer()
        svg = render_cover_svg("栅格化测试")
        try:
            payload = renderer.rasterize_svg(svg, fmt="PNG", approved=True)
        except Exception as exc:  # ModuleUnavailableError when no cairosvg
            self.assertIn("cairosvg", str(exc))
            self.skipTest("cairosvg 未安装，跳过栅格化分支")
        self.assertEqual(payload.kind, "png")
        self.assertEqual(payload.content[:8], b"\x89PNG\r\n\x1a\n")


if __name__ == "__main__":
    unittest.main()
