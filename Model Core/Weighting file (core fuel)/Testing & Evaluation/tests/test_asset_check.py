"""K0 素材检查脚本测试：边缘/裁切预检、PSD/MOV 结构报告、拼回合成、交付清单。"""

from __future__ import annotations

import io
import struct
import unittest

from PIL import Image

from asset_check import (
    assemble_layers,
    check_assets,
    check_sprite_edges,
    decode_image_safe,
    delivery_manifest,
    file_extension,
    format_manifest,
    inspect_extended,
    mov_boxes,
    psd_header,
)


def png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def make_sprite(*, edge: str | None = None) -> bytes:
    """构造透明角色图：居中主体；edge='light' 加亮边，edge='crop' 让内容贴边。"""
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    for x in range(16, 48):
        for y in range(16, 48):
            image.putpixel((x, y), (60, 60, 90, 255))
    if edge == "light":
        for x in range(64):
            image.putpixel((x, 0), (240, 240, 240, 255))
            image.putpixel((x, 63), (240, 240, 240, 255))
    if edge == "crop":
        for y in range(64):
            image.putpixel((0, y), (60, 60, 90, 255))
    return png_bytes(image)


class SpriteEdgeTests(unittest.TestCase):
    def test_clean_sprite_has_no_edge_warnings(self) -> None:
        result = check_sprite_edges(make_sprite())
        self.assertEqual(result["warnings"], [])

    def test_light_edge_is_reported_as_edge_residue(self) -> None:
        result = check_sprite_edges(make_sprite(edge="light"))
        joined = " ".join(result["warnings"])
        self.assertIn("边缘", joined)

    def test_touching_edge_is_reported_as_possible_crop(self) -> None:
        result = check_sprite_edges(make_sprite(edge="crop"))
        joined = " ".join(result["warnings"])
        self.assertIn("贴边", joined)

    def test_decode_rejects_truncated_image(self) -> None:
        data = png_bytes(Image.new("RGBA", (8, 8), (0, 0, 0, 0)))
        truncated = data[: len(data) // 2]
        with self.assertRaises(ValueError):
            decode_image_safe(truncated)


class AssembleTests(unittest.TestCase):
    def test_assemble_layers_composites_in_order(self) -> None:
        layer = Image.new("RGBA", (10, 10), (255, 0, 0, 255))
        canvas = assemble_layers([(layer, 5, 5)], (20, 20))
        self.assertEqual(canvas.size, (20, 20))
        self.assertEqual(canvas.getpixel((7, 7)), (255, 0, 0, 255))
        self.assertEqual(canvas.getpixel((0, 0)), (0, 0, 0, 0))


class PsdHeaderTests(unittest.TestCase):
    def _make_psd_header(self, *, has_layers: bool) -> bytes:
        header = b"8BPS" + struct.pack(">H6xH2I2H", 1, 3, 64, 64, 8, 3)
        color_data_len = struct.pack(">I", 0)
        resource_len = struct.pack(">I", 0)
        layer_section_len = struct.pack(">I", 8 if has_layers else 0)
        return header + color_data_len + resource_len + layer_section_len

    def test_valid_psd_reports_header_and_layer_section(self) -> None:
        result = psd_header(self._make_psd_header(has_layers=True))
        self.assertTrue(result["checks"]["signature_valid"])
        self.assertEqual(result["checks"]["width"], 64)
        self.assertTrue(result["checks"]["has_layer_section"])
        self.assertTrue(any("K2" in warning for warning in result["warnings"]))

    def test_bad_signature_is_rejected(self) -> None:
        result = psd_header(b"NOTPSD" + b"\x00" * 30)
        self.assertFalse(result["checks"]["signature_valid"])

    def test_short_file_is_reported(self) -> None:
        result = psd_header(b"\x00\x01")
        self.assertIn("过短", result["warnings"][0])


class MovBoxTests(unittest.TestCase):
    def _make_mov(self) -> bytes:
        ftyp_size = 8 + 8
        ftyp = struct.pack(">I", ftyp_size) + b"ftyp" + b"qt  " + b"\x00\x00\x02\x00"
        mdhd_size = 8 + 20
        mdhd = (
            struct.pack(">I", mdhd_size)
            + b"mdhd"
            + b"\x00"
            + b"\x00" * 3
            + b"\x00" * 8
            + struct.pack(">II", 600, 30000)
        )
        trak_size = 8 + mdhd_size
        trak = struct.pack(">I", trak_size) + b"trak" + mdhd
        moov_size = 8 + trak_size
        moov = struct.pack(">I", moov_size) + b"moov" + trak
        return ftyp + moov

    def test_mov_reports_brand_and_tracks(self) -> None:
        result = mov_boxes(self._make_mov())
        self.assertEqual(result["checks"]["brand"], "qt  ")
        self.assertEqual(result["checks"]["trak_count"], 1)
        self.assertAlmostEqual(result["checks"]["duration_seconds"], 50.0, places=3)
        self.assertTrue(any("K6" in warning for warning in result["warnings"]))

    def test_garbage_mov_reports_missing_ftyp(self) -> None:
        result = mov_boxes(b"\x00\x00\x00\x05\x00\x00\x00\x00")
        self.assertTrue(any("ftyp" in warning for warning in result["warnings"]))


class CheckAssetsTests(unittest.TestCase):
    def test_batch_check_includes_only_registered_for_unknown(self) -> None:
        results = check_assets(
            [{"name": "a.png", "data": make_sprite()}, {"name": "b.txt", "data": b"hello"}]
        )
        by_name = {entry["file_name"]: entry for entry in results}
        self.assertIn("checks", by_name["a.png"])
        self.assertTrue(any("尚未接入" in w for w in by_name["b.txt"]["warnings"]))

    def test_oversized_file_is_registered_without_reading(self) -> None:
        results = check_assets(
            [{"name": "big.png", "data": b"\x00" * (10 * 1024 * 1024 + 1)}]
        )
        self.assertTrue(any("上限" in w for w in results[0]["warnings"]))

    def test_empty_file_is_reported(self) -> None:
        results = check_assets([{"name": "empty.png", "data": b""}])
        self.assertTrue(any("为空" in w for w in results[0]["warnings"]))

    def test_extension_parsing_handles_dotted_names(self) -> None:
        self.assertEqual(file_extension("a.model3.json"), ".model3.json")
        self.assertEqual(file_extension("b.physics3.json"), ".physics3.json")
        self.assertEqual(file_extension("c.png"), ".png")
        self.assertEqual(file_extension("noext"), "")


class ManifestTests(unittest.TestCase):
    def test_complete_four_piece_manifest(self) -> None:
        manifest = delivery_manifest(
            ["base.psd", "parts.json", "seq_000.png", "seq_001.png", "character.model3.json"]
        )
        self.assertTrue(manifest["complete"])
        self.assertEqual(manifest["missing"], [])
        self.assertEqual(manifest["categories"]["透明 PNG 序列"], ["seq_000.png", "seq_001.png"])

    def test_incomplete_manifest_lists_missing(self) -> None:
        manifest = delivery_manifest(["base.psd"])
        self.assertFalse(manifest["complete"])
        self.assertIn("部件清单", manifest["missing"])
        self.assertIn("缺失", format_manifest(manifest))

    def test_inspect_extended_psd_mov(self) -> None:
        psd = inspect_extended(
            "base.psd",
            b"8BPS" + struct.pack(">H6xH2I2H", 1, 3, 64, 64, 8, 3) + b"\x00" * 12,
        )
        self.assertEqual(psd.format, "PSD")
        mov = inspect_extended("clip.mov", b"\x00\x00\x00\x18ftypqt  \x00\x00\x02\x00")
        self.assertEqual(mov.format, "QuickTime / MOV")


if __name__ == "__main__":
    unittest.main()
