"""E11 角色数据一键备份（第 8 层基础设施最轻形态）测试。"""

import json
import tempfile
import unittest
from pathlib import Path

import api
from backup import backup_character_data


def _make_data(root: Path) -> None:
    """造一份最小角色数据：记忆 / 情绪 / 角色卡 / 演出规则。"""
    (root / "memory.json").write_text(
        json.dumps({"entries": [{"id": "m1", "content": "用户喜欢简洁回复"}]}),
        encoding="utf-8",
    )
    (root / "affect.json").write_text(
        json.dumps({"mode": "simulated", "mood": "calm"}), encoding="utf-8"
    )
    characters = root / "characters"
    characters.mkdir()
    (characters / "default.json").write_text(
        json.dumps({"name": "墨灵"}), encoding="utf-8"
    )
    rules = root / "Docs & Compliance"
    rules.mkdir(parents=True)
    (rules / "performance_rules.json").write_text(
        json.dumps({"semantic_actions": []}), encoding="utf-8"
    )


class BackupCharacterDataTest(unittest.TestCase):
    """备份：文件齐全、时间戳目录唯一、空数据报错、端点形状。"""

    def test_backs_up_core_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "data"
            data.mkdir()
            _make_data(data)
            backup_root = root / "backups"
            result = backup_character_data(
                data,
                backup_root,
                extra_files=["Docs & Compliance/performance_rules.json"],
            )
            self.assertIn("memory.json", result["files"])
            self.assertIn("affect.json", result["files"])
            self.assertIn("characters/", result["files"])
            self.assertIn("Docs & Compliance/performance_rules.json", result["files"])
            target = Path(result["backup_dir"])
            self.assertTrue((target / "memory.json").is_file())
            self.assertTrue((target / "characters" / "default.json").is_file())
            self.assertTrue(
                (target / "Docs & Compliance" / "performance_rules.json").is_file()
            )

    def test_repeated_backups_do_not_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "data"
            data.mkdir()
            (data / "memory.json").write_text("{}", encoding="utf-8")
            backup_root = root / "backups"
            first = backup_character_data(data, backup_root)
            second = backup_character_data(data, backup_root)
            self.assertNotEqual(first["backup_dir"], second["backup_dir"])
            self.assertEqual(len(list(backup_root.iterdir())), 2)

    def test_empty_data_raises(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "data"
            data.mkdir()
            with self.assertRaises(ValueError):
                backup_character_data(data, root / "backups")

    def test_backup_endpoint_shape(self) -> None:
        handler = api.ApiHandler.__new__(api.ApiHandler)
        seen = {}
        handler._send_json = lambda status, payload: seen.update(
            {"status": status, "payload": payload}
        )
        handler.path = "/v1/backup/create"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "data"
            data.mkdir()
            _make_data(data)
            handler.character_root = data
            handler.backup_root = root / "backups"
            handler.do_POST()
        self.assertEqual(seen["status"].value, 200)
        self.assertIn("backup_dir", seen["payload"])
        self.assertGreaterEqual(seen["payload"]["count"], 1)
        self.assertIn("memory.json", seen["payload"]["files"])


if __name__ == "__main__":
    unittest.main()
