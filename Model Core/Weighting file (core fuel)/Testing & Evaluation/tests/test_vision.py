import tempfile
import unittest
from pathlib import Path

from utils import PermissionDenied
from vision import VisionError, analyze_image


class VisionTests(unittest.TestCase):
    def test_image_analysis_passes_bytes_to_the_configured_engine(self) -> None:
        class LocalVisionEngine:
            model_name = "local-vision"

            def generate(self, request, *, image=None):
                self.request = request
                self.image = image
                return "summary: 一张测试图片\nlabels: test,local\nhas_text: yes"

        engine = LocalVisionEngine()
        image = b"\x89PNG\r\n\x1a\nsample"

        result = analyze_image(
            image,
            engine,
            approved=True,
            purpose="测试图片分析",
        )

        self.assertEqual(engine.image, image)
        self.assertIn("描述这张图", engine.request.prompt)
        self.assertEqual(result["summary"], "一张测试图片")
        self.assertEqual(result["labels"], ["test", "local"])
        self.assertTrue(result["has_text"])
        self.assertEqual(result["engine"], "local-vision")

    def test_image_analysis_requires_approval_and_nonempty_input(self) -> None:
        with self.assertRaisesRegex(PermissionDenied, "尚未授权"):
            analyze_image(b"image")

        with self.assertRaisesRegex(VisionError, "empty"):
            analyze_image(b"", approved=True)

    def test_image_analysis_rejects_oversized_bytes_and_files(self) -> None:
        with self.assertRaisesRegex(VisionError, "10 MB"):
            analyze_image(b"x" * (10 * 1024 * 1024 + 1), approved=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "large.png"
            with image_path.open("wb") as image_file:
                image_file.truncate(10 * 1024 * 1024 + 1)
            with self.assertRaisesRegex(VisionError, "10 MB"):
                analyze_image(image_path, approved=True)


if __name__ == "__main__":
    unittest.main()
