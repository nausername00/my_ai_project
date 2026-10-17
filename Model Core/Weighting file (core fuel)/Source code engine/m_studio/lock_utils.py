"""E4 最小版 · 写操作互斥锁（FileLock，内核级）。

防分身/多请求并发写同一个状态文件互相覆盖。

实现：对"目标文件旁独立的 lock 文件"加内核级字节锁（msvcrt.locking / fcntl.flock），
**目标文件本身不受锁影响**（可正常 open("w") 写入），锁的是"抢锁权"而非文件内容。

- 无删除竞态：锁文件允许残留（0 字节，无害）——内核按 fd 管理锁，fd 关闭即释放；
  下次任意进程 open 同一 lock 文件可再次加锁。
- 进程/线程崩溃或退出时内核自动释放，无"陈旧锁"问题。
- 锁粒度 = 目标路径；同一路径的写操作被串行化。
"""

from __future__ import annotations

import os
import time
from typing import Optional

if os.name == "nt":  # pragma: no cover - Windows
    import msvcrt
else:  # pragma: no cover - POSIX
    import fcntl


class FileLock:
    """对 target_path 的内核级互斥锁（同一文件的写操作串行化）。"""

    def __init__(self, target_path: str, timeout: float = 5.0, poll: float = 0.02) -> None:
        self.target_path = target_path
        self.lock_path = target_path + ".lock"
        self.timeout = timeout
        self.poll = poll
        self._fd: Optional[int] = None

    # ------------------------------------------------------------------ 锁
    def acquire(self) -> bool:
        # 锁文件允许残留（0 字节无害）；O_RDWR 不截断，避免误伤已有内容
        fd = os.open(self.lock_path, os.O_RDWR | os.O_CREAT)
        deadline = time.time() + self.timeout
        while True:
            try:
                if os.name == "nt":
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._fd = fd
                return True
            except OSError:
                if time.time() > deadline:
                    os.close(fd)
                    return False
                time.sleep(self.poll)

    def release(self) -> None:
        if self._fd is None:
            return
        try:
            if os.name == "nt":
                os.lseek(self._fd, 0, os.SEEK_SET)
                msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            os.close(self._fd)
        except OSError:
            pass
        self._fd = None

    # ------------------------------------------------------------------ with
    def __enter__(self) -> "FileLock":
        if not self.acquire():
            raise TimeoutError(f"未能获取文件锁: {self.lock_path}")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


def with_file_lock(target_path: str, timeout: float = 5.0):
    """便捷装饰器：被装饰函数执行期间持有 target_path 的写锁。"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            with FileLock(target_path, timeout=timeout):
                return func(*args, **kwargs)
        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper
    return decorator
