import unittest

from agent import route_cognition


class CognitiveRoutingTests(unittest.TestCase):
    def test_routes_open_ended_ideas_to_divergent_exploration(self) -> None:
        route = route_cognition("还有什么不同方向可以补充？")

        self.assertEqual(route.mode, "divergent")
        self.assertIn("彼此不同", route.instruction)

    def test_routes_requests_to_reverse_review_to_critical_mode(self) -> None:
        route = route_cognition("请反过来审视这个方案的风险")

        self.assertEqual(route.mode, "critical")
        self.assertIn("反例", route.instruction)

    def test_routes_explicit_reverse_thinking_to_critical_mode(self) -> None:
        route = route_cognition("请进行反思维检查")

        self.assertEqual(route.mode, "critical")

    def test_routes_distress_to_care_without_unrequested_problem_solving(self) -> None:
        route = route_cognition("我最近很孤独")

        self.assertEqual(route.mode, "care")
        self.assertIn("不把倾诉自动改造成问题清单", route.instruction)

    def test_regular_chat_stays_in_direct_mode(self) -> None:
        route = route_cognition("今天天气不错。")

        self.assertEqual(route.mode, "direct")
        self.assertIn("直接回应", route.instruction)

    def test_respects_a_request_not_to_expand(self) -> None:
        route = route_cognition("不要发散，直接回答我这个问题")

        self.assertEqual(route.mode, "direct")
