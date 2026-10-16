"""S6 三角协作（冰/火/平衡）：思维角色、审校解析、确定性裁决、回路编排。
T1 三角唤醒入口：HTTP 端点冒烟（trio-roles / trio）。"""

import json
import os
import tempfile
import unittest
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread
from unittest.mock import patch

from app import create_server
from avatar_persona import PersonaRegistry
from avatar_trio import (
    _decide,
    _parse_review,
    list_trio_roles,
    run_trio,
)
from inference import InferenceEngine


class _StubEngine:
    """只读 backend/endpoint/model_name 的桩，让 is_local_engine 判定为本机。"""

    model_name = "stub"
    backend = type("B", (), {"endpoint": "http://127.0.0.1:11434"})()


class ThinkingRolesTest(unittest.TestCase):
    """三角角色定义与 persona 的 thinking_mode 维度。"""

    def test_list_trio_roles_has_three_modes(self) -> None:
        roles = list_trio_roles()
        self.assertEqual(len(roles), 3)
        modes = {role["mode"] for role in roles}
        self.assertEqual(modes, {"fire", "ice", "balance"})

    def test_thinking_personas_seed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = PersonaRegistry(Path(directory) / "personas.json")
            roles = {role["avatar_id"]: role for role in registry.list_thinking_roles()}
            self.assertIn("fire_breakthrough", roles)
            self.assertIn("ice_guardian", roles)
            self.assertIn("balance_mediator", roles)
            # 思维角色的 behavior.thinking_mode 与角色一致
            fire = registry.behavior_of("fire_breakthrough")
            self.assertEqual(fire["thinking_mode"], "fire")
            ice = registry.behavior_of("ice_guardian")
            self.assertEqual(ice["thinking_mode"], "ice")
            balance = registry.behavior_of("balance_mediator")
            self.assertEqual(balance["thinking_mode"], "balance")

    def test_invalid_thinking_mode_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = PersonaRegistry(Path(directory) / "personas.json")
            persona = {
                "avatar_id": "x",
                "name": "X",
                "situations": {"greeting": "你好"},
                "behavior": {"thinking_mode": "chaos"},
            }
            with self.assertRaises(ValueError):
                registry.upsert(persona)


class ParseReviewTest(unittest.TestCase):
    """冰的审校解析：JSON / 关键字 / 容错。"""

    def test_parses_json(self) -> None:
        review = _parse_review(
            '{"verdict":"revise","issues":["缺少边界说明"],"suggestions":["补上权限范围"]}'
        )
        self.assertEqual(review["verdict"], "revise")
        self.assertIn("缺少边界说明", review["issues"])
        self.assertIn("补上权限范围", review["suggestions"])

    def test_parses_keyword_when_not_json(self) -> None:
        review = _parse_review("校验结论：reject。问题：结构混乱，证据不足。")
        self.assertEqual(review["verdict"], "reject")

    def test_unknown_when_unparseable(self) -> None:
        review = _parse_review("今天天气不错。")
        self.assertEqual(review["verdict"], "unknown")
        self.assertEqual(review["issues"], [])


class DecideTest(unittest.TestCase):
    """平衡裁决：adopt / patch / rework / defer 四条路径（不靠多数票）。"""

    def test_accept_adopts_fire(self) -> None:
        review = {"verdict": "accept", "issues": [], "suggestions": []}
        decision = _decide("任务", "火方案", review, rounds_used=1, max_rounds=2)
        self.assertEqual(decision["action"], "adopt")
        self.assertIn("火方案", decision["final"])

    def test_revise_patches_fire_with_ice_fixes(self) -> None:
        review = {
            "verdict": "revise",
            "issues": ["缺边界"],
            "suggestions": ["补上权限范围"],
        }
        decision = _decide("任务", "火方案", review, rounds_used=1, max_rounds=2)
        self.assertEqual(decision["action"], "patch")
        self.assertIn("火方案", decision["final"])
        self.assertIn("补上权限范围", decision["final"])

    def test_reject_within_limit_returns_rework(self) -> None:
        review = {"verdict": "reject", "issues": ["致命缺陷"], "suggestions": []}
        decision = _decide("任务", "火方案", review, rounds_used=1, max_rounds=2)
        self.assertEqual(decision["action"], "rework")
        self.assertEqual(decision["final"], "")

    def test_reject_at_limit_defers_to_moling(self) -> None:
        review = {"verdict": "reject", "issues": ["依旧不过"], "suggestions": []}
        decision = _decide("任务", "火方案", review, rounds_used=2, max_rounds=2)
        self.assertEqual(decision["action"], "defer")

    def test_unknown_defers_conservatively(self) -> None:
        review = {"verdict": "unknown", "issues": [], "suggestions": []}
        decision = _decide("任务", "火方案", review, rounds_used=1, max_rounds=2)
        self.assertEqual(decision["action"], "defer")
        self.assertIn("回退", decision["reason"])


class RunTrioTest(unittest.TestCase):
    """回路编排：注入 stub 回调，验证 adopt / rework 后 defer 全链路。"""

    def _engine(self) -> InferenceEngine:
        return _StubEngine()  # type: ignore[return-value]

    def test_adopt_round(self) -> None:
        result = run_trio(
            self._engine(),
            "你是墨灵。",
            "给周日安排一个放松方案",
            fire=lambda task: "去海边散步、放轻音乐、读一本漫画。",
            ice=lambda task, fire: '{"verdict":"accept","issues":[],"suggestions":[]}',
        )
        self.assertEqual(result["rounds_used"], 1)
        self.assertEqual(result["decision"]["action"], "adopt")
        self.assertIn("海边散步", result["decision"]["final"])
        self.assertEqual(result["lead"], "moling")
        self.assertEqual(result["source"], "local")

    def test_rework_then_defer(self) -> None:
        calls = {"fire": 0}
        engine = self._engine()

        def fire(task: str) -> str:
            calls["fire"] += 1
            return "创意方案 A"

        result = run_trio(
            engine,
            "你是墨灵。",
            "设计一个高风险自动化方案",
            fire=fire,
            ice=lambda task, fire_output: '{"verdict":"reject","issues":["越界"],"suggestions":[]}',
            max_rounds=2,
        )
        # 两轮重做后仍被打回 → defer 给主墨灵
        self.assertEqual(calls["fire"], 2)
        self.assertEqual(result["rounds_used"], 2)
        self.assertEqual(result["decision"]["action"], "defer")
        self.assertEqual(len(result["rounds"]), 4)  # fire/ice × 2

    def test_rejects_remote_engine(self) -> None:
        remote = type(
            "Remote",
            (),
            {"model_name": "r", "backend": type("B", (), {"endpoint": "https://x"})()},
        )()
        with self.assertRaises(ValueError):
            run_trio(remote, "你是墨灵。", "任务")  # type: ignore[arg-type]


class TrioHttpSmokeTest(unittest.TestCase):
    """T1 HTTP 端点冒烟：trio-roles 清单与 trio 协作（placeholder 后端）。"""

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

    def _get(self, path: str) -> tuple[int, dict]:
        self.connection.request("GET", path)
        response = self.connection.getresponse()
        return response.status, json.loads(response.read())

    def _post(self, path: str, payload: dict) -> tuple[int, dict]:
        self.connection.request(
            "POST",
            path,
            json.dumps(payload),
            {"Content-Type": "application/json"},
        )
        response = self.connection.getresponse()
        return response.status, json.loads(response.read())

    def test_trio_roles_list(self) -> None:
        status, body = self._get("/v1/avatars/trio-roles")
        self.assertEqual(status, 200)
        roles = body["roles"]
        self.assertEqual(len(roles), 3)
        self.assertEqual({role["mode"] for role in roles}, {"fire", "ice", "balance"})

    def test_trio_run_returns_decision(self) -> None:
        status, body = self._post(
            "/v1/avatars/trio",
            {"message": "给周日安排一个放松计划"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["lead"], "moling")
        self.assertIn(body["decision"]["action"], ("adopt", "patch", "rework", "defer"))
        self.assertTrue(body["rounds"])

    def test_trio_rejects_empty_message(self) -> None:
        status, body = self._post("/v1/avatars/trio", {"message": "  "})
        self.assertEqual(status, 400)
        self.assertIn("message", body["error"])

    def test_trio_rejects_bad_max_rounds(self) -> None:
        status, body = self._post(
            "/v1/avatars/trio",
            {"message": "任务", "max_rounds": 5},
        )
        self.assertEqual(status, 400)
        self.assertIn("max_rounds", body["error"])

    def test_trio_rejects_unknown_field(self) -> None:
        status, body = self._post(
            "/v1/avatars/trio",
            {"message": "任务", "magic": True},
        )
        self.assertEqual(status, 400)
        self.assertIn("不支持的字段", body["error"])


if __name__ == "__main__":
    unittest.main()
