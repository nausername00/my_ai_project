"""Tests for the discovery learning loop (file curiosity + context praise)."""

import tempfile
import unittest
from pathlib import Path

from discovery import PermissionDenied, discover_file, observe_context
from inference import InferenceEngine
from character import CharacterStore


class DiscoveryModuleTests(unittest.TestCase):
    def _store(self, tmp):
        return CharacterStore(
            str(Path(tmp) / "characters" / "default.json"),
            str(Path(tmp) / "memory.json"),
            str(Path(tmp) / "assets"),
        )

    def test_discover_file_requires_permission(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            engine = InferenceEngine()
            with self.assertRaises(PermissionDenied):
                discover_file("note.txt", "text", "hello", engine, store, approved=False)

    def test_discover_file_curious_feedback_and_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            engine = InferenceEngine()
            result = discover_file(
                "blender 学习笔记.txt",
                "text",
                "今天学会了用 blender 建模一个杯子",
                engine,
                store,
                approved=True,
            )
        self.assertIn("feedback", result)
        self.assertTrue(result["feedback"])
        # 发现可尝试内容 → 惊喜情绪 + 提议做一次 mini 尝试
        self.assertEqual(result["affect"]["mood"], "surprised")
        self.assertEqual(result["memory"]["source"], "discovery")
        self.assertIn("blender", result["memory"]["content"])
        self.assertTrue(result["explore_proposal"]["proposed"])
        self.assertIn("blender", result["explore_proposal"]["topic"])

    def test_discover_image_without_perception_is_honest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            engine = InferenceEngine()
            result = discover_file(
                "photo.png",
                "image",
                "",
                engine,
                store,
                approved=True,
            )
        self.assertEqual(result["affect"]["mood"], "curious")
        self.assertFalse(result["explore_proposal"]["proposed"])
        self.assertTrue(result["feedback"])

    def test_observe_context_requires_permission(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            engine = InferenceEngine()
            with self.assertRaises(PermissionDenied):
                observe_context("webpage", "text", engine, store, approved=False)

    def test_observe_context_praises_and_remembers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            engine = InferenceEngine()
            result = observe_context(
                "webpage",
                "这是一个简洁的网页，标题清晰，配色舒服",
                engine,
                store,
                approved=True,
            )
        self.assertTrue(result["feedback"])
        self.assertEqual(result["kind"], "webpage")
        self.assertEqual(result["memory"]["source"], "discovery")


if __name__ == "__main__":
    unittest.main()
