"""L0 / L2 helper – retrieval engine abstraction for project knowledge
(generic RAG primitive).  Long-term memory in :mod:`memory` uses a
lighter-weight, hand-built BM25-lite; this module is the *general* adapter
that can additionally consume project folders, notes, or external document
stores.

Placeholder-first
-----------------
The default engine (``KeywordRetrievalEngine``) runs on pure-stdlib TF/IDF
with word tokenisation + stop-words, so it works with zero extra packages.
Optional dense retrievers can plug in later via the same protocol and are
imported lazily, raising :class:`utils.ModuleUnavailableError` if the
``retrieval`` extra isn't installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections import Counter
from importlib.util import find_spec
import json
import math
import os
import re
from pathlib import Path
from threading import RLock
from typing import Any, Iterable, Mapping, Sequence

from utils import (
    ModuleUnavailableError,
    SingletonLock,
    safe_relpath,
    truncate_text,
    utc_now_iso,
)

__all__ = [
    "Chunk",
    "KeywordRetrievalEngine",
    "RetrievalError",
    "RetrievalEngine",
    "SearchHit",
    "ingest_path",
]


TEXT_SUFFIXES = frozenset(
    {
        ".py", ".md", ".txt", ".rst", ".json", ".yaml", ".yml",
        ".toml", ".ini", ".cfg", ".js", ".ts", ".tsx", ".jsx",
        ".c", ".h", ".cpp", ".cc", ".hpp", ".rs", ".go", ".java",
        ".cs", ".rb", ".php", ".sh", ".ps1", ".html", ".css",
    }
)
IGNORED_DIRS = frozenset({".git", ".venv", "venv", "__pycache__", "node_modules", ".idea", ".vscode", "dist", "build"})
STOPWORDS_EN = {
    "the", "a", "an", "and", "or", "but", "if", "then", "of", "to", "in",
    "on", "for", "with", "by", "is", "are", "be", "been", "being", "that",
    "this", "these", "those", "it", "as", "at", "from", "into", "about",
}
STOPWORDS_ZH = {"的", "了", "在", "是", "我", "你", "他", "她", "它", "和", "就", "也", "都", "要", "会", "能", "有"}
STOPWORDS = STOPWORDS_EN | STOPWORDS_ZH


class RetrievalError(RuntimeError):
    """Generic retrieval failure (IO / parse / incompatible shape)."""


@dataclass(frozen=True)
class Chunk:
    id: str
    source: str
    text: str
    kind: str = "text"
    tags: tuple = ()
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "text": self.text,
            "kind": self.kind,
            "tags": list(self.tags),
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class SearchHit:
    chunk: Chunk
    score: float
    matched_terms: tuple = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk": self.chunk.to_dict(),
            "score": round(float(self.score), 4),
            "matched_terms": list(self.matched_terms),
        }


# ---------------------------------------------------------------------------
# Tokenisation helpers (pure stdlib)
# ---------------------------------------------------------------------------

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-]{2,}|[\u4e00-\u9fff]{2,}|[0-9][0-9\-]{2,}")


def tokenize(text: str) -> list[str]:
    if not text:
        return []
    lowered = text.casefold()
    tokens: list[str] = []
    for m in _WORD_RE.finditer(lowered):
        t = m.group(0).strip("_-")
        if len(t) >= 2 and t not in STOPWORDS:
            tokens.append(t)
    return tokens


def _chunk_text(text: str, *, max_chars: int = 1000, overlap: int = 160) -> list[str]:
    if not isinstance(max_chars, int) or max_chars < 120:
        raise RetrievalError("max_chars must be >= 120")
    overlap = max(0, min(overlap, max_chars // 2))
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    out: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        out.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return out


# ---------------------------------------------------------------------------
# Ingestion helpers
# ---------------------------------------------------------------------------

def ingest_path(
    root: str | Path,
    *,
    allowed_suffixes: Iterable[str] | None = None,
    ignored_dirs: Iterable[str] | None = None,
    max_chars: int = 1000,
    limit_files: int = 2000,
) -> list[Chunk]:
    """Walk ``root`` and return text chunks suitable for
    :meth:`RetrievalEngine.ingest_many`.

    Only *readable* text files are visited; binary or non-UTF-8 content is
    skipped silently so ingestion never crashes on a random repo.
    """
    root_path = Path(root).expanduser().resolve()
    if not root_path.exists():
        raise RetrievalError(f"root not found: {root_path.as_posix()}")
    suffixes = {s.lower() for s in (allowed_suffixes or TEXT_SUFFIXES)}
    skip_dirs = set(ignored_dirs or IGNORED_DIRS)
    results: list[Chunk] = []
    scanned = 0
    # Choose iteration order so directory walks are deterministic on Windows.
    file_paths: list[Path] = []
    if root_path.is_file():
        file_paths.append(root_path)
    else:
        for base, dirs, files in os.walk(root_path):
            dirs[:] = sorted(d for d in dirs if d not in skip_dirs)
            for fn in sorted(files):
                file_paths.append(Path(base) / fn)
    for file_path in file_paths:
        if file_path.suffix.lower() not in suffixes:
            continue
        try:
            rel = safe_relpath(root_path, file_path)
        except Exception:
            rel = file_path.name
        try:
            raw = file_path.read_bytes()
        except OSError:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = raw.decode("utf-8", errors="ignore")
            except Exception:
                continue
        text = truncate_text(text.strip(), 60_000, "")
        if len(text) < 40:
            continue
        chunks = _chunk_text(text, max_chars=max_chars)
        created = utc_now_iso()
        for idx, piece in enumerate(chunks):
            results.append(
                Chunk(
                    id=f"{rel}:{idx}",
                    source=rel,
                    text=piece,
                    kind="file",
                    tags=(file_path.suffix.lower(),),
                    created_at=created,
                )
            )
        scanned += 1
        if scanned >= limit_files:
            break
    return results


# ---------------------------------------------------------------------------
# Engine protocols
# ---------------------------------------------------------------------------

class RetrievalEngine:
    """Abstract protocol / facade.  Subclasses override ``ingest_many`` and
    ``search``.  The default implementation delegates to a pure-keyword
    engine so ``RetrievalEngine()`` still works out of the box."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._inner = KeywordRetrievalEngine(*args, **kwargs)

    # protocol methods --------------------------------------------------
    def ingest(self, chunk: Chunk) -> None:
        self._inner.ingest(chunk)

    def ingest_many(self, chunks: Iterable[Chunk]) -> int:
        return self._inner.ingest_many(chunks)

    def search(
        self,
        query: str,
        *,
        top_k: int = 6,
        filters: Mapping[str, Any] | None = None,
    ) -> list[SearchHit]:
        return self._inner.search(query, top_k=top_k, filters=filters or {})

    def clear(self) -> None:
        self._inner.clear()

    def size(self) -> int:
        return self._inner.size()

    def export(self, path: str | Path) -> None:
        self._inner.export(path)

    @classmethod
    def load(cls, path: str | Path) -> "RetrievalEngine":
        inner = KeywordRetrievalEngine.load(path)
        engine = cls.__new__(cls)
        engine._inner = inner
        return engine


# ---------------------------------------------------------------------------
# Pure-stdlib TF-IDF implementation
# ---------------------------------------------------------------------------

class KeywordRetrievalEngine:
    """Inverted-index based search with:

    * term-document TF × IDF scoring,
    * BM25-ish k1/b length normalisation (approximate, keeps code simple),
    * chunk metadata filters (``source`` prefix, ``kind``, ``tags``),
    * thread-safe ``RLock`` / :class:`SingletonLock` aliased at load time.
    """

    def __init__(self) -> None:
        self._chunks: dict[str, Chunk] = {}
        self._tokens: dict[str, Counter] = {}
        self._doc_lens: dict[str, int] = {}
        self._avg_len: float = 0.0
        self._k1: float = 1.2
        self._b: float = 0.75
        self._lock = RLock()

    # ------------------------------------------------------------------
    def size(self) -> int:
        with self._lock:
            return len(self._chunks)

    def clear(self) -> None:
        with self._lock:
            self._chunks.clear()
            self._tokens.clear()
            self._doc_lens.clear()
            self._avg_len = 0.0

    # ------------------------------------------------------------------
    def ingest(self, chunk: Chunk) -> None:
        if not isinstance(chunk, Chunk):
            raise RetrievalError("ingest() expects a Chunk instance")
        tokens = tokenize(chunk.text)
        with self._lock:
            # De-dupe by id; remove old posting if replacing.
            if chunk.id in self._chunks:
                for term, c in self._tokens.items():
                    c.pop(chunk.id, None)
            self._chunks[chunk.id] = chunk
            self._doc_lens[chunk.id] = max(1, len(tokens))
            counter = Counter(tokens)
            for term, count in counter.items():
                self._tokens.setdefault(term, Counter())[chunk.id] = count
            self._refresh_avg_len()

    def ingest_many(self, chunks: Iterable[Chunk]) -> int:
        n = 0
        for c in chunks:
            self.ingest(c)
            n += 1
        return n

    # ------------------------------------------------------------------
    def search(
        self,
        query: str,
        *,
        top_k: int = 6,
        filters: Mapping[str, Any] | None = None,
    ) -> list[SearchHit]:
        top_k = max(1, int(top_k))
        q_tokens = [t for t in tokenize(query) if t in self._tokens]
        if not q_tokens:
            # Graceful fall-back: substring scan on sources + tags.
            with self._lock:
                return self._fallback_search(query, top_k=top_k, filters=filters or {})
        filters = filters or {}
        with self._lock:
            N = max(1, len(self._chunks))
            avgdl = self._avg_len or 1.0
            scores: dict[str, float] = Counter()
            hit_terms: dict[str, set[str]] = {}
            for term in q_tokens:
                posting = self._tokens[term]
                if not posting:
                    continue
                df = len(posting)
                idf = math.log(1 + (N - df + 0.5) / (df + 0.5))
                for doc_id, tf in posting.items():
                    dl = self._doc_lens.get(doc_id, 1)
                    denom = tf + self._k1 * (1 - self._b + self._b * (dl / avgdl))
                    if denom <= 0:
                        continue
                    rs = idf * (tf * (self._k1 + 1)) / denom
                    scores[doc_id] += rs
                    hit_terms.setdefault(doc_id, set()).add(term)
            if not scores:
                return []
            ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
            hits: list[SearchHit] = []
            for doc_id, score in ranked:
                if len(hits) >= top_k:
                    break
                chunk = self._chunks.get(doc_id)
                if chunk is None:
                    continue
                if not _matches_filters(chunk, filters):
                    continue
                hits.append(
                    SearchHit(
                        chunk=chunk,
                        score=float(score),
                        matched_terms=tuple(sorted(hit_terms.get(doc_id, ()))),
                    )
                )
            return hits

    # ------------------------------------------------------------------
    def _fallback_search(self, query: str, *, top_k: int, filters: Mapping[str, Any]) -> list[SearchHit]:
        if not query:
            return []
        needle = query.casefold()
        ranked: list[tuple[float, Chunk, list[str]]] = []
        for c in self._chunks.values():
            if not _matches_filters(c, filters):
                continue
            src_hit = needle in str(c.source).casefold()
            text_hits = []
            for line in truncate_text(c.text, 4000, "").splitlines():
                if needle in line.casefold():
                    text_hits.append(line.strip()[:120])
                    if len(text_hits) >= 3:
                        break
            score = 0.0
            if src_hit:
                score += 2.0
            if text_hits:
                score += 1.0 + 0.3 * len(text_hits)
            if score <= 0:
                continue
            ranked.append((score, c, text_hits))
        ranked.sort(key=lambda t: t[0], reverse=True)
        return [
            SearchHit(chunk=c, score=s, matched_terms=tuple(matches))
            for s, c, matches in ranked[:top_k]
        ]

    # ------------------------------------------------------------------
    def _refresh_avg_len(self) -> None:
        if not self._doc_lens:
            self._avg_len = 0.0
            return
        total = sum(self._doc_lens.values())
        self._avg_len = float(total) / float(len(self._doc_lens))

    # ------------------------------------------------------------------
    def export(self, path: str | Path) -> None:
        target = Path(path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            payload = {
                "chunks": [c.to_dict() for c in self._chunks.values()],
                "tokens": {term: dict(docs) for term, docs in self._tokens.items()},
                "doc_lens": dict(self._doc_lens),
                "k1": self._k1,
                "b": self._b,
            }
        target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "KeywordRetrievalEngine":
        source = Path(path).expanduser().resolve()
        if not source.is_file():
            raise RetrievalError(f"retrieval snapshot not found: {source.as_posix()}")
        payload = json.loads(source.read_text(encoding="utf-8"))
        engine = cls()
        with engine._lock:
            for c in payload.get("chunks", []):
                chunk = Chunk(
                    id=str(c["id"]),
                    source=str(c["source"]),
                    text=str(c["text"]),
                    kind=str(c.get("kind") or "text"),
                    tags=tuple(c.get("tags") or ()),
                    created_at=str(c.get("created_at") or ""),
                )
                engine._chunks[chunk.id] = chunk
            for term, docs in (payload.get("tokens") or {}).items():
                engine._tokens[term] = Counter({str(k): int(v) for k, v in docs.items()})
            for k, v in (payload.get("doc_lens") or {}).items():
                engine._doc_lens[str(k)] = int(v)
            engine._k1 = float(payload.get("k1") or 1.2)
            engine._b = float(payload.get("b") or 0.75)
            engine._refresh_avg_len()
        return engine


# ---------------------------------------------------------------------------
# Small filter helpers (used by both search + fall-back)
# ---------------------------------------------------------------------------

def _matches_filters(chunk: Chunk, filters: Mapping[str, Any]) -> bool:
    if not filters:
        return True
    src_prefix = filters.get("source_prefix")
    if src_prefix and not str(chunk.source).startswith(str(src_prefix)):
        return False
    kind = filters.get("kind")
    if kind and chunk.kind != kind:
        return False
    tags = filters.get("tags") or filters.get("tag")
    if tags:
        required = {t.lower() for t in (tags.split(",") if isinstance(tags, str) else tags)}
        have = {t.lower() for t in chunk.tags}
        if not required.issubset(have):
            return False
    return True


# ---------------------------------------------------------------------------
# Optional FAISS / dense adapter (import-lazy, retrieval extra)
# ---------------------------------------------------------------------------

def _require_faiss_deps() -> tuple[Any, Any]:
    missing = [
        name
        for name in ("numpy", "faiss")
        if find_spec(name) is None and find_spec("faiss_cpu" if name == "faiss" else name) is None
    ]
    if missing:
        raise ModuleUnavailableError(
            "DenseRetrievalEngine requires numpy + faiss-cpu; install the "
            "'retrieval' extra (pip install .[retrieval])."
        )
    import importlib
    numpy = importlib.import_module("numpy")
    try:
        faiss = importlib.import_module("faiss")
    except ImportError:
        faiss = importlib.import_module("faiss_cpu")
    return numpy, faiss
