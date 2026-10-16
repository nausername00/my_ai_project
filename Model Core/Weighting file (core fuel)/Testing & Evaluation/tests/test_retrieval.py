"""D 层测试补全 · retrieval：分词、Chunk 结构、关键词检索、过滤器、导入导出、ingest_path。"""

import os
import tempfile
import unittest

from retrieval import (
    Chunk,
    KeywordRetrievalEngine,
    RetrievalEngine,
    RetrievalError,
    SearchHit,
    ingest_path,
    tokenize,
)


class TokenizeTest(unittest.TestCase):
    def test_empty_text(self) -> None:
        self.assertEqual(tokenize(""), [])
        self.assertEqual(tokenize(None), [])

    def test_english_tokens(self) -> None:
        tokens = tokenize("Hello world hello world")
        self.assertEqual(tokens.count("hello"), 2)
        self.assertEqual(tokens.count("world"), 2)

    def test_chinese_tokens(self) -> None:
        tokens = tokenize("墨灵是一个本地伙伴系统")
        self.assertTrue(any("墨灵" in t for t in tokens))
        self.assertTrue(any("伙伴" in t for t in tokens))

    def test_stopwords_filtered(self) -> None:
        tokens = tokenize("the and of a very long query for retrieval")
        self.assertNotIn("the", tokens)
        self.assertNotIn("and", tokens)

    def test_short_tokens_skipped(self) -> None:
        tokens = tokenize("a b c ok abc")
        self.assertNotIn("a", tokens)
        self.assertNotIn("ok", tokens)  # 2 字符词不在词表（最短 3 字符）
        self.assertIn("abc", tokens)


class ChunkTest(unittest.TestCase):
    def test_to_dict_shape(self) -> None:
        chunk = Chunk(
            id="c1",
            source="notes/plan.md",
            text="你好世界",
            kind="file",
            tags=(".md",),
            created_at="2026-10-16T00:00:00Z",
        )
        data = chunk.to_dict()
        self.assertEqual(data["id"], "c1")
        self.assertEqual(data["source"], "notes/plan.md")
        self.assertEqual(data["text"], "你好世界")
        self.assertEqual(data["kind"], "file")
        self.assertEqual(data["tags"], [".md"])

    def test_defaults(self) -> None:
        chunk = Chunk(id="x", source="s", text="t")
        self.assertEqual(chunk.kind, "text")
        self.assertEqual(chunk.tags, ())


class KeywordEngineTest(unittest.TestCase):
    def test_ingest_requires_chunk(self) -> None:
        engine = KeywordRetrievalEngine()
        with self.assertRaises(RetrievalError):
            engine.ingest("not a chunk")  # type: ignore[arg-type]

    def test_ingest_and_search(self) -> None:
        engine = KeywordRetrievalEngine()
        engine.ingest(Chunk(id="a", source="doc1", text="墨灵喜欢画画和唱歌"))
        engine.ingest(Chunk(id="b", source="doc2", text="墨灵喜欢写代码和调试"))
        hits = engine.search("画画", top_k=5)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].chunk.id, "a")
        self.assertGreater(hits[0].score, 0.0)

    def test_search_no_match_empty(self) -> None:
        engine = KeywordRetrievalEngine()
        engine.ingest(Chunk(id="a", source="doc1", text="今天天气不错"))
        hits = engine.search("量子计算")
        self.assertEqual(hits, [])

    def test_search_ranked_by_relevance(self) -> None:
        engine = KeywordRetrievalEngine()
        engine.ingest(Chunk(id="weak", source="d1", text="伙伴系统"))
        engine.ingest(
            Chunk(id="strong", source="d2", text="伙伴系统 伙伴系统 长期记忆 伙伴系统")
        )
        hits = engine.search("伙伴系统", top_k=5)
        self.assertEqual(hits[0].chunk.id, "strong")

    def test_search_top_k_limit(self) -> None:
        engine = KeywordRetrievalEngine()
        for i in range(5):
            engine.ingest(Chunk(id=f"c{i}", source="s", text=f"关键词{i} 测试"))
        hits = engine.search("测试", top_k=3)
        self.assertEqual(len(hits), 3)

    def test_size_clear_ingest_many(self) -> None:
        engine = KeywordRetrievalEngine()
        chunks = [
            Chunk(id="a", source="s1", text="第一条 内容"),
            Chunk(id="b", source="s2", text="第二条 内容"),
        ]
        self.assertEqual(engine.ingest_many(chunks), 2)
        self.assertEqual(engine.size(), 2)
        engine.clear()
        self.assertEqual(engine.size(), 0)

    def test_same_id_replaces(self) -> None:
        engine = KeywordRetrievalEngine()
        engine.ingest(Chunk(id="a", source="s1", text="旧文本 甲"))
        engine.ingest(Chunk(id="a", source="s2", text="新文本 乙"))
        self.assertEqual(engine.size(), 1)
        hits = engine.search("乙")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].chunk.source, "s2")

    def test_filters_by_source_prefix(self) -> None:
        engine = KeywordRetrievalEngine()
        engine.ingest(Chunk(id="a", source="docs/guide.md", text="过滤器 主题"))
        engine.ingest(Chunk(id="b", source="tests/test_x.py", text="过滤器 主题"))
        hits = engine.search("过滤器", top_k=5, filters={"source_prefix": "docs/"})
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].chunk.id, "a")

    def test_filters_by_kind_and_tags(self) -> None:
        engine = KeywordRetrievalEngine()
        engine.ingest(Chunk(id="a", source="s1", text="主题词 内容", kind="file", tags=(".md",)))
        engine.ingest(Chunk(id="b", source="s2", text="主题词 内容", kind="text", tags=()))
        hits = engine.search("主题词", top_k=5, filters={"kind": "file"})
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].chunk.id, "a")
        hits2 = engine.search("主题词", top_k=5, filters={"tags": ".md"})
        self.assertEqual(len(hits2), 1)
        self.assertEqual(hits2[0].chunk.id, "a")

    def test_export_load_roundtrip(self) -> None:
        engine = KeywordRetrievalEngine()
        engine.ingest(Chunk(id="a", source="s1", text="导出 导入 往返"))
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "index.json")
            engine.export(path)
            loaded = KeywordRetrievalEngine.load(path)
        self.assertEqual(loaded.size(), 1)
        self.assertEqual(loaded.search("往返")[0].chunk.id, "a")

    def test_search_hit_to_dict(self) -> None:
        engine = KeywordRetrievalEngine()
        engine.ingest(Chunk(id="a", source="s1", text="结果 结构"))
        hit = engine.search("结果")[0]
        data = hit.to_dict()
        self.assertIn("chunk", data)
        self.assertIn("score", data)
        self.assertIn("matched_terms", data)


class RetrievalEngineFacadeTest(unittest.TestCase):
    def test_facade_delegates(self) -> None:
        engine = RetrievalEngine()
        engine.ingest(Chunk(id="a", source="s1", text="外观 委托"))
        self.assertEqual(engine.size(), 1)
        hits = engine.search("委托")
        self.assertEqual(len(hits), 1)
        engine.clear()
        self.assertEqual(engine.size(), 0)

    def test_facade_load(self) -> None:
        engine = RetrievalEngine()
        engine.ingest(Chunk(id="a", source="s1", text="加载 测试"))
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "idx.json")
            engine.export(path)
            loaded = RetrievalEngine.load(path)
        self.assertEqual(loaded.size(), 1)


class IngestPathTest(unittest.TestCase):
    def test_missing_root_raises(self) -> None:
        with self.assertRaises(RetrievalError):
            ingest_path("/definitely/not/exists")

    def test_walks_directory_and_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sub = os.path.join(tmp, "src")
            os.makedirs(sub)
            with open(os.path.join(sub, "a.txt"), "w", encoding="utf-8") as f:
                f.write("这是第一份足够长的可检索文档内容，用于测试目录遍历与分块，长度必须超过四十个字符的收录阈值。")
            with open(os.path.join(sub, "b.md"), "w", encoding="utf-8") as f:
                f.write("这是第二份足够长的可检索文档内容，标题与正文应当被收录，同样需要超过四十个字符的最低长度要求。")
            chunks = ingest_path(tmp, max_chars=1000)
        self.assertGreaterEqual(len(chunks), 2)
        sources = {c.source for c in chunks}
        self.assertTrue(any("a.txt" in s for s in sources))
        self.assertTrue(any("b.md" in s for s in sources))

    def test_non_utf8_and_short_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "bin.dat"), "wb") as f:
                f.write(b"\xff\xfe\x00binary")
            with open(os.path.join(tmp, "short.txt"), "w", encoding="utf-8") as f:
                f.write("短")  # < 40 chars → skipped
            chunks = ingest_path(tmp)
        self.assertEqual(chunks, [])

    def test_suffix_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "a.py"), "w", encoding="utf-8") as f:
                f.write("def helper():\n    return 1\n# 足够长的注释内容用于过滤测试，要超过四十个字符的最低收录阈值。")
            with open(os.path.join(tmp, "b.md"), "w", encoding="utf-8") as f:
                f.write("这是一段足够长的 Markdown 内容，用于验证后缀过滤是否生效，长度同样要超过四十个字符阈值。")
            chunks = ingest_path(tmp, allowed_suffixes=(".py",))
        sources = {c.source for c in chunks}
        self.assertTrue(any("a.py" in s for s in sources))
        self.assertFalse(any("b.md" in s for s in sources))

    def test_single_file_ingest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "note.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write("这是单文件导入测试的完整内容，长度需要超过四十个字符的最低收录阈值，确保可以产生至少一个检索分块。")
            chunks = ingest_path(path)
        self.assertGreaterEqual(len(chunks), 1)


if __name__ == "__main__":
    unittest.main()
