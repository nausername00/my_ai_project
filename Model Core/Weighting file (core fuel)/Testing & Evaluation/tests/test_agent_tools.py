import tempfile
import unittest
from pathlib import Path

from agent_tools import execute_project_tool


class AgentToolTests(unittest.TestCase):
    def test_lists_workspace_files_and_excludes_sensitive_and_build_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text("print('ok')", encoding="utf-8")
            (root / ".env").write_text("TOKEN=secret", encoding="utf-8")
            (root / "credentials.json").write_text("{}", encoding="utf-8")
            (root / "node_modules").mkdir()
            (root / "node_modules" / "dependency.js").write_text("", encoding="utf-8")

            result = execute_project_tool(root, "list_project_files", {"path": "."})

        paths = {entry["path"] for entry in result["entries"]}
        self.assertEqual(paths, {"src"})
        self.assertFalse(result["truncated"])

    def test_reads_utf8_project_text_within_size_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "notes.md"
            target.write_text("墨灵学习计划", encoding="utf-8")

            result = execute_project_tool(
                root,
                "read_project_file",
                {"path": "notes.md"},
            )

        self.assertEqual(result["content"], "墨灵学习计划")
        self.assertEqual(result["path"], "notes.md")

    def test_creates_new_utf8_file_and_verifies_read_back(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "成果").mkdir()
            content = "墨灵的小小成果\n本地优先"

            result = execute_project_tool(
                root,
                "create_project_file",
                {"path": "成果/阶段建议.md", "content": content},
            )

            created_file = root / "成果" / "阶段建议.md"
            self.assertEqual(created_file.read_text(encoding="utf-8"), content)
            self.assertTrue(result["created"])
            self.assertEqual(result["path"], "成果/阶段建议.md")
            self.assertEqual(result["verification"]["status"], "confirmed")
            self.assertTrue(result["verification"]["content_matches"])

    def test_create_tool_never_overwrites_and_rejects_unsafe_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            existing = root / "existing.md"
            existing.write_text("保留原内容", encoding="utf-8")
            (root / ".env").write_text("SECRET=x", encoding="utf-8")
            (root / "node_modules").mkdir()
            for path, content in (
                ("existing.md", "覆盖"),
                ("../outside.md", "越界"),
                (".env", "密钥"),
                (".hidden.md", "隐藏目标"),
                ("image.png", "不是允许的文本类型"),
                ("node_modules/file.md", "排除目录"),
                ("missing/file.md", "不自动创建父目录"),
            ):
                with self.subTest(path=path):
                    with self.assertRaises(ValueError):
                        execute_project_tool(
                            root,
                            "create_project_file",
                            {"path": path, "content": content},
                        )
            self.assertEqual(existing.read_text(encoding="utf-8"), "保留原内容")

    def test_create_tool_rejects_symlinked_parent_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "project"
            root.mkdir()
            outside = Path(directory) / "outside"
            outside.mkdir()
            link = root / "linked"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest("symlink creation is unavailable")
            with self.assertRaisesRegex(ValueError, "symbolic links"):
                execute_project_tool(
                    root,
                    "create_project_file",
                    {"path": "linked/escaped.md", "content": "must not escape"},
                )

    def test_create_tool_rejects_invalid_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for arguments in (
                {"path": "new.md", "content": ""},
                {"path": "new.md", "content": "x" * 4001},
                {"path": "new.md", "content": "body", "mkdir": True},
                {"path": "folder/../new.md", "content": "traversal"},
                {"path": "C:relative.md", "content": "drive-relative"},
                {"path": "notes.md:stream", "content": "alternate stream"},
                {"path": "CON.md", "content": "reserved name"},
                {"path": "notes.md.", "content": "trailing dot"},
                {"path": "new.md", "content": "\ud800"},
            ):
                with self.subTest(arguments=arguments):
                    with self.assertRaises(ValueError):
                        execute_project_tool(root, "create_project_file", arguments)

    def test_rejects_traversal_absolute_sensitive_binary_and_write_tools(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.md").write_text("ok", encoding="utf-8")
            (root / ".env").write_text("secret", encoding="utf-8")
            (root / "image.png").write_bytes(b"binary")
            outside = Path(directory).parent / "outside.md"
            outside.write_text("outside", encoding="utf-8")
            try:
                for tool, arguments in (
                    ("read_project_file", {"path": "../outside.md"}),
                    ("read_project_file", {"path": str(outside)}),
                    ("read_project_file", {"path": ".env"}),
                    ("read_project_file", {"path": "image.png"}),
                    ("write_file", {"path": "notes.md", "content": "change"}),
                ):
                    with self.subTest(tool=tool, arguments=arguments):
                        with self.assertRaises(ValueError):
                            execute_project_tool(root, tool, arguments)
            finally:
                outside.unlink(missing_ok=True)

    def test_rejects_symlinks_that_escape_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "project"
            root.mkdir()
            outside = Path(directory) / "outside.md"
            outside.write_text("outside", encoding="utf-8")
            link = root / "escape.md"
            try:
                link.symlink_to(outside)
            except OSError:
                self.skipTest("symlink creation is unavailable")
            with self.assertRaises(ValueError):
                execute_project_tool(root, "read_project_file", {"path": "escape.md"})
