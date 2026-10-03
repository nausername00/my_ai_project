"""L3 planning — ReAct loop + execution-mode router.

Combines the L1 scene classification (``scene``), the L2 cognitive router
(``agent``), and the existing single-shot :mod:`brain` planner into a
multi-step Thought → Action → Observation → Reflection loop.  The module is
*placeholder-first*: when the plugged :class:`InferenceEngine` is the
``placeholder`` backend the loop still runs against a built-in heuristic
(tool-free) trail so the rest of the architecture can exercise it without
installing any model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
import json
from typing import Any, Callable, Iterable, Mapping

from utils import ModuleUnavailableError, PermissionDenied, SingletonLock, truncate_text

__all__ = [
    "ExecutionMode",
    "ExecutionRouterDecision",
    "Priority",
    "ReActPlanError",
    "ReActPlanResult",
    "ReActPlanner",
    "ReActStep",
    "mode_router",
]


class Priority(int):
    """Integer priority (1 lowest → 5 highest)."""

    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4
    CRITICAL = 5


class ExecutionMode(str, Enum):
    """How the L4 :class:`ExecutionController` should handle a plan."""

    PROPOSE = "propose"                # suggest steps; do not act
    ACT = "act"                        # execute approved tool calls directly
    ASK_PERMISSION = "ask_permission"  # show a human consent dialog first
    IDLE = "idle"                      # nothing to do


@dataclass(frozen=True)
class ExecutionRouterDecision:
    """Output of :func:`mode_router`.

    ``requires_approval`` lists tool names that still need a human "OK"
    before L4 can run them; it is *always* non-empty for the
    :data:`ExecutionMode.ASK_PERMISSION` mode.
    """

    mode: ExecutionMode
    priority: int
    reason: str
    requires_approval: tuple = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "priority": int(self.priority),
            "reason": self.reason,
            "requires_approval": list(self.requires_approval),
        }


@dataclass(frozen=True)
class ReActStep:
    index: int
    thought: str
    action_type: str                 # "tool" | "answer" | "ask_user" | "blocked" | "abort"
    tool_name: str | None
    tool_args: dict = field(default_factory=dict)
    observation: str = ""
    reflection: str = ""
    elapsed_ms: int = 0
    requires_approval: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": int(self.index),
            "thought": self.thought,
            "action_type": self.action_type,
            "tool_name": self.tool_name,
            "tool_args": dict(self.tool_args),
            "observation": str(self.observation),
            "reflection": self.reflection,
            "elapsed_ms": int(self.elapsed_ms),
            "requires_approval": bool(self.requires_approval),
        }


@dataclass(frozen=True)
class ReActPlanResult:
    intent: str
    steps: tuple
    final_answer: str = ""
    needs_user_decision: bool = False
    next_action: dict | None = None
    timed_out: bool = False
    safety_blocked_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "steps": [s.to_dict() for s in self.steps],
            "final_answer": self.final_answer,
            "needs_user_decision": bool(self.needs_user_decision),
            "next_action": self.next_action,
            "timed_out": bool(self.timed_out),
            "safety_blocked_reason": self.safety_blocked_reason,
        }


class ReActPlanError(RuntimeError):
    """Raised when the loop cannot proceed for structural reasons."""


# ---------------------------------------------------------------------------
# Built-in tool approvals.  Anything *not* in this set defaults to
# requires_approval=True, regardless of what the model asks.  This is the
# "permission second" layer (after the util.PermissionDenied gates in each
# actual L4 function).
# ---------------------------------------------------------------------------

NATURALLY_SAFE_TOOLS: frozenset[str] = frozenset({
    "list_project_files", "read_project_file", "read_memory", "search_memory",
    "list_memories", "ping", "status", "list_tools",
})

INTENT_TO_DEFAULT_MODE: dict[str, ExecutionMode] = {
    "answer": ExecutionMode.ACT,
    "learn": ExecutionMode.PROPOSE,
    "create": ExecutionMode.PROPOSE,
    "review": ExecutionMode.PROPOSE,
    "ask_permission": ExecutionMode.ASK_PERMISSION,
    "idle": ExecutionMode.IDLE,
}


# ---------------------------------------------------------------------------
# Helper helpers
# ---------------------------------------------------------------------------

def _extract_json_object(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end < 0 or end <= start:
        return None
    try:
        obj = json.loads(cleaned[start : end + 1])
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def _safe_elapsed(start: float) -> int:
    return int(round((time.monotonic() - start) * 1000))


# ---------------------------------------------------------------------------
# mode_router (Phase 4-12).
# ---------------------------------------------------------------------------

def mode_router(
    cognitive_decision: Any,
    intent: str,
    plan_steps: Iterable[Mapping[str, Any]] = (),
    *,
    approved_tools: Iterable[str] = (),
    user_prefer_confirm: bool = False,
) -> ExecutionRouterDecision:
    """Decide whether the companion should (a) propose steps, (b) directly
    act, (c) ask permission, or (d) do nothing.

    Inputs
    ------
    cognitive_decision:
        Either a :class:`agent.RoutedDecision` or any dict-shaped object
        exposing ``scene``, ``confidence``, ``mode``, ``recommended_intent``.
    intent:
        A value from :data:`brain.ALLOWED_INTENTS` (already normalised by
        upstream callers; invalid intents fall back to ``ask_permission``).
    plan_steps:
        Iterable of step-dicts (each may contain ``risk`` / ``tool`` /
        ``requires_approval``).
    approved_tools:
        Set of tool names the user has *already* consented to for this run;
        everything else still needs permission.
    user_prefer_confirm:
        Global "safety-first" flag; when true even ACT plans become
        PROPOSE unless the step is strictly read-only.
    """
    try:
        scene = getattr(cognitive_decision, "scene", cognitive_decision.get("scene") if isinstance(cognitive_decision, dict) else "chat") or "chat"
        confidence = float(getattr(cognitive_decision, "confidence", cognitive_decision.get("confidence") if isinstance(cognitive_decision, dict) else 0.0) or 0.0)
        cognitive_mode = getattr(cognitive_decision, "mode", cognitive_decision.get("mode") if isinstance(cognitive_decision, dict) else "direct") or "direct"
    except Exception:
        scene, confidence, cognitive_mode = "chat", 0.0, "direct"
    approved = frozenset(approved_tools)
    needs = list[str]()
    max_risk_rank = 0
    risk_rank = {"local_reversible": 1, "requires_permission": 2, "blocked": 3}
    for step in plan_steps:
        tool = step.get("tool") if isinstance(step, Mapping) else None
        risk = step.get("risk") if isinstance(step, Mapping) else None
        if isinstance(tool, str) and tool and tool not in approved and tool not in NATURALLY_SAFE_TOOLS:
            needs.append(tool)
        if isinstance(risk, str) and risk in risk_rank:
            max_risk_rank = max(max_risk_rank, risk_rank[risk])
        if isinstance(step, Mapping) and step.get("requires_approval") and tool:
            if tool not in needs:
                needs.append(tool)

    if intent == "ask_permission" or max_risk_rank >= 2:
        mode = ExecutionMode.ASK_PERMISSION
        priority = Priority.HIGH
        reason = f"intent={intent} / 步骤含风险({max_risk_rank})，需要用户授权。"
    elif intent == "idle":
        mode = ExecutionMode.IDLE
        priority = Priority.LOW
        reason = "无事可做，idle。"
    elif user_prefer_confirm:
        mode = ExecutionMode.PROPOSE
        priority = Priority.NORMAL
        reason = "用户偏好先确认；先走 propose 后 act。"
    elif cognitive_mode == "critical" or scene in {"system"}:
        mode = ExecutionMode.PROPOSE
        priority = Priority.NORMAL + (1 if confidence > 0.7 else 0)
        reason = f"场景={scene} / 批判性思考，先列建议再动手。"
    elif needs:
        mode = ExecutionMode.ASK_PERMISSION
        priority = Priority.HIGH
        reason = f"有 {len(needs)} 个工具尚未授权。"
    else:
        mode = INTENT_TO_DEFAULT_MODE.get(intent, ExecutionMode.PROPOSE)
        if cognitive_mode == "care":
            mode = ExecutionMode.PROPOSE
        priority = Priority.NORMAL
        if confidence >= 0.75 and intent in {"answer", "create"}:
            priority = Priority.HIGH
        reason = f"scene={scene}, confidence={round(confidence,2)}, cognitive_mode={cognitive_mode}。"
    return ExecutionRouterDecision(
        mode=mode,
        priority=max(Priority.LOW, min(Priority.CRITICAL, priority)),
        reason=reason,
        requires_approval=tuple(dict.fromkeys(needs)),
    )


# ---------------------------------------------------------------------------
# ReActPlanner.run (Phase 4-11).
# ---------------------------------------------------------------------------

class ReActPlanner:
    """Multi-step ReAct loop that is safe even when no inference engine is
    available.

    Parameters
    ----------
    engine:
        Anything exposing ``engine.generate(GenerationRequest, ...)`` or
        ``None``.  ``None`` / the placeholder backend fall back to
        rule-based heuristics.
    tool_catalog:
        Mapping of ``tool_name -> {"description": ..., "requires_approval": bool, ...}``.
        Defaults to :data:`agent_tools.TOOL_CATALOG` (lazy import).
    max_steps:
        Hard cap on loop iterations to prevent infinite loops.
    timeout_seconds:
        Wall-clock bound for the whole loop.
    """

    def __init__(
        self,
        engine: Any = None,
        tool_catalog: Mapping[str, Any] | None = None,
        *,
        max_steps: int = 8,
        timeout_seconds: int = 180,
    ) -> None:
        if max_steps < 1:
            raise ReActPlanError("max_steps must be >= 1")
        if timeout_seconds < 5:
            raise ReActPlanError("timeout_seconds must be >= 5")
        self.engine = engine
        self._catalog = tool_catalog
        self.max_steps = int(max_steps)
        self.timeout_seconds = int(timeout_seconds)
        self._lock = SingletonLock()

    # ------------------------------------------------------------------
    @property
    def tool_catalog(self) -> dict[str, Any]:
        if self._catalog is None:
            try:
                from agent_tools import TOOL_CATALOG
                self._catalog = dict(TOOL_CATALOG)
            except Exception:
                self._catalog = {}
        return dict(self._catalog)

    # ------------------------------------------------------------------
    def _is_placeholder(self) -> bool:
        if self.engine is None:
            return True
        name = getattr(self.engine, "model_name", "placeholder") or "placeholder"
        return str(name).lower() == "placeholder"

    # ------------------------------------------------------------------
    def _step_placeholder(self, idx: int, task: str, history: list[ReActStep]) -> ReActStep:
        """Zero-model fallback: produce 1-2 useful ReAct steps before
        returning an answer.
        """
        t0 = time.monotonic()
        low = task.casefold()
        if idx == 0:
            thought = (
                "（占位 ReAct，Thought 1/2）先判断任务是否只涉及读项目或纯回答；"
                "不涉及副作用则直接回答。"
            )
            action_type = "tool"
            tool_name = "list_project_files"
            tool_args = {"path": "."}
            requires_approval = tool_name not in NATURALLY_SAFE_TOOLS
            observation = ""
            reflection = "列出文件后我能更好判断后续需不需要 ask_permission。"
        elif idx == 1:
            thought = "（占位 ReAct，Thought 2/2）已完成读工具，收尾给出直接建议。"
            action_type = "answer"
            tool_name = None
            tool_args = {}
            requires_approval = False
            observation = "[placeholder: 无真实观察，留给 controller/agent_tools 去补]"
            reflection = "如果任务需要修改外部状态，mode_router 会转 ASK_PERMISSION。"
        else:
            thought = "（占位 ReAct 收敛）超过占位步数，中止并请求 controller 决策。"
            action_type = "abort"
            tool_name = None
            tool_args = {}
            requires_approval = False
            observation = ""
            reflection = "换真实 LLM 或补更多步骤再试。"
        return ReActStep(
            index=idx,
            thought=thought,
            action_type=action_type,
            tool_name=tool_name,
            tool_args=tool_args,
            observation=observation,
            reflection=reflection,
            elapsed_ms=_safe_elapsed(t0),
            requires_approval=requires_approval,
        )

    # ------------------------------------------------------------------
    def _step_with_engine(self, idx: int, task: str, history: list[ReActStep], scene_info: Mapping[str, Any]) -> ReActStep:
        t0 = time.monotonic()
        if self.engine is None:
            return self._step_placeholder(idx, task, history)
        try:
            from inference import GenerationRequest
        except Exception as exc:
            raise ReActPlanError(f"cannot import GenerationRequest: {exc}")
        history_text_lines = []
        for h in history[-6:]:
            history_text_lines.append(
                f"Step {h.index}: THOUGHT={truncate_text(h.thought,200,'')}\n"
                f"  ACTION={h.action_type}/{h.tool_name or '-'} args={json.dumps(h.tool_args, ensure_ascii=False)[:160]}\n"
                f"  OBS={truncate_text(h.observation,500,'')}\n  REFLECT={truncate_text(h.reflection,200,'')}"
            )
        catalog_json = json.dumps(self.tool_catalog, ensure_ascii=False)[:4000]
        scene_json = json.dumps(dict(scene_info or {}), ensure_ascii=False)[:600]
        prompt = (
            "你正在执行 Thought→Action→Observation→Reflection 的 ReAct 循环。\n"
            "规则：\n"
            "1) action_type 只能是 tool / answer / ask_user / blocked / abort。\n"
            "2) tool_name 必须来自 tool_catalog；读项目之外的任何工具默认都需要人工批准（requires_approval=true）。\n"
            "3) observation 字段请留空字符串，由 controller 在下一轮填入。\n"
            "4) 请严格只输出 JSON，不要 Markdown 或额外文字。格式：\n"
            '{"thought":"...","action_type":"tool","tool_name":"list_project_files",'
            '"tool_args":{"path":"."},"reflection":"...","requires_approval":false}\n'
            f"当前意图/场景（scene_info）：{scene_json}\n"
            f"工具清单（tool_catalog）：{catalog_json}\n"
            + ("历史步骤：\n" + "\n".join(history_text_lines) if history_text_lines else "（尚无历史）\n")
            + f"任务：{truncate_text(task,2000,'')}\n"
            f"第 {idx + 1} 步（共最多 {self.max_steps} 步）。"
        )
        try:
            req = GenerationRequest(
                prompt=prompt,
                max_tokens=420,
                json_mode=True,
                temperature=0.1,
                system_prompt=(
                    "你是墨灵内部规划器。仅返回合法 JSON；禁止编造观察结果；"
                    "禁止越过权限闸门调用危险工具。"
                ),
            )
            raw = self.engine.generate(req).strip()
        except Exception as exc:
            return ReActStep(
                index=idx,
                thought=f"模型调用失败：{exc}",
                action_type="abort",
                tool_name=None,
                tool_args={},
                observation="",
                reflection="回退到 controller 手动决策。",
                elapsed_ms=_safe_elapsed(t0),
                requires_approval=False,
            )
        obj = _extract_json_object(raw)
        if obj is None:
            return ReActStep(
                index=idx,
                thought=f"模型返回非 JSON：{truncate_text(raw, 200, '')}",
                action_type="abort",
                tool_name=None,
                tool_args={},
                observation="",
                reflection="无法解析，放弃。",
                elapsed_ms=_safe_elapsed(t0),
                requires_approval=False,
            )
        action_type = str(obj.get("action_type") or "answer").lower()
        if action_type not in {"tool", "answer", "ask_user", "blocked", "abort"}:
            action_type = "abort"
        tool_name = obj.get("tool_name") if action_type == "tool" else None
        if isinstance(tool_name, str):
            tool_name = tool_name.strip() or None
        if tool_name and tool_name not in self.tool_catalog:
            # Unknown tool → automatically blocked-for-safety.
            return ReActStep(
                index=idx,
                thought=str(obj.get("thought") or "")[:1000],
                action_type="blocked",
                tool_name=tool_name,
                tool_args=dict(obj.get("tool_args") or {}) if isinstance(obj.get("tool_args"), dict) else {},
                observation="",
                reflection=f"未知工具 '{tool_name}' 不在 catalog，blocked。",
                elapsed_ms=_safe_elapsed(t0),
                requires_approval=True,
            )
        tool_args = obj.get("tool_args") if isinstance(obj.get("tool_args"), dict) else {}
        requires_approval = bool(obj.get("requires_approval") or (
            tool_name is not None and tool_name not in NATURALLY_SAFE_TOOLS
        ))
        return ReActStep(
            index=idx,
            thought=truncate_text(str(obj.get("thought") or ""), 1500, ""),
            action_type=action_type,
            tool_name=tool_name,
            tool_args=tool_args,
            observation="",
            reflection=truncate_text(str(obj.get("reflection") or ""), 1000, ""),
            elapsed_ms=_safe_elapsed(t0),
            requires_approval=requires_approval,
        )

    # ------------------------------------------------------------------
    def run(
        self,
        task: str,
        *,
        intent: str = "answer",
        scene_info: Mapping[str, Any] | None = None,
        context: Iterable[tuple[str, str]] = (),
        approved_tools: Iterable[str] = (),
        on_step: Callable[[ReActStep], None] | None = None,
        observation_injector: Callable[[ReActStep], str] | None = None,
    ) -> ReActPlanResult:
        if not isinstance(task, str) or not task.strip():
            raise ReActPlanError("task must be a non-empty string")
        intent_ok = {"answer", "learn", "create", "review", "ask_permission", "idle"}
        if intent not in intent_ok:
            intent = "ask_permission"
        approved = frozenset(approved_tools)
        steps: list[ReActStep] = []
        start = time.monotonic()
        timed_out = False
        safety_reason: str | None = None
        final_answer = ""
        next_action: dict[str, Any] | None = None
        needs_user_decision = False

        with self._lock:
            for idx in range(self.max_steps):
                if time.monotonic() - start > self.timeout_seconds:
                    timed_out = True
                    break
                if self._is_placeholder():
                    raw_step = self._step_placeholder(idx, task, steps)
                else:
                    raw_step = self._step_with_engine(idx, task, steps, scene_info or {})
                # Inject observation from an external controller if provided.
                obs = ""
                if raw_step.action_type == "tool" and observation_injector is not None:
                    try:
                        obs = str(observation_injector(raw_step) or "")
                    except PermissionDenied as exc:
                        obs = f"[PermissionDenied] {exc}"
                    except Exception as exc:
                        obs = f"[ERROR] {exc}"
                # If a tool call *still* needs approval but wasn't granted,
                # convert the action to ask_user and bail so controller can
                # show UI.
                if (
                    raw_step.action_type == "tool"
                    and raw_step.requires_approval
                    and raw_step.tool_name not in approved
                    and raw_step.tool_name not in NATURALLY_SAFE_TOOLS
                ):
                    step = ReActStep(
                        index=idx,
                        thought=raw_step.thought,
                        action_type="ask_user",
                        tool_name=raw_step.tool_name,
                        tool_args=raw_step.tool_args,
                        observation=obs,
                        reflection=(
                            raw_step.reflection
                            + f" 工具 '{raw_step.tool_name}' 尚未获得本次会话批准，转为 ASK_PERMISSION。"
                        ),
                        elapsed_ms=raw_step.elapsed_ms,
                        requires_approval=True,
                    )
                    needs_user_decision = True
                    next_action = {
                        "action": "ask_permission",
                        "tool": raw_step.tool_name,
                        "args": dict(raw_step.tool_args),
                        "reason": step.reflection,
                    }
                    steps.append(step)
                    if on_step is not None:
                        on_step(step)
                    break
                else:
                    step = ReActStep(
                        index=idx,
                        thought=raw_step.thought,
                        action_type=raw_step.action_type,
                        tool_name=raw_step.tool_name,
                        tool_args=raw_step.tool_args,
                        observation=obs,
                        reflection=raw_step.reflection,
                        elapsed_ms=raw_step.elapsed_ms,
                        requires_approval=raw_step.requires_approval,
                    )
                steps.append(step)
                if on_step is not None:
                    try:
                        on_step(step)
                    except Exception:
                        pass
                if step.action_type == "answer":
                    final_answer = truncate_text(step.observation or step.thought or "", 8000, "")
                    break
                if step.action_type == "ask_user":
                    needs_user_decision = True
                    if next_action is None:
                        next_action = {
                            "action": "clarify",
                            "prompt": truncate_text(step.thought, 600, ""),
                        }
                    break
                if step.action_type == "blocked":
                    safety_reason = truncate_text(step.reflection or f"步骤 {idx} 被安全策略拦截。", 600, "")
                    break
                if step.action_type == "abort":
                    break
        return ReActPlanResult(
            intent=intent,
            steps=tuple(steps),
            final_answer=final_answer,
            needs_user_decision=needs_user_decision,
            next_action=next_action,
            timed_out=timed_out,
            safety_blocked_reason=safety_reason,
        )
