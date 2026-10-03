"""Pure-stdlib helpers shared by every layer of the companion stack.

This module intentionally has zero third-party imports so the placeholder
backend remains fully runnable on a vanilla Python 3.10+.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from functools import wraps
import hashlib
import hmac
import logging
import os
import re
import threading
import time
from typing import Any, Callable, Iterable, ParamSpec, TypeVar

__all__ = [
    "PermissionDenied",
    "ModuleUnavailableError",
    "safe_filename",
    "safe_relpath",
    "truncate_bytes",
    "truncate_text",
    "retry",
    "rate_limit",
    "sanitize_for_log",
    "thread_local_cache",
    "sha256_hex",
    "constant_time_compare",
    "utc_now_iso",
    "batched",
    "SingletonLock",
]

log = logging.getLogger(__name__)
_P = ParamSpec("_P")
_R = TypeVar("_R")


class PermissionDenied(RuntimeError):
    """Raised when an external-side-effect function is called without the
    explicit ``approved=True`` gate.  Callers should *never* catch this and
    retry silently; the gate must remain visible."""


class ModuleUnavailableError(RuntimeError):
    """Raised when an optional perception / execution extra is not installed.

    Unlike :class:`PermissionDenied`, this error is recoverable: callers
    typically fall back to a placeholder or skip the capability.
    """


_INVALID_FS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_MAX_FS = 160
_PATH_TRAVERSAL = re.compile(r"(?:^|[/\\])\.+(?:[/\\]|$)")


def safe_filename(name: str, fallback: str = "unnamed") -> str:
    """Return a filename safe across Windows / macOS / Linux.

    Empty or fully sanitised inputs fall back to ``fallback`` which is itself
    sanitised.  The result is never longer than ``_MAX_FS`` bytes (UTF-8).
    """
    if not isinstance(name, str):
        return safe_filename(fallback)
    cleaned = _INVALID_FS.sub("_", name).strip().strip(".")
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        cleaned = fallback if isinstance(fallback, str) and fallback else "unnamed"
        cleaned = _INVALID_FS.sub("_", cleaned).strip().strip(".") or "unnamed"
    encoded = cleaned.encode("utf-8")
    if len(encoded) > _MAX_FS:
        encoded = encoded[:_MAX_FS]
        cleaned = encoded.decode("utf-8", errors="ignore")
    return cleaned


def safe_relpath(path: str) -> str:
    """Normalise a user-supplied relative path string or reject it.

    Traversal fragments such as ``..`` and null bytes cause
    :class:`PermissionDenied`.  The result always uses POSIX separators.
    """
    if not isinstance(path, str) or not path.strip():
        raise PermissionDenied("path must be a non-empty string")
    if "\x00" in path:
        raise PermissionDenied("path contains null bytes")
    if _PATH_TRAVERSAL.search(path.replace("\\", "/")):
        raise PermissionDenied("path must not contain traversal segments")
    return path.replace("\\", "/").lstrip("./").strip()


def truncate_bytes(data: bytes, limit: int) -> bytes:
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("data must be bytes-like")
    if limit < 0:
        raise ValueError("limit must be non-negative")
    return bytes(data[:limit])


def truncate_text(text: str, limit: int, ellipsis: str = "…") -> str:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if limit < 0:
        raise ValueError("limit must be non-negative")
    if len(text) <= limit:
        return text
    if limit <= len(ellipsis):
        return ellipsis[:limit]
    return text[: limit - len(ellipsis)] + ellipsis


def retry(
    max_attempts: int = 3,
    delay: float = 0.0,
    backoff: float = 1.0,
    on: tuple[type[BaseException], ...] = (OSError, TimeoutError),
) -> Callable[[Callable[_P, _R]], Callable[_P, _R]]:
    """Retry ``func`` on whitelisted exceptions with optional exponential
    backoff.  Zero-third-party dependencies (``time.sleep`` only)."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    def decorator(func: Callable[_P, _R]) -> Callable[_P, _R]:
        @wraps(func)
        def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            attempt = 0
            sleep_for = float(delay)
            last: BaseException | None = None
            while attempt < max_attempts:
                attempt += 1
                try:
                    return func(*args, **kwargs)
                except on as exc:  # type: ignore[misc]
                    last = exc
                    if attempt >= max_attempts:
                        break
                    log.debug(
                        "%s failed on attempt %d/%d: %s; retrying in %.3fs",
                        getattr(func, "__name__", "callable"),
                        attempt,
                        max_attempts,
                        exc,
                        sleep_for,
                    )
                    if sleep_for > 0:
                        time.sleep(sleep_for)
                    sleep_for *= float(backoff) if backoff > 0 else 1.0
            assert last is not None
            raise last
        return wrapper
    return decorator


@dataclass(frozen=True)
class _RateBucket:
    tokens: float
    reset_at: float


def rate_limit(
    calls: int = 10,
    period: float = 1.0,
) -> Callable[[Callable[_P, _R]], Callable[_P, _R]]:
    """Simple token-bucket rate limiter keyed per decorated callable.

    Thread-safe via a module-level lock.  Does *not* sleep the caller: the
    bucket raises :class:`PermissionDenied` when exhausted so the caller can
    decide whether to defer, queue, or surface a user-visible notice.
    """
    if calls < 1 or period <= 0:
        raise ValueError("calls must be >= 1 and period must be > 0")

    _lock = threading.Lock()
    state: dict[int, _RateBucket] = {}

    def decorator(func: Callable[_P, _R]) -> Callable[_P, _R]:
        key = id(func)

        @wraps(func)
        def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            now = time.monotonic()
            with _lock:
                bucket = state.get(key)
                if bucket is None or now >= bucket.reset_at:
                    bucket = _RateBucket(tokens=float(calls) - 1.0, reset_at=now + period)
                    state[key] = bucket
                elif bucket.tokens >= 1.0:
                    state[key] = _RateBucket(
                        tokens=bucket.tokens - 1.0, reset_at=bucket.reset_at
                    )
                else:
                    raise PermissionDenied(
                        f"rate limit exceeded for {getattr(func, '__name__', 'callable')}: "
                        f"{calls}/{period}s"
                    )
            return func(*args, **kwargs)
        return wrapper
    return decorator


_SECRET_MASK = re.compile(
    r"\b(sk-[A-Za-z0-9_\-]{8,}|Bearer\s+[A-Za-z0-9_\-\.]{8,}|"
    r"api[_-]?key[\"'`]?\s*[:=]\s*[\"'`]?[A-Za-z0-9_\-]{4,})\b",
    re.IGNORECASE,
)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def sanitize_for_log(message: Any, max_len: int = 2000) -> str:
    """Return a log-safe string: masks likely secrets, strips control chars,
    truncates to ``max_len``.  Always succeeds – never raises."""
    try:
        if isinstance(message, (bytes, bytearray)):
            text = message.decode("utf-8", errors="replace")
        else:
            text = str(message)
    except Exception:  # pragma: no cover - defensive
        text = "<unstringifiable value>"
    text = _CONTROL.sub("", text)
    text = _SECRET_MASK.sub("<redacted>", text)
    return truncate_text(text, max_len, ellipsis="…")


_cache_lock = threading.Lock()


def thread_local_cache(max_entries: int = 128) -> Callable[[Callable[_P, _R]], Callable[_P, _R]]:
    """Per-thread memoizer keyed on ``(args, sorted(kwargs.items()))``.

    Intended for hot-path helpers such as path normalisation, not for
    arbitrary model outputs.  The cache is bounded per thread to avoid
    unbounded growth.
    """
    if max_entries < 1:
        raise ValueError("max_entries must be >= 1")
    storage = threading.local()

    def decorator(func: Callable[_P, _R]) -> Callable[_P, _R]:
        @wraps(func)
        def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            with _cache_lock:
                store: dict[Any, _R] | None = getattr(storage, "store", None)
                order: list[Any] | None = getattr(storage, "order", None)
                if store is None:
                    store = {}
                    order = []
                    storage.store = store
                    storage.order = order
            assert store is not None and order is not None
            try:
                key = (args, tuple(sorted(kwargs.items())))
                hash(key)
            except TypeError:
                return func(*args, **kwargs)
            with _cache_lock:
                if key in store:
                    order.remove(key)
                    order.append(key)
                    return store[key]
            result = func(*args, **kwargs)
            with _cache_lock:
                if key in store:
                    try:
                        order.remove(key)
                    except ValueError:
                        pass
                store[key] = result
                order.append(key)
                while len(order) > max_entries:
                    evict = order.pop(0)
                    store.pop(evict, None)
            return result
        return wrapper
    return decorator


def sha256_hex(data: bytes | bytearray | memoryview | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(bytes(data)).hexdigest()


def constant_time_compare(a: str, b: str) -> bool:
    """Timing-safe equality for tokens/keys.  Accepts strings (UTF-8 bytes)."""
    if not isinstance(a, str) or not isinstance(b, str):
        return False
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def batched(iterable: Iterable[_R], size: int) -> Iterable[list[_R]]:
    """Backport of ``itertools.batched`` (Python 3.12) for 3.10 support."""
    if size < 1:
        raise ValueError("size must be >= 1")
    batch: list[_R] = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


class SingletonLock:
    """Context manager + reusable lock wrapper used by CharacterStore and
    MemoryStore so we can replace its backend (e.g. for process-level
    file-backed locking) in one place without touching call sites."""

    def __init__(self) -> None:
        self._lock = threading.RLock()

    def __enter__(self) -> "SingletonLock":
        self._lock.acquire()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self._lock.release()
