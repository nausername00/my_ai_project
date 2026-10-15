"""审计日志（阶段 0：字段白名单 + 轮转 + 失败静默）。

把 API 请求的**元数据**以 JSONL 形式追加到 Logs & Checkpoints/logs/api_audit.jsonl。

白名单原则：只记录定位问题所需的最小元数据——
  ts / method / route / status / duration_ms / error / client
绝不记录：请求头（含 Authorization、X-Moling-Tool-Capability）、请求体、
记忆正文、完整对话、音频/图像内容、文件路径中的用户私有信息。
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# 允许写入审计行的字段白名单；白名单之外的键一律拒绝。
_ALLOWED_FIELDS = frozenset(
    {
        "ts",
        "method",
        "route",
        "status",
        "duration_ms",
        "error",
        "client",
    }
)

_MAX_BYTES = 5 * 1024 * 1024  # 单文件 5 MB 后轮转


class AuditLog:
    """线程安全的 JSONL 审计日志；日志失败时静默（不干扰请求处理）。"""

    def __init__(self, log_dir: str | Path, filename: str = "api_audit.jsonl") -> None:
        self._directory = Path(log_dir)
        self._filename = filename
        self._lock = threading.Lock()
        self._path: Path | None = None
        self._bytes_written = 0

    # -- 路径 -----------------------------------------------------------

    def _resolve_path(self) -> Path:
        if self._path is None:
            self._directory.mkdir(parents=True, exist_ok=True)
            self._path = self._directory / self._filename
            if self._path.exists():
                try:
                    self._bytes_written = self._path.stat().st_size
                except OSError:
                    self._bytes_written = 0
        return self._path

    def _rotate(self) -> None:
        """当前文件超过上限时，把旧文件改名为 api_audit.1.jsonl 并另起新文件。"""
        if self._bytes_written < _MAX_BYTES:
            return
        path = self._resolve_path()
        if path.exists():
            try:
                archived = path.with_name(path.stem + ".1" + path.suffix)
                if archived.exists():
                    archived.unlink()
                path.rename(archived)
            except OSError:
                return  # 轮转失败不中断请求
        self._bytes_written = 0
        self._path = None

    # -- 写入 -----------------------------------------------------------

    def record(
        self,
        *,
        method: str = "",
        route: str = "",
        status: int = 200,
        duration_ms: float = 0.0,
        error: str = "",
        client: str = "",
    ) -> bool:
        """写入一条审计记录；只接受白名单字段，写失败返回 False 而不抛出。"""
        entry: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "method": str(method)[:32],
            "route": str(route)[:256],
            "status": int(status),
            "duration_ms": round(float(duration_ms), 1),
            "error": str(error)[:64],
            "client": str(client)[:16],
        }
        # 防御：任何不在白名单里的键（哪怕调用方误传）都不得落盘。
        entry = {key: value for key, value in entry.items() if key in _ALLOWED_FIELDS}
        try:
            line = (json.dumps(entry, ensure_ascii=False) + "\n").encode("utf-8")
        except (TypeError, ValueError):
            return False
        with self._lock:
            self._rotate()
            path = self._resolve_path()
            try:
                with path.open("ab") as handle:
                    handle.write(line)
                self._bytes_written += len(line)
            except OSError:
                return False
        return True

    # -- 读取（供测试与 /v1/status 审计视图使用） ----------------------

    def read_entries(self, limit: int = 50) -> list[dict[str, Any]]:
        """回读最近 limit 条审计记录；文件缺失/损坏时返回已解析部分。"""
        entries: list[dict[str, Any]] = []
        path = self._resolve_path()
        if not path.exists():
            return entries
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        parsed = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(parsed, dict):
                        entries.append(parsed)
                    if len(entries) >= limit:
                        break
        except OSError:
            return entries
        return entries
