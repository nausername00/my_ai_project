import unittest

from brain import create_brain_plan, validate_brain_plan, verify_tool_observation


class BrainPlanTests(unittest.TestCase):
    def test_validates_structured_plan_and_risk_boundaries(self) -> None:
        plan = validate_brain_plan(
            {
                "intent": "learn",
                "summary": "先拆解翻译器的学习目标",
                "steps": [
                    {
                        "title": "阅读现有实现",
                        "action": "整理输入、模型和输出边界",
                        "risk": "local_reversible",
                        "tool": "list_project_files",
                        "arguments": {"path": "."},
                        "success_criteria": "返回项目文件列表",
                    },
                    {
                        "title": "联网查资料",
                        "action": "先请求用户许可再搜索",
                        "risk": "requires_permission",
                        "tool": None,
                        "arguments": {},
                        "success_criteria": "获得明确许可",
                    },
                ],
                "memory_candidates": ["学习翻译器架构"],
                "reflection_question": "是否能用测试证明改进有效？",
            }
        )
        self.assertEqual(plan.intent, "learn")
        self.assertEqual(plan.steps[1]["risk"], "requires_permission")

    def test_rejects_unvalidated_tool_risk(self) -> None:
        with self.assertRaises(ValueError):
            validate_brain_plan(
                {
                    "intent": "create",
                    "summary": "做事",
                    "steps": [
                        {
                            "title": "执行",
                            "action": "直接改文件",
                            "risk": "safe",
                            "tool": None,
                            "arguments": {},
                            "success_criteria": "文件改变",
                        },
                    ],
                    "memory_candidates": [],
                    "reflection_question": "有效吗？",
                }
            )

    def test_rejects_unavailable_or_mutating_plan_tools(self) -> None:
        for tool, arguments in (
            ("write_project_file", {"path": "note.txt", "content": "text"}),
            ("run_tests", {"command": ["py", "-m", "pytest"]}),
            ("read_project_file", {"path": "README.md", "unexpected": True}),
            ("create_project_file", {"path": "note.md", "content": "text"}),
        ):
            with self.subTest(tool=tool):
                with self.assertRaises(ValueError):
                    validate_brain_plan(
                        {
                            "intent": "create",
                            "summary": "检查计划工具边界",
                            "steps": [
                                {
                                    "title": "尝试不支持的工具",
                                    "action": "执行工具",
                                    "risk": "local_reversible",
                                    "tool": tool,
                                    "arguments": arguments,
                                    "success_criteria": "请求被拒绝",
                                },
                            ],
                            "memory_candidates": [],
                            "reflection_question": "工具范围是否明确？",
                        }
                    )

    def test_accepts_new_file_creation_only_with_permission_risk(self) -> None:
        plan = validate_brain_plan(
            {
                "intent": "create",
                "summary": "新建一份阶段建议",
                "steps": [
                    {
                        "title": "创建建议文件",
                        "action": "在用户确认后新建文件",
                        "risk": "requires_permission",
                        "tool": "create_project_file",
                        "arguments": {
                            "path": "成果/阶段建议.md",
                            "content": "优先完善本地视觉授权体验。",
                        },
                        "success_criteria": "文件新建且回读内容一致",
                    },
                ],
                "memory_candidates": [],
                "reflection_question": "成果是否符合预期？",
            }
        )
        self.assertEqual(plan.steps[0]["tool"], "create_project_file")
        self.assertEqual(plan.steps[0]["risk"], "requires_permission")

        with self.assertRaisesRegex(ValueError, "requires_permission"):
            validate_brain_plan(
                {
                    "intent": "create",
                    "summary": "错误风险标记",
                    "steps": [
                        {
                            "title": "创建建议文件",
                            "action": "创建文件",
                            "risk": "local_reversible",
                            "tool": "create_project_file",
                            "arguments": {"path": "note.md", "content": "text"},
                            "success_criteria": "文件存在",
                        },
                    ],
                    "memory_candidates": [],
                    "reflection_question": "风险是否正确？",
                }
            )

    def test_rejects_arguments_without_a_tool(self) -> None:
        with self.assertRaises(ValueError):
            validate_brain_plan(
                {
                    "intent": "learn",
                    "summary": "检查参数一致性",
                    "steps": [
                        {
                            "title": "无工具步骤",
                            "action": "说明下一步",
                            "risk": "requires_permission",
                            "tool": None,
                            "arguments": {"path": "README.md"},
                            "success_criteria": "没有执行工具",
                        },
                    ],
                    "memory_candidates": [],
                    "reflection_question": "步骤是否清楚？",
                }
            )

    def test_model_json_is_parsed_without_executing_steps(self) -> None:
        class FakeEngine:
            model_name = "fake-local"

            def __init__(self) -> None:
                self.calls = 0

            def generate(self, request):
                self.calls += 1
                return (
                    '{"intent":"review","summary":"检查当前方案",'
                    '"steps":[{"title":"检查代码","action":"列出测试缺口",'
                    '"risk":"local_reversible","tool":null,"arguments":{},'
                    '"success_criteria":"列出测试缺口"}],"memory_candidates":[],'
                    '"reflection_question":"哪些测试能证明改进有效？"}'
                )

        engine = FakeEngine()
        plan = create_brain_plan(engine, "墨灵系统提示", "检查翻译器")
        self.assertEqual(engine.calls, 1)
        self.assertEqual(plan.steps[0]["risk"], "local_reversible")
        self.assertIsNone(plan.steps[0]["tool"])

    def test_verifies_only_observed_evidence(self) -> None:
        class FakeEngine:
            model_name = "fake-local"

            def generate(self, request):
                self.request = request
                return '{"status":"confirmed","evidence":"返回了 3 个文件条目"}'

        engine = FakeEngine()
        result = verify_tool_observation(
            engine,
            "角色提示",
            "查看项目",
            "返回非空文件列表",
            {"entries": ["a.py", "b.py", "c.py"]},
        )
        self.assertEqual(result["status"], "confirmed")
        self.assertIn("不可信数据", engine.request.prompt)
