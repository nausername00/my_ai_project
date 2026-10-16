"""T3 轻量平台治理：成本账本（按后端分桶）、任务状态时间线、HTTP 端点冒烟。"""

import json
import os
import tempfile
import unittest
from http.client import HTTPConnection
from threading import Thread
from unittest.mock import patch

from app import create_server
from governance import CostLedger, task_status_timeline


class CostLedgerTest(unittest.TestCase):
    def test_record_and_snapshot(self) -> None:
        ledger = CostLedger()
        ledger.record("qwen2.5:3b", 120, 5000.0)
        ledger.record("qwen2.5:3b", 80, 3000.0)
        ledger.record("placeholder", 10, 1.0)
        snapshot = ledger.snapshot()
        self.assertEqual(snapshot["totals"]["count"], 3)
        self.assertEqual(snapshot["totals"]["chars"], 210)
        bucket = snapshot["backends"]["qwen2.5:3b"]
        self.assertEqual(bucket["count"], 2)
        self.assertEqual(bucket["avg_ms"], 4000.0)

    def test_negative_values_clamped(self) -> None:
        ledger = CostLedger()
        ledger.record("backend-a", -5, -1.0)
        snapshot = ledger.snapshot()
        self.assertEqual(snapshot["totals"]["chars"], 0)
        self.assertEqual(snapshot["totals"]["total_ms"], 0.0)

    def test_empty_snapshot(self) -> None:
        snapshot = CostLedger().snapshot()
        self.assertEqual(snapshot["totals"]["count"], 0)
        self.assertEqual(snapshot["backends"], {})

    def test_unknown_backend_normalized(self) -> None:
        ledger = CostLedger()
        ledger.record("  ", 1, 1.0)
        self.assertIn("unknown", ledger.snapshot()["backends"])


class TaskTimelineTest(unittest.TestCase):
    def test_aggregates_by_status(self) -> None:
        entries = [
            {"at": 1.0, "task": "mood_echo", "result_status": "ok", "authorization": "auto_local"},
            {"at": 2.0, "task": "safe_exec", "result_status": "blocked", "authorization": "denied"},
            {"at": 3.0, "task": "external_search", "result_status": "blocked"},
            {"at": 4.0, "task": "mix_audio", "result_status": "failed"},
        ]
        view = task_status_timeline(entries)
        self.assertEqual(view["total"], 4)
        self.assertEqual(view["by_status"]["ok"], 1)
        self.assertEqual(view["by_status"]["blocked"], 2)
        self.assertEqual(view["by_status"]["failed"], 1)
        self.assertEqual(view["recent"][0]["task"], "mix_audio")  # 最近在前

    def test_empty(self) -> None:
        view = task_status_timeline([])
        self.assertEqual(view["total"], 0)
        self.assertEqual(view["recent"], [])


class PlatformHttpSmokeTest(unittest.TestCase):
    """T3 HTTP 冒烟：GET /v1/status/platform。"""

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

    def test_platform_endpoint_shape(self) -> None:
        self.connection.request("GET", "/v1/status/platform")
        response = self.connection.getresponse()
        self.assertEqual(response.status, 200)
        body = json.loads(response.read())
        self.assertIn("tasks", body)
        self.assertIn("costs", body)
        self.assertIn("generations", body)
        self.assertIn("by_status", body["tasks"])
        self.assertIn("backends", body["costs"])


if __name__ == "__main__":
    unittest.main()
