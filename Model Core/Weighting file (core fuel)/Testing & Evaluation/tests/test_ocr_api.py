"""OCR 前端透出：/v1/ocr/analyze HTTP 端点测试。

与图片分析同链：consent 授权、真实解码验证、10MB/40MP 上限；
识别走 ocr_text + extract_fields（本文件用 patch 保证确定性与速度，
真实引擎识别由 ocr_acceptance.py 真实验收覆盖）。
"""

import base64
import hashlib
import hmac
import io
import json
import os
import secrets
import tempfile
import unittest
from http.client import HTTPConnection
from threading import Thread
from unittest.mock import patch

from PIL import Image

from app import create_server

CAPABILITY = "a" * 64  # 64 hex 字符的 HMAC 密钥


def _consent_header() -> str:
    nonce = secrets.token_hex(16)  # 每次唯一，避免触发一次性消费机制
    timestamp = str(int(__import__("time").time() * 1000))
    key = bytes.fromhex(CAPABILITY)
    signature = hmac.new(
        key, f"{nonce}.{timestamp}".encode("ascii"), "sha256"
    ).hexdigest()
    return f"{nonce}.{timestamp}.{signature}"


def _png_bytes(width: int = 40, height: int = 40) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(buffer, format="PNG")
    return buffer.getvalue()


class OcrApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.environment = patch.dict(
            os.environ,
            {
                "MODEL_BACKEND": "placeholder",
                "MOLING_VISION_CAPABILITY": CAPABILITY,
                "MOLING_TOOL_CAPABILITY": CAPABILITY,
                "MOLING_LOG_DIR": os.path.join(self.temp_dir.name, "logs"),
                "CHARACTER_CARD_PATH": os.path.join(self.temp_dir.name, "character.json"),
                "CHARACTER_MEMORY_PATH": os.path.join(self.temp_dir.name, "memory.json"),
                "CHARACTER_ASSET_DIR": self.temp_dir.name,
                "CHARACTER_PRIVACY_PATH": os.path.join(self.temp_dir.name, "privacy.json"),
                "CHARACTER_AFFECT_PATH": os.path.join(self.temp_dir.name, "affect.json"),
                "AVATAR_REGISTRY_PATH": os.path.join(self.temp_dir.name, "avatars.json"),
                "AVATAR_AWAKEN_LOG_PATH": os.path.join(self.temp_dir.name, "awaken_log.json"),
                "AVATAR_TOOL_LOG_PATH": os.path.join(self.temp_dir.name, "tool_log.json"),
            },
        )
        self.environment.start()
        self.server = create_server()
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.connection = HTTPConnection("127.0.0.1", self.server.server_port)

    def tearDown(self) -> None:
        self.connection.close()
        self.server.shutdown()
        self.server.server_close()
        self.environment.stop()
        self.temp_dir.cleanup()

    def _post_ocr(self, payload: dict, consent: str | None) -> tuple[int, dict]:
        headers = {"Content-Type": "application/json"}
        if consent is not None:
            headers["X-Moling-Vision-Consent"] = consent
        self.connection.request("POST", "/v1/ocr/analyze", json.dumps(payload), headers)
        response = self.connection.getresponse()
        return response.status, json.loads(response.read())

    def test_requires_consent(self) -> None:
        status, body = self._post_ocr(
            {"image_base64": base64.b64encode(_png_bytes()).decode(), "content_type": "image/png"},
            consent=None,
        )
        self.assertEqual(status, 403)
        self.assertIn("授权", body["error"])

    def test_invalid_consent_signature_rejected(self) -> None:
        status, body = self._post_ocr(
            {"image_base64": "eA==", "content_type": "image/png"},
            consent="c" * 32 + ".1" + "." + "0" * 64,
        )
        self.assertEqual(status, 403)

    def test_rejects_unsupported_content_type(self) -> None:
        status, body = self._post_ocr(
            {"image_base64": "eA==", "content_type": "image/gif"},
            consent=_consent_header(),
        )
        self.assertEqual(status, 400)
        self.assertIn("PNG, JPEG, and WebP", body["error"])

    def test_rejects_invalid_base64(self) -> None:
        status, body = self._post_ocr(
            {"image_base64": "%%%not-base64%%%", "content_type": "image/png"},
            consent=_consent_header(),
        )
        self.assertEqual(status, 400)

    def test_rejects_signature_mismatch_content(self) -> None:
        # 声明 png 但内容不是 png（签名校验拦截）
        status, body = self._post_ocr(
            {"image_base64": base64.b64encode(b"not a png at all").decode(), "content_type": "image/png"},
            consent=_consent_header(),
        )
        self.assertEqual(status, 400)
        self.assertIn("do not match", body["error"])

    def test_ok_returns_text_and_fields(self) -> None:
        fake_ocr = {
            "engine": "tesseract",
            "text": "供应商：山间小筑\n金额：1,280.50\n发票号：INV-2026-00123",
            "chars": 28,
        }
        fake_fields = {
            "fields": {"supplier": "山间小筑", "amount": "1,280.50", "invoice_no": "INV-2026-00123"},
            "matched": ["amount", "invoice_no", "supplier"],
            "source_text_len": 28,
        }
        with (
            patch("api.ocr_text", return_value=fake_ocr),
            patch("api.extract_fields", return_value=fake_fields),
            patch("api.detect_ocr_engine", return_value={"available": True, "languages": ["eng", "chi_sim"]}),
        ):
            status, body = self._post_ocr(
                {"image_base64": base64.b64encode(_png_bytes()).decode(), "content_type": "image/png"},
                consent=_consent_header(),
            )
        self.assertEqual(status, 200)
        self.assertEqual(body["engine"], "tesseract")
        self.assertEqual(body["chars"], 28)
        self.assertEqual(body["fields"]["amount"], "1,280.50")
        self.assertIn("invoice_no", body["matched"])

    def test_consent_is_single_use(self) -> None:
        payload = {
            "image_base64": base64.b64encode(_png_bytes()).decode(),
            "content_type": "image/png",
        }
        consent = _consent_header()  # 固定一个 nonce，验证一次性消耗
        with (
            patch("api.ocr_text", return_value={"engine": "tesseract", "text": "x", "chars": 1}),
            patch("api.extract_fields", return_value={"fields": {}, "matched": [], "source_text_len": 1}),
            patch("api.detect_ocr_engine", return_value={"available": True, "languages": ["eng"]}),
        ):
            first, _ = self._post_ocr(payload, consent=consent)
            self.assertEqual(first, 200)
            second, body = self._post_ocr(payload, consent=consent)
            self.assertEqual(second, 403)  # 同一 nonce 二次使用被拒
            self.assertIn("授权", body["error"])

    def test_rejects_when_engine_missing(self) -> None:
        with patch("api.detect_ocr_engine", return_value={"available": False}):
            status, body = self._post_ocr(
                {"image_base64": base64.b64encode(_png_bytes()).decode(), "content_type": "image/png"},
                consent=_consent_header(),
            )
        self.assertEqual(status, 400)
        self.assertIn("Tesseract", body["error"])


if __name__ == "__main__":
    unittest.main()
