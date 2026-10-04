"""Tests for the external partner review circle (GPT / DeepSeek / Qwen + local)."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from inference import InferenceEngine
from character import CharacterStore
from partners import (
    EXTERNAL_PARTNERS,
    build_moling_profile,
    evaluate_molings,
    list_partner_status,
)


class PartnerReviewTests(unittest.TestCase):
    def _store(self, tmp):
        return CharacterStore(
            str(Path(tmp) / "characters" / "default.json"),
            str(Path(tmp) / "memory.json"),
            str(Path(tmp) / "assets"),
        )

    def test_external_partners_are_disabled_without_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            engine = InferenceEngine()
            status = list_partner_status(engine)
        self.assertEqual(status["local_model"], "placeholder")
        externals = [p for p in status["partners"] if p["source"] == "external"]
        self.assertEqual(len(externals), len(EXTERNAL_PARTNERS))
        for partner in externals:
            self.assertFalse(partner["enabled"])
            self.assertEqual(partner["status"], "disabled")
            self.assertIn("API Key", partner["reason"])

    def test_external_partner_enabled_when_key_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            engine = InferenceEngine()
            with patch.dict(
                os.environ,
                {"PARTNER_DEEPSEEK_API_KEY": "sk-test"},
            ):
                status = list_partner_status(engine)
        deepseek = next(
            p for p in status["partners"] if p["id"] == "deepseek"
        )
        self.assertTrue(deepseek["enabled"])
        self.assertEqual(deepseek["model"], "deepseek-chat")

    def test_build_profile_contains_core_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            store.add_memory("今天学了 blender 建模", "user", "model")
            profile = build_moling_profile(store)
        self.assertIn("nickname", profile)
        self.assertIn("agent_reflection", profile)
        self.assertIn("core_values", profile)
        self.assertEqual(profile["memory_count"], 1)

    def test_evaluate_runs_locally_and_skips_external(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            engine = InferenceEngine()
            result = evaluate_molings("all", engine, store)
        self.assertEqual(result["scope"], "all")
        self.assertTrue(result["profile"]["nickname"])
        local = next(r for r in result["partners"] if r["id"] == "local")
        self.assertEqual(local["status"], "completed")
        self.assertIn("verdict", local)
        disabled = [r for r in result["partners"] if r["status"] == "disabled"]
        self.assertEqual(len(disabled), len(EXTERNAL_PARTNERS))
        self.assertTrue(result["synthesis"])

    def test_parse_review_extracts_sections(self) -> None:
        from partners import _parse_review

        text = (
            "总评：很有潜力，7.5/10\n"
            "亮点：\n1) 角色设定自洽\n2) 权限设计克制\n"
            "缺口：\n1) 缺少长期记忆的沉淀机制\n"
            "建议：\n1) 增加每周复盘"
        )
        parsed = _parse_review(text)
        self.assertEqual(parsed["verdict"], "很有潜力，7.5/10")
        self.assertIn("角色设定自洽", parsed["highlights"])
        self.assertIn("缺少长期记忆的沉淀机制", parsed["gaps"])
        self.assertIn("增加每周复盘", parsed["suggestions"])


if __name__ == "__main__":
    unittest.main()
