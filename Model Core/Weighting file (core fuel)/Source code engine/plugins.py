"""T6 插件 manifest 注册 + 基于成本账本的后端动态选型（第 11 / 12 层轻量落地）。

- PluginRegistry：本地插件清单（JSON）的读取与注册，确定性校验、可测试；
  只登记元数据（name/version/capabilities），不加载任意代码（插件执行另行授权）。
- choose_backend：消费 T3 CostLedger 快照，按任务偏好（speed/quality/balance）
  从可用后端中选择——speed 选平均耗时最低、quality 选调用最频繁（经验最多）、
  balance 回落到默认后端。规则确定、可复算，不依赖模型判断。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
_MAX_CAPABILITIES = 20
_MAX_CAPABILITY_LEN = 30


class PluginRegistry:
    """本地插件清单（JSON）：{plugins: [...]}，注册为覆盖更新，可追溯。"""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def _load(self) -> list[dict[str, Any]]:
        if not self._path.is_file():
            return []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            plugins = data.get("plugins", [])
            return list(plugins) if isinstance(plugins, list) else []
        except (OSError, ValueError, TypeError):
            return []

    def _save(self, plugins: list[dict[str, Any]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps({"plugins": plugins}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def list(self) -> list[dict[str, Any]]:
        return [dict(p) for p in self._load()]

    def register(self, manifest: dict[str, Any]) -> dict[str, Any]:
        """校验并注册插件 manifest；同名覆盖更新。未知字段拒绝。"""
        unknown = set(manifest) - {"name", "version", "capabilities"}
        if unknown:
            raise ValueError(f"manifest 包含不支持的字段: {sorted(unknown)}")
        name = str(manifest.get("name", "")).strip()
        version = str(manifest.get("version", "")).strip()
        capabilities = manifest.get("capabilities", [])
        if not 1 <= len(name) <= 40:
            raise ValueError("name 必须是 1–40 个字符")
        if not _VERSION_RE.match(version):
            raise ValueError("version 必须符合 x.y.z 格式")
        if not isinstance(capabilities, list) or not capabilities:
            raise ValueError("capabilities 必须是非空字符串列表")
        if len(capabilities) > _MAX_CAPABILITIES:
            raise ValueError(f"capabilities 最多 {_MAX_CAPABILITIES} 项")
        for capability in capabilities:
            if not isinstance(capability, str) or not 1 <= len(capability) <= _MAX_CAPABILITY_LEN:
                raise ValueError(f"capabilities 项必须是 1–{_MAX_CAPABILITY_LEN} 字符的字符串")

        plugins = self._load()
        entry = {"name": name, "version": version, "capabilities": list(capabilities)}
        for index, existing in enumerate(plugins):
            if existing.get("name") == name:
                plugins[index] = entry
                break
        else:
            plugins.append(entry)
        self._save(plugins)
        return entry


def choose_backend(
    ledger_snapshot: dict[str, Any],
    *,
    task: str = "chat",
    prefer: str = "balance",
    default: str = "local",
) -> dict[str, Any]:
    """基于成本账本按任务偏好选后端：speed→avg_ms 最低；quality→count 最多；
    balance→默认后端。规则确定、可复算。"""
    prefer = prefer if prefer in ("speed", "quality", "balance") else "balance"
    backends = ledger_snapshot.get("backends", {}) or {}
    candidates = sorted(backends)
    chosen, reason = default, "默认后端（balance 或无历史数据）"
    if backends and prefer == "speed":
        chosen = min(
            backends,
            key=lambda name: (backends[name].get("avg_ms", 0.0), name),
        )
        reason = f"speed：选择平均耗时最低的后端（{task}）"
    elif backends and prefer == "quality":
        chosen = max(
            backends,
            key=lambda name: (backends[name].get("count", 0), name),
        )
        reason = f"quality：选择调用最频繁（经验最多）的后端（{task}）"
    return {
        "task": task,
        "prefer": prefer,
        "chosen": chosen,
        "reason": reason,
        "candidates": candidates,
    }
