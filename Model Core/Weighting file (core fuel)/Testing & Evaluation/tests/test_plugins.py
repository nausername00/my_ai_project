"""T6 插件 manifest 注册 + 基于成本账本的后端动态选型。"""

import json
import os
import tempfile
import unittest
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread
from unittest.mock import patch

from app import create_server
from plugins import PluginRegistry, choose_backend


class PluginRegistryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "plugins.json"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_register_and_list(self) -> None:
        registry = PluginRegistry(self.path)
        registry.register(
            {"name": "weather", "version": "1.0.0", "capabilities": ["external_search"]}
        )
        plugins = registry.list()
        self.assertEqual(len(plugins), 1)
        self.assertEqual(plugins[0]["name"], "weather")

    def test_duplicate_name_updates(self) -> None:
        registry = PluginRegistry(self.path)
        registry.register({"name": "a", "version": "1.0.0", "capabilities": ["x"]})
        registry.register({"name": "a", "version": "2.0.0", "capabilities": ["x", "y"]})
        plugins = registry.list()
        self.assertEqual(len(plugins), 1)
        self.assertEqual(plugins[0]["version"], "2.0.0")
        self.assertEqual(len(plugins[0]["capabilities"]), 2)

    def test_invalid_version_rejected(self) -> None:
        with self.assertRaises(ValueError):
            PluginRegistry(self.path).register(
                {"name": "a", "version": "two", "capabilities": ["x"]}
            )

    def test_empty_capabilities_rejected(self) -> None:
        with self.assertRaises(ValueError):
            PluginRegistry(self.path).register(
                {"name": "a", "version": "1.0.0", "capabilities": []}
            )

    def test_unknown_fields_rejected(self) -> None:
        with self.assertRaises(ValueError):
            PluginRegistry(self.path).register(
                {"name": "a", "version": "1.0.0", "capabilities": ["x"], "exec": "rm -rf"}
            )

    def test_missing_file_lists_empty(self) -> None:
        self.assertEqual(PluginRegistry(self.path).list(), [])


class ChooseBackendTest(unittest.TestCase):
    def _ledger(self) -> dict:
        return {
            "backends": {
                "qwen2.5:0.5b": {"count": 10, "chars": 100, "total_ms": 5000.0, "avg_ms": 500.0},
                "qwen2.5:3b": {"count": 5, "chars": 100, "total_ms": 15000.0, "avg_ms": 3000.0},
            },
            "totals": {"count": 15, "chars": 200, "total_ms": 20000.0},
        }

    def test_speed_picks_lowest_avg_ms(self) -> None:
        result = choose_backend(self._ledger(), prefer="speed")
        self.assertEqual(result["chosen"], "qwen2.5:0.5b")
        self.assertIn("speed", result["reason"])

    def test_quality_picks_most_frequent(self) -> None:
        result = choose_backend(self._ledger(), prefer="quality")
        self.assertEqual(result["chosen"], "qwen2.5:0.5b")
        self.assertIn("quality", result["reason"])

    def test_balance_uses_default(self) -> None:
        result = choose_backend(self._ledger(), prefer="balance", default="qwen2.5:3b")
        self.assertEqual(result["chosen"], "qwen2.5:3b")

    def test_empty_ledger_falls_back(self) -> None:
        result = choose_backend({"backends": {}}, prefer="speed", default="local")
        self.assertEqual(result["chosen"], "local")

    def test_invalid_prefer_normalized(self) -> None:
        result = choose_backend(self._ledger(), prefer="magic")
        self.assertEqual(result["prefer"], "balance")


class PluginsHttpSmokeTest(unittest.TestCase):
    """T6 HTTP 冒烟：插件注册/列表 + 动态选型端点。"""

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
                "PLUGIN_REGISTRY_PATH": os.path.join(self.temp_dir.name, "plugins.json"),
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

    def _post(self, path: str, payload: dict) -> tuple[int, dict]:
        self.connection.request(
            "POST", path, body=json.dumps(payload), headers={"Content-Type": "application/json"}
        )
        response = self.connection.getresponse()
        return response.status, json.loads(response.read())

    def test_plugins_list_empty(self) -> None:
        self.connection.request("GET", "/v1/plugins")
        response = self.connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(response.read())["plugins"], [])

    def test_register_plugin(self) -> None:
        status, body = self._post(
            "/v1/plugins/register",
            {"manifest": {"name": "translate", "version": "1.0.0", "capabilities": ["ocr_text"]}},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["registered"]["name"], "translate")
        self.assertEqual(len(body["plugins"]), 1)

    def test_register_invalid_rejected(self) -> None:
        status, body = self._post(
            "/v1/plugins/register",
            {"manifest": {"name": "bad", "version": "x", "capabilities": ["y"]}},
        )
        self.assertEqual(status, 400)
        self.assertIn("error", body)

    def test_model_choose_endpoint(self) -> None:
        self.connection.request("GET", "/v1/model/choose?task=chat&prefer=balance")
        response = self.connection.getresponse()
        self.assertEqual(response.status, 200)
        body = json.loads(response.read())
        self.assertIn("chosen", body)
        self.assertEqual(body["prefer"], "balance")

    def test_model_choose_invalid_prefer_falls_back(self) -> None:
        self.connection.request("GET", "/v1/model/choose?prefer=magic")
        response = self.connection.getresponse()
        self.assertEqual(response.status, 200)
        body = json.loads(response.read())
        self.assertEqual(body["prefer"], "balance")


if __name__ == "__main__":
    unittest.main()
