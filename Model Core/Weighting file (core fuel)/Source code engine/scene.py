"""L1 scene classifier: text + optional multi-modal metadata -> one of
seven companion scenarios plus a confidence score and a recommended
brain-plan intent aligned with :data:`brain.ALLOWED_INTENTS`.

The default implementation is a pure-heuristic rule engine (zero deps) so it
works alongside the placeholder backend.  A ``LLMBackedSceneClassifier`` is
provided as a drop-in replacement once a real :class:`InferenceEngine` is
available.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Iterable, Mapping

from utils import truncate_text

__all__ = [
    "SCENES",
    "SCENE_TO_INTENT",
    "SceneClassification",
    "HeuristicSceneClassifier",
    "LLMBackedSceneClassifier",
    "SceneClassifier",
]

SCENES = (
    "code",        # 编程/代码/工程/脚本/配置
    "create",      # 创作：写作/绘图/谱曲/文案/剧本
    "companion",   # 陪伴/聊天/情感支持
    "learn",       # 学习/研究/阅读/课程
    "game",        # 游戏/玩法/攻略
    "system",      # 系统/设备/文件管理操作
    "chat",        # 杂项闲聊/身份/寒暄
)
SCENE_SET = frozenset(SCENES)

# Aligns every scene with a valid brain-plan intent.
SCENE_TO_INTENT: dict[str, str] = {
    "code": "create",
    "create": "create",
    "companion": "answer",
    "learn": "learn",
    "game": "answer",
    "system": "ask_permission",
    "chat": "answer",
}


_KEYWORDS: dict[str, tuple[str, ...]] = {
    "code": (
        "代码", "编码", "编程", "程序", "脚本", "bug", "debug", "修复", "重构",
        "函数", "类", "模块", "算法", "sql", "python", "java", "javascript",
        "typescript", "react", "vue", "部署", "编译", "报错", "log", "日志",
        "commit", "git", "仓库", "api", "接口", "路由", "测试用例",
    ),
    "create": (
        "写", "创作", "画", "生成", "设计", "文案", "剧本", "小说", "诗歌",
        "海报", "封面", "头像", "编曲", "作曲", "策划", "方案", "ppt",
        "演讲稿", "总结文档", "报告", "story", "draft", "大纲",
    ),
    "companion": (
        "陪我", "陪你", "陪陪", "聊聊天", "倾诉", "好累", "好烦",
        "心情不好", "我好累", "好难过", "难过", "孤独", "想你",
        "安慰", "鼓励", "抱抱", "陪伴", "无聊", "在吗", "在嘛",
    ),
    "learn": (
        "学习", "学会", "教程", "怎么学", "入门", "讲解一下", "解释",
        "原理", "概念", "知识点", "做题", "作业", "考试", "复习",
        "笔记", "背诵", "练习", "research", "paper", "论文", "阅读",
    ),
    "game": (
        "游戏", "攻略", "关卡", "boss", "装备", "存档", "mod", "服务器",
        "开黑", "组队", "排位", "minecraft", "mc", "原神", "steam",
        "陪玩", "下棋", "打牌", "rpg", "剧情", "npc",
    ),
    "system": (
        "打开", "启动", "关闭", "删除", "复制", "移动", "下载", "安装",
        "卸载", "清理", "设置", "改设置", "屏幕", "截图", "录屏", "声音",
        "麦克风", "重启", "关机", "登录", "注册", "浏览器", "网页",
        "cmd", "terminal", "命令行", "终端", "管理员",
    ),
    "chat": (
        "你好", "早上好", "晚上好", "吃饭了吗", "在吗", "你是谁",
        "介绍一下自己", "多大", "生日", "爱好", "今天过得怎么样",
        "天气", "最近", "闲聊", "唠唠", "哈哈", "嗯嗯", "嘿嘿",
    ),
}

_STOPWORDS = frozenset(("的", "了", "呢", "吗", "啊", "吧", "是", "我", "你"))


def _normalize(text: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        "".join(ch for ch in text.casefold() if ch.isalnum() or "\u4e00" <= ch <= "\u9fff"),
    ).strip()


@dataclass(frozen=True)
class SceneClassification:
    scene: str
    confidence: float
    recommended_intent: str
    matched_rules: tuple[str, ...]
    scores: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene": self.scene,
            "confidence": round(float(self.confidence), 4),
            "recommended_intent": self.recommended_intent,
            "matched_rules": list(self.matched_rules),
            "scores": {k: round(float(v), 4) for k, v in sorted(self.scores.items())},
        }


class HeuristicSceneClassifier:
    """Keyword + rule-based classifier.  Always importable / runs offline."""

    def __init__(
        self,
        keywords: Mapping[str, Iterable[str]] | None = None,
    ) -> None:
        self.keywords: dict[str, tuple[str, ...]] = {
            scene: tuple(kw.casefold() for kw in (keywords or _KEYWORDS).get(scene, ()))
            for scene in SCENES
        }

    def _score_text(self, text: str) -> dict[str, float]:
        normalized = _normalize(text)
        scores: dict[str, float] = {scene: 0.0 for scene in SCENES}
        if not normalized:
            return scores
        for scene, kws in self.keywords.items():
            hits = 0
            unique_hits = set()
            for kw in kws:
                if not kw:
                    continue
                count = normalized.count(kw)
                if count:
                    hits += count
                    unique_hits.add(kw)
            if hits:
                weight = 1.0 + len(unique_hits) * 0.15
                scores[scene] = float(hits) * weight
        # Tie-breakers from punctuation / question / imperatives
        if any(mark in text for mark in ("?", "？", "怎么", "如何", "能否", "能不能")):
            scores["learn"] += 0.6
            scores["chat"] += 0.3
        if any(mark in text for mark in ("!", "！", "🥺", "😢", "😭")):
            scores["companion"] += 0.6
        return scores

    def _apply_meta(self, scores: dict[str, float], meta: Mapping[str, Any]) -> list[str]:
        matched: list[str] = []
        audio_energy = meta.get("audio_energy")
        has_screen = bool(meta.get("has_screen"))
        has_mouse_move = bool(meta.get("has_mouse_movement"))
        active_window = str(meta.get("active_window_title") or "").casefold()
        if isinstance(audio_energy, (int, float)) and audio_energy > 0.7:
            scores["companion"] += 0.4
            matched.append("meta:audio_high_energy")
        if has_screen:
            scores["code"] += 0.3
            scores["system"] += 0.2
            matched.append("meta:screen_capture_available")
        if has_mouse_move:
            scores["game"] += 0.3
            scores["system"] += 0.2
            matched.append("meta:mouse_activity")
        if any(term in active_window for term in ("code", "vscode", "pycharm", "ide", "visual studio", "sublime")):
            scores["code"] += 0.9
            matched.append("meta:active_window:ide")
        if any(term in active_window for term in ("chrome", "edge", "firefox", "browser", "safari")):
            scores["learn"] += 0.4
            matched.append("meta:active_window:browser")
        if any(term in active_window for term in ("steam", "游戏", "game", "原神", "minecraft", "mc", "mine")):
            scores["game"] += 1.0
            matched.append("meta:active_window:game")
        if any(term in active_window for term in ("explorer", "文件", "settings", "control panel", "设置")):
            scores["system"] += 0.7
            matched.append("meta:active_window:file_or_settings")
        return matched

    def classify(
        self,
        text: str,
        meta: Mapping[str, Any] | None = None,
    ) -> SceneClassification:
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        working_text = truncate_text(text.strip(), 4000, "")
        scores = self._score_text(working_text)
        matched_rules = list(self._matched_keyword_rules(working_text))
        if meta:
            matched_rules.extend(self._apply_meta(scores, meta))
        # Compute ranking
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        top_scene, top_score = ranked[0]
        second_score = ranked[1][1] if len(ranked) > 1 else 0.0
        if top_score <= 0:
            top_scene = "chat"
            confidence = 0.2
        else:
            gap = top_score - second_score
            confidence = max(
                0.2,
                min(
                    0.98,
                    0.5
                    + (gap / (top_score + 1.0)) * 0.35
                    + min(top_score / 6.0, 0.3),
                ),
            )
        return SceneClassification(
            scene=top_scene,
            confidence=float(confidence),
            recommended_intent=SCENE_TO_INTENT[top_scene],
            matched_rules=tuple(matched_rules),
            scores=dict(scores),
        )

    def _matched_keyword_rules(self, text: str) -> Iterable[str]:
        normalized = _normalize(text)
        if not normalized:
            return
        for scene, kws in self.keywords.items():
            for kw in kws:
                if kw and kw in normalized:
                    yield f"kw:{scene}:{kw[:24]}"
                    break  # one rule per scene to keep trace short


class LLMBackedSceneClassifier(HeuristicSceneClassifier):
    """Asks the language model for a scene label, then falls back to the
    heuristic classifier if the model call fails or returns nonsense.

    The returned :class:`SceneClassification` preserves the heuristic score
    breakdown for debugging; the LLM decision only overrides ``scene`` and
    ``confidence`` when we are confident in its output.
    """

    MAX_TEXT = 2000

    def __init__(
        self,
        engine: Any,
        keywords: Mapping[str, Iterable[str]] | None = None,
    ) -> None:
        super().__init__(keywords=keywords)
        self.engine = engine

    def classify(
        self,
        text: str,
        meta: Mapping[str, Any] | None = None,
    ) -> SceneClassification:
        heuristic = super().classify(text, meta=meta)
        engine = getattr(self, "engine", None)
        model_name = getattr(engine, "model_name", "placeholder") if engine else "placeholder"
        if model_name == "placeholder":
            return heuristic
        try:
            from inference import GenerationRequest
        except Exception:
            return heuristic
        payload_meta = {
            k: (str(v)[:200] if not isinstance(v, (int, float, bool)) else v)
            for k, v in (meta or {}).items()
        }
        prompt = (
            "把用户输入分类到以下场景之一，只输出 JSON：\n"
            + json.dumps(
                [
                    {"scene": s, "intent": SCENE_TO_INTENT[s]}
                    for s in SCENES
                ],
                ensure_ascii=False,
            )
            + "\nmust return JSON exactly:\n"
            '{"scene":"code","confidence":0.92,"reason":"短理由"}\n'
            "scene 必须是上述 7 个之一；confidence ∈ [0,1]；reason 不超过 80 字；"
            "不输出 Markdown 或额外文字。"
            f"\n用户输入：{truncate_text(text, self.MAX_TEXT)}"
            + (f"\n元数据：{json.dumps(payload_meta, ensure_ascii=False)[:800]}" if payload_meta else "")
        )
        try:
            from inference import GenerationRequest as _GR
            req = _GR(
                prompt=prompt,
                max_tokens=220,
                json_mode=True,
                temperature=0.0,
                system_prompt="你是严格的场景分类器，只输出合法 JSON。",
            )
            raw = engine.generate(req).strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            decision = json.loads(raw)
            scene = decision.get("scene")
            confidence = float(decision.get("confidence", 0.0) or 0.0)
            reason = str(decision.get("reason", ""))[:80]
            if scene in SCENE_SET and 0.0 <= confidence <= 1.0:
                rules = list(heuristic.matched_rules)
                if reason:
                    rules.append(f"llm_reason:{reason}")
                # Blend confidence: respect the LLM but anchor to heuristic signal.
                blended = (
                    confidence * 0.7
                    + max(heuristic.confidence, 0.2) * 0.3
                )
                return SceneClassification(
                    scene=scene,
                    confidence=float(max(0.05, min(0.99, blended))),
                    recommended_intent=SCENE_TO_INTENT[scene],
                    matched_rules=tuple(rules),
                    scores=heuristic.scores,
                )
        except Exception:
            # Fall through to the heuristic result.
            pass
        return heuristic


SceneClassifier = HeuristicSceneClassifier
