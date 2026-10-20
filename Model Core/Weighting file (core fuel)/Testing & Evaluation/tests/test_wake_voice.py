"""wake_voice 常驻语音唤醒核心单测（不依赖麦克风/真实 whisper）。

覆盖：关键词匹配、状态机（唤醒→聆听→冷却）、静音跳过、暂停防自唤醒、
识别失败容错、事件格式。
"""

import unittest

import numpy as np

from wake_voice import (
    WakeVoiceEngine,
    match_wake_keyword,
    _rms,
    _to_wav_bytes,
    resample_linear,
)


class FakeSpeech:
    """注入识别文本的假 SpeechService。"""

    def __init__(self, text: str) -> None:
        self.text = text

    def transcribe_audio(self, _audio: bytes, _suffix: str) -> dict:
        return {"text": self.text}


def _block(level: int = 2000, size: int = 25600) -> np.ndarray:
    """构造指定 RMS 的 int16 音频块（有声=白噪*level，静音=全零）。"""
    if level <= 0:
        return np.zeros(size, dtype=np.int16)
    rng = np.random.default_rng(7)
    noise = rng.normal(0.0, level, size).astype(np.float32)
    peak = float(np.max(np.abs(noise))) or 1.0
    scaled = (noise / peak * min(level * 3, 32767)).astype(np.int16)
    return scaled


class MatchKeywordTest(unittest.TestCase):
    def test_hits(self) -> None:
        for text in ("墨灵", "墨灵墨灵", "墨灵墨灵~", "小墨灵", "你好墨灵", "墨灵在吗"):
            self.assertTrue(match_wake_keyword(text), text)
        # whisper 常输出繁体：也应命中
        for text in ("墨靈墨靈在嗎?", "墨靈在嗎", "墨靈靈"):
            self.assertTrue(match_wake_keyword(text), repr(text))

    def test_misses(self) -> None:
        for text in ("", "在的哟", "今天天气不错", "墨", "林", "hello", None):
            self.assertFalse(match_wake_keyword(text), repr(text))


class EngineStateTest(unittest.TestCase):
    def _engine(self, text: str = "") -> WakeVoiceEngine:
        return WakeVoiceEngine(FakeSpeech(text), threshold=140)

    def test_silent_block_no_event(self) -> None:
        engine = self._engine("墨灵墨灵")
        events = engine.feed_chunk(_block(level=0))
        self.assertEqual(events, [])

    def test_noisy_non_keyword_no_wake(self) -> None:
        engine = self._engine("今天天气不错")
        events = engine.feed_chunk(_block(level=2000))
        self.assertEqual(events, [])
        self.assertEqual(engine.state, "idle")

    def test_wake_hit(self) -> None:
        engine = self._engine("墨灵墨灵")
        events = engine.feed_chunk(_block(level=2000))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "wake")
        self.assertEqual(events[0]["text"], "墨灵墨灵")
        self.assertEqual(engine.state, "listening")

    def test_heard_within_window(self) -> None:
        engine = self._engine("墨灵墨灵")
        engine.feed_chunk(_block(level=2000))  # 先触发唤醒
        self.assertEqual(engine.state, "listening")
        engine.speech = FakeSpeech("帮我写个计划")  # 唤醒后用户话语
        events = engine.feed_chunk(_block(level=2000))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "heard")
        self.assertEqual(events[0]["text"], "帮我写个计划")

    def test_no_duplicate_wake_in_window(self) -> None:
        engine = self._engine("墨灵墨灵")
        engine.feed_chunk(_block(level=2000))  # wake
        engine._heard_once = True
        events = engine.feed_chunk(_block(level=2000))  # 窗口内再喊
        self.assertEqual(events, [])  # 不再重复 wake

    def test_pause_suppresses(self) -> None:
        engine = self._engine("墨灵墨灵")
        engine.pause()
        events = engine.feed_chunk(_block(level=2000))
        self.assertEqual(events, [])
        engine.resume()
        events = engine.feed_chunk(_block(level=2000))
        self.assertEqual(len(events), 1)

    def test_recognize_failure_tolerant(self) -> None:
        class BoomSpeech:
            def transcribe_audio(self, _a, _b):  # noqa: ANN001
                raise RuntimeError("boom")

        engine = WakeVoiceEngine(BoomSpeech(), threshold=140)
        events = engine.feed_chunk(_block(level=2000))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "error")
        self.assertEqual(engine.state, "idle")


class UtilsTest(unittest.TestCase):
    def test_rms_silent_zero(self) -> None:
        self.assertAlmostEqual(_rms(np.zeros(100, dtype=np.int16)), 0.0)

    def test_rms_noise_positive(self) -> None:
        self.assertGreater(_rms(_block(level=2000)), 100.0)

    def test_to_wav_bytes(self) -> None:
        data = _to_wav_bytes(np.zeros(8000, dtype=np.int16))
        self.assertTrue(data.startswith(b"RIFF"))
        self.assertGreater(len(data), 44)

    def test_resample_48k_to_16k(self) -> None:
        src = np.linspace(-3000, 3000, 48000, dtype=np.int16)
        out = resample_linear(src, 48000, 16000)
        self.assertEqual(len(out), 16000)
        self.assertEqual(out.dtype, np.int16)

    def test_resample_same_rate_noop(self) -> None:
        src = _block(level=2000, size=16000)
        out = resample_linear(src, 16000, 16000)
        self.assertTrue(np.array_equal(out, src))


if __name__ == "__main__":
    unittest.main()
