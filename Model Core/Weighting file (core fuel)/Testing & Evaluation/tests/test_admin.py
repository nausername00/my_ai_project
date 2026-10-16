"""T4 服务化：认证判定、self-host 端点（默认关、需 token）、HTTP 冒烟。"""

import json
import os
import tempfile
import unittest
from http.client import HTTPConnection
from threading import Thread
from unittest.mock import patch

from app import create_server
import api


class AuthCheckTest(unittest.TestCase):
    """_auth_allowed 纯函数：公开/状态放行、admin 需 token、非本机需 token。"""

    def setUp(self) -> None:
        self.token_patch = patch("api._AUTH_TOKEN", "")
        self.token_patch.start()

    def tearDown(self) -> None:
        self.token_patch.stop()

    def test_public_and_status_always_allowed(self) -> None:
        self.assertTrue(api._auth_allowed("/health", True, ""))
        self.assertTrue(api._auth_allowed("/v1/status/metrics", False, ""))
        self.assertTrue(api._auth_allowed("/v1/status/platform", False, ""))

    def test_admin_requires_token_even_loopback(self) -> None:
        self.assertFalse(api._auth_allowed("/v1/admin/self-host", True, ""))
        self.assertFalse(api._auth_allowed("/v1/admin/self-host", True, "wrong"))
        with patch("api._AUTH_TOKEN", "secret"):
            self.assertTrue(api._auth_allowed("/v1/admin/self-host", True, "secret"))
            self.assertFalse(api._auth_allowed("/v1/admin/self-host", True, "wrong"))

    def test_loopback_free_without_token(self) -> None:
        self.assertTrue(api._auth_allowed("/v1/chat", True, ""))

    def test_non_loopback_requires_token(self) -> None:
        self.assertFalse(api._auth_allowed("/v1/chat", False, ""))
        with patch("api._AUTH_TOKEN", "secret"):
            self.assertTrue(api._auth_allowed("/v1/chat", False, "secret"))
            self.assertFalse(api._auth_allowed("/v1/chat", False, "wrong"))


class SelfHostToggleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.enabled_patch = patch("api._SELF_HOST_ENABLED", False)
        self.token_patch = patch("api._AUTH_TOKEN", "secret")
        self.enabled_patch.start()
        self.token_patch.start()

    def tearDown(self) -> None:
        self.token_patch.stop()
        self.enabled_patch.stop()

    def test_cannot_enable_without_token(self) -> None:
        with patch("api._AUTH_TOKEN", ""):
            result = api._set_self_host(True)
            self.assertIn("error", result)
            self.assertIn("MOLING_API_TOKEN", result["error"])

    def test_toggle_with_token(self) -> None:
        result = api._set_self_host(True)
        self.assertTrue(result["enabled"])
        result = api._set_self_host(False)
        self.assertFalse(result["enabled"])

    def test_status_shape(self) -> None:
        status = api._self_host_status()
        self.assertFalse(status["enabled"])
        self.assertTrue(status["token_configured"])
        self.assertFalse(status["tls"])
        self.assertIn("hint", status)


class AdminHttpSmokeTest(unittest.TestCase):
    """T4 HTTP 冒烟：无 token 401 / 带 token 200 / 开关切换。"""

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
        self.token_patch = patch("api._AUTH_TOKEN", "")
        self.enabled_patch = patch("api._SELF_HOST_ENABLED", False)
        self.token_patch.start()
        self.enabled_patch.start()
        self.server = create_server()
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.connection = HTTPConnection("127.0.0.1", self.server.server_port)

    def tearDown(self) -> None:
        self.connection.close()
        self.server.shutdown()
        self.server.server_close()
        self.enabled_patch.stop()
        self.token_patch.stop()
        self.environment.stop()
        self.temp_dir.cleanup()

    def _get(self, path: str, token: str | None = None) -> tuple[int, dict]:
        headers = {}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        self.connection.request("GET", path, headers=headers)
        response = self.connection.getresponse()
        body = json.loads(response.read())
        return response.status, body

    def _post(self, path: str, payload: dict, token: str | None = None) -> tuple[int, dict]:
        headers = {"Content-Type": "application/json"}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        self.connection.request(
            "POST", path, body=json.dumps(payload), headers=headers
        )
        response = self.connection.getresponse()
        body = json.loads(response.read())
        return response.status, body

    def test_admin_requires_token_without_configured_token(self) -> None:
        status, body = self._get("/v1/admin/self-host")
        self.assertEqual(status, 401)
        self.assertIn("error", body)

    def test_health_is_public(self) -> None:
        status, _ = self._get("/health")
        self.assertEqual(status, 200)

    def test_admin_with_token(self) -> None:
        with patch("api._AUTH_TOKEN", "secret"):
            status, body = self._get("/v1/admin/self-host", token="secret")
            self.assertEqual(status, 200)
            self.assertFalse(body["enabled"])
            self.assertTrue(body["token_configured"])

    def test_admin_wrong_token_rejected(self) -> None:
        with patch("api._AUTH_TOKEN", "secret"):
            status, _ = self._get("/v1/admin/self-host", token="wrong")
            self.assertEqual(status, 401)

    def test_toggle_self_host(self) -> None:
        with patch("api._AUTH_TOKEN", "secret"):
            status, body = self._post(
                "/v1/admin/self-host", {"enabled": True}, token="secret"
            )
            self.assertEqual(status, 200)
            self.assertTrue(body["enabled"])

    def test_toggle_requires_bool(self) -> None:
        with patch("api._AUTH_TOKEN", "secret"):
            status, body = self._post(
                "/v1/admin/self-host", {"enabled": "yes"}, token="secret"
            )
            self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
