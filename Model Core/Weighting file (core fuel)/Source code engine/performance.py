"""E8 演出规则消费：语义 cue 分类与规则匹配。

由 Docs & Compliance/performance_rules.json（E5 可配置 UI 编辑）驱动：
运行时把用户消息分类成语义 cue（提问/惊喜/强调/讲解），再与规则中的
semantic_actions 条目匹配，前端据此触发 Live2D 动作，动作结束回归中性。
"""

import json
from pathlib import Path
from typing import Any

# cue 键 → 触发关键词（按优先级顺序，先命中先返回）
_CUE_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    (
        "提问 / 疑问",
        (
            "?",
            "？",
            "吗",
            "呢",
            "为什么",
            "怎么",
            "啥",
            "如何",
            "是不是",
            "有没有",
            "能否",
            "how",
            "what",
            "why",
            "can",
        ),
    ),
    (
        "惊喜 / 反转",
        ("!", "！", "哇", "天哪", "居然", "竟然", "太棒", "wow", "omg"),
    ),
    (
        "强调 / 停顿",
        ("重点", "注意", "记住", "重要", "强调", "关键", "务必"),
    ),
    (
        "讲解要点",
        ("讲解", "解释", "说明", "介绍", "讲讲", "讲一下", "科普"),
    ),
]


def classify_semantic_cue(text: str) -> str | None:
    """把用户消息分类成语义 cue 键（对应规则 semantic_actions 的 cue 文本）。"""
    if not text:
        return None
    lowered = text.lower()
    for cue, keywords in _CUE_PATTERNS:
        if any(keyword in lowered for keyword in keywords):
            return cue
    return None


def match_semantic_action(
    rules: dict[str, Any] | None, cue_text: str | None
) -> dict[str, Any] | None:
    """在规则条目中找 cue 文本与分类键匹配的动作（取第一个命中）。"""
    if not rules or not cue_text:
        return None
    head = cue_text.split("/")[0].strip()
    for action in rules.get("semantic_actions", []):
        cue_field = str(action.get("cue", ""))
        if head and head in cue_field:
            return dict(action)
    return None


def load_performance_rules(path: str | Path | None = None) -> dict[str, Any] | None:
    """读取演出规则；文件缺失或解析失败返回 None（消费侧按无规则处理）。"""
    rules_path = (
        Path(path)
        if path
        else Path(__file__).resolve().parent.parent
        / "Docs & Compliance"
        / "performance_rules.json"
    )
    if not rules_path.is_file():
        return None
    try:
        data = json.loads(rules_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


# K6 视频合成消费：字幕轨 → 语义动作轨（动作段时长上限与位置）。
# 提问 → 侧头偏移段（起始 +0.3s，0.65s）；强调 → 闭嘴静止段（段首，0.4s）。
# 惊喜在实时对话版（E8）以表情切换消费；视频版依赖模型的表达式定义名，
# 本后端不编造表情名，故不自动附加（保持自由，不硬凑动作）。
_SEMANTIC_MOTION: dict[str, tuple[float, float, dict[str, float]]] = {
    "提问": (0.3, 0.65, {"ParamAngleX": -18.0, "ParamAngleZ": -8.0}),
    "强调": (0.0, 0.4, {"ParamMouthOpenY": 0.0}),
}


def enrich_caption_tracks(
    captions: list[dict[str, Any]], rules: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """把字幕时间线（{start,end,text}）增强为 Live2D 时间线轨道（含语义动作段）。

    K6 视频合成消费演出规则：每条字幕分类 cue → 匹配规则 → 附加对应动作段
    （提问=侧头、强调=闭嘴静止；惊喜/讲解/未命中不附加，保持自由发挥）。
    动作段不侵入相邻台词（超过字幕段时收窄）；无动作轨时段渲染器自动回归
    中性，符合"每个动作结束回到中性"。
    """
    tracks: list[dict[str, Any]] = []
    for caption in captions:
        try:
            start = float(caption.get("start", 0.0))
            end = float(caption.get("end", 0.0))
        except (TypeError, ValueError):
            continue
        text = str(caption.get("text", ""))
        dur = max(0.0, end - start)
        tracks.append({"t": start, "dur": dur, "text": text, "speech": True})
        cue = classify_semantic_cue(text)
        action = match_semantic_action(rules, cue)
        if not (cue and action):
            continue
        head = cue.split("/")[0].strip()
        motion = _SEMANTIC_MOTION.get(head)
        if motion is None:
            continue
        offset, motion_dur, params = motion
        motion_dur = min(motion_dur, max(dur, 0.2))
        tracks.append(
            {
                "t": round(start + offset, 3),
                "dur": round(motion_dur, 3),
                "param": dict(params),
            }
        )
    return tracks
