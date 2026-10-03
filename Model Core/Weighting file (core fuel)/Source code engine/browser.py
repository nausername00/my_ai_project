"""L4 execution – browser automation with a hard permission gate.

Public API pattern: every operation takes ``approved`` first (``False`` by
default), raises :class:`utils.PermissionDenied` if not granted, and only
then lazily imports Playwright/Selenium.  The module also enforces a
hostname allow-list (``allowed_hosts``) – empty list = block all – so a
rogue planner call can never unexpectedly exfiltrate data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib.util import find_spec
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlparse

from utils import ModuleUnavailableError, PermissionDenied, SingletonLock, truncate_text

__all__ = [
    "BrowserAutomation",
    "BrowserAutomationError",
    "ClickedElement",
    "ScreenshotResult",
    "allowed_host",
    "browser_click",
    "browser_fill",
    "browser_goto",
    "browser_screenshot",
    "browser_text_content",
]


class BrowserAutomationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ScreenshotResult:
    url: str
    bytes_length: int
    path: str | None
    title: str
    captured_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "bytes_length": int(self.bytes_length),
            "path": self.path,
            "title": self.title,
            "captured_at": self.captured_at,
        }


@dataclass(frozen=True)
class ClickedElement:
    selector: str
    url_after: str
    clicked_at: str

    def to_dict(self) -> dict[str, Any]:
        return {"selector": self.selector, "url_after": self.url_after, "clicked_at": self.clicked_at}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _gate(op: str, approved: bool, purpose: str | None) -> None:
    if not approved:
        detail = purpose and f"（目的：{purpose}）" or ""
        raise PermissionDenied(
            f"用户尚未授权浏览器操作 '{op}'{detail}。请显式传入 approved=True。"
        )


def allowed_host(url: str, allowed_hosts: Iterable[str]) -> bool:
    """Return ``True`` if the hostname of ``url`` is on the allow-list.

    The allow-list supports either exact hostnames or ``.foo.com`` prefix
    wildcard (matches any subdomain of ``foo.com`` *and* ``foo.com``
    itself).  An empty ``allowed_hosts`` list denies every URL.
    """
    if not url:
        return False
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    if not host:
        return False
    allowed = [str(h).lower() for h in allowed_hosts]
    if host in allowed:
        return True
    for entry in allowed:
        if entry.startswith("."):
            if host == entry[1:] or host.endswith(entry):
                return True
        elif entry.startswith("*."):
            suffix = entry[1:]  # .foo.com
            if host.endswith(suffix):
                return True
    return False


def _enforce_host(url: str, allowed_hosts: Iterable[str]) -> None:
    if not allowed_host(url, allowed_hosts):
        raise PermissionDenied(
            f"URL 不在浏览器域名白名单：{truncate_text(url, 240, '')}\n"
            f"允许列表：{list(allowed_hosts)!r}"
        )


def _require_playwright() -> Any:
    if find_spec("playwright") is None:
        raise ModuleUnavailableError(
            "BrowserAutomation 需要 playwright；请安装 execution extra:  pip install .[execution]"
        )
    import importlib
    return importlib.import_module("playwright.sync_api")


# ---------------------------------------------------------------------------
# Stateless function API (playwright only for now; selenium adapter TBD)
# ---------------------------------------------------------------------------

def _pw_open(url: str, allowed_hosts: Iterable[str], headless: bool):
    pw_api = _require_playwright()
    pw = pw_api.sync_playwright().start()
    browser = pw.chromium.launch(headless=bool(headless))
    context = browser.new_context(locale="zh-CN")
    page = context.new_page()
    _enforce_host(url, allowed_hosts)
    page.goto(url, wait_until="domcontentloaded")
    return pw, browser, context, page


def _close_all(pw, browser, context) -> None:
    try:
        context.close()
    except Exception:
        pass
    try:
        browser.close()
    except Exception:
        pass
    try:
        pw.stop()
    except Exception:
        pass


def browser_goto(
    url: str,
    *,
    approved: bool = False,
    purpose: str | None = None,
    allowed_hosts: Iterable[str] = (),
    headless: bool = True,
) -> dict[str, Any]:
    _gate("browser_goto", approved, purpose)
    pw = browser = context = page = None
    try:
        pw, browser, context, page = _pw_open(url, allowed_hosts, headless)
        title = page.title() or ""
        current = page.url
    except PermissionDenied:
        raise
    except ModuleUnavailableError:
        raise
    except Exception as exc:
        raise BrowserAutomationError(f"browser_goto failed: {exc}") from exc
    finally:
        _close_all(pw, browser, context)
    return {
        "url_after": current,
        "title": title,
        "approved": True,
        "purpose": str(purpose or ""),
    }


def browser_screenshot(
    url: str,
    *,
    approved: bool = False,
    purpose: str | None = None,
    allowed_hosts: Iterable[str] = (),
    headless: bool = True,
    save_path: Any | None = None,
    full_page: bool = True,
) -> ScreenshotResult:
    _gate("browser_screenshot", approved, purpose)
    pw = browser = context = page = None
    try:
        pw, browser, context, page = _pw_open(url, allowed_hosts, headless)
        from utils import utc_now_iso, safe_filename
        img_bytes = page.screenshot(full_page=bool(full_page), type="png")
        title = page.title() or ""
        current = page.url
    except PermissionDenied:
        raise
    except ModuleUnavailableError:
        raise
    except Exception as exc:
        raise BrowserAutomationError(f"browser_screenshot failed: {exc}") from exc
    finally:
        _close_all(pw, browser, context)
    target_path: str | None = None
    if save_path is not None:
        from pathlib import Path
        p = Path(save_path).expanduser().resolve()
        if p.suffix.lower() != ".png":
            p = p / safe_filename(f"browser_{utc_now_iso().replace(':','-')}.png")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(img_bytes)
        target_path = p.as_posix()
    return ScreenshotResult(
        url=current,
        bytes_length=len(img_bytes),
        path=target_path,
        title=title,
        captured_at=utc_now_iso(),
    )


def browser_click(
    url: str,
    selector: str,
    *,
    approved: bool = False,
    purpose: str | None = None,
    allowed_hosts: Iterable[str] = (),
    headless: bool = True,
) -> ClickedElement:
    _gate("browser_click", approved, purpose)
    pw = browser = context = page = None
    try:
        pw, browser, context, page = _pw_open(url, allowed_hosts, headless)
        from utils import utc_now_iso
        page.click(str(selector))
        page.wait_for_load_state("domcontentloaded")
        after = page.url
    except PermissionDenied:
        raise
    except ModuleUnavailableError:
        raise
    except Exception as exc:
        raise BrowserAutomationError(f"browser_click failed: {exc}") from exc
    finally:
        _close_all(pw, browser, context)
    return ClickedElement(selector=str(selector), url_after=after, clicked_at=utc_now_iso())


def browser_fill(
    url: str,
    selector: str,
    value: str,
    *,
    approved: bool = False,
    purpose: str | None = None,
    allowed_hosts: Iterable[str] = (),
    headless: bool = True,
    submit: bool = False,
) -> dict[str, Any]:
    _gate("browser_fill", approved, purpose)
    pw = browser = context = page = None
    try:
        pw, browser, context, page = _pw_open(url, allowed_hosts, headless)
        from utils import utc_now_iso
        page.fill(str(selector), str(value))
        if submit:
            page.press(str(selector), "Enter")
            try:
                page.wait_for_load_state("domcontentloaded")
            except Exception:
                pass
        after = page.url
    except PermissionDenied:
        raise
    except ModuleUnavailableError:
        raise
    except Exception as exc:
        raise BrowserAutomationError(f"browser_fill failed: {exc}") from exc
    finally:
        _close_all(pw, browser, context)
    return {
        "selector": str(selector),
        "filled_length": len(str(value)),
        "submit": bool(submit),
        "url_after": after,
        "approved": True,
        "purpose": str(purpose or ""),
    }


def browser_text_content(
    url: str,
    selector: str = "body",
    *,
    approved: bool = False,
    purpose: str | None = None,
    allowed_hosts: Iterable[str] = (),
    headless: bool = True,
    limit_chars: int = 12000,
) -> dict[str, Any]:
    _gate("browser_text_content", approved, purpose)
    pw = browser = context = page = None
    try:
        pw, browser, context, page = _pw_open(url, allowed_hosts, headless)
        text = page.text_content(str(selector)) or ""
        after = page.url
    except PermissionDenied:
        raise
    except ModuleUnavailableError:
        raise
    except Exception as exc:
        raise BrowserAutomationError(f"browser_text_content failed: {exc}") from exc
    finally:
        _close_all(pw, browser, context)
    return {
        "selector": str(selector),
        "text": truncate_text(text, int(limit_chars), ""),
        "url_after": after,
        "approved": True,
        "purpose": str(purpose or ""),
    }


# ---------------------------------------------------------------------------
# Stateful facade – keeps the browser open across multiple calls
# ---------------------------------------------------------------------------

class BrowserAutomation:
    """Reusable session object.  Permission is still checked per-call via
    ``approved`` or the constructor ``session_approved`` +
    ``session_allowed_hosts`` combo.
    """

    def __init__(
        self,
        *,
        approved: bool = False,
        session_purpose: str | None = None,
        session_allowed_hosts: Iterable[str] = (),
        headless: bool = True,
    ) -> None:
        self.session_approved = bool(approved)
        self.session_purpose = str(session_purpose or "")
        self.session_allowed_hosts = tuple(session_allowed_hosts)
        self.headless = bool(headless)
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
        self._lock = SingletonLock()

    # -- lifecycle --------------------------------------------------------
    def open(self, url: str, *, approved: bool | None = None, purpose: str | None = None):
        ok = bool(approved) or (self.session_approved and "goto" in {"goto"})
        self._ensure_open()
        _gate("BrowserAutomation.open", ok, purpose or self.session_purpose)
        hosts = self.session_allowed_hosts
        _enforce_host(url, hosts)
        with self._lock:
            self._page.goto(url, wait_until="domcontentloaded")
            return {"url_after": self._page.url, "title": self._page.title() or ""}

    def _ensure_open(self) -> None:
        if self._page is not None:
            return
        with self._lock:
            if self._page is not None:
                return
            pw_api = _require_playwright()
            self._pw = pw_api.sync_playwright().start()
            self._browser = self._pw.chromium.launch(headless=self.headless)
            self._context = self._browser.new_context(locale="zh-CN")
            self._page = self._context.new_page()

    def close(self) -> None:
        with self._lock:
            _close_all(self._pw, self._browser, self._context)
            self._pw = self._browser = self._context = self._page = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    # -- operation wrappers ----------------------------------------------
    def _approved(self, explicit: bool | None, tool: str) -> bool:
        return bool(explicit) or (self.session_approved and tool in {"screenshot","click","fill","text"})

    def screenshot(self, *, approved: bool | None = None, purpose: str | None = None, save_path=None, full_page: bool = True) -> ScreenshotResult:
        _gate("BrowserAutomation.screenshot", self._approved(approved, "screenshot"), purpose or self.session_purpose)
        from utils import utc_now_iso, safe_filename
        with self._lock:
            self._ensure_open()
            data = self._page.screenshot(full_page=full_page, type="png")
            url = self._page.url
            title = self._page.title() or ""
        target: str | None = None
        if save_path is not None:
            from pathlib import Path
            p = Path(save_path).expanduser().resolve()
            if p.suffix.lower() != ".png":
                p = p / safe_filename(f"session_{utc_now_iso().replace(':','-')}.png")
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
            target = p.as_posix()
        return ScreenshotResult(url=url, bytes_length=len(data), path=target, title=title, captured_at=utc_now_iso())

    def click(self, selector: str, *, approved: bool | None = None, purpose: str | None = None) -> ClickedElement:
        _gate("BrowserAutomation.click", self._approved(approved, "click"), purpose or self.session_purpose)
        from utils import utc_now_iso
        with self._lock:
            self._ensure_open()
            self._page.click(str(selector))
            try:
                self._page.wait_for_load_state("domcontentloaded")
            except Exception:
                pass
            after = self._page.url
        return ClickedElement(selector=str(selector), url_after=after, clicked_at=utc_now_iso())

    def fill(self, selector: str, value: str, *, approved: bool | None = None, purpose: str | None = None, submit: bool = False) -> dict[str, Any]:
        _gate("BrowserAutomation.fill", self._approved(approved, "fill"), purpose or self.session_purpose)
        with self._lock:
            self._ensure_open()
            self._page.fill(str(selector), str(value))
            if submit:
                self._page.press(str(selector), "Enter")
                try:
                    self._page.wait_for_load_state("domcontentloaded")
                except Exception:
                    pass
            after = self._page.url
        return {"selector": str(selector), "filled_length": len(str(value)), "submit": submit, "url_after": after}

    def text(self, selector: str = "body", *, approved: bool | None = None, purpose: str | None = None, limit: int = 12000) -> dict[str, Any]:
        _gate("BrowserAutomation.text", self._approved(approved, "text"), purpose or self.session_purpose)
        with self._lock:
            self._ensure_open()
            txt = self._page.text_content(str(selector)) or ""
            after = self._page.url
        return {"selector": str(selector), "text": truncate_text(txt, int(limit), ""), "url_after": after}
