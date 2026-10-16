"""D 层测试补全 · collaboration：协作伙伴清单、角色解析、综合校验、本机引擎判定、协作循环。"""

import json
import unittest

from collaboration import (
    COLLABORATORS,
    MAX_ROLE_INSTRUCTION_LENGTH,
    Collaborator,
    _validate_synthesis,
    is_local_engine,
    list_collaborator_roles,
    resolve_collaborators,
    run_collaboration,
)
from inference import ModelUnavailableError


class RolesTest(unittest.TestCase):
    def test_list_roles_shape(self) -> None:
        roles = list_collaborator_roles()
        self.assertEqual(len(roles), len(COLLABORATORS))
        for role in roles:
            for key in ("key", "name", "focus", "instruction"):
                self.assertIn(key, role)
                self.assertIsInstance(role[key], str)
                self.assertTrue(role[key])

    def test_keys_unique(self) -> None:
        roles = list_collaborator_roles()
        keys = [r["key"] for r in roles]
        self.assertEqual(len(keys), len(set(keys)))

    def test_resolve_none_returns_all(self) -> None:
        resolved = resolve_collaborators(None)
        self.assertEqual(len(resolved), len(COLLABORATORS))
        self.assertTrue(all(isinstance(c, Collaborator) for c in resolved))

    def test_resolve_custom_config(self) -> None:
        resolved = resolve_collaborators(
            [{"key": "code", "enabled": True, "instruction": "只检查边界条件。"}]
        )
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0].key, "code")
        self.assertEqual(resolved[0].instruction, "只检查边界条件。")

    def test_resolve_disabled_role_skipped(self) -> None:
        resolved = resolve_collaborators(
            [{"key": "code", "enabled": False, "instruction": "x"},
             {"key": "testing", "enabled": True, "instruction": "y"}]
        )
        self.assertEqual([c.key for c in resolved], ["testing"])

    def test_resolve_empty_list_rejected(self) -> None:
        with self.assertRaises(ValueError):
            resolve_collaborators([])

    def test_resolve_unknown_key_rejected(self) -> None:
        with self.assertRaises(ValueError):
            resolve_collaborators([{"key": "nope", "enabled": True, "instruction": "x"}])

    def test_resolve_missing_fields_rejected(self) -> None:
        with self.assertRaises(ValueError):
            resolve_collaborators([{"key": "code", "enabled": True}])

    def test_resolve_duplicate_rejected(self) -> None:
        with self.assertRaises(ValueError):
            resolve_collaborators(
                [{"key": "code", "enabled": True, "instruction": "a"},
                 {"key": "code", "enabled": True, "instruction": "b"}]
            )

    def test_resolve_overlong_instruction_rejected(self) -> None:
        long_text = "长" * (MAX_ROLE_INSTRUCTION_LENGTH + 1)
        with self.assertRaises(ValueError):
            resolve_collaborators([{"key": "code", "enabled": True, "instruction": long_text}])

    def test_resolve_all_disabled_rejected(self) -> None:
        with self.assertRaises(ValueError):
            resolve_collaborators(
                [{"key": "code", "enabled": False, "instruction": "a"},
                 {"key": "ui", "enabled": False, "instruction": "b"}]
            )


class ValidateSynthesisTest(unittest.TestCase):
    def test_valid_json(self) -> None:
        raw = json.dumps(
            {
                "consensus": ["结论一"],
                "prioritized": ["优先一"],
                "conflicts": [],
                "next_steps": ["下一步一"],
            },
            ensure_ascii=False,
        )
        result = _validate_synthesis(raw)
        self.assertEqual(result["consensus"], ["结论一"])
        self.assertEqual(result["conflicts"], [])

    def test_markdown_wrapped(self) -> None:
        raw = "```json\n" + json.dumps(
            {"consensus": ["c"], "prioritized": ["p"], "conflicts": [], "next_steps": ["n"]}
        ) + "\n```"
        result = _validate_synthesis(raw)
        self.assertEqual(result["consensus"], ["c"])

    def test_invalid_json_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _validate_synthesis("not json at all")

    def test_missing_field_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _validate_synthesis(json.dumps({"consensus": ["c"]}))

    def test_non_string_item_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _validate_synthesis(
                json.dumps({"consensus": [1], "prioritized": [], "conflicts": [], "next_steps": []})
            )

    def test_overlong_item_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _validate_synthesis(
                json.dumps(
                    {
                        "consensus": ["长" * 800],
                        "prioritized": [],
                        "conflicts": [],
                        "next_steps": [],
                    },
                    ensure_ascii=False,
                )
            )

    def test_duplicate_items_deduped(self) -> None:
        raw = json.dumps(
            {"consensus": ["相同结论", "相同结论"], "prioritized": [], "conflicts": [], "next_steps": []},
            ensure_ascii=False,
        )
        result = _validate_synthesis(raw)
        self.assertEqual(result["consensus"], ["相同结论"])


class FakeEngine:
    """Minimal InferenceEngine stand-in: only what collaboration touches.

    Deterministic by call order: first 4 calls are the four collaborator
    opinions (architecture, code, ui, testing), the next call is synthesis.
    """

    model_name = "fake-model"

    def __init__(self, opinion_text: str, synthesis_json: str | None = None,
                 fail_roles: set[str] | None = None) -> None:
        self.opinion_text = opinion_text
        self.synthesis_json = synthesis_json
        self.fail_roles = fail_roles or set()
        self.backend = None  # no endpoint → treated as local
        self._call_index = 0
        self._role_order = ("architecture", "code", "ui", "testing")

    def generate(self, request) -> str:
        index = self._call_index
        self._call_index += 1
        if index < 4:
            role_key = self._role_order[index]
            if role_key in self.fail_roles:
                raise ModelUnavailableError("模拟模型不可用")
            return self.opinion_text
        if self.synthesis_json is not None:
            return self.synthesis_json
        return '{"consensus":["默认综合"],"prioritized":["默认优先"],"conflicts":[],"next_steps":["默认下一步"]}'


class LocalEngineTest(unittest.TestCase):
    def test_no_backend_is_local(self) -> None:
        class Engine:
            model_name = "x"
        self.assertTrue(is_local_engine(Engine()))

    def test_localhost_endpoint_is_local(self) -> None:
        class Backend:
            endpoint = "http://127.0.0.1:11434"
        class Engine:
            model_name = "x"
            backend = Backend()
        self.assertTrue(is_local_engine(Engine()))

    def test_remote_endpoint_not_local(self) -> None:
        class Backend:
            endpoint = "https://api.example.com/v1"
        class Engine:
            model_name = "x"
            backend = Backend()
        self.assertFalse(is_local_engine(Engine()))


class RunCollaborationTest(unittest.TestCase):
    def test_full_run_with_synthesis(self) -> None:
        engine = FakeEngine(
            opinion_text="这是可执行的评审建议。",
            synthesis_json=json.dumps(
                {"consensus": ["结论"], "prioritized": ["优先"], "conflicts": [], "next_steps": ["下一步"]},
                ensure_ascii=False,
            ),
        )
        result = run_collaboration(engine, "system", "评审一个边界条件")
        self.assertEqual(result["model"], "fake-model")
        self.assertEqual(result["lead"], "moling")
        self.assertEqual(len(result["collaborators"]), len(COLLABORATORS))
        self.assertTrue(all(c["status"] == "completed" for c in result["collaborators"]))
        self.assertIsNotNone(result["synthesis"])
        self.assertIn("consensus", result["synthesis"])
        self.assertEqual(result["synthesis_error"], "")

    def test_partial_failure_still_synthesizes(self) -> None:
        engine = FakeEngine(
            opinion_text="正常意见",
            synthesis_json='{"consensus":["综合"],"prioritized":[],"conflicts":[],"next_steps":[]}',
            fail_roles={"architecture"},
        )
        result = run_collaboration(engine, "system", "任务")
        statuses = {c["agent"]: c["status"] for c in result["collaborators"]}
        self.assertEqual(statuses["architecture"], "failed")
        self.assertTrue(all(statuses[k] == "completed" for k in ("code", "ui", "testing")))
        self.assertIsNotNone(result["synthesis"])
        failed = [c for c in result["collaborators"] if c["status"] == "failed"]
        self.assertTrue(all(c["error"] for c in failed))

    def test_all_failed_no_synthesis(self) -> None:
        engine = FakeEngine(
            opinion_text="x",
            fail_roles={"architecture", "code", "ui", "testing"},
        )
        result = run_collaboration(engine, "system", "任务")
        self.assertTrue(all(c["status"] == "failed" for c in result["collaborators"]))
        self.assertIsNone(result["synthesis"])

    def test_remote_engine_rejected(self) -> None:
        class Backend:
            endpoint = "https://api.example.com"
        class Engine:
            model_name = "x"
            backend = Backend()

            def generate(self, request) -> str:
                return "x"
        with self.assertRaises(ValueError):
            run_collaboration(Engine(), "system", "任务")


if __name__ == "__main__":
    unittest.main()
