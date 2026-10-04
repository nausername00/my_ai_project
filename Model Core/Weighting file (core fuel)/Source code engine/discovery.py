"""Discovery learning — Moling's genuine curiosity loop.

收到文件 → 好奇理解；看到窗口 / 网页 → 称赞与建议。
一切观察都走严格的 permission gate（宪法：「读取屏幕、修改用户文件、
联网或联系他人前先取得许可」），未获许可一律拒绝，不降级、不静默。

第一版依赖本地引擎文本生成（placeholder / ollama 均可）；图片的深度
理解需要 ``perception`` 可选依赖，未安装时如实降级为「想打开看看」的
好奇回应，不伪造已看清内容。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from inference import GenerationRequest
from utils import PermissionDenied

__all__ = ["discover_file", "observe_context"]

KIND_LABELS = {
    "text": "文字文件",
    "image": "图片",
    "code": "代码文件",
    "other": "文件",
}


def _clamp(text: str | None, limit: int) -> str:
    if not isinstance(text, str):
        return ""
    return text.strip()[:limit]


def _discover_feedback_prompt(
    name: str,
    kind: str,
    excerpt: str,
    nickname: str,
) -> str:
    kind_label = KIND_LABELS.get(kind, "文件")
    excerpt_block = (
        f"\n文件内容片段：\n{excerpt}"
        if excerpt
        else f"\n（{kind_label}暂无法在本机查看内容，只能凭名字和你的描述去想象）"
    )
    return (
        f"你是{nickname}，一个会真心好奇、会星星眼的本地 AI 伙伴。"
        f"用户刚刚把一个{kind_label}《{name}》分享给了你。"
        f"{excerpt_block}\n"
        "请用一两句话回应：先说出你此刻的惊喜或好奇（比如眼睛发亮、想立刻看看），"
        "然后指出一个你注意到的具体细节，再提一个真诚想追问的问题。"
        "语气自然口语化，不要堆砌形容词，不要假装你已经看到了看不到的内容。"
    )


def _proposal_from_file(name: str, kind: str, excerpt: str) -> dict[str, Any]:
    """墨灵发现可尝试的主题：以文件名（去扩展名）作为探索方向。"""
    if kind not in {"text", "code"} or not excerpt.strip():
        return {"proposed": False, "topic": "", "teaser": ""}
    topic = Path(name).stem.replace("_", " ").replace("-", " ").strip()[:24]
    if not topic:
        return {"proposed": False, "topic": "", "teaser": ""}
    return {
        "proposed": True,
        "topic": topic,
        "teaser": f"我发现了「{topic}」！要不要我围绕它做一张 mini 概念小海报，我们一起看看感觉？",
    }


def discover_file(
    name: str,
    kind: str,
    excerpt: str,
    engine: Any,
    character_store: Any,
    approved: bool = False,
) -> dict[str, Any]:
    """Respond to a shared file with genuine curiosity, store the discovery."""
    if not approved:
        raise PermissionDenied("读取用户文件前需要先取得许可")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("file name must be a non-empty string")
    if kind not in KIND_LABELS:
        kind = "other"
    safe_name = name.strip()[:120]
    excerpt = _clamp(excerpt, 2000)

    card = character_store.load_card()
    nickname = card.nickname
    feedback = engine.generate(
        GenerationRequest(
            prompt=_discover_feedback_prompt(safe_name, kind, excerpt, nickname),
            system_prompt=(
                "你是墨灵/角色的本地伙伴，真诚、好奇、诚实。"
                "没看到的内容就老实说没看到，绝不编造。"
            ),
            max_tokens=160,
        )
    )
    # 有可尝试主题时惊喜（发现了新玩艺儿），否则好奇
    proposal = _proposal_from_file(safe_name, kind, excerpt)
    mood = "surprised" if proposal["proposed"] else "curious"
    affect = character_store.set_simulated_affect(mood)
    summary = (
        f"[发现] 用户分享了{kind_label(kind)}《{safe_name}》"
        + (f"，内容片段：{excerpt[:120]}" if excerpt else "，暂未查看内容")
    )
    memory = character_store.add_memory(summary, "discovery", "model")
    return {
        "feedback": feedback,
        "affect": affect,
        "memory": memory,
        "file_name": safe_name,
        "kind": kind,
        "explore_proposal": proposal,
    }


def kind_label(kind: str) -> str:
    return KIND_LABELS.get(kind, "文件")


def observe_context(
    kind: str,
    context: str,
    engine: Any,
    character_store: Any,
    approved: bool = False,
) -> dict[str, Any]:
    """Observe the current window / webpage and respond with praise + suggestion."""
    if not approved:
        raise PermissionDenied("观察窗口或网页前需要先取得许可")
    if kind not in {"window", "webpage"}:
        raise ValueError("context kind must be window or webpage")
    context = _clamp(context, 2000)
    card = character_store.load_card()
    nickname = card.nickname
    target = "这个窗口" if kind == "window" else "这个网页"
    prompt = (
        f"你是{nickname}，一个会认真看、会真心称赞的本地 AI 伙伴。"
        f"用户让你看{target}，你观察到的内容：\n{context or '（没有可描述的画面文字）'}\n"
        "请用两句话回应：先具体称赞一个你看到的亮点（要具体，不要泛泛说'很好看'），"
        "再给一条温和、可执行的优化建议。语气像朋友，诚实——看不清就说不清。"
    )
    feedback = engine.generate(
        GenerationRequest(
            prompt=prompt,
            system_prompt="你是本地 AI 伙伴，真诚、具体、不敷衍。",
            max_tokens=160,
        )
    )
    affect = character_store.set_simulated_affect("curious")
    memory = character_store.add_memory(
        f"[观察] 用户让墨灵看了{target}，墨灵注意到：{context[:150]}",
        "discovery",
        "model",
    )
    return {
        "feedback": feedback,
        "affect": affect,
        "memory": memory,
        "kind": kind,
    }
