"""FileLock 快速冒烟。用完即删。"""
import os
import sys
import tempfile

sys.path.insert(0, r"D:\Coding\code program\test\This is mine\my_ai_project\Model Core\Weighting file (core fuel)\Source code engine")
from m_studio.lock_utils import FileLock, _pid_alive

print("pid_alive(999999999)=", _pid_alive(999999999))
print("pid_alive(self)=", _pid_alive(os.getpid()))

d = tempfile.mkdtemp()
target = os.path.join(d, "s.json")
l1 = FileLock(target, timeout=0.2)
l2 = FileLock(target, timeout=0.2)
print("l1.acquire=", l1.acquire())
print("l2.acquire(超时)=", l2.acquire())
l1.release()
print("release 后锁文件存在=", os.path.exists(target + ".lock"))
print("l2.acquire(释放后)=", l2.acquire())
l2.release()

# 陈旧锁
lp = target + ".lock"
with open(lp, "w", encoding="ascii") as f:
    f.write("999999999")
l3 = FileLock(target, timeout=0.5)
print("stale acquire=", l3.acquire())
l3.release()
print("SMOKE OK")
