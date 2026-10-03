"""L4 execution – desktop automation (keyboard / mouse / clipboard / process).

Every public function takes ``approved`` as its first keyword argument with
``False`` as default and raises :class:`utils.PermissionDenied` *before*
importing any heavy dependency.  Optional back-ends (``pyautogui``,
``pygetwindow``, ``psutil``) are import-lazy and raise
:class:`utils.ModuleUnavailableError` when missing – that way the module
always imports cleanly with zero third-party packages.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from utils import (
    ModuleUnavailableError,
    PermissionDenied,
    SingletonLock,
    safe_relpath,
    truncate_text,
    utc_now_iso,
)

__all__ = [
    "ClipboardPayload",
    "DesktopAutomation",
    "DesktopAutomationError",
    "ExecutedProcess",
    "automate_click",
    "automate_hotkey",
    "automate_keystrokes",
    "automate_mouse_move",
    "automate_type",
    "clipboard_read",
    "clipboard_write",
    "list_processes",
    "open_in_explorer",
    "run_sandboxed_shell",
]


class DesktopAutomationError(RuntimeError):
    """Raised for desktop side-effects that fail for any structural reason
    *after* the permission gate has passed."""


@dataclass(frozen=True)
class ClipboardPayload:
    kind: str
    value: str
    captured_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "value": self.value,
            "captured_at": self.captured_at,
        }


@dataclass(frozen=True)
class ExecutedProcess:
    command: tuple
    returncode: int
    stdout: str
    stderr: str
    duration_ms: int
    killed: bool
    timed_out: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": list(self.command),
            "returncode": int(self.returncode),
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_ms": int(self.duration_ms),
            "killed": bool(self.killed),
            "timed_out": bool(self.timed_out),
        }


# ---------------------------------------------------------------------------
# Permission & dependency gates
# ---------------------------------------------------------------------------

def _gate(operation: str, approved: bool, purpose: str | None) -> None:
    if not approved:
        detail = purpose and f"（目的：{purpose}）" or ""
        raise PermissionDenied(
            f"用户尚未授权桌面操作 '{operation}'{detail}。\n"
            "请显式传入 approved=True 后重试。"
        )


def _require(name: str, human: str, extra: str) -> Any:
    if find_spec(name) is None:
        raise ModuleUnavailableError(
            f"{human} 需要包 '{name}'；请安装 'execution' extra:  pip install .[{extra}]"
        )
    import importlib
    return importlib.import_module(name)


# ---------------------------------------------------------------------------
# Keyboard / mouse primitives (Phase 5-13)
# ---------------------------------------------------------------------------

def automate_mouse_move(
    *,
    approved: bool = False,
    purpose: str | None = None,
    x: int,
    y: int,
    duration_seconds: float = 0.2,
) -> dict[str, Any]:
    _gate("automate_mouse_move", approved, purpose)
    pag = _require("pyautogui", "automate_mouse_move", "execution")
    import time as _t
    t0 = _t.monotonic()
    try:
        pag.moveTo(int(x), int(y), duration=float(duration_seconds))
    except Exception as exc:
        raise DesktopAutomationError(f"mouse move failed: {exc}") from exc
    return {
        "x": int(x),
        "y": int(y),
        "duration_ms": int(round((_t.monotonic() - t0) * 1000)),
        "approved": True,
        "purpose": str(purpose or ""),
    }


def automate_click(
    *,
    approved: bool = False,
    purpose: str | None = None,
    x: int | None = None,
    y: int | None = None,
    button: str = "left",
    clicks: int = 1,
    interval_seconds: float = 0.05,
) -> dict[str, Any]:
    _gate("automate_click", approved, purpose)
    pag = _require("pyautogui", "automate_click", "execution")
    import time as _t
    t0 = _t.monotonic()
    try:
        if x is None or y is None:
            pag.click(button=str(button), clicks=int(clicks), interval=float(interval_seconds))
        else:
            pag.click(
                x=int(x), y=int(y),
                button=str(button), clicks=int(clicks), interval=float(interval_seconds),
            )
    except Exception as exc:
        raise DesktopAutomationError(f"automate_click failed: {exc}") from exc
    return {
        "x": x, "y": y, "button": str(button), "clicks": int(clicks),
        "duration_ms": int(round((_t.monotonic() - t0) * 1000)),
        "approved": True, "purpose": str(purpose or ""),
    }


def automate_type(
    *,
    approved: bool = False,
    purpose: str | None = None,
    text: str,
    interval_seconds: float = 0.0,
) -> dict[str, Any]:
    _gate("automate_type", approved, purpose)
    text = truncate_text(str(text), 2000, "")
    if not text:
        raise DesktopAutomationError("text is empty")
    pag = _require("pyautogui", "automate_type", "execution")
    import time as _t
    t0 = _t.monotonic()
    try:
        pag.write(text, interval=float(interval_seconds))
    except Exception as exc:
        raise DesktopAutomationError(f"automate_type failed: {exc}") from exc
    return {
        "text_length": len(text),
        "duration_ms": int(round((_t.monotonic() - t0) * 1000)),
        "approved": True, "purpose": str(purpose or ""),
    }


def automate_keystrokes(
    *,
    approved: bool = False,
    purpose: str | None = None,
    keys: Sequence[str],
) -> dict[str, Any]:
    _gate("automate_keystrokes", approved, purpose)
    if not keys:
        raise DesktopAutomationError("keys must be a non-empty list")
    keys_list = [str(k) for k in keys][:64]
    pag = _require("pyautogui", "automate_keystrokes", "execution")
    import time as _t
    t0 = _t.monotonic()
    try:
        for k in keys_list:
            pag.press(k)
    except Exception as exc:
        raise DesktopAutomationError(f"automate_keystrokes failed: {exc}") from exc
    return {
        "keys": keys_list,
        "duration_ms": int(round((_t.monotonic() - t0) * 1000)),
        "approved": True, "purpose": str(purpose or ""),
    }


def automate_hotkey(
    *,
    approved: bool = False,
    purpose: str | None = None,
    keys: Sequence[str],
) -> dict[str, Any]:
    _gate("automate_hotkey", approved, purpose)
    if not keys:
        raise DesktopAutomationError("hotkey needs at least one key")
    keys_list = [str(k) for k in keys][:10]
    pag = _require("pyautogui", "automate_hotkey", "execution")
    import time as _t
    t0 = _t.monotonic()
    try:
        pag.hotkey(*keys_list)
    except Exception as exc:
        raise DesktopAutomationError(f"automate_hotkey failed: {exc}") from exc
    return {
        "keys": keys_list,
        "duration_ms": int(round((_t.monotonic() - t0) * 1000)),
        "approved": True, "purpose": str(purpose or ""),
    }


# ---------------------------------------------------------------------------
# Clipboard primitives
# ---------------------------------------------------------------------------

def clipboard_read(
    *,
    approved: bool = False,
    purpose: str | None = None,
) -> ClipboardPayload:
    _gate("clipboard_read", approved, purpose)
    try:
        # Windows first (stdlib ctypes).  Fall back to pyperclip.
        if sys.platform.startswith("win"):
            import ctypes
            CF_UNICODETEXT = 13
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            user32.OpenClipboard(0)
            try:
                handle = user32.GetClipboardData(CF_UNICODETEXT)
                if not handle:
                    text = ""
                else:
                    k32.GlobalLock.restype = ctypes.c_void_p
                    ptr = k32.GlobalLock(handle)
                    try:
                        text = ctypes.c_wchar_p(ptr).value or ""
                    finally:
                        k32.GlobalUnlock(handle)
            finally:
                user32.CloseClipboard()
        else:
            pyperclip = _require("pyperclip", "clipboard_read", "execution")
            text = pyperclip.paste() or ""
    except ModuleUnavailableError:
        raise
    except Exception as exc:
        raise DesktopAutomationError(f"clipboard_read failed: {exc}") from exc
    return ClipboardPayload(kind="text", value=truncate_text(text, 20000, ""), captured_at=utc_now_iso())


def clipboard_write(
    value: str,
    *,
    approved: bool = False,
    purpose: str | None = None,
) -> ClipboardPayload:
    _gate("clipboard_write", approved, purpose)
    value = truncate_text(str(value), 20000, "")
    try:
        if sys.platform.startswith("win"):
            import ctypes
            CF_UNICODETEXT = 13
            GMEM_MOVEABLE = 0x0002
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            data = value.encode("utf-16le") + b"\x00\x00"
            handle = k32.GlobalAlloc(GMEM_MOVEABLE, len(data))
            k32.GlobalLock.restype = ctypes.c_void_p
            ptr = k32.GlobalLock(handle)
            ctypes.memmove(ptr, data, len(data))
            k32.GlobalUnlock(handle)
            user32.OpenClipboard(0)
            try:
                user32.EmptyClipboard()
                user32.SetClipboardData(CF_UNICODETEXT, handle)
            finally:
                user32.CloseClipboard()
        else:
            pyperclip = _require("pyperclip", "clipboard_write", "execution")
            pyperclip.copy(value)
    except ModuleUnavailableError:
        raise
    except Exception as exc:
        raise DesktopAutomationError(f"clipboard_write failed: {exc}") from exc
    return ClipboardPayload(kind="text", value=value, captured_at=utc_now_iso())


# ---------------------------------------------------------------------------
# OS helpers
# ---------------------------------------------------------------------------

def open_in_explorer(
    path: str | Path,
    *,
    approved: bool = False,
    purpose: str | None = None,
    workspace_root: str | Path | None = None,
) -> dict[str, Any]:
    _gate("open_in_explorer", approved, purpose)
    p = Path(path).expanduser()
    if workspace_root is not None:
        rel = safe_relpath(Path(workspace_root).expanduser().resolve(), p.resolve())
        p = (Path(workspace_root).expanduser().resolve() / rel).resolve()
    else:
        p = p.resolve()
    if not p.exists():
        raise DesktopAutomationError(f"path does not exist: {p.as_posix()}")
    import time as _t
    t0 = _t.monotonic()
    try:
        if sys.platform.startswith("win"):
            os.startfile(p)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", p.as_posix()])
        else:
            subprocess.Popen(["xdg-open", p.as_posix()])
    except Exception as exc:
        raise DesktopAutomationError(f"open_in_explorer failed: {exc}") from exc
    return {
        "path": p.as_posix(),
        "duration_ms": int(round((_t.monotonic() - t0) * 1000)),
        "approved": True, "purpose": str(purpose or ""),
    }


def list_processes(
    *,
    approved: bool = False,
    purpose: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    _gate("list_processes", approved, purpose)
    psutil = _require("psutil", "list_processes", "execution")
    try:
        procs = []
        for proc in psutil.process_iter(["pid", "name", "username", "cpu_percent", "memory_info"]):
            info = proc.info
            mem = (info.get("memory_info") or None)
            rss = int(getattr(mem, "rss", 0) or 0)
            procs.append({
                "pid": int(info.get("pid", 0)),
                "name": str(info.get("name") or ""),
                "username": str(info.get("username") or ""),
                "cpu_percent": round(float(info.get("cpu_percent") or 0.0), 2),
                "rss_bytes": rss,
            })
            if len(procs) >= int(limit):
                break
        procs.sort(key=lambda d: d["rss_bytes"], reverse=True)
    except Exception as exc:
        raise DesktopAutomationError(f"list_processes failed: {exc}") from exc
    return procs


# ---------------------------------------------------------------------------
# Sandboxed shell (strictly opt-in).  Purposefully restrictive default.
# ---------------------------------------------------------------------------

_SAFE_COMMANDS: frozenset[str] = frozenset({
    "echo", "dir", "ls", "cd", "pwd", "type", "cat", "date", "time",
    "where", "which", "git", "python", "py", "node", "npm", "pip",
    "black", "ruff", "mypy", "pytest",
})


def run_sandboxed_shell(
    command: Sequence[str] | str,
    *,
    approved: bool = False,
    purpose: str | None = None,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    timeout_seconds: int = 30,
    safe_commands: Iterable[str] = _SAFE_COMMANDS,
) -> ExecutedProcess:
    _gate("run_sandboxed_shell", approved, purpose)
    import time as _t, shlex as _sh
    if isinstance(command, str):
        cmd_list = _sh.split(command, posix=os.name != "nt")
    else:
        cmd_list = [str(c) for c in command]
    if not cmd_list:
        raise DesktopAutomationError("empty command")
    exe = cmd_list[0]
    safe = frozenset(safe_commands)
    exe_base = Path(exe).name.casefold()
    if exe_base not in {s.casefold() for s in safe}:
        raise PermissionDenied(
            f"命令 '{exe_base}' 未列入 sandbox 白名单。"
            "若你明确需要，请在 safe_commands 里加入它并再次授权 approved=True。"
        )
    t0 = _t.monotonic()
    killed = False
    timed_out = False
    resolved_cwd = Path(cwd).resolve() if cwd else None
    proc_env = os.environ.copy()
    if env:
        proc_env.update({str(k): str(v) for k, v in env.items()})
    try:
        proc = subprocess.Popen(
            cmd_list,
            cwd=str(resolved_cwd) if resolved_cwd else None,
            env=proc_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,
        )
    except Exception as exc:
        raise DesktopAutomationError(f"failed to launch command: {exc}") from exc
    try:
        out, err = proc.communicate(timeout=max(1, int(timeout_seconds)))
    except subprocess.TimeoutExpired:
        proc.kill()
        killed = True
        timed_out = True
        out, err = proc.communicate()
    rc = proc.returncode if proc.returncode is not None else -1
    return ExecutedProcess(
        command=tuple(cmd_list),
        returncode=int(rc),
        stdout=truncate_text(out or "", 200_000, ""),
        stderr=truncate_text(err or "", 200_000, ""),
        duration_ms=int(round((_t.monotonic() - t0) * 1000)),
        killed=bool(killed),
        timed_out=bool(timed_out),
    )


# ---------------------------------------------------------------------------
# Facade object (convenient for long-lived app state)
# ---------------------------------------------------------------------------

class DesktopAutomation:
    """Thread-safe facade that carries an approval-granting scope so the
    caller doesn't have to re-pass ``approved`` on every invocation.
    """

    def __init__(
        self,
        *,
        approved: bool = False,
        session_purpose: str | None = None,
        session_approved_tools: Iterable[str] = (),
    ) -> None:
        self.session_approved = bool(approved)
        self.session_purpose = str(session_purpose or "")
        self.session_approved_tools = frozenset(session_approved_tools)
        self._lock = SingletonLock()

    # -- helpers ----------------------------------------------------------
    def _ok(self, tool: str, explicit: bool | None) -> bool:
        return bool(explicit) or (self.session_approved and tool in self.session_approved_tools)

    def _purpose(self, override: str | None) -> str:
        return str(override or self.session_purpose or "")

    # -- public API -------------------------------------------------------
    def mouse_move(self, x: int, y: int, *, approved: bool | None = None, purpose: str | None = None, **kw):
        return automate_mouse_move(approved=self._ok("mouse_move", approved), purpose=self._purpose(purpose), x=x, y=y, **kw)

    def click(self, *, approved: bool | None = None, purpose: str | None = None, **kw):
        return automate_click(approved=self._ok("click", approved), purpose=self._purpose(purpose), **kw)

    def keyboard_type(self, text: str, *, approved: bool | None = None, purpose: str | None = None, **kw):
        return automate_type(approved=self._ok("keyboard_type", approved), purpose=self._purpose(purpose), text=text, **kw)

    def keystrokes(self, keys: Sequence[str], *, approved: bool | None = None, purpose: str | None = None):
        return automate_keystrokes(approved=self._ok("keystrokes", approved), purpose=self._purpose(purpose), keys=keys)

    def hotkey(self, keys: Sequence[str], *, approved: bool | None = None, purpose: str | None = None):
        return automate_hotkey(approved=self._ok("hotkey", approved), purpose=self._purpose(purpose), keys=keys)

    def clipboard_read(self, *, approved: bool | None = None, purpose: str | None = None):
        return clipboard_read(approved=self._ok("clipboard_read", approved), purpose=self._purpose(purpose))

    def clipboard_write(self, value: str, *, approved: bool | None = None, purpose: str | None = None):
        return clipboard_write(value, approved=self._ok("clipboard_write", approved), purpose=self._purpose(purpose))

    def open_path(self, path: str | Path, *, approved: bool | None = None, purpose: str | None = None, **kw):
        return open_in_explorer(path, approved=self._ok("open_path", approved), purpose=self._purpose(purpose), **kw)

    def ps(self, *, approved: bool | None = None, purpose: str | None = None, **kw):
        return list_processes(approved=self._ok("ps", approved), purpose=self._purpose(purpose), **kw)

    def shell(self, command, *, approved: bool | None = None, purpose: str | None = None, **kw):
        return run_sandboxed_shell(command, approved=self._ok("shell", approved), purpose=self._purpose(purpose), **kw)
