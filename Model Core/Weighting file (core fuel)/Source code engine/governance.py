"""T3 轻量平台治理：任务状态时间线 + 按后端成本统计（第 7 层 / E4 最轻形态）。

- CostLedger：线程安全地按后端分桶累计 请求数 / 字符数 / 耗时（内存态，
  与既有 _METRICS 一致）；供「多后端并行后按成本选型」（T6 动态选型）消费。
- task_status_timeline：把分身工具痕迹（tool_log）聚合成任务状态时间线视图
  （总数 / 各状态分布 / 最近条目），本地确定性、可测试。
"""

from __future__ import annotations

import threading
from time import time
from typing import Any


class CostLedger:
    """按后端分桶的生成成本账本（线程安全）。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._backends: dict[str, dict[str, float]] = {}

    def record(self, backend: str, chars: int, elapsed_ms: float) -> None:
        """记录一次生成：backend 非空归一化，负值截断为 0。"""
        name = str(backend).strip() or "unknown"
        with self._lock:
            bucket = self._backends.setdefault(
                name, {"count": 0.0, "chars": 0.0, "total_ms": 0.0}
            )
            bucket["count"] += 1
            bucket["chars"] += max(0, chars)
            bucket["total_ms"] += max(0.0, elapsed_ms)

    def snapshot(self) -> dict[str, Any]:
        """快照：每后端 {count/chars/total_ms/avg_ms} + 汇总 totals。"""
        with self._lock:
            backends: dict[str, dict[str, Any]] = {}
            for name, bucket in self._backends.items():
                count = int(bucket["count"])
                total_ms = round(bucket["total_ms"], 1)
                backends[name] = {
                    "count": count,
                    "chars": int(bucket["chars"]),
                    "total_ms": total_ms,
                    "avg_ms": round(total_ms / count, 1) if count else 0.0,
                }
            totals = {
                "count": sum(b["count"] for b in backends.values()),
                "chars": sum(b["chars"] for b in backends.values()),
                "total_ms": round(sum(b["total_ms"] for b in backends.values()), 1),
            }
        return {"backends": backends, "totals": totals, "generated_at": round(time(), 1)}


# 可展示的任务终态（tool_log result_status 之外补 "running" 语义）
_TERMINAL_STATUSES = ("ok", "denied", "failed", "blocked", "cancelled")


def task_status_timeline(
    entries: list[dict[str, Any]],
    *,
    limit: int = 100,
) -> dict[str, Any]:
    """把工具痕迹聚合为任务状态视图：总数 / 各状态分布 / 最近时间线。"""
    by_status: dict[str, int] = {status: 0 for status in _TERMINAL_STATUSES}
    by_status["pending"] = 0
    recent: list[dict[str, Any]] = []
    for entry in reversed(list(entries)):
        status = str(entry.get("result_status") or entry.get("decision") or "unknown")
        normalized = status if status in by_status else "unknown"
        by_status[normalized] = by_status.get(normalized, 0) + 1
        recent.append(
            {
                "at": entry.get("at"),
                "task": entry.get("task"),
                "avatar_id": entry.get("avatar_id"),
                "status": normalized,
                "authorization": entry.get("authorization"),
            }
        )
        if len(recent) >= limit:
            break
    return {
        "total": sum(by_status.values()),
        "by_status": by_status,
        "recent": recent,
    }
