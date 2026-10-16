"""T6 插件 manifest 注册 + 基于成本账本的后端动态选型（第 11 / 12 层轻量落地）。

- PluginRegistry：本地插件清单（JSON）的读取与注册，确定性校验、可测试；
  只登记元数据（name/version/capabilities/permissions），不加载任意代码
  （插件执行需经 PluginApprovals 显式授权）。
- PluginApprovals：用户批准存储（approvals.json）——插件执行任意能力前必须
  已获用户批准；批准可查看、可撤销，默认全部拒绝（默认关原则）。
- choose_backend：消费 T3 CostLedger 快照，按任务偏好（speed/quality/balance）
  从可用后端中选择——speed 选平均耗时最低、quality 选调用最频繁（经验最多）、
  balance 回落到默认后端。规则确定、可复算，不依赖模型判断。
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
_MAX_CAPABILITIES = 20
_MAX_CAPABILITY_LEN = 30
_MAX_PERMISSIONS = 10
_MAX_PERMISSION_LEN = 30
_PERMISSION_RE = re.compile(r"^[a-z][a-z0-9:_-]*$")


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

    def get(self, name: str) -> dict[str, Any] | None:
        """按插件名取 manifest；不存在返回 None。"""
        for plugin in self._load():
            if plugin.get("name") == name:
                return dict(plugin)
        return None

    def register(self, manifest: dict[str, Any]) -> dict[str, Any]:
        """校验并注册插件 manifest；同名覆盖更新。未知字段拒绝。

        支持字段：name / version / capabilities（能力声明，必填）/
        permissions（权限声明，可选，执行前须经用户批准）。
        """
        unknown = set(manifest) - {"name", "version", "capabilities", "permissions"}
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

        permissions = manifest.get("permissions", [])
        if not isinstance(permissions, list):
            raise ValueError("permissions 必须是字符串列表")
        if len(permissions) > _MAX_PERMISSIONS:
            raise ValueError(f"permissions 最多 {_MAX_PERMISSIONS} 项")
        for permission in permissions:
            if (
                not isinstance(permission, str)
                or not 1 <= len(permission) <= _MAX_PERMISSION_LEN
                or not _PERMISSION_RE.match(permission)
            ):
                raise ValueError(
                    f"permissions 项必须是 1–{_MAX_PERMISSION_LEN} 字符、"
                    "小写字母/数字/_/-/: 组成（如 file:read）"
                )

        plugins = self._load()
        entry = {
            "name": name,
            "version": version,
            "capabilities": list(capabilities),
            "permissions": list(permissions),
        }
        for index, existing in enumerate(plugins):
            if existing.get("name") == name:
                plugins[index] = entry
                break
        else:
            plugins.append(entry)
        self._save(plugins)
        return entry


class PluginApprovals:
    """用户批准存储（approvals.json）：{name: {permissions:[...], approved_at}}。

    默认全部拒绝；授权可查看/追加/撤销。文件损坏时按无授权处理（不静默放行）。
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self._path.is_file():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def _save(self, data: dict[str, dict[str, Any]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def authorize(self, name: str, permissions: list[str]) -> dict[str, Any]:
        """为插件批准指定权限（全量覆盖）。校验权限名格式。"""
        name = str(name or "").strip()
        if not name or len(name) > 40:
            raise ValueError("插件名必须为 1–40 个字符")
        if not isinstance(permissions, list):
            raise ValueError("permissions 必须是字符串列表")
        for permission in permissions:
            if (
                not isinstance(permission, str)
                or not 1 <= len(permission) <= _MAX_PERMISSION_LEN
                or not _PERMISSION_RE.match(permission)
            ):
                raise ValueError(f"permissions 项格式不合法: {permission!r}")
        data = self._load()
        data[name] = {
            "permissions": list(dict.fromkeys(permissions)),
            "approved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        self._save(data)
        return self.status(name)

    def revoke(self, name: str) -> dict[str, Any]:
        """撤销插件全部授权（默认回到拒绝）。"""
        data = self._load()
        data.pop(name, None)
        self._save(data)
        return {"name": name, "permissions": [], "approved": False}

    def is_authorized(self, name: str, permission: str) -> bool:
        """指定权限是否已获用户批准（执行前校验用）。"""
        entry = self._load().get(name)
        return bool(entry) and permission in entry.get("permissions", [])

    def status(self, name: str) -> dict[str, Any]:
        """插件授权状态：已批准权限列表与是否批准（只读，供展示/决策）。"""
        entry = self._load().get(name)
        if not entry:
            return {"name": name, "permissions": [], "approved": False}
        return {
            "name": name,
            "permissions": list(entry.get("permissions", [])),
            "approved": bool(entry.get("permissions")),
            "approved_at": entry.get("approved_at"),
        }


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
