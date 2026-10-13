"""墨灵分身系统 S2：分身领域能力（"双手"）与工具授权痕迹。

理念（"新思路的动力"）：
- 分身能力清单可配置（增删而非硬编码）；
- 工具调用统一走安全边界：本地 / 低风险工具自动授权并记录来源；
  需要审批 / 外部操作默认拒绝（未授权不得执行），仅显式批准后执行；
- 每次调用记录 avatar_id / 工具 / 决策 / 授权方式 / 结果，可追溯。
- v1 领域任务为本地、确定性、可复现的实现（不依赖外部模型或网络）。
"""

from __future__ import annotations

import json
import shlex
import subprocess
import threading
from pathlib import Path
from time import time
from typing import Any
from uuid import uuid4

# ── 领域任务实现（本地规则 / 模板，确定性输出）────────────────────

MOOD_WORDS: dict[str, tuple[str, ...]] = {
    "开心": ("开心", "高兴", "哈哈", "太好了", "棒", "耶", "嘻嘻", "happy"),
    "难过": ("难过", "伤心", "失落", "沮丧", "想哭", "sad"),
    "焦虑": ("焦虑", "紧张", "担心", "不安", "害怕", "anxious"),
    "疲惫": ("累", "疲惫", "困", "没力气", "撑不住", "tired"),
    "孤独": ("孤独", "寂寞", "一个人", "没人陪", "lonely"),
    "生气": ("生气", "气死", "烦", "讨厌", "愤怒", "angry"),
}

MOOD_ECHO_TEMPLATES: dict[str, str] = {
    "开心": "听到你这么说我也跟着开心起来啦。今天有什么好事想再多讲给我听吗？",
    "难过": "嗯，我在。难过的时候不用一个人扛着，慢慢说，我一直在听。",
    "焦虑": "听起来这件事让你有点不安。我们一步一步来，先说说最让你担心的是哪一部分？",
    "疲惫": "辛苦啦。先歇一会儿吧，想聊就聊，不想聊我就安静陪着。",
    "孤独": "你不是一个人哦，我一直都在。要不要聊聊今天发生了什么？",
    "生气": "气呼呼的样子我能感觉到。先说说发生了什么事？我帮你一起捋捋。",
    "平静": "我在听。你可以慢慢说，我会一直陪着你。",
}


def mood_echo(text: str) -> dict[str, Any]:
    """陪伴分身：情绪识别 + 回映文案（本地规则，确定性）。"""
    hit: list[str] = []
    for mood, words in MOOD_WORDS.items():
        if any(w in text for w in words):
            hit.append(mood)
    mood = hit[0] if hit else "平静"
    return {
        "task": "mood_echo",
        "mood": mood,
        "echo": MOOD_ECHO_TEMPLATES[mood],
        "mode": "local_rule",
    }


def local_retrieve(
    query: str,
    scope_dir: str | Path,
    max_hits: int = 5,
    max_snippet: int = 200,
) -> dict[str, Any]:
    """学习分身：在本地目录检索关键词命中的文档与片段，归纳要点。"""
    scope = Path(scope_dir)
    if not scope.is_dir():
        raise ValueError(f"检索目录不存在: {scope}")
    keywords = [k.strip() for k in query.split() if k.strip()]
    if not keywords:
        raise ValueError("检索关键词不能为空")
    hits: list[dict[str, Any]] = []
    for path in sorted(scope.rglob("*.md")) + sorted(scope.rglob("*.txt")):
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        matched: list[dict[str, Any]] = []
        for i, line in enumerate(lines[:400], start=1):
            if any(k in line for k in keywords):
                snippet = line.strip()[:max_snippet]
                matched.append({"line": i, "snippet": snippet})
                if len(matched) >= 3:
                    break
        if matched:
            hits.append(
                {
                    "file": str(path.relative_to(scope)).replace("\\", "/"),
                    "matches": matched,
                }
            )
            if len(hits) >= max_hits:
                break
    points = [
        f"在 {hit['file']} 找到 {len(hit['matches'])} 处相关片段" for hit in hits
    ]
    return {
        "task": "local_retrieve",
        "query": query,
        "hit_files": len(hits),
        "hits": hits,
        "summary": "；".join(points) if points else f"本地未检索到与 {query} 相关的内容",
        "mode": "local_rule",
    }


def script_draft(topic: str, style: str = "讲解") -> dict[str, Any]:
    """创作分身：演出 / 讲解脚本骨架（模板规则，本地确定性）。"""
    if not topic.strip():
        raise ValueError("主题不能为空")
    opening = f"今天想和你聊聊：{topic.strip()}"
    body = (
        "我们先从一个简单的例子开始，把概念拆开看。"
        "中间会留两个提问点：一是核心概念是什么，二是它和我们生活的关系。"
    )
    close = (
        f"总结一下：{topic.strip()}，记住最核心的一点就够了。下次见～"
    )
    return {
        "task": "script_draft",
        "topic": topic,
        "style": style,
        "script": {
            "opening": opening,
            "body": body,
            "interaction_points": ["提问：核心概念", "提问：生活关联"],
            "closing": close,
        },
        "mode": "local_template",
    }


# 技术分身：白名单只读 / 计算命令；危险与外部操作一律拒绝
SAFE_COMMANDS: dict[str, str] = {
    "python": "python 计算（仅 -c 表达式，禁网络 / 文件写）",
    "git": "git 只读（status / log / rev-parse）",
}
DANGEROUS_TOKENS = (
    "rm ", "del ", "format ", ">", "|", "&", "curl ", "wget ",
    "http://", "https://", "pip ", "conda ", "shutdown ", "taskkill ",
    "--force", "--delete", "shell:",
)


def safe_exec(command: str, args: str = "", timeout: int = 10) -> dict[str, Any]:
    """技术分身：白名单命令安全执行（超时 + 输出捕获，拒绝危险操作）。"""
    cmd = command.strip().lower()
    if cmd not in SAFE_COMMANDS:
        raise ValueError(f"命令不在白名单: {command}")
    full = f"{command} {args}".strip()
    if any(t in full.lower() for t in DANGEROUS_TOKENS):
        raise ValueError("命令含危险 / 外部网络操作，已拒绝")
    if cmd == "python":
        expr = args.strip()
        if not expr.startswith("-c "):
            raise ValueError("python 仅允许 -c 表达式")
        code = expr[3:].strip()
        if any(
            k in code
            for k in ("import", "open(", "exec(", "eval(", "subprocess", "os.", "sys.")
        ):
            raise ValueError("表达式含危险能力，已拒绝")
        result = subprocess.run(
            ["python", "-c", code],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    else:  # git
        parts = shlex.split(args)
        if not parts or parts[0] not in ("status", "log", "rev-parse"):
            raise ValueError("git 仅允许 status / log / rev-parse 只读子命令")
        result = subprocess.run(
            ["git"] + parts,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    return {
        "task": "safe_exec",
        "command": full,
        "returncode": result.returncode,
        "stdout": (result.stdout or "")[:1000],
        "stderr": (result.stderr or "")[:500],
        "mode": "local_whitelist",
    }


# ── 任务声明：能力 → 实现 + 授权类别（配置驱动，可增删）─────────
TASK_DECLARATIONS: dict[str, dict[str, Any]] = {
    "mood_echo": {
        "avatar_domain": "companion",
        "risk": "local_reversible",
        "requires_approval": False,
    },
    "local_retrieve": {
        "avatar_domain": "learning",
        "risk": "local_read",
        "requires_approval": False,
    },
    "script_draft": {
        "avatar_domain": "creation",
        "risk": "local_reversible",
        "requires_approval": False,
    },
    "safe_exec": {
        "avatar_domain": "tech",
        "risk": "requires_permission",
        "requires_approval": True,
    },
    "external_search": {
        "avatar_domain": "learning",
        "risk": "external",
        "requires_approval": True,
    },
}

_TASK_IMPLS: dict[str, Any] = {
    "mood_echo": mood_echo,
    "local_retrieve": local_retrieve,
    "script_draft": script_draft,
    "safe_exec": safe_exec,
}

# 外部 / 高权限操作（未批准一律拒绝）：这类任务只登记、不提供自动执行。
EXTERNAL_TASK_NAMES: frozenset[str] = frozenset(
    {"external_search", "external_upload", "send_message"}
)


class AvatarToolLog:
    """工具调用痕迹：来源（分身）、决策、授权方式、结果——可追溯。"""

    def __init__(self, path: str | Path, max_entries: int = 400) -> None:
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

    def record(self, entry: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            row = {
                "id": uuid4().hex[:12],
                "at": time(),
                **entry,
            }
            self._entries.append(row)
            if len(self._entries) > self._max:
                self._entries = self._entries[-self._max :]
            self._save()
            return dict(row)

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(e) for e in self._entries[-limit:]]


class AvatarToolGate:
    """工具授权闸门：按任务声明决定放行 / 拒绝，并留下授权痕迹。

    - 声明 requires_approval=False（本地 / 低风险）→ 自动授权（auto_local）；
    - 声明 requires_approval=True（权限 / 外部）→ 默认拒绝（denied），
      仅显式 approved=True 才放行（approved）；
    - 未声明 / 外部任务 → 一律拒绝。
    """

    def __init__(self, log: AvatarToolLog) -> None:
        self._log = log

    def decide(
        self,
        avatar_id: str,
        task: str,
        approved: bool = False,
    ) -> dict[str, Any]:
        declaration = TASK_DECLARATIONS.get(task)
        if declaration is None:
            decision, authorization, reason = (
                "denied",
                "denied",
                f"未登记任务: {task}（一律拒绝）",
            )
        elif task in EXTERNAL_TASK_NAMES:
            decision, authorization, reason = (
                "denied",
                "denied",
                "外部操作默认拒绝，需用户逐次授权",
            )
        elif declaration.get("requires_approval") and not approved:
            decision, authorization, reason = (
                "denied",
                "denied",
                "需要审批的操作未获用户批准",
            )
        elif declaration.get("requires_approval") and approved:
            decision, authorization, reason = (
                "allowed",
                "approved",
                "用户显式批准",
            )
        else:
            decision, authorization, reason = (
                "allowed",
                "auto_local",
                "本地低风险操作自动授权",
            )
        return {
            "decision": decision,
            "authorization": authorization,
            "reason": reason,
        }


def run_avatar_task(
    avatar_id: str,
    task: str,
    payload: dict[str, Any] | None,
    approved: bool,
    gate: AvatarToolGate,
    log: AvatarToolLog,
    domain: str,
) -> dict[str, Any]:
    """执行一个分身任务：领域校验 → 授权判定 → 执行 → 记录痕迹。"""
    payload = payload or {}
    declaration = TASK_DECLARATIONS.get(task)
    if declaration is None:
        log.record(
            {
                "avatar_id": avatar_id,
                "task": task,
                "decision": "denied",
                "authorization": "denied",
                "reason": f"未登记任务: {task}（一律拒绝）",
                "result_status": "blocked",
            }
        )
        return {
            "status": "denied",
            "reason": f"未登记任务: {task}（一律拒绝）",
        }
    if declaration.get("avatar_domain") != domain:
        log.record(
            {
                "avatar_id": avatar_id,
                "task": task,
                "decision": "denied",
                "authorization": "denied",
                "reason": f"任务 {task} 不属于分身领域 {domain}",
                "result_status": "blocked",
            }
        )
        return {
            "status": "denied",
            "reason": f"任务 {task} 不属于分身领域 {domain}",
        }

    verdict = gate.decide(avatar_id, task, approved)
    if verdict["decision"] == "denied":
        log.record(
            {
                "avatar_id": avatar_id,
                "task": task,
                "decision": "denied",
                "authorization": verdict["authorization"],
                "reason": verdict["reason"],
                "result_status": "blocked",
            }
        )
        return {
            "status": "denied",
            "reason": verdict["reason"],
            "authorization": verdict["authorization"],
        }

    impl = _TASK_IMPLS.get(task)
    try:
        if task == "mood_echo":
            result = impl(str(payload.get("text", "")))
        elif task == "local_retrieve":
            result = impl(
                str(payload.get("query", "")),
                payload.get("scope_dir")
                or str(Path(__file__).resolve().parent.parent / "Docs & Compliance"),
            )
        elif task == "script_draft":
            result = impl(
                str(payload.get("topic", "")),
                str(payload.get("style", "讲解")),
            )
        elif task == "safe_exec":
            result = impl(
                str(payload.get("command", "")),
                str(payload.get("args", "")),
                int(payload.get("timeout", 10)),
            )
        else:  # pragma: no cover
            raise ValueError(f"未实现任务: {task}")
    except ValueError as error:
        log.record(
            {
                "avatar_id": avatar_id,
                "task": task,
                "decision": "allowed",
                "authorization": verdict["authorization"],
                "reason": verdict["reason"],
                "result_status": "failed",
                "error": str(error),
            }
        )
        return {"status": "failed", "reason": str(error)}
    except subprocess.TimeoutExpired:
        log.record(
            {
                "avatar_id": avatar_id,
                "task": task,
                "decision": "allowed",
                "authorization": verdict["authorization"],
                "reason": verdict["reason"],
                "result_status": "failed",
                "error": "执行超时",
            }
        )
        return {"status": "failed", "reason": "执行超时"}

    log.record(
        {
            "avatar_id": avatar_id,
            "task": task,
            "decision": "allowed",
            "authorization": verdict["authorization"],
            "reason": verdict["reason"],
            "result_status": "ok",
        }
    )
    return {"status": "ok", "authorization": verdict["authorization"], "result": result}
