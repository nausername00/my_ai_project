"""Bounded project tools exposed to the approved agent loop."""

import hashlib
from pathlib import Path
from typing import Any


MAX_READ_BYTES = 256 * 1024
MAX_LIST_ENTRIES = 200
EXCLUDED_DIRECTORIES = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    "release",
    "dist",
    "build",
}
SENSITIVE_NAMES = {
    ".env",
    ".env.local",
    "id_rsa",
    "id_ed25519",
    "credentials.json",
    "secrets.json",
}
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
TEXT_EXTENSIONS = {
    ".c",
    ".cjs",
    ".css",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
TOOL_CATALOG = {
    "list_project_files": {
        "name": "list_project_files",
        "description": "列出项目中的非隐藏文件；默认排除依赖、构建目录和密钥文件。",
        "arguments": {"path": "项目内相对目录，可省略或用 . 表示项目根目录"},
        "risk": "read_only",
        "requires_approval": False,
    },
    "read_project_file": {
        "name": "read_project_file",
        "description": "读取项目内受支持的 UTF-8 文本文件；拒绝密钥文件、二进制和超大文件。",
        "arguments": {"path": "项目内相对文件路径"},
        "risk": "read_only",
        "requires_approval": False,
    },
    "create_project_file": {
        "name": "create_project_file",
        "description": "在项目现有目录中新建 UTF-8 文本文件；拒绝覆盖现有文件，需逐次审批。",
        "arguments": {"path": "项目内相对新文件路径", "content": "最多 4,000 字符的 UTF-8 内容"},
        "risk": "requires_permission",
        "requires_approval": True,
    },
    "write_project_file": {
        "name": "write_project_file",
        "description": "把 UTF-8 内容写入项目内的一个文件（新建或覆盖）；不允许写密钥或二进制。",
        "arguments": {"path": "项目内相对路径", "content": "文件内容字符串", "mkdir": "若父目录不存在是否自动创建"},
        "risk": "requires_permission",
        "requires_approval": True,
    },
    "patch_project_file": {
        "name": "patch_project_file",
        "description": "对单个项目文本文件做最小化 old→new 字符串替换；仅替换第一处匹配。",
        "arguments": {"path": "项目内相对路径", "old_string": "需要被替换的原片段", "new_string": "替换后的片段"},
        "risk": "requires_permission",
        "requires_approval": True,
    },
    "run_tests": {
        "name": "run_tests",
        "description": "在 sandbox 内运行 pytest（或自定义）测试命令；白名单命令。",
        "arguments": {"command": "命令参数列表或字符串", "timeout_seconds": "超时秒数"},
        "risk": "requires_permission",
        "requires_approval": True,
    },
    "run_sandboxed_shell": {
        "name": "run_sandboxed_shell",
        "description": "在严格命令白名单里运行 shell；不允许任意命令。",
        "arguments": {"command": "命令参数列表或字符串", "cwd": "工作目录（必须在 workspace 内）", "timeout_seconds": "超时秒数", "safe_commands": "可覆盖的白名单列表"},
        "risk": "requires_permission",
        "requires_approval": True,
    },
    "browser_goto": {
        "name": "browser_goto",
        "description": "打开浏览器并访问指定 URL（需已加入 allowed_browser_hosts）。",
        "arguments": {"url": "目标 URL", "headless": "是否无头模式"},
        "risk": "requires_permission",
        "requires_approval": True,
    },
    "browser_screenshot": {
        "name": "browser_screenshot",
        "arguments": {"url": "目标 URL", "save_path": "可选保存路径或目录", "full_page": "是否整页", "headless": "是否无头"},
        "description": "对指定 URL 整页截图并返回 PNG 信息。",
        "risk": "requires_permission",
        "requires_approval": True,
    },
    "browser_click": {
        "name": "browser_click",
        "arguments": {"url": "起始 URL", "selector": "CSS 选择器", "headless": "是否无头"},
        "description": "打开 URL 后点击选择器定位的元素。",
        "risk": "requires_permission",
        "requires_approval": True,
    },
    "browser_fill": {
        "name": "browser_fill",
        "arguments": {"url": "起始 URL", "selector": "CSS 选择器", "value": "要填入的字符串", "submit": "是否按 Enter 提交"},
        "description": "在表单元素里填入字符串，可选提交。",
        "risk": "requires_permission",
        "requires_approval": True,
    },
    "browser_text": {
        "name": "browser_text",
        "arguments": {"url": "目标 URL", "selector": "CSS 选择器（默认 body）", "limit_chars": "返回字符上限"},
        "description": "读取指定元素的 innerText。",
        "risk": "requires_permission",
        "requires_approval": True,
    },
    "render_cover": {
        "name": "render_cover",
        "arguments": {"title": "封面标题", "subtitle": "副标题", "palette": "可选色板名", "width": "像素宽", "height": "像素高", "save_dir": "可选保存目录（需 approved）"},
        "description": "生成一张 SVG 海报图（无需生图模型）。",
        "risk": "local_reversible",
        "requires_approval": False,
    },
    "render_avatar": {
        "name": "render_avatar",
        "arguments": {"name": "用于字母头像的名称", "palette": "色板", "size": "正方形像素尺寸", "save_dir": "可选保存目录（需 approved）"},
        "description": "生成一个 SVG 字母头像。",
        "risk": "local_reversible",
        "requires_approval": False,
    },
    "render_chart": {
        "name": "render_chart",
        "arguments": {"title": "标题", "values": "数值列表", "palette": "色板", "width": "宽", "height": "高"},
        "description": "生成一个 SVG 柱状图。",
        "risk": "local_reversible",
        "requires_approval": False,
    },
    "creator_create": {
        "name": "creator_create",
        "arguments": {"prompt": "提示词", "kind": "cover/avatar/chart/placeholder", "subtitle": "", "name": "", "size": "", "values": "[]", "palette": "", "save_dir": ""},
        "description": "统一入口走 visualize.Creator。",
        "risk": "local_reversible",
        "requires_approval": False,
    },
    "clipboard_read": {
        "name": "clipboard_read",
        "description": "读取系统剪贴板（纯文本）。",
        "arguments": {},
        "risk": "requires_permission",
        "requires_approval": True,
    },
    "clipboard_write": {
        "name": "clipboard_write",
        "arguments": {"value": "写入剪贴板的文本"},
        "description": "把字符串写入系统剪贴板。",
        "risk": "requires_permission",
        "requires_approval": True,
    },
    "open_path": {
        "name": "open_path",
        "arguments": {"path": "workspace 内或显式路径"},
        "description": "在文件管理器 / Finder / Explorer 中打开路径。",
        "risk": "requires_permission",
        "requires_approval": True,
    },
    "mouse_move": {
        "name": "mouse_move",
        "arguments": {"x": "绝对 X 像素", "y": "绝对 Y 像素", "duration_seconds": "移动时长"},
        "description": "移动鼠标到指定坐标。",
        "risk": "requires_permission",
        "requires_approval": True,
    },
    "click": {
        "name": "click",
        "arguments": {"x": "", "y": "", "button": "left/middle/right", "clicks": "点击次数", "interval_seconds": "点击间隔"},
        "description": "模拟鼠标点击。",
        "risk": "requires_permission",
        "requires_approval": True,
    },
    "keyboard_type": {
        "name": "keyboard_type",
        "arguments": {"text": "要输入的字符串", "interval_seconds": "按键间隔"},
        "description": "模拟键盘输入（英文为主；复杂 IME 场景请用 paste/clipboard_write）。",
        "risk": "requires_permission",
        "requires_approval": True,
    },
    "keystrokes": {"name": "keystrokes", "arguments": {"keys": "按键列表"}, "description": "依次按下按键。", "risk": "requires_permission", "requires_approval": True},
    "hotkey": {"name": "hotkey", "arguments": {"keys": "修饰键组合，如 ['ctrl','c']"}, "description": "同时按下组合键。", "risk": "requires_permission", "requires_approval": True},
    "ps": {"name": "ps", "arguments": {"limit": "返回的进程条数"}, "description": "列出当前系统进程，按 RSS 降序。", "risk": "requires_permission", "requires_approval": True},
    "shell": {"name": "shell", "arguments": {"command": "命令列表或字符串", "cwd": "", "timeout_seconds": "", "safe_commands": "可覆盖白名单"}, "description": "别名，等价 run_sandboxed_shell。", "risk": "requires_permission", "requires_approval": True},
    "read_memory": {"name": "read_memory", "arguments": {"id": "记忆条目的 id"}, "description": "读取角色长时记忆条目。", "risk": "local_reversible", "requires_approval": False},
    "list_memories": {"name": "list_memories", "arguments": {"limit": "返回条数", "scene": "可选场景过滤"}, "description": "列出角色长时记忆。", "risk": "local_reversible", "requires_approval": False},
    "search_memory": {"name": "search_memory", "arguments": {"query": "查询字符串", "limit": "返回条数"}, "description": "搜索角色长时记忆。", "risk": "local_reversible", "requires_approval": False},
    "add_memory": {"name": "add_memory", "arguments": {"content": "记忆内容", "source": "来源，如 agent/user", "visibility": "private/friend/public", "tags": "列表或逗号分隔", "scene": "场景名", "importance": "0..1 浮点数"}, "description": "新增一条角色记忆（需 approved）。", "risk": "requires_permission", "requires_approval": True},
}
PLAN_TOOL_NAMES = frozenset(
    {"list_project_files", "read_project_file", "create_project_file"}
)


def validate_tool_arguments(tool_name: Any, arguments: Any) -> dict[str, Any]:
    if tool_name not in TOOL_CATALOG:
        raise ValueError("tool is not registered")
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise ValueError("tool arguments must be an object")
    if tool_name == "list_project_files":
        if set(arguments) - {"path"}:
            raise ValueError("list_project_files accepts only an optional path")
        path = arguments.get("path", ".")
        if not isinstance(path, str) or not path.strip():
            raise ValueError("path must be a non-empty relative path")
        if Path(path).is_absolute():
            raise ValueError("absolute paths are not allowed")
        return {"path": path}
    if tool_name == "read_project_file":
        if set(arguments) != {"path"}:
            raise ValueError("read_project_file requires exactly one path argument")
        path = arguments["path"]
        if not isinstance(path, str) or not path.strip():
            raise ValueError("path must be a non-empty relative file path")
        if Path(path).is_absolute():
            raise ValueError("absolute paths are not allowed")
        return {"path": path}
    if tool_name == "create_project_file":
        if set(arguments) != {"path", "content"}:
            raise ValueError("create_project_file requires exactly path and content")
        path = arguments["path"]
        content = arguments["content"]
        path_parts = path.replace("\\", "/").split("/") if isinstance(path, str) else []
        if (
            not isinstance(path, str)
            or not path.strip()
            or path != path.strip()
            or len(path) > 500
            or Path(path).is_absolute()
            or Path(path).drive
            or Path(path).root
            or any(
                part in {"", ".", ".."}
                or ":" in part
                or part.endswith((".", " "))
                or part.split(".", 1)[0].upper() in WINDOWS_RESERVED_NAMES
                for part in path_parts
            )
        ):
            raise ValueError("create_project_file path must be a relative path up to 500 characters")
        if Path(path).name.startswith(".") or _is_sensitive(Path(path)):
            raise ValueError("create_project_file refuses hidden or sensitive files")
        if not isinstance(content, str) or not content.strip() or len(content) > 4000:
            raise ValueError("create_project_file content must contain 1 to 4000 characters")
        return {"path": path, "content": content}
    if tool_name == "write_project_file":
        required = {"path", "content"}
        optional = {"mkdir"}
        if not required.issubset(arguments) or not set(arguments).issubset(required | optional):
            raise ValueError("write_project_file 需要 path + content，可选 mkdir")
        path = arguments["path"]
        if not isinstance(path, str) or not path.strip() or Path(path).is_absolute():
            raise ValueError("write_project_file path 必须是非空相对路径")
        if not isinstance(arguments["content"], str):
            raise ValueError("write_project_file content 必须是字符串")
        if Path(path).name.startswith(".env") or _is_sensitive(Path(path)):
            raise ValueError("write_project_file 拒绝写入敏感/密钥文件")
        mkdir = bool(arguments.get("mkdir", True))
        return {"path": path, "content": arguments["content"], "mkdir": mkdir}
    if tool_name == "patch_project_file":
        required = {"path", "old_string", "new_string"}
        if set(arguments) != required:
            raise ValueError("patch_project_file 需要 path、old_string、new_string 三个参数")
        path = arguments["path"]
        if not isinstance(path, str) or not path.strip() or Path(path).is_absolute():
            raise ValueError("patch_project_file path 必须是非空相对路径")
        for k in ("old_string", "new_string"):
            if not isinstance(arguments[k], str):
                raise ValueError(f"patch_project_file {k} 必须是字符串")
        return {"path": path, "old_string": arguments["old_string"], "new_string": arguments["new_string"]}
    if tool_name in {"run_tests", "run_sandboxed_shell"}:
        optional = {"command", "timeout_seconds", "cwd", "safe_commands"}
        if not set(arguments).issubset(optional):
            raise ValueError(f"{tool_name} 只接受 command/timeout_seconds/cwd/safe_commands")
        out = {"command": arguments.get("command") or (
            ["py", "-3", "-m", "pytest", "-q"] if tool_name == "run_tests" else ["echo", "hello"]
        )}
        if "timeout_seconds" in arguments:
            out["timeout_seconds"] = int(arguments["timeout_seconds"])
        if "cwd" in arguments:
            out["cwd"] = arguments["cwd"]
        if "safe_commands" in arguments:
            out["safe_commands"] = list(arguments["safe_commands"])
        return out
    # 其余工具：arguments 本身允许自由结构，但值必须是 JSON 基本类型以降低注入面
    def _prim(v):
        if v is None or isinstance(v, (bool, int, float, str)):
            return True
        if isinstance(v, list):
            return all(_prim(x) for x in v)
        if isinstance(v, dict):
            return all(isinstance(k, str) and _prim(x) for k, x in v.items())
        return False
    for k, v in arguments.items():
        if not isinstance(k, str) or not _prim(v):
            raise ValueError(f"{tool_name} 参数必须是 JSON 基本类型")
    return dict(arguments)


def _resolve_regular_file(workspace_root: Path, relative_path: Any, *, must_exist: bool) -> Path:
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise ValueError("path must be a non-empty relative path")
    requested = Path(relative_path)
    if requested.is_absolute():
        raise ValueError("absolute paths are not allowed")
    root = workspace_root.resolve(strict=True)
    candidate = root / requested
    resolved = candidate.resolve(strict=must_exist)
    if not resolved.is_relative_to(root):
        raise ValueError("path must remain within the project workspace")
    if candidate.is_symlink():
        raise ValueError("symlinks are not allowed for project file writes")
    if must_exist and not resolved.is_file():
        raise ValueError("path must identify an existing regular file")
    if _is_sensitive(resolved) or resolved.suffix.lower() not in TEXT_EXTENSIONS:
        raise ValueError("write/patch 仅接受非敏感 UTF-8 文本扩展名")
    return resolved


def _resolve_directory(workspace_root: Path, relative_path: Any) -> Path:
    if relative_path is None:
        relative_path = "."
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise ValueError("path must be a non-empty relative path")
    requested = Path(relative_path)
    if requested.is_absolute():
        raise ValueError("absolute paths are not allowed")
    candidate = workspace_root / requested
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(workspace_root):
        raise ValueError("path must remain within the project workspace")
    if not resolved.is_dir():
        raise ValueError("path must identify a project directory")
    return resolved


def _is_sensitive(path: Path) -> bool:
    name = path.name.casefold()
    return (
        name in SENSITIVE_NAMES
        or name.startswith(".env.")
        or name.endswith((".pem", ".key", ".p12", ".pfx"))
        or "credential" in name
        or "secret" in name
    )


def list_project_files(workspace_root: Path, arguments: Any) -> dict[str, Any]:
    arguments = validate_tool_arguments("list_project_files", arguments)
    root = workspace_root.resolve(strict=True)
    directory = _resolve_directory(root, arguments.get("path"))
    entries = []
    truncated = False
    for path in sorted(directory.iterdir(), key=lambda item: item.name.casefold()):
        if path.name.startswith(".") or _is_sensitive(path):
            continue
        if path.is_dir():
            if path.name.casefold() in EXCLUDED_DIRECTORIES:
                continue
            if path.is_symlink():
                continue
            kind = "directory"
        elif path.is_file() and not path.is_symlink():
            kind = "file"
        else:
            continue
        if len(entries) >= MAX_LIST_ENTRIES:
            truncated = True
            break
        entries.append(
            {
                "path": path.relative_to(root).as_posix(),
                "kind": kind,
            }
        )
    return {
        "tool": "list_project_files",
        "path": directory.relative_to(root).as_posix() or ".",
        "entries": entries,
        "truncated": truncated,
    }


def read_project_file(workspace_root: Path, arguments: Any) -> dict[str, Any]:
    arguments = validate_tool_arguments("read_project_file", arguments)
    relative_path = arguments["path"]
    requested = Path(relative_path)
    if requested.is_absolute():
        raise ValueError("absolute paths are not allowed")
    root = workspace_root.resolve(strict=True)
    candidate = root / requested
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise ValueError("path must remain within the project workspace")
    if candidate.is_symlink() or not resolved.is_file():
        raise ValueError("path must identify a regular project file")
    if _is_sensitive(resolved):
        raise ValueError("reading sensitive files is not allowed")
    if resolved.suffix.casefold() not in TEXT_EXTENSIONS:
        raise ValueError("file type is not supported for text reading")
    if resolved.stat().st_size > MAX_READ_BYTES:
        raise ValueError("file exceeds the 256 KB read limit")
    try:
        content = resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("file is not valid UTF-8 text") from error
    return {
        "tool": "read_project_file",
        "path": resolved.relative_to(root).as_posix(),
        "bytes": resolved.stat().st_size,
        "content": content,
    }


def create_project_file(workspace_root: Path, arguments: Any) -> dict[str, Any]:
    args = validate_tool_arguments("create_project_file", arguments)
    try:
        content_bytes = args["content"].encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError("new file content must be valid UTF-8 text") from error
    root = workspace_root.resolve(strict=True)
    requested = Path(args["path"])
    candidate_parent = root
    for part in requested.parent.parts:
        if part == "..":
            raise ValueError("new file paths cannot contain parent-directory traversal")
        candidate_parent = candidate_parent / part
        if candidate_parent.is_symlink():
            raise ValueError("new file paths cannot traverse symbolic links")
    try:
        parent = candidate_parent.resolve(strict=True)
    except FileNotFoundError as error:
        raise ValueError("new file parent must already exist inside the project workspace") from error
    if not parent.is_relative_to(root) or not parent.is_dir():
        raise ValueError("new file parent must be an existing directory inside the project workspace")
    relative_parent = parent.relative_to(root)
    if any(
        part.startswith(".")
        or part.casefold() in EXCLUDED_DIRECTORIES
        or _is_sensitive(Path(part))
        for part in relative_parent.parts
    ):
        raise ValueError("new files cannot be created in hidden, sensitive, or excluded directories")
    target = parent / requested.name
    if _is_sensitive(target) or target.suffix.casefold() not in TEXT_EXTENSIONS:
        raise ValueError("new file must use a supported, non-sensitive text extension")

    try:
        with target.open("x", encoding="utf-8", newline="") as file:
            file.write(args["content"])
            file.flush()
    except FileExistsError as error:
        raise ValueError("target already exists; create_project_file never overwrites files") from error

    digest = hashlib.sha256(content_bytes).hexdigest()
    try:
        read_back = target.read_bytes()
    except OSError as error:
        return {
            "tool": "create_project_file",
            "path": target.relative_to(root).as_posix(),
            "created": True,
            "bytes": len(content_bytes),
            "sha256": digest,
            "verification": {
                "status": "uncertain",
                "error": f"file was created but read-back failed: {error}",
            },
        }
    read_back_digest = hashlib.sha256(read_back).hexdigest()
    return {
        "tool": "create_project_file",
        "path": target.relative_to(root).as_posix(),
        "created": True,
        "bytes": len(content_bytes),
        "sha256": digest,
        "verification": {
            "status": "confirmed" if read_back == content_bytes else "not_met",
            "bytes": len(read_back),
            "sha256": read_back_digest,
            "content_matches": read_back == content_bytes,
        },
    }


def write_project_file(workspace_root: Path, arguments: Any) -> dict[str, Any]:
    args = validate_tool_arguments("write_project_file", arguments)
    relative_path = args["path"]
    content = args["content"]
    if len(content) > 4 * 1024 * 1024:
        raise ValueError("单次写入不能超过 4MB")
    resolved = _resolve_regular_file(workspace_root, relative_path, must_exist=False)
    if args.get("mkdir", True):
        resolved.parent.mkdir(parents=True, exist_ok=True)
    if resolved.exists() and (resolved.is_symlink() or not resolved.is_file()):
        raise ValueError("目标路径已存在且不是普通文件")
    before_bytes = -1
    if resolved.exists():
        before_bytes = resolved.stat().st_size
    resolved.write_text(content, encoding="utf-8")
    return {
        "tool": "write_project_file",
        "path": resolved.relative_to(workspace_root.resolve(strict=True)).as_posix(),
        "bytes": len(content.encode("utf-8")),
        "overwrote_existing": before_bytes >= 0,
        "previous_bytes": before_bytes,
    }


def patch_project_file(workspace_root: Path, arguments: Any) -> dict[str, Any]:
    args = validate_tool_arguments("patch_project_file", arguments)
    resolved = _resolve_regular_file(workspace_root, args["path"], must_exist=True)
    old_s = args["old_string"]
    new_s = args["new_string"]
    if not old_s:
        raise ValueError("old_string 不能为空")
    original = resolved.read_text(encoding="utf-8")
    count = original.count(old_s)
    if count == 0:
        raise ValueError("old_string 未在目标文件中出现（可能文件已变更，请重新读取再 patch）")
    if count > 1:
        raise ValueError(f"old_string 出现 {count} 处，为避免歧义请提供更长上下文以便唯一匹配")
    replaced = original.replace(old_s, new_s, 1)
    resolved.write_text(replaced, encoding="utf-8")
    return {
        "tool": "patch_project_file",
        "path": resolved.relative_to(workspace_root.resolve(strict=True)).as_posix(),
        "replacements": 1,
        "previous_bytes": len(original.encode("utf-8")),
        "bytes": len(replaced.encode("utf-8")),
    }


def execute_project_tool(
    workspace_root: Path,
    tool_name: Any,
    arguments: Any,
) -> dict[str, Any]:
    if tool_name == "list_project_files":
        return list_project_files(workspace_root, arguments)
    if tool_name == "read_project_file":
        return read_project_file(workspace_root, arguments)
    if tool_name == "create_project_file":
        return create_project_file(workspace_root, arguments)
    if tool_name == "write_project_file":
        return write_project_file(workspace_root, arguments)
    if tool_name == "patch_project_file":
        return patch_project_file(workspace_root, arguments)
    # run_tests / run_sandboxed_shell 把权限和 dispatch 交给 computer_use 模块；
    # 这里只负责参数校验。
    if tool_name in {"run_tests", "run_sandboxed_shell"}:
        args = validate_tool_arguments(tool_name, arguments)
        import computer_use as _cu
        cmd = args["command"]
        safe = list(args.get("safe_commands") or _cu._SAFE_COMMANDS)
        result = _cu.run_sandboxed_shell(
            cmd,
            approved=True,
            purpose=f"agent_tools:{tool_name}",
            cwd=str(args.get("cwd") or workspace_root),
            timeout_seconds=int(args.get("timeout_seconds", 180 if tool_name == "run_tests" else 60)),
            safe_commands=safe,
        )
        return {"tool": tool_name, "result": result.to_dict()}
    # 其余（browser / visualize / system / memory 等）由 controller 直接路由到对应模块；
    # 这里仍做参数校验后返回一个 catalog 引用，避免上游调用误判为未注册。
    _ = validate_tool_arguments(tool_name, arguments)
    return {"tool": tool_name, "routed_by": "controller"}
