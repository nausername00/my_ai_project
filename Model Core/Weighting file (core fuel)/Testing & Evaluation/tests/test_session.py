"""T5 手机陪伴：断点续接端点（会话上下文摘要）+ 简报默认关核验。"""

import json
import os
import tempfile
import unittest
from http.client import HTTPConnection
from threading import Thread
from unittest.mock import patch

from app import create_server


class SessionResumeSmokeTest(unittest.TestCase):
    """T5 HTTP 冒烟：GET /v1/session/resume 可恢复摘要 + 简报默认关。"""

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
                "AVATAR_REGISTRY_PATH": os.path.join(self.temp_dir.name, "avatars.json"),
                "AVATAR_AWAKEN_LOG_PATH": os.path.join(
                    self.temp_dir.name, "awaken_log.json"
                ),
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

    def test_resume_endpoint_shape(self) -> None:
        self.connection.request("GET", "/v1/session/resume")
        response = self.connection.getresponse()
        self.assertEqual(response.status, 200)
        body = json.loads(response.read())
        self.assertIn("resume_at", body)
        self.assertIsInstance(body["personas"], list)
        self.assertIsInstance(body["memories"], list)

    def test_brief_default_off(self) -> None:
        self.connection.request("GET", "/v1/session/resume")
        response = self.connection.getresponse()
        body = json.loads(response.read())
        self.assertTrue(body["brief"]["available"])
        self.assertFalse(body["brief"]["enabled"])  # 简报默认关，不自动推送

    def test_resume_hint_present(self) -> None:
        self.connection.request("GET", "/v1/session/resume")
        response = self.connection.getresponse()
        body = json.loads(response.read())
        self.assertIn("/v1/chat", body["hint"])


if __name__ == "__main__":
    unittest.main()
