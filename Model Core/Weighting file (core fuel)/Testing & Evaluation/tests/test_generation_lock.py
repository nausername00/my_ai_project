"""E12 生成互斥锁：同一时刻只允许一次模型推理（并发保护，E4 队列最轻形态）。"""

import threading
import time
import unittest

from inference import GenerationRequest, InferenceEngine


class SlowBackend:
    """慢速后端：每次生成固定耗时，用于观察并发是否被串行化。"""

    model_name = "slow"

    def __init__(self, delay: float = 0.15) -> None:
        self.delay = delay

    def generate(self, request: GenerationRequest, *, image=None) -> str:
        time.sleep(self.delay)
        return f"[slow] {request.prompt}"


class GenerationLockTest(unittest.TestCase):
    """并发调用被串行化；单线程/异常后调用不受影响。"""

    def _request(self, prompt: str) -> GenerationRequest:
        return GenerationRequest(prompt=prompt, max_tokens=8)

    def test_concurrent_calls_are_serialized(self) -> None:
        delay = 0.12
        engine = InferenceEngine(SlowBackend(delay=delay))
        completions: list[float] = []
        completions_lock = threading.Lock()
        results: list[str] = []

        def worker(prompt: str) -> None:
            text = engine.generate(self._request(prompt))
            with completions_lock:
                completions.append(time.perf_counter())
                results.append(text)

        threads = [
            threading.Thread(target=worker, args=(f"任务{i}",)) for i in range(2)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(len(completions), 2)
        # 串行时两次完成时刻至少相差一个单次耗时（并发则几乎同时完成）
        self.assertGreaterEqual(
            max(completions) - min(completions), delay * 0.8
        )
        self.assertEqual(sorted(results), sorted(["[slow] 任务0", "[slow] 任务1"]))

    def test_single_call_returns_normally(self) -> None:
        engine = InferenceEngine(SlowBackend(delay=0.0))
        self.assertEqual(
            engine.generate(self._request("你好")), "[slow] 你好"
        )

    def test_lock_released_after_backend_error(self) -> None:
        class FailingBackend:
            model_name = "failing"
            attempts = 0

            def generate(self, request, *, image=None) -> str:
                FailingBackend.attempts += 1
                if FailingBackend.attempts == 1:
                    raise RuntimeError("boom")
                return "recovered"

        engine = InferenceEngine(FailingBackend())
        with self.assertRaises(RuntimeError):
            engine.generate(self._request("x"))
        # 异常后锁已释放，第二次调用正常
        self.assertEqual(engine.generate(self._request("x")), "recovered")


if __name__ == "__main__":
    unittest.main()
