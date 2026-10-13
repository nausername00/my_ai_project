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
from avatar_advice import AvatarShortMemory
from avatar_media import CaptionTimelineStore
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


class FakeMemoryStore:
    """最小主记忆替身：记录来源、可删除（验证主权唯一与可撤销）。"""

    def __init__(self) -> None:
        self._entries: dict[str, dict] = {}

    def add_memory(
        self,
        content: str,
        source: str = "user",
        visibility: str = "model",
        reason: str | None = None,
    ) -> dict:
        entry = {
            "id": f"mem-{len(self._entries) + 1}",
            "content": content,
            "source": source,
            "visibility": visibility,
            "reason": reason,
            "created_at": "2026-10-14T00:00:00",
            "status": "active",
        }
        self._entries[entry["id"]] = entry
        return dict(entry)

    def delete_memory(self, memory_id: str) -> None:
        if memory_id not in self._entries:
            raise LookupError(f"memory not found: {memory_id}")
        del self._entries[memory_id]

    def list_memories(self) -> list[dict]:
        return list(self._entries.values())


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


class AvatarCollabS3Test(unittest.TestCase):
    """S3：跨领域协作（拆解 / 去重 / 并行）+ 成果回写（来源 / 撤销 / 主权唯一）。"""

    def setUp(self) -> None:
        tmp = tempfile.mkdtemp(prefix="moling_avatars_s3_")
        self.store = FakeMemoryStore()
        self.system = AvatarSystem(
            registry_path=Path(tmp) / "avatars.json",
            awaken_log_path=Path(tmp) / "awaken_log.json",
            character_store=self.store,
        )

    def test_plan_identifies_cross_domain(self) -> None:
        plan = self.system.plan_task("做一期讲解视频：查资料、写脚本、跑渲染")
        domains = plan["domains"]
        self.assertIn("learning", domains)
        self.assertIn("creation", domains)
        self.assertIn("tech", domains)
        # 同领域去重：每个领域至多一个子任务
        task_ids = [t["avatar_id"] for t in plan["tasks"]]
        self.assertEqual(len(task_ids), len(set(task_ids)))

    def test_plan_same_domain_dedup(self) -> None:
        plan = self.system.plan_task("查资料、再查资料、整理归纳")
        self.assertEqual(plan["domains"], ["learning"])

    def test_plan_empty_message(self) -> None:
        plan = self.system.plan_task("")
        self.assertEqual(plan["tasks"], [])

    def test_execute_collaboration(self) -> None:
        execution = self.system.execute_plan(
            "做一期讲解视频：查资料写脚本", approved=True
        )
        self.assertEqual(execution["status"], "ok")
        task_status = {t["domain"]: t["status"] for t in execution["tasks"]}
        self.assertEqual(task_status.get("learning"), "ok")
        self.assertEqual(task_status.get("creation"), "ok")
        self.assertIn("learning", execution["active_avatars"])
        self.assertIn("creation", execution["active_avatars"])

    def test_execute_tech_needs_input(self) -> None:
        execution = self.system.execute_plan("帮我写代码跑渲染", approved=True)
        tech = next(t for t in execution["tasks"] if t["domain"] == "tech")
        self.assertEqual(tech["status"], "pending")
        self.assertIn("具体命令", tech["reason"])

    def test_execute_records_wake_confirmation(self) -> None:
        self.system.execute_plan("查资料整理一份总结", approved=True)
        entries = self.system.awaken_log.list()
        self.assertTrue(entries)
        self.assertTrue(entries[-1]["confirmed"])
        self.assertIn("learning", entries[-1]["avatar_ids"])

    def test_writeback_requires_approval(self) -> None:
        result = self.system.writeback(
            "creation", "脚本已生成", approved=False
        )
        self.assertEqual(result["status"], "denied")
        self.assertIn("主权唯一", result["reason"])
        self.assertEqual(self.store.list_memories(), [])

    def test_writeback_approved_with_source(self) -> None:
        result = self.system.writeback(
            "creation", "脚本已生成", approved=True, reason="S3 演示"
        )
        self.assertEqual(result["status"], "ok")
        memory = result["memory"]
        self.assertEqual(memory["source"], "avatar:creation")
        self.assertEqual(memory["content"], "脚本已生成")
        stored = self.store.list_memories()
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["id"], memory["id"])

    def test_writeback_revocable(self) -> None:
        result = self.system.writeback(
            "learning", "资料要点", approved=True
        )
        memory_id = result["memory"]["id"]
        self.store.delete_memory(memory_id)
        self.assertEqual(self.store.list_memories(), [])

    def test_parallel_writeback_no_overwrite(self) -> None:
        # 多条回写各自独立（主权唯一：不互相覆盖）
        first = self.system.writeback("learning", "要点 A", approved=True)
        second = self.system.writeback("creation", "脚本 B", approved=True)
        self.assertNotEqual(first["memory"]["id"], second["memory"]["id"])
        entries = self.store.list_memories()
        self.assertEqual(len(entries), 2)

    def test_execute_with_writeback(self) -> None:
        execution = self.system.execute_plan(
            "做一期讲解视频：查资料写脚本", approved=True, writeback=True
        )
        self.assertEqual(execution["status"], "ok")
        self.assertIn("writeback", execution)
        self.assertEqual(execution["writeback"]["status"], "ok")
        memory = execution["writeback"]["memory"]
        self.assertEqual(memory["source"], "avatar:main")
        self.assertEqual(len(self.store.list_memories()), 1)


class AvatarApiS3Test(unittest.TestCase):
    """S3 HTTP 端点冒烟：plan / execute / writeback。"""

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

    def _post(self, path: str, payload: dict) -> tuple[int, dict]:
        self.connection.request(
            "POST",
            path,
            json.dumps(payload),
            {"Content-Type": "application/json"},
        )
        response = self.connection.getresponse()
        return response.status, json.loads(response.read())

    def test_plan_endpoint(self) -> None:
        status, payload = self._post(
            "/v1/avatars/plan",
            {"message": "做一期讲解视频：查资料写脚本"},
        )
        self.assertEqual(status, 200)
        domains = payload["plan"]["domains"]
        self.assertIn("learning", domains)
        self.assertIn("creation", domains)

    def test_execute_endpoint(self) -> None:
        status, payload = self._post(
            "/v1/avatars/execute",
            {"message": "做一期讲解视频：查资料写脚本", "approved": True},
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["execution"]["status"], "ok")

    def test_writeback_endpoint_unapproved_denied(self) -> None:
        status, payload = self._post(
            "/v1/avatars/writeback",
            {"avatar_id": "creation", "content": "脚本", "approved": False},
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "denied")

    def test_writeback_endpoint_approved(self) -> None:
        status, payload = self._post(
            "/v1/avatars/writeback",
            {"avatar_id": "creation", "content": "脚本已生成", "approved": True},
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["memory"]["source"], "avatar:creation")


class AvatarEvolutionS4Test(unittest.TestCase):
    """S4：技能沉淀（K 系列能力卡 + 被分身调用）+ 自省回路（策略调整可应用 / 可撤销）。"""

    def setUp(self) -> None:
        tmp = tempfile.mkdtemp(prefix="moling_avatars_s4_")
        self.store = FakeMemoryStore()
        self.system = AvatarSystem(
            registry_path=Path(tmp) / "avatars.json",
            awaken_log_path=Path(tmp) / "awaken_log.json",
            character_store=self.store,
        )

    def test_k_series_skill_cards_present(self) -> None:
        skills = self.system.skill_list()
        ids = {s["id"] for s in skills}
        self.assertTrue(
            {"live2d_render", "portrait_draft", "video_timeline"} <= ids
        )
        self.assertTrue(
            {"document_retrieve", "script_draft", "mood_echo"} <= ids
        )

    def test_skill_card_has_source(self) -> None:
        card = self.system.skills.get("live2d_render")
        self.assertIsNotNone(card)
        self.assertEqual(card["source"], "K6")  # type: ignore[union-attr]
        self.assertEqual(card["status"], "available")

    def test_skill_card_invoked_by_avatar(self) -> None:
        # 技能卡被分身实际调用：script_draft 卡绑定创作分身任务并真实执行
        card = self.system.skill_for_task("script_draft")
        self.assertIsNotNone(card)
        self.assertEqual(card["invoke"], "script_draft")  # type: ignore[union-attr]
        result = self.system.run_task(
            "creation", "script_draft", {"topic": "演示"}
        )
        self.assertEqual(result["status"], "ok")
        # tool_log 中留下调用痕迹（skill → task 绑定可追溯）
        entries = self.system.tool_log_list()
        self.assertEqual(entries[-1]["task"], "script_draft")

    def test_register_skill_card(self) -> None:
        card = self.system.register_skill(
            {
                "id": "ffmpeg_mix",
                "name": "人声优先混音",
                "description": "背景音乐不盖人声（K6 待办）",
                "capability": "video_script",
                "invoke": None,
                "source": "K6",
            }
        )
        self.assertEqual(card["status"], "available")
        self.assertEqual(card["source"], "K6")
        # 重复登记拒绝
        with self.assertRaises(ValueError):
            self.system.register_skill(
                {"id": "ffmpeg_mix", "name": "重复", "capability": "x"}
            )

    def test_introspection_stats(self) -> None:
        self.system.run_task("creation", "script_draft", {"topic": "A"})
        self.system.run_task("creation", "script_draft", {"topic": "B"})
        self.system.run_task("tech", "safe_exec", {"command": "python", "args": "-c 1"})
        report = self.system.introspect()
        stats = report["stats"]
        self.assertEqual(stats["tool_total"], 3)
        self.assertEqual(stats["ok"], 2)
        self.assertEqual(stats["denied"], 1)
        self.assertIn("需要审批的操作未获用户批准", stats["denied_reasons"])

    def test_introspection_adjustment_applied(self) -> None:
        # 构造高确认率场景：3 次唤醒全部确认 → 建议提前询问并应用
        for _ in range(3):
            self.system.confirm_awaken(
                ["learning"], confirmed=True, reason="S4 演示"
            )
        report = self.system.introspect(apply=True)
        self.assertTrue(report["applied"])
        adjustment = report["applied"][0]
        self.assertEqual(adjustment["key"], "ask_min_length")
        self.assertLess(adjustment["new"], adjustment["old"])
        # 行为差异可验证：调整后阈值已更新
        self.assertEqual(
            self.system.router.get_settings()["ask_min_length"],
            adjustment["new"],
        )

    def test_introspection_adjustment_revert(self) -> None:
        for _ in range(3):
            self.system.confirm_awaken(
                ["learning"], confirmed=True, reason="S4 演示"
            )
        report = self.system.introspect(apply=True)
        adjustment_id = report["applied"][0]["id"]
        old_value = report["applied"][0]["old"]
        result = self.system.revert_adjustment(adjustment_id)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["restored"], old_value)
        self.assertEqual(
            self.system.router.get_settings()["ask_min_length"], old_value
        )

    def test_introspection_insufficient_sample(self) -> None:
        # 样本不足（<3）不调整
        self.system.confirm_awaken(["learning"], confirmed=True, reason="A")
        report = self.system.introspect(apply=True)
        self.assertEqual(report["applied"], [])
        self.assertEqual(report["proposed"], [])

    def test_introspection_low_confirm_reduces_asking(self) -> None:
        # 低确认率 → 提高 ask_min_length（减少打扰）
        self.system.router.update_settings({"ask_min_length": 60})
        for _ in range(3):
            self.system.confirm_awaken(
                ["tech"], confirmed=False, reason="S4 演示"
            )
        report = self.system.introspect(apply=True)
        self.assertTrue(report["applied"])
        adjustment = report["applied"][0]
        self.assertGreater(adjustment["new"], adjustment["old"])

    def test_introspection_log_traceable(self) -> None:
        self.system.run_task("creation", "script_draft", {"topic": "A"})
        self.system.introspect()
        entries = self.system.introspection_list()
        self.assertEqual(len(entries), 1)
        self.assertIn("stats", entries[0])
        self.assertIn("at", entries[0])


class AvatarApiS4Test(unittest.TestCase):
    """S4 HTTP 端点冒烟：skills / introspect。"""

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

    def test_skills_endpoint(self) -> None:
        status, payload = self._get("/v1/avatars/skills")
        self.assertEqual(status, 200)
        ids = {s["id"] for s in payload["skills"]}
        self.assertIn("live2d_render", ids)
        self.assertIn("document_retrieve", ids)
        self.assertIn("mix_audio", ids)

    def test_skills_register_endpoint(self) -> None:
        status, payload = self._post(
            "/v1/avatars/skills/register",
            {
                "id": "halo_check",
                "name": "白边检查",
                "description": "透明素材边缘白边自动检查（K6 待办）",
                "capability": "video_script",
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["skill"]["id"], "halo_check")

    def test_introspect_endpoint(self) -> None:
        status, payload = self._post(
            "/v1/avatars/introspect", {"apply": False}
        )
        self.assertEqual(status, 200)
        self.assertIn("stats", payload)
        self.assertIn("tool_total", payload["stats"])

    def test_introspection_log_endpoint(self) -> None:
        self._post("/v1/avatars/introspect", {"apply": False})
        status, payload = self._get("/v1/avatars/introspection-log")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(len(payload["entries"]), 1)


class AvatarPersonaS5Test(unittest.TestCase):
    """S5 前置：性格分化（四分身语气可区分、模板可定制、兜底不抛错）。"""

    def setUp(self) -> None:
        tmp = tempfile.mkdtemp(prefix="moling_avatars_s5_")
        self.store = FakeMemoryStore()
        self.system = AvatarSystem(
            registry_path=Path(tmp) / "avatars.json",
            awaken_log_path=Path(tmp) / "awaken_log.json",
            character_store=self.store,
        )

    def test_default_personas_present(self) -> None:
        ids = {p["avatar_id"] for p in self.system.persona_list()}
        self.assertEqual(ids, {"companion", "learning", "creation", "tech"})
        for avatar_id in ids:
            persona = self.system.personas.get(avatar_id)
            self.assertIsNotNone(persona)
            self.assertIn("situations", persona)  # type: ignore[union-attr]

    def test_same_situation_distinct_outputs(self) -> None:
        companion = self.system.persona_speak("companion", "task_ok", result="检查通过")
        learning = self.system.persona_speak("learning", "task_ok", result="检查通过")
        creation = self.system.persona_speak("creation", "task_ok", result="检查通过")
        tech = self.system.persona_speak("tech", "task_ok", result="检查通过")
        # 同一情境、同一事实，四个分身措辞可被规则区分
        self.assertIn("我们做到了", companion)
        self.assertIn("结论", learning)
        self.assertIn("这个感觉", creation)
        self.assertIn("已记录", tech)
        self.assertEqual(len({companion, learning, creation, tech}), 4)

    def test_template_variable_substitution(self) -> None:
        message = self.system.persona_speak("tech", "task_ok", result="渲染 12 帧")
        self.assertIn("渲染 12 帧", message)

    def test_unknown_avatar_falls_back(self) -> None:
        message = self.system.persona_speak("ghost", "task_ok", result="x")
        self.assertIsInstance(message, str)
        self.assertTrue(message)

    def test_unknown_situation_falls_back(self) -> None:
        message = self.system.persona_speak("tech", "no_such_situation")
        self.assertIsInstance(message, str)
        self.assertTrue(message)

    def test_upsert_custom_persona(self) -> None:
        self.system.upsert_persona(
            {
                "avatar_id": "companion",
                "name": "定制陪伴",
                "tone": "cozy",
                "situations": {"task_ok": "搞定啦：{result}"},
            }
        )
        message = self.system.persona_speak("companion", "task_ok", result="整理完成")
        self.assertIn("搞定啦", message)
        self.assertIn("整理完成", message)

    def test_invalid_persona_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.system.upsert_persona({"avatar_id": "x"})
        with self.assertRaises(ValueError):
            self.system.upsert_persona(
                {"avatar_id": "x", "name": "X", "situations": {"task_ok": ""}}
            )

    def test_run_task_message_decorated(self) -> None:
        # run_task 结果附带该分身的性格消息（表现层装饰）
        result = self.system.run_task("creation", "script_draft", {"topic": "演示"})
        self.assertEqual(result["status"], "ok")
        self.assertIn("这个感觉", result["message"])


class AvatarApiS5Test(unittest.TestCase):
    """S5 前置 HTTP 冒烟：personas 列表与登记。"""

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

    def test_personas_endpoint(self) -> None:
        status, payload = self._get("/v1/avatars/personas")
        self.assertEqual(status, 200)
        ids = {p["avatar_id"] for p in payload["personas"]}
        self.assertEqual(ids, {"companion", "learning", "creation", "tech"})

    def test_personas_upsert_endpoint(self) -> None:
        status, payload = self._post(
            "/v1/avatars/personas",
            {
                "avatar_id": "companion",
                "name": "定制陪伴",
                "situations": {"task_ok": "搞定啦：{result}"},
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["persona"]["name"], "定制陪伴")


class AvatarPersonaParamsS5Test(unittest.TestCase):
    """A1 性格参数深化：jargon / verbosity / max_sentence 真实生效且确定性可测。"""

    def setUp(self) -> None:
        tmp = tempfile.mkdtemp(prefix="moling_avatars_a1_")
        self.store = FakeMemoryStore()
        self.system = AvatarSystem(
            registry_path=Path(tmp) / "avatars.json",
            awaken_log_path=Path(tmp) / "awaken_log.json",
            character_store=self.store,
        )

    def test_default_styles_have_params(self) -> None:
        for persona in self.system.persona_list():
            style = persona["style"]
            self.assertIn("jargon_map", style)
            self.assertIn("verbosity", style)
            self.assertIn("max_sentence", style)

    def test_tech_jargon_high_replaces_terms(self) -> None:
        text = self.system.persona_speak("tech", "task_ok", result="查看记录")
        self.assertIn("检索记录", text)

    def test_learning_medium_keeps_terms(self) -> None:
        text = self.system.persona_speak("learning", "task_ok", result="查看记录")
        self.assertNotIn("检索记录", text)

    def test_companion_verbose_appends_phrase(self) -> None:
        text = self.system.persona_speak("companion", "task_ok", result="检查通过")
        self.assertTrue(text.endswith("我们一步一步来"))

    def test_max_sentence_truncates(self) -> None:
        self.system.upsert_persona(
            {
                "avatar_id": "tech",
                "name": "技术小墨",
                "situations": {"task_ok": "{result}"},
                "style": {"max_sentence": 8, "jargon": "low", "verbosity": "normal"},
            }
        )
        text = self.system.persona_speak("tech", "task_ok", result="这是一个很长的检查结果")
        self.assertLessEqual(len(text), 8)
        self.assertTrue(text.endswith("…"))

    def test_upsert_normalizes_style_defaults(self) -> None:
        self.system.upsert_persona(
            {
                "avatar_id": "creation",
                "name": "创作小墨",
                "situations": {"task_ok": "{result}"},
                "style": {"max_sentence": 20, "jargon": "low"},
            }
        )
        persona = self.system.personas.get("creation")
        self.assertEqual(persona["style"]["verbosity"], "normal")  # type: ignore[index]
        self.assertEqual(persona["style"]["jargon_map"], {})  # type: ignore[index]


class AvatarScriptPersonaA2Test(unittest.TestCase):
    """A2 演出脚本人格化：script_draft 结果套上对应分身开场 / 收尾。"""

    def setUp(self) -> None:
        tmp = tempfile.mkdtemp(prefix="moling_avatars_a2_")
        self.store = FakeMemoryStore()
        self.system = AvatarSystem(
            registry_path=Path(tmp) / "avatars.json",
            awaken_log_path=Path(tmp) / "awaken_log.json",
            character_store=self.store,
        )

    def test_creation_script_styled(self) -> None:
        result = self.system.run_task(
            "creation", "script_draft", {"topic": "光合作用"}, approved=True
        )
        self.assertEqual(result["status"], "ok")
        styled = result["script_styled"]
        self.assertTrue(styled["opening"].startswith("试试这个感觉："))
        self.assertIn("persona", styled)
        self.assertEqual(styled["persona"], "creation")

    def test_tech_script_styled_differs(self) -> None:
        draft = {"opening": "今天想和你聊聊：光合作用", "body": "正文", "closing": "总结"}
        styled = self.system.persona_script("tech", draft)
        self.assertTrue(styled["opening"].startswith("具体来说："))
        self.assertEqual(styled["persona"], "tech")

    def test_script_styled_preserves_body(self) -> None:
        result = self.system.run_task(
            "creation", "script_draft", {"topic": "光合作用"}, approved=True
        )
        body = result["result"]["script"]["body"]
        self.assertEqual(result["script_styled"]["body"], body)


class AvatarMediaMixAudioA3Test(unittest.TestCase):
    """A3 人声优先混音（纯标准库 wave）：输出存在、时长以人声为准、峰值受控、任务链路可跑。"""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="moling_avatars_a3_")
        self.voice = self._make_tone(Path(self.tmp) / "voice.wav", freq=440, amp=8000, frames=8000)
        self.music = self._make_tone(Path(self.tmp) / "music.wav", freq=220, amp=16000, frames=16000)
        self.store = FakeMemoryStore()
        self.system = AvatarSystem(
            registry_path=Path(self.tmp) / "avatars.json",
            awaken_log_path=Path(self.tmp) / "awaken_log.json",
            character_store=self.store,
        )

    @staticmethod
    def _make_tone(path: Path, freq: int, amp: int, frames: int, rate: int = 8000) -> Path:
        import array
        import math
        import wave as wave_module

        samples = array.array("h")
        for i in range(frames):
            samples.append(int(amp * math.sin(2 * math.pi * freq * i / rate)))
        with wave_module.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(samples.tobytes())
        return path

    def test_mix_voice_first_output(self) -> None:
        from avatar_media import mix_voice_first

        out = Path(self.tmp) / "mix.wav"
        info = mix_voice_first(self.voice, self.music, out, music_gain_db=-6.0)
        self.assertEqual(info["status"], "ok")
        self.assertTrue(out.exists())
        self.assertEqual(info["frames"], 8000)
        self.assertEqual(info["mode"], "voice_first_v1")

    def test_mix_peak_bounded_by_voice_plus_ducked_music(self) -> None:
        import array
        import wave as wave_module

        from avatar_media import mix_voice_first

        out = Path(self.tmp) / "mix2.wav"
        mix_voice_first(self.voice, self.music, out, music_gain_db=-6.0)
        with wave_module.open(str(out), "rb") as w:
            samples = array.array("h")
            samples.frombytes(w.readframes(w.getnframes()))
        peak = max(abs(s) for s in samples)
        # -6dB ≈ 0.5 增益：峰值不应超过 人声 8000 + 音乐×0.5 8000 = 16000（clamp 后）
        self.assertLessEqual(peak, 16000)

    def test_mix_audio_task_via_system(self) -> None:
        out = Path(self.tmp) / "task_mix.wav"
        result = self.system.run_task(
            "creation",
            "mix_audio",
            {"voice": str(self.voice), "music": str(self.music), "out": str(out)},
            approved=True,
        )
        self.assertEqual(result["status"], "ok")
        self.assertTrue(out.exists())

    def test_mix_audio_missing_path_rejected(self) -> None:
        result = self.system.run_task(
            "creation", "mix_audio", {"voice": "", "music": "", "out": ""}, approved=True
        )
        self.assertEqual(result["status"], "failed")

    def test_mix_audio_skill_card_registered(self) -> None:
        card = self.system.skills.by_invoke("mix_audio")
        self.assertIsNotNone(card)
        self.assertEqual(card["source"], "K6")  # type: ignore[index]


class AvatarAssetQualityB1Test(unittest.TestCase):
    """B1 边缘白边检查：透明素材质检可复现、风险分级正确。"""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="moling_avatars_b1_")
        self.store = FakeMemoryStore()
        self.system = AvatarSystem(
            registry_path=Path(self.tmp) / "avatars.json",
            awaken_log_path=Path(self.tmp) / "awaken_log.json",
            character_store=self.store,
        )

    @staticmethod
    def _make_image(path: Path, mode: str) -> Path:
        from PIL import Image

        img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        pixels = img.load()
        for y in range(8, 24):
            for x in range(8, 24):
                pixels[x, y] = (120, 60, 200, 255)
        if mode == "halo":
            for y in range(5, 27):
                for x in range(5, 27):
                    if img.getpixel((x, y))[3] == 0:
                        pixels[x, y] = (250, 250, 252, 90)  # 半透明白 → 白边
        elif mode == "dark_edge":
            for y in range(5, 27):
                for x in range(5, 27):
                    if img.getpixel((x, y))[3] == 0:
                        pixels[x, y] = (40, 30, 60, 90)  # 半透明深色 → 无白边
        img.save(str(path))
        return path

    def test_halo_image_flagged_high(self) -> None:
        image = self._make_image(Path(self.tmp) / "halo.png", "halo")
        result = self.system.run_task(
            "creation", "check_halo", {"image": str(image)}, approved=True
        )
        self.assertEqual(result["status"], "ok")
        self.assertIn("risk", result["result"])
        self.assertGreater(result["result"]["halo_ratio"], 0.15)

    def test_dark_edge_low_risk(self) -> None:
        image = self._make_image(Path(self.tmp) / "dark.png", "dark_edge")
        result = self.system.run_task(
            "creation", "check_halo", {"image": str(image)}, approved=True
        )
        self.assertEqual(result["status"], "ok")
        self.assertLessEqual(result["result"]["halo_ratio"], 0.02)

    def test_missing_image_rejected(self) -> None:
        result = self.system.run_task(
            "creation",
            "check_halo",
            {"image": str(Path(self.tmp) / "nope.png")},
            approved=True,
        )
        self.assertEqual(result["status"], "failed")


class PerformanceRulesB2Test(unittest.TestCase):
    """B2 动作清单成文：演出规则 JSON 结构可读、字段完整。"""

    def test_rules_file_structure(self) -> None:
        import json as json_module

        path = (
            Path(__file__).resolve().parent.parent.parent
            / "Docs & Compliance"
            / "performance_rules.json"
        )
        self.assertTrue(path.exists())
        data = json_module.loads(path.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(data["semantic_actions"]), 4)
        self.assertGreaterEqual(len(data["stage_rules"]), 3)
        for action in data["semantic_actions"]:
            for key in ("cue", "motion", "timing"):
                self.assertIn(key, action)
        self.assertIn("mouth_curve", data)


class CaptionTimelineB3Test(unittest.TestCase):
    """B3 字幕时间戳数据层：可编辑、可保存、换音重算口型。"""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="moling_avatars_b3_")
        self.store = CaptionTimelineStore(Path(self.tmp) / "captions.json")

    def test_set_and_edit_timestamp(self) -> None:
        self.store.set("clip1", [{"start": 0.0, "end": 1.0, "text": "你好"}])
        info = self.store.edit_timestamp("clip1", 0, 0.2, 1.4)
        self.assertEqual(info["start"], 0.2)
        self.assertEqual(info["end"], 1.4)
        captions = self.store.get("clip1")
        self.assertEqual(captions[0]["text"], "你好")

    def test_invalid_captions_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.store.set("clip2", [])

    def test_align_mouth_recomputes(self) -> None:
        import array
        import wave as wave_module

        voice = Path(self.tmp) / "voice.wav"
        samples = array.array("h")
        samples.extend([0] * 4000)  # 前半静音 → closed
        samples.extend([12000] * 4000)  # 后半响亮 → open
        with wave_module.open(str(voice), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(8000)
            w.writeframes(samples.tobytes())
        self.store.set("clip3", [{"start": 0.0, "end": 0.5, "text": "前"},
                                 {"start": 0.5, "end": 1.0, "text": "后"}])
        info = self.store.align_mouth("clip3", voice)
        aligned = self.store.get("clip3")
        self.assertEqual(info["status"], "ok")
        self.assertEqual(aligned[0]["mouth"], "closed")
        self.assertEqual(aligned[1]["mouth"], "open")

    def test_persisted_across_reload(self) -> None:
        self.store.set("clip4", [{"start": 0.0, "end": 1.0, "text": "持久"}])
        reloaded = CaptionTimelineStore(self.store.path)
        self.assertEqual(reloaded.get("clip4")[0]["text"], "持久")


class SuggestionEngineC1Test(unittest.TestCase):
    """C1 建议引擎：自省统计 → 确定性建议（本地规则）。"""

    def test_empty_stats_no_suggestions(self) -> None:
        from avatar_advice import SuggestionEngine

        suggestions = SuggestionEngine.stats_to_suggestions(
            {"tool_total": 0, "denied": 0, "failed": 0}
        )
        self.assertEqual(suggestions, [])

    def test_denied_boundary_suggestion(self) -> None:
        from avatar_advice import SuggestionEngine

        suggestions = SuggestionEngine.stats_to_suggestions(
            {
                "tool_total": 10,
                "denied": 3,
                "denied_reasons": {"requires_permission": 3},
                "failed": 0,
                "wake_total": 0,
                "wake_ratio": 0.0,
            }
        )
        kinds = {s["kind"] for s in suggestions}
        self.assertIn("approval_boundary", kinds)

    def test_failed_reliability_suggestion(self) -> None:
        from avatar_advice import SuggestionEngine

        suggestions = SuggestionEngine.stats_to_suggestions(
            {
                "tool_total": 10,
                "denied": 0,
                "failed": 4,
                "wake_total": 0,
                "wake_ratio": 0.0,
            }
        )
        self.assertIn("task_reliability", {s["kind"] for s in suggestions})

    def test_steady_fallback(self) -> None:
        from avatar_advice import SuggestionEngine

        suggestions = SuggestionEngine.stats_to_suggestions(
            {
                "tool_total": 5,
                "denied": 0,
                "failed": 0,
                "wake_total": 0,
                "wake_ratio": 0.0,
            }
        )
        self.assertEqual(suggestions[0]["kind"], "steady")

    def test_threshold_suggestion_on_low_wake_ratio(self) -> None:
        from avatar_advice import SuggestionEngine

        suggestions = SuggestionEngine.stats_to_suggestions(
            {
                "tool_total": 5,
                "denied": 0,
                "failed": 0,
                "wake_total": 5,
                "wake_ratio": 0.2,
            }
        )
        self.assertIn("threshold", {s["kind"] for s in suggestions})


class AvatarShortMemoryC2Test(unittest.TestCase):
    """C2 分身短记忆：工作偏好存储（主权边界内），可撤销、可持久化。"""

    def setUp(self) -> None:
        tmp = tempfile.mkdtemp(prefix="moling_avatars_c2_")
        self.store = FakeMemoryStore()
        self.system = AvatarSystem(
            registry_path=Path(tmp) / "avatars.json",
            awaken_log_path=Path(tmp) / "awaken_log.json",
            character_store=self.store,
        )

    def test_set_get_delete_via_system(self) -> None:
        self.system.short_memory_set("creation", "preferred_style", "讲解")
        self.system.short_memory_set("tech", "shell_verbosity", "brief")
        self.assertEqual(
            self.system.short_memory_get("creation"),
            {"preferred_style": "讲解"},
        )
        result = self.system.short_memory_delete("creation", "preferred_style")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(self.system.short_memory_get("creation"), {})

    def test_persisted_across_reload(self) -> None:
        path = Path(self.system.short_memory.path)
        self.system.short_memory_set("learning", "citation_style", "apa")
        reloaded = AvatarShortMemory(path)
        self.assertEqual(reloaded.get("learning"), {"citation_style": "apa"})

    def test_value_type_guard(self) -> None:
        with self.assertRaises(ValueError):
            self.system.short_memory_set("creation", "key1", {"dict": "not-allowed"})

    def test_invalid_key_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.system.short_memory_set("creation", "", "x")


class DailyBriefC3Test(unittest.TestCase):
    """C3 每日自省简报：tool_log 统计 + 建议（本地确定性规则）。"""

    def setUp(self) -> None:
        tmp = tempfile.mkdtemp(prefix="moling_avatars_c3_")
        self.store = FakeMemoryStore()
        self.system = AvatarSystem(
            registry_path=Path(tmp) / "avatars.json",
            awaken_log_path=Path(tmp) / "awaken_log.json",
            character_store=self.store,
        )

    def test_brief_structure_and_stats(self) -> None:
        from avatar_advice import build_daily_brief

        log = [
            {"decision": "allowed", "error": None, "task": "mood_echo"},
            {"decision": "allowed", "error": None, "task": "script_draft"},
            {"decision": "denied", "task": "external_search"},
            {"decision": "allowed", "error": "boom", "task": "safe_exec"},
        ]
        brief = build_daily_brief(log, [{"kind": "steady", "severity": "none", "text": "稳"}])
        self.assertEqual(brief["tool_total"], 4)
        self.assertEqual(brief["stats"], {"ok": 2, "denied": 1, "failed": 1})
        self.assertIn("mood_echo", brief["skills_used"])
        self.assertEqual(brief["mode"], "local_rule")

    def test_system_daily_brief_empty(self) -> None:
        brief = self.system.daily_brief()
        self.assertEqual(brief["tool_total"], 0)
        self.assertIn("date", brief)
        self.assertIn("suggestions", brief)

    def test_system_suggestions_empty(self) -> None:
        self.assertEqual(self.system.suggestions(), [])


if __name__ == "__main__":
    unittest.main()
