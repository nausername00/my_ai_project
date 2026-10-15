"""墨灵分身系统 S5 前置：性格分化模板。

把四个分身的「语气 / 句式 / 情境措辞」做成可配置模板（persona）：
同一情境下不同分身输出可被规则区分；persona 只作用于表现层，
不触碰记忆、授权与自省策略（延续 S 系列安全边界）。

设计约束：
- 本地确定性：纯静态模板 + 字符串替换，不依赖外部模型 / 网络；
- 可配置：用户可登记 / 覆盖分身性格（配置而非硬编码）；
- 懒落盘：仅实例化不写用户目录，首次 upsert 才保存；
- 兜底：未知分身 / 未知情境回落中性模板，不抛错。
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any


# ── 四分身初始性格 ──────────────────────────────────────────────
DEFAULT_PERSONAS: dict[str, dict[str, Any]] = {
    "companion": {
        "avatar_id": "companion",
        "name": "陪伴小墨",
        "tone": "warm",
        "traits": ["温柔", "松弛", "共情"],
        "style": {
            "max_sentence": 24,
            "jargon": "low",
            "pronoun_bias": "we",
            "verbosity": "verbose",
            "jargon_map": {},
        },
        "openers": ["慢慢来，", "我在呢，", ""],
        "phrases": ["我们一步一步来", "我陪你一起看"],
        "situations": {
            "task_ok": "{result}，我们做到了。",
            "task_denied": "这个先放一放，不着急，等你愿意再说。",
            "task_failed": "没关系，我们换个办法再来。",
            "needs_input": "告诉我你的想法，我陪你一起把它做出来。",
            "wake_offer": "需要的话，我随时都在。",
            "suggestion": "要不要试试这个感觉？",
            "writeback_ok": "已经记好啦，以后用得上的时候我会记得。",
            "greeting": "嗨，我在呢。",
        },
    },
    "learning": {
        "avatar_id": "learning",
        "name": "学习小墨",
        "tone": "patient",
        "traits": ["耐心", "求是", "循证"],
        "style": {
            "max_sentence": 40,
            "jargon": "medium",
            "pronoun_bias": "you",
            "verbosity": "normal",
            "jargon_map": {},
        },
        "openers": ["简单说就是，", "先给你结论：", ""],
        "phrases": ["再深入一点的话……", "依据是这样的："],
        "situations": {
            "task_ok": "结论：{result}。依据如下，可以再展开。",
            "task_denied": "这一步需要你的授权；结果我先留在这里，你确认后我再写入。",
            "task_failed": "这次没有拿到可用结果，原因我会再核对。",
            "needs_input": "请提供具体命令或检索范围，我会按你给的边界执行。",
            "wake_offer": "这部分我可以帮你查证，需要就说一声。",
            "suggestion": "基于近况统计，这里可以优化：{result}。",
            "writeback_ok": "要点已回写，来源与时间已标注，可随时撤销。",
            "greeting": "你好，今天想一起学点什么？",
        },
    },
    "creation": {
        "avatar_id": "creation",
        "name": "创作小墨",
        "tone": "vivid",
        "traits": ["灵动", "画面感", "鼓励"],
        "style": {
            "max_sentence": 32,
            "jargon": "low",
            "pronoun_bias": "you",
            "verbosity": "normal",
            "jargon_map": {},
        },
        "openers": ["试试这个感觉：", "换个角度想，", ""],
        "phrases": ["画面感一下就出来了", "大胆试，不满意我们再改"],
        "situations": {
            "task_ok": "{result}——就是这个感觉，可以继续往下推。",
            "task_denied": "这个点子先留着，等你说好我们再动。",
            "task_failed": "这次没成型，换个角度再试一次。",
            "needs_input": "给我一个方向或关键词，我来起稿。",
            "wake_offer": "想产出点什么的时候，我随时能搭把手。",
            "suggestion": "有个新想法：{result}，要不要试试？",
            "writeback_ok": "灵感已经收进记忆，下次创作可以直接用。",
            "greeting": "嗨，今天想创造点什么？",
        },
    },
    "tech": {
        "avatar_id": "tech",
        "name": "技术小墨",
        "tone": "precise",
        "traits": ["严谨", "简洁", "边界意识"],
        "style": {
            "max_sentence": 30,
            "jargon": "high",
            "pronoun_bias": "none",
            "verbosity": "normal",
            "jargon_map": {"查看": "检索", "报告": "记录"},
        },
        "openers": ["具体来说：", "结论：", ""],
        "phrases": ["注意边界：", "参数需确认："],
        "situations": {
            "task_ok": "{result}（已记录参数与结果）。",
            "task_denied": "未获批准，未执行；如需执行请显式授权。",
            "task_failed": "执行失败，原因见日志；未做破坏性操作。",
            "needs_input": "请提供具体命令；我不会凭空生成。",
            "wake_offer": "技术任务可交给我，需你提供明确命令。",
            "suggestion": "可优化项（基于自省统计）：{result}。",
            "writeback_ok": "结果已回写，source 与时间戳已记录，可撤销。",
            "greeting": "就绪。今天处理什么？",
        },
    },
}

# ── S6 三角思维角色（冰 / 火 / 平衡）────────────────────────────
# 给分身的「思路」配专门角色：打破常规(火) → 严格校验(冰) → 引导与排雷(平衡)。
# 与四分身并存：可登记为独立分身，也可作为协作时注入的思维视角。
DEFAULT_THINKING_PERSONAS: dict[str, dict[str, Any]] = {
    "fire_breakthrough": {
        "avatar_id": "fire_breakthrough",
        "name": "破局·火",
        "tone": "bold",
        "traits": ["打破常规", "发散", "敢想"],
        "behavior": {
            "output_style": "detailed",
            "structured": False,
            "task_affinity": [],
            "thinking_mode": "fire",
        },
        "style": {
            "max_sentence": 48,
            "jargon": "low",
            "pronoun_bias": "you",
            "verbosity": "verbose",
            "jargon_map": {},
        },
        "openers": ["跳出框架想：", "如果反过来呢？", "不妨大胆一点："],
        "phrases": ["先别急着否定，", "这个角度还没试过"],
        "situations": {
            "task_ok": "方案在这：{result}。先跑起来看效果，不行我们再换思路。",
            "task_denied": "这条野路先记着，等你点头我们再闯。",
            "task_failed": "没成，但那说明这条路不对——换个更野的角度再来。",
            "needs_input": "给我一个方向或一句话，我帮你把边界外的地方也想想。",
            "wake_offer": "需要跳出常规的思路时叫我。",
            "suggestion": "有个不按套路的主意：{result}，敢不敢试？",
            "writeback_ok": "点子已存档，以后灵感来了直接用。",
            "greeting": "嗨，今天要破什么局？",
        },
    },
    "ice_guardian": {
        "avatar_id": "ice_guardian",
        "name": "守界·冰",
        "tone": "strict",
        "traits": ["严格逻辑", "结构化", "守边界"],
        "behavior": {
            "output_style": "balanced",
            "structured": True,
            "task_affinity": [],
            "thinking_mode": "ice",
        },
        "style": {
            "max_sentence": 42,
            "jargon": "high",
            "pronoun_bias": "none",
            "verbosity": "normal",
            "jargon_map": {"想法": "假设", "问题": "缺陷"},
        },
        "openers": ["按约束核一遍：", "结论先行：", ""],
        "phrases": ["此处有边界：", "需补验证："],
        "situations": {
            "task_ok": "校验通过：{result}（条件与边界已逐项核对）。",
            "task_denied": "该方案越界或未经授权，未放行；请补授权或改约束。",
            "task_failed": "校验失败：结构与证据不足，结论不可采纳。",
            "needs_input": "请提供任务约束与验收标准，缺项无法校验。",
            "wake_offer": "需要严格审校或排雷时叫我。",
            "suggestion": "风险点（按严重度排序）：{result}。",
            "writeback_ok": "结论已入档，附带校验记录，可回溯。",
            "greeting": "就绪。要核什么？",
        },
    },
    "balance_mediator": {
        "avatar_id": "balance_mediator",
        "name": "调和·衡",
        "tone": "steady",
        "traits": ["引导", "排雷", "权衡"],
        "behavior": {
            "output_style": "balanced",
            "structured": False,
            "task_affinity": [],
            "thinking_mode": "balance",
        },
        "style": {
            "max_sentence": 40,
            "jargon": "medium",
            "pronoun_bias": "we",
            "verbosity": "normal",
            "jargon_map": {},
        },
        "openers": ["两边都听过了：", "先求稳，再谈新：", ""],
        "phrases": ["风险与价值都要看", "先排雷，再前进"],
        "situations": {
            "task_ok": "已调和定案：{result}。创意保住，风险可控。",
            "task_denied": "这一步先按住：创意虽好，边界或风险不允许现在动。",
            "task_failed": "三方未达成可行方案，先回主墨灵，别硬闯。",
            "needs_input": "请给出任务与可接受的风险边界，我来撮合三方。",
            "wake_offer": "需要引导、排雷或仲裁时叫我。",
            "suggestion": "平衡后的建议：{result}。",
            "writeback_ok": "共识已记录，含分歧与裁决依据。",
            "greeting": "我在，两边都听听再说。",
        },
    },
}

# 未知分身 / 未知情境的中性兜底（不抛错）
_NEUTRAL_SITUATIONS: dict[str, str] = {
    "task_ok": "任务完成：{result}",
    "task_denied": "操作未获批准，未执行。",
    "task_failed": "任务失败，详见日志。",
    "needs_input": "请补充必要信息后继续。",
    "wake_offer": "我可以协助处理这部分。",
    "suggestion": "建议：{result}",
    "writeback_ok": "结果已记录。",
    "greeting": "你好，我在。",
}

_REQUIRED_PERSONA_FIELDS = ("avatar_id", "name", "situations")

# E1 行为参数：输出形态偏好（纯表现层，不触碰执行 / 授权逻辑）
_OUTPUT_STYLES = ("brief", "balanced", "detailed")

# S6 思维模式：给分身的「思路」分维度，不替换表现层，也不触碰执行 / 授权。
# fire=打破常规(发散)  ice=严格逻辑与结构化约束(收敛)  balance=引导与排雷(在两者间平衡)
_THINKING_MODES = ("fire", "ice", "balance")


def _neutral_behavior() -> dict[str, Any]:
    """未配置行为参数时的中性默认（任何分身 / 未知分身均回落）。"""
    return {
        "output_style": "balanced",
        "structured": False,
        "task_affinity": [],
        "thinking_mode": "balance",
    }


class PersonaRegistry:
    """性格模板注册表：四分身语气 / 情境措辞，可查询、可登记 / 覆盖。"""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()
        self._personas: dict[str, dict[str, Any]] = {}
        self._load_or_seed()

    def _load_or_seed(self) -> None:
        if self._path.is_file():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                for persona in data.get("personas", []):
                    if isinstance(persona, dict) and persona.get("avatar_id"):
                        self._personas[str(persona["avatar_id"])] = persona
            except (OSError, ValueError, TypeError):
                self._personas = {}
        for template in DEFAULT_PERSONAS.values():
            if template["avatar_id"] not in self._personas:
                self._personas[template["avatar_id"]] = dict(template)
        # 不在此落盘：仅实例化不写用户目录；upsert 时才保存

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(
                {"version": 1, "personas": list(self._personas.values())},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(p) for p in self._personas.values()]

    def get(self, avatar_id: str) -> dict[str, Any] | None:
        with self._lock:
            persona = self._personas.get(avatar_id)
            return dict(persona) if persona else None

    def upsert(self, persona: dict[str, Any]) -> dict[str, Any]:
        """登记 / 覆盖分身性格：必填校验 + 情境模板校验。"""
        if not isinstance(persona, dict):
            raise ValueError("persona 必须是对象")
        missing = [k for k in _REQUIRED_PERSONA_FIELDS if not persona.get(k)]
        if missing:
            raise ValueError(f"persona 缺少必填字段: {', '.join(missing)}")
        avatar_id = str(persona["avatar_id"])
        if not avatar_id.strip():
            raise ValueError("avatar_id 不能为空")
        situations = persona["situations"]
        if not isinstance(situations, dict) or not situations:
            raise ValueError("situations 必须是非空对象")
        for key, template in situations.items():
            if not isinstance(template, str) or not template.strip():
                raise ValueError(f"情境模板非法: {key}")
        behavior = persona.get("behavior") or {}
        output_style = str(behavior.get("output_style", "balanced"))
        if output_style not in _OUTPUT_STYLES:
            raise ValueError(
                f"output_style 必须为 {'/'.join(_OUTPUT_STYLES)} 之一"
            )
        thinking_mode = str(behavior.get("thinking_mode", "balance"))
        if thinking_mode not in _THINKING_MODES:
            raise ValueError(
                f"thinking_mode 必须为 {'/'.join(_THINKING_MODES)} 之一"
            )
        task_affinity = list(behavior.get("task_affinity", []))
        if any(not isinstance(item, str) or not item.strip() for item in task_affinity):
            raise ValueError("task_affinity 必须是非空字符串列表")
        with self._lock:
            normalized = {
                "avatar_id": avatar_id,
                "name": str(persona["name"]),
                "tone": str(persona.get("tone", "neutral")),
                "traits": list(persona.get("traits", [])),
                "style": {
                    "max_sentence": int(persona.get("style", {}).get("max_sentence", 0) or 0),
                    "jargon": str(persona.get("style", {}).get("jargon", "low")),
                    "pronoun_bias": str(persona.get("style", {}).get("pronoun_bias", "none")),
                    "verbosity": str(persona.get("style", {}).get("verbosity", "normal")),
                    "jargon_map": dict(persona.get("style", {}).get("jargon_map", {})),
                },
                "behavior": {
                    "output_style": output_style,
                    "structured": bool(behavior.get("structured", False)),
                    "task_affinity": task_affinity,
                    "thinking_mode": thinking_mode,
                },
                "openers": list(persona.get("openers", [])),
                "phrases": list(persona.get("phrases", [])),
                "situations": dict(situations),
            }
            self._personas[avatar_id] = normalized
            self._save()
            return dict(normalized)

    def behavior_of(self, avatar_id: str) -> dict[str, Any]:
        """读取分身行为参数（E1/S6）：未配置时回落中性默认，不抛错。

        思维角色（破局·火/守界·冰/调和·衡）未登记时回落到静态模板，
        不写入 personas.json。
        """
        persona = self._personas.get(avatar_id)
        if persona is None:
            persona = DEFAULT_THINKING_PERSONAS.get(avatar_id)
        behavior = (persona or {}).get("behavior")
        if not isinstance(behavior, dict):
            return _neutral_behavior()
        return {
            "output_style": behavior.get("output_style", "balanced"),
            "structured": bool(behavior.get("structured", False)),
            "task_affinity": list(behavior.get("task_affinity", [])),
            "thinking_mode": behavior.get("thinking_mode", "balance"),
        }

    def list_thinking_roles(self) -> list[dict[str, Any]]:
        """S6：返回三角思维角色模板（破局·火 / 守界·冰 / 调和·衡），只读定义。"""
        return [dict(template) for template in DEFAULT_THINKING_PERSONAS.values()]

    def speak(
        self,
        avatar_id: str,
        situation: str,
        **variables: Any,
    ) -> str:
        """按分身性格渲染情境消息；未知分身 / 情境回落中性兜底。"""
        persona = self._personas.get(avatar_id)
        if persona is None:
            persona = DEFAULT_THINKING_PERSONAS.get(avatar_id)
        template: str | None = None
        style: dict[str, Any] = {}
        if persona is not None and isinstance(persona.get("situations"), dict):
            template = persona["situations"].get(situation)
            style = persona.get("style") or {}
        if template is None:
            template = _NEUTRAL_SITUATIONS.get(situation, "已处理。")
        text = self._render(template, variables)
        if persona is not None:
            text = self._apply_style(persona, style, text)
            output_style = self.behavior_of(avatar_id)["output_style"]
            text = self._apply_output_style(persona, output_style, text)
        return text

    @staticmethod
    def _apply_output_style(
        persona: dict[str, Any],
        output_style: str,
        text: str,
    ) -> str:
        """E1 行为参数生效（纯表现层）：brief 压缩到首句；detailed 追加惯用语；balanced 不处理。"""
        if output_style == "brief":
            for marker in ("。", "！", "？"):
                idx = text.find(marker)
                if idx >= 8:
                    return text[: idx + 1]
        elif output_style == "detailed":
            phrases = persona.get("phrases") or []
            tail = phrases[1] if len(phrases) > 1 else (phrases[0] if phrases else "")
            if tail and not text.endswith(tail):
                return f"{text} {tail}"
        return text

    @staticmethod
    def _apply_style(persona: dict[str, Any], style: dict[str, Any], text: str) -> str:
        """性格参数真实生效（确定性、可测）：术语密度 → 措辞替换；活跃度 → 追加惯用语；回应长度 → 超长截断。"""
        if style.get("jargon") == "high":
            for word, term in (style.get("jargon_map") or {}).items():
                if word:
                    text = text.replace(word, term)
        if style.get("verbosity") == "verbose":
            phrases = persona.get("phrases") or []
            if phrases and phrases[0]:
                text = f"{text} {phrases[0]}"
        max_len = int(style.get("max_sentence") or 0)
        if max_len > 0 and len(text) > max_len:
            text = text[: max_len - 1].rstrip() + "…"
        return text

    @staticmethod
    def _render(template: str, variables: dict[str, Any]) -> str:
        out = template
        for key, value in variables.items():
            out = out.replace("{" + key + "}", str(value))
        return out
