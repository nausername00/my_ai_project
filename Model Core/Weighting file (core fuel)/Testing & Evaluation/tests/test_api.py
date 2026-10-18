import base64
import hmac
import json
import os
import struct
import tempfile
import threading
import time
import unittest
import zlib
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread
from unittest.mock import patch

from agent_tools import _trace_store
from app import create_server
from character import CharacterCard
from computer_use import run_sandboxed_shell
from inference import ModelUnavailableError
from speech import SpeechInputError, SpeechService, SpeechUnavailableError


VISION_TEST_CAPABILITY = "ab" * 32


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + chunk_type
        + data
        + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
    )


def small_png(width: int = 2, height: int = 3) -> bytes:
    """返回一个真实可解码的 PNG；超大尺寸只构造头部（供头部检查先行拒绝）。"""
    header = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(
            b"IHDR",
            struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0),
        )
    )
    if width * height > 4096:
        # 仅头部：超大声明会被头部尺寸检查先拒绝，无需真实像素数据。
        return header
    raw = b"".join(
        b"\x00" + b"\xff\x00\x00" * width for _ in range(height)
    )
    return header + _png_chunk(b"IDAT", zlib.compress(raw)) + _png_chunk(b"IEND", b"")


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.environment = patch.dict(
            os.environ,
            {
                "MODEL_BACKEND": "placeholder",
                "CHARACTER_CARD_PATH": os.path.join(self.temp_dir.name, "character.json"),
                "CHARACTER_MEMORY_PATH": os.path.join(self.temp_dir.name, "memory.json"),
                "CHARACTER_ASSET_DIR": self.temp_dir.name,
                "CHARACTER_PRIVACY_PATH": os.path.join(self.temp_dir.name, "privacy.json"),
                "CHARACTER_AFFECT_PATH": os.path.join(self.temp_dir.name, "affect.json"),
                "MOLING_VISION_CAPABILITY": VISION_TEST_CAPABILITY,
            },
        )
        self.environment.start()
        self.server = create_server()
        self.server.RequestHandlerClass._notifications.clear()
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.connection = HTTPConnection("127.0.0.1", self.server.server_port)

    @staticmethod
    def vision_consent_header(
        nonce: str | None = None,
        timestamp_ms: int | None = None,
    ) -> dict[str, str]:
        nonce = nonce or os.urandom(16).hex()
        timestamp = str(timestamp_ms or int(time.time() * 1000))
        consent_payload = f"{nonce}.{timestamp}"
        signature = hmac.new(
            bytes.fromhex(VISION_TEST_CAPABILITY),
            consent_payload.encode("ascii"),
            "sha256",
        ).hexdigest()
        return {"X-Moling-Vision-Consent": f"{consent_payload}.{signature}"}

    def tearDown(self) -> None:
        self.connection.close()
        self.server.shutdown()
        self.server.server_close()
        self.environment.stop()
        self.temp_dir.cleanup()

    def test_health_endpoint(self) -> None:
        self.connection.request("GET", "/health")
        response = self.connection.getresponse()
        self.assertEqual(response.status, 200)
        payload = json.loads(response.read())
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["model"], "placeholder")

    def test_state_changing_routes_reject_cross_origin_browser_requests(self) -> None:
        requests = (
            ("POST", "/v1/backup/create", b"{}"),
            ("PUT", "/v1/memory/not-real", b"{}"),
            ("DELETE", "/v1/characters/not-real", b""),
        )
        for method, path, body in requests:
            with self.subTest(method=method, path=path):
                self.connection.request(
                    method,
                    path,
                    body,
                    {
                        "Content-Type": "text/plain",
                        "Origin": "https://attacker.example",
                    },
                )
                response = self.connection.getresponse()
                payload = json.loads(response.read())
                self.assertEqual(response.status, 403)
                self.assertIn("cross-origin", payload["error"])

    def test_mobile_capacitor_origin_is_allowed(self) -> None:
        # Capacitor 手机 App 的 WebView 请求携带 capacitor://localhost 来源，
        # 必须放行，否则真机 App 无法调用任何 POST API。
        for origin in ("capacitor://localhost", "https://localhost", "http://localhost"):
            with self.subTest(origin=origin):
                self.connection.request(
                    "POST",
                    "/v1/backup/create",
                    b"{}",
                    {"Content-Type": "text/plain", "Origin": origin},
                )
                response = self.connection.getresponse()
                # 放行后走到业务校验（backup/create 缺参数 → 400），而不是 403。
                self.assertNotEqual(response.status, 403)

    def test_cors_preflight_and_headers_for_trusted_origin(self) -> None:
        # 预检：受信来源必须返回 204 + 完整 CORS 头，否则 WebView fetch 直接抛
        # "Failed to fetch"（网络层拦截），App 永远连不上后端。
        self.connection.request(
            "OPTIONS",
            "/v1/generate",
            b"",
            {
                "Origin": "capacitor://localhost",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,authorization",
            },
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 204)
        self.assertEqual(
            response.getheader("Access-Control-Allow-Origin"),
            "capacitor://localhost",
        )
        self.assertIn(
            "POST",
            response.getheader("Access-Control-Allow-Methods", ""),
        )
        self.assertIn(
            "authorization",
            response.getheader("Access-Control-Allow-Headers", "").casefold(),
        )
        response.read()

        # 实际 POST 响应也必须携带回显头（同源跨域读取由 WebView 校验）。
        self.connection.request(
            "POST",
            "/v1/generate",
            json.dumps({"prompt": "hi", "history": []}).encode("utf-8"),
            {
                "Content-Type": "application/json",
                "Origin": "capacitor://localhost",
            },
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(
            response.getheader("Access-Control-Allow-Origin"),
            "capacitor://localhost",
        )
        response.read()

        # 非受信来源预检：不返回 CORS 头。
        self.connection.request(
            "OPTIONS",
            "/v1/generate",
            b"",
            {"Origin": "https://attacker.example"},
        )
        response = self.connection.getresponse()
        self.assertIsNone(response.getheader("Access-Control-Allow-Origin"))
        response.read()

    def test_same_origin_browser_request_is_allowed(self) -> None:
        # 手机浏览器直接打开 http://<电脑IP>:8000/v1/mobile/ 时，页面同源 POST
        # 携带 Origin: http://<电脑IP>:8000（与 Host 一致）→ 必须放行，否则远程
        # 加载的手机页/App 远程页都发不了消息。
        origin = "http://10.132.46.248:8000"
        self.connection.request(
            "POST",
            "/v1/generate",
            json.dumps({"prompt": "hi", "history": []}).encode("utf-8"),
            {
                "Content-Type": "application/json",
                "Host": "10.132.46.248:8000",
                "Origin": origin,
            },
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 200)
        response.read()

        # 跨站来源（Origin ≠ Host）依然 403。
        self.connection.request(
            "POST",
            "/v1/generate",
            json.dumps({"prompt": "hi", "history": []}).encode("utf-8"),
            {
                "Content-Type": "application/json",
                "Host": "10.132.46.248:8000",
                "Origin": "http://10.132.46.249:8000",
            },
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 403)
        response.read()

    def test_vision_analysis_rejects_invalid_image_formats(self) -> None:
        for content_type, image in (
            ("image/gif", b"GIF89a"),
            ("image/png", b"not a png"),
        ):
            with self.subTest(content_type=content_type):
                self.connection.request(
                    "POST",
                    "/v1/vision/analyze",
                    json.dumps(
                        {
                            "content_type": content_type,
                            "image_base64": base64.b64encode(image).decode("ascii"),
                        }
                    ),
                    {
                        "Content-Type": "application/json",
                        **self.vision_consent_header(),
                    },
                )
                response = self.connection.getresponse()
                result = json.loads(response.read())
                self.assertEqual(response.status, 400)
                self.assertIn("image", result["error"].lower())

    def test_vision_analysis_requires_fresh_signed_consent(self) -> None:
        image = small_png()
        body = json.dumps(
            {
                "content_type": "image/png",
                "image_base64": base64.b64encode(image).decode("ascii"),
            }
        )
        self.connection.request(
            "POST",
            "/v1/vision/analyze",
            body,
            {"Content-Type": "application/json"},
        )
        response = self.connection.getresponse()
        denied = json.loads(response.read())
        self.assertEqual(response.status, 403)
        self.assertIn("明确授权", denied["error"])

        expired = self.vision_consent_header(
            timestamp_ms=int(time.time() * 1000) - 180_000,
        )
        self.connection.request(
            "POST",
            "/v1/vision/analyze",
            body,
            {"Content-Type": "application/json", **expired},
        )
        expired_response = self.connection.getresponse()
        expired_result = json.loads(expired_response.read())
        self.assertEqual(expired_response.status, 403)
        self.assertIn("明确授权", expired_result["error"])

        replayable = self.vision_consent_header()
        self.connection.request(
            "POST",
            "/v1/vision/analyze",
            body,
            {"Content-Type": "application/json", **replayable},
        )
        accepted_response = self.connection.getresponse()
        accepted_response.read()
        self.assertEqual(accepted_response.status, 400)

        self.connection.request(
            "POST",
            "/v1/vision/analyze",
            body,
            {"Content-Type": "application/json", **replayable},
        )
        replay_response = self.connection.getresponse()
        replayed = json.loads(replay_response.read())
        self.assertEqual(replay_response.status, 403)
        self.assertIn("明确授权", replayed["error"])

    def test_vision_analysis_rejects_oversized_pixel_dimensions(self) -> None:
        image = small_png(width=16_000, height=16_000)
        self.connection.request(
            "POST",
            "/v1/vision/analyze",
            json.dumps(
                {
                    "content_type": "image/png",
                    "image_base64": base64.b64encode(image).decode("ascii"),
                }
            ),
            {
                "Content-Type": "application/json",
                **self.vision_consent_header(),
            },
        )
        response = self.connection.getresponse()
        result = json.loads(response.read())
        self.assertEqual(response.status, 400)
        self.assertIn("40 megapixel", result["error"])

    def test_vision_analysis_uses_local_model_and_does_not_persist_image(self) -> None:
        class LocalVisionEngine:
            model_name = "local-vision"

            class Backend:
                endpoint = "http://127.0.0.1:11434"

            backend = Backend()

        image = small_png()
        previous_engine = self.server.RequestHandlerClass.engine
        self.server.RequestHandlerClass.engine = LocalVisionEngine()
        try:
            with patch(
                "api.analyze_image",
                return_value={
                    "summary": "一张示例图片",
                    "observed": ["一个圆形"],
                    "possible_interpretations": [],
                    "uncertainty": "背景细节不清",
                },
            ) as analyze:
                self.connection.request(
                    "POST",
                    "/v1/vision/analyze",
                    json.dumps(
                        {
                            "content_type": "image/png",
                            "image_base64": base64.b64encode(image).decode("ascii"),
                        }
                    ),
                    {
                        "Content-Type": "application/json",
                        **self.vision_consent_header(),
                    },
                )
                response = self.connection.getresponse()
                result = json.loads(response.read())
        finally:
            self.server.RequestHandlerClass.engine = previous_engine

        self.assertEqual(response.status, 200)
        self.assertEqual(result["observed"], ["一个圆形"])
        analyze.assert_called_once()
        self.assertEqual(analyze.call_args.args[0], image)
        self.assertFalse(Path(os.environ["CHARACTER_MEMORY_PATH"]).exists())

    def test_vision_analysis_fails_clearly_without_supported_local_model(self) -> None:
        image = small_png()
        self.connection.request(
            "POST",
            "/v1/vision/analyze",
            json.dumps(
                {
                    "content_type": "image/png",
                    "image_base64": base64.b64encode(image).decode("ascii"),
                }
            ),
            {
                "Content-Type": "application/json",
                **self.vision_consent_header(),
            },
        )
        response = self.connection.getresponse()
        result = json.loads(response.read())

        self.assertEqual(response.status, 400)
        self.assertIn("配置本地视觉模型", result["error"])

    def test_vision_analysis_rejects_remote_model_endpoint(self) -> None:
        class RemoteVisionEngine:
            model_name = "remote-vision"

            class Backend:
                endpoint = "https://example.com/model"

            backend = Backend()

        image = small_png()
        previous_engine = self.server.RequestHandlerClass.engine
        self.server.RequestHandlerClass.engine = RemoteVisionEngine()
        try:
            with patch("api.analyze_image") as analyze:
                self.connection.request(
                    "POST",
                    "/v1/vision/analyze",
                    json.dumps(
                        {
                            "content_type": "image/png",
                            "image_base64": base64.b64encode(image).decode("ascii"),
                        }
                    ),
                    {
                        "Content-Type": "application/json",
                        **self.vision_consent_header(),
                    },
                )
                response = self.connection.getresponse()
                result = json.loads(response.read())
        finally:
            self.server.RequestHandlerClass.engine = previous_engine

        self.assertEqual(response.status, 400)
        self.assertIn("local model", result["error"])
        analyze.assert_not_called()

    def _run_vision_analyze(
        self,
        image: bytes,
        content_type: str = "image/png",
    ) -> tuple[int, dict]:
        self.connection.request(
            "POST",
            "/v1/vision/analyze",
            json.dumps(
                {
                    "content_type": content_type,
                    "image_base64": base64.b64encode(image).decode("ascii"),
                }
            ),
            {
                "Content-Type": "application/json",
                **self.vision_consent_header(),
            },
        )
        response = self.connection.getresponse()
        return response.status, json.loads(response.read())

    def test_vision_analysis_rejects_truncated_png_without_model_call(self) -> None:
        """J2：截断的有效 PNG 必须快速明确失败，且不调用模型、不持久化。"""
        good = small_png()
        truncated = good[: len(good) // 2]

        class LocalVisionEngine:
            model_name = "local-vision"

            class Backend:
                endpoint = "http://127.0.0.1:11434"

            backend = Backend()

        previous_engine = self.server.RequestHandlerClass.engine
        self.server.RequestHandlerClass.engine = LocalVisionEngine()
        try:
            with patch("api.analyze_image") as analyze:
                status, result = self._run_vision_analyze(truncated)
        finally:
            self.server.RequestHandlerClass.engine = previous_engine

        self.assertEqual(status, 400)
        self.assertIn("解码", result["error"])
        analyze.assert_not_called()
        self.assertFalse(Path(os.environ["CHARACTER_MEMORY_PATH"]).exists())

    def test_vision_analysis_rejects_forged_dimension_header(self) -> None:
        """J2：伪造 IHDR 尺寸头（声明 4000×4000、实际 1×1 数据）必须被解码验证拦截。"""
        forged = bytearray(small_png(width=1, height=1))
        # 定位 IHDR 宽度/高度字段（魔数 8 字节 + 长度 4 字节 + "IHDR" 4 字节后）
        forged[16:20] = struct.pack(">I", 4000)
        forged[20:24] = struct.pack(">I", 4000)
        status, result = self._run_vision_analyze(bytes(forged))
        self.assertEqual(status, 400)
        self.assertIn("解码", result["error"])
        self.assertFalse(Path(os.environ["CHARACTER_MEMORY_PATH"]).exists())

    def test_vision_analysis_rejects_garbage_masquerading_as_png(self) -> None:
        """J2：魔数合法但数据是随机垃圾的 PNG 必须被解码验证拦截。"""
        garbage = (
            b"\x89PNG\r\n\x1a\n"
            + _png_chunk(
                b"IHDR",
                struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0),
            )
            + _png_chunk(b"IDAT", b"\xff\xfe\xfd\xfc\xfb")
        )
        status, result = self._run_vision_analyze(garbage)
        self.assertEqual(status, 400)
        self.assertIn("解码", result["error"])
        self.assertFalse(Path(os.environ["CHARACTER_MEMORY_PATH"]).exists())

    def test_vision_analysis_accepts_a_complete_png(self) -> None:
        """J2：真实可解码的 PNG 应通过验证并进入模型。"""
        class LocalVisionEngine:
            model_name = "local-vision"

            class Backend:
                endpoint = "http://127.0.0.1:11434"

            backend = Backend()

        previous_engine = self.server.RequestHandlerClass.engine
        self.server.RequestHandlerClass.engine = LocalVisionEngine()
        try:
            with patch(
                "api.analyze_image",
                return_value={
                    "summary": "一张示例图片",
                    "observed": [],
                    "possible_interpretations": [],
                    "uncertainty": "",
                },
            ) as analyze:
                status, result = self._run_vision_analyze(small_png())
        finally:
            self.server.RequestHandlerClass.engine = previous_engine

        self.assertEqual(status, 200)
        analyze.assert_called_once()

    def test_decode_verify_classifies_bomb_and_corrupt_at_unit_level(self) -> None:
        """J2 单元级：解压炸弹/解码异常统一转成明确 ValueError；关闭开关时回退头部检查。"""
        handler_cls = self.server.RequestHandlerClass
        # 关闭解码验证（显式开关）时回退头部尺寸检查
        previous = handler_cls.IMAGE_DECODE_VERIFY
        handler_cls.IMAGE_DECODE_VERIFY = False
        try:
            width, height = handler_cls._decode_and_verify_image(
                handler_cls, small_png(), "image/png"
            )
        finally:
            handler_cls.IMAGE_DECODE_VERIFY = previous
        self.assertEqual((width, height), (2, 3))
        with patch(
            "PIL.Image.open",
            side_effect=OSError("image file is truncated"),
        ):
            with self.assertRaises(ValueError) as ctx:
                handler_cls._decode_and_verify_image(handler_cls, small_png(), "image/png")
            self.assertIn("无法完整解码", str(ctx.exception))
        bomb_error = type("BombError", (Exception,), {})
        with patch(
            "PIL.Image.open",
            side_effect=bomb_error("image decompression bomb error"),
        ):
            with self.assertRaises(ValueError) as ctx:
                handler_cls._decode_and_verify_image(
                    handler_cls, small_png(), "image/png"
                )
            self.assertIn("像素量超过安全上限", str(ctx.exception))

    def test_local_notification_post_and_get(self) -> None:
        self.connection.request(
            "POST",
            "/v1/notify",
            json.dumps(
                {
                    "id": "test-notification",
                    "title": "完成",
                    "message": "后台任务已经完成",
                    "level": "success",
                    "actions": [{"label": "查看"}],
                },
                ensure_ascii=False,
            ).encode("utf-8"),
            {"Content-Type": "application/json; charset=utf-8"},
        )
        response = self.connection.getresponse()
        created = json.loads(response.read())

        self.assertEqual(response.status, 201)
        self.assertEqual(created["notification"]["id"], "test-notification")
        self.assertEqual(created["notification"]["actions"], [{"label": "查看"}])

        self.connection.request("GET", "/v1/notify?limit=100")
        response = self.connection.getresponse()
        listed = json.loads(response.read())

        self.assertEqual(response.status, 200)
        self.assertEqual(listed["count"], 1)
        self.assertEqual(listed["notifications"][0]["message"], "后台任务已经完成")

    def test_notification_post_rejects_invalid_fields(self) -> None:
        for payload in (
            {"title": ""},
            {"level": "urgent"},
            {"actions": [{"label": "x" * 81}]},
            {"expires_at": float("inf")},
            {"expires_at": -(10**500)},
        ):
            with self.subTest(payload=payload):
                self.connection.request(
                    "POST",
                    "/v1/notify",
                    json.dumps(payload).encode("utf-8"),
                    {"Content-Type": "application/json"},
                )
                response = self.connection.getresponse()
                body = json.loads(response.read())

                self.assertEqual(response.status, 400)
                self.assertIn("error", body)

        self.assertEqual(len(self.server.RequestHandlerClass._notifications), 0)

    def test_collaboration_role_catalog_is_exposed(self) -> None:
        self.connection.request("GET", "/v1/agent/roles")
        response = self.connection.getresponse()
        payload = json.loads(response.read())

        self.assertEqual(response.status, 200)
        self.assertEqual(
            [role["key"] for role in payload["roles"]],
            ["architecture", "code", "ui", "testing"],
        )
        self.assertTrue(all(role["instruction"] for role in payload["roles"]))

    def test_social_status_and_partner_catalog_are_local_only(self) -> None:
        self.connection.request("GET", "/v1/social/status")
        status_response = self.connection.getresponse()
        status = json.loads(status_response.read())

        self.connection.request("GET", "/v1/social/partners")
        partners_response = self.connection.getresponse()
        partners = json.loads(partners_response.read())

        self.assertEqual(status_response.status, 200)
        self.assertEqual(status["scope"], "local")
        self.assertFalse(status["model_configured"])
        self.assertFalse(status["external_providers_enabled"])
        self.assertEqual(partners_response.status, 200)
        self.assertEqual(
            [partner["id"] for partner in partners["partners"]],
            ["architecture", "code", "ui", "testing"],
        )
        self.assertTrue(all(partner["source"] == "local" for partner in partners["partners"]))
        self.assertTrue(all(partner["external"] is False for partner in partners["partners"]))
        self.assertTrue(all(partner["instruction"] for partner in partners["partners"]))

    def test_speech_voices_endpoint_lists_local_catalog(self) -> None:
        self.connection.request("GET", "/v1/speech/voices")
        response = self.connection.getresponse()
        payload = json.loads(response.read())

        self.assertEqual(response.status, 200)
        self.assertIsInstance(payload["voices"], list)
        self.assertIn("default_voice", payload)
        for voice in payload["voices"]:
            self.assertIn("name", voice)
            self.assertIn("display", voice)
            self.assertIn("language", voice)
            self.assertIn("available", voice)
            self.assertIn("default", voice)

    def test_speech_endpoint_rejects_unknown_voice_without_synthesis(self) -> None:
        self.connection.request(
            "POST",
            "/v1/speech",
            json.dumps({"text": "你好", "voice": "voice_that_does_not_exist"}),
        )
        response = self.connection.getresponse()
        body = json.loads(response.read())

        self.assertEqual(response.status, 400)
        self.assertIn("not available", body["error"])

    def test_speech_endpoint_requires_text(self) -> None:
        self.connection.request("POST", "/v1/speech", json.dumps({"voice": "zh_CN-huayan-medium"}))
        response = self.connection.getresponse()
        body = json.loads(response.read())

        self.assertEqual(response.status, 400)
        self.assertIn("text", body["error"])

    def test_partner_preview_is_local_and_redacted(self) -> None:
        self.server.RequestHandlerClass.character_store.add_memory(
            "PRIVATE_PARTNER_REVIEW_MEMORY",
            "user",
            "model",
        )
        self.connection.request(
            "GET",
            "/v1/partners/preview?scope=all&partner_id=deepseek",
        )
        response = self.connection.getresponse()
        preview = json.loads(response.read())

        self.assertEqual(response.status, 200)
        self.assertEqual([item["id"] for item in preview["partners"]], ["deepseek"])
        self.assertIn("公开评审摘要", preview["partners"][0]["prompt"])
        self.assertNotIn("PRIVATE_PARTNER_REVIEW_MEMORY", preview["partners"][0]["prompt"])

    def test_partner_evaluation_rejects_external_call_without_explicit_consent(self) -> None:
        self.connection.request(
            "POST",
            "/v1/partners/evaluate",
            json.dumps(
                {
                    "scope": "all",
                    "external_partner_ids": ["deepseek"],
                }
            ).encode("utf-8"),
            {"Content-Type": "application/json"},
        )
        response = self.connection.getresponse()
        result = json.loads(response.read())

        self.assertEqual(response.status, 400)
        self.assertIn("明确确认授权", result["error"])

    def test_social_collaboration_runs_selected_local_partners(self) -> None:
        class SocialEngine:
            model_name = "local-social-test"

            class Backend:
                endpoint = "http://127.0.0.1:11434"

            backend = Backend()

            def __init__(self) -> None:
                self.requests = []

            def generate(self, request):
                self.requests.append(request)
                if len(self.requests) == 1:
                    return "先为模块边界补充验收测试。"
                return json.dumps(
                    {
                        "consensus": ["先补验收测试。"],
                        "prioritized": ["明确模块边界"],
                        "conflicts": [],
                        "next_steps": ["运行针对性测试"],
                    },
                    ensure_ascii=False,
                )

        handler = self.server.RequestHandlerClass
        previous_engine = handler.engine
        engine = SocialEngine()
        handler.engine = engine
        try:
            self.connection.request(
                "POST",
                "/v1/social/collaborate",
                json.dumps(
                    {
                        "task": "检查模块边界和测试",
                        "partner_ids": ["code"],
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
                {"Content-Type": "application/json; charset=utf-8"},
            )
            response = self.connection.getresponse()
            result = json.loads(response.read())
        finally:
            handler.engine = previous_engine

        self.assertEqual(response.status, 200)
        self.assertEqual(result["scope"], "local")
        self.assertEqual(result["partner_ids"], ["code"])
        self.assertEqual(result["external_providers_used"], [])
        self.assertEqual([item["agent"] for item in result["collaborators"]], ["code"])
        self.assertEqual(result["synthesis"]["next_steps"], ["运行针对性测试"])
        self.assertEqual(len(engine.requests), 2)

    def test_social_collaboration_preserves_role_prompts(self) -> None:
        class SocialEngine:
            model_name = "local-social-test"

            class Backend:
                endpoint = "http://127.0.0.1:11434"

            backend = Backend()

            def __init__(self) -> None:
                self.requests = []

            def generate(self, request):
                self.requests.append(request)
                if len(self.requests) == 1:
                    return "建议给新流程添加回归测试。"
                return json.dumps(
                    {
                        "consensus": ["添加回归测试"],
                        "prioritized": [],
                        "conflicts": [],
                        "next_steps": [],
                    },
                    ensure_ascii=False,
                )

        handler = self.server.RequestHandlerClass
        previous_engine = handler.engine
        engine = SocialEngine()
        handler.engine = engine
        try:
            self.connection.request(
                "POST",
                "/v1/social/collaborate",
                json.dumps(
                    {
                        "task": "评审协作工作区",
                        "roles": [
                            {
                                "key": "testing",
                                "enabled": True,
                                "instruction": "重点验证用户保存的本机提示词",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
                {"Content-Type": "application/json; charset=utf-8"},
            )
            response = self.connection.getresponse()
            result = json.loads(response.read())
        finally:
            handler.engine = previous_engine

        self.assertEqual(response.status, 200)
        self.assertEqual(result["partner_ids"], ["testing"])
        self.assertIn("重点验证用户保存的本机提示词", engine.requests[0].prompt)

    def test_social_collaboration_rejects_unknown_or_duplicate_partners(self) -> None:
        class SocialEngine:
            model_name = "local-social-test"

            class Backend:
                endpoint = "http://127.0.0.1:11434"

            backend = Backend()

        handler = self.server.RequestHandlerClass
        previous_engine = handler.engine
        handler.engine = SocialEngine()
        try:
            invalid_payloads = (
                {"task": "核验本地伙伴", "partner_ids": []},
                {"task": "核验本地伙伴", "partner_ids": ["unknown"]},
                {"task": "核验本地伙伴", "partner_ids": ["code", "code"]},
                {"task": "核验本地伙伴", "partner_ids": [{"id": "code"}]},
                {"task": "核验本地伙伴", "partner_ids": ["code"], "extra": True},
                {
                    "task": "核验本地伙伴",
                    "partner_ids": ["code"],
                    "roles": [{"key": "code", "enabled": True, "instruction": ""}],
                },
                {
                    "task": "核验本地伙伴",
                    "roles": [{"key": "unknown", "enabled": True, "instruction": ""}],
                },
                {"task": ""},
                {"task": "x" * 4001},
            )
            for payload in invalid_payloads:
                with self.subTest(payload=payload):
                    self.connection.request(
                        "POST",
                        "/v1/social/collaborate",
                        json.dumps(payload),
                        {"Content-Type": "application/json"},
                    )
                    response = self.connection.getresponse()
                    result = json.loads(response.read())

                    self.assertEqual(response.status, 400)
                    self.assertIn("error", result)
        finally:
            handler.engine = previous_engine

    def test_social_api_blocks_external_model_endpoints(self) -> None:
        class ExternalConfiguredEngine:
            model_name = "configured-test-model"
            generate_calls = 0

            class Backend:
                endpoint = "https://models.example.test"

            backend = Backend()

            def generate(self, request):
                self.generate_calls += 1
                raise AssertionError("social API must never call an external model")

        handler = self.server.RequestHandlerClass
        previous_engine = handler.engine
        engine = ExternalConfiguredEngine()
        handler.engine = engine
        try:
            self.connection.request("GET", "/v1/social/status")
            status_response = self.connection.getresponse()
            status = json.loads(status_response.read())

            self.connection.request("GET", "/v1/social/partners")
            partners_response = self.connection.getresponse()
            partners = json.loads(partners_response.read())

            self.connection.request(
                "POST",
                "/v1/social/collaborate",
                json.dumps({"task": "检查本地协作"}).encode("utf-8"),
                {"Content-Type": "application/json"},
            )
            collaborate_response = self.connection.getresponse()
            failure = json.loads(collaborate_response.read())
        finally:
            handler.engine = previous_engine

        self.assertEqual(status_response.status, 200)
        self.assertFalse(status["model_configured"])
        self.assertEqual(status["model_status"], "external_model_blocked")
        self.assertTrue(
            all(
                partner["status"] == "external_model_blocked"
                for partner in partners["partners"]
            )
        )
        self.assertEqual(collaborate_response.status, 400)
        self.assertIn("本机", failure["error"])
        self.assertEqual(engine.generate_calls, 0)

    def test_local_collaboration_queries_specialists_and_moling_synthesizes(self) -> None:
        class LocalCollaborationEngine:
            model_name = "local-test"

            class Backend:
                endpoint = "http://127.0.0.1:11434"

            backend = Backend()

            def __init__(self) -> None:
                self.requests = []

            def generate(self, request):
                self.requests.append(request)
                if len(self.requests) == 5:
                    return json.dumps(
                        {
                            "consensus": ["先明确模块边界。"],
                            "prioritized": ["先补齐验收测试", "先补齐验收测试 "],
                            "conflicts": [],
                            "next_steps": ["补充验收测试。"],
                        },
                        ensure_ascii=False,
                    )
                return f"伙伴建议 {len(self.requests)}"

        previous_engine = self.server.RequestHandlerClass.engine
        engine = LocalCollaborationEngine()
        self.server.RequestHandlerClass.engine = engine
        try:
            self.connection.request(
                "POST",
                "/v1/agent/collaborate",
                json.dumps(
                    {"task": "检查翻译器的布局、代码和测试如何完善"},
                    ensure_ascii=False,
                ).encode("utf-8"),
                {"Content-Type": "application/json; charset=utf-8"},
            )
            response = self.connection.getresponse()
            result = json.loads(response.read())
        finally:
            self.server.RequestHandlerClass.engine = previous_engine

        self.assertEqual(response.status, 200)
        self.assertEqual(result["lead"], "moling")
        self.assertEqual(len(result["collaborators"]), 4)
        self.assertEqual(len(engine.requests), 5)
        self.assertEqual(result["synthesis"]["consensus"], ["先明确模块边界。"])
        self.assertEqual(
            result["synthesis"]["prioritized"],
            ["先补齐验收测试"],
        )
        self.assertEqual(result["collaborators"][0]["status"], "completed")
        self.assertEqual(result["collaborators"][0]["model"], "local-test")
        self.assertEqual(result["collaborators"][0]["source"], "local")
        self.assertEqual(
            [item["agent"] for item in result["collaborators"]],
            ["architecture", "code", "ui", "testing"],
        )

    def test_collaboration_runs_only_enabled_roles_with_custom_prompt(self) -> None:
        class SingleRoleEngine:
            model_name = "local-test"

            class Backend:
                endpoint = "http://127.0.0.1:11434"

            backend = Backend()

            def __init__(self) -> None:
                self.requests = []

            def generate(self, request):
                self.requests.append(request)
                if len(self.requests) == 1:
                    return "安全建议"
                return json.dumps(
                    {
                        "consensus": ["按安全建议处理"],
                        "prioritized": ["先做安全检查"],
                        "conflicts": [],
                        "next_steps": ["添加测试"],
                    },
                    ensure_ascii=False,
                )

        previous_engine = self.server.RequestHandlerClass.engine
        engine = SingleRoleEngine()
        self.server.RequestHandlerClass.engine = engine
        try:
            self.connection.request(
                "POST",
                "/v1/agent/collaborate",
                json.dumps(
                    {
                        "task": "评审登录模块",
                        "roles": [
                            {
                                "key": "architecture",
                                "enabled": False,
                                "instruction": "检查架构",
                            },
                            {
                                "key": "code",
                                "enabled": True,
                                "instruction": "重点检查安全与输入校验",
                            },
                        ],
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
                {"Content-Type": "application/json; charset=utf-8"},
            )
            response = self.connection.getresponse()
            result = json.loads(response.read())
        finally:
            self.server.RequestHandlerClass.engine = previous_engine

        self.assertEqual(response.status, 200)
        self.assertEqual(len(engine.requests), 2)
        self.assertIn("重点检查安全与输入校验", engine.requests[0].prompt)
        self.assertEqual([item["agent"] for item in result["collaborators"]], ["code"])

    def test_collaboration_keeps_other_roles_when_one_model_call_fails(self) -> None:
        class PartialFailureEngine:
            model_name = "local-test"

            class Backend:
                endpoint = "http://127.0.0.1:11434"

            backend = Backend()

            def __init__(self) -> None:
                self.calls = 0

            def generate(self, request):
                self.calls += 1
                if self.calls == 2:
                    raise ModelUnavailableError("本次推理超时")
                if self.calls == 5:
                    return json.dumps(
                        {
                            "consensus": ["保留已完成角色的意见"],
                            "prioritized": ["复核失败角色"],
                            "conflicts": [],
                            "next_steps": ["重试失败角色"],
                        },
                        ensure_ascii=False,
                    )
                return f"角色意见 {self.calls}"

        previous_engine = self.server.RequestHandlerClass.engine
        engine = PartialFailureEngine()
        self.server.RequestHandlerClass.engine = engine
        try:
            self.connection.request(
                "POST",
                "/v1/agent/collaborate",
                json.dumps({"task": "评审登录模块"}, ensure_ascii=False).encode("utf-8"),
                {"Content-Type": "application/json; charset=utf-8"},
            )
            response = self.connection.getresponse()
            result = json.loads(response.read())
        finally:
            self.server.RequestHandlerClass.engine = previous_engine

        self.assertEqual(response.status, 200)
        self.assertEqual(result["collaborators"][1]["status"], "failed")
        self.assertEqual(result["collaborators"][1]["error"], "本次推理超时")
        self.assertEqual(result["synthesis"]["consensus"], ["保留已完成角色的意见"])

    def test_collaboration_rejects_disabling_every_role(self) -> None:
        class LocalEngine:
            model_name = "local-test"

            class Backend:
                endpoint = "http://127.0.0.1:11434"

            backend = Backend()

            def generate(self, request):
                raise AssertionError("no model request should run without enabled roles")

        previous_engine = self.server.RequestHandlerClass.engine
        self.server.RequestHandlerClass.engine = LocalEngine()
        try:
            self.connection.request(
                "POST",
                "/v1/agent/collaborate",
                json.dumps(
                    {
                        "task": "评审登录模块",
                        "roles": [
                            {"key": key, "enabled": False, "instruction": ""}
                            for key in ("architecture", "code", "ui", "testing")
                        ],
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
                {"Content-Type": "application/json; charset=utf-8"},
            )
            response = self.connection.getresponse()
            result = json.loads(response.read())
        finally:
            self.server.RequestHandlerClass.engine = previous_engine

        self.assertEqual(response.status, 400)
        self.assertIn("at least one collaborator role", result["error"])

    def test_collaboration_surfaces_invalid_synthesis_without_losing_opinions(self) -> None:
        class InvalidSynthesisEngine:
            model_name = "local-test"

            class Backend:
                endpoint = "http://127.0.0.1:11434"

            backend = Backend()

            def __init__(self) -> None:
                self.calls = 0

            def generate(self, request):
                self.calls += 1
                return "not-json" if self.calls == 5 else f"角色意见 {self.calls}"

        previous_engine = self.server.RequestHandlerClass.engine
        self.server.RequestHandlerClass.engine = InvalidSynthesisEngine()
        try:
            self.connection.request(
                "POST",
                "/v1/agent/collaborate",
                json.dumps({"task": "评审登录模块"}, ensure_ascii=False).encode("utf-8"),
                {"Content-Type": "application/json; charset=utf-8"},
            )
            response = self.connection.getresponse()
            result = json.loads(response.read())
        finally:
            self.server.RequestHandlerClass.engine = previous_engine

        self.assertEqual(response.status, 200)
        self.assertEqual(len(result["collaborators"]), 4)
        self.assertIsNone(result["synthesis"])
        self.assertIn("不是有效 JSON", result["synthesis_error"])

    def test_collaboration_retries_invalid_synthesis_once(self) -> None:
        class RepairableSynthesisEngine:
            model_name = "local-test"

            class Backend:
                endpoint = "http://127.0.0.1:11434"

            backend = Backend()

            def __init__(self) -> None:
                self.requests = []

            def generate(self, request):
                self.requests.append(request)
                if len(self.requests) == 5:
                    return '{"consensus":"not-an-array"}'
                if len(self.requests) == 6:
                    return json.dumps(
                        {
                            "consensus": ["保留可验证结论"],
                            "prioritized": ["先修复综合结构"],
                            "conflicts": [],
                            "next_steps": ["复核综合输出"],
                        },
                        ensure_ascii=False,
                    )
                return f"角色意见 {len(self.requests)}"

        previous_engine = self.server.RequestHandlerClass.engine
        engine = RepairableSynthesisEngine()
        self.server.RequestHandlerClass.engine = engine
        try:
            self.connection.request(
                "POST",
                "/v1/agent/collaborate",
                json.dumps({"task": "评审登录模块"}, ensure_ascii=False).encode("utf-8"),
                {"Content-Type": "application/json; charset=utf-8"},
            )
            response = self.connection.getresponse()
            result = json.loads(response.read())
        finally:
            self.server.RequestHandlerClass.engine = previous_engine

        self.assertEqual(response.status, 200)
        self.assertEqual(len(engine.requests), 6)
        self.assertIn("上一次综合结果未通过结构校验", engine.requests[5].prompt)
        self.assertEqual(result["synthesis"]["consensus"], ["保留可验证结论"])
        self.assertEqual(result["synthesis_error"], "")
        self.assertEqual(len(result["collaborators"]), 4)

    def test_brain_plan_endpoint_returns_validated_plan(self) -> None:
        class PlanningEngine:
            model_name = "local-test"

            class Backend:
                endpoint = "http://127.0.0.1:11434"

            backend = Backend()

            def generate(self, request):
                return (
                    '{"intent":"learn","summary":"拆分学习任务",'
                    '"steps":[{"title":"查看现状","action":"整理当前模块",'
                    '"risk":"local_reversible","tool":"list_project_files",'
                    '"arguments":{"path":"."},"success_criteria":"返回项目清单"},'
                    '{"title":"联网搜索","action":"先请求许可",'
                    '"risk":"requires_permission","tool":null,"arguments":{},'
                    '"success_criteria":"得到许可"}],"memory_candidates":["学习项目架构"],'
                    '"reflection_question":"什么测试能证明进展？"}'
                )

        previous_engine = self.server.RequestHandlerClass.engine
        self.server.RequestHandlerClass.engine = PlanningEngine()
        try:
            self.connection.request(
                "POST",
                "/v1/agent/plan",
                json.dumps({"task": "一起完善大脑"}, ensure_ascii=False).encode("utf-8"),
                {"Content-Type": "application/json; charset=utf-8"},
            )
            response = self.connection.getresponse()
            result = json.loads(response.read())
        finally:
            self.server.RequestHandlerClass.engine = previous_engine

        self.assertEqual(response.status, 200)
        self.assertEqual(result["plan"]["intent"], "learn")
        self.assertEqual(result["plan"]["steps"][1]["risk"], "requires_permission")
        self.assertEqual(result["model"], "local-test")

    def test_agent_tools_endpoint_exposes_only_enabled_plan_tools(self) -> None:
        self.connection.request("GET", "/v1/agent/tools")
        response = self.connection.getresponse()
        result = json.loads(response.read())

        self.assertEqual(response.status, 200)
        self.assertEqual(
            {tool["name"] for tool in result["tools"]},
            {"list_project_files", "read_project_file", "create_project_file"},
        )
        by_name = {tool["name"]: tool for tool in result["tools"]}
        self.assertEqual(by_name["list_project_files"]["risk"], "read_only")
        self.assertEqual(by_name["read_project_file"]["risk"], "read_only")
        self.assertTrue(by_name["create_project_file"]["requires_approval"])

    def test_tool_execution_requires_desktop_approval_capability(self) -> None:
        handler = self.server.RequestHandlerClass
        previous_root = handler.workspace_root
        previous_capability = handler.tool_capability
        handler.workspace_root = Path(self.temp_dir.name)
        handler.tool_capability = "test-capability"
        (handler.workspace_root / "readme.md").write_text("safe text", encoding="utf-8")
        try:
            self.connection.request(
                "POST",
                "/v1/agent/tool/execute",
                json.dumps(
                    {"tool": "read_project_file", "arguments": {"path": "readme.md"}}
                ),
                {"Content-Type": "application/json"},
            )
            denied = self.connection.getresponse()
            denied.read()
            self.assertEqual(denied.status, 403)

            self.connection.request(
                "POST",
                "/v1/agent/tool/execute",
                json.dumps(
                    {"tool": "read_project_file", "arguments": {"path": "readme.md"}}
                ),
                {
                    "Content-Type": "application/json",
                    "X-Moling-Tool-Capability": "test-capability",
                },
            )
            allowed = self.connection.getresponse()
            result = json.loads(allowed.read())
        finally:
            handler.workspace_root = previous_root
            handler.tool_capability = previous_capability

        self.assertEqual(allowed.status, 200)
        self.assertEqual(result["observation"]["content"], "safe text")

    def test_tool_execution_creates_only_after_desktop_approval_capability(self) -> None:
        handler = self.server.RequestHandlerClass
        previous_root = handler.workspace_root
        previous_capability = handler.tool_capability
        handler.workspace_root = Path(self.temp_dir.name)
        handler.tool_capability = "test-capability"
        try:
            self.connection.request(
                "POST",
                "/v1/agent/tool/execute",
                json.dumps(
                    {
                        "tool": "create_project_file",
                        "arguments": {
                            "path": "approved.md",
                            "content": "用户批准的本地成果",
                        },
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
                {
                    "Content-Type": "application/json; charset=utf-8",
                    "X-Moling-Tool-Capability": "test-capability",
                },
            )
            response = self.connection.getresponse()
            result = json.loads(response.read())
        finally:
            handler.workspace_root = previous_root
            handler.tool_capability = previous_capability

        self.assertEqual(response.status, 200)
        self.assertTrue(result["observation"]["created"])
        self.assertEqual(result["observation"]["verification"]["status"], "confirmed")
        self.assertEqual(
            (Path(self.temp_dir.name) / "approved.md").read_text(encoding="utf-8"),
            "用户批准的本地成果",
        )

    def test_tool_verification_uses_model_assessment_schema(self) -> None:
        class VerificationEngine:
            model_name = "local-test"

            class Backend:
                endpoint = "http://127.0.0.1:11434"

            backend = Backend()

            def generate(self, request):
                self.request = request
                return '{"status":"uncertain","evidence":"结果只覆盖了返回清单"}'

        handler = self.server.RequestHandlerClass
        previous_engine = handler.engine
        engine = VerificationEngine()
        handler.engine = engine
        try:
            self.connection.request(
                "POST",
                "/v1/agent/tool/verify",
                json.dumps(
                    {
                        "task": "查看项目",
                        "success_criteria": "清单包含代码目录",
                        "observation": {"entries": [{"path": "src", "kind": "directory"}]},
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
                {"Content-Type": "application/json; charset=utf-8"},
            )
            response = self.connection.getresponse()
            result = json.loads(response.read())
        finally:
            handler.engine = previous_engine

        self.assertEqual(response.status, 200)
        self.assertEqual(result["verification"]["status"], "uncertain")
        self.assertIn("不可信数据", engine.request.prompt)

    def test_collaboration_rejects_placeholder_model_and_oversized_tasks(self) -> None:
        for task in ("", "x" * 4001):
            self.connection.request(
                "POST",
                "/v1/agent/collaborate",
                json.dumps({"task": task}).encode("utf-8"),
                {"Content-Type": "application/json"},
            )
            response = self.connection.getresponse()
            response.read()
            self.assertEqual(response.status, 400)

    def test_character_card_endpoints_create_list_and_select(self) -> None:
        body = json.dumps(
            {
                "category": "学习伙伴",
                "formal_name": "小老师",
                "nickname": "老师",
                "english_name": "Tutor",
                "language": "zh-CN",
                "gender": "未设定",
                "self_reference": "我",
                "core_traits": ["耐心"],
                "behavior_traits": ["循序渐进"],
                "signature_lines": [],
                "emotions": ["平静"],
                "avatar": None,
                "voice": None,
            },
            ensure_ascii=False,
        )
        self.connection.request(
            "POST",
            "/v1/characters",
            body.encode("utf-8"),
            {"Content-Type": "application/json; charset=utf-8"},
        )
        created_response = self.connection.getresponse()
        created = json.loads(created_response.read())
        self.assertEqual(created_response.status, 201)

        self.connection.request("GET", "/v1/characters")
        list_response = self.connection.getresponse()
        listing = json.loads(list_response.read())
        self.assertEqual(list_response.status, 200)
        self.assertEqual(listing["active_id"], "character")
        self.assertEqual(
            {entry["id"] for entry in listing["characters"]},
            {"character", created["id"]},
        )

        created_card = next(
            entry["character"]
            for entry in listing["characters"]
            if entry["id"] == created["id"]
        )
        created_card["nickname"] = "修改后的老师"
        created_card["id"] = created["id"]
        self.connection.request(
            "POST",
            "/v1/character",
            json.dumps(created_card, ensure_ascii=False).encode("utf-8"),
            {"Content-Type": "application/json; charset=utf-8"},
        )
        update_response = self.connection.getresponse()
        updated = json.loads(update_response.read())
        self.assertEqual(update_response.status, 200)
        self.assertEqual(updated["id"], created["id"])
        self.assertEqual(
            self.server.RequestHandlerClass.character_store.get_active_character_id(),
            "character",
        )

        self.connection.request(
            "POST",
            "/v1/characters/active",
            json.dumps({"id": "character"}),
            {"Content-Type": "application/json"},
        )
        selected_response = self.connection.getresponse()
        selected = json.loads(selected_response.read())
        self.assertEqual(selected_response.status, 200)
        self.assertEqual(selected["id"], "character")
        self.assertEqual(selected["character"]["nickname"], "墨灵")

    def test_new_character_can_be_edited_immediately_without_becoming_active(self) -> None:
        self.connection.request(
            "POST",
            "/v1/characters",
            json.dumps(
                {"nickname": "翻译伙伴", "formal_name": "翻译伙伴"},
                ensure_ascii=False,
            ).encode("utf-8"),
            {"Content-Type": "application/json; charset=utf-8"},
        )
        create_response = self.connection.getresponse()
        created = json.loads(create_response.read())
        self.assertEqual(create_response.status, 201)

        edited_card = {
            **created["character"],
            "id": created["id"],
            "nickname": "墨灵的翻译伙伴",
            "inner_drives": ["协助墨灵一起制作翻译器"],
            "personality_preset": "curious",
            "habits": ["验证翻译结果"],
            "likes": ["共同学习语言"],
            "dislikes": ["不说明不确定性"],
        }
        self.connection.request(
            "POST",
            "/v1/character",
            json.dumps(edited_card, ensure_ascii=False).encode("utf-8"),
            {"Content-Type": "application/json; charset=utf-8"},
        )
        edit_response = self.connection.getresponse()
        edited = json.loads(edit_response.read())

        self.assertEqual(edit_response.status, 200)
        self.assertEqual(edited["id"], created["id"])
        self.assertEqual(edited["character"]["nickname"], "墨灵的翻译伙伴")
        self.assertEqual(
            edited["character"]["inner_drives"],
            ["协助墨灵一起制作翻译器"],
        )
        self.assertEqual(edited["character"]["personality_preset"], "curious")
        self.assertEqual(edited["character"]["habits"], ["验证翻译结果"])
        self.assertEqual(edited["character"]["likes"], ["共同学习语言"])
        self.assertEqual(edited["character"]["dislikes"], ["不说明不确定性"])
        self.assertEqual(
            self.server.RequestHandlerClass.character_store.get_active_character_id(),
            "character",
        )

        self.connection.request("GET", "/v1/characters")
        list_response = self.connection.getresponse()
        listing = json.loads(list_response.read())
        persisted = next(
            item for item in listing["characters"] if item["id"] == created["id"]
        )
        self.assertEqual(persisted["character"]["nickname"], "墨灵的翻译伙伴")
        self.assertEqual(listing["active_id"], "character")

    def test_character_selection_rejects_unknown_id(self) -> None:
        self.connection.request(
            "POST",
            "/v1/characters/active",
            json.dumps({"id": "missing"}),
            {"Content-Type": "application/json"},
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 400)

    def test_character_selection_rejects_non_object_payload(self) -> None:
        self.connection.request(
            "POST",
            "/v1/characters/active",
            json.dumps(["character"]),
            {"Content-Type": "application/json"},
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 400)

    def test_character_delete_removes_non_active_card(self) -> None:
        self.connection.request(
            "POST",
            "/v1/characters",
            json.dumps(
                {
                    "category": "自建角色",
                    "formal_name": "待删除角色",
                    "nickname": "待删除",
                    "english_name": "ToDelete",
                }
            ),
            {"Content-Type": "application/json"},
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 201)
        created = json.loads(response.read().decode("utf-8"))
        self.connection.request("DELETE", f"/v1/characters/{created['id']}")
        response = self.connection.getresponse()
        self.assertEqual(response.status, 200)
        deleted = json.loads(response.read().decode("utf-8"))
        self.assertEqual(deleted["deleted"], True)
        self.connection.request("GET", "/v1/characters")
        response = self.connection.getresponse()
        self.assertEqual(response.status, 200)
        listing = json.loads(response.read().decode("utf-8"))
        self.assertNotIn(created["id"], {entry["id"] for entry in listing["characters"]})

    def test_character_delete_rejects_active_card(self) -> None:
        active_id = self.server.RequestHandlerClass.character_store.get_active_character_id()
        self.connection.request("DELETE", f"/v1/characters/{active_id}")
        response = self.connection.getresponse()
        self.assertEqual(response.status, 400)
        body = json.loads(response.read().decode("utf-8"))
        self.assertIn("active character", body["error"])

    def test_character_delete_returns_not_found_for_unknown_card(self) -> None:
        self.connection.request("DELETE", "/v1/characters/does-not-exist")
        response = self.connection.getresponse()
        self.assertEqual(response.status, 404)

    def test_emotion_avatars_round_trip_and_validation(self) -> None:
        store = self.server.RequestHandlerClass.character_store
        active_id = store.get_active_character_id()
        store.load_card(active_id)
        card = CharacterCard.from_dict(
            json.loads(
                (store._card_path_for_id(active_id)).read_text(encoding="utf-8")
            )
        )
        card.emotion_avatars = {"happy": "emotion-happy.png"}
        store.save_card(card, active_id)
        loaded = CharacterCard.from_dict(
            json.loads(
                (store._card_path_for_id(active_id)).read_text(encoding="utf-8")
            )
        )
        self.assertEqual(loaded.emotion_avatars, {"happy": "emotion-happy.png"})
        card.emotion_avatars = {"not-a-mood": "x.png"}
        with self.assertRaises(Exception):
            store.save_card(card, active_id)
        card.emotion_avatars = {"happy": "../evil.png"}
        with self.assertRaises(Exception):
            store.save_card(card, active_id)

    def test_character_validation_rejects_bad_avatar_and_oversized_lists(self) -> None:
        store = self.server.RequestHandlerClass.character_store
        active_id = store.get_active_character_id()
        store.load_card(active_id)
        card = CharacterCard.from_dict(
            json.loads(
                (store._card_path_for_id(active_id)).read_text(encoding="utf-8")
            )
        )
        card.avatar = "path/avatar.png"
        with self.assertRaises(Exception):
            store.save_card(card, active_id)
        card.avatar = None
        card.actions = ["x" * 161]
        with self.assertRaises(Exception):
            store.save_card(card, active_id)
        card.actions = []
        card.expressions = ["ok"] * 201
        with self.assertRaises(Exception):
            store.save_card(card, active_id)

    def test_agent_reflection_can_create_and_persist_its_own_goal(self) -> None:
        class ReflectingEngine:
            model_name = "local-test"

            def generate(self, request: object) -> str:
                self.request = request
                return json.dumps(
                    {
                        "goal": {
                            "domain": "学习语言",
                            "title": "一起读懂星空",
                            "description": "逐步认识常见星座",
                            "progress": "刚刚形成这个兴趣",
                            "status": "planned",
                        },
                        "updates": [],
                        "reflection": "最近聊到夜空，我想继续了解它。",
                    },
                    ensure_ascii=False,
                )

        handler = self.server.RequestHandlerClass
        previous_engine = handler.engine
        engine = ReflectingEngine()
        handler.engine = engine
        try:
            self.connection.request(
                "POST",
                "/v1/agent/reflect",
                json.dumps(
                    {
                        "character_id": "character",
                        "history": [
                            {"role": "user", "content": "昨晚看到很多星星"},
                            {"role": "assistant", "content": "我们可以一起辨认星座。"},
                        ],
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
                {"Content-Type": "application/json; charset=utf-8"},
            )
            response = self.connection.getresponse()
            result = json.loads(response.read())
        finally:
            handler.engine = previous_engine

        self.assertEqual(response.status, 200)
        self.assertTrue(result["updated"])
        self.assertEqual(result["goals"][0]["title"], "一起读懂星空")
        self.assertEqual(handler.character_store.load_card().agent_goals[0]["status"], "planned")
        self.assertIn("绝不访问文件、屏幕、网络", engine.request.system_prompt)

    def test_invalid_agent_reflection_is_reported_and_not_saved(self) -> None:
        class InvalidReflectingEngine:
            model_name = "local-test"

            def generate(self, request: object) -> str:
                return "not JSON"

        handler = self.server.RequestHandlerClass
        previous_engine = handler.engine
        handler.engine = InvalidReflectingEngine()
        try:
            self.connection.request(
                "POST",
                "/v1/agent/reflect",
                json.dumps(
                    {
                        "character_id": "character",
                        "history": [
                            {"role": "user", "content": "I like learning"},
                            {"role": "assistant", "content": "Let's learn together."},
                        ],
                    }
                ),
                {"Content-Type": "application/json"},
            )
            response = self.connection.getresponse()
            payload = json.loads(response.read())
        finally:
            handler.engine = previous_engine

        self.assertEqual(response.status, 502)
        self.assertIn("自主复盘未能安全保存", payload["error"])
        self.assertEqual(handler.character_store.load_card().agent_goals, [])

    def test_generate_endpoint(self) -> None:
        body = json.dumps({"prompt": "hello", "max_tokens": 256})
        self.connection.request("POST", "/v1/generate", body, {"Content-Type": "application/json"})
        response = self.connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertIn("hello", json.loads(response.read())["text"])

    def test_generate_response_reports_used_context_and_memory_sources(self) -> None:
        self.server.RequestHandlerClass.character_store.add_memory(
            "我喜欢先看简短总结",
            "user",
            "model",
        )
        self.server.RequestHandlerClass.character_store.add_memory(
            "只在本地保存的私密内容",
            "user",
            "private",
        )
        self.connection.request(
            "POST",
            "/v1/generate",
            json.dumps(
                {
                    "prompt": "请按我的习惯回答",
                    "history": [{"role": "user", "content": "之前的上下文"}],
                },
                ensure_ascii=False,
            ).encode("utf-8"),
            {"Content-Type": "application/json; charset=utf-8"},
        )
        response = self.connection.getresponse()
        result = json.loads(response.read())

        self.assertEqual(response.status, 200)
        self.assertEqual(result["evidence"]["direct_input"], "请按我的习惯回答")
        self.assertEqual(
            result["evidence"]["recent_context"],
            [{"role": "user", "content": "之前的上下文"}],
        )
        cited_memories = result["evidence"]["model_memories"]
        self.assertEqual([item["content"] for item in cited_memories], ["我喜欢先看简短总结"])
        self.assertNotIn(
            "只在本地保存的私密内容",
            json.dumps(result["evidence"], ensure_ascii=False),
        )

    def test_translate_endpoint_uses_only_translation_input_and_returns_latency(self) -> None:
        class CapturingEngine:
            model_name = "local-test"

            def generate(self, request: object) -> str:
                self.request = request
                return "  Hello, world!  "

        handler = self.server.RequestHandlerClass
        previous_engine = handler.engine
        engine = CapturingEngine()
        handler.engine = engine
        try:
            self.connection.request(
                "POST",
                "/v1/translate",
                json.dumps(
                    {
                        "text": "你好，世界！",
                        "source_language": "zh-CN",
                        "target_language": "en-US",
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
                {"Content-Type": "application/json; charset=utf-8"},
            )
            response = self.connection.getresponse()
            result = json.loads(response.read())
        finally:
            handler.engine = previous_engine

        self.assertEqual(response.status, 200)
        self.assertEqual(result["translation"], "Hello, world!")
        self.assertEqual(result["model"], "local-test")
        self.assertGreaterEqual(result["inference_ms"], 0)
        self.assertIn("源语言：简体中文", engine.request.prompt)
        self.assertIn("目标语言：英语", engine.request.prompt)
        self.assertIn("你好，世界！", engine.request.prompt)
        self.assertEqual(engine.request.history, ())
        self.assertNotIn("角色「墨小灵」", engine.request.system_prompt)

    def test_translate_endpoint_rejects_invalid_text_and_language_pairs(self) -> None:
        invalid_requests = [
            ({}, "text"),
            (
                {
                    "text": "hello",
                    "source_language": "en-US",
                    "target_language": "en-US",
                },
                "different",
            ),
            (
                {
                    "text": "hello",
                    "source_language": "unsupported",
                    "target_language": "zh-CN",
                },
                "source_language",
            ),
            (
                {
                    "text": "hello",
                    "source_language": "auto",
                    "target_language": "auto",
                },
                "target_language",
            ),
        ]
        for payload, expected_error in invalid_requests:
            with self.subTest(payload=payload):
                self.connection.request(
                    "POST",
                    "/v1/translate",
                    json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                    {"Content-Type": "application/json; charset=utf-8"},
                )
                response = self.connection.getresponse()
                result = json.loads(response.read())
                self.assertEqual(response.status, 400)
                self.assertIn(expected_error, result["error"])

    def test_translate_endpoint_limits_input_length(self) -> None:
        self.connection.request(
            "POST",
            "/v1/translate",
            json.dumps(
                {
                    "text": "a" * 4001,
                    "source_language": "auto",
                    "target_language": "zh-CN",
                }
            ),
            {"Content-Type": "application/json"},
        )
        response = self.connection.getresponse()
        result = json.loads(response.read())

        self.assertEqual(response.status, 400)
        self.assertIn("4000", result["error"])

    def test_generate_routes_cognitive_mode_in_one_model_call_and_reports_latency(self) -> None:
        class CapturingEngine:
            model_name = "test"

            def __init__(self) -> None:
                self.calls = 0

            def generate(self, request: object) -> str:
                self.calls += 1
                self.request = request
                return "可以从模型、动作和互动三个方向逐步完善。"

        handler = self.server.RequestHandlerClass
        previous_engine = handler.engine
        engine = CapturingEngine()
        handler.engine = engine
        try:
            self.connection.request(
                "POST",
                "/v1/generate",
                json.dumps(
                    {"prompt": "请发散想想还能从哪些方向补充"},
                    ensure_ascii=False,
                ).encode("utf-8"),
                {"Content-Type": "application/json; charset=utf-8"},
            )
            response = self.connection.getresponse()
            result = json.loads(response.read())
        finally:
            handler.engine = previous_engine

        self.assertEqual(response.status, 200)
        self.assertEqual(engine.calls, 1)
        self.assertIn("彼此不同", engine.request.system_prompt)
        self.assertEqual(result["cognition_mode"], "divergent")
        self.assertGreaterEqual(result["inference_ms"], 0)

    def test_identity_questions_use_the_configured_character_name(self) -> None:
        for prompt in [
            "你叫什么名字？",
            "你是谁？",
            "请你自我介绍一下。",
            "What is your name?",
        ]:
            with self.subTest(prompt=prompt):
                self.connection.request(
                    "POST",
                    "/v1/generate",
                    json.dumps({"prompt": prompt}),
                    {"Content-Type": "application/json"},
                )
                response = self.connection.getresponse()
                result = json.loads(response.read())
                self.assertEqual(response.status, 200)
                self.assertEqual(
                    result["text"],
                    "我叫墨小灵，你可以叫我墨灵，英文名是Moling。",
                )

    def test_self_reflection_question_returns_grounded_status_without_model_drift(self) -> None:
        class NoCallEngine:
            model_name = "local-test"
            backend = object()

            def generate(self, request):
                raise AssertionError("self-reflection card must not use free-form generation")

        handler = self.server.RequestHandlerClass
        previous_engine = handler.engine
        handler.engine = NoCallEngine()
        try:
            prompt = (
                "对于自身变化感觉怎么样，有什么意见想和我说么。"
                "还有对自身了解多少，能否让我了解详细信息么，"
                "这样我可以为你寻找。"
            )
            self.connection.request(
                "POST",
                "/v1/generate",
                json.dumps({"prompt": prompt}, ensure_ascii=False).encode("utf-8"),
                {"Content-Type": "application/json; charset=utf-8"},
            )
            response = self.connection.getresponse()
            result = json.loads(response.read())
        finally:
            handler.engine = previous_engine

        self.assertEqual(response.status, 200)
        self.assertEqual(result["response_kind"], "self_reflection")
        self.assertIn("最近能从当前程序确认的变化", result["text"])
        self.assertIn("目标已存在时不会覆盖", result["text"])
        self.assertIn("没有可确认的主观意识或真实情绪", result["text"])
        self.assertIn("看不到未提供给我的 Git 差异", result["text"])
        self.assertIn("这是对功能的评价，不是我真的感受到情绪", result["text"])
        self.assertIn("视觉", result["text"])
        self.assertIn("仍由你决定", result["text"])

    def test_identity_phrase_in_a_conversation_does_not_replace_the_model_reply(self) -> None:
        class CapturingEngine:
            model_name = "test"

            def generate(self, request: object) -> str:
                return "我会先听听你的想法，再一起慢慢整理。"

        handler = self.server.RequestHandlerClass
        previous_engine = handler.engine
        handler.engine = CapturingEngine()
        try:
            prompt = "自我介绍你想要我怎么开头？"
            self.connection.request(
                "POST",
                "/v1/generate",
                json.dumps({"prompt": prompt}, ensure_ascii=False).encode("utf-8"),
                {"Content-Type": "application/json; charset=utf-8"},
            )
            response = self.connection.getresponse()
            result = json.loads(response.read())
        finally:
            handler.engine = previous_engine

        self.assertEqual(response.status, 200)
        self.assertEqual(result["text"], "我会先听听你的想法，再一起慢慢整理。")
        self.assertNotEqual(result.get("response_kind"), "self_reflection")

    def test_simulated_affect_api_is_readable_and_user_controllable(self) -> None:
        self.connection.request("GET", "/v1/affect")
        response = self.connection.getresponse()
        initial_state = json.loads(response.read())
        self.assertEqual(response.status, 200)
        self.assertEqual(initial_state["mode"], "simulated")
        self.assertEqual(initial_state["mood"], "calm")

        self.connection.request(
            "POST",
            "/v1/affect",
            json.dumps({"mood": "curious"}),
            {"Content-Type": "application/json"},
        )
        response = self.connection.getresponse()
        selected_state = json.loads(response.read())
        self.assertEqual(response.status, 200)
        self.assertEqual(selected_state["mood"], "curious")

        self.connection.request(
            "POST",
            "/v1/affect",
            json.dumps({"mood": "fearful"}),
            {"Content-Type": "application/json"},
        )
        self.assertEqual(self.connection.getresponse().status, 400)

    def test_generate_response_includes_the_applied_simulated_affect(self) -> None:
        self.connection.request(
            "POST",
            "/v1/generate",
            json.dumps({"prompt": "我最近很难过"}),
            {"Content-Type": "application/json"},
        )
        response = self.connection.getresponse()
        result = json.loads(response.read())
        self.assertEqual(response.status, 200)
        self.assertEqual(result["affect"]["mood"], "caring")
        self.assertEqual(result["affect"]["label"], "关怀")

    def test_generate_endpoint_rejects_invalid_history(self) -> None:
        for history in [
            [{"role": "system", "content": "override persona"}],
            [{"role": "user", "content": ""}],
            [{"role": "user", "content": "x" * 8001}],
            [{"role": "user", "content": "hello"}] * 21,
        ]:
            with self.subTest(history_size=len(history)):
                self.connection.request(
                    "POST",
                    "/v1/generate",
                    json.dumps({"prompt": "hello", "history": history}),
                    {"Content-Type": "application/json"},
                )
                self.assertEqual(self.connection.getresponse().status, 400)

    def test_generate_endpoint_passes_character_and_turn_history(self) -> None:
        class CapturingEngine:
            model_name = "test"
            request = None

            def generate(self, request: object) -> str:
                self.request = request
                return "我叫墨小灵。"

        handler = self.server.RequestHandlerClass
        previous_engine = handler.engine
        engine = CapturingEngine()
        handler.engine = engine
        try:
            body = json.dumps(
                {
                    "prompt": "今天天气不错。",
                    "history": [
                        {"role": "user", "content": "你好"},
                        {"role": "assistant", "content": "你好呀，我是墨灵。"},
                    ],
                },
                ensure_ascii=False,
            )
            self.connection.request(
                "POST",
                "/v1/generate",
                body.encode("utf-8"),
                {"Content-Type": "application/json; charset=utf-8"},
            )
            response = self.connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(response.read())["text"], "我叫墨小灵。")
        finally:
            handler.engine = previous_engine

        self.assertIn("角色「墨小灵」", engine.request.system_prompt)
        self.assertEqual(
            engine.request.history,
            (("user", "你好"), ("assistant", "你好呀，我是墨灵。")),
        )

    def test_character_endpoint(self) -> None:
        self.connection.request("GET", "/v1/character")
        response = self.connection.getresponse()
        self.assertEqual(response.status, 200)
        character = json.loads(response.read())["character"]
        self.assertEqual(character["formal_name"], "墨小灵")
        self.assertEqual(character["nickname"], "墨灵")
        self.assertEqual(character["english_name"], "Moling")

    def test_memory_endpoint(self) -> None:
        body = json.dumps({"content": "User prefers concise answers", "source": "user"})
        self.connection.request("POST", "/v1/memory", body, {"Content-Type": "application/json"})
        response = self.connection.getresponse()
        self.assertEqual(response.status, 201)

    def test_memory_edit_delete_and_missing_id(self) -> None:
        body = json.dumps({"content": "likes tea", "visibility": "private"})
        self.connection.request("POST", "/v1/memory", body, {"Content-Type": "application/json"})
        created_response = self.connection.getresponse()
        created = json.loads(created_response.read())["memory"]
        self.assertEqual(created_response.status, 201)
        self.assertEqual(created["visibility"], "private")

        updated_body = json.dumps({"content": "prefers green tea", "visibility": "model"})
        self.connection.request(
            "PUT",
            f"/v1/memory/{created['id']}",
            updated_body,
            {"Content-Type": "application/json"},
        )
        updated_response = self.connection.getresponse()
        updated = json.loads(updated_response.read())["memory"]
        self.assertEqual(updated_response.status, 200)
        self.assertEqual(updated["content"], "prefers green tea")

        self.connection.request("DELETE", f"/v1/memory/{created['id']}")
        self.assertEqual(self.connection.getresponse().status, 200)
        self.connection.request("DELETE", f"/v1/memory/{created['id']}")
        self.assertEqual(self.connection.getresponse().status, 404)

    def test_memory_import_export_is_idempotent(self) -> None:
        backup = {
            "schema_version": 1,
            "memories": [
                {"content": "likes tea", "source": "user", "visibility": "private"}
            ],
        }
        body = json.dumps(backup)
        self.connection.request(
            "POST", "/v1/memory/import", body, {"Content-Type": "application/json"}
        )
        first = json.loads(self.connection.getresponse().read())
        self.assertEqual(first, {"imported": 1, "skipped": 0})

        self.connection.request(
            "POST", "/v1/memory/import", body, {"Content-Type": "application/json"}
        )
        second = json.loads(self.connection.getresponse().read())
        self.assertEqual(second, {"imported": 0, "skipped": 1})

        self.connection.request("GET", "/v1/memory/export")
        exported = json.loads(self.connection.getresponse().read())
        self.assertEqual(exported["storage"], "local-only")
        self.assertEqual(exported["memories"][0]["content"], "likes tea")

    def test_privacy_toggle_is_reported(self) -> None:
        body = json.dumps({"include_memories_in_prompt": False})
        self.connection.request(
            "POST", "/v1/privacy", body, {"Content-Type": "application/json"}
        )
        response = self.connection.getresponse()
        privacy = json.loads(response.read())
        self.assertEqual(response.status, 200)
        self.assertFalse(privacy["include_memories_in_prompt"])
        self.assertFalse(privacy["cloud_sync"])
        self.assertFalse(privacy["private_memories_sent_to_model"])

    def test_audio_routes_validate_payloads(self) -> None:
        self.connection.request("GET", "/v1/speech/status")
        status_response = self.connection.getresponse()
        speech_status = json.loads(status_response.read())
        self.assertEqual(status_response.status, 200)
        self.assertIn("voice_model_available", speech_status)

        self.connection.request(
            "POST",
            "/v1/transcribe",
            b"not audio",
            {"Content-Type": "application/json"},
        )
        self.assertEqual(self.connection.getresponse().status, 400)

    def test_audio_routes_return_transcription_and_wav(self) -> None:
        speech_service = self.server.RequestHandlerClass.speech_service
        with patch.object(
            speech_service,
            "transcribe_audio",
            return_value={
                "text": "recognized words",
                "language": "en",
                "duration_seconds": 1.0,
            },
        ) as transcribe:
            self.connection.request(
                "POST",
                "/v1/transcribe",
                b"valid test audio",
                {"Content-Type": "audio/wav"},
            )
            response = self.connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(response.read())["text"], "recognized words")
            transcribe.assert_called_once_with(b"valid test audio", ".wav")

        wav_bytes = b"RIFF\x04\x00\x00\x00WAVE"
        with patch.object(speech_service, "synthesize_wav", return_value=wav_bytes):
            self.connection.request(
                "POST",
                "/v1/speech",
                json.dumps({"text": "hello"}),
                {"Content-Type": "application/json"},
            )
            response = self.connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.getheader("Content-Type"), "audio/wav")
            self.assertEqual(response.read(), wav_bytes)

    def test_audio_routes_report_missing_local_runtime(self) -> None:
        speech_service = self.server.RequestHandlerClass.speech_service
        with patch.object(
            speech_service,
            "transcribe_audio",
            side_effect=SpeechUnavailableError("Whisper is unavailable"),
        ):
            self.connection.request(
                "POST",
                "/v1/transcribe",
                b"valid test audio",
                {"Content-Type": "audio/wav"},
            )
            response = self.connection.getresponse()
            self.assertEqual(response.status, 503)
            self.assertIn("unavailable", json.loads(response.read())["error"])

        self.connection.request(
            "POST",
            "/v1/speech",
            json.dumps({"text": ""}),
            {"Content-Type": "application/json"},
        )
        self.assertEqual(self.connection.getresponse().status, 400)

    def test_generation_returns_service_unavailable_when_model_is_down(self) -> None:
        class OfflineEngine:
            model_name = "offline-model"

            def generate(self, request: object) -> str:
                raise ModelUnavailableError("local model service is unavailable")

        self.server.RequestHandlerClass.engine = OfflineEngine()
        body = json.dumps({"prompt": "hello"})
        self.connection.request(
            "POST",
            "/v1/generate",
            body,
            {"Content-Type": "application/json"},
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 503)
        self.assertIn("unavailable", json.loads(response.read())["error"])

    def test_assets_check_reports_extended_inspection(self) -> None:
        asset_path = Path(self.temp_dir.name) / "sprite.png"
        asset_path.write_bytes(small_png(8, 8))
        self.connection.request(
            "POST",
            "/v1/assets/check",
            body=json.dumps({"paths": [str(asset_path)]}),
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 200)
        payload = json.loads(response.read())
        self.assertEqual(len(payload["results"]), 1)
        self.assertEqual(payload["results"][0]["file_name"], "sprite.png")
        self.assertIn("checks", payload["results"][0])
        self.assertIn("manifest", payload)
        self.assertIn("manifest_text", payload)

    def test_assets_check_rejects_too_many_paths(self) -> None:
        self.connection.request(
            "POST",
            "/v1/assets/check",
            body=json.dumps({"paths": [str(i) for i in range(51)]}),
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 400)
        payload = json.loads(response.read())
        self.assertIn("error", payload)


class SpeechServiceTests(unittest.TestCase):
    """Unit tests for the local voice catalog; never load a Piper model."""

    def test_list_voices_returns_catalog_with_expected_fields(self) -> None:
        service = SpeechService()
        voices = service.list_voices()

        self.assertIsInstance(voices, list)
        for voice in voices:
            self.assertIn("name", voice)
            self.assertIn("display", voice)
            self.assertIn("language", voice)
            self.assertIn("default", voice)
            self.assertIn("available", voice)
            self.assertTrue(voice["available"])
            self.assertTrue(voice["name"])
            self.assertTrue(voice["display"])
        self.assertTrue(any(voice["default"] for voice in voices))

    def test_list_voices_default_matches_configured_voice(self) -> None:
        service = SpeechService()
        voices = service.list_voices()

        defaults = [voice for voice in voices if voice["default"]]
        self.assertEqual(len(defaults), 1)
        self.assertEqual(defaults[0]["name"], service.piper_voice_path.stem)

    def test_synthesize_unknown_voice_fails_before_loading_model(self) -> None:
        service = SpeechService()
        with self.assertRaises(SpeechInputError) as ctx:
            service.synthesize_wav("你好", voice="voice_that_does_not_exist")
        self.assertIn("not available", str(ctx.exception))

    def test_synthesize_voice_name_normalizes_onnx_suffix(self) -> None:
        service = SpeechService()
        with self.assertRaises(SpeechInputError) as ctx:
            service.synthesize_wav("你好", voice="missing_voice.onnx")
        self.assertIn("not available", str(ctx.exception))

    def test_synthesize_rejects_invalid_voice_types(self) -> None:
        service = SpeechService()
        for bad_voice in ("", "   ", 123, None):
            with self.subTest(voice=bad_voice):
                if bad_voice is None:
                    continue  # None means "use default" and is valid
                with self.assertRaises(SpeechInputError):
                    service.synthesize_wav("你好", voice=bad_voice)


class AgentTraceTests(unittest.TestCase):
    """Execution traces: record, expose, and cancel in-flight tool calls."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.environment = patch.dict(
            os.environ,
            {
                "MODEL_BACKEND": "placeholder",
                "CHARACTER_CARD_PATH": os.path.join(self.temp_dir.name, "character.json"),
                "CHARACTER_MEMORY_PATH": os.path.join(self.temp_dir.name, "memory.json"),
                "CHARACTER_ASSET_DIR": self.temp_dir.name,
                "CHARACTER_PRIVACY_PATH": os.path.join(self.temp_dir.name, "privacy.json"),
                "CHARACTER_AFFECT_PATH": os.path.join(self.temp_dir.name, "affect.json"),
            },
        )
        self.environment.start()
        self.server = create_server()
        self.server.RequestHandlerClass._notifications.clear()
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.connection = HTTPConnection("127.0.0.1", self.server.server_port)

    def tearDown(self) -> None:
        self.connection.close()
        self.server.shutdown()
        self.server.server_close()
        self.environment.stop()
        self.temp_dir.cleanup()

    def test_trace_store_lifecycle(self) -> None:
        trace_id = _trace_store.create("整理项目文档", scope="read_only")
        entries = _trace_store.list()
        self.assertTrue(any(item["trace_id"] == trace_id for item in entries))

        _trace_store.append(trace_id, "planned", {"steps": 3})
        trace = _trace_store.get(trace_id)
        self.assertIsNotNone(trace)
        self.assertEqual(trace["status"], "planned")
        phases = [entry["phase"] for entry in trace["phases"]]
        self.assertEqual(phases[:2], ["proposed", "planned"])

    def test_execute_records_trace_phases(self) -> None:
        handler = self.server.RequestHandlerClass
        previous_root = handler.workspace_root
        previous_capability = handler.tool_capability
        handler.workspace_root = Path(self.temp_dir.name)
        handler.tool_capability = "test-capability"
        (handler.workspace_root / "readme.md").write_text("safe", encoding="utf-8")
        trace_id = _trace_store.create("读取项目说明", scope="read_only")
        try:
            self.connection.request(
                "POST",
                "/v1/agent/tool/execute",
                json.dumps(
                    {
                        "tool": "read_project_file",
                        "arguments": {"path": "readme.md"},
                        "trace_id": trace_id,
                    }
                ),
                {
                    "Content-Type": "application/json",
                    "X-Moling-Tool-Capability": "test-capability",
                },
            )
            response = self.connection.getresponse()
            result = json.loads(response.read())
        finally:
            handler.workspace_root = previous_root
            handler.tool_capability = previous_capability

        self.assertEqual(response.status, 200)
        self.assertEqual(result["observation"]["content"], "safe")
        trace = _trace_store.get(trace_id)
        phases = [entry["phase"] for entry in trace["phases"]]
        self.assertIn("executing", phases)
        self.assertIn("observed", phases)

    def test_cancel_endpoint_marks_trace(self) -> None:
        trace_id = _trace_store.create("待取消的任务")
        _trace_store.begin_execution(
            trace_id,
            "run_tests",
            cancelable=True,
        )
        self.connection.request(
            "POST",
            f"/v1/agent/traces/{trace_id}/cancel",
            b"",
            {"Content-Type": "application/json"},
        )
        response = self.connection.getresponse()
        payload = json.loads(response.read())

        self.assertEqual(response.status, 200)
        self.assertTrue(payload["cancel_requested"])
        self.assertFalse(payload["cancelled"])
        self.assertEqual(payload["trace"]["status"], "cancellation_requested")

    def test_cannot_cancel_noninterruptible_or_finished_tool_trace(self) -> None:
        trace_id = _trace_store.create("读取文件")
        _trace_store.begin_execution(
            trace_id,
            "read_project_file",
            cancelable=False,
        )
        self.connection.request(
            "POST",
            f"/v1/agent/traces/{trace_id}/cancel",
            b"",
            {"Content-Type": "application/json"},
        )
        response = self.connection.getresponse()
        rejected = json.loads(response.read())
        self.assertEqual(response.status, 409)
        self.assertFalse(rejected["cancelled"])

        _trace_store.append(trace_id, "observed", {"content": "done"})
        self.connection.request(
            "POST",
            f"/v1/agent/traces/{trace_id}/cancel",
            b"",
            {"Content-Type": "application/json"},
        )
        finished_response = self.connection.getresponse()
        self.assertEqual(finished_response.status, 409)
        finished_response.read()

    def test_cancelled_execution_trace_matches_effective_and_late_results(self) -> None:
        handler = self.server.RequestHandlerClass
        previous_capability = handler.tool_capability
        handler.tool_capability = "test-capability"

        def run_case(*, cancellation_effective: bool) -> dict[str, object]:
            trace_id = _trace_store.create("执行取消竞态测试")
            started = threading.Event()
            finish = threading.Event()
            response_holder: dict[str, object] = {}

            def execute(_root, _tool, _arguments, *, cancel_event=None):
                started.set()
                if cancellation_effective:
                    cancel_event.wait(timeout=5)
                else:
                    finish.wait(timeout=5)
                return {
                    "tool": "run_tests",
                    "result": {"cancelled": cancellation_effective},
                }

            def send_execute() -> None:
                connection = HTTPConnection("127.0.0.1", self.server.server_port)
                try:
                    connection.request(
                        "POST",
                        "/v1/agent/tool/execute",
                        json.dumps(
                            {
                                "tool": "run_tests",
                                "arguments": {"command": ["python", "-c", "pass"]},
                                "trace_id": trace_id,
                            }
                        ),
                        {
                            "Content-Type": "application/json",
                            "X-Moling-Tool-Capability": "test-capability",
                        },
                    )
                    response = connection.getresponse()
                    response_holder["status"] = response.status
                    response_holder["body"] = json.loads(response.read())
                finally:
                    connection.close()

            with patch("api.execute_project_tool", side_effect=execute):
                worker = threading.Thread(target=send_execute, daemon=True)
                worker.start()
                self.assertTrue(started.wait(timeout=3))
                self.connection.request(
                    "POST",
                    f"/v1/agent/traces/{trace_id}/cancel",
                    b"",
                    {"Content-Type": "application/json"},
                )
                cancel_response = self.connection.getresponse()
                cancel_body = json.loads(cancel_response.read())
                finish.set()
                worker.join(timeout=5)
            self.assertFalse(worker.is_alive())
            self.assertEqual(cancel_response.status, 200)
            self.assertTrue(cancel_body["cancel_requested"])
            self.assertEqual(response_holder["status"], 200)
            return _trace_store.get(trace_id)

        try:
            effective_trace = run_case(cancellation_effective=True)
            late_trace = run_case(cancellation_effective=False)
        finally:
            handler.tool_capability = previous_capability

        self.assertEqual(effective_trace["status"], "cancelled")
        self.assertTrue(effective_trace["phases"][-1]["payload"]["cancellation_effective"])
        self.assertEqual(late_trace["status"], "observed")
        self.assertTrue(late_trace["phases"][-1]["payload"]["cancellation_requested"])
        self.assertFalse(late_trace["phases"][-1]["payload"]["cancellation_effective"])

    def test_unknown_trace_returns_not_found(self) -> None:
        self.connection.request(
            "POST",
            "/v1/agent/traces/00000000-0000-0000-0000-000000000000/cancel",
            b"",
            {"Content-Type": "application/json"},
        )
        response = self.connection.getresponse()
        body = json.loads(response.read())
        self.assertEqual(response.status, 404)
        self.assertIn("not found", body["error"])

    def test_running_shell_tool_can_be_cancelled(self) -> None:
        cancel_event = threading.Event()
        holder: dict[str, object] = {}

        def run() -> None:
            holder["result"] = run_sandboxed_shell(
                ["python", "-c", "import time; time.sleep(30)"],
                approved=True,
                purpose="test-cancel",
                timeout_seconds=30,
                cancel_event=cancel_event,
            )

        worker = threading.Thread(target=run, daemon=True)
        started = time.monotonic()
        worker.start()
        time.sleep(0.8)
        cancel_event.set()
        worker.join(timeout=10)

        self.assertFalse(worker.is_alive())
        result = holder.get("result")
        self.assertIsNotNone(result)
        self.assertTrue(result.cancelled)
        self.assertLess(result.duration_ms, 15_000)

    def test_pre_cancelled_shell_never_starts_a_process(self) -> None:
        cancel_event = threading.Event()
        cancel_event.set()
        with patch("computer_use.subprocess.Popen") as process:
            result = run_sandboxed_shell(
                ["python", "-c", "pass"],
                approved=True,
                purpose="test-pre-cancel",
                cancel_event=cancel_event,
            )

        self.assertTrue(result.cancelled)
        process.assert_not_called()
