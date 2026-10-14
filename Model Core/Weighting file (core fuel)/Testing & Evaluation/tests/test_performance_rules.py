"""B 组遗留 E 轮：演出规则可配置 UI 的后端校验与读写端点测试。"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import api


def valid_rules() -> dict:
    return {
        "version": 1,
        "purpose": "测试用演出规则",
        "semantic_actions": [
            {"cue": "提问 / 疑问", "motion": "思考（侧头 + 手托下巴）", "timing": "提问后约 0.3s"},
            {"cue": "惊喜 / 反转", "motion": "拍手", "timing": "反转点"},
        ],
        "stage_rules": ["人物放置在画面右侧", "动作跟随语义走"],
        "layered_parts": [
            {"part": "眼睛", "usage": "开合 / 眨眼", "layers": "1"},
            {"part": "手部", "usage": "抬手 / 摊手 / 拍手", "layers": "2"},
        ],
        "mouth_curve": {
            "mode": "volume_based",
            "rule": "有声音时小幅开口，停顿时闭嘴",
            "recompute": "换配音后重算口型开合曲线",
        },
    }


class ValidatePerformanceRulesTest(unittest.TestCase):
    """校验函数：合法通过、坏类型/缺字段/超长拒绝、规范化保留字段。"""

    def test_accepts_full_rules(self) -> None:
        normalized = api.validate_performance_rules(valid_rules())
        self.assertEqual(len(normalized["semantic_actions"]), 2)
        self.assertEqual(normalized["stage_rules"][0], "人物放置在画面右侧")
        self.assertEqual(normalized["layered_parts"][1]["layers"], "2")
        self.assertEqual(normalized["mouth_curve"]["mode"], "volume_based")

    def test_rejects_non_object_root(self) -> None:
        with self.assertRaises(ValueError):
            api.validate_performance_rules([])

    def test_rejects_semantic_actions_not_list(self) -> None:
        rules = valid_rules()
        rules["semantic_actions"] = "not-a-list"
        with self.assertRaises(ValueError):
            api.validate_performance_rules(rules)

    def test_rejects_missing_action_field(self) -> None:
        rules = valid_rules()
        rules["semantic_actions"][0].pop("cue")
        with self.assertRaises(ValueError):
            api.validate_performance_rules(rules)

    def test_rejects_overlong_text(self) -> None:
        rules = valid_rules()
        rules["stage_rules"] = ["x" * 201]
        with self.assertRaises(ValueError):
            api.validate_performance_rules(rules)

    def test_rejects_layers_non_string(self) -> None:
        rules = valid_rules()
        rules["layered_parts"][0]["layers"] = 2
        with self.assertRaises(ValueError):
            api.validate_performance_rules(rules)

    def test_rejects_too_many_actions(self) -> None:
        rules = valid_rules()
        rules["semantic_actions"] = [{"cue": "c", "motion": "m", "timing": "t"}] * 101
        with self.assertRaises(ValueError):
            api.validate_performance_rules(rules)


class PerformanceRulesEndpointTest(unittest.TestCase):
    """GET/PUT 端点：临时目录替换路径，验证读写闭环与非法请求拒绝。"""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.rules_path = Path(self.temp.name) / "performance_rules.json"
        self.patcher = patch("api.performance_rules_path", return_value=self.rules_path)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.addCleanup(self.temp.cleanup)

    def _send(self, handler: api.ApiHandler, path: str, body: str = "") -> None:
        handler.path = path
        handler.headers = {"Content-Length": str(len(body.encode("utf-8")))}
        if body:
            handler.rfile = type(
                "R",
                (),
                {"read": lambda self, n: body.encode("utf-8")[:n]},
            )()
        handler._send_json = lambda status, payload: None
        handler.send_error = lambda status, message=None: None
        if body:
            handler.do_PUT()
        else:
            handler.do_GET()

    def test_get_returns_saved_rules(self) -> None:
        self.rules_path.write_text(json.dumps(valid_rules()), encoding="utf-8")
        handler = api.ApiHandler.__new__(api.ApiHandler)
        seen = {}
        handler._send_json = lambda status, payload: seen.update(
            {"status": status, "payload": payload}
        )
        handler.path = "/v1/performance/rules"
        handler.do_GET()
        self.assertEqual(seen["payload"]["semantic_actions"][0]["cue"], "提问 / 疑问")

    def test_get_missing_file_returns_not_found(self) -> None:
        handler = api.ApiHandler.__new__(api.ApiHandler)
        seen = {}
        handler._send_json = lambda status, payload: seen.update(
            {"status": status, "payload": payload}
        )
        handler.path = "/v1/performance/rules"
        handler.do_GET()
        self.assertEqual(seen["status"].value, 404)

    def test_put_roundtrip_preserves_structure(self) -> None:
        handler = api.ApiHandler.__new__(api.ApiHandler)
        seen = {}
        handler._send_json = lambda status, payload: seen.update(
            {"status": status, "payload": payload}
        )
        handler.path = "/v1/performance/rules"
        handler.headers = {"Content-Length": str(len(json.dumps(valid_rules())))}
        handler.rfile = type(
            "R",
            (),
            {"read": lambda self, n: json.dumps(valid_rules()).encode("utf-8")[:n]},
        )()
        handler.do_PUT()
        self.assertEqual(seen["status"].value, 200)
        self.assertIn("updated", seen["payload"])
        saved = json.loads(self.rules_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["semantic_actions"][1]["motion"], "拍手")
        self.assertEqual(len(saved["layered_parts"]), 2)

    def test_put_rejects_invalid_rules(self) -> None:
        handler = api.ApiHandler.__new__(api.ApiHandler)
        seen = {}
        handler._send_json = lambda status, payload: seen.update(
            {"status": status, "payload": payload}
        )
        handler.path = "/v1/performance/rules"
        bad = valid_rules()
        bad["stage_rules"] = "not-a-list"
        body = json.dumps(bad)
        handler.headers = {"Content-Length": str(len(body))}
        handler.rfile = type("R", (), {"read": lambda self, n: body.encode("utf-8")[:n]})()
        handler.do_PUT()
        self.assertEqual(seen["status"].value, 400)
        self.assertFalse(self.rules_path.exists())


if __name__ == "__main__":
    unittest.main()

