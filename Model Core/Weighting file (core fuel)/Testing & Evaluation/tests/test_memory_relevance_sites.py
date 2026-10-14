"""E6 扩展：记忆相关性注入已覆盖全部生成调用点（防新增/遗漏回归）。

主对话（E6 原接入）之外的协作、计划、验证、自我复盘与探索提议场景
都应把当前文本传入 build_system_prompt(context_text=...)，否则这些场景
回退「最近 20 条」而非相关性排序注入。
"""

import re
import unittest
from pathlib import Path

ENGINE_DIR = (
    Path(__file__).resolve().parent.parent.parent / "Source code engine"
)


def _has_context_text(source: str, call_start: int) -> bool:
    """build_system_prompt( 调用起 600 字符内是否出现 context_text=。"""
    return "context_text=" in source[call_start : call_start + 600]


class RelevanceInjectionSitesTest(unittest.TestCase):
    """所有 build_system_prompt 调用点都必须携带 context_text=。"""

    def test_api_sites_all_pass_context_text(self) -> None:
        source = (ENGINE_DIR / "api.py").read_text(encoding="utf-8")
        positions = [
            match.start()
            for match in re.finditer(r"build_system_prompt\(", source)
        ]
        # api.py 现有 6 处调用（主对话 + 协作/计划/验证/复盘扩展）
        self.assertGreaterEqual(len(positions), 6)
        for position in positions:
            self.assertTrue(
                _has_context_text(source, position),
                msg=f"api.py 调用点 offset={position} 未传 context_text",
            )

    def test_explore_site_passes_context_text(self) -> None:
        source = (ENGINE_DIR / "explore.py").read_text(encoding="utf-8")
        positions = [
            match.start()
            for match in re.finditer(r"build_system_prompt\(", source)
        ]
        self.assertEqual(len(positions), 1)
        self.assertTrue(_has_context_text(source, positions[0]))


if __name__ == "__main__":
    unittest.main()
