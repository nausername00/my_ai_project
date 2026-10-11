"""J5: bounded proactive proposals & shared goals.

Covers opt-in gating, frequency, quiet hours, pause/stop, respond actions,
goal CRUD with consent-gated progress persistence, and store round-trips.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from proposals import (
    DEFAULT_SETTINGS,
    ProposalStore,
    SharedGoal,
    is_within_quiet_hours,
)


def _store(directory: str) -> ProposalStore:
    return ProposalStore(Path(directory) / "proposals.json")


def _now() -> datetime:
    return datetime(2026, 10, 10, 12, 0, 0, tzinfo=timezone.utc)


class QuietHoursTest(unittest.TestCase):
    def test_plain_window(self) -> None:
        windows = [{"start": "09:00", "end": "17:00"}]
        self.assertTrue(is_within_quiet_hours(datetime(2026, 10, 10, 10, 0), windows))
        self.assertFalse(is_within_quiet_hours(datetime(2026, 10, 10, 20, 0), windows))

    def test_wrapping_midnight_window(self) -> None:
        windows = [{"start": "23:00", "end": "07:00"}]
        self.assertTrue(is_within_quiet_hours(datetime(2026, 10, 10, 23, 30), windows))
        self.assertTrue(is_within_quiet_hours(datetime(2026, 10, 11, 2, 0), windows))
        self.assertFalse(is_within_quiet_hours(datetime(2026, 10, 10, 12, 0), windows))

    def test_equal_bounds_are_ignored(self) -> None:
        self.assertFalse(
            is_within_quiet_hours(
                datetime(2026, 10, 10, 12, 0), [{"start": "00:00", "end": "00:00"}]
            )
        )

    def test_invalid_windows_are_skipped(self) -> None:
        self.assertFalse(
            is_within_quiet_hours(
                datetime(2026, 10, 10, 12, 0), [{"start": "oops", "end": "17:00"}]
            )
        )


class ProposalGatingTest(unittest.TestCase):
    def test_disabled_by_default_never_proposes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = _store(directory)
            goal = store.add_goal("学 Blender", "会好奇地尝试")
            self.assertFalse(store.get_settings()["enabled"])
            self.assertIsNone(store.pending_proposal(now=_now()))
            self.assertIsNone(store.pending_proposal(candidates=[goal], now=_now()))

    def test_enabled_but_paused_never_proposes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = _store(directory)
            store.update_settings({"enabled": True, "paused": True})
            store.add_goal("目标A")
            self.assertIsNone(store.pending_proposal(now=_now()))

    def test_quiet_hours_block_proposal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = _store(directory)
            store.update_settings({"enabled": True, "quiet_hours": [{"start": "00:00", "end": "23:59"}]})
            store.add_goal("目标A")
            self.assertIsNone(store.pending_proposal(now=_now()))

    def test_frequency_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = _store(directory)
            store.update_settings({"enabled": True, "frequency_minutes": 60})
            goal = store.add_goal("目标A")
            # 首次（无 last_proposed_at）直接可提议
            proposal = store.pending_proposal(now=_now())
            self.assertIsNotNone(proposal)
            self.assertEqual(proposal["goal_id"], goal["id"])
            # 记录提议时钟后，频率未到不提议
            store.set_last_proposed(_now().isoformat())
            self.assertIsNone(store.pending_proposal(now=_now() + timedelta(minutes=30)))
            self.assertIsNotNone(store.pending_proposal(now=_now() + timedelta(hours=1, minutes=1)))

    def test_proposal_records_clock_after_accept(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = _store(directory)
            store.update_settings({"enabled": True, "frequency_minutes": 60})
            goal = store.add_goal("目标A")
            store.respond(goal["id"], "accept")
            settings = store.get_settings()
            self.assertIsNotNone(settings.get("last_proposed_at"))
            # 频率未到：不再提议
            self.assertIsNone(store.pending_proposal(now=_now() + timedelta(minutes=30)))

    def test_declined_goal_has_cooldown_and_other_goal_proposes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = _store(directory)
            store.update_settings({"enabled": True})
            g1 = store.add_goal("已拒绝的目标")
            g2 = store.add_goal("另一目标")
            store.respond(g1["id"], "decline")
            proposal = store.pending_proposal(now=_now())
            self.assertIsNotNone(proposal)
            self.assertEqual(proposal["goal_id"], g2["id"])

    def test_stop_pauses_all_proposals(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = _store(directory)
            store.update_settings({"enabled": True})
            goal = store.add_goal("目标A")
            result = store.respond(goal["id"], "stop")
            self.assertTrue(result["paused"])
            self.assertTrue(store.get_settings()["paused"])
            self.assertIsNone(store.pending_proposal(now=_now()))


class GoalCrudTest(unittest.TestCase):
    def test_goal_lifecycle_and_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = _store(directory)
            goal = store.add_goal("学画画", "每天一张速写")
            self.assertEqual(goal["status"], "active")
            updated = store.update_goal(goal["id"], {"status": "paused"})
            self.assertEqual(updated["status"], "paused")
            store.update_goal(goal["id"], {"status": "completed"})
            ended = store.update_goal(goal["id"], {"status": "ended"})
            self.assertEqual(ended["status"], "ended")
            store.delete_goal(goal["id"])
            self.assertEqual(store.list_goals(), [])
            with self.assertRaises(LookupError):
                store.delete_goal(goal["id"])

    def test_progress_only_saved_with_consent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = _store(directory)
            goal = store.add_goal("目标A", consented=True)
            updated = store.update_goal(goal["id"], {"progress_note": "推进了第一步"})
            self.assertEqual(updated["progress_note"], "推进了第一步")
            # 撤销同意后，进展不再持久化
            store.update_goal(goal["id"], {"consented": False})
            blank = store.update_goal(goal["id"], {"progress_note": "新进展"})
            self.assertEqual(blank["progress_note"], "")

    def test_validation_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = _store(directory)
            with self.assertRaises(ValueError):
                store.add_goal("")
            with self.assertRaises(ValueError):
                store.update_settings({"frequency_minutes": 1})
            with self.assertRaises(ValueError):
                store.update_settings({"quiet_hours": [{"start": "25:00", "end": "26:00"}]})
            goal = store.add_goal("目标A")
            with self.assertRaises(ValueError):
                store.update_goal(goal["id"], {"status": "archived"})

    def test_roundtrip_persists_settings_goals_and_actions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = _store(directory)
            store.update_settings({"enabled": True, "frequency_minutes": 30})
            goal = store.add_goal("持久化目标")
            store.respond(goal["id"], "decline")
            store.save()
            reloaded = ProposalStore(Path(directory) / "proposals.json")
            self.assertTrue(reloaded.get_settings()["enabled"])
            self.assertEqual(reloaded.get_settings()["frequency_minutes"], 30)
            self.assertEqual(len(reloaded.list_goals()), 1)
            # decline 后的目标在冷却内不会被再次提议
            self.assertIsNone(reloaded.pending_proposal(now=_now()))

    def test_shared_goal_roundtrip(self) -> None:
        goal = SharedGoal.from_dict(
            {
                "title": "目标",
                "description": "说明",
                "status": "paused",
                "progress_note": "进展",
                "consented": False,
            }
        )
        payload = goal.to_dict()
        self.assertEqual(payload["status"], "paused")
        self.assertEqual(payload["consented"], False)
        restored = SharedGoal.from_dict(payload)
        self.assertEqual(restored.title, "目标")


if __name__ == "__main__":
    unittest.main()
