"""T2 OCR 与结构化抽取：引擎探测、规则抽取、OCR 明确报错、任务分发。"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from avatar_tasks import AvatarToolGate, AvatarToolLog, run_avatar_task
from ocr import detect_ocr_engine, extract_fields, ocr_text


class DetectEngineTest(unittest.TestCase):
    def test_returns_structured_result(self) -> None:
        result = detect_ocr_engine()
        self.assertIn("available", result)
        self.assertIn("hint", result)
        self.assertIsInstance(result["available"], bool)

    def test_unavailable_has_install_hint(self) -> None:
        with patch("ocr._find_tesseract", return_value=None):
            result = detect_ocr_engine()
            self.assertFalse(result["available"])
            self.assertIn("Tesseract", result["hint"])
            self.assertIn("不依赖网络", result["hint"])


class ExtractFieldsTest(unittest.TestCase):
    def test_label_lines(self) -> None:
        text = (
            "供应商：山间小筑文创有限公司\n"
            "发票号：INV-2026-00123\n"
            "日期：2026-10-16\n"
            "金额：¥1,280.50\n"
        )
        result = extract_fields(text)
        fields = result["fields"]
        self.assertEqual(fields["supplier"], "山间小筑文创有限公司")
        self.assertEqual(fields["invoice_no"], "INV-2026-00123")
        self.assertEqual(fields["date"], "2026-10-16")
        self.assertEqual(fields["amount"], "¥1,280.50")
        self.assertIn("amount", result["matched"])

    def test_amount_fallback_from_plain_text(self) -> None:
        result = extract_fields("本月水电费共计 89.60 元，请及时缴纳。")
        self.assertEqual(result["fields"]["amount"], "89.60")

    def test_date_fallback_variants(self) -> None:
        result = extract_fields("开票时间 2026/10/16 之后请核对。")
        self.assertEqual(result["fields"]["date"], "2026/10/16")

    def test_no_match_does_not_invent(self) -> None:
        result = extract_fields("今天天气不错，适合散步。")
        self.assertEqual(result["fields"], {})
        self.assertEqual(result["matched"], [])

    def test_english_labels(self) -> None:
        result = extract_fields("Vendor: Acme Ltd\nTotal: $42.00\nDate: 2026-10-15")
        self.assertEqual(result["fields"]["supplier"], "Acme Ltd")
        self.assertEqual(result["fields"]["amount"], "$42.00")
        self.assertEqual(result["fields"]["date"], "2026-10-15")


class OcrTextTest(unittest.TestCase):
    def test_missing_file_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            ocr_text("Z:/no/such/file.png")
        self.assertIn("不存在", str(ctx.exception))

    def test_no_engine_raises_with_hint_not_silent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "sample.png"
            image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
            with patch("ocr._find_tesseract", return_value=None):
                with self.assertRaises(ValueError) as ctx:
                    ocr_text(str(image))
                message = str(ctx.exception)
                self.assertIn("OCR 引擎", message)
                self.assertIn("Tesseract", message)


class AvatarTaskOcrTest(unittest.TestCase):
    """T2 任务分发：extract_fields 走分身任务通道；ocr_text 无引擎明确失败。"""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        log = AvatarToolLog(Path(self.temp_dir.name) / "tool_log.json")
        self.gate = AvatarToolGate(log)
        self.log = log

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _run(self, task: str, payload: dict) -> dict:
        return run_avatar_task(
            avatar_id="learning",
            task=task,
            payload=payload,
            approved=False,
            gate=self.gate,
            log=self.log,
            domain="learning",
        )

    def test_extract_fields_task_ok(self) -> None:
        result = self._run(
            "extract_fields",
            {"text": "供应商：测试公司\n金额：¥66.00"},
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["result"]["fields"]["supplier"], "测试公司")
        self.assertEqual(result["authorization"], "auto_local")

    def test_ocr_text_task_fails_clearly_without_engine(self) -> None:
        image = Path(self.temp_dir.name) / "sample.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
        with patch("ocr._find_tesseract", return_value=None):
            result = self._run("ocr_text", {"image": str(image)})
        self.assertEqual(result["status"], "failed")
        self.assertIn("OCR 引擎", result["reason"])


if __name__ == "__main__":
    unittest.main()
