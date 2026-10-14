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
