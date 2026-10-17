"""E4 最小版 · 写互斥锁测试（内核级文件锁）。

覆盖：FileLock 互斥/上下文清理/超时、
并发摸头计数不丢失（读-改-写原子化）、重复获取不残留。
"""
import os
import threading

import pytest

from m_studio.lock_utils import FileLock
from m_studio.m5_headpat import HeadpatScript


def test_filelock_mutual_exclusion(tmp_path) -> None:
    target = str(tmp_path / "state.json")
    lock1 = FileLock(target, timeout=0.1)
    lock2 = FileLock(target, timeout=0.1)
    assert lock1.acquire()
    # 第二个锁在同一文件上应超时失败
    assert not lock2.acquire()
    lock1.release()
    # 释放后第二个锁可获取
    assert lock2.acquire()
    lock2.release()


def test_filelock_context_manager_cleans_up(tmp_path) -> None:
    target = str(tmp_path / "s.json")
    with FileLock(target):
        pass
    # 锁文件残留无害（内核按 fd 管理锁）；退出后可再次获取
    assert FileLock(target, timeout=0.1).acquire()


def test_filelock_timeout_raises_in_context(tmp_path) -> None:
    target = str(tmp_path / "s.json")
    held = FileLock(target, timeout=0.2)
    held.acquire()
    try:
        with pytest.raises(TimeoutError):
            with FileLock(target, timeout=0.1):
                pass
    finally:
        held.release()


def test_filelock_reentrant_after_release(tmp_path) -> None:
    """同一目标文件：释放后立即可再次获取（锁文件残留不影响）。"""
    target = str(tmp_path / "s.json")
    for _ in range(3):
        with FileLock(target, timeout=1.0):
            pass
    assert FileLock(target, timeout=0.1).acquire()


def test_concurrent_headpat_count_no_loss(tmp_path) -> None:
    """多线程并发摸头：写锁保证计数不丢（读-改-写原子化）。"""
    state_path = str(tmp_path / "headpat.json")
    script = HeadpatScript(state_path=state_path)
    n = 20
    threads = [threading.Thread(target=script.touch) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert script.status()["count"] == n
    # 锁文件残留无害；目标状态文件本身无 .lock 痕迹要求（内核锁独立于目标文件）
