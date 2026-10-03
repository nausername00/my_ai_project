"""Lightweight, single-pass cognitive routing for companion responses."""

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping


CognitiveMode = Literal["direct", "divergent", "critical", "care"]


@dataclass(frozen=True)
class CognitiveRoute:
    mode: CognitiveMode
    instruction: str


@dataclass(frozen=True)
class RoutedDecision(CognitiveRoute):
    """Cognitive route combined with L1 scene metadata for downstream
    planner / controller consumption.

    Backwards compatible with :class:`CognitiveRoute` callers: any code that
    only reads ``mode`` or ``instruction`` keeps working.  Additional fields
    are all optional (sensible defaults exist) on the wire formats.
    """

    scene: str = "chat"
    confidence: float = 0.0
    recommended_intent: str = "answer"
    matched_rules: tuple = ()
    scene_scores: dict = field(default_factory=dict)


_DIVERGENT_CUES = (
    "发散",
    "头脑风暴",
    "脑暴",
    "多想几种",
    "不同方向",
    "还有什么",
    "还能补充",
    "其他想法",
    "有什么新",
    "点子",
    "创意",
    "发散性思维",
    "跳跃性思维",
    "跨界联想",
    "brainstorm",
    "divergent",
)
_CRITICAL_CUES = (
    "逆向",
    "逆向思维",
    "反思维",
    "反向思考",
    "反向思维",
    "反过来",
    "挑战假设",
    "反驳",
    "反面",
    "风险",
    "利弊",
    "比较方案",
    "该不该",
    "是否应该",
    "counterargument",
    "devil's advocate",
    "trade-off",
)
_DIRECT_CUES = (
    "不要发散",
    "别发散",
    "不用发散",
    "不要逆向",
    "无需反向思考",
)
_CARE_CUES = (
    "难过",
    "伤心",
    "孤独",
    "烦躁",
    "痛苦",
    "低落",
    "沮丧",
    "焦虑",
    "sad",
    "lonely",
    "upset",
)

_INSTRUCTIONS: dict[CognitiveMode, str] = {
    "direct": (
        "先理解用户这条消息真正要解决的事并直接回应。只在会影响结论时说明假设或不确定性；"
        "不要为了展示思考而列分析过程，也不要强行追问。"
    ),
    "divergent": (
        "围绕用户的问题探索彼此不同的可能方向，避免把同一想法换词重复；"
        "筛选最贴题且可行的选项，简要说明差异、取舍或下一步。"
        "除非用户要求完整清单，否则优先给少量高价值选项。不要输出隐藏的逐步推理过程。"
    ),
    "critical": (
        "审视关键前提，并从相反视角寻找反例、失败条件和副作用；"
        "区分已知事实与推测，不要为了反对而反对。最后给出综合判断或更稳妥的替代方案，"
        "只呈现关键理由，不输出隐藏的逐步推理过程。"
    ),
    "care": (
        "先回应用户明确表达的处境和感受，不把倾诉自动改造成问题清单或优化建议；"
        "不擅自诊断情绪。若用户在寻求帮助，再温和提供一个具体可选的下一步。"
    ),
}


def route_cognition(prompt: str) -> CognitiveRoute:
    """Select a concise response strategy without an extra model call."""
    normalized = " ".join(prompt.casefold().split())
    if any(cue in normalized for cue in _DIRECT_CUES):
        mode: CognitiveMode = "direct"
    elif any(cue in normalized for cue in _CARE_CUES):
        mode: CognitiveMode = "care"
    elif any(cue in normalized for cue in _CRITICAL_CUES):
        mode = "critical"
    elif any(cue in normalized for cue in _DIVERGENT_CUES):
        mode = "divergent"
    else:
        mode = "direct"
    return CognitiveRoute(mode=mode, instruction=_INSTRUCTIONS[mode])


_SCENE_MODE_OVERRIDE: dict[str, CognitiveMode] = {
    "code": "direct",
    "learn": "direct",
    "system": "critical",
    "create": "divergent",
    "game": "divergent",
    "companion": "care",
    "chat": "direct",
}

_SCENE_INSTRUCTION_SUFFIX: dict[str, str] = {
    "code": (
        "当前场景=code：若产生代码或 patch，保持可运行、最小化变更，"
        "并明确标出需要用户授权的破坏性操作。"
    ),
    "learn": (
        "当前场景=learn：先解释核心概念（含类比），再给结构化要点，"
        "最后留一个用户可以立刻动手的小练习或校验问题。"
    ),
    "system": (
        "当前场景=system：任何会影响系统、文件或设置的动作都必须先说明"
        "风险并要求用户显式授权，再给出可执行建议或确认清单。"
    ),
    "create": (
        "当前场景=create：产出先给 2-3 个差异化方向，选定后再输出完整内容，"
        "避免一次性给出过长版本。"
    ),
    "game": (
        "当前场景=game：避免剧透，结论优先（怎么做），再补充背景或设定。"
    ),
    "companion": (
        "当前场景=companion：语速放缓、避免说教；先情绪确认，再酌情陪聊或陪伴。"
    ),
    "chat": "",
}


class SceneAwareRouter:
    """Combines the L1 :class:`HeuristicSceneClassifier` with the existing
    keyword-based :func:`route_cognition`.

    Decision rules:
      * If classifier confidence >= ``high_conf_threshold`` the scene drives
        the cognitive *mode* and appends a scene-tailored instruction suffix;
        the keyword router is still executed and its cues are logged in
        ``matched_rules`` for observability.
      * If confidence < ``low_conf_threshold`` we fall back entirely to
        :func:`route_cognition` and keep the scene info for metadata only.
      * The middle band blends both: keyword cues may still override the mode
        (e.g. a "sad" cue still promotes ``care`` even if the guess was
        ``code``).
    """

    HIGH_CONF = 0.72
    LOW_CONF = 0.35

    def __init__(
        self,
        classifier: Any = None,
        *,
        high_conf_threshold: float = HIGH_CONF,
        low_conf_threshold: float = LOW_CONF,
    ) -> None:
        if classifier is None:
            # Lazy import keeps `import agent` working even if scene module
            # is unavailable (shouldn't happen but keeps the layer robust).
            from scene import SceneClassifier as _SC

            classifier = _SC()
        self.classifier = classifier
        self.high_conf = float(high_conf_threshold)
        self.low_conf = float(low_conf_threshold)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def route(
        self,
        prompt: str,
        meta: Mapping[str, Any] | None = None,
    ) -> RoutedDecision:
        if not isinstance(prompt, str):
            raise TypeError("prompt must be a string")
        scene_info = self.classifier.classify(prompt, meta=meta or {})
        keyword_route = route_cognition(prompt)
        mode: CognitiveMode = keyword_route.mode
        instruction = keyword_route.instruction
        confidence = float(scene_info.confidence)
        scene = scene_info.scene
        if confidence >= self.high_conf:
            override = _SCENE_MODE_OVERRIDE.get(scene, mode)
            suffix = _SCENE_INSTRUCTION_SUFFIX.get(scene, "")
            mode = override
            if suffix:
                instruction = f"{keyword_route.instruction}\n{suffix}"
        elif confidence < self.low_conf:
            # Pure keyword fall-back; scene is recorded but not acted on.
            pass
        else:
            # Middle band: scene nudges mode only when keywords are neutral.
            if mode == "direct" and scene in _SCENE_MODE_OVERRIDE:
                mode = _SCENE_MODE_OVERRIDE[scene]
            suffix = _SCENE_INSTRUCTION_SUFFIX.get(scene, "")
            if suffix:
                instruction = f"{keyword_route.instruction}\n{suffix}"
        return RoutedDecision(
            mode=mode,
            instruction=instruction,
            scene=scene,
            confidence=confidence,
            recommended_intent=scene_info.recommended_intent,
            matched_rules=tuple(scene_info.matched_rules),
            scene_scores=dict(scene_info.scores),
        )

    def to_dict(self, decision: RoutedDecision) -> dict[str, Any]:
        """Serialize a decision to JSON-able primitives (backwards compatible
        with the older :class:`CognitiveRoute` shape — new fields are
        additive).
        """
        return {
            "mode": decision.mode,
            "instruction": decision.instruction,
            "scene": decision.scene,
            "confidence": round(float(decision.confidence), 4),
            "recommended_intent": decision.recommended_intent,
            "matched_rules": list(decision.matched_rules),
            "scene_scores": {
                k: round(float(v), 4) for k, v in decision.scene_scores.items()
            },
        }


def route_with_scene(
    prompt: str,
    meta: Mapping[str, Any] | None = None,
    *,
    router: SceneAwareRouter | None = None,
) -> RoutedDecision:
    """Module-level convenience wrapper for :meth:`SceneAwareRouter.route`.

    This reuses a module-scoped singleton router so callers don't have to
    carry one around.  The singleton classifier is the pure heuristic one —
    no LLM back-end is ever used implicitly.
    """
    global _DEFAULT_ROUTER
    if _DEFAULT_ROUTER is None:
        _DEFAULT_ROUTER = SceneAwareRouter()
    if router is None:
        router = _DEFAULT_ROUTER
    return router.route(prompt, meta=meta)


_DEFAULT_ROUTER: SceneAwareRouter | None = None