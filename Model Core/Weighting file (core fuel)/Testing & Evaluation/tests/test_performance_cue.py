"""E8 演出规则消费：语义 cue 分类、规则匹配与 /v1/performance/cue 端点测试。"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import api
from performance import (
    classify_semantic_cue,
    enrich_caption_tracks,
    load_performance_rules,
    match_semantic_action,
)

DEFAULT_ACTIONS = [
    {"cue": "提问 / 疑问", "motion": "思考（侧头 + 手托下巴）", "timing": "提问后约 0.3s"},
    {"cue": "惊喜 / 反转", "motion": "拍手", "timing": "反转点"},
    {"cue": "强调 / 停顿", "motion": "停半拍", "timing": "重点句之前"},
]


def rules_with(actions=None):
    return {
        "version": 1,
        "semantic_actions": actions if actions is not None else DEFAULT_ACTIONS,
        "stage_rules": [],
        "layered_parts": [],
        "mouth_curve": {},
    }


class ClassifySemanticCueTest(unittest.TestCase):
    """分类：问句/感叹/强调/讲解/中性/空文本。"""

    def test_question_forms(self) -> None:
        self.assertEqual(classify_semantic_cue("你会画画吗？"), "提问 / 疑问")
        self.assertEqual(classify_semantic_cue("怎么做到的"), "提问 / 疑问")
        self.assertEqual(classify_semantic_cue("why does it rain"), "提问 / 疑问")
        self.assertEqual(classify_semantic_cue("能否帮我看看"), "提问 / 疑问")

    def test_surprise_forms(self) -> None:
        self.assertEqual(classify_semantic_cue("太棒了！"), "惊喜 / 反转")
        self.assertEqual(classify_semantic_cue("哇 居然成功了"), "惊喜 / 反转")

    def test_emphasis_forms(self) -> None:
        self.assertEqual(classify_semantic_cue("记住这个重点"), "强调 / 停顿")
        self.assertEqual(classify_semantic_cue("注意安全"), "强调 / 停顿")

    def test_explanation_forms(self) -> None:
        self.assertEqual(classify_semantic_cue("帮我讲解一下"), "讲解要点")
        self.assertEqual(classify_semantic_cue("科普一下"), "讲解要点")

    def test_neutral_and_empty(self) -> None:
        self.assertIsNone(classify_semantic_cue("好的 谢谢"))
        self.assertIsNone(classify_semantic_cue(""))
        self.assertIsNone(classify_semantic_cue(None))  # type: ignore[arg-type]


class MatchSemanticActionTest(unittest.TestCase):
    """匹配：cue 键头词与条目 cue 文本子串命中；未命中返回 None。"""

    def test_matches_default_cue(self) -> None:
        action = match_semantic_action(rules_with(), "提问 / 疑问")
        self.assertIsNotNone(action)
        self.assertIn("思考", action["motion"])

    def test_matches_rewritten_cue(self) -> None:
        rules = rules_with(
            [{"cue": "用户提问时", "motion": "托腮思考", "timing": "0.5s"}]
        )
        action = match_semantic_action(rules, "提问 / 疑问")
        self.assertEqual(action["motion"], "托腮思考")

    def test_no_cue_or_empty_rules(self) -> None:
        self.assertIsNone(match_semantic_action(rules_with(), None))
        self.assertIsNone(match_semantic_action(None, "提问 / 疑问"))
        self.assertIsNone(match_semantic_action(rules_with([]), "惊喜 / 反转"))

    def test_unmatched_cue(self) -> None:
        self.assertIsNone(match_semantic_action(rules_with(), "讲解要点"))


class LoadPerformanceRulesTest(unittest.TestCase):
    """加载：真实文件可读；缺失/坏文件返回 None；临时目录可用。"""

    def test_default_path_exists(self) -> None:
        rules = load_performance_rules()
        self.assertIsNotNone(rules)
        self.assertIn("semantic_actions", rules)

    def test_missing_file_returns_none(self) -> None:
        self.assertIsNone(load_performance_rules(Path("no-such-file.json")))

    def test_temp_file_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rules.json"
            path.write_text(json.dumps(rules_with()), encoding="utf-8")
            rules = load_performance_rules(path)
            self.assertEqual(len(rules["semantic_actions"]), 3)

    def test_broken_file_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rules.json"
            path.write_text("{broken", encoding="utf-8")
            self.assertIsNone(load_performance_rules(path))


class PerformanceCueEndpointTest(unittest.TestCase):
    """POST /v1/performance/cue：返回 cue 与命中的动作。"""

    def _call(self, text: str) -> dict:
        handler = api.ApiHandler.__new__(api.ApiHandler)
        seen = {}
        handler._send_json = lambda status, payload: seen.update(
            {"status": status, "payload": payload}
        )
        handler._read_json = lambda: {"text": text}
        handler.path = "/v1/performance/cue"
        handler.do_POST()
        return seen

    def test_question_returns_action(self) -> None:
        seen = self._call("你会画画吗？")
        self.assertEqual(seen["status"].value, 200)
        self.assertEqual(seen["payload"]["cue"], "提问 / 疑问")
        self.assertIsNotNone(seen["payload"]["action"])

    def test_neutral_returns_no_action(self) -> None:
        seen = self._call("好的 谢谢")
        self.assertEqual(seen["payload"]["cue"], None)
        self.assertIsNone(seen["payload"]["action"])


class EnrichCaptionTracksTest(unittest.TestCase):
    """K6 视频合成消费：字幕轨 → 语义动作轨（提问侧头 / 强调闭嘴 / 其余自由）。"""

    def _rules(self):
        return rules_with()

    def test_neutral_caption_only_speech_track(self) -> None:
        tracks = enrich_caption_tracks(
            [{"start": 0.0, "end": 2.0, "text": "好的 谢谢"}], self._rules()
        )
        self.assertEqual(len(tracks), 1)
        self.assertEqual(tracks[0]["speech"], True)
        self.assertNotIn("param", tracks[0])

    def test_question_caption_appends_tilt_track(self) -> None:
        tracks = enrich_caption_tracks(
            [{"start": 1.0, "end": 3.0, "text": "你会画画吗？"}], self._rules()
        )
        self.assertEqual(len(tracks), 2)
        tilt = tracks[1]
        self.assertEqual(tilt["t"], 1.3)  # 提问后约 0.3s
        self.assertEqual(tilt["dur"], 0.65)
        self.assertEqual(tilt["param"]["ParamAngleX"], -18.0)

    def test_emphasis_caption_appends_hold_track(self) -> None:
        tracks = enrich_caption_tracks(
            [{"start": 0.0, "end": 2.0, "text": "记住这个重点"}], self._rules()
        )
        self.assertEqual(len(tracks), 2)
        hold = tracks[1]
        self.assertEqual(hold["t"], 0.0)
        self.assertEqual(hold["param"]["ParamMouthOpenY"], 0.0)

    def test_short_caption_clamps_motion_duration(self) -> None:
        tracks = enrich_caption_tracks(
            [{"start": 0.0, "end": 0.3, "text": "为什么？"}], self._rules()
        )
        tilt = tracks[1]
        self.assertLessEqual(tilt["dur"], 0.3)

    def test_no_rules_keeps_captions_unchanged(self) -> None:
        captions = [{"start": 0.0, "end": 1.0, "text": "你会画画吗？"}]
        tracks = enrich_caption_tracks(captions, None)
        self.assertEqual(len(tracks), 1)
        self.assertNotIn("param", tracks[0])

    def test_empty_and_invalid_inputs(self) -> None:
        self.assertEqual(enrich_caption_tracks([], self._rules()), [])
        tracks = enrich_caption_tracks(
            [{"start": "bad", "end": 1.0, "text": "x"}], self._rules()
        )
        self.assertEqual(tracks, [])


if __name__ == "__main__":
    unittest.main()
