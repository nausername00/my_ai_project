"""D 层测试补全 · scene：场景分类器（关键词评分、meta 加成、置信度与回落）。"""

import unittest

from scene import (
    HeuristicSceneClassifier,
    SCENES,
    SCENE_SET,
    SCENE_TO_INTENT,
    SceneClassification,
)


class SceneRegistryTest(unittest.TestCase):
    def test_scenes_are_unique_and_known(self) -> None:
        self.assertEqual(len(SCENES), len(set(SCENES)))
        self.assertEqual(SCENE_SET, frozenset(SCENES))
        for scene in SCENES:
            self.assertIn(scene, SCENE_TO_INTENT)

    def test_scene_to_intent_mapping(self) -> None:
        self.assertEqual(SCENE_TO_INTENT["code"], "create")
        self.assertEqual(SCENE_TO_INTENT["companion"], "answer")
        self.assertEqual(SCENE_TO_INTENT["learn"], "learn")
        self.assertEqual(SCENE_TO_INTENT["system"], "ask_permission")


class ScoreTextTest(unittest.TestCase):
    def test_empty_text_all_zero(self) -> None:
        classifier = HeuristicSceneClassifier()
        scores = classifier._score_text("")
        self.assertTrue(all(v == 0.0 for v in scores.values()))

    def test_question_boost(self) -> None:
        classifier = HeuristicSceneClassifier()
        scores = classifier._score_text("怎么学习量子力学原理？")
        self.assertGreater(scores["learn"], 0.0)

    def test_emoji_boost(self) -> None:
        classifier = HeuristicSceneClassifier()
        scores = classifier._score_text("我好累 😢 想找人说说话")
        self.assertGreater(scores["companion"], 0.0)

    def test_code_keywords(self) -> None:
        classifier = HeuristicSceneClassifier()
        scores = classifier._score_text("帮我修复这个 bug，检查 git 提交记录和接口路由")
        self.assertGreater(scores["code"], 0.0)

    def test_non_string_raises(self) -> None:
        classifier = HeuristicSceneClassifier()
        with self.assertRaises(TypeError):
            classifier.classify(123)  # type: ignore[arg-type]


class ApplyMetaTest(unittest.TestCase):
    def setUp(self) -> None:
        self.classifier = HeuristicSceneClassifier()

    def test_high_audio_energy(self) -> None:
        scores = {scene: 0.0 for scene in SCENES}
        matched = self.classifier._apply_meta(scores, {"audio_energy": 0.9})
        self.assertGreater(scores["companion"], 0.0)
        self.assertIn("meta:audio_high_energy", matched)

    def test_screen_capture(self) -> None:
        scores = {scene: 0.0 for scene in SCENES}
        matched = self.classifier._apply_meta(scores, {"has_screen": True})
        self.assertGreater(scores["code"], 0.0)
        self.assertIn("meta:screen_capture_available", matched)

    def test_active_window_ide(self) -> None:
        scores = {scene: 0.0 for scene in SCENES}
        matched = self.classifier._apply_meta(scores, {"active_window_title": "Visual Studio Code"})
        self.assertGreater(scores["code"], 0.0)
        self.assertIn("meta:active_window:ide", matched)

    def test_active_window_game(self) -> None:
        scores = {scene: 0.0 for scene in SCENES}
        matched = self.classifier._apply_meta(scores, {"active_window_title": "原神"})
        self.assertGreater(scores["game"], 0.0)
        self.assertIn("meta:active_window:game", matched)


class ClassifyTest(unittest.TestCase):
    def test_classify_structure(self) -> None:
        classifier = HeuristicSceneClassifier()
        result = classifier.classify("怎么入门 Python 和测试用例？")
        self.assertIsInstance(result, SceneClassification)
        data = result.to_dict()
        for key in ("scene", "confidence", "recommended_intent", "matched_rules", "scores"):
            self.assertIn(key, data)

    def test_classify_confidence_bounds(self) -> None:
        classifier = HeuristicSceneClassifier()
        for text in ("随便聊聊", "帮我修 bug", "怎么学画画", "陪我聊聊天吧"):
            data = classifier.classify(text).to_dict()
            self.assertGreaterEqual(data["confidence"], 0.2)
            self.assertLessEqual(data["confidence"], 0.98)

    def test_empty_text_falls_back_to_chat(self) -> None:
        classifier = HeuristicSceneClassifier()
        data = classifier.classify("   ").to_dict()
        self.assertEqual(data["scene"], "chat")
        self.assertAlmostEqual(data["confidence"], 0.2)

    def test_meta_affects_classification(self) -> None:
        classifier = HeuristicSceneClassifier()
        with_meta = classifier.classify("", meta={"active_window_title": "pycharm"})
        self.assertEqual(with_meta.scene, "code")

    def test_custom_keywords(self) -> None:
        classifier = HeuristicSceneClassifier(
            keywords={"code": ("自定义代码词",), "chat": ("闲聊",)}
        )
        result = classifier.classify("自定义代码词 相关内容")
        self.assertEqual(result.scene, "code")

    def test_recommended_intent_valid(self) -> None:
        classifier = HeuristicSceneClassifier()
        result = classifier.classify("如何做一份学习笔记？")
        self.assertIn(result.recommended_intent, {"answer", "learn", "create", "ask_permission"})


if __name__ == "__main__":
    unittest.main()
