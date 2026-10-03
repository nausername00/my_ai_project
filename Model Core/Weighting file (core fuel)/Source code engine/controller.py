"""L4 六路执行控制器（code / UI / create / game / system / dialogue）。

The controller takes a routed decision (``agent.RoutedDecision``) + a
planned ReAct result (``planner.ReActPlanResult``) + any user approvals,
then dispatches each step to the right execution module while double-
checking permission gates.  Nothing in this module touches third-party
packages directly – it imports the sibling :mod:`computer_use`,
:mod:`browser`, :mod:`visualize`, :mod:`agent_tools`, :mod:`speech`
modules lazily so importing :mod:`controller` itself is always cheap.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import time
from typing import Any, Callable, Iterable, Mapping

from utils import (
    ModuleUnavailableError,
    PermissionDenied,
    SingletonLock,
    truncate_text,
    utc_now_iso,
)

__all__ = [
    "CHANNELS",
    "Channel",
    "ControllerError",
    "ExecutionController",
    "ExecutionResult",
    "StepResult",
    "classify_channel",
]


class Channel(str):
    CODE = "code"
    UI = "ui"
    CREATE = "create"
    GAME = "game"
    SYSTEM = "system"
    DIALOGUE = "dialogue"


CHANNELS: frozenset[str] = frozenset({Channel.CODE, Channel.UI, Channel.CREATE, Channel.GAME, Channel.SYSTEM, Channel.DIALOGUE})


class ControllerError(RuntimeError):
    pass


@dataclass(frozen=True)
class StepResult:
    step_index: int
    channel: str
    action: str
    success: bool
    payload: dict = field(default_factory=dict)
    error: str | None = None
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_index": int(self.step_index),
            "channel": self.channel,
            "action": self.action,
            "success": bool(self.success),
            "payload": dict(self.payload),
            "error": self.error,
            "duration_ms": int(self.duration_ms),
        }


@dataclass(frozen=True)
class ExecutionResult:
    final_answer: str
    mode: str
    channel: str
    steps: tuple
    summary: dict = field(default_factory=dict)
    needs_user_decision: bool = False
    decision_request: dict | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "final_answer": self.final_answer,
            "mode": self.mode,
            "channel": self.channel,
            "steps": [s.to_dict() for s in self.steps],
            "summary": dict(self.summary),
            "needs_user_decision": bool(self.needs_user_decision),
            "decision_request": self.decision_request,
        }


# ---------------------------------------------------------------------------
# Channel classifier
# ---------------------------------------------------------------------------

_SCENE_TO_CHANNEL: dict[str, str] = {
    "code": Channel.CODE,
    "learn": Channel.DIALOGUE,
    "create": Channel.CREATE,
    "game": Channel.GAME,
    "system": Channel.SYSTEM,
    "companion": Channel.DIALOGUE,
    "chat": Channel.DIALOGUE,
}


def classify_channel(
    scene: str,
    intent: str | None = None,
    *,
    tool_name: str | None = None,
) -> str:
    """Map scene + intent + tool to one of the six channels."""
    if tool_name:
        t = str(tool_name)
        if t in {"write_project_file", "patch_project_file", "run_tests", "run_sandboxed_shell",
                 "list_project_files", "read_project_file"}:
            return Channel.CODE
        if t in {"browser_goto", "browser_click", "browser_fill", "browser_screenshot", "browser_text"}:
            return Channel.UI
        if t in {"render_cover", "render_avatar", "render_chart", "creator_create"}:
            return Channel.CREATE
        if t in {"game_hint", "game_save"}:
            return Channel.GAME
        if t in {"mouse_move", "click", "keyboard_type", "keystrokes", "hotkey",
                 "clipboard_read", "clipboard_write", "open_path", "ps"}:
            return Channel.SYSTEM
    scene_channel = _SCENE_TO_CHANNEL.get((scene or "chat").lower(), Channel.DIALOGUE)
    if intent == "create":
        scene_channel = Channel.CREATE
    return scene_channel


# ---------------------------------------------------------------------------
# ExecutionController
# ---------------------------------------------------------------------------

class ExecutionController:
    """Routes tool / answer / ask_user steps to the six channels.

    Parameters
    ----------
    workspace_root:
        Project root for :mod:`agent_tools` operations.
    approved_permissions:
        Mapping of permission scope → bool.  Recognised scopes are
        ``screen``, ``microphone``, ``clipboard``, ``desktop_automation``,
        ``browser``, ``shell``, ``write_file``, ``remote_social``.
    approved_tools:
        Iterable of tool names already OK'd for this session.
    allowed_browser_hosts:
        Hostname allow-list passed through to :mod:`browser`.
    """

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        approved_permissions: Mapping[str, bool] | None = None,
        approved_tools: Iterable[str] = (),
        allowed_browser_hosts: Iterable[str] = (),
    ) -> None:
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        if not self.workspace_root.exists():
            raise ControllerError(f"workspace_root does not exist: {self.workspace_root.as_posix()}")
        self.approved_permissions: dict[str, bool] = {k: bool(v) for k, v in (approved_permissions or {}).items()}
        self.approved_tools: set[str] = set(approved_tools or ())
        self.allowed_browser_hosts = tuple(allowed_browser_hosts or ())
        self._lock = SingletonLock()

    # ------------------------------------------------------------------
    # Permission helpers
    # ------------------------------------------------------------------
    def has_permission(self, scope: str) -> bool:
        return bool(self.approved_permissions.get(scope, False))

    def grant_permission(self, scope: str, value: bool = True) -> None:
        with self._lock:
            self.approved_permissions[scope] = bool(value)

    def grant_tool(self, tool: str, value: bool = True) -> None:
        with self._lock:
            if value:
                self.approved_tools.add(tool)
            else:
                self.approved_tools.discard(tool)

    def _ok_tool(self, tool_name: str, tool_approved_flag: bool | None) -> bool:
        if tool_approved_flag is True:
            return True
        if tool_name in self.approved_tools:
            return True
        # naturally safe read-only tools (already restricted to workspace)
        return tool_name in {"list_project_files", "read_project_file", "ping", "status", "list_tools"}

    # ------------------------------------------------------------------
    # High-level execute()
    # ------------------------------------------------------------------
    def execute(
        self,
        *,
        plan_result: Any,
        routed_decision: Any,
        mode_router_decision: Any,
        user_approved_flags: Mapping[str, bool] | None = None,
        on_step: Callable[[StepResult], None] | None = None,
    ) -> ExecutionResult:
        """Execute a planned ReAct result according to the mode router.

        ``plan_result`` and ``routed_decision`` can be the dataclass
        instances *or* dict-shaped payloads – this is how the HTTP layer
        (``api.py``) reuses this controller without round-tripping back
        through Python imports.
        """
        # Step 1: normalise inputs to plain dicts we can rely on.
        mode_decision = _to_dict(mode_router_decision)
        mode = str(mode_decision.get("mode") or "propose")
        route = _to_dict(routed_decision)
        scene = str(route.get("scene") or "chat")
        intent = str(_to_dict(plan_result).get("intent") or "answer")
        plan_steps = list(_to_dict(plan_result).get("steps") or [])
        user_flags = {k: bool(v) for k, v in (user_approved_flags or {}).items()}
        channel = classify_channel(scene, intent=intent)

        # If mode is ASK_PERMISSION or PROPOSE → return a no-op result
        # with a human-facing permission payload.
        if mode in {"ask_permission", "propose"}:
            req = self._build_permission_request(
                plan_steps=plan_steps,
                mode=mode,
                route=route,
                mode_decision=mode_decision,
            )
            return ExecutionResult(
                final_answer=self._proposal_text(plan_steps, route, mode_decision, mode),
                mode=mode,
                channel=channel,
                steps=(),
                summary={"proposal_steps": [_step_summary(s) for s in plan_steps[:8]]},
                needs_user_decision=True,
                decision_request=req,
            )

        if mode == "idle":
            return ExecutionResult(
                final_answer="无事可做（idle）。",
                mode="idle",
                channel=channel,
                steps=(),
                summary={},
            )

        # ACT mode: execute every step in order.
        results: list[StepResult] = []
        for idx, step in enumerate(plan_steps[:12]):
            step_dict = _to_dict(step)
            ch = classify_channel(scene, intent=intent, tool_name=step_dict.get("tool"))
            t0 = time.monotonic()
            try:
                payload = self._run_step(step_dict, ch, user_flags=user_flags)
                ok = True
                err = None
            except PermissionDenied as exc:
                payload = {}
                ok = False
                err = f"[PermissionDenied] {exc}"
            except ModuleUnavailableError as exc:
                payload = {}
                ok = False
                err = f"[ModuleUnavailableError] {exc}"
            except Exception as exc:
                payload = {}
                ok = False
                err = f"[{type(exc).__name__}] {exc}"
            sr = StepResult(
                step_index=int(step_dict.get("index") or idx),
                channel=ch,
                action=str(step_dict.get("action_type") or step_dict.get("tool") or "step"),
                success=ok,
                payload=payload or {},
                error=err,
                duration_ms=int(round((time.monotonic() - t0) * 1000)),
            )
            results.append(sr)
            if on_step is not None:
                try:
                    on_step(sr)
                except Exception:
                    pass
            # Stop on first failure that requires human input.
            if not ok and ("PermissionDenied" in (err or "") or "ModuleUnavailableError" in (err or "")):
                req = {
                    "reason": err,
                    "retryable": True,
                    "failed_step": sr.to_dict(),
                }
                return ExecutionResult(
                    final_answer=self._fail_text(results),
                    mode="act",
                    channel=ch,
                    steps=tuple(results),
                    summary={},
                    needs_user_decision=True,
                    decision_request=req,
                )

        final = self._answer_from_results(results, route)
        return ExecutionResult(
            final_answer=final,
            mode="act",
            channel=channel,
            steps=tuple(results),
            summary={
                "success_steps": sum(1 for r in results if r.success),
                "failed_steps": sum(1 for r in results if not r.success),
            },
        )

    # ------------------------------------------------------------------
    # Step dispatch
    # ------------------------------------------------------------------
    def _run_step(self, step: dict, channel: str, *, user_flags: Mapping[str, bool]) -> dict:
        action_type = str(step.get("action_type") or "tool").lower()
        tool_name = step.get("tool_name") if step.get("tool_name") else step.get("tool")
        tool_args = step.get("tool_args") or {}
        step_approved = bool(step.get("requires_approval") is False or self._ok_tool(str(tool_name or ""), None))
        if action_type == "answer":
            return {"text": truncate_text(str(step.get("observation") or step.get("thought") or ""), 8000, "")}
        if action_type in {"ask_user", "blocked", "abort"}:
            return {"note": action_type, "reflection": step.get("reflection") or "", "tool": tool_name}
        if action_type != "tool":
            raise ControllerError(f"未知 action_type: {action_type}")
        if not tool_name:
            raise ControllerError("tool step missing tool_name")
        tool = str(tool_name)
        # Code channel
        if tool in {"list_project_files", "read_project_file", "write_project_file", "patch_project_file",
                    "run_tests", "run_sandboxed_shell"}:
            return self._dispatch_code(tool, tool_args, step_approved=step_approved, user_flags=user_flags)
        # UI channel (browser)
        if tool.startswith("browser_"):
            return self._dispatch_browser(tool, tool_args, step_approved=step_approved)
        # Create channel (visualize)
        if tool in {"render_cover", "render_avatar", "render_chart", "creator_create"}:
            return self._dispatch_create(tool, tool_args, step_approved=step_approved)
        # System channel (computer_use)
        if tool in {"mouse_move", "click", "keyboard_type", "keystrokes", "hotkey",
                    "clipboard_read", "clipboard_write", "open_path", "ps", "shell"}:
            return self._dispatch_system(tool, tool_args, step_approved=step_approved)
        # Dialogue channel (character memory)
        if tool in {"read_memory", "list_memories", "add_memory", "search_memory"}:
            return self._dispatch_dialogue(tool, tool_args, step_approved=step_approved)
        # Game channel: pure placeholder for now.
        if tool in {"game_hint", "game_save"}:
            return {"channel": Channel.GAME, "tool": tool, "note": "game channel placeholder (本地占位)"}
        raise ControllerError(f"未注册工具: {tool}")

    # ------------------------------------------------------------------
    # Channel-specific dispatchers
    # ------------------------------------------------------------------
    def _dispatch_code(self, tool: str, args: Mapping[str, Any], *, step_approved: bool, user_flags: Mapping[str, bool]) -> dict:
        import agent_tools as _at
        tool_args = dict(args)
        if tool == "list_project_files":
            return _at.execute_project_tool(self.workspace_root, "list_project_files", {"path": tool_args.get("path", ".")})
        if tool == "read_project_file":
            return _at.execute_project_tool(self.workspace_root, "read_project_file", {"path": tool_args["path"]})
        if tool in {"write_project_file", "patch_project_file"}:
            if not self.has_permission("write_file") or not step_approved:
                raise PermissionDenied(f"工具 '{tool}' 需要 write_file 权限并显式批准。")
            return _at.execute_project_tool(self.workspace_root, tool, tool_args)
        if tool == "run_tests":
            if not self.has_permission("shell") or not step_approved:
                raise PermissionDenied("run_tests 需要 shell 权限。")
            cmd = tool_args.get("command", ["py", "-3", "-m", "pytest", "-q"])
            import computer_use as _cu
            return _cu.run_sandboxed_shell(
                cmd,
                approved=True,
                purpose="controller: run_tests",
                cwd=str(self.workspace_root),
                timeout_seconds=int(tool_args.get("timeout_seconds", 180)),
            ).to_dict()
        if tool == "run_sandboxed_shell":
            if not self.has_permission("shell") or not step_approved:
                raise PermissionDenied("run_sandboxed_shell 需要 shell 权限。")
            import computer_use as _cu
            return _cu.run_sandboxed_shell(
                tool_args.get("command"),
                approved=True,
                purpose="controller: sandboxed_shell",
                cwd=str(tool_args.get("cwd") or self.workspace_root),
                timeout_seconds=int(tool_args.get("timeout_seconds", 60)),
                safe_commands=tool_args.get("safe_commands") or _cu._SAFE_COMMANDS,
            ).to_dict()
        raise ControllerError(f"code channel 未知工具: {tool}")

    def _dispatch_browser(self, tool: str, args: Mapping[str, Any], *, step_approved: bool) -> dict:
        if not self.has_permission("browser") or not step_approved:
            raise PermissionDenied("browser 工具需要 browser 权限并显式批准。")
        import browser as _br
        a = dict(args)
        hosts = tuple(a.get("allowed_hosts") or self.allowed_browser_hosts)
        if not hosts:
            raise PermissionDenied("浏览器域名白名单为空，请先设置 allowed_browser_hosts 并授权 approved。")
        approved = True
        purpose = a.get("purpose") or "controller: browser step"
        if tool == "browser_goto":
            return _br.browser_goto(a["url"], approved=approved, purpose=purpose, allowed_hosts=hosts,
                                    headless=bool(a.get("headless", True)))
        if tool == "browser_screenshot":
            return _br.browser_screenshot(
                a["url"], approved=approved, purpose=purpose, allowed_hosts=hosts,
                headless=bool(a.get("headless", True)),
                save_path=a.get("save_path"), full_page=bool(a.get("full_page", True)),
            ).to_dict()
        if tool == "browser_click":
            return _br.browser_click(a["url"], a["selector"], approved=approved, purpose=purpose,
                                     allowed_hosts=hosts, headless=bool(a.get("headless", True))).to_dict()
        if tool == "browser_fill":
            return _br.browser_fill(
                a["url"], a["selector"], a.get("value", ""),
                approved=approved, purpose=purpose, allowed_hosts=hosts,
                headless=bool(a.get("headless", True)), submit=bool(a.get("submit", False)),
            )
        if tool == "browser_text":
            return _br.browser_text_content(
                a["url"], a.get("selector", "body"), approved=approved, purpose=purpose,
                allowed_hosts=hosts, headless=bool(a.get("headless", True)),
                limit_chars=int(a.get("limit_chars", 12000)),
            )
        raise ControllerError(f"browser 未知工具: {tool}")

    def _dispatch_create(self, tool: str, args: Mapping[str, Any], *, step_approved: bool) -> dict:
        import visualize as _vz
        a = dict(args)
        if tool == "creator_create":
            payload = _vz.Creator(**{k: a[k] for k in {"width", "height", "default_palette"} if k in a}).create(
                a.get("prompt") or "",
                kind=a.get("kind", "cover"),
                **{k: a[k] for k in {"subtitle", "name", "size", "values", "palette"} if k in a},
            )
        elif tool == "render_cover":
            payload = _vz.render_cover_svg(a.get("title") or a.get("prompt") or "",
                                           subtitle=a.get("subtitle", ""),
                                           **{k: a[k] for k in {"width", "height", "palette"} if k in a})
        elif tool == "render_avatar":
            payload = _vz.render_avatar_svg(a.get("name") or a.get("prompt") or "?",
                                            palette=a.get("palette"), size=a.get("size", 512))
        elif tool == "render_chart":
            payload = _vz.SVGRenderer(**{k:a[k] for k in {"width","height","palette"} if k in a}).chart(
                a.get("title") or a.get("prompt") or "chart",
                list(a.get("values") or []),
                palette=a.get("palette"),
            )
        else:
            raise ControllerError(f"create 未知工具: {tool}")
        out = payload.to_dict()
        if a.get("save_dir"):
            if not step_approved:
                raise PermissionDenied("保存创作产物需要显式 approved。")
            r = _vz.SVGRenderer() if payload.kind == "svg" else _vz.PillowRenderer()
            saved = r.save(payload, a["save_dir"], approved=True, purpose=a.get("purpose") or "controller create save")
            out["saved_path"] = saved.path
        return out

    def _dispatch_system(self, tool: str, args: Mapping[str, Any], *, step_approved: bool) -> dict:
        import computer_use as _cu
        a = dict(args)
        scope_map = {
            "mouse_move": "desktop_automation",
            "click": "desktop_automation",
            "keystrokes": "desktop_automation",
            "keyboard_type": "desktop_automation",
            "hotkey": "desktop_automation",
            "clipboard_read": "clipboard",
            "clipboard_write": "clipboard",
            "open_path": "desktop_automation",
            "ps": "desktop_automation",
            "shell": "shell",
        }
        scope = scope_map[tool]
        if not self.has_permission(scope) or not step_approved:
            raise PermissionDenied(f"system 工具 '{tool}' 需要 scope={scope} 权限并显式 approved。")
        if tool == "mouse_move":
            return _cu.automate_mouse_move(approved=True, purpose=a.get("purpose"), x=a["x"], y=a["y"],
                                           duration_seconds=a.get("duration_seconds", 0.2))
        if tool == "click":
            return _cu.automate_click(approved=True, purpose=a.get("purpose"),
                                      x=a.get("x"), y=a.get("y"),
                                      button=a.get("button","left"),
                                      clicks=a.get("clicks",1),
                                      interval_seconds=a.get("interval_seconds",0.05))
        if tool == "keyboard_type":
            return _cu.automate_type(approved=True, purpose=a.get("purpose"),
                                     text=a["text"], interval_seconds=a.get("interval_seconds",0.0))
        if tool == "keystrokes":
            return _cu.automate_keystrokes(approved=True, purpose=a.get("purpose"), keys=a["keys"])
        if tool == "hotkey":
            return _cu.automate_hotkey(approved=True, purpose=a.get("purpose"), keys=a["keys"])
        if tool == "clipboard_read":
            return _cu.clipboard_read(approved=True, purpose=a.get("purpose")).to_dict()
        if tool == "clipboard_write":
            return _cu.clipboard_write(a["value"], approved=True, purpose=a.get("purpose")).to_dict()
        if tool == "open_path":
            return _cu.open_in_explorer(a["path"], approved=True, purpose=a.get("purpose"),
                                        workspace_root=a.get("workspace_root", self.workspace_root))
        if tool == "ps":
            return {"processes": _cu.list_processes(approved=True, purpose=a.get("purpose"), limit=a.get("limit", 50))}
        if tool == "shell":
            return _cu.run_sandboxed_shell(
                a["command"], approved=True, purpose=a.get("purpose") or "controller shell",
                cwd=a.get("cwd"), timeout_seconds=a.get("timeout_seconds", 60),
            ).to_dict()
        raise ControllerError(f"system 未知工具: {tool}")

    def _dispatch_dialogue(self, tool: str, args: Mapping[str, Any], *, step_approved: bool) -> dict:
        a = dict(args)
        # Dialogue/memory tools need at least one of: approved step OR user
        # having granted read_memory in earlier grants.
        import character as _ch
        store = getattr(_ch.CharacterStore.instance if hasattr(_ch.CharacterStore, "instance") else _ch.CharacterStore(), "memory_store", None)
        if store is None:
            raise ControllerError("CharacterStore 未初始化 memory_store；请先构造 CharacterStore()。")
        if tool == "list_memories":
            return {"items": [m.to_dict() if hasattr(m, "to_dict") else m for m in store.list(limit=a.get("limit", 50), scene=a.get("scene"))]}
        if tool == "read_memory":
            entry = store.get(a["id"])
            return entry.to_dict() if hasattr(entry, "to_dict") else entry
        if tool == "search_memory":
            return {"items": [h.to_dict() if hasattr(h, "to_dict") else h
                              for h in store.search(a["query"], limit=a.get("limit", 10))]}
        if tool == "add_memory":
            if not step_approved:
                raise PermissionDenied("add_memory 需要显式 approved。")
            created = store.add(a["content"], source=a.get("source","agent"),
                                visibility=a.get("visibility","private"),
                                tags=a.get("tags"), scene=a.get("scene"),
                                importance=float(a.get("importance",0.5)))
            return created.to_dict() if hasattr(created, "to_dict") else created
        raise ControllerError(f"dialogue 未知工具: {tool}")

    # ------------------------------------------------------------------
    # Presentation helpers
    # ------------------------------------------------------------------
    def _build_permission_request(self, *, plan_steps, mode, route, mode_decision) -> dict:
        return {
            "requested_at": utc_now_iso(),
            "mode": mode,
            "scene": route.get("scene"),
            "recommended_intent": route.get("recommended_intent"),
            "mode_reason": mode_decision.get("reason"),
            "requires_approval": list(mode_decision.get("requires_approval") or []) or self._collect_tools_needing_approval(plan_steps),
            "steps": [_step_summary(s) for s in plan_steps[:10]],
            "channel": classify_channel(str(route.get("scene") or "chat"), intent=mode_decision.get("recommended_intent")),
        }

    @staticmethod
    def _collect_tools_needing_approval(steps: Iterable[Any]) -> list[str]:
        names: list[str] = []
        for s in steps:
            d = _to_dict(s)
            tool = d.get("tool_name") or d.get("tool")
            if not tool:
                continue
            if d.get("requires_approval", tool not in {"list_project_files","read_project_file","ping","status","list_tools"}):
                names.append(str(tool))
        # dedupe-preserve-order
        return list(dict.fromkeys(names))

    @staticmethod
    def _proposal_text(steps, route, mode_decision, mode) -> str:
        mode_title = {"propose": "建议方案（先确认再动手）", "ask_permission": "需要你批准权限后继续"}.get(mode, "方案")
        head = f"[{mode_title}] 场景={route.get('scene') or 'chat'}，" \
               f"模式={mode_decision.get('mode')}，理由：{mode_decision.get('reason') or ''}"
        body_lines = []
        for i, s in enumerate(steps[:8], 1):
            body_lines.append(f"{i}. {_step_summary(s)}")
        body = "\n".join(body_lines) if body_lines else "（无具体步骤）"
        return f"{head}\n{body}"

    @staticmethod
    def _answer_from_results(results, route) -> str:
        if not results:
            return "（controller: 无可执行步骤）"
        good = [r for r in results if r.success]
        bad = [r for r in results if not r.success]
        final_lines = [f"执行完毕 · 成功 {len(good)} / 失败 {len(bad)} · 场景={route.get('scene','chat')}"]
        for r in good[-4:]:
            if r.action == "answer" and r.payload.get("text"):
                final_lines.append("—— 最终回答 ——\n" + r.payload["text"])
                break
        for r in bad[:2]:
            final_lines.append(f"✗ Step{r.step_index} [{r.channel}/{r.action}] 失败: {r.error}")
        return "\n".join(final_lines)

    @staticmethod
    def _fail_text(results) -> str:
        last = results[-1] if results else None
        return f"执行中断：{last.error if last else '未知错误'}。请检查 decision_request 获取详情。"


# ---------------------------------------------------------------------------
# Tiny util repeated throughout.
# ---------------------------------------------------------------------------

def _to_dict(obj: Any) -> dict:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    to_dict = getattr(obj, "to_dict", None)
    if callable(to_dict):
        try:
            d = to_dict()
            return d if isinstance(d, dict) else {}
        except Exception:
            pass
    # dataclass fallback
    try:
        import dataclasses as _dc
        if _dc.is_dataclass(obj):
            return {f.name: getattr(obj, f.name) for f in _dc.fields(obj)}
    except Exception:
        pass
    return {}


def _step_summary(step: Any) -> str:
    d = _to_dict(step)
    title = d.get("title") or d.get("thought") or ""
    tool = d.get("tool") or d.get("tool_name")
    risk = d.get("risk")
    parts = []
    if title:
        parts.append(truncate_text(str(title), 80, ""))
    if tool:
        parts.append(f"tool={tool}")
    if risk:
        parts.append(f"risk={risk}")
    if d.get("requires_approval"):
        parts.append("需要批准")
    return " · ".join(parts) or "(空步骤)"
