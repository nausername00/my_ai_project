"""S6 三角协作回路：冰（守界）/ 火（破局）/ 平衡（调和）。

把一次任务交给三个思维角色：
  火（fire）   → 打破常规，发散方案；
  冰（ice）    → 严格逻辑与结构化约束，逐项校验并给出 verdict；
  平衡（衡）   → 引导与排雷，在冰火之间独立裁决（不靠多数票）。

边界与 S 系列一致：本模块只产出「建议 / 裁决 / 文案」，不执行任何
文件、网络、系统或外部操作；裁决规则本地确定性、可测试；
冰的输出解析失败时保守回退（defer），安全优先。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Callable

from inference import GenerationRequest, InferenceEngine, ModelUnavailableError
from collaboration import is_local_engine


@dataclass(frozen=True)
class ThinkingRole:
    key: str
    name: str
    mode: str
    focus: str
    instruction: str


THINKING_ROLES = (
    ThinkingRole(
        "fire",
        "破局·火",
        "fire",
        "打破常规、发散、敢想",
        "跳出既有框架给出方案：换角度、反着想、补出边界外的可能性；"
        "只给思路与可执行的方案文本，不声称已执行任何操作。",
    ),
    ThinkingRole(
        "ice",
        "守界·冰",
        "ice",
        "严格逻辑、结构化、守边界",
        "校验方案的结构、边界、风险、证据与可行性：给出 verdict"
        "（accept=可采纳 / revise=需修正 / reject=打回重做）与问题清单；"
        "不执行任何操作，只输出校验结论。",
    ),
    ThinkingRole(
        "balance",
        "调和·衡",
        "balance",
        "引导、排雷、权衡",
        "先听火与冰的原始观点，独立裁决：创意保住多少、风险如何处置、"
        "要不要打回重做或回退给主墨灵；不做简单多数票。",
    ),
)

MAX_RESPONSE_CHARS = 1600
# 裁决动作：adopt=采纳火方案 / patch=火为主体+冰修正 / rework=打回火重做 / defer=回主墨灵
VALID_ACTIONS = ("adopt", "patch", "rework", "defer")


def list_trio_roles() -> list[dict[str, str]]:
    return [
        {
            "key": role.key,
            "name": role.name,
            "mode": role.mode,
            "focus": role.focus,
            "instruction": role.instruction,
        }
        for role in THINKING_ROLES
    ]


# ---------------------------------------------------------------------------
# 冰的审校解析（确定性、可测）
# ---------------------------------------------------------------------------


def _parse_review(raw: str) -> dict[str, Any]:
    """解析冰的审校输出：优先 JSON，其次关键字；解析失败按保守处理。

    返回 {verdict, issues, suggestions, raw}；verdict ∈ accept/revise/reject/unknown。
    """
    text = raw.strip()
    parsed: dict[str, Any] = {}
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            parsed = data
    except json.JSONDecodeError:
        pass

    verdict = str(parsed.get("verdict", "")).strip().lower()
    if verdict not in {"accept", "revise", "reject"}:
        lowered = text.casefold()
        if "verdict" in lowered and "accept" in lowered:
            verdict = "accept"
        elif "revise" in lowered:
            verdict = "revise"
        elif "reject" in lowered:
            verdict = "reject"
        else:
            verdict = "unknown"

    issues = parsed.get("issues")
    if not isinstance(issues, list):
        issues = []
    issues = [str(item).strip() for item in issues if str(item).strip()][:8]
    suggestions = parsed.get("suggestions")
    if not isinstance(suggestions, list):
        suggestions = []
    suggestions = [str(item).strip() for item in suggestions if str(item).strip()][:8]
    return {
        "verdict": verdict,
        "issues": issues,
        "suggestions": suggestions,
        "raw": raw,
    }


# ---------------------------------------------------------------------------
# 平衡裁决（确定性核心：不靠多数票，安全优先）
# ---------------------------------------------------------------------------


def _decide(
    task: str,
    fire_output: str,
    review: dict[str, Any],
    *,
    rounds_used: int,
    max_rounds: int,
) -> dict[str, Any]:
    """平衡者裁决：根据冰的 verdict 独立决定动作与最终文案。

    - accept  → adopt：采纳火方案，附冰的提醒（若有）。
    - revise  → patch：火为主体，冰的修正建议并排追加。
    - reject  → rework（未到重做上限）/ defer（已到上限或任务危险）。
    - unknown → defer：解析失败时保守回退给主墨灵，绝不强行采纳。
    """
    verdict = review.get("verdict")
    issues = review.get("issues") or []
    suggestions = review.get("suggestions") or []

    if verdict == "accept":
        tail = ""
        if issues:
            tail = "\n[守界提醒] " + "；".join(issues[:3])
        return {
            "action": "adopt",
            "reason": "冰校验通过，采纳火方案。",
            "final": (fire_output[:MAX_RESPONSE_CHARS] + tail).strip(),
        }
    if verdict == "revise":
        patches = "; ".join(suggestions[:4]) or "; ".join(issues[:4])
        final = fire_output[:MAX_RESPONSE_CHARS]
        if patches:
            final = f"{final}\n[冰的修正] {patches}"
        return {
            "action": "patch",
            "reason": "火方案有创意但需补强，采纳主体并纳入冰的修正。",
            "final": final.strip(),
        }
    if verdict == "reject":
        if rounds_used < max_rounds:
            return {
                "action": "rework",
                "reason": f"冰判定方案不可采纳（{len(issues)} 个问题），打回火重做。",
                "final": "",
            }
        return {
            "action": "defer",
            "reason": "多轮重做后冰仍未放行，回退给主墨灵直接处理，避免硬闯。",
            "final": "",
        }
    return {
        "action": "defer",
        "reason": "冰的审校未给出可解析结论，保守回退给主墨灵。",
        "final": "",
    }


# ---------------------------------------------------------------------------
# 默认三方调用（真实模型）；测试可注入 stub 回调
# ---------------------------------------------------------------------------


def _make_fire_caller(
    engine: InferenceEngine,
    system_prompt: str,
) -> Callable[[str], str]:
    def call(task: str) -> str:
        response = engine.generate(
            GenerationRequest(
                prompt=(
                    "这是一个本地协作任务。你不是墨灵本人，而是她的协作伙伴『破局·火』。"
                    "请打破常规给出方案思路：换角度、反着想、补出边界外的可能性。"
                    "只提供可核验、可执行的方案文本，不要声称已修改文件或完成测试。"
                    f"\n任务：\n{task}"
                ),
                max_tokens=520,
                system_prompt=(
                    system_prompt
                    + "\n你是『破局·火』。不要执行文件、网络、联系人、系统操作。"
                ),
            )
        ).strip()
        if not response:
            raise ModelUnavailableError("模型返回了空方案")
        return response

    return call


def _make_ice_caller(
    engine: InferenceEngine,
    system_prompt: str,
) -> Callable[[str, str], str]:
    def call(task: str, fire_output: str) -> str:
        response = engine.generate(
            GenerationRequest(
                prompt=(
                    "这是一个本地协作校验任务。你不是墨灵本人，而是『守界·冰』。"
                    "严格校验下面的方案：结构、边界、风险、证据与可行性。"
                    "请输出 JSON（不要 Markdown）："
                    '{"verdict":"accept|revise|reject","issues":["问题1"],"suggestions":["修正1"]}；'
                    "没有内容时用空数组。若无法给出 JSON，也请直接说明 verdict"
                    "（accept/revise/reject）与问题。不要声称已执行任何操作。"
                    f"\n任务：\n{task}\n\n待校验方案：\n{fire_output}"
                ),
                max_tokens=420,
                system_prompt=(
                    system_prompt
                    + "\n你是『守界·冰』。不要执行文件、网络、联系人、系统操作。"
                ),
                temperature=0.0,
            )
        ).strip()
        if not response:
            raise ModelUnavailableError("模型返回了空校验")
        return response

    return call


def _make_balance_caller(
    engine: InferenceEngine,
    system_prompt: str,
) -> Callable[[str, str, dict[str, Any], dict[str, Any]], str]:
    def call(
        task: str,
        fire_output: str,
        review: dict[str, Any],
        decision: dict[str, Any],
    ) -> str:
        response = engine.generate(
            GenerationRequest(
                prompt=(
                    "这是一个本地协作总结任务。你是墨灵的分身『调和·衡』，"
                    "负责把火与冰的产出合成给用户听：说明采纳了什么、修正了什么、"
                    "为什么这样裁决；语气温和但明确。只给最终文案，不要执行任何操作。"
                    f"\n任务：\n{task}"
                    f"\n火方案：\n{fire_output[:800]}"
                    f"\n冰校验：{review.get('raw', '')[:500]}"
                    f"\n平衡裁决：{decision.get('reason', '')} / 动作={decision.get('action', '')}"
                ),
                max_tokens=420,
                system_prompt=(
                    system_prompt
                    + "\n你是『调和·衡』。不要执行文件、网络、联系人、系统操作。"
                ),
            )
        ).strip()
        return response or decision.get("reason", "")

    return call


# ---------------------------------------------------------------------------
# 三角回路
# ---------------------------------------------------------------------------


def run_trio(
    engine: InferenceEngine,
    system_prompt: str,
    task: str,
    *,
    fire: Callable[[str], str] | None = None,
    ice: Callable[[str, str], str] | None = None,
    balance: Callable[[str, str, dict[str, Any], dict[str, Any]], str] | None = None,
    max_rounds: int = 2,
) -> dict[str, Any]:
    """跑一轮（最多 max_rounds 轮）三角协作：火发散 → 冰校验 → 衡裁决。

    只允许本机模型服务；回调可注入（测试用 stub）。
    """
    if not is_local_engine(engine):
        raise ValueError("三角协作只允许使用本机模型服务")
    fire_fn = fire or _make_fire_caller(engine, system_prompt)
    ice_fn = ice or _make_ice_caller(engine, system_prompt)
    balance_fn = balance
    started_at = perf_counter()

    rounds: list[dict[str, Any]] = []
    current_fire = fire_fn(task)
    rounds.append({"role": "fire", "name": "破局·火", "response": current_fire})

    review = _parse_review(ice_fn(task, current_fire))
    rounds.append(
        {
            "role": "ice",
            "name": "守界·冰",
            "response": review["raw"],
            "verdict": review["verdict"],
        }
    )
    rounds_used = 1
    while review["verdict"] == "reject" and rounds_used < max_rounds:
        rounds_used += 1
        current_fire = fire_fn(
            f"{task}\n\n上一轮方案被『守界·冰』打回，原因："
            + ("；".join(review["issues"]) or "结构/边界/风险不足")
            + "。请换一个思路重新给出方案。"
        )
        rounds.append({"role": "fire", "name": "破局·火", "response": current_fire})
        review = _parse_review(ice_fn(task, current_fire))
        rounds.append(
            {
                "role": "ice",
                "name": "守界·冰",
                "response": review["raw"],
                "verdict": review["verdict"],
            }
        )

    decision = _decide(
        task,
        current_fire,
        review,
        rounds_used=rounds_used,
        max_rounds=max_rounds,
    )
    balance_text = ""
    if balance_fn is not None:
        try:
            balance_text = balance_fn(task, current_fire, review, decision) or ""
        except ModelUnavailableError:
            balance_text = ""
    final = decision["final"] or balance_text or current_fire

    return {
        "task": task,
        "lead": "moling",
        "roles": [role.key for role in THINKING_ROLES],
        "rounds": rounds,
        "rounds_used": rounds_used,
        "decision": {
            "action": decision["action"],
            "reason": decision["reason"],
            "final": final,
        },
        "model": engine.model_name,
        "source": "local",
        "duration_ms": round((perf_counter() - started_at) * 1000),
    }
