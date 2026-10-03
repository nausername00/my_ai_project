import os
import json
import unittest
import base64
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from unittest.mock import patch

from inference import (
    GenerationRequest,
    InferenceEngine,
    ModelUnavailableError,
    OllamaBackend,
    TransformersBackend,
)


class InferenceEngineTests(unittest.TestCase):
    def test_preserves_system_prompt_when_calling_backend(self) -> None:
        class CapturingBackend:
            model_name = "test"

            def generate(self, request: GenerationRequest) -> str:
                self.request = request
                return "answer"

        backend = CapturingBackend()
        result = InferenceEngine(backend).generate(
            GenerationRequest(
                " hello ",
                32,
                "你是可可。",
                (("user", "你好"), ("assistant", "你好呀，我是可可。")),
                json_mode=True,
                temperature=0.0,
            )
        )

        self.assertEqual(result, "answer")
        self.assertEqual(backend.request.prompt, "hello")
        self.assertEqual(backend.request.system_prompt, "你是可可。")
        self.assertEqual(
            backend.request.history,
            (("user", "你好"), ("assistant", "你好呀，我是可可。")),
        )
        self.assertTrue(backend.request.json_mode)
        self.assertEqual(backend.request.temperature, 0.0)

    def test_generates_deterministic_response(self) -> None:
        result = InferenceEngine().generate(GenerationRequest("hello", 20))
        self.assertEqual(result, "[placeholder] hello")

    def test_rejects_empty_prompt(self) -> None:
        with self.assertRaises(ValueError):
            InferenceEngine().generate(GenerationRequest(" "))

    def test_enforces_token_limit(self) -> None:
        with self.assertRaises(ValueError):
            InferenceEngine().generate(GenerationRequest("hello", 0))

    def test_transformers_backend_requires_existing_directory(self) -> None:
        with self.assertRaises(ModelUnavailableError):
            TransformersBackend("missing-model-directory")

    def test_environment_selects_placeholder_backend(self) -> None:
        previous = os.environ.get("MODEL_BACKEND")
        os.environ["MODEL_BACKEND"] = "placeholder"
        try:
            self.assertEqual(InferenceEngine.from_environment().model_name, "placeholder")
        finally:
            if previous is None:
                os.environ.pop("MODEL_BACKEND", None)
            else:
                os.environ["MODEL_BACKEND"] = previous

    def test_ollama_backend_posts_chat_request_and_returns_content(self) -> None:
        received: dict[str, object] = {}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                received["path"] = self.path
                received["payload"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                body = json.dumps({"message": {"content": "local answer"}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                return

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            backend = OllamaBackend(
                "test-model",
                f"http://127.0.0.1:{server.server_port}",
                timeout=2,
            )
            result = backend.generate(
                GenerationRequest(
                    "hello",
                    32,
                    "Answer helpfully.",
                    (("user", "previous question"), ("assistant", "previous answer")),
                    json_mode=True,
                    temperature=0.0,
                )
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(result, "local answer")
        self.assertEqual(received["path"], "/api/chat")
        self.assertEqual(received["payload"]["model"], "test-model")
        self.assertEqual(received["payload"]["messages"][0]["role"], "system")
        self.assertEqual(
            received["payload"]["messages"][0]["content"],
            "Answer helpfully.",
        )
        self.assertEqual(received["payload"]["messages"][1]["content"], "previous question")
        self.assertEqual(received["payload"]["messages"][2]["content"], "previous answer")
        self.assertEqual(received["payload"]["messages"][3]["content"], "hello")
        self.assertEqual(received["payload"]["format"], "json")
        self.assertEqual(received["payload"]["options"]["temperature"], 0.0)
        self.assertEqual(received["payload"]["options"]["num_predict"], 32)

    def test_ollama_backend_sends_image_only_to_loopback(self) -> None:
        received: dict[str, object] = {}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                received["payload"] = json.loads(
                    self.rfile.read(int(self.headers["Content-Length"]))
                )
                body = json.dumps({"message": {"content": "看见一张示例图片"}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                return

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        image = b"\x89PNG\r\n\x1a\nsample"
        try:
            engine = InferenceEngine(
                OllamaBackend(
                    "local-vision-test",
                    f"http://127.0.0.1:{server.server_port}",
                    timeout=2,
                )
            )
            result = engine.generate(GenerationRequest("描述图片"), image=image)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        user_message = received["payload"]["messages"][-1]
        self.assertEqual(result, "看见一张示例图片")
        self.assertEqual(user_message["content"], "描述图片")
        self.assertEqual(user_message["images"], [base64.b64encode(image).decode("ascii")])

    def test_image_input_is_rejected_for_non_ollama_backends(self) -> None:
        with self.assertRaises(ModelUnavailableError):
            InferenceEngine().generate(GenerationRequest("describe"), image=b"image")

    def test_ollama_rejects_remote_image_endpoint_and_oversized_images(self) -> None:
        remote = InferenceEngine(OllamaBackend("vision", "https://example.com"))
        with self.assertRaisesRegex(ModelUnavailableError, "loopback"):
            remote.generate(GenerationRequest("describe"), image=b"image")

        local = InferenceEngine(OllamaBackend("vision", "http://127.0.0.1:11434"))
        with self.assertRaisesRegex(ValueError, "10 MB"):
            local.generate(GenerationRequest("describe"), image=b"x" * (10 * 1024 * 1024 + 1))

    def test_ollama_backend_reports_connection_failure(self) -> None:
        backend = OllamaBackend("test-model", "http://127.0.0.1:1", timeout=0.1)
        with self.assertRaises(ModelUnavailableError):
            backend.generate(GenerationRequest("hello"))

    def test_environment_selects_ollama_backend(self) -> None:
        with patch.dict(
            os.environ,
            {
                "MODEL_BACKEND": "ollama",
                "OLLAMA_MODEL": "local-test",
                "OLLAMA_URL": "http://127.0.0.1:11434",
            },
            clear=False,
        ):
            engine = InferenceEngine.from_environment()
        self.assertEqual(engine.model_name, "local-test")