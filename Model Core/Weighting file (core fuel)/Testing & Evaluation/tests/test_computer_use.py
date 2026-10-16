"""D 层测试补全 · computer_use（接口级）：授权门、沙箱 shell 白名单、超时/取消、结果结构。

不驱动真实鼠标/键盘/GUI；只验证安全门、白名单与进程执行契约。
"""

import threading
import unittest

from computer_use import (
    DesktopAutomationError,
    ExecutedProcess,
    PermissionDenied,
    _SAFE_COMMANDS,
    _gate,
    run_sandboxed_shell,
)


class GateTest(unittest.TestCase):
    def test_unapproved_raises(self) -> None:
        with self.assertRaises(PermissionDenied):
            _gate("shell", approved=False, purpose=None)

    def test_unapproved_with_purpose(self) -> None:
        with self.assertRaises(PermissionDenied) as ctx:
            _gate("shell", approved=False, purpose="测试目的")
        self.assertIn("测试目的", str(ctx.exception))

    def test_approved_passes(self) -> None:
        _gate("shell", approved=True, purpose=None)  # no raise


class SafeCommandsTest(unittest.TestCase):
    def test_safe_commands_contain_expected(self) -> None:
        for cmd in ("echo", "dir", "ls", "where", "which", "python", "py", "node", "git"):
            self.assertIn(cmd, _SAFE_COMMANDS)

    def test_dangerous_not_whitelisted(self) -> None:
        for cmd in ("rmdir", "del", "rm", "format", "shutdown", "taskkill", "powershell"):
            self.assertNotIn(cmd, _SAFE_COMMANDS)


class SandboxedShellTest(unittest.TestCase):
    def test_unapproved_rejected_before_run(self) -> None:
        with self.assertRaises(PermissionDenied):
            run_sandboxed_shell(["echo", "hi"], approved=False)

    def test_empty_command_rejected(self) -> None:
        with self.assertRaises(DesktopAutomationError):
            run_sandboxed_shell([], approved=True)

    def test_non_whitelisted_command_rejected(self) -> None:
        with self.assertRaises(PermissionDenied) as ctx:
            run_sandboxed_shell(["rmdir", "x"], approved=True)
        self.assertIn("rmdir", str(ctx.exception))

    def test_echo_runs_and_returns_result(self) -> None:
        result = run_sandboxed_shell(
            ["py", "-c", "print('hello-moling')"], approved=True, timeout_seconds=10
        )
        self.assertIsInstance(result, ExecutedProcess)
        self.assertEqual(result.returncode, 0)
        self.assertIn("hello-moling", result.stdout)
        self.assertGreaterEqual(result.duration_ms, 0)

    def test_result_to_dict_shape(self) -> None:
        result = run_sandboxed_shell(
            ["py", "-c", "print('shape-check')"], approved=True, timeout_seconds=10
        )
        data = result.to_dict()
        for key in ("command", "returncode", "stdout", "stderr", "duration_ms",
                    "killed", "timed_out", "cancelled"):
            self.assertIn(key, data)

    def test_string_command_supported(self) -> None:
        result = run_sandboxed_shell(
            "py -c print('string-mode-ok')", approved=True, timeout_seconds=10
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("string-mode-ok", result.stdout)

    def test_cancel_event_short_circuits(self) -> None:
        cancel = threading.Event()
        cancel.set()
        result = run_sandboxed_shell(
            ["py", "-c", "print('x')"], approved=True,
            timeout_seconds=10, cancel_event=cancel,
        )
        self.assertTrue(result.cancelled)
        self.assertEqual(result.returncode, -1)

    def test_timeout_kills(self) -> None:
        result = run_sandboxed_shell(
            ["py", "-c", "import time; time.sleep(30)"],
            approved=True,
            timeout_seconds=1,
        )
        self.assertTrue(result.timed_out)
        self.assertTrue(result.killed)
        self.assertNotEqual(result.returncode, 0)

    def test_custom_safe_commands_extend_whitelist(self) -> None:
        result = run_sandboxed_shell(
            ["py", "-c", "print('custom-ok')"],
            approved=True,
            timeout_seconds=10,
            safe_commands=list(_SAFE_COMMANDS) + ["py"],
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("custom-ok", result.stdout)


if __name__ == "__main__":
    unittest.main()
