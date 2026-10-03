"""Tests for the CORE_WORLD explore vertical slice."""

import json
import os
import tempfile
import unittest
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread
from unittest.mock import patch
from xml.etree import ElementTree

from app import create_server
from explore import (
    propose_exploration,
    record_exploration_reaction,
    run_exploration,
)
from inference import InferenceEngine
from character import CharacterStore


class ExploreModuleTests(unittest.TestCase):
    def test_propose_detects_interest(self) -> None:
        proposal = propose_exploration("我最近好喜欢画画，想试试看水彩")
        self.assertTrue(proposal["proposed"])
        self.assertIn("画", proposal["topic"])
        self.assertEqual(proposal["try_kind"], "cover_svg")

    def test_propose_ignores_small_talk(self) -> None:
        proposal = propose_exploration("你好，今天天气不错")
        self.assertFalse(proposal["proposed"])

    def test_run_creates_svg_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = CharacterStore(
                str(Path(tmp) / "characters" / "default.json"),
                str(Path(tmp) / "memory.json"),
                str(Path(tmp) / "assets"),
            )
            engine = InferenceEngine()
            result = run_exploration(
                "我喜欢星空摄影",
                topic="星空摄影",
                engine=engine,
                character_store=store,
                record_memory=True,
            )
        self.assertFalse(result["failed"])
        self.assertEqual(result["feedback_intent"], "share_win")
        self.assertIsNotNone(result["artifact"])
        svg_root = ElementTree.fromstring(result["artifact"]["content"])
        self.assertEqual(svg_root.tag, "{http://www.w3.org/2000/svg}svg")
        self.assertIn("想听", result["feedback_intent_label"])

    def test_react_praise_writes_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = CharacterStore(
                str(Path(tmp) / "characters" / "default.json"),
                str(Path(tmp) / "memory.json"),
                str(Path(tmp) / "assets"),
            )
            reacted = record_exploration_reaction(
                topic="画画",
                reaction="praise",
                character_store=store,
                note="配色好看",
            )
            memories = store.list_memories()
        self.assertIsNotNone(reacted["memory"])
        self.assertTrue(any("探索反馈" in m["content"] for m in memories))


class ExploreApiTests(unittest.TestCase):
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

    def _post(self, path: str, body: dict) -> tuple[int, dict]:
        conn = self.connection
        conn.request(
            "POST",
            path,
            json.dumps(body, ensure_ascii=False).encode("utf-8"),
            {"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        data = json.loads(response.read())
        response.read()
        return response.status, data

    def test_generate_includes_explore_proposal(self) -> None:
        status, data = self._post(
            "/v1/generate",
            {"prompt": "我超爱听爵士乐，最近迷上了", "max_tokens": 32},
        )
        self.assertEqual(status, 200)
        self.assertIsNotNone(data.get("explore_proposal"))
        self.assertTrue(data["explore_proposal"]["proposed"])

    def test_explore_run_endpoint(self) -> None:
        status, data = self._post(
            "/v1/explore/run",
            {"message": "我喜欢烘焙", "topic": "烘焙"},
        )
        self.assertEqual(status, 200)
        self.assertIn("artifact", data)
        self.assertIn("feedback_intent", data)


if __name__ == "__main__":
    unittest.main()
