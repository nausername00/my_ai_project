"""D 层测试补全 · browser（接口级）：域名白名单、授权门、结果结构。

不实跑 playwright（外部依赖）；只测纯函数、权限门与数据结构契约。
"""

import unittest
from unittest.mock import patch

from browser import (
    ClickedElement,
    PermissionDenied,
    ScreenshotResult,
    _enforce_host,
    _gate,
    allowed_host,
)


class AllowedHostTest(unittest.TestCase):
    def test_exact_host(self) -> None:
        self.assertTrue(allowed_host("https://example.com/page", ["example.com"]))
        self.assertTrue(allowed_host("http://example.com:8080/x", ["example.com"]))

    def test_case_insensitive(self) -> None:
        self.assertTrue(allowed_host("https://EXAMPLE.com", ["example.com"]))
        self.assertTrue(allowed_host("https://example.com", ["EXAMPLE.com"]))

    def test_subdomain_wildcard_dot(self) -> None:
        self.assertTrue(allowed_host("https://blog.example.com/x", [".example.com"]))
        self.assertTrue(allowed_host("https://example.com", [".example.com"]))

    def test_asterisk_wildcard(self) -> None:
        self.assertTrue(allowed_host("https://a.b.example.com", ["*.example.com"]))

    def test_other_domain_rejected(self) -> None:
        self.assertFalse(allowed_host("https://evil.com", ["example.com"]))
        self.assertFalse(allowed_host("https://example.org", [".example.com"]))

    def test_empty_url_rejected(self) -> None:
        self.assertFalse(allowed_host("", ["example.com"]))
        self.assertFalse(allowed_host("not a url", ["example.com"]))

    def test_empty_allowlist_denies_all(self) -> None:
        self.assertFalse(allowed_host("https://example.com", []))

    def test_bare_host_without_scheme(self) -> None:
        self.assertFalse(allowed_host("example.com", ["example.com"]))
        self.assertFalse(allowed_host("example.com/x", ["example.com"]))


class EnforceHostTest(unittest.TestCase):
    def test_allowed_passes(self) -> None:
        _enforce_host("https://example.com", ["example.com"])  # no raise

    def test_denied_raises(self) -> None:
        with self.assertRaises(PermissionDenied) as ctx:
            _enforce_host("https://other.net", ["example.com"])
        self.assertIn("白名单", str(ctx.exception))


class GateTest(unittest.TestCase):
    def test_unapproved_raises(self) -> None:
        with self.assertRaises(PermissionDenied):
            _gate("browser_open", approved=False, purpose=None)

    def test_approved_passes(self) -> None:
        _gate("browser_open", approved=True, purpose=None)


class ResultStructureTest(unittest.TestCase):
    def test_screenshot_result_to_dict(self) -> None:
        result = ScreenshotResult(
            url="https://example.com/shot",
            bytes_length=4096,
            path="C:\\shot.png",
            title="页面标题",
            captured_at="2026-10-16T00:00:00Z",
        )
        data = result.to_dict()
        self.assertEqual(data["url"], "https://example.com/shot")
        self.assertEqual(data["bytes_length"], 4096)
        self.assertEqual(data["path"], "C:\\shot.png")
        self.assertEqual(data["title"], "页面标题")

    def test_clicked_element_to_dict(self) -> None:
        result = ClickedElement(
            selector="#btn",
            url_after="https://example.com/after",
            clicked_at="2026-10-16T00:00:00Z",
        )
        data = result.to_dict()
        self.assertEqual(data["selector"], "#btn")
        self.assertEqual(data["url_after"], "https://example.com/after")


class AutomationApprovalTest(unittest.TestCase):
    def test_unapproved_open_rejected(self) -> None:
        from browser import BrowserAutomation

        automator = BrowserAutomation(session_allowed_hosts=["example.com"])
        with patch.object(automator, "_ensure_open", lambda: None):
            with self.assertRaises(PermissionDenied):
                automator.open("https://example.com", approved=False)

    def test_host_outside_allowlist_rejected(self) -> None:
        from browser import BrowserAutomation

        automator = BrowserAutomation(approved=True, session_allowed_hosts=["example.com"])
        with patch.object(automator, "_ensure_open", lambda: None):
            with self.assertRaises(PermissionDenied):
                automator.open("https://other.net", approved=True)

    def test_allowed_host_passes_gate(self) -> None:
        from browser import BrowserAutomation

        automator = BrowserAutomation(approved=True, session_allowed_hosts=["example.com"])
        with patch.object(automator, "_ensure_open", lambda: None):
            with patch.object(automator, "_page") as page:
                page.goto.return_value = None
                page.url = "https://example.com/"
                page.title.return_value = "标题"
                result = automator.open("https://example.com", approved=True)
        self.assertEqual(result["title"], "标题")


if __name__ == "__main__":
    unittest.main()
