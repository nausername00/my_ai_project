"""L2 memory: three-layer store (short / long / cross-scene) with a
keyword-retrieval fallback so it runs on zero third-party deps.

The public API is intentionally compatible with the ``add_memory`` /
``list_memories`` / ``update_memory`` / ``delete_memory`` surface that
:class:`character.CharacterStore` exposes, so we can swap the underlying
implementation without breaking HTTP routes or tests.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import math
import re
from pathlib import Path
import uuid
from typing import Any, Iterable

from utils import (
    ModuleUnavailableError,
    SingletonLock,
    sanitize_for_log,
    sha256_hex,
    truncate_text,
    utc_now_iso,
)

__all__ = [
    "MemoryStore",
    "MemoryEntry",
    "ShortTermBuffer",
    "LongTermStore",
    "CrossSceneSummary",
    "SEARCH_RESULT_KEY",
]

SEARCH_RESULT_KEY = "memory_id"
_MAX_CONTENT = 20_000
_TOKEN_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9_]+")


def _validate_content(value: Any, field_name: str = "content") -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    value = value.strip()
    if not value:
        raise ValueError(f"{field_name} must not be empty")
    if len(value) > _MAX_CONTENT:
        raise ValueError(
            f"{field_name} must not exceed {_MAX_CONTENT} characters"
        )
    return value


def _tokenize(text: str) -> list[str]:
    """Lightweight tokenizer that works for both CJK and Latin text with zero
    dependencies.  No stopword list – rank is cheap and downstream callers
    filter by score anyway."""
    if not isinstance(text, str):
        return []
    tokens = _TOKEN_RE.findall(text.lower())
    expanded: list[str] = []
    for tok in tokens:
        expanded.append(tok)
        if len(tok) >= 2:
            expanded.append(tok)
        if "\u4e00" <= tok[:1] <= "\u9fff":
            for ch in tok:
                expanded.append(ch)
            if len(tok) >= 2:
                for i in range(len(tok) - 1):
                    expanded.append(tok[i : i + 2])
    return expanded


@dataclass
class MemoryEntry:
    id: str
    content: str
    source: str
    visibility: str
    created_at: str
    tags: list[str] = field(default_factory=list)
    importance: int = 0  # 0..10
    embedding_id: str | None = None
    scene: str | None = None

    def to_dict(self) -> dict[str, Any]:
        base: dict[str, Any] = {
            "id": self.id,
            "content": self.content,
            "source": self.source,
            "visibility": self.visibility,
            "created_at": self.created_at,
            "tags": list(self.tags),
            "importance": int(self.importance),
        }
        if self.embedding_id:
            base["embedding_id"] = self.embedding_id
        if self.scene:
            base["scene"] = self.scene
        return base

    @classmethod
    def from_dict(cls, payload: Any) -> "MemoryEntry":
        if not isinstance(payload, dict):
            raise TypeError("memory entry must be a dict")
        content = _validate_content(payload.get("content"))
        source_raw = payload.get("source", "user")
        if not isinstance(source_raw, str) or not source_raw.strip():
            raise ValueError("source must be a non-empty string")
        source = source_raw.strip()
        visibility = payload.get("visibility", "model")
        if visibility not in {"model", "private"}:
            raise ValueError("visibility must be 'model' or 'private'")
        memory_id = payload.get("id")
        if memory_id is None:
            memory_id = uuid.uuid4().hex
        elif not isinstance(memory_id, str) or not memory_id.strip():
            raise ValueError("id must be a non-empty string when provided")
        created_at = payload.get("created_at", utc_now_iso())
        if not isinstance(created_at, str) or not created_at.strip():
            created_at = utc_now_iso()
        raw_tags = payload.get("tags", [])
        if not isinstance(raw_tags, list) or any(
            not isinstance(t, str) or not t.strip() for t in raw_tags
        ):
            raise ValueError("tags must be a list of non-empty strings")
        if len(raw_tags) > 64:
            raise ValueError("tags must contain at most 64 items")
        tags = [t.strip() for t in raw_tags]
        importance = int(payload.get("importance", 0) or 0)
        if not 0 <= importance <= 10:
            raise ValueError("importance must be between 0 and 10")
        embedding_id = payload.get("embedding_id")
        if embedding_id is not None and (
            not isinstance(embedding_id, str) or not embedding_id.strip()
        ):
            raise ValueError("embedding_id must be a non-empty string or null")
        scene = payload.get("scene")
        if scene is not None and (not isinstance(scene, str) or not scene.strip()):
            raise ValueError("scene must be a non-empty string or null")
        return cls(
            id=str(memory_id).strip(),
            content=content,
            source=source,
            visibility=visibility,
            created_at=created_at,
            tags=tags,
            importance=importance,
            embedding_id=embedding_id,
            scene=scene if isinstance(scene, str) and scene.strip() else None,
        )


class ShortTermBuffer:
    """Session-level sliding window + optional per-dialogue compression.

    Pure in-memory; intentionally not persisted.
    """

    def __init__(self, max_items: int = 40, session_id: str | None = None) -> None:
        if max_items < 2:
            raise ValueError("max_items must be >= 2")
        self.max_items = max_items
        self.session_id = session_id or uuid.uuid4().hex
        self._items: deque[dict[str, str]] = deque(maxlen=max_items)

    def push(self, role: str, text: str) -> None:
        if role not in {"user", "assistant", "tool", "system"}:
            raise ValueError("role must be user/assistant/tool/system")
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        self._items.append(
            {"role": role, "text": truncate_text(text, 8000), "ts": utc_now_iso()}
        )

    def items(self, limit: int | None = None) -> list[tuple[str, str]]:
        seq = list(self._items)
        if limit is not None and limit >= 0:
            seq = seq[-limit:]
        return [(item["role"], item["text"]) for item in seq]

    def clear(self) -> None:
        self._items.clear()

    def __len__(self) -> int:
        return len(self._items)


class LongTermStore:
    """Persistent JSON-backed long-term memory with keyword/BM25-lite search.

    Schema matches legacy character-store entries so migrations are lossless.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._entries: dict[str, MemoryEntry] = {}
        self._dirty = False
        self._load()

    # ---------- persistence ----------
    def _load(self) -> None:
        self._entries.clear()
        if not self.path.is_file():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot read long-term memory store: {exc}") from exc
        if not isinstance(raw, list):
            raise ValueError("long-term memory store must contain a JSON list")
        for index, item in enumerate(raw):
            try:
                entry = MemoryEntry.from_dict(item)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"invalid long-term memory entry #{index}: {exc}"
                ) from exc
            self._entries[entry.id] = entry
        self._dirty = False

    def save(self) -> None:
        if not self._dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [entry.to_dict() for entry in self._entries.values()]
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        tmp.replace(self.path)
        self._dirty = False

    # ---------- CRUD ----------
    def add(
        self,
        content: str,
        source: str,
        visibility: str = "model",
        tags: Iterable[str] | None = None,
        importance: int = 0,
        scene: str | None = None,
    ) -> MemoryEntry:
        entry = MemoryEntry.from_dict(
            {
                "content": _validate_content(content),
                "source": source,
                "visibility": visibility,
                "tags": [t.strip() for t in tags] if tags else [],
                "importance": importance,
                "scene": scene,
                "id": uuid.uuid4().hex,
                "created_at": utc_now_iso(),
            }
        )
        self._entries[entry.id] = entry
        self._dirty = True
        return entry

    def list(self, visibility: str | None = None, limit: int | None = None) -> list[MemoryEntry]:
        items = sorted(
            self._entries.values(),
            key=lambda e: (e.created_at, e.id),
        )
        if visibility in {"model", "private"}:
            items = [e for e in items if e.visibility == visibility]
        if isinstance(limit, int) and limit >= 0:
            items = items[-limit:]
        return items

    def get(self, memory_id: str) -> MemoryEntry:
        if not isinstance(memory_id, str) or memory_id not in self._entries:
            raise LookupError(f"memory not found: {sanitize_for_log(memory_id, 80)}")
        return self._entries[memory_id]

    def update(
        self,
        memory_id: str,
        content: str,
        visibility: str,
        source: str = "user",
        tags: Iterable[str] | None = None,
        importance: int | None = None,
        scene: str | None = "__NO_CHANGE__",
    ) -> MemoryEntry:
        existing = self.get(memory_id)
        payload = existing.to_dict()
        payload["content"] = _validate_content(content)
        payload["visibility"] = visibility
        payload["source"] = source
        if tags is not None:
            payload["tags"] = [t.strip() for t in tags]
        if importance is not None:
            payload["importance"] = importance
        if scene != "__NO_CHANGE__":
            payload["scene"] = scene
        merged = MemoryEntry.from_dict(payload)
        self._entries[merged.id] = merged
        self._dirty = True
        return merged

    def delete(self, memory_id: str) -> None:
        if memory_id not in self._entries:
            raise LookupError(f"memory not found: {sanitize_for_log(memory_id, 80)}")
        del self._entries[memory_id]
        self._dirty = True

    # ---------- search ----------
    def search(
        self,
        query: str,
        top_k: int = 8,
        visibility: str | None = "model",
    ) -> list[dict[str, Any]]:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string")
        if top_k < 1:
            raise ValueError("top_k must be >= 1")
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []
        docs: list[tuple[MemoryEntry, list[str]]] = []
        for entry in self._entries.values():
            if visibility is not None and entry.visibility != visibility:
                continue
            docs.append((entry, _tokenize(entry.content + " " + " ".join(entry.tags))))
        if not docs:
            return []
        df: Counter[str] = Counter()
        for _, tokens in docs:
            unique = set(tokens)
            for tok in query_tokens:
                if tok in unique:
                    df[tok] += 1
        N = len(docs)
        scored: list[tuple[float, MemoryEntry]] = []
        for entry, tokens in docs:
            tf = Counter(tokens)
            score = 0.0
            len_norm = math.sqrt(len(tokens) + 1)
            for tok in query_tokens:
                f = tf.get(tok, 0)
                if not f:
                    continue
                idf = math.log(1 + N / (1 + df.get(tok, 0)))
                score += (f / (f + 0.5 + 1.5)) * idf
            score += float(entry.importance) * 0.15
            if entry.scene and any(
                scene_word in query.lower()
                for scene_word in _tokenize(entry.scene or "")
            ):
                score += 0.4
            if score > 0:
                scored.append((score / len_norm, entry))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        results: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for score, entry in scored:
            if entry.id in seen_ids:
                continue
            seen_ids.add(entry.id)
            item = entry.to_dict()
            item["score"] = round(float(score), 6)
            results.append(item)
            if len(results) >= top_k:
                break
        return results

    def __len__(self) -> int:
        return len(self._entries)


@dataclass
class SceneSummary:
    key: str
    title: str
    summary: str
    last_updated_at: str
    memory_ids: list[str] = field(default_factory=list)
    source: str = "synthesis"

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "title": self.title,
            "summary": self.summary,
            "last_updated_at": self.last_updated_at,
            "memory_ids": list(self.memory_ids),
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, payload: Any) -> "SceneSummary":
        if not isinstance(payload, dict):
            raise TypeError("scene summary must be a dict")
        key_raw = payload.get("key")
        title_raw = payload.get("title")
        summary_raw = payload.get("summary")
        if (
            not isinstance(key_raw, str)
            or not key_raw.strip()
            or not isinstance(title_raw, str)
            or not title_raw.strip()
            or not isinstance(summary_raw, str)
            or not summary_raw.strip()
        ):
            raise ValueError("scene summary requires non-empty key/title/summary")
        updated = payload.get("last_updated_at") or utc_now_iso()
        ids = payload.get("memory_ids", [])
        if not isinstance(ids, list) or any(
            not isinstance(i, str) or not i.strip() for i in ids
        ):
            raise ValueError("memory_ids must be a list of non-empty strings")
        source = payload.get("source", "synthesis")
        if not isinstance(source, str) or not source.strip():
            source = "synthesis"
        return cls(
            key=key_raw.strip(),
            title=title_raw.strip(),
            summary=truncate_text(summary_raw.strip(), 8000),
            last_updated_at=str(updated).strip() or utc_now_iso(),
            memory_ids=[i.strip() for i in ids],
            source=source.strip(),
        )


class CrossSceneSummary:
    """Per-scene / per-project / per-person synthesised summaries.

    The synthesise step optionally delegates to the LLM so summaries are
    semantic rather than just extractive; if no engine is available we fall
    back to concatenating the top memory snippets and mark
    ``source = "extract"``.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._summaries: dict[str, SceneSummary] = {}
        self._dirty = False
        self._load()

    def _load(self) -> None:
        self._summaries.clear()
        if not self.path.is_file():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot read cross-scene summaries: {exc}") from exc
        if not isinstance(raw, list):
            raise ValueError("cross-scene store must contain a JSON list")
        for index, item in enumerate(raw):
            try:
                summary = SceneSummary.from_dict(item)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"invalid cross-scene summary #{index}: {exc}"
                ) from exc
            self._summaries[summary.key] = summary
        self._dirty = False

    def save(self) -> None:
        if not self._dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [s.to_dict() for s in self._summaries.values()]
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        tmp.replace(self.path)
        self._dirty = False

    @staticmethod
    def bucket_key(kind: str, value: str) -> str:
        if kind not in {"scene", "project", "person", "goal"}:
            raise ValueError("kind must be scene/project/person/goal")
        if not isinstance(value, str) or not value.strip():
            raise ValueError("value must be a non-empty string")
        safe = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff_\-]+", "_", value.strip())
        return f"{kind}:{safe[:80]}"

    def list(self) -> list[SceneSummary]:
        return sorted(
            self._summaries.values(),
            key=lambda s: (s.last_updated_at, s.key),
            reverse=True,
        )

    def upsert(
        self,
        key: str,
        title: str,
        summary: str,
        memory_ids: Iterable[str] | None = None,
        source: str = "synthesis",
    ) -> SceneSummary:
        built = SceneSummary.from_dict(
            {
                "key": key,
                "title": title,
                "summary": summary,
                "last_updated_at": utc_now_iso(),
                "memory_ids": list(memory_ids or []),
                "source": source,
            }
        )
        self._summaries[built.key] = built
        self._dirty = True
        return built

    def delete(self, key: str) -> None:
        if key not in self._summaries:
            raise LookupError(f"cross-scene summary not found: {sanitize_for_log(key, 80)}")
        del self._summaries[key]
        self._dirty = True


class MemoryStore:
    """Facade that owns a short/long/cross-scene triplet.

    All mutation methods are serialised via :class:`SingletonLock` so the
    store remains safe inside the threaded HTTP server.
    """

    def __init__(
        self,
        long_term_path: Path,
        cross_scene_path: Path | None = None,
        short_term_capacity: int = 40,
    ) -> None:
        self._lock = SingletonLock()
        self.long_term = LongTermStore(Path(long_term_path))
        self.cross_scene = CrossSceneSummary(
            Path(cross_scene_path)
            if cross_scene_path is not None
            else Path(long_term_path).with_name("cross_scene.json")
        )
        self.short_term = ShortTermBuffer(max_items=short_term_capacity)

    def save(self) -> None:
        with self._lock:
            self.long_term.save()
            self.cross_scene.save()

    # ---------- short-term ----------
    def push_dialogue(self, role: str, text: str) -> None:
        with self._lock:
            self.short_term.push(role, text)

    def recent_dialogue(self, limit: int | None = None) -> list[tuple[str, str]]:
        with self._lock:
            return self.short_term.items(limit)

    def clear_short_term(self) -> None:
        with self._lock:
            self.short_term.clear()

    # ---------- long-term CRUD (mirrors CharacterStore API shape) ----------
    def add_memory(
        self,
        content: str,
        source: str = "user",
        visibility: str = "model",
        tags: Iterable[str] | None = None,
        importance: int = 0,
        scene: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            entry = self.long_term.add(
                content=content,
                source=source,
                visibility=visibility,
                tags=tags,
                importance=importance,
                scene=scene,
            )
            self._dirty = True
            return entry.to_dict()

    def list_memories(self, visibility: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            return [e.to_dict() for e in self.long_term.list(visibility=visibility)]

    def update_memory(
        self,
        memory_id: str,
        content: str,
        visibility: str,
        source: str = "user",
        tags: Iterable[str] | None = None,
        importance: int | None = None,
        scene: str | None = "__NO_CHANGE__",
    ) -> dict[str, Any]:
        with self._lock:
            updated = self.long_term.update(
                memory_id=memory_id,
                content=content,
                visibility=visibility,
                source=source,
                tags=tags,
                importance=importance,
                scene=scene,
            )
            self._dirty = True
            return updated.to_dict()

    def delete_memory(self, memory_id: str) -> None:
        with self._lock:
            self.long_term.delete(memory_id)
            self._dirty = True

    def search_memories(
        self,
        query: str,
        top_k: int = 8,
        visibility: str | None = "model",
    ) -> list[dict[str, Any]]:
        with self._lock:
            return self.long_term.search(query=query, top_k=top_k, visibility=visibility)

    # ---------- cross-scene ----------
    def list_cross_scene(self) -> list[dict[str, Any]]:
        with self._lock:
            return [s.to_dict() for s in self.cross_scene.list()]

    def upsert_cross_scene(
        self,
        key: str,
        title: str,
        summary: str,
        memory_ids: Iterable[str] | None = None,
        source: str = "synthesis",
    ) -> dict[str, Any]:
        with self._lock:
            result = self.cross_scene.upsert(key, title, summary, memory_ids, source)
            self._dirty = True
            return result.to_dict()

    def synthesize_cross_scene(
        self,
        engine: Any,
        key: str,
        title: str,
        system_prompt: str = "",
    ) -> dict[str, Any]:
        """Best-effort LLM synthesis; falls back to extractive concatenation
        so the function is always safe to call even without a real engine."""
        with self._lock:
            entries = self.long_term.list()
            related = [
                e
                for e in entries
                if (e.scene and CrossSceneSummary.bucket_key("scene", e.scene) == key)
                or any(tag in key for tag in e.tags)
            ]
            if not related:
                related = entries[-10:]
            snippets = "\n".join(
                f"- [{e.created_at}] {truncate_text(e.content, 500)}" for e in related[-20:]
            )
            summary = ""
            source = "extract"
            if engine is not None and getattr(engine, "model_name", "placeholder") != "placeholder":
                try:
                    from inference import GenerationRequest  # local import to avoid cycles
                    req = GenerationRequest(
                        prompt=(
                            "把下面的相关记忆片段综合成一段 2~6 句的可读摘要，"
                            "突出跨时间段重复出现的主题和尚未完成的目标。"
                            "不要编造不在原文中的事实；不要输出隐私敏感细节。"
                            f"\n汇总键：{key}\n标题：{title}"
                            f"\n相关片段（按时间升序）：\n{snippets}"
                        ),
                        max_tokens=360,
                        system_prompt=system_prompt or "你是本地的记忆综合器。",
                        temperature=0.0,
                    )
                    raw = engine.generate(req).strip()
                    if raw:
                        summary = truncate_text(raw, 2000)
                        source = "synthesis"
                except Exception as exc:  # pragma: no cover - best effort
                    summary = ""
            if not summary:
                summary = "（尚未执行 LLM 综合）相关记忆：" + truncate_text(
                    " | ".join(truncate_text(e.content, 120) for e in related[-8:]),
                    1500,
                )
                source = "extract"
            result = self.cross_scene.upsert(
                key=key,
                title=title,
                summary=summary,
                memory_ids=[e.id for e in related[-64:]],
                source=source,
            )
            self._dirty = True
            return result.to_dict()

    # ---------- import / export compatible with CharacterStore ----------
    def export_memories(self) -> dict[str, Any]:
        with self._lock:
            return {
                "schema_version": 2,
                "exported_at": utc_now_iso(),
                "storage": "local-only",
                "memories": [e.to_dict() for e in self.long_term.list()],
                "cross_scene": [s.to_dict() for s in self.cross_scene.list()],
            }

    def import_memories(self, payload: Any) -> dict[str, int]:
        if not isinstance(payload, dict):
            raise TypeError("import payload must be a dict")
        imported_raw = payload.get("memories")
        if not isinstance(imported_raw, list):
            raise ValueError("import must contain a memories list")
        if len(imported_raw) > 2000:
            raise ValueError("an import may contain at most 2000 memories")
        cross_raw = payload.get("cross_scene")
        if cross_raw is not None and not isinstance(cross_raw, list):
            raise ValueError("cross_scene must be a list")
        with self._lock:
            known = {
                sha256_hex(
                    (e.content or "") + "||" + (e.source or "") + "||" + (e.visibility or "")
                )
                for e in self.long_term.list()
            }
            added = 0
            skipped = 0
            for item in imported_raw:
                try:
                    entry = MemoryEntry.from_dict(item)
                except (TypeError, ValueError):
                    skipped += 1
                    continue
                sig = sha256_hex(entry.content + "||" + entry.source + "||" + entry.visibility)
                if sig in known:
                    skipped += 1
                    continue
                self.long_term._entries[entry.id] = entry  # type: ignore[attr-defined]
                self.long_term._dirty = True  # type: ignore[attr-defined]
                known.add(sig)
                added += 1
            scene_added = 0
            if isinstance(cross_raw, list):
                for item in cross_raw:
                    try:
                        summary = SceneSummary.from_dict(item)
                    except (TypeError, ValueError):
                        continue
                    self.cross_scene._summaries[summary.key] = summary  # type: ignore[attr-defined]
                    self.cross_scene._dirty = True  # type: ignore[attr-defined]
                    scene_added += 1
            self._dirty = True
            self.save()
            return {
                "imported_memories": added,
                "skipped_memories": len(imported_raw) - added,
                "skipped_invalid_memories": skipped,
                "imported_cross_scene": scene_added,
            }
