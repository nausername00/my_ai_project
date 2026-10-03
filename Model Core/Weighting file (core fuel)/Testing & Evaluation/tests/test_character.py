import tempfile
import unittest
from pathlib import Path

from character import CharacterCard, CharacterStore


class CharacterStoreTests(unittest.TestCase):
    def test_rejects_non_string_asset_names(self) -> None:
        for field in ("avatar", "voice"):
            with self.subTest(field=field):
                card = CharacterCard().to_dict()
                card[field] = []
                with self.assertRaises(ValueError):
                    CharacterCard.from_dict(card)

    def test_lists_supported_local_avatar_formats(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            asset_dir = root / "assets"
            asset_dir.mkdir()
            for file_name in ("portrait.png", "portrait.jpg", "portrait.webp", "ignored.svg"):
                (asset_dir / file_name).write_bytes(b"")
            store = CharacterStore(
                str(root / "character.json"),
                str(root / "memory.json"),
                str(asset_dir),
            )

            assets = store.list_assets()

        self.assertEqual(
            assets,
            [
                {"name": "portrait.jpg", "kind": "avatar"},
                {"name": "portrait.png", "kind": "avatar"},
                {"name": "portrait.webp", "kind": "avatar"},
            ],
        )

    def test_saves_role_profile_and_includes_persona_in_system_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = CharacterStore(
                str(root / "character.json"),
                str(root / "memory.json"),
                str(root / "assets"),
            )
            card = CharacterCard.from_dict(
                {
                    "nickname": "Coco",
                    "gender": "female",
                    "self_reference": "I",
                    "core_traits": ["curious"],
                    "behavior_traits": ["gentle"],
                    "habits": ["check assumptions"],
                    "likes": ["learning together"],
                    "dislikes": ["dishonesty"],
                    "signature_lines": ["Let me think."],
                    "emotions": ["calm"],
                }
            )
            store.save_card(card)
            system_prompt = store.build_system_prompt()

        self.assertIn("Coco", system_prompt)
        self.assertIn("curious", system_prompt)
        self.assertIn("check assumptions", system_prompt)
        self.assertIn("learning together", system_prompt)
        self.assertIn("dishonesty", system_prompt)
        self.assertIn("Let me think.", system_prompt)
        self.assertIn("只有用户明确问姓名或身份", system_prompt)
        self.assertIn("不要主动重复介绍", system_prompt)

    def test_default_character_has_moling_identity_and_emotional_expression(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = CharacterStore(
                str(root / "character.json"),
                str(root / "memory.json"),
                str(root / "assets"),
            )
            prompt = store.build_system_prompt()

        self.assertIn("角色「墨小灵」", prompt)
        self.assertIn("情绪表达范围", prompt)
        self.assertIn("只有用户明确问姓名或身份", prompt)
        self.assertIn("不要无缘由地说", prompt)
        self.assertIn("先回应用户这条消息真正谈的事", prompt)
        self.assertIn("英文名「Moling」", prompt)
        self.assertEqual(store.load_card().core_traits, ["温柔", "真诚", "有主见"])
        self.assertEqual(store.load_card().emotions, ["开心", "好奇", "担心", "害羞"])

    def test_character_cards_can_be_created_listed_and_switched_without_affect_leaking(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = CharacterStore(
                str(root / "default.json"),
                str(root / "memory.json"),
                str(root / "assets"),
            )
            store.set_simulated_affect("happy")
            created = store.create_character(
                {
                    "category": "学习伙伴",
                    "formal_name": "小老师",
                    "nickname": "老师",
                    "english_name": "Tutor",
                    "language": "zh-CN",
                    "gender": "未设定",
                    "self_reference": "我",
                    "core_traits": ["耐心"],
                    "behavior_traits": ["循序渐进"],
                    "signature_lines": [],
                    "emotions": ["平静"],
                    "avatar": None,
                    "voice": None,
                }
            )
            listing = store.list_characters()
            store.set_active_character(created["id"])
            new_character_affect = store.get_simulated_affect()
            store.set_simulated_affect("curious")
            active_prompt = store.build_system_prompt()
            store.set_active_character("default")
            default_affect = store.get_simulated_affect()
            default_card = store.load_card()

        self.assertEqual(listing["active_id"], "default")
        self.assertEqual({entry["id"] for entry in listing["characters"]}, {"default", created["id"]})
        self.assertEqual(new_character_affect["mood"], "calm")
        self.assertIn("Respond in Simplified Chinese", active_prompt)
        self.assertEqual(default_affect["mood"], "happy")
        self.assertEqual(default_card.nickname, "墨灵")

    def test_agent_goals_are_validated_and_included_in_character_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = CharacterStore(
                str(root / "default.json"),
                str(root / "memory.json"),
                str(root / "assets"),
            )
            card = CharacterCard.from_dict(
                {
                    **CharacterCard().to_dict(),
                    "agent_goals": [
                        {
                            "domain": "learn",
                            "title": "一起学日语",
                            "description": "每周练习两次基础会话",
                            "progress": "已经学会问候语",
                            "status": "active",
                        }
                    ],
                }
            )
            store.save_card(card)
            prompt = store.build_system_prompt()
            invalid_card = card.to_dict()
            invalid_card["agent_goals"] = [
                {
                    "domain": "learn",
                    "title": "目标",
                    "description": "无效状态",
                    "progress": "尚未开始",
                    "status": "unknown",
                }
            ]

        self.assertIn("一起学日语", prompt)
        self.assertIn("每周练习两次基础会话", prompt)
        self.assertIn("自然推进而不要强行把每次聊天转成目标任务", prompt)
        self.assertIn("必须请求用户明确许可", prompt)
        with self.assertRaises(ValueError):
            CharacterCard.from_dict(invalid_card)

    def test_legacy_persona_fields_migrate_to_explicit_inner_character_dimensions(self) -> None:
        legacy = CharacterCard().to_dict()
        legacy.pop("core_values")
        legacy.pop("emotional_range")
        legacy["core_traits"] = ["真诚", "独立"]
        legacy["emotions"] = ["开心", "担心"]
        card = CharacterCard.from_dict(
            legacy
        )
        serialized = card.to_dict()
        self.assertEqual(card.core_values, ["真诚", "独立"])
        self.assertEqual(card.core_traits, ["真诚", "独立"])
        self.assertEqual(card.emotional_range, ["开心", "担心"])
        self.assertIn("inner_drives", serialized)
        self.assertNotIn("core_traits", serialized)
        self.assertNotIn("emotions", serialized)

    def test_missing_personality_card_fields_migrate_and_validate(self) -> None:
        legacy = CharacterCard().to_dict()
        for field in ("personality_preset", "habits", "likes", "dislikes"):
            legacy.pop(field)
        migrated = CharacterCard.from_dict(legacy)
        self.assertEqual(migrated.personality_preset, "custom")
        self.assertEqual(
            migrated.habits,
            ["先听完再回应", "重要事情先确认事实", "愿意承认并修正错误"],
        )
        self.assertEqual(migrated.likes, ["真诚交流", "共同探索", "把想法做成作品"])
        self.assertEqual(
            migrated.dislikes,
            ["敷衍与欺骗", "未经许可越界", "把猜测说成事实"],
        )

        for field, invalid_value in (
            ("personality_preset", []),
            ("habits", ["x" * 121]),
            ("likes", ["喜欢"] * 41),
            ("dislikes", [""]),
        ):
            with self.subTest(field=field):
                invalid = {**CharacterCard().to_dict(), field: invalid_value}
                with self.assertRaises(ValueError):
                    CharacterCard.from_dict(invalid)

    def test_agent_reflection_cannot_write_after_autonomy_is_disabled_or_card_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = CharacterStore(
                str(root / "default.json"),
                str(root / "memory.json"),
                str(root / "assets"),
            )
            store.save_card(
                CharacterCard.from_dict(
                    {
                        **CharacterCard().to_dict(),
                        "agent_autonomy_enabled": False,
                    }
                )
            )
            disabled_result = store.apply_agent_reflection(
                {"goal": None, "updates": [], "reflection": "late result"},
                "default",
            )
            changed_card_result = store.apply_agent_reflection(
                {"goal": None, "updates": [], "reflection": "stale result"},
                "another-character",
            )

        self.assertIsNone(disabled_result)
        self.assertIsNone(changed_card_result)
        self.assertEqual(store.load_card().agent_reflection, "")

    def test_model_resource_paths_and_emotion_mappings_are_validated(self) -> None:
        base = CharacterCard().to_dict()
        invalid_paths = {
            **base,
            "model_files": ["models/../../outside.png"],
        }
        invalid_mapping = {
            **base,
            "actions": ["wave"],
            "emotion_mapping": {
                "happy": {"action": "delete-files", "expression": ""}
            },
        }
        with self.assertRaises(ValueError):
            CharacterCard.from_dict(invalid_paths)
        with self.assertRaises(ValueError):
            CharacterCard.from_dict(invalid_mapping)

    def test_disabling_agent_autonomy_hides_its_goals_from_chat_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = CharacterStore(
                str(root / "default.json"),
                str(root / "memory.json"),
                str(root / "assets"),
            )
            card = CharacterCard.from_dict(
                {
                    **CharacterCard().to_dict(),
                    "agent_autonomy_enabled": False,
                    "agent_goals": [
                        {
                            "domain": "learn",
                            "title": "内部目标",
                            "description": "持续学习",
                            "progress": "刚开始",
                            "status": "active",
                        }
                    ],
                }
            )
            store.save_card(card)
            prompt = store.build_system_prompt()

        self.assertNotIn("内部目标", prompt)
        self.assertNotIn("智能体自主性：你可以", prompt)

    def test_character_id_validation_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = CharacterStore(
                str(root / "default.json"),
                str(root / "memory.json"),
                str(root / "assets"),
            )
            with self.assertRaises(ValueError):
                store.set_active_character("../outside")

    def test_simulated_affect_distinguishes_dynamic_emotional_states(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = CharacterStore(
                str(root / "character.json"),
                str(root / "memory.json"),
                str(root / "assets"),
            )
            observed = {
                "开心": store.observe_user_message("我今天好开心"),
                "好奇": store.observe_user_message("我很好奇这个怎么做"),
                "担心": store.observe_user_message("我最近心情有点低落"),
                "害羞": store.observe_user_message("说到这里我有点害羞"),
            }

        self.assertEqual(
            {name: state["mood"] for name, state in observed.items()},
            {
                "开心": "happy",
                "好奇": "curious",
                "担心": "caring",
                "害羞": "shy",
            },
        )

    def test_private_memories_and_global_opt_out_are_excluded_from_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = CharacterStore(
                str(root / "character.json"),
                str(root / "memory.json"),
                str(root / "assets"),
            )
            store.add_memory("shared preference", visibility="model")
            store.add_memory("private note", visibility="private")
            system_prompt = store.build_system_prompt()
            self.assertIn("shared preference", system_prompt)
            self.assertNotIn("private note", system_prompt)

            store.set_privacy_settings({"include_memories_in_prompt": False})
            opted_out_prompt = store.build_system_prompt()

        self.assertNotIn("shared preference", opted_out_prompt)
        self.assertNotIn("private note", opted_out_prompt)

    def test_simulated_affect_changes_from_local_text_rules_without_saving_message(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = CharacterStore(
                str(root / "character.json"),
                str(root / "memory.json"),
                str(root / "assets"),
            )

            caring = store.observe_user_message("我今天很难过，想找人说说")
            caring_prompt = store.build_system_prompt(caring)
            persisted = (root / "affect.json").read_text(encoding="utf-8")
            calm = store.observe_user_message("今天天气不错")
            reset = store.set_simulated_affect("calm")
            reloaded = store.get_simulated_affect()

        self.assertEqual(caring["mood"], "caring")
        self.assertIn("当前角色表达状态：关怀", caring_prompt)
        self.assertNotIn("我今天很难过", persisted)
        self.assertEqual(calm["mood"], "calm")
        self.assertEqual(reset["reason"], "用户手动重置")
        self.assertEqual(reloaded["mood"], "calm")

    def test_simulated_affect_rejects_unknown_mood(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = CharacterStore(
                str(root / "character.json"),
                str(root / "memory.json"),
                str(root / "assets"),
            )
            with self.assertRaises(ValueError):
                store.set_simulated_affect("fear_of_shutdown")

    def test_simulated_affect_rejects_malformed_persisted_mood(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            affect_path = root / "affect.json"
            affect_path.write_text(
                '{"mode":"simulated","mood":[],"reason":"test","updated_at":"now"}',
                encoding="utf-8",
            )
            store = CharacterStore(
                str(root / "character.json"),
                str(root / "memory.json"),
                str(root / "assets"),
            )

            with self.assertRaises(ValueError):
                store.get_simulated_affect()
