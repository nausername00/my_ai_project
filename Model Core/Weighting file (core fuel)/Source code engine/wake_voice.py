"""常驻语音唤醒：麦克风连续监听「墨灵/墨灵墨灵~」→ 事件输出（Electron 主进程消费）。

设计要点：
- **本地优先**：识别复用 speech.py 的 SpeechService（faster_whisper small 已在本机缓存，
  离线可用）；不依赖任何云端语音服务。
- **轻量常驻**：16kHz 单声道块（默认 1.6s），能量门限（RMS 低于阈值=静音跳过），
  只有"有声块"才送 whisper 识别，把 CPU 消耗压到最低。
- **防自唤醒**：墨灵自己说话（TTS 播放）会被麦克风拾音 → 支持 stdin 命令
  `PAUSE`（播语音期间暂停识别）/ `RESUME` / `QUIT`，由 Electron 在播放前后下发。
- **可编程核心**：`WakeVoiceEngine.feed_chunk()` 接收 int16 数组纯函数式处理，
  单测无需麦克风；CLI `--listen` 用 sounddevice 常驻采集。

事件行协议（stdout，Electron 逐行解析）：
  EVENT|status|{"state":"idle|listening|cooldown","heard":"..."}
  EVENT|wake|{text}           命中唤醒词（text=识别原文）
  EVENT|heard|{text}          唤醒聆听窗口内识别到的用户话语
  EVENT|error|{message}

用法：
  py -3 wake_voice.py --listen [--threshold 140] [--chunk-ms 1600]
  py -3 wake_voice.py --test 20            # 真麦克风自测 20 秒，打印每块识别结果
"""

from __future__ import annotations

import argparse
import json
import queue
import sys
import threading
import time

import numpy as np

from speech import SpeechService

SAMPLE_RATE = 16000
CHUNK_SECONDS = 1.6
DEFAULT_THRESHOLD = 140  # int16 RMS，低于视为静音
LISTEN_WINDOW_S = 8.0    # 唤醒后聆听窗口
COOLDOWN_S = 5.0         # 唤醒后冷却（防连击）
WAKE_KEYWORD = "墨灵"


def _rms(samples: np.ndarray) -> float:
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))


def resample_linear(samples: np.ndarray, src_rate: int, dst_rate: int = SAMPLE_RATE) -> np.ndarray:
    """线性插值重采样（44.1k/48k 麦克风 → whisper 需要的 16k）。"""
    if src_rate == dst_rate or samples.size == 0:
        return samples
    n_out = max(1, int(round(len(samples) * dst_rate / src_rate)))
    x_in = np.linspace(0.0, 1.0, num=len(samples), endpoint=False)
    x_out = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
    return np.interp(x_out, x_in, samples.astype(np.float64)).astype(np.int16)


def _to_wav_bytes(samples: np.ndarray) -> bytes:
    """int16 单声道 16kHz → WAV bytes（供 SpeechService.transcribe_audio 使用）。"""
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(samples.astype("<i2").tobytes())
    return buf.getvalue()


def match_wake_keyword(text: str) -> bool:
    """唤醒词匹配：识别文本含「墨灵」（覆盖 墨灵/墨灵墨灵~/小墨灵 等；whisper 输出的繁体自动归一）。"""
    normalized = _simplify(str(text or ""))
    return WAKE_KEYWORD in normalized


# whisper 可能输出繁体（如「墨靈墨靈在嗎?」）：常见字轻量归一后再匹配。
_SIMPLIFY_MAP = str.maketrans(
    {"靈": "灵", "嗎": "吗", "喲": "哟", "這": "这", "說": "说", "請": "请",
     "聽": "听", "沒": "没", "麼": "么", "來": "来", "個": "个", "問": "问", "嗎": "吗"}
)


def _simplify(text: str) -> str:
    return text.translate(_SIMPLIFY_MAP)


class WakeVoiceEngine:
    """唤醒状态机核心（纯逻辑，可注入音频块；不经麦克风即可单测）。"""

    def __init__(
        self,
        speech: SpeechService,
        threshold: int = DEFAULT_THRESHOLD,
        chunk_ms: int = int(CHUNK_SECONDS * 1000),
        listen_window_s: float = LISTEN_WINDOW_S,
        cooldown_s: float = COOLDOWN_S,
        source_rate: int = SAMPLE_RATE,
    ) -> None:
        self.speech = speech
        self.threshold = threshold
        self.source_rate = source_rate
        self.chunk_samples = int(source_rate * chunk_ms / 1000)
        self.listen_window_s = listen_window_s
        self.cooldown_s = cooldown_s
        self.state = "idle"  # idle | listening | cooldown
        self._woke_at = 0.0
        self._heard_once = False
        self._paused = False

    # -- 外部控制 -----------------------------------------------------------
    def pause(self) -> None:
        """TTS 播放期间暂停识别（防自唤醒）。"""
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    @property
    def paused(self) -> bool:
        return self._paused

    # -- 音频块处理 ----------------------------------------------------------
    def feed_chunk(self, samples: np.ndarray) -> list[dict[str, str]]:
        """处理一个音频块，返回本块产生的事件列表（可单测、可 CLI 复用）。"""
        events: list[dict[str, str]] = []
        if self._paused or samples.size == 0:
            return events
        level = _rms(samples)
        if level < self.threshold:
            self._tick()
            return events
        try:
            text = self.speech.transcribe_audio(
                _to_wav_bytes(resample_linear(samples, self.source_rate)), ".wav"
            )["text"]
        except Exception as error:  # 识别失败不中断常驻监听
            events.append({"type": "error", "message": f"recognize failed: {error}"})
            self._tick()
            return events
        now = time.monotonic()
        if self.state == "listening":
            if text and not self._heard_once:
                self._heard_once = True
                events.append({"type": "heard", "text": text})
            elif now - self._woke_at > self.listen_window_s:
                self.state = "idle"
        elif match_wake_keyword(text):
            self.state = "listening"
            self._woke_at = now
            self._heard_once = False
            events.append({"type": "wake", "text": text})
        else:
            self._tick()
        return events

    def _tick(self) -> None:
        """非命中块：推进冷却 / 聆听窗口超时状态。"""
        now = time.monotonic()
        if self.state == "cooldown" and now - self._woke_at > self.cooldown_s:
            self.state = "idle"
        elif self.state == "listening" and now - self._woke_at > self.listen_window_s:
            self.state = "idle"

    def status(self) -> dict[str, object]:
        return {
            "state": self.state,
            "paused": self._paused,
            "threshold": self.threshold,
            "source_rate": self.source_rate,
            "chunk_samples": self.chunk_samples,
            "listen_window_s": self.listen_window_s,
            "cooldown_s": self.cooldown_s,
            "keyword": WAKE_KEYWORD,
        }


# ---------------------------------------------------------------------------
# CLI：常驻监听 / 自测
# ---------------------------------------------------------------------------
def _emit(event: dict[str, str]) -> None:
    print(f"EVENT|{event.get('type', 'unknown')}|{event.get('text', event.get('message', ''))}", flush=True)


def _stdin_loop(engine: WakeVoiceEngine) -> None:
    for line in sys.stdin:
        command = line.strip().upper()
        if command == "PAUSE":
            engine.pause()
        elif command == "RESUME":
            engine.resume()
        elif command == "QUIT":
            break


def run_listen(args: argparse.Namespace) -> int:
    try:
        import sounddevice as sd
    except ImportError:
        print("EVENT|error|需要 sounddevice：py -3 -m pip install sounddevice", flush=True)
        return 2

    engine = WakeVoiceEngine(
        SpeechService(),
        threshold=args.threshold,
        chunk_ms=args.chunk_ms,
        source_rate=args.rate,
    )
    threading.Thread(target=_stdin_loop, args=(engine,), daemon=True).start()

    audio_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=8)

    def callback(indata, _frames, _time_info, status) -> None:  # noqa: ANN001
        if status:
            _emit({"type": "error", "message": f"audio: {status}"})
        try:
            audio_queue.put_nowait(indata.copy())
        except queue.Full:
            pass  # 处理不过来就丢块，不阻塞采集

    try:
        with sd.InputStream(
            samplerate=args.rate,
            channels=1,
            dtype="int16",
            blocksize=engine.chunk_samples,
            device=args.device or None,
            callback=callback,
        ):
            _emit({"type": "status", "message": json.dumps({"state": "listening"})})
            while True:
                block = audio_queue.get()
                for event in engine.feed_chunk(block):
                    _emit(event)
    except KeyboardInterrupt:
        return 0
    except Exception as error:  # 麦克风不可用等
        _emit({"type": "error", "message": f"mic unavailable: {error}"})
        return 1


def run_test(args: argparse.Namespace) -> int:
    """真麦克风自测：打印每块能量与识别文本，不触发唤醒状态机。"""
    try:
        import sounddevice as sd
    except ImportError:
        print("需要 sounddevice：py -3 -m pip install sounddevice", file=sys.stderr)
        return 2

    speech = SpeechService()
    chunk = int(args.rate * args.chunk_ms / 1000)
    print(f"[selftest] {args.test}s @ {args.rate}Hz chunk={args.chunk_ms}ms threshold={args.threshold} device={args.device}", flush=True)
    print("[selftest] 请正常说话；说「墨灵墨灵~」验证识别；Ctrl+C 结束", flush=True)

    results: queue.Queue[np.ndarray] = queue.Queue(maxsize=16)

    def callback(indata, _frames, _time_info, status) -> None:  # noqa: ANN001
        if status:
            print(f"[audio] {status}", file=sys.stderr)
        try:
            results.put_nowait(indata.copy())
        except queue.Full:
            pass

    deadline = time.monotonic() + args.test
    try:
        with sd.InputStream(
            samplerate=args.rate, channels=1, dtype="int16",
            blocksize=chunk, device=args.device or None, callback=callback,
        ):
            while time.monotonic() < deadline:
                try:
                    block = results.get(timeout=0.5)
                except queue.Empty:
                    continue
                level = _rms(block)
                if level < args.threshold:
                    print(f"[{level:.0f}] (静音跳过)", flush=True)
                    continue
                try:
                    text = speech.transcribe_audio(
                        _to_wav_bytes(resample_linear(block, args.rate)), ".wav"
                    )["text"]
                except Exception as error:
                    text = f"<识别失败 {error}>"
                print(f"[{level:.0f}] {text!r}", flush=True)
    except Exception as error:
        print(f"mic unavailable: {error}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="墨灵常驻语音唤醒（本地 whisper）")
    parser.add_argument("--listen", action="store_true", help="常驻监听模式（事件行协议输出）")
    parser.add_argument("--test", type=float, default=0, help="真麦克风自测时长（秒）")
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    parser.add_argument("--chunk-ms", type=int, default=int(CHUNK_SECONDS * 1000))
    parser.add_argument("--device", type=int, default=None, help="sounddevice 输入设备索引（默认系统默认输入）")
    parser.add_argument("--rate", type=int, default=SAMPLE_RATE, help="采集采样率（默认 16000；44.1k/48k 麦克风自动重采样）")
    args = parser.parse_args()

    if args.test > 0:
        return run_test(args)
    if args.listen:
        return run_listen(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
