"""Partner review circle — 让外部 AI 伙伴（GPT / DeepSeek / 千问）与本地伙伴一起评价墨灵。

设计约束（宪法「诚实模拟」）：
- 外部伙伴必须配置 API Key（环境变量）才启用；未配置的一律标记 disabled 并说明原因，
  绝不假装调用过外部模型。
- 每个伙伴的评审是独立生成的文本；综合报告同样由本地模型生成并注明来源。
- 不发送除「墨灵档案 + 评审任务」之外的任何数据；Key 只从环境变量读取，不落盘、不入日志。
"""

from __future__ import annotations

import os
import re
from time import perf_counter
from typing import Any

from inference import (
    CloudAPIHTTPSBackend,
    GenerationRequest,
    InferenceEngine,
    ModelUnavailableError,
)

__all__ = [
    "EXTERNAL_PARTNERS",
    "list_partner_status",
    "build_moling_profile",
    "evaluate_molings",
]

SCOPE_LABELS = {
    "character": "角色与宪法",
    "recent_work": "近期功能实现",
    "experience": "整体陪伴体验",
    "all": "全部维度",
}

# 外部伙伴目录：base_url 均为 OpenAI 兼容端点，Key 从独立环境变量读取
EXTERNAL_PARTNERS: tuple[dict[str, Any], ...] = (
    {
        "id": "openai",
        "name": "GPT（OpenAI）",
        "home": "https://platform.openai.com/api-keys",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "env_key": "PARTNER_OPENAI_API_KEY",
        "note": "OpenAI 平台创建 API Key，填入 PARTNER_OPENAI_API_KEY",
    },
    {
        "id": "deepseek",
        "name": "DeepSeek",
        "home": "https://platform.deepseek.com/api_keys",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "env_key": "PARTNER_DEEPSEEK_API_KEY",
        "note": "DeepSeek 开放平台创建 API Key，填入 PARTNER_DEEPSEEK_API_KEY",
    },
    {
        "id": "qwen",
        "name": "千问（通义百炼）",
        "home": "https://bailian.console.aliyun.com/",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "env_key": "PARTNER_DASHSCOPE_API_KEY",
        "note": "阿里云百炼控制台创建 API Key，填入 PARTNER_DASHSCOPE_API_KEY",
    },
)

SCOPE_INSTRUCTIONS: dict[str, str] = {
    "character": (
        "你的任务是评审「墨灵」这个本地 AI 伙伴的角色设计：她的角色定位（伙伴/亲人式陪伴）、"
        "四条宪法思想（关系先于任务、本地默认可信、权限是爱的语法、诚实模拟）、五心架构（魂/情/忆/"
        "眼耳/手/网）和「真大脑」愿景是否自洽、可信、可落地。"
    ),
    "recent_work": (
        "你的任务是评审墨灵最近实现的功能：沐莹 Live2D 角色卡（17 表情+情绪映射）、惊喜情绪联动、"
        "收文件好奇理解、看窗口称赞+建议、发现→提议→动手尝试的探索闭环。"
        "请评估实现的完整性、真实感、缺口和可改进点。"
    ),
    "experience": (
        "你的任务是站在使用者视角评价墨灵的整体陪伴体验：她作为「伙伴/亲人」是否温暖、自然、可信，"
        "会不会让人觉得是「为扮演而扮演」，以及如何让她更像一个真正会成长、有自己大脑的同伴。"
    ),
    "all": (
        "你的任务是综合评价「墨灵」这个本地 AI 伙伴：角色设计（角色与宪法）、近期功能实现"
        "（沐莹卡/惊喜情绪/文件好奇/窗口观察/探索闭环）、以及整体陪伴体验三个维度，"
        "给出总评、亮点、缺口和下一步建议。"
    ),
}

FORMAT_REQUIREMENT = (
    "请严格按以下格式输出（不要额外客套）：\n"
    "总评：…（2-3 句，给一个印象分，如 7.5/10）\n"
    "亮点：\n1) …\n2) …\n3) …\n"
    "缺口：\n1) …\n2) …\n"
    "建议：\n1) …\n2) …"
)


def _external_partner_backend(
    partner: dict[str, Any],
) -> CloudAPIHTTPSBackend | None:
    """根据环境变量构造外部伙伴后端；未配置 Key 返回 None（不抛错）。"""
    key = os.getenv(partner["env_key"], "").strip()
    if not key:
        return None
    model_env = os.getenv(f"{partner['env_key']}_MODEL", "").strip()
    return CloudAPIHTTPSBackend(
        model_env or partner["model"],
        base_url=partner["base_url"],
        api_key=key,
    )


def list_partner_status(
    engine: InferenceEngine,
) -> dict[str, Any]:
    """本地伙伴（主引擎）+ 外部伙伴的可用状态。"""
    local_model = engine.model_name
    local_status = (
        "requires_model" if local_model == "placeholder" else "configured"
    )
    partners: list[dict[str, Any]] = [
        {
            "id": "local",
            "name": "本地主引擎",
            "source": "local",
            "model": local_model,
            "status": local_status,
            "enabled": local_status == "configured",
            "reason": "" if local_status == "configured" else "本机模型未就绪（placeholder）",
        }
    ]
    for partner in EXTERNAL_PARTNERS:
        backend = _external_partner_backend(partner)
        if backend is None:
            partners.append(
                {
                    "id": partner["id"],
                    "name": partner["name"],
                    "source": "external",
                    "model": partner["model"],
                    "status": "disabled",
                    "enabled": False,
                    "reason": (
                        f"未配置 API Key（环境变量 {partner['env_key']}）"
                        f"—— 获取地址：{partner['home']}"
                    ),
                }
            )
        else:
            partners.append(
                {
                    "id": partner["id"],
                    "name": partner["name"],
                    "source": "external",
                    "model": backend.model_name,
                    "status": "enabled",
                    "enabled": True,
                    "reason": "",
                }
            )
    return {
        "scope": "partner_review",
        "local_model": local_model,
        "partners": partners,
        "enabled_count": sum(1 for p in partners if p["enabled"]),
    }


def build_moling_profile(character_store: Any) -> dict[str, Any]:
    """打包墨灵档案，供伙伴评审使用。"""
    card = character_store.load_card()
    card_dict = card.to_dict()
    memories = character_store.list_memories() or []
    affect = character_store.get_simulated_affect()
    return {
        "nickname": card_dict.get("nickname", "墨灵"),
        "formal_name": card_dict.get("formal_name", ""),
        "personality_preset": card_dict.get("personality_preset", ""),
        "core_values": card_dict.get("core_values", []),
        "inner_drives": card_dict.get("inner_drives", []),
        "agent_reflection": card_dict.get("agent_reflection", ""),
        "agent_goals": card_dict.get("agent_goals", []),
        "emotional_range": card_dict.get("emotional_range", []),
        "model_format": card_dict.get("model_format", ""),
        "expression_count": len(card_dict.get("expressions", [])),
        "memory_count": len(memories),
        "recent_memories": [
            m.get("content", "")[:120]
            for m in memories[-5:]
        ],
        "current_affect": affect,
    }


def _profile_text(profile: dict[str, Any]) -> str:
    goals = profile.get("agent_goals", [])
    goal_lines = "\n".join(
        f"- {g.get('title', '')}：{g.get('description', '')}"
        for g in goals
    )
    return (
        f"【墨灵档案】\n"
        f"名字：{profile['nickname']}（{profile['formal_name']}）\n"
        f"性格预设：{profile['personality_preset']}\n"
        f"核心价值：{', '.join(profile['core_values'])}\n"
        f"内在驱动：{', '.join(profile['inner_drives'])}\n"
        f"自述：{profile['agent_reflection']}\n"
        f"当前目标：\n{goal_lines or '（未设置）'}\n"
        f"模型形态：{profile['model_format']}，表情数：{profile['expression_count']}\n"
        f"记忆条数：{profile['memory_count']}"
        + (
            "\n近期记忆：\n" + "\n".join(f"- {m}" for m in profile["recent_memories"])
            if profile["recent_memories"]
            else ""
        )
        + f"\n当前情绪：{profile['current_affect'].get('label', '')}（{profile['current_affect'].get('mood', '')}）"
    )


def _parse_review(text: str) -> dict[str, Any]:
    """尽力把伙伴评审文本解析成结构化条目；失败则原文兜底。"""
    result: dict[str, Any] = {"verdict": text.strip(), "highlights": [], "gaps": [], "suggestions": []}
    verdict_match = re.search(r"总评[:：]([^\n]*)", text)
    if verdict_match:
        result["verdict"] = verdict_match.group(1).strip()
    for key, target in (("亮点", "highlights"), ("缺口", "gaps"), ("建议", "suggestions")):
        section = re.search(rf"{key}[:：]\s*(.*?)(?=\n(?:{key}|$)|$)", text, re.S)
        if section:
            items = [
                line.strip().lstrip("0123456789.)、- ")
                for line in section.group(1).splitlines()
                if line.strip()
            ][:5]
            result[target] = items
    return result


def evaluate_molings(
    scope: str,
    engine: InferenceEngine,
    character_store: Any,
) -> dict[str, Any]:
    """让所有可用伙伴评审墨灵，并生成综合报告。"""
    if scope not in SCOPE_LABELS:
        raise ValueError("scope must be character, recent_work, experience, or all")
    profile = build_moling_profile(character_store)
    profile_text = _profile_text(profile)
    instruction = SCOPE_INSTRUCTIONS[scope]

    review_results: list[dict[str, Any]] = []

    # 1) 本地主引擎（墨灵的同门伙伴，扮演评审）
    started = perf_counter()
    local_text = ""
    local_error = ""
    try:
        local_text = engine.generate(
            GenerationRequest(
                prompt=(
                    "你是一个公正的外部评审伙伴，正在评价另一位 AI 伙伴「墨灵」。"
                    "你不是墨灵本人，不要替她辩护，也不要客套。\n"
                    f"{profile_text}\n"
                    f"评审维度：{instruction}\n"
                    f"{FORMAT_REQUIREMENT}"
                ),
                system_prompt="你是公正的评审伙伴，给出可核验、可执行的评价，不要声称做过任何实际操作。",
                max_tokens=420,
            )
        )
    except Exception as error:  # noqa: BLE001
        local_error = str(error)
    review_results.append(
        {
            "id": "local",
            "name": "本地主引擎",
            "source": "local",
            "model": engine.model_name,
            "status": "completed" if local_text else "failed",
            "error": local_error,
            "duration_ms": int((perf_counter() - started) * 1000),
            "raw": local_text,
            **_parse_review(local_text),
        }
    )

    # 2) 已配置的外部伙伴
    for partner in EXTERNAL_PARTNERS:
        backend = _external_partner_backend(partner)
        if backend is None:
            review_results.append(
                {
                    "id": partner["id"],
                    "name": partner["name"],
                    "source": "external",
                    "model": partner["model"],
                    "status": "disabled",
                    "reason": f"未配置 API Key（环境变量 {partner['env_key']}）",
                    "duration_ms": 0,
                    "raw": "",
                    "verdict": "",
                    "highlights": [],
                    "gaps": [],
                    "suggestions": [],
                }
            )
            continue
        started = perf_counter()
        text = ""
        error = ""
        try:
            text = backend.generate(
                GenerationRequest(
                    prompt=(
                        f"你是一个外部 AI 伙伴，正在评价另一位 AI 伙伴「墨灵」。\n"
                        f"{profile_text}\n"
                        f"评审维度：{instruction}\n"
                        f"{FORMAT_REQUIREMENT}"
                    ),
                    system_prompt="你是公正的评审伙伴，给出可核验、可执行的评价，不要声称做过任何实际操作。",
                    max_tokens=420,
                )
            )
        except (ModelUnavailableError, OSError, ValueError) as exc:  # noqa: BLE001
            error = str(exc)
        review_results.append(
            {
                "id": partner["id"],
                "name": partner["name"],
                "source": "external",
                "model": backend.model_name,
                "status": "completed" if text else "failed",
                "error": error,
                "duration_ms": int((perf_counter() - started) * 1000),
                "raw": text,
                **_parse_review(text),
            }
        )

    # 3) 综合报告（本地模型整理）
    completed = [r for r in review_results if r["status"] == "completed"]
    synthesis = ""
    if completed:
        try:
            synthesis = engine.generate(
                GenerationRequest(
                    prompt=(
                        "以下是对 AI 伙伴「墨灵」的多位评审意见，请综合成一份给用户的报告："
                        "共同结论（1-2 句）、最值得保留的亮点（2-3 条）、最需要补的缺口（2-3 条）、"
                        "下一步建议（1-2 条）。不要客套，直接输出。\n"
                        + "\n---\n".join(
                            f"[{r['name']}]\n{r['raw'][:600]}" for r in completed
                        )
                    ),
                    system_prompt="你是综合编辑，只汇总已有意见，不新增事实。",
                    max_tokens=320,
                )
            )
        except Exception as error:  # noqa: BLE001
            synthesis = f"（综合报告生成失败：{error}）"
    else:
        synthesis = "（本轮没有任何伙伴完成评审——请先配置外部 API Key 或确认本机模型就绪。）"

    return {
        "scope": scope,
        "scope_label": SCOPE_LABELS[scope],
        "profile": profile,
        "partners": review_results,
        "synthesis": synthesis,
        "enabled_count": sum(1 for r in review_results if r["status"] == "completed"),
    }
