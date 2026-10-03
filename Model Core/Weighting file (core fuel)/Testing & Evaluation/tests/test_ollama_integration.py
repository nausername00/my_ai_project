import json
import os
import tempfile
import unittest
from http.client import HTTPConnection
from threading import Thread
from unittest.mock import patch

from app import create_server


@unittest.skipUnless(
    os.getenv("RUN_OLLAMA_INTEGRATION") == "1",
    "set RUN_OLLAMA_INTEGRATION=1 to test a live local Ollama model",
)
class OllamaIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.environment = patch.dict(
            os.environ,
            {
                "MODEL_BACKEND": "ollama",
                "OLLAMA_MODEL": os.getenv("OLLAMA_MODEL", "qwen2.5:3b"),
                "OLLAMA_URL": os.getenv("OLLAMA_URL", "http://127.0.0.1:11434"),
                "CHARACTER_CARD_PATH": os.path.join(self.temp_dir.name, "character.json"),
                "CHARACTER_MEMORY_PATH": os.path.join(self.temp_dir.name, "memory.json"),
                "CHARACTER_ASSET_DIR": self.temp_dir.name,
                "CHARACTER_AFFECT_PATH": os.path.join(self.temp_dir.name, "affect.json"),
            },
        )
        self.environment.start()
        self.server = create_server()
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.environment.stop()
        self.temp_dir.cleanup()

    def test_generation_uses_live_local_model(self) -> None:
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=180)
        try:
            body = json.dumps(
                {"prompt": "Answer with only the number: what is 2+2?", "max_tokens": 32}
            )
            connection.request(
                "POST",
                "/v1/generate",
                body,
                {"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            result = json.loads(response.read())
        finally:
            connection.close()

        self.assertEqual(response.status, 200, result)
        self.assertEqual(result["model"], os.environ["OLLAMA_MODEL"])
        self.assertNotIn("[placeholder]", result["text"])
        self.assertIn("4", result["text"])

    def test_translation_uses_live_local_model(self) -> None:
        results = []
        for source_text in ("你好，世界！", "我喜欢学习新的语言。"):
            connection = HTTPConnection(
                "127.0.0.1",
                self.server.server_port,
                timeout=180,
            )
            try:
                body = json.dumps(
                    {
                        "text": source_text,
                        "source_language": "zh-CN",
                        "target_language": "en-US",
                    },
                    ensure_ascii=False,
                )
                connection.request(
                    "POST",
                    "/v1/translate",
                    body.encode("utf-8"),
                    {"Content-Type": "application/json; charset=utf-8"},
                )
                response = connection.getresponse()
                results.append(json.loads(response.read()))
            finally:
                connection.close()

        self.assertEqual(response.status, 200, results[-1])
        for result in results:
            self.assertEqual(result["model"], os.environ["OLLAMA_MODEL"])
            self.assertTrue(result["translation"].strip())
        self.assertTrue(
            any(
                word in results[0]["translation"].casefold()
                for word in ("hello", "hi")
            ),
            results[0],
        )
        self.assertIn("learn", results[1]["translation"].casefold(), results[1])
        self.assertIn("language", results[1]["translation"].casefold(), results[1])

    def test_agent_reflection_uses_local_model_and_persists_valid_state(self) -> None:
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=180)
        try:
            body = json.dumps(
                {
                    "character_id": "character",
                    "history": [
                        {
                            "role": "user",
                            "content": "我最近在学日语，想多练习日常会话。",
                        },
                        {
                            "role": "assistant",
                            "content": "我们可以一起练习问候和点餐。",
                        },
                    ],
                },
                ensure_ascii=False,
            )
            connection.request(
                "POST",
                "/v1/agent/reflect",
                body.encode("utf-8"),
                {"Content-Type": "application/json; charset=utf-8"},
            )
            response = connection.getresponse()
            result = json.loads(response.read())
        finally:
            connection.close()

        self.assertEqual(response.status, 200, result)
        self.assertTrue(result["updated"])
        self.assertIsInstance(result["goals"], list)
        self.assertIsInstance(result["reflection"], str)
        self.assertEqual(result["ignored_updates"], 0, result)
        self.assertEqual(result["ignored_goals"], 0, result)
