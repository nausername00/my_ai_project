"""墨灵分身系统 S3：跨领域协作与主记忆回写（"统一目标"）。

理念（"新思路的动力"）：
- 主墨灵拆解任务 → 唤醒对应分身 → 并行执行独立子任务 → 汇总结果给用户；
- 同领域不重复唤醒（去重）；需要审批 / 外部操作仍走 S2 授权闸门；
- 成果回写主记忆：统一入口（AvatarSystem.writeback），带来源 avatar:<id>
  与时间戳，可追溯、可单独撤销（J4 记忆系统）；分身不能直接写主记忆，
  记忆主权唯一（只有主墨灵 / 用户确认后写入）。
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from avatar_tasks import TASK_DECLARATIONS, EXTERNAL_TASK_NAMES

# 领域 → 默认子任务（v1 本地可复现；外部 / 需审批任务仍由闸门拦截）
_DOMAIN_TASKS: dict[str, dict[str, Any]] = {
    "learning": {"task": "local_retrieve", "needs_input": False},
    "creation": {"task": "script_draft", "needs_input": False},
    "companion": {"task": "mood_echo", "needs_input": False},
    # 技术子任务需要具体命令，不凭空生成（v1 标注 needs_input）
    "tech": {"task": "safe_exec", "needs_input": True},
}

_DOMAIN_CUES: dict[str, tuple[str, ...]] = {
    "learning": ("查", "搜", "资料", "整理", "归纳", "总结", "调研", "研究"),
    "creation": ("文案", "立绘", "海报", "视频", "脚本", "创作", "故事", "演出", "写作", "设计"),
    "tech": ("代码", "脚本", "程序", "bug", "修复", "格式", "转换", "python", "git", "打包", "渲染"),
    "companion": ("难过", "开心", "焦虑", "累", "孤独", "情绪", "心事", "聊聊", "陪伴"),
}


class AvatarOrchestrator:
    """跨领域任务编排：拆解 → 去重 → 并行执行 → 汇总。"""

    def __init__(self, run_task: Callable[..., dict[str, Any]]) -> None:
        """run_task: (avatar_id, task, payload, approved) -> result dict。"""
        self._run_task = run_task

    def plan(self, message: str) -> dict[str, Any]:
        """把消息拆成子任务计划（同领域去重，不重复唤醒）。"""
        text = (message or "").strip()
        if not text:
            return {"plan_id": None, "tasks": [], "reason": "空消息无需协作"}
        hit_domains: list[str] = []
        for domain, cues in _DOMAIN_CUES.items():
            if any(c in text for c in cues) and domain not in hit_domains:
                hit_domains.append(domain)
        tasks: list[dict[str, Any]] = []
        for domain in hit_domains:
            spec = _DOMAIN_TASKS[domain]
            payload: dict[str, Any]
            if domain == "learning":
                payload = {"query": text}
            elif domain == "creation":
                payload = {"topic": text, "style": "讲解"}
            elif domain == "companion":
                payload = {"text": text}
            else:  # tech
                payload = {}
            tasks.append(
                {
                    "domain": domain,
                    "avatar_id": domain,
                    "task": spec["task"],
                    "payload": payload,
                    "needs_input": spec["needs_input"],
                }
            )
        return {
            "plan_id": _plan_id(text),
            "domains": hit_domains,
            "tasks": tasks,
            "note": "同领域已去重；技术子任务需用户提供具体命令",
        }

    def execute(
        self,
        message: str,
        approved: bool = False,
        confirm_wake: Callable[[list[str], bool, str], Any] | None = None,
    ) -> dict[str, Any]:
        """执行一个协作计划：唤醒涉及分身 → 并行执行 → 汇总。

        confirm_wake 缺省时不额外记录唤醒（由调用方按需传入）。
        """
        plan = self.plan(message)
        tasks = plan.get("tasks", [])
        if not tasks:
            return {"status": "noop", "reason": plan.get("reason", "无需协作")}

        avatar_ids = sorted({t["avatar_id"] for t in tasks if t["avatar_id"]})
        if confirm_wake is not None:
            confirm_wake(avatar_ids, True, f"协作任务: {message[:40]}")

        results: list[dict[str, Any]] = []

        def _run_one(task: dict[str, Any]) -> dict[str, Any]:
            if task.get("needs_input"):
                return {
                    "domain": task["domain"],
                    "status": "pending",
                    "reason": "需要用户提供具体命令",
                }
            result = self._run_task(
                task["avatar_id"],
                task["task"],
                task["payload"],
                approved=approved,
            )
            if result.get("status") == "ok":
                summary = _summarize(task["domain"], result.get("result", {}))
                return {
                    "domain": task["domain"],
                    "status": "ok",
                    "summary": summary,
                }
            return {
                "domain": task["domain"],
                "status": result.get("status", "failed"),
                "reason": result.get("reason", ""),
            }

        with ThreadPoolExecutor(max_workers=min(len(tasks), 3)) as pool:
            results = list(pool.map(_run_one, tasks))

        ok_domains = [r["domain"] for r in results if r.get("status") == "ok"]
        summary = "；".join(
            r.get("summary", r.get("reason", r.get("status", "")))
            for r in results
        )
        return {
            "status": "ok" if ok_domains else "noop",
            "domains": plan.get("domains", []),
            "tasks": results,
            "summary": summary or "协作未产出可汇总结果",
            "active_avatars": avatar_ids,
        }


def _plan_id(text: str) -> str:
    import hashlib

    return "plan-" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]


def _summarize(domain: str, result: dict[str, Any]) -> str:
    if domain == "learning":
        return f"本地检索到 {result.get('hit_files', 0)} 份相关文档"
    if domain == "creation":
        script = result.get("script", {})
        opening = script.get("opening", "")
        return f"脚本已生成：{opening[:30]}"
    if domain == "companion":
        return f"回映情绪：{result.get('mood', '平静')}"
    return "已执行"  # tech
