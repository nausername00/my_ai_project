"""draw_portrait（墨灵试画）工具测试。

不连接真实 ComfyUI：全部 mock 客户端，覆盖参数校验、成功保存、
默认种子回退、ComfyUI 失败降级与目录自动创建。
"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent_tools import execute_project_tool

FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


class FakeClient:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def generate(self, workflow, timeout_seconds=300.0):
        return [{"filename": "fake.png", "subfolder": "", "type": "output"}]

    def fetch_image(self, ref):
        return FAKE_PNG


class FakeFailClient(FakeClient):
    def generate(self, workflow, timeout_seconds=300.0):
        from comfyui_client import ComfyUIError

        raise ComfyUIError("无法连接本机 ComfyUI（模拟）")


class DrawPortraitTests(unittest.TestCase):
    def _patch_client(self, client_cls=FakeClient):
        patcher = mock.patch("comfyui_client.ComfyUIClient", client_cls)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _root(self) -> Path:
        directory = tempfile.mkdtemp()
        return Path(directory)

    def test_rejects_invalid_arguments(self) -> None:
        root = self._root()
        cases = (
            ({"count": 0}, "count 越界（0）"),
            ({"count": 4}, "count 越界（4）"),
            ({"count": "2"}, "count 非整数"),
            ({"style_prompt": 123}, "style_prompt 非字符串"),
            ({"style_prompt": "x" * 2001}, "style_prompt 超长"),
            ({"seed_base": "abc"}, "seed_base 非整数"),
            ({"unknown": 1}, "未知参数"),
        )
        for arguments, label in cases:
            with self.subTest(label=label):
                with self.assertRaises(ValueError):
                    execute_project_tool(root, "draw_portrait", arguments)

    def test_generates_drafts_into_character_drafts_dir(self) -> None:
        self._patch_client()
        root = self._root()
        result = execute_project_tool(
            root,
            "draw_portrait",
            {"count": 2, "seed_base": 7},
        )
        self.assertEqual(result["tool"], "draw_portrait")
        self.assertEqual(result["count"], 2)
        seeds = [draft["seed"] for draft in result["drafts"]]
        self.assertEqual(seeds, [7, 8])
        for draft in result["drafts"]:
            target = root / draft["path"]
            self.assertTrue(target.is_file())
            self.assertEqual(target.read_bytes(), FAKE_PNG)
            self.assertTrue(draft["path"].startswith("Character/K1 Portrait/drafts/"))

    def test_default_seed_falls_back_to_recommended_list(self) -> None:
        self._patch_client()
        root = self._root()
        result = execute_project_tool(root, "draw_portrait", {})
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["drafts"][0]["seed"], 20261031)

    def test_comfyui_failure_returns_error_without_raising(self) -> None:
        self._patch_client(FakeFailClient)
        root = self._root()
        result = execute_project_tool(root, "draw_portrait", {})
        self.assertIn("error", result)
        self.assertIn("无法连接", result["error"])
        self.assertIn("hint", result)

    def test_creates_drafts_dir_automatically(self) -> None:
        self._patch_client()
        root = self._root()  # 空目录，无 Character 结构
        result = execute_project_tool(root, "draw_portrait", {"count": 1})
        self.assertEqual(result["count"], 1)
        self.assertTrue((root / "Character" / "K1 Portrait" / "drafts").is_dir())


if __name__ == "__main__":
    unittest.main()
