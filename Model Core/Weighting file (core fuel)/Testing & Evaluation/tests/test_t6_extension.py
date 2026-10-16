"""T6 遗留闭环：插件执行授权（PluginApprovals）+ 多后端并行 + 手机客户端载体静态服务。"""

import json
import os
import tempfile
import unittest
from http.client import HTTPConnection
from threading import Thread
from unittest.mock import patch

from inference import InferenceEngine, PlaceholderBackend, ModelUnavailableError
from plugins import PluginApprovals, PluginRegistry


class PluginApprovalsTest(unittest.TestCase):
    """T6 插件执行授权：默认全拒；批准/撤销/校验；非法权限拒绝；损坏文件按无授权。"""

    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "approvals.json")
        self.approvals = PluginApprovals(self.path)

    def tearDown(self) -> None:
        self.dir.cleanup()

    def test_default_denied(self) -> None:
        self.assertFalse(self.approvals.is_authorized("helper", "file:read"))
        self.assertEqual(self.approvals.status("helper"), {"name": "helper", "permissions": [], "approved": False})

    def test_authorize_and_check(self) -> None:
        self.approvals.authorize("helper", ["file:read", "network"])
        self.assertTrue(self.approvals.is_authorized("helper", "file:read"))
        self.assertTrue(self.approvals.is_authorized("helper", "network"))
        self.assertFalse(self.approvals.is_authorized("helper", "execute"))
        status = self.approvals.status("helper")
        self.assertTrue(status["approved"])
        self.assertEqual(set(status["permissions"]), {"file:read", "network"})

    def test_authorize_overwrites_full(self) -> None:
        self.approvals.authorize("helper", ["file:read", "network"])
        self.approvals.authorize("helper", ["network"])  # 全量覆盖 → file:read 失效
        self.assertFalse(self.approvals.is_authorized("helper", "file:read"))
        self.assertTrue(self.approvals.is_authorized("helper", "network"))

    def test_revoke_returns_denied(self) -> None:
        self.approvals.authorize("helper", ["file:read"])
        result = self.approvals.revoke("helper")
        self.assertFalse(result["approved"])
        self.assertFalse(self.approvals.is_authorized("helper", "file:read"))

    def test_invalid_permission_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.approvals.authorize("helper", ["UPPER:bad"])
        with self.assertRaises(ValueError):
            self.approvals.authorize("helper", "file:read")  # 非列表

    def test_corrupt_file_treated_as_none(self) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{not json")
        self.assertFalse(self.approvals.is_authorized("helper", "file:read"))

    def test_registry_permissions_roundtrip(self) -> None:
        reg_path = os.path.join(self.dir.name, "plugins.json")
        registry = PluginRegistry(reg_path)
        registry.register(
            {
                "name": "helper",
                "version": "1.0.0",
                "capabilities": ["tool:run"],
                "permissions": ["file:read", "network"],
            }
        )
        entry = registry.get("helper")
        self.assertEqual(entry["permissions"], ["file:read", "network"])
        # 非法权限声明拒绝
        with self.assertRaises(ValueError):
            registry.register(
                {
                    "name": "bad",
                    "version": "1.0.0",
                    "capabilities": ["tool:run"],
                    "permissions": ["RM -RF"],
                }
            )
        # 缺省 permissions 合法（保持向后兼容）
        registry.register({"name": "plain", "version": "1.0.0", "capabilities": ["x"]})
        self.assertEqual(registry.get("plain")["permissions"], [])


class MultiBackendTest(unittest.TestCase):
    """T6 多后端并行：注册/列表/解析/按指定后端生成；非法 id 拒绝。"""

    def setUp(self) -> None:
        self.engine = InferenceEngine(PlaceholderBackend())

    def test_register_and_list(self) -> None:
        self.engine.register_backend("fast", PlaceholderBackend())
        backends = self.engine.list_backends()
        self.assertEqual(backends[0]["id"], "default")
        self.assertEqual([b["id"] for b in backends], ["default", "fast"])

    def test_resolve_default_and_extra(self) -> None:
        self.engine.register_backend("fast", PlaceholderBackend())
        self.assertIs(self.engine.resolve_backend(None), self.engine.backend)
        self.assertIs(self.engine.resolve_backend("default"), self.engine.backend)
        self.assertIs(self.engine.resolve_backend("fast"), self.engine._extra_backends["fast"])

    def test_generate_via_extra_backend(self) -> None:
        self.engine.register_backend("fast", PlaceholderBackend())
        text = self.engine.generate(
            type("R", (), {"prompt": "你好", "max_tokens": 64, "system_prompt": "", "history": (), "json_mode": False, "temperature": None})(),
            backend_id="fast",
        )
        self.assertTrue(text.startswith("[placeholder]"))

    def test_unknown_backend_rejected(self) -> None:
        with self.assertRaises(ModelUnavailableError):
            self.engine.resolve_backend("ghost")

    def test_invalid_backend_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.register_backend("Bad ID!", PlaceholderBackend())


class T6ExtensionHttpSmokeTest(unittest.TestCase):
    """HTTP 冒烟：插件授权端点、多后端端点、mobile 静态服务与目录穿越防护。"""

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
                "AVATAR_AWAKEN_LOG_PATH": os.path.join(self.temp_dir.name, "awaken_log.json"),
                "AVATAR_TOOL_LOG_PATH": os.path.join(self.temp_dir.name, "tool_log.json"),
                "PLUGIN_REGISTRY_PATH": os.path.join(self.temp_dir.name, "plugins.json"),
                "PLUGIN_APPROVALS_PATH": os.path.join(self.temp_dir.name, "approvals.json"),
            },
        )
        self.environment.start()
        from app import create_server

        self.server = create_server()
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.connection = HTTPConnection("127.0.0.1", self.server.server_port)

    def tearDown(self) -> None:
        self.connection.close()
        self.server.shutdown()
        self.server.server_close()
        self.environment.stop()

    def _request(self, method: str, path: str, payload: dict | None = None):
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"} if body else {}
        self.connection.request(method, path, body=body, headers=headers)
        response = self.connection.getresponse()
        data = response.read().decode("utf-8", "replace")
        parsed = json.loads(data) if data else None
        return response.status, parsed

    def test_plugin_approve_status_revoke_flow(self) -> None:
        # 注册插件（带权限声明）
        status, body = self._request(
            "POST",
            "/v1/plugins/register",
            {
                "manifest": {
                    "name": "helper",
                    "version": "1.0.0",
                    "capabilities": ["tool:run"],
                    "permissions": ["file:read"],
                }
            },
        )
        self.assertEqual(status, 200)
        # 未授权时 status 显示拒绝
        status, body = self._request("GET", "/v1/plugins/helper/status")
        self.assertEqual(status, 200)
        self.assertFalse(body["approvals"]["approved"])
        # 批准 file:read
        status, body = self._request("POST", "/v1/plugins/helper/approve", {"permissions": ["file:read"]})
        self.assertEqual(status, 200)
        self.assertTrue(body["approvals"]["approved"])
        # 未注册插件批准 → 404
        status, _ = self._request("POST", "/v1/plugins/nope/approve", {"permissions": ["file:read"]})
        self.assertEqual(status, 404)
        # 非法权限 → 400
        status, _ = self._request("POST", "/v1/plugins/helper/approve", {"permissions": ["BAD"]})
        self.assertEqual(status, 400)
        # 撤销
        status, body = self._request("DELETE", "/v1/plugins/helper/approvals")
        self.assertEqual(status, 200)
        self.assertFalse(body["approved"])

    def test_backend_registry_endpoints(self) -> None:
        status, body = self._request("GET", "/v1/model/backends")
        self.assertEqual(status, 200)
        self.assertEqual(body["backends"][0]["id"], "default")
        # 注册额外后端
        status, body = self._request(
            "POST",
            "/v1/model/backends/register",
            {"id": "backup", "backend": "placeholder"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["registered"]["id"], "backup")
        # 非法后端类型 → 400
        status, _ = self._request(
            "POST",
            "/v1/model/backends/register",
            {"id": "x", "backend": "magic"},
        )
        self.assertEqual(status, 400)

    def test_mobile_static_service(self) -> None:
        # /v1/mobile/ 返回 HTML（非 JSON），直接读原文验证
        self.connection.request("GET", "/v1/mobile/")
        response = self.connection.getresponse()
        html = response.read().decode("utf-8")
        self.assertEqual(response.status, 200)
        self.assertIn("text/html", response.getheader("Content-Type", ""))
        self.assertIn("墨灵", html)
        status, body = self._request("GET", "/v1/mobile/manifest.json")
        self.assertEqual(status, 200)
        self.assertEqual(body["short_name"], "墨灵")
        # 目录穿越拒绝
        status, _ = self._request("GET", "/v1/mobile/../../app.py")
        self.assertEqual(status, 400)
        # 未匹配扩展名拒绝
        status, _ = self._request("GET", "/v1/mobile/secret.txt")
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
