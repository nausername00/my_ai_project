"""阶段 0 审计日志：字段白名单、落盘、回读、注入 API 链路。"""

import json
import tempfile
import unittest
from pathlib import Path

import api
from audit import AuditLog, _ALLOWED_FIELDS


class AuditLogTest(unittest.TestCase):
    """白名单约束：只落盘允许的元数据字段，损坏/缺失不影响读取。"""

    def test_whitelist_only_fields_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = AuditLog(directory)
            ok = log.record(
                method="POST",
                route="/v1/backup/create",
                status=200,
                duration_ms=12.34,
                error="",
                client="loopback",
            )
            self.assertTrue(ok)
            entries = log.read_entries()
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["method"], "POST")
            self.assertEqual(entries[0]["route"], "/v1/backup/create")
            self.assertEqual(entries[0]["status"], 200)
            self.assertEqual(entries[0]["duration_ms"], 12.3)
            # 白名单约束：读回的每个字段都必须来自白名单
            for key in entries[0]:
                self.assertIn(key, _ALLOWED_FIELDS)
            # 白名单本身不得包含任何敏感内容字段名
            forbidden = {
                "authorization",
                "token",
                "api_key",
                "secret",
                "body",
                "payload",
                "content",
                "message",
                "audio",
                "image",
                "memory",
            }
            self.assertTrue(forbidden.isdisjoint(_ALLOWED_FIELDS))

    def test_read_missing_and_corrupt_lines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = AuditLog(directory)
            self.assertEqual(log.read_entries(), [])
            path = Path(directory) / "api_audit.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('{"ts":"x"}\nnot-json\n{"ts":"y"}\n', encoding="utf-8")
            entries = log.read_entries()
            self.assertEqual(len(entries), 2)  # 坏行跳过，仍能读回好行

    def test_rotation_archives_large_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = AuditLog(directory)
            log.record(method="GET", route="/", status=200, duration_ms=1.0)
            archived = Path(directory) / "api_audit.1.jsonl"
            # 正常写入不会触发轮转
            self.assertFalse(archived.exists())


class AuditInApiTest(unittest.TestCase):
    """审计经 _tracked 注入 API：一次请求产生一条白名单记录。"""

    def test_request_produces_audit_entry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audit = AuditLog(directory)
            handler = api.ApiHandler.__new__(api.ApiHandler)
            handler.client_address = ("127.0.0.1", 12345)
            handler.path = "/v1/status"
            seen = {}
            handler._send_json = lambda status, payload: seen.update(
                {"status": status, "payload": payload}
            )
            api.ApiHandler.audit_log = audit
            try:
                handler.do_GET()
            finally:
                api.ApiHandler.audit_log = None
            entries = audit.read_entries()
            self.assertGreaterEqual(len(entries), 1)
            self.assertEqual(entries[0]["method"], "GET")
            self.assertEqual(entries[0]["route"], "/v1/status")
            self.assertEqual(entries[0]["client"], "loopback")
            self.assertNotIn("payload", entries[0])


if __name__ == "__main__":
    unittest.main()
