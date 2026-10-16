"""D 层测试补全 · utils：文件名安全、路径穿越、截断、重试、限流、日志清洗、哈希、批量、单例锁、线程缓存。"""

import threading
import time
import unittest

from utils import (
    PermissionDenied,
    SingletonLock,
    batched,
    constant_time_compare,
    rate_limit,
    retry,
    safe_filename,
    safe_relpath,
    sanitize_for_log,
    sha256_hex,
    thread_local_cache,
    truncate_bytes,
    truncate_text,
)


class SafeFilenameTest(unittest.TestCase):
    def test_invalid_chars_replaced(self) -> None:
        name = safe_filename('a/b\\c:d*e?f"g<h>i|j')
        self.assertNotIn("/", name)
        self.assertNotIn(":", name)
        self.assertNotIn("*", name)

    def test_empty_falls_back(self) -> None:
        self.assertEqual(safe_filename(""), "unnamed")
        self.assertEqual(safe_filename("   "), "unnamed")
        self.assertEqual(safe_filename("..."), "unnamed")

    def test_non_string_falls_back(self) -> None:
        self.assertEqual(safe_filename(12345), "unnamed")

    def test_whitespace_collapsed(self) -> None:
        self.assertEqual(safe_filename("  hello    world  "), "hello world")

    def test_length_limited(self) -> None:
        name = safe_filename("长" * 500)
        self.assertLessEqual(len(name.encode("utf-8")), 255)


class SafeRelpathTest(unittest.TestCase):
    def test_normal_path_normalised(self) -> None:
        self.assertEqual(safe_relpath("docs/guide.md"), "docs/guide.md")
        self.assertEqual(safe_relpath("src\\main.py"), "src/main.py")

    def test_traversal_rejected(self) -> None:
        for bad in ("../secret", "a/../../etc", "..\\win"):
            with self.assertRaises(PermissionDenied):
                safe_relpath(bad)

    def test_null_byte_rejected(self) -> None:
        with self.assertRaises(PermissionDenied):
            safe_relpath("a\x00b")

    def test_empty_rejected(self) -> None:
        with self.assertRaises(PermissionDenied):
            safe_relpath("")
        with self.assertRaises(PermissionDenied):
            safe_relpath("   ")


class TruncateTest(unittest.TestCase):
    def test_truncate_bytes(self) -> None:
        self.assertEqual(truncate_bytes(b"abcdef", 3), b"abc")
        self.assertEqual(truncate_bytes(b"abc", 10), b"abc")
        with self.assertRaises(ValueError):
            truncate_bytes(b"a", -1)
        with self.assertRaises(TypeError):
            truncate_bytes("abc", 3)  # type: ignore[arg-type]

    def test_truncate_text(self) -> None:
        self.assertEqual(truncate_text("你好世界", 2), "你…")
        self.assertEqual(truncate_text("abc", 5), "abc")
        self.assertEqual(truncate_text("abcdef", 3, "..."), "...")
        with self.assertRaises(ValueError):
            truncate_text("a", -1)


class RetryTest(unittest.TestCase):
    def test_success_first_attempt(self) -> None:
        calls = []

        @retry(max_attempts=3)
        def work() -> str:
            calls.append(1)
            return "ok"

        self.assertEqual(work(), "ok")
        self.assertEqual(len(calls), 1)

    def test_retries_then_succeeds(self) -> None:
        calls = []

        @retry(max_attempts=3, delay=0)
        def work() -> str:
            calls.append(1)
            if len(calls) < 3:
                raise OSError("transient")
            return "done"

        self.assertEqual(work(), "done")
        self.assertEqual(len(calls), 3)

    def test_exhausted_raises_last(self) -> None:
        calls = []

        @retry(max_attempts=2, delay=0)
        def work() -> str:
            calls.append(1)
            raise OSError("always")

        with self.assertRaises(OSError):
            work()
        self.assertEqual(len(calls), 2)

    def test_non_whitelisted_exception_not_retried(self) -> None:
        calls = []

        @retry(max_attempts=3, on=(OSError,))
        def work() -> str:
            calls.append(1)
            raise ValueError("not retried")

        with self.assertRaises(ValueError):
            work()
        self.assertEqual(len(calls), 1)

    def test_invalid_max_attempts(self) -> None:
        with self.assertRaises(ValueError):
            retry(max_attempts=0)


class RateLimitTest(unittest.TestCase):
    def test_allows_burst_within_budget(self) -> None:
        calls = []

        @rate_limit(calls=2, period=60.0)
        def work() -> str:
            calls.append(1)
            return "ok"

        work()
        work()
        self.assertEqual(len(calls), 2)
        with self.assertRaises(PermissionDenied):
            work()
        self.assertEqual(len(calls), 2)

    def test_invalid_params(self) -> None:
        with self.assertRaises(ValueError):
            rate_limit(calls=0)
        with self.assertRaises(ValueError):
            rate_limit(period=0)


class SanitizeLogTest(unittest.TestCase):
    def test_string_shortened(self) -> None:
        long_text = "x" * 3000
        out = sanitize_for_log(long_text, max_len=100)
        self.assertLessEqual(len(out), 100 + 3)

    def test_non_string_serialised(self) -> None:
        out = sanitize_for_log({"a": 1}, max_len=100)
        self.assertIn("a", out)

    def test_sensitive_literal_masked(self) -> None:
        out = sanitize_for_log("api_key=abc123secret secret", max_len=200)
        self.assertNotIn("abc123secret", out)
        self.assertIn("redacted", out)

    def test_bearer_token_masked(self) -> None:
        out = sanitize_for_log("Authorization: Bearer abcdefgh12345678", max_len=200)
        self.assertNotIn("abcdefgh12345678", out)


class HashCompareTest(unittest.TestCase):
    def test_sha256_hex(self) -> None:
        self.assertEqual(len(sha256_hex(b"data")), 64)
        self.assertEqual(sha256_hex("文本"), sha256_hex("文本"))

    def test_constant_time_compare(self) -> None:
        self.assertTrue(constant_time_compare("abc", "abc"))
        self.assertFalse(constant_time_compare("abc", "abd"))
        self.assertFalse(constant_time_compare("abc", "abcd"))


class BatchedTest(unittest.TestCase):
    def test_batches(self) -> None:
        self.assertEqual(list(batched([1, 2, 3, 4, 5], 2)), [[1, 2], [3, 4], [5]])
        self.assertEqual(list(batched([], 3)), [])
        self.assertEqual(list(batched([1], 10)), [[1]])

    def test_invalid_size(self) -> None:
        with self.assertRaises(ValueError):
            list(batched([1], 0))


class SingletonLockTest(unittest.TestCase):
    def test_serialises_access(self) -> None:
        lock = SingletonLock()
        order: list[str] = []

        def worker(tag: str) -> None:
            with lock:
                order.append(tag + "-in")
                time.sleep(0.05)
                order.append(tag + "-out")

        threads = [threading.Thread(target=worker, args=(t,)) for t in ("a", "b")]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(order, ["a-in", "a-out", "b-in", "b-out"])


class ThreadLocalCacheTest(unittest.TestCase):
    def test_caches_per_thread(self) -> None:
        cache = thread_local_cache(max_entries=2)

        @cache
        def compute(key: str) -> str:
            return f"v-{key}"

        self.assertEqual(compute("a"), "v-a")
        self.assertEqual(compute("a"), "v-a")  # cached


if __name__ == "__main__":
    unittest.main()
