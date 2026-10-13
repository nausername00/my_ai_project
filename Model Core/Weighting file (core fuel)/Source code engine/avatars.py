"""墨灵分身系统 S1：分身份 / 状态机 / 睡眠唤醒 / 阈值判断 / 唤醒确认。

理念（"新思路的动力"）：主墨灵 + 按需唤醒的专项分身，分领域陪伴与帮助；
睡眠 / 唤醒控制资源（睡眠不占推理）；唤醒确认把主动权留给用户；
记忆主权唯一（长期记忆只由主墨灵统一写入，分身成果经回写接口提交）。
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from time import time
from typing import Any, Literal
from uuid import uuid4

from avatar_tasks import AvatarToolGate, AvatarToolLog, run_avatar_task
from avatar_collab import AvatarOrchestrator

AvatarStatus = Literal["active", "sleeping"]


# ── 预置分身领域定义 ──────────────────────────────────────────────
DEFAULT_AVATARS: list[dict[str, Any]] = [
    {
        "id": "companion",
        "name": "陪伴分身",
        "domain": "companion",
        "description": "聊天、情绪回映、日常提醒与倾听",
        "capabilities": ["dialogue", "mood", "daily_reminder"],
        "status": "sleeping",
    },
    {
        "id": "learning",
        "name": "学习分身",
        "domain": "learning",
        "description": "查资料、整理信息、归纳要点",
        "capabilities": ["search", "summarize", "organize"],
        "status": "sleeping",
    },
    {
        "id": "creation",
        "name": "创作分身",
        "domain": "creation",
        "description": "文案、立绘、Live2D 演出与视频脚本",
        "capabilities": ["writing", "portrait", "live2d_stage", "video_script"],
        "status": "sleeping",
    },
    {
        "id": "tech",
        "name": "技术分身",
        "domain": "tech",
        "description": "代码读写、脚本执行、格式转换",
        "capabilities": ["code", "script_exec", "format_convert"],
        "status": "sleeping",
    },
]


@dataclass
class AvatarProfile:
    """一个分身的身份与运行时状态。"""

    avatar_id: str
    name: str
    domain: str
    description: str = ""
    capabilities: list[str] = field(default_factory=list)
    status: AvatarStatus = "sleeping"
    created_at: float = field(default_factory=time)
    last_active_at: float = 0.0
    breakpoint: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.avatar_id,
            "name": self.name,
            "domain": self.domain,
            "description": self.description,
            "capabilities": list(self.capabilities),
            "status": self.status,
            "created_at": self.created_at,
            "last_active_at": self.last_active_at,
            "breakpoint": dict(self.breakpoint),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AvatarProfile":
        return cls(
            avatar_id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            domain=str(data.get("domain", "")),
            description=str(data.get("description", "")),
            capabilities=[str(c) for c in data.get("capabilities", [])],
            status="active" if data.get("status") == "active" else "sleeping",
            created_at=float(data.get("created_at", 0.0) or time()),
            last_active_at=float(data.get("last_active_at", 0.0) or 0.0),
            breakpoint=dict(data.get("breakpoint", {}) or {}),
        )


class AvatarRegistry:
    """分身注册表：持久化 JSON，管理状态机（睡眠 / 唤醒）。

    睡眠 = 保留身份与断点，不占用推理资源；唤醒 = 恢复活跃（可携带断点）。
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()
        self._avatars: dict[str, AvatarProfile] = {}
        self._load_or_seed()

    def _load_or_seed(self) -> None:
        if self._path.is_file():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                items = data.get("avatars", []) if isinstance(data, dict) else []
                for item in items:
                    profile = AvatarProfile.from_dict(item)
                    if profile.avatar_id:
                        self._avatars[profile.avatar_id] = profile
            except (OSError, ValueError, TypeError):
                self._avatars = {}
        # 预置四个分身（已有同名 id 则保留现有状态，不覆盖）
        for template in DEFAULT_AVATARS:
            if template["id"] not in self._avatars:
                self._avatars[template["id"]] = AvatarProfile(
                    avatar_id=template["id"],
                    name=template["name"],
                    domain=template["domain"],
                    description=template["description"],
                    capabilities=list(template["capabilities"]),
                    status="sleeping",
                )
        # 不在此落盘：仅实例化不应写用户目录；首次 wake / create 等变更时才保存

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "avatars": [p.to_dict() for p in self._avatars.values()],
        }
        self._path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def list(self) -> list[AvatarProfile]:
        with self._lock:
            return sorted(
                self._avatars.values(), key=lambda p: p.avatar_id
            )

    def get(self, avatar_id: str) -> AvatarProfile | None:
        with self._lock:
            return self._avatars.get(avatar_id)

    def create(
        self,
        name: str,
        domain: str,
        description: str = "",
        capabilities: list[str] | None = None,
    ) -> AvatarProfile:
        with self._lock:
            avatar_id = f"{domain}-{uuid4().hex[:8]}"
            profile = AvatarProfile(
                avatar_id=avatar_id,
                name=name,
                domain=domain,
                description=description,
                capabilities=list(capabilities or []),
                status="sleeping",
            )
            self._avatars[avatar_id] = profile
            self._save()
            return profile

    def wake(self, avatar_id: str, breakpoint: dict[str, Any] | None = None) -> AvatarProfile:
        with self._lock:
            profile = self._avatars.get(avatar_id)
            if profile is None:
                raise KeyError(f"分身不存在: {avatar_id}")
            profile.status = "active"
            profile.last_active_at = time()
            if breakpoint:
                profile.breakpoint = dict(breakpoint)
            self._save()
            return profile

    def sleep(self, avatar_id: str, breakpoint: dict[str, Any] | None = None) -> AvatarProfile:
        with self._lock:
            profile = self._avatars.get(avatar_id)
            if profile is None:
                raise KeyError(f"分身不存在: {avatar_id}")
            if breakpoint is not None:
                profile.breakpoint = dict(breakpoint)
            profile.status = "sleeping"
            self._save()
            return profile

    def update_capabilities(
        self, avatar_id: str, capabilities: list[str]
    ) -> AvatarProfile:
        with self._lock:
            profile = self._avatars.get(avatar_id)
            if profile is None:
                raise KeyError(f"分身不存在: {avatar_id}")
            profile.capabilities = [str(c) for c in capabilities]
            self._save()
            return profile

    def active_count(self) -> int:
        with self._lock:
            return sum(1 for p in self._avatars.values() if p.status == "active")


# ── 阈值判断（v1：规则式，可测、可配置）───────────────────────────
_DIRECT_CUES = (
    "你好", "您好", "嗨", "哈喽", "在吗", "谢谢", "感谢", "晚安", "早安",
    "再见", "拜拜", "聊聊", "随便聊聊", "辛苦了", "加油", "hello", "hi",
    "嗯", "哦", "好的", "好", "ok", "yes", "no",
)
_ASK_CUES = (
    "研究", "调研", "方案", "规划", "总结报告", "深度分析", "完整",
    "从头到尾", "多步骤", "系列", "全程", "同时", "还要", "另外",
    "和...一起", "跨", "多领域", "帮忙做", "帮我做一个", "计划",
)
_DOMAIN_CUES: dict[str, tuple[str, ...]] = {
    "learning": ("查", "搜", "资料", "整理", "归纳", "总结", "调研", "研究"),
    "creation": ("文案", "立绘", "海报", "视频", "脚本", "创作", "故事", "演出", "写作", "设计"),
    "tech": ("代码", "脚本", "程序", "bug", "修复", "格式", "转换", "python", "git", "打包", "渲染"),
    "companion": ("难过", "开心", "焦虑", "累", "孤独", "情绪", "心事", "聊聊", "陪伴"),
}


class ThresholdRouter:
    """唤醒确认阈值：简单任务主墨灵直做；复杂 / 跨领域任务才询问用户。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._settings: dict[str, Any] = {
            "enabled": True,
            # 单领域关键词命中即认为主墨灵可直接处理
            "direct_cues": list(_DIRECT_CUES),
            "ask_cues": list(_ASK_CUES),
            "ask_min_length": 80,  # 无关键词时按消息长度兜底
        }

    def get_settings(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._settings)

    def update_settings(self, patch: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            for key in ("enabled", "direct_cues", "ask_cues", "ask_min_length"):
                if key in patch and patch[key] is not None:
                    self._settings[key] = patch[key]
            return dict(self._settings)

    def assess(
        self,
        message: str,
        suggested: list[str] | None = None,
    ) -> dict[str, Any]:
        """返回 {decision: "direct"|"ask", reason, suggested_avatars}。

        - 命中 ask 词或疑似跨领域 → ask（建议唤醒对应分身）
        - 命中 direct 词 → direct（主墨灵直做）
        - 其余：长消息 / 含多领域词 → ask；短消息 → direct
        """
        with self._lock:
            settings = dict(self._settings)
        text = (message or "").strip()
        if not settings.get("enabled", True):
            return {
                "decision": "direct",
                "reason": "阈值判断已停用（用户配置）",
                "suggested_avatars": [],
            }
        if not text:
            return {
                "decision": "direct",
                "reason": "空消息由主墨灵直接处理",
                "suggested_avatars": [],
            }

        ask_cues = settings.get("ask_cues") or []
        direct_cues = settings.get("direct_cues") or []
        ask_min = int(settings.get("ask_min_length", 80))

        hit_ask = [c for c in ask_cues if c in text]
        hit_direct = [c for c in direct_cues if c in text]

        domain_hits = [
            domain
            for domain, cues in _DOMAIN_CUES.items()
            if any(c in text for c in cues)
        ]

        suggested_ids: list[str] = []
        if suggested:
            suggested_ids = [s for s in suggested if s]
        elif domain_hits:
            suggested_ids = domain_hits
        # 创作 + 技术 / 学习 + 创作等组合视为跨领域
        multi_domain = len(set(domain_hits)) >= 2

        if hit_ask or multi_domain:
            return {
                "decision": "ask",
                "reason": "命中复杂/跨领域信号"
                + (f"（关键词: {','.join(hit_ask[:3])}）" if hit_ask else "")
                + (f"（领域: {','.join(sorted(set(domain_hits)))}）" if multi_domain else ""),
                "suggested_avatars": suggested_ids[:3],
            }
        if hit_direct and not domain_hits:
            return {
                "decision": "direct",
                "reason": f"日常信号（{hit_direct[0]}），主墨灵直做",
                "suggested_avatars": [],
            }
        if len(text) >= ask_min:
            return {
                "decision": "ask",
                "reason": f"消息较长（{len(text)} 字），建议确认是否需要更多墨灵帮助",
                "suggested_avatars": suggested_ids[:3],
            }
        return {
            "decision": "direct",
            "reason": "单领域简单任务，主墨灵直做",
            "suggested_avatars": suggested_ids[:1] if domain_hits else [],
        }


class AwakenLog:
    """唤醒确认记录：谁被唤醒、用户是否确认、时间——可追溯。"""

    def __init__(self, path: str | Path, max_entries: int = 200) -> None:
        self._path = Path(path)
        self._max = max_entries
        self._lock = threading.Lock()
        self._entries: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        if self._path.is_file():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                self._entries = list(data.get("entries", []))[-self._max :]
            except (OSError, ValueError, TypeError):
                self._entries = []

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps({"entries": self._entries}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def record(
        self,
        avatar_ids: list[str],
        confirmed: bool,
        reason: str = "",
        requested_by: str = "main",
    ) -> dict[str, Any]:
        with self._lock:
            entry = {
                "id": uuid4().hex[:12],
                "avatar_ids": [str(a) for a in avatar_ids],
                "confirmed": bool(confirmed),
                "reason": str(reason),
                "requested_by": str(requested_by),
                "at": time(),
            }
            self._entries.append(entry)
            if len(self._entries) > self._max:
                self._entries = self._entries[-self._max :]
            self._save()
            return dict(entry)

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(e) for e in self._entries[-limit:]]


class AvatarSystem:
    """分身系统门面：注册表 + 阈值 + 唤醒确认日志 + 工具闸门与痕迹 + 协作与回写。"""

    def __init__(
        self,
        registry_path: str | Path,
        awaken_log_path: str | Path,
        tool_log_path: str | Path | None = None,
        character_store: Any | None = None,
    ) -> None:
        self.registry = AvatarRegistry(registry_path)
        self.router = ThresholdRouter()
        self.awaken_log = AwakenLog(awaken_log_path)
        tool_log = tool_log_path or (Path(awaken_log_path).parent / "tool_log.json")
        self.tool_log = AvatarToolLog(tool_log)
        self.tool_gate = AvatarToolGate(self.tool_log)
        self._character_store = character_store
        self.orchestrator = AvatarOrchestrator(self.run_task)

    def status(self) -> dict[str, Any]:
        avatars = [p.to_dict() for p in self.registry.list()]
        return {
            "avatars": avatars,
            "active_count": self.registry.active_count(),
            "threshold": self.router.get_settings(),
        }

    def assess(self, message: str) -> dict[str, Any]:
        result = self.router.assess(message)
        result["active_avatars"] = [
            p.avatar_id for p in self.registry.list() if p.status == "active"
        ]
        return result

    def confirm_awaken(
        self,
        avatar_ids: list[str],
        confirmed: bool,
        reason: str = "",
    ) -> dict[str, Any]:
        """记录唤醒确认；仅当用户确认时唤醒对应分身（用户主权）。"""
        entry = self.awaken_log.record(
            avatar_ids=avatar_ids,
            confirmed=confirmed,
            reason=reason,
        )
        if entry["confirmed"]:
            for avatar_id in entry["avatar_ids"]:
                try:
                    self.registry.wake(avatar_id)
                except KeyError:
                    continue
        return entry

    def update_capabilities(
        self,
        avatar_id: str,
        mode: str = "set",
        capability: str = "",
        capabilities: list[str] | None = None,
    ) -> AvatarProfile:
        """能力清单可增删（配置而非硬编码）。

        mode=set 直接覆盖；mode=add / remove 单个增删（幂等）。
        """
        profile = self.registry.get(avatar_id)
        if profile is None:
            raise KeyError(f"分身不存在: {avatar_id}")
        if mode == "set":
            return self.registry.update_capabilities(avatar_id, capabilities or [])
        if mode == "add":
            if not capability:
                raise ValueError("add 模式需要 capability")
            current = list(profile.capabilities)
            if capability not in current:
                current.append(capability)
            return self.registry.update_capabilities(avatar_id, current)
        if mode == "remove":
            if not capability:
                raise ValueError("remove 模式需要 capability")
            current = [c for c in profile.capabilities if c != capability]
            return self.registry.update_capabilities(avatar_id, current)
        raise ValueError(f"未知模式: {mode}")

    def run_task(
        self,
        avatar_id: str,
        task: str,
        payload: dict[str, Any] | None = None,
        approved: bool = False,
    ) -> dict[str, Any]:
        """执行分身领域任务：领域校验 + 授权判定 + 执行 + 记录痕迹。

        未授权的高权限 / 外部操作一律拒绝；分身只在自身领域做事。
        """
        profile = self.registry.get(avatar_id)
        if profile is None:
            return {
                "status": "denied",
                "reason": f"分身不存在: {avatar_id}",
            }
        return run_avatar_task(
            avatar_id=avatar_id,
            task=task,
            payload=payload,
            approved=approved,
            gate=self.tool_gate,
            log=self.tool_log,
            domain=profile.domain,
        )

    def tool_log_list(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.tool_log.list(limit=limit)

    def plan_task(self, message: str) -> dict[str, Any]:
        """主墨灵拆解跨领域任务 → 子任务计划（同领域去重）。"""
        return self.orchestrator.plan(message)

    def execute_plan(
        self,
        message: str,
        approved: bool = False,
        writeback: bool = False,
    ) -> dict[str, Any]:
        """执行协作计划：唤醒涉及分身（记录确认）→ 并行执行 → 汇总。

        writeback=True 且 approved=True 时，把协作摘要回写主记忆（带来源）。
        """
        execution = self.orchestrator.execute(
            message,
            approved=approved,
            confirm_wake=self._record_collab_wake,
        )
        if writeback and approved and execution.get("status") == "ok":
            memory = self.writeback(
                avatar_id="main",
                content=f"协作任务完成：{execution.get('summary', '')}",
                approved=True,
                reason="跨领域协作成果回写",
            )
            execution["writeback"] = memory
        return execution

    def _record_collab_wake(
        self, avatar_ids: list[str], confirmed: bool, reason: str
    ) -> dict[str, Any]:
        return self.confirm_awaken(
            avatar_ids=avatar_ids, confirmed=confirmed, reason=reason
        )

    def writeback(
        self,
        avatar_id: str,
        content: str,
        approved: bool = False,
        reason: str = "",
    ) -> dict[str, Any]:
        """成果回写主记忆（主权唯一：统一入口，带来源 avatar:<id>）。

        未批准 → 拒绝（记忆只由主墨灵 / 用户确认后写入）；
        批准 → 写入 J4 记忆系统并返回 memory id（可单独撤销）。
        """
        if self.registry.get(avatar_id) is None and avatar_id != "main":
            return {"status": "denied", "reason": f"分身不存在: {avatar_id}"}
        if not approved:
            return {
                "status": "denied",
                "reason": "成果回写主记忆需用户确认（记忆主权唯一）",
            }
        if self._character_store is None:
            return {"status": "failed", "reason": "主记忆存储不可用"}
        try:
            memory = self._character_store.add_memory(
                content=content,
                source=f"avatar:{avatar_id}",
                visibility="model",
                reason=reason or f"分身成果回写（{avatar_id}）",
            )
        except (TypeError, ValueError) as error:
            return {"status": "failed", "reason": str(error)}
        return {"status": "ok", "memory": memory}
