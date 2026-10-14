"""E7 轻量可观测指标 + E9 生成统计：请求计数/延迟/错误率 与 /v1/status/metrics 快照测试。"""

import unittest

import api


class FakeHandler:
    """模拟 ApiHandler：只有 path 属性的最小桩。"""

    def __init__(self, path: str = "/v1/test") -> None:
        self.path = path


class TrackedDecoratorTest(unittest.TestCase):
    """_tracked 包装：成功/异常请求的计数、延迟与错误率。"""

    def setUp(self) -> None:
        api._METRICS.clear()

    def test_successful_call_counts_and_duration(self) -> None:
        calls = []

        def fake(self) -> int:
            calls.append(self.path)
            return 7

        wrapped = api._tracked(fake)
        result = wrapped(FakeHandler("/v1/example"))
        self.assertEqual(result, 7)
        snapshot = api.metrics_snapshot()
        self.assertEqual(snapshot["totals"]["count"], 1)
        self.assertEqual(snapshot["totals"]["error_count"], 0)
        entry = snapshot["requests"][0]
        self.assertEqual(entry["method"], "fake")
        self.assertEqual(entry["path"], "/v1/example")
        self.assertIn("total_ms", entry)

    def test_exception_counts_as_error_and_reports(self) -> None:
        def fake(self) -> None:
            raise ValueError("boom")

        wrapped = api._tracked(fake)
        with self.assertRaises(ValueError):
            wrapped(FakeHandler("/v1/fail"))
        snapshot = api.metrics_snapshot()
        self.assertEqual(snapshot["totals"]["count"], 1)
        self.assertEqual(snapshot["totals"]["error_count"], 1)
        self.assertEqual(snapshot["requests"][0]["error_count"], 1)

    def test_path_prefix_grouping(self) -> None:
        self.assertEqual(api._path_prefix("/v1/memory/usage"), "/v1/memory")
        self.assertEqual(api._path_prefix("/v1/agent/traces/x"), "/v1/agent")
        self.assertEqual(api._path_prefix("/health"), "/health")
        self.assertEqual(api._path_prefix("/"), "/")

    def test_repeated_calls_aggregate(self) -> None:
        def fake(self) -> None:
            return None

        wrapped = api._tracked(fake)
        for _ in range(3):
            wrapped(FakeHandler("/v1/memory/usage"))
        snapshot = api.metrics_snapshot()
        entry = snapshot["requests"][0]
        self.assertEqual(entry["count"], 3)
        self.assertEqual(entry["path"], "/v1/memory")


class MetricsSnapshotTest(unittest.TestCase):
    """快照形状：started_at / uptime_s / requests 排序 / totals。"""

    def setUp(self) -> None:
        api._METRICS.clear()

    def test_snapshot_shape(self) -> None:
        snapshot = api.metrics_snapshot()
        self.assertIn("started_at", snapshot)
        self.assertIn("uptime_s", snapshot)
        self.assertEqual(snapshot["requests"], [])
        self.assertEqual(snapshot["totals"]["count"], 0)

    def test_snapshot_sorts_by_count_desc(self) -> None:
        def fake(self) -> None:
            return None

        wrapped = api._tracked(fake)
        wrapped(FakeHandler("/v1/a"))
        wrapped(FakeHandler("/v1/a"))
        wrapped(FakeHandler("/v1/b"))
        snapshot = api.metrics_snapshot()
        self.assertEqual(snapshot["requests"][0]["path"], "/v1/a")
        self.assertEqual(snapshot["requests"][0]["count"], 2)

    def test_avg_ms_present(self) -> None:
        def fake(self) -> None:
            return None

        wrapped = api._tracked(fake)
        wrapped(FakeHandler("/v1/a"))
        snapshot = api.metrics_snapshot()
        self.assertIn("avg_ms", snapshot["requests"][0])


class GenerationStatsTest(unittest.TestCase):
    """E9 生成统计：record_generation 累计与快照 generations 形状。"""

    def setUp(self) -> None:
        api._GENERATION_STATS.clear()
        api._GENERATION_STATS.update({"count": 0.0, "chars": 0.0, "total_ms": 0.0})

    def test_record_accumulates(self) -> None:
        api.record_generation(120, 350.0)
        api.record_generation(80, 150.0)
        snapshot = api.metrics_snapshot()
        generations = snapshot["generations"]
        self.assertEqual(generations["count"], 2)
        self.assertEqual(generations["chars"], 200)
        self.assertEqual(generations["total_ms"], 500.0)
        self.assertEqual(generations["avg_ms"], 250.0)

    def test_empty_state_shape(self) -> None:
        snapshot = api.metrics_snapshot()
        self.assertEqual(snapshot["generations"]["count"], 0)
        self.assertEqual(snapshot["generations"]["avg_ms"], 0.0)

    def test_negative_inputs_clamped(self) -> None:
        api.record_generation(-5, -10.0)
        snapshot = api.metrics_snapshot()
        self.assertEqual(snapshot["generations"]["chars"], 0)
        self.assertEqual(snapshot["generations"]["total_ms"], 0.0)


if __name__ == "__main__":
    unittest.main()
