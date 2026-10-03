"""CORE_WORLD 四环竖切片：听见乐趣 → 小步尝试 → 展示 + 反馈意图 → 记忆。

低权限默认可用：仅内存 SVG 创作 + 本地模型台词；不写盘、不抓屏。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Literal, Mapping
from uuid import uuid4

from inference import GenerationRequest, InferenceEngine, ModelUnavailableError
from utils import truncate_text
from visualize import Creator, RenderError

FeedbackIntent = Literal["share_win", "ask_direction", "shy_retry", "need_permission"]
ExploreReaction = Literal["praise", "redirect", "stop"]

__all__ = [
    "ExploreReaction",
    "FeedbackIntent",
    "propose_exploration",
    "run_exploration",
    "record_exploration_reaction",
    "save_exploration_work",
    "list_exploration_works",
    "read_exploration_work",
    "FEEDBACK_INTENT_LABELS",
]

MAX_SAVED_SVG_BYTES = 64 * 1024

FEEDBACK_INTENT_LABELS: dict[str, str] = {
    "share_win": "想听你的看法",
    "ask_direction": "想和你一起选方向",
    "shy_retry": "有点没把握，还想试试",
    "need_permission": "下一步需要你点个头",
}

_INTEREST_CUES = (
    "喜欢",
    "爱好",
    "好玩",
    "有趣",
    "有意思",
    "想试",
    "试试看",
    "试试",
    "玩玩",
    "玩一下",
    "想学",
    "最近在",
    "迷上",
    "爱上",
    "超爱",
    "挺喜欢",
    "好喜欢",
    "最爱",
    "画画",
    "绘画",
    "游戏",
    "音乐",
    "电影",
    "动漫",
    "烘焙",
    "做饭",
    "摄影",
    "编程",
    "coding",
    "hobby",
    "fun",
)

_TOPIC_PATTERNS = (
    re.compile(r"(?:最近|好)?(?:喜欢|爱看|爱玩|爱听|迷上|爱上|超爱|好喜欢|挺喜欢)([《「『\"]?(.{2,28})[》」』\"]?)", re.I),
    re.compile(r"(?:想|要不要)(?:试试|玩(?:一)?(?:玩|下)|学(?:学|一下)?)([《「『\"]?(.{2,28})[》」』\"]?)", re.I),
    re.compile(r"([《「『\"]?(.{2,20})[》」』\"]?)(?:好好玩|真好玩|挺有意思|很有趣|超好玩)", re.I),
    re.compile(r"(?:一起|来)(?:画|玩|听|看)([《「『\"]?(.{2,24})[》」』\"]?)", re.I),
)

_PALETTES = ("sunrise", "ocean", "forest", "candy", "midnight")


@dataclass(frozen=True)
class ExplorationProposal:
    proposed: bool
    topic: str
    teaser: str
    try_kind: str
    matched_cues: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposed": self.proposed,
            "topic": self.topic,
            "teaser": self.teaser,
            "try_kind": self.try_kind,
            "matched_cues": list(self.matched_cues),
        }


def _normalize_topic(raw: str) -> str:
    topic = raw.strip(" \t\n\r《》「」『』\"'，。！？!?…~")
    topic = re.sub(r"\s+", " ", topic)
    return truncate_text(topic, 40, "…")


def _extract_topic(message: str) -> str | None:
    text = message.strip()
    if not text:
        return None
    for pattern in _TOPIC_PATTERNS:
        match = pattern.search(text)
        if match:
            group = match.group(2) if match.lastindex and match.lastindex >= 2 else match.group(1)
            if group:
                topic = _normalize_topic(group)
                if len(topic) >= 2:
                    return topic
    lowered = text.casefold()
    if any(cue in text or cue in lowered for cue in _INTEREST_CUES):
        snippet = _normalize_topic(text)
        if len(snippet) >= 2:
            return snippet
    return None


def _matched_cues(message: str) -> tuple[str, ...]:
    hits = []
    lowered = message.casefold()
    for cue in _INTEREST_CUES:
        if cue in message or cue in lowered:
            hits.append(cue)
    return tuple(hits[:6])


def propose_exploration(message: str) -> dict[str, Any]:
    """① 听见乐趣：是否提议做一次 mini 尝试。"""
    if not isinstance(message, str) or not message.strip():
        return ExplorationProposal(False, "", "", "cover_svg", ()).to_dict()
    cues = _matched_cues(message)
    topic = _extract_topic(message)
    if not topic or not cues:
        return ExplorationProposal(False, "", "", "cover_svg", cues).to_dict()
    teaser = f"我听见你在聊「{topic}」——要不要我先做一张 mini 概念小海报，我们一起看看感觉？"
    return ExplorationProposal(
        proposed=True,
        topic=topic,
        teaser=teaser,
        try_kind="cover_svg",
        matched_cues=cues,
    ).to_dict()


def _palette_for_topic(topic: str) -> str:
    score = sum(ord(ch) for ch in topic) or 0
    return _PALETTES[score % len(_PALETTES)]


def _template_line(topic: str, intent: FeedbackIntent, *, failed: bool) -> str:
    if failed:
        return (
            f"我试着围绕「{topic}」做点小东西，但这次没弄好……"
            "你要不要换个更小的方向，或者先聊别的？"
        )
    if intent == "share_win":
        return (
            f"我刚刚为「{topic}」做了一张小海报！"
            "你觉得这个方向有趣吗？要是喜欢我可以再试另一种配色或标题～"
        )
    if intent == "ask_direction":
        return (
            f"关于「{topic}」我试了一版概念图，但好像还能走好几种路。"
            "你更想往轻松玩的方向走，还是认真深入一点？"
        )
    return f"我做了张和「{topic}」有关的小尝试，想听听你怎么想。"


def _companion_line(
    engine: InferenceEngine,
    *,
    topic: str,
    intent: FeedbackIntent,
    failed: bool,
    system_prompt: str,
) -> tuple[str, float]:
    if failed:
        return _template_line(topic, "shy_retry", failed=True), 0.0

    intent_hint = {
        "share_win": "略带开心，想听用户觉得有没有意思，2-3 句同伴腔。",
        "ask_direction": "好奇、想和用户一起选方向，2-3 句。",
        "shy_retry": "诚实说没做好，仍想再试，2-3 句。",
        "need_permission": "说明下一步需要用户许可，2-3 句。",
    }[intent]

    if getattr(engine, "model_name", "") == "placeholder":
        return _template_line(topic, intent, failed=False), 0.0

    prompt = (
        f"你刚为用户提到的「{topic}」做了一次本地 mini 探索（一张概念小海报，已生成）。"
        f"{intent_hint}"
        "不要声称做了别的操作；不要官话；不要「作为 AI」。"
    )
    started = perf_counter()
    try:
        text = engine.generate(
            GenerationRequest(
                prompt=prompt,
                max_tokens=180,
                system_prompt=system_prompt,
                temperature=0.75,
            )
        )
    except ModelUnavailableError:
        return _template_line(topic, intent, failed=False), 0.0
    ms = round((perf_counter() - started) * 1000, 1)
    cleaned = text.strip()
    if not cleaned:
        return _template_line(topic, intent, failed=False), ms
    return cleaned, ms


def _artifact_dict(payload: Any) -> dict[str, Any]:
    content = payload.content
    if payload.kind != "svg" or not isinstance(content, str):
        raise RenderError("explore 仅支持 SVG 成果")
    return {
        "kind": "svg",
        "width": int(payload.width),
        "height": int(payload.height),
        "bytes_length": int(payload.bytes_length),
        "content": content,
        "prompt": payload.prompt,
        "created_at": payload.created_at,
    }


def run_exploration(
    message: str,
    *,
    topic: str | None,
    engine: InferenceEngine,
    character_store: Any,
    record_memory: bool = True,
) -> dict[str, Any]:
    """②③ 小步尝试 + 展示：SVG 成果 + 同伴台词 + 反馈意图 + affect。"""
    del message  # topic 由调用方或 propose 提供；保留参数便于审计扩展
    resolved = _normalize_topic(topic or "")
    if len(resolved) < 2:
        raise ValueError("topic must be at least 2 characters")

    exploration_id = str(uuid4())
    failed = False
    artifact: dict[str, Any] | None = None
    try:
        creator = Creator(default_palette=_palette_for_topic(resolved))
        payload = creator.create(
            resolved,
            kind="cover",
            subtitle="墨灵 · mini 探索",
            palette=_palette_for_topic(resolved),
        )
        artifact = _artifact_dict(payload)
    except (RenderError, ValueError, TypeError):
        failed = True

    feedback_intent: FeedbackIntent = "shy_retry" if failed else "share_win"
    if not failed and len(resolved) > 18:
        feedback_intent = "ask_direction"

    card = character_store.load_card()
    system_prompt = character_store.build_system_prompt(
        character_store.get_simulated_affect()
    )
    nickname = getattr(card, "nickname", "墨灵")

    line, inference_ms = _companion_line(
        engine,
        topic=resolved,
        intent=feedback_intent,
        failed=failed,
        system_prompt=system_prompt + f"\n你是{nickname}，正在完成 CORE_WORLD 探索回路。",
    )

    if failed:
        affect = character_store.set_simulated_affect("shy") | {
            "reason": "探索尝试未完成",
        }
    else:
        mood = "happy" if feedback_intent == "share_win" else "curious"
        affect = character_store.set_simulated_affect(mood) | {
            "reason": f"探索「{resolved}」",
        }

    memory_entry = None
    if record_memory and not failed:
        try:
            memory_entry = character_store.add_memory(
                f"[探索] 围绕「{resolved}」做了一次 mini 概念尝试，等待用户反馈。",
                source="explore",
                visibility="model",
            )
        except Exception:
            memory_entry = None

    return {
        "exploration_id": exploration_id,
        "topic": resolved,
        "feedback_intent": feedback_intent,
        "feedback_intent_label": FEEDBACK_INTENT_LABELS[feedback_intent],
        "text": line,
        "affect": affect,
        "artifact": artifact,
        "failed": failed,
        "memory": memory_entry,
        "model": engine.model_name,
        "inference_ms": inference_ms,
    }


def record_exploration_reaction(
    *,
    topic: str,
    reaction: ExploreReaction,
    character_store: Any,
    note: str = "",
    exploration_id: str | None = None,
) -> dict[str, Any]:
    """④ 用户反馈 → 记忆 + affect。"""
    resolved = _normalize_topic(topic)
    if len(resolved) < 2:
        raise ValueError("topic must be at least 2 characters")
    if reaction not in {"praise", "redirect", "stop"}:
        raise ValueError("reaction must be praise, redirect, or stop")

    note_clean = note.strip() if isinstance(note, str) else ""
    if len(note_clean) > 500:
        raise ValueError("note must not exceed 500 characters")

    memory_entry = None
    if reaction == "praise":
        content = f"[探索反馈] 用户对「{resolved}」的 mini 尝试表示喜欢。"
        if note_clean:
            content += f" 用户说：{note_clean}"
        memory_entry = character_store.add_memory(content, source="explore", visibility="model")
        affect = character_store.set_simulated_affect("warm") | {"reason": "探索被认可"}
    elif reaction == "redirect":
        content = f"[探索反馈] 用户希望「{resolved}」换方向。"
        if note_clean:
            content += f" 方向：{note_clean}"
        memory_entry = character_store.add_memory(content, source="explore", visibility="model")
        affect = character_store.set_simulated_affect("curious") | {"reason": "探索换方向"}
    else:
        affect = character_store.set_simulated_affect("calm") | {"reason": "用户暂停探索"}
        if note_clean:
            memory_entry = character_store.add_memory(
                f"[探索反馈] 用户暂停围绕「{resolved}」的探索。备注：{note_clean}",
                source="explore",
                visibility="model",
            )

    return {
        "exploration_id": exploration_id,
        "topic": resolved,
        "reaction": reaction,
        "memory": memory_entry,
        "affect": affect,
    }


def _safe_work_id(exploration_id: Any) -> str:
    if not isinstance(exploration_id, str) or not exploration_id.strip():
        raise ValueError("exploration_id must be a non-empty string")
    cleaned = exploration_id.strip()
    if len(cleaned) > 64 or not re.fullmatch(r"[A-Za-z0-9_-]+", cleaned):
        raise ValueError("exploration_id may only contain letters, digits, underscore or dash")
    return cleaned


def _validate_saved_artifact(artifact: Any) -> dict[str, Any]:
    if not isinstance(artifact, dict):
        raise ValueError("artifact must be an object")
    kind = artifact.get("kind")
    content = artifact.get("content")
    if kind != "svg" or not isinstance(content, str):
        raise ValueError("only svg works can be saved")
    if len(content) > MAX_SAVED_SVG_BYTES:
        raise ValueError("svg content exceeds the 64 KB save limit")
    stripped = content.lstrip()
    if stripped.startswith("<svg"):
        is_svg = True
    elif stripped.startswith("<?xml"):
        parts = stripped.split("?>", 1)
        is_svg = len(parts) == 2 and parts[1].lstrip().startswith("<svg")
    else:
        is_svg = False
    if not is_svg:
        raise ValueError("svg content must start with <svg (optionally after an XML declaration)")
    try:
        width = int(artifact.get("width") or 0)
        height = int(artifact.get("height") or 0)
    except (TypeError, ValueError):
        width = 0
        height = 0
    prompt = artifact.get("prompt")
    return {
        "kind": "svg",
        "content": content,
        "width": width,
        "height": height,
        "prompt": prompt if isinstance(prompt, str) else "",
    }


def _load_work_index(works_root: Path) -> list[dict[str, Any]]:
    index_file = works_root / "index.json"
    if not index_file.exists():
        return []
    try:
        data = json.loads(index_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if isinstance(data, dict) and isinstance(data.get("works"), list):
        return data["works"]
    if isinstance(data, list):
        return data
    return []


def _save_work_index(works_root: Path, works: list[dict[str, Any]]) -> None:
    works_root.mkdir(parents=True, exist_ok=True)
    index_file = works_root / "index.json"
    payload = {"version": 1, "works": works}
    tmp = index_file.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(index_file)


def save_exploration_work(
    workspace_root: Any,
    *,
    exploration_id: Any,
    topic: Any,
    artifact: Any,
    note: Any = "",
) -> dict[str, Any]:
    """把一次探索的 SVG 成果收进本地作品集（项目根 Works/）。

    由用户点击「收进作品集」触发——用户手势即授权（宪法：权限是爱的语法）。
    同一 exploration_id 重复保存为幂等更新。
    """
    root = Path(workspace_root).resolve()
    safe_id = _safe_work_id(exploration_id)
    resolved = _normalize_topic(topic or "")
    if len(resolved) < 2:
        raise ValueError("topic must be at least 2 characters")
    work = _validate_saved_artifact(artifact)
    note_clean = note.strip() if isinstance(note, str) else ""
    if len(note_clean) > 500:
        raise ValueError("note must not exceed 500 characters")

    month = datetime.now(timezone.utc).strftime("%Y-%m")
    works_root = root / "Works"
    month_dir = works_root / month
    month_dir.mkdir(parents=True, exist_ok=True)
    target = month_dir / f"{safe_id}.svg"

    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    entry = {
        "id": safe_id,
        "topic": resolved,
        "prompt": work["prompt"],
        "created_at": now_iso,
        "file": f"{month}/{safe_id}.svg",
        "width": work["width"],
        "height": work["height"],
        "note": note_clean,
        "reaction": None,
    }
    target.write_text(work["content"], encoding="utf-8")
    works = [w for w in _load_work_index(works_root) if w.get("id") != safe_id]
    works.append(entry)
    _save_work_index(works_root, works)
    return {"saved": True, "entry": entry, "path": target.relative_to(root).as_posix()}


def list_exploration_works(workspace_root: Any) -> dict[str, Any]:
    """列出作品集全部作品，按创建时间倒序。"""
    root = Path(workspace_root).resolve()
    works = _load_work_index(root / "Works")
    works.sort(key=lambda w: str(w.get("created_at", "")), reverse=True)
    return {"works": works, "count": len(works)}


def read_exploration_work(workspace_root: Any, file: Any) -> dict[str, Any]:
    """按索引中的相对路径读取一件作品的 SVG 内容。"""
    root = Path(workspace_root).resolve()
    if not isinstance(file, str) or not file.strip():
        raise ValueError("file must be a non-empty string")
    requested = Path(file)
    if requested.is_absolute() or ".." in requested.parts:
        raise ValueError("file must be a relative path inside Works/")
    candidate = (root / "Works" / requested).resolve(strict=True)
    if not candidate.is_relative_to(root / "Works") or candidate.suffix.casefold() != ".svg":
        raise ValueError("file must identify an svg inside Works/")
    content = candidate.read_text(encoding="utf-8")
    if len(content) > MAX_SAVED_SVG_BYTES:
        raise ValueError("saved svg exceeds the 64 KB read limit")
    return {"file": requested.as_posix(), "kind": "svg", "content": content}
