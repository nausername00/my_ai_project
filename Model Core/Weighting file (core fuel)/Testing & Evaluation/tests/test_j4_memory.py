"""J4: memory traceability & revocation.

Covers:
- MemoryEntry gains reason/status/use_count/last_used_at with backward
  compatibility for old (pre-J4) payloads.
- paused memories are excluded from list() and search() (never re-recalled
  after revocation).
- pause/resume lifecycle.
- record_usage tracks which memories were injected into a reply.
- CharacterStore: build_system_prompt records usage of injected memories;
  pausing a memory removes it from the prompt.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from character import CharacterStore, MemoryNotFoundError
from memory import LongTermStore, MemoryEntry, MemoryStore, MemoryUsageLog


class MemoryEntryJ4Test(unittest.TestCase):
    def test_old_payload_parses_with_defaults(self) -> None:
        entry = MemoryEntry.from_dict(
            {
                "id": "m1",
                "content": "旧数据",
                "source": "user",
                "visibility": "model",
                "created_at": "2026-01-01T00:00:00+00:00",
            }
        )
        self.assertEqual(entry.status, "active")
        self.assertIsNone(entry.reason)
        self.assertEqual(entry.use_count, 0)
        self.assertIsNone(entry.last_used_at)

    def test_new_fields_roundtrip(self) -> None:
        entry = MemoryEntry.from_dict(
            {
                "content": "带原因的记忆",
                "source": "explore",
                "visibility": "model",
                "reason": "探索运行记录",
                "status": "paused",
                "use_count": 3,
                "last_used_at": "2026-10-10T00:00:00+00:00",
            }
        )
        payload = entry.to_dict()
        self.assertEqual(payload["status"], "paused")
        self.assertEqual(payload["reason"], "探索运行记录")
        self.assertEqual(payload["use_count"], 3)
        self.assertEqual(payload["last_used_at"], "2026-10-10T00:00:00+00:00")

    def test_invalid_status_and_use_count_rejected(self) -> None:
        with self.assertRaises(ValueError):
            MemoryEntry.from_dict({"content": "x", "status": "archived"})
        with self.assertRaises(ValueError):
            MemoryEntry.from_dict({"content": "x", "use_count": -1})


class LongTermStoreJ4Test(unittest.TestCase):
    def _store(self, directory: str) -> LongTermStore:
        return LongTermStore(Path(directory) / "memory.json")

    def test_paused_memories_excluded_from_list_and_search(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(directory)
            active = store.add("活跃记忆", source="user")
            paused = store.add("暂停记忆", source="user")
            store.pause(paused.id)

            listed = store.list()
            self.assertEqual([e.id for e in listed], [active.id])
            self.assertNotIn(paused.id, [e.id for e in listed])

            results = store.search("暂停记忆", top_k=8)
            self.assertNotIn(paused.id, [r["id"] for r in results])
            results_active = store.search("活跃记忆", top_k=8)
            self.assertEqual(results_active[0]["id"], active.id)

    def test_pause_resume_lifecycle_preserves_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(directory)
            entry = store.add("带原因的", source="explore", reason="探索记录")
            paused = store.pause(entry.id)
            self.assertEqual(paused.status, "paused")
            self.assertEqual(paused.reason, "探索记录")
            resumed = store.resume(entry.id)
            self.assertEqual(resumed.status, "active")
            self.assertIn(entry.id, [e.id for e in store.list()])

    def test_record_usage_updates_count_and_time(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(directory)
            a = store.add("记忆A", source="user")
            b = store.add("记忆B", source="user")
            touched = store.record_usage([a.id, b.id, "missing-id"])
            self.assertEqual(touched, 2)
            self.assertEqual(store.get(a.id).use_count, 1)
            self.assertIsNotNone(store.get(a.id).last_used_at)
            self.assertEqual(store.get(b.id).use_count, 1)

    def test_record_usage_skips_paused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(directory)
            a = store.add("记忆A", source="user")
            store.pause(a.id)
            touched = store.record_usage([a.id])
            self.assertEqual(touched, 0)
            self.assertEqual(store.get(a.id).use_count, 0)

    def test_update_supports_status_and_reason(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(directory)
            entry = store.add("原始内容", source="user")
            updated = store.update(
                entry.id,
                content="更正后的内容",
                visibility="model",
                source="user",
                reason="用户更正",
                status="paused",
            )
            self.assertEqual(updated.content, "更正后的内容")
            self.assertEqual(updated.reason, "用户更正")
            self.assertEqual(updated.status, "paused")
            self.assertEqual(updated.use_count, 0)

    def test_delete_removes_from_recall_entirely(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(directory)
            entry = store.add("待删除", source="user")
            store.delete(entry.id)
            self.assertEqual(store.search("待删除", top_k=8), [])
            with self.assertRaises(LookupError):
                store.get(entry.id)

    def test_persist_and_reload_keeps_j4_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(directory)
            entry = store.add("持久化", source="explore", reason="原因", status="paused")
            store.record_usage([entry.id])
            store.save()
            reloaded = LongTermStore(Path(directory) / "memory.json")
            restored = reloaded.get(entry.id)
            self.assertEqual(restored.status, "paused")
            self.assertEqual(restored.reason, "原因")
            self.assertEqual(restored.use_count, 0)  # paused 不被记录使用


class CharacterStoreJ4Test(unittest.TestCase):
    def _store(self, directory: str) -> CharacterStore:
        return CharacterStore(
            str(Path(directory) / "character.json"),
            str(Path(directory) / "memory.json"),
            str(Path(directory) / "assets"),
        )

    def test_add_memory_accepts_reason_and_returns_new_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(directory)
            entry = store.add_memory("探索记录", source="explore", reason="探索运行记录")
            self.assertEqual(entry["reason"], "探索运行记录")
            self.assertEqual(entry["status"], "active")
            self.assertEqual(entry["use_count"], 0)

    def test_build_system_prompt_records_usage_of_injected_memories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(directory)
            store.add_memory("用户喜欢雨天", source="user")
            entries = store.list_memories()
            self.assertEqual(entries[0]["use_count"], 0)
            prompt = store.build_system_prompt()
            self.assertIn("用户喜欢雨天", prompt)
            after = store.list_memories()
            self.assertEqual(after[0]["use_count"], 1)
            self.assertIsNotNone(after[0]["last_used_at"])

    def test_paused_memory_removed_from_prompt_and_not_recalled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(directory)
            entry = store.add_memory("不想被记住的事", source="user")
            store.update_memory(
                entry["id"],
                content=entry["content"],
                visibility="model",
                status="paused",
            )
            prompt = store.build_system_prompt()
            self.assertNotIn("不想被记住的事", prompt)
            listed = store.list_memories()
            self.assertNotIn(entry["id"], [e["id"] for e in listed])

    def test_delete_memory_then_not_recalled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(directory)
            entry = store.add_memory("要遗忘的事", source="user")
            store.delete_memory(entry["id"])
            with self.assertRaises(MemoryNotFoundError):
                store.delete_memory(entry["id"])
            prompt = store.build_system_prompt()
            self.assertNotIn("要遗忘的事", prompt)


class MemoryUsageLogE2Test(unittest.TestCase):
    """E2 记忆使用追踪：按回复时间线 + 撤销联动（删除/暂停后不再出现在追踪）。"""

    def _store(self, directory: str) -> tuple[MemoryStore, MemoryUsageLog]:
        store = MemoryStore(
            long_term_path=Path(directory) / "memory.json",
            cross_scene_path=Path(directory) / "cross_scene.json",
            short_term_capacity=40,
        )
        log = MemoryUsageLog(Path(directory) / "usage_log.json")
        return store, log

    def test_record_filters_non_string_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, log = self._store(directory)
            self.assertEqual(log.record("r1", ["m1", 123, "", None]), 1)

    def test_record_appends_timeline_reverse_chronological(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, log = self._store(directory)
            log.record("r1", ["m1"])
            log.record("r2", ["m2", "m3"])
            recent = log.list()
            self.assertEqual(recent[0]["reply_id"], "r2")
            self.assertEqual(recent[1]["reply_id"], "r1")
            self.assertEqual(recent[0]["memory_ids"], ["m2", "m3"])

    def test_by_memory_returns_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, log = self._store(directory)
            log.record("r1", ["m1"])
            log.record("r2", ["m1", "m2"])
            history = log.by_memory("m1")
            self.assertEqual([h["reply_id"] for h in history], ["r2", "r1"])

    def test_usage_summary_reflects_counts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, log = self._store(directory)
            a = store.add_memory("记忆A", source="user")
            b = store.add_memory("记忆B", source="explore", reason="探索记录")
            store.record_memory_usage([a["id"], b["id"], a["id"]])
            summary = log.usage_summary(store)
            by_id = {item["memory_id"]: item for item in summary}
            self.assertEqual(by_id[a["id"]]["use_count"], 2)
            self.assertEqual(by_id[b["id"]]["use_count"], 1)
            self.assertEqual(by_id[b["id"]]["source"], "explore")

    def test_deleted_memory_gone_from_tracking(self) -> None:
        """验收：被撤销（删除）的记忆不再出现在聚合追踪中。"""
        with tempfile.TemporaryDirectory() as directory:
            store, log = self._store(directory)
            a = store.add_memory("要撤销", source="user")
            store.record_memory_usage([a["id"]])
            store.delete_memory(a["id"])
            summary = log.usage_summary(store)
            self.assertNotIn(a["id"], [item["memory_id"] for item in summary])

    def test_paused_memory_gone_from_tracking(self) -> None:
        """验收：被暂停的记忆不再出现在聚合追踪中。"""
        with tempfile.TemporaryDirectory() as directory:
            store, log = self._store(directory)
            a = store.add_memory("要暂停", source="user")
            store.record_memory_usage([a["id"]])
            store.pause_memory(a["id"])
            summary = log.usage_summary(store)
            self.assertNotIn(a["id"], [item["memory_id"] for item in summary])

    def test_persist_and_reload_keeps_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, log = self._store(directory)
            log.record("r1", ["m1"])
            reloaded = MemoryUsageLog(Path(directory) / "usage_log.json")
            self.assertEqual(reloaded.list()[0]["reply_id"], "r1")


class CharacterStoreE2Test(unittest.TestCase):
    """E2 联动：build_system_prompt 自动记录时间线；memory_usage 查询端点数据。"""

    def _store(self, directory: str) -> CharacterStore:
        return CharacterStore(
            str(Path(directory) / "character.json"),
            str(Path(directory) / "memory.json"),
            str(Path(directory) / "assets"),
        )

    def test_build_system_prompt_records_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(directory)
            entry = store.add_memory("用户喜欢雨天", source="user")
            store.build_system_prompt(reply_id="msg-1")
            history = store.usage_log.by_memory(entry["id"])
            self.assertEqual(history[0]["reply_id"], "msg-1")

    def test_memory_usage_query_shape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(directory)
            store.add_memory("偏好", source="user")
            payload = store.memory_usage()
            self.assertIn("summary", payload)
            self.assertIn("recent", payload)
            self.assertEqual(payload["summary"][0]["source"], "user")


if __name__ == "__main__":
    unittest.main()
