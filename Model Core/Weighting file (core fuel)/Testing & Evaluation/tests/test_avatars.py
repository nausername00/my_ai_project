"""S1: 墨灵分身底座验收测试。

覆盖：
- 预置四分身（陪伴/学习/创作/技术）创建与持久化；
- 睡眠 / 唤醒状态机：唤醒恢复活跃、睡眠保留断点、睡眠不占推理资源（active_count）；
- 阈值判断：简单任务主墨灵直做，复杂 / 跨领域任务建议唤醒并给出对应分身；
- 唤醒确认流程：确认后唤醒、未确认保持睡眠（用户主权），记录可追溯；
- 自定义分身创建与能力清单更新。
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread
from unittest.mock import patch

from app import create_server
from avatars import (
    AvatarRegistry,
    AvatarSystem,
    ThresholdRouter,
    DEFAULT_AVATARS,
)


def make_system() -> AvatarSystem:
    tmp = tempfile.mkdtemp(prefix="moling_avatars_")
    return AvatarSystem(
        registry_path=Path(tmp) / "avatars.json",
        awaken_log_path=Path(tmp) / "awaken_log.json",
    )


class AvatarRegistryS1Test(unittest.TestCase):
    def test_seeds_four_default_avatars(self) -> None:
        system = make_system()
        avatars = system.registry.list()
        self.assertEqual(
            [a.avatar_id for a in avatars],
            ["companion", "creation", "learning", "tech"],
        )
        self.assertTrue(all(a.status == "sleeping" for a in avatars))
        self.assertEqual(system.registry.active_count(), 0)

    def test_state_persists_across_reload(self) -> None:
        tmp = tempfile.mkdtemp(prefix="moling_avatars_")
        registry = AvatarRegistry(Path(tmp) / "avatars.json")
        registry.wake("learning", breakpoint={"task": "整理 K 系列文档"})
        reloaded = AvatarRegistry(Path(tmp) / "avatars.json")
        profile = reloaded.get("learning")
        self.assertIsNotNone(profile)
        self.assertEqual(profile.status, "active")  # type: ignore[union-attr]
        self.assertEqual(
            profile.breakpoint.get("task"), "整理 K 系列文档"  # type: ignore[union-attr]
        )

    def test_wake_and_sleep_state_machine(self) -> None:
        system = make_system()
        system.registry.wake("creation")
        self.assertEqual(system.registry.active_count(), 1)
        system.registry.sleep("creation", breakpoint={"scene": "分镜 3"})
        profile = system.registry.get("creation")
        self.assertEqual(profile.status, "sleeping")  # type: ignore[union-attr]
        self.assertEqual(profile.breakpoint.get("scene"), "分镜 3")  # type: ignore[union-attr]
        self.assertEqual(system.registry.active_count(), 0)

    def test_wake_unknown_avatar_raises(self) -> None:
        system = make_system()
        with self.assertRaises(KeyError):
            system.registry.wake("not-exist")

    def test_create_custom_avatar(self) -> None:
        system = make_system()
        profile = system.registry.create(
            name="调研小灵",
            domain="research",
            description="深度资料调研",
            capabilities=["search", "cite"],
        )
        self.assertTrue(profile.avatar_id.startswith("research-"))
        self.assertEqual(profile.status, "sleeping")
        self.assertEqual(system.registry.get(profile.avatar_id).name, "调研小灵")  # type: ignore[union-attr]

    def test_update_capabilities(self) -> None:
        system = make_system()
        profile = system.registry.update_capabilities("tech", ["code", "debug"])
        self.assertEqual(profile.capabilities, ["code", "debug"])


class ThresholdRouterS1Test(unittest.TestCase):
    def test_direct_casual_message(self) -> None:
        router = ThresholdRouter()
        result = router.assess("你好呀，今天过得怎么样")
        self.assertEqual(result["decision"], "direct")

    def test_complex_task_suggests_ask(self) -> None:
        router = ThresholdRouter()
        result = router.assess(
            "帮我研究一下怎么给墨灵做视频，同时还要写文案和跑渲染"
        )
        self.assertEqual(result["decision"], "ask")
        # 学习(研究/资料) + 创作(视频/文案) + 技术(渲染) → 跨领域
        self.assertIn("learning", result["suggested_avatars"])
        self.assertIn("creation", result["suggested_avatars"])

    def test_single_domain_long_task_direct(self) -> None:
        router = ThresholdRouter()
        result = router.assess("把这段代码改成用 python 重写")
        self.assertEqual(result["decision"], "direct")

    def test_long_message_falls_back_to_ask(self) -> None:
        router = ThresholdRouter()
        result = router.assess("我想请你从头到尾帮我梳理一下整个项目的现状" + "。" * 60)
        self.assertEqual(result["decision"], "ask")

    def test_disabled_threshold_returns_direct(self) -> None:
        router = ThresholdRouter()
        router.update_settings({"enabled": False})
        result = router.assess("帮我研究一个完整方案同时写代码")
        self.assertEqual(result["decision"], "direct")
        self.assertIn("停用", result["reason"])

    def test_explicit_suggested_avatars(self) -> None:
        router = ThresholdRouter()
        result = router.assess("随便聊聊", suggested=["companion"])
        self.assertEqual(result["decision"], "direct")
        self.assertEqual(result["suggested_avatars"], ["companion"])


class AwakenFlowS1Test(unittest.TestCase):
    def test_confirm_wakes_avatar(self) -> None:
        system = make_system()
        entry = system.confirm_awaken(
            avatar_ids=["learning"], confirmed=True, reason="用户确认唤醒"
        )
        self.assertTrue(entry["confirmed"])
        self.assertEqual(system.registry.get("learning").status, "active")  # type: ignore[union-attr]

    def test_decline_keeps_sleeping(self) -> None:
        system = make_system()
        entry = system.confirm_awaken(
            avatar_ids=["creation", "tech"], confirmed=False, reason="用户暂不需要"
        )
        self.assertFalse(entry["confirmed"])
        self.assertEqual(system.registry.get("creation").status, "sleeping")  # type: ignore[union-attr]
        self.assertEqual(system.registry.get("tech").status, "sleeping")  # type: ignore[union-attr]
        self.assertEqual(system.registry.active_count(), 0)

    def test_awaken_log_is_traceable(self) -> None:
        system = make_system()
        system.awaken_log.record(["learning"], confirmed=True, reason="A")
        system.awaken_log.record(["creation"], confirmed=False, reason="B")
        entries = system.awaken_log.list()
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[-1]["avatar_ids"], ["creation"])

    def test_assess_reports_active_avatars(self) -> None:
        system = make_system()
        system.registry.wake("companion")
        result = system.assess("帮我查一份资料")
        self.assertEqual(result["decision"], "direct")
        self.assertIn("companion", result["active_avatars"])


class DefaultAvatarCatalogTest(unittest.TestCase):
    def test_catalog_defines_four_domains(self) -> None:
        domains = {a["domain"] for a in DEFAULT_AVATARS}
        self.assertEqual(domains, {"companion", "learning", "creation", "tech"})


class AvatarApiS1Test(unittest.TestCase):
    """真实 HTTP 端点冒烟（create_server + placeholder 后端）。"""

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

    def test_get_avatars_lists_four_defaults(self) -> None:
        status, payload = self._get("/v1/avatars")
        self.assertEqual(status, 200)
        ids = {a["id"] for a in payload["avatars"]}
        # 默认四分身必须存在；自定义分身测试先于本方法时总数可能 >4
        self.assertTrue({"companion", "learning", "creation", "tech"} <= ids)
        self.assertEqual(payload["active_count"], 0)

    def test_assess_complex_task_suggests_ask(self) -> None:
        status, payload = self._post(
            "/v1/avatars/assess",
            {"message": "帮我研究墨灵视频方案，同时写文案还要跑渲染"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["decision"], "ask")
        self.assertIn("learning", payload["suggested_avatars"])
        self.assertIn("creation", payload["suggested_avatars"])
        self.assertIn("tech", payload["suggested_avatars"])

    def test_assess_simple_task_direct(self) -> None:
        status, payload = self._post(
            "/v1/avatars/assess", {"message": "你好呀"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["decision"], "direct")

    def test_awaken_confirmed_wakes_avatar(self) -> None:
        status, payload = self._post(
            "/v1/avatars/awaken",
            {"avatar_ids": ["learning"], "confirmed": True, "reason": "冒烟确认"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["entry"]["confirmed"])
        _, status_payload = self._get("/v1/avatars")
        learning = next(
            a for a in status_payload["avatars"] if a["id"] == "learning"
        )
        self.assertEqual(learning["status"], "active")

    def test_awaken_declined_keeps_sleeping(self) -> None:
        status, payload = self._post(
            "/v1/avatars/awaken",
            {"avatar_ids": ["tech"], "confirmed": False, "reason": "冒烟拒绝"},
        )
        self.assertEqual(status, 200)
        self.assertFalse(payload["entry"]["confirmed"])
        _, status_payload = self._get("/v1/avatars")
        tech = next(a for a in status_payload["avatars"] if a["id"] == "tech")
        self.assertEqual(tech["status"], "sleeping")

    def test_create_custom_avatar_endpoint(self) -> None:
        status, payload = self._post(
            "/v1/avatars/create",
            {
                "name": "调研小灵",
                "domain": "research",
                "description": "深度资料调研",
                "capabilities": ["search", "cite"],
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["avatar"]["id"].startswith("research-"))
        self.assertEqual(payload["avatar"]["name"], "调研小灵")

    def test_sleep_endpoint(self) -> None:
        self._post("/v1/avatars/awaken", {"avatar_ids": ["creation"], "confirmed": True})
        status, payload = self._post(
            "/v1/avatars/sleep", {"id": "creation", "breakpoint": {"scene": "分镜 5"}}
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["avatar"]["status"], "sleeping")
        self.assertEqual(payload["avatar"]["breakpoint"]["scene"], "分镜 5")

    def test_threshold_settings_update(self) -> None:
        status, payload = self._post(
            "/v1/avatars/threshold", {"enabled": False}
        )
        self.assertEqual(status, 200)
        self.assertFalse(payload["threshold"]["enabled"])


class AvatarTasksS2Test(unittest.TestCase):
    """S2：分身领域能力（可复现任务）+ 工具授权痕迹 + 能力清单可配置。"""

    def setUp(self) -> None:
        self.system = make_system()

    def test_companion_mood_echo(self) -> None:
        result = self.system.run_task(
            "companion", "mood_echo", {"text": "今天有点难过"}
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["result"]["mood"], "难过")
        self.assertIn("我在", result["result"]["echo"])

    def test_learning_local_retrieve(self) -> None:
        docs = (
            Path(__file__).resolve().parents[2] / "Docs & Compliance"
        )
        result = self.system.run_task(
            "learning",
            "local_retrieve",
            {"query": "分身", "scope_dir": str(docs)},
        )
        self.assertEqual(result["status"], "ok")
        self.assertGreaterEqual(result["result"]["hit_files"], 1)
        snippets = [
            m["snippet"]
            for hit in result["result"]["hits"]
            for m in hit["matches"]
        ]
        self.assertTrue(any("分身" in s for s in snippets))

    def test_creation_script_draft(self) -> None:
        result = self.system.run_task(
            "creation", "script_draft", {"topic": "时间管理", "style": "讲解"}
        )
        self.assertEqual(result["status"], "ok")
        self.assertIn("时间管理", result["result"]["script"]["opening"])
        self.assertEqual(result["result"]["script"]["closing"], "总结一下：时间管理，记住最核心的一点就够了。下次见～")

    def test_tech_safe_exec_calculation(self) -> None:
        result = self.system.run_task(
            "tech",
            "safe_exec",
            {"command": "python", "args": "-c print(1+1)"},
            approved=True,
        )
        self.assertEqual(result["status"], "ok")
        self.assertIn("2", result["result"]["stdout"])

    def test_tech_rejects_dangerous_command(self) -> None:
        result = self.system.run_task(
            "tech",
            "safe_exec",
            {"command": "python", "args": "-c 'import os'"},
            approved=True,
        )
        self.assertEqual(result["status"], "failed")
        self.assertIn("危险", result["reason"])

    def test_task_outside_domain_denied(self) -> None:
        result = self.system.run_task(
            "companion", "safe_exec", {"command": "python", "args": "-c 1+1"}
        )
        self.assertEqual(result["status"], "denied")
        self.assertIn("不属于分身领域", result["reason"])
        entries = self.system.tool_log_list()
        self.assertEqual(entries[-1]["decision"], "denied")
        self.assertEqual(entries[-1]["result_status"], "blocked")

    def test_unapproved_approval_task_denied(self) -> None:
        # safe_exec 需要审批；未批准 → 拒绝并留下痕迹
        result = self.system.run_task(
            "tech", "safe_exec", {"command": "python", "args": "-c 1+1"}
        )
        self.assertEqual(result["status"], "denied")
        self.assertEqual(result["authorization"], "denied")
        entries = self.system.tool_log_list()
        self.assertEqual(entries[-1]["authorization"], "denied")

    def test_approved_task_runs_and_traces(self) -> None:
        result = self.system.run_task(
            "tech",
            "safe_exec",
            {"command": "python", "args": "-c print(2*3)"},
            approved=True,
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["authorization"], "approved")
        entries = self.system.tool_log_list()
        self.assertEqual(entries[-1]["authorization"], "approved")
        self.assertEqual(entries[-1]["result_status"], "ok")

    def test_unknown_task_denied(self) -> None:
        result = self.system.run_task("learning", "not_a_task", {})
        self.assertEqual(result["status"], "denied")
        self.assertIn("未登记", result["reason"])

    def test_external_operation_denied_by_default(self) -> None:
        result = self.system.run_task(
            "learning", "external_search", {"query": "anything"}
        )
        self.assertEqual(result["status"], "denied")
        self.assertIn("外部操作默认拒绝", result["reason"])

    def test_capabilities_add_and_remove(self) -> None:
        profile = self.system.update_capabilities(
            "tech", mode="add", capability="network_audit"
        )
        self.assertIn("network_audit", profile.capabilities)
        profile = self.system.update_capabilities(
            "tech", mode="remove", capability="network_audit"
        )
        self.assertNotIn("network_audit", profile.capabilities)
        # 持久化：重建系统后能力清单仍在
        reloaded = AvatarRegistry(self.system.registry._path)
        self.assertIn("code", reloaded.get("tech").capabilities)  # type: ignore[union-attr]

    def test_capabilities_set_overwrites(self) -> None:
        profile = self.system.update_capabilities(
            "learning", mode="set", capabilities=["deep_dive"]
        )
        self.assertEqual(profile.capabilities, ["deep_dive"])

    def test_tool_log_is_traceable(self) -> None:
        self.system.run_task("creation", "script_draft", {"topic": "演示"})
        self.system.run_task("tech", "safe_exec", {"command": "python", "args": "-c 1"})
        entries = self.system.tool_log_list()
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["avatar_id"], "creation")
        self.assertEqual(entries[0]["task"], "script_draft")
        self.assertEqual(entries[0]["authorization"], "auto_local")
        self.assertEqual(entries[0]["result_status"], "ok")
        self.assertIn("at", entries[0])


class AvatarApiS2Test(unittest.TestCase):
    """S2 HTTP 端点冒烟：task / capabilities / tool-log。"""

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

    def test_task_endpoint_learning(self) -> None:
        status, payload = self._post(
            "/v1/avatars/task",
            {
                "avatar_id": "learning",
                "task": "local_retrieve",
                "payload": {
                    "query": "分身",
                    "scope_dir": str(Path(__file__).resolve().parents[1]),
                },
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")

    def test_task_endpoint_unapproved_denied(self) -> None:
        status, payload = self._post(
            "/v1/avatars/task",
            {
                "avatar_id": "tech",
                "task": "safe_exec",
                "payload": {"command": "python", "args": "-c 1+1"},
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "denied")
        self.assertEqual(payload["authorization"], "denied")

    def test_task_endpoint_approved_runs(self) -> None:
        status, payload = self._post(
            "/v1/avatars/task",
            {
                "avatar_id": "tech",
                "task": "safe_exec",
                "payload": {"command": "python", "args": "-c print(2+2)"},
                "approved": True,
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["result"]["stdout"].strip(), "4")

    def test_capabilities_endpoint(self) -> None:
        status, payload = self._post(
            "/v1/avatars/capabilities",
            {"avatar_id": "creation", "mode": "add", "capability": "storyboard"},
        )
        self.assertEqual(status, 200)
        self.assertIn("storyboard", payload["profile"]["capabilities"])

    def test_tool_log_endpoint(self) -> None:
        self._post(
            "/v1/avatars/task",
            {"avatar_id": "creation", "task": "script_draft", "payload": {"topic": "冒烟"}},
        )
        status, payload = self._get("/v1/avatars/tool-log")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(len(payload["entries"]), 1)
        self.assertEqual(payload["entries"][-1]["task"], "script_draft")


if __name__ == "__main__":
    unittest.main()
