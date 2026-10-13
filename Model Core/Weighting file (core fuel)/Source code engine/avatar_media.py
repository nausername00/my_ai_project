"""墨灵媒体工具：纯标准库音频处理（不依赖 ffmpeg）。

mix_voice_first —— 人声优先混音 v1：音乐音量降低后与人声叠加（16-bit PCM WAV）。
- duration="first"：以人声时长为准（与视频合成习惯一致），音乐不足部分循环补齐。
- v2（可选）：接入 ffmpeg 侧链压缩实现动态闪避（检测到 ffmpeg 时可用）。
"""
from __future__ import annotations

import array
import json
import math
import wave
from pathlib import Path
from typing import Any

_NEUTRAL_CAPTIONS: list[dict[str, Any]] = []


def _read_wav(path: str | Path) -> tuple[Any, array.array]:
    """读取 16-bit PCM WAV，返回 (params, samples)。"""
    with wave.open(str(path), "rb") as w:
        params = w.getparams()
        frames = w.readframes(w.getnframes())
    if params.sampwidth != 2:
        raise ValueError("仅支持 16-bit PCM WAV")
    samples = array.array("h")
    samples.frombytes(frames)
    return params, samples


def _write_wav(path: str | Path, params: Any, samples: array.array) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(params.nchannels)
        w.setsampwidth(params.sampwidth)
        w.setframerate(params.framerate)
        w.writeframes(samples.tobytes())


def mix_voice_first(
    voice_path: str | Path,
    music_path: str | Path,
    out_path: str | Path,
    music_gain_db: float = -6.0,
    duration: str = "first",
) -> dict[str, Any]:
    """人声优先混音 v1：音乐降低 gain 后与人声叠加，输出时长以人声为准。

    确定性保证：输出样本 = clamp(人声样本 + 音乐样本×gain)，峰值不会超过人声峰值 + 音乐峰值×gain，
    人声被完整保留、音乐被压低——"人声优先"的最简可验证实现。
    """
    voice_params, voice = _read_wav(voice_path)
    music_params, music = _read_wav(music_path)
    if voice_params.sampwidth != music_params.sampwidth:
        raise ValueError("人声与音乐采样位宽不一致")
    if voice_params.nchannels != music_params.nchannels:
        raise ValueError("人声与音乐声道数不一致")
    if not voice:
        raise ValueError("人声文件为空")

    gain = 10.0 ** (music_gain_db / 20.0)
    total = len(voice)
    if duration != "first":
        total = min(total, len(music))
    if total <= 0:
        raise ValueError("混音时长为空")

    out = array.array("h")
    for index in range(total):
        voice_sample = voice[index]
        music_sample = int(music[index % len(music)] * gain)
        merged = voice_sample + music_sample
        out.append(max(-32768, min(32767, merged)))

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _write_wav(out_path, voice_params, out)
    return {
        "status": "ok",
        "out": str(out_path),
        "frames": total,
        "duration_sec": round(total / voice_params.framerate, 3),
        "mode": "voice_first_v1",
        "music_gain_db": music_gain_db,
    }


def compute_mouth_curve(
    voice_path: str | Path,
    segment_sec: float = 0.2,
    threshold: float = 0.05,
) -> dict[str, Any]:
    """按音量重算口型开合曲线：每段 RMS 高于阈值 → open，否则 closed。

    规则（K5/K6 待办）：有声音时小幅开口，停顿时闭嘴；换配音后按新音频重算。
    返回与字幕时间戳对齐的分段曲线，供前端 / 演出时间线使用。
    """
    params, samples = _read_wav(voice_path)
    rate = params.framerate
    channels = params.nchannels
    segment = max(1, int(segment_sec * rate * channels))
    total_segments = max(1, math.ceil(len(samples) / segment))
    curve: list[dict[str, Any]] = []
    for index in range(total_segments):
        start = index * segment
        chunk = samples[start : start + segment]
        if not chunk:
            curve.append({"open": False, "rms": 0.0})
            continue
        rms = math.sqrt(sum(s * s for s in chunk) / len(chunk)) / 32768.0
        curve.append({"open": rms >= threshold, "rms": round(rms, 5)})
    return {
        "status": "ok",
        "segment_sec": segment_sec,
        "threshold": threshold,
        "curve": curve,
        "open_ratio": round(
            sum(1 for c in curve if c["open"]) / len(curve), 4
        ) if curve else 0.0,
    }


class CaptionTimelineStore:
    """字幕时间戳数据层：每条字幕 {start, end, text} 可编辑、可保存，支持换音重算对齐。

    存储隔离：单文件 JSON（caption_timelines.json），测试走独立路径。
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._timelines: dict[str, list[dict[str, Any]]] = {}
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._timelines = data
            except (json.JSONDecodeError, OSError):
                self._timelines = {}

    def get(self, clip_id: str) -> list[dict[str, Any]]:
        return list(self._timelines.get(clip_id, _NEUTRAL_CAPTIONS))

    def set(self, clip_id: str, captions: list[dict[str, Any]]) -> dict[str, Any]:
        cleaned: list[dict[str, Any]] = []
        for item in captions:
            if not isinstance(item, dict):
                continue
            try:
                cleaned.append(
                    {
                        "start": float(item.get("start", 0.0)),
                        "end": float(item.get("end", 0.0)),
                        "text": str(item.get("text", "")),
                    }
                )
            except (TypeError, ValueError):
                continue
        if not cleaned:
            raise ValueError("字幕列表为空或格式非法")
        self._timelines[clip_id] = cleaned
        self._save()
        return {"status": "ok", "clip_id": clip_id, "count": len(cleaned)}

    def edit_timestamp(
        self, clip_id: str, index: int, start: float, end: float
    ) -> dict[str, Any]:
        captions = self._timelines.get(clip_id)
        if not captions or not (0 <= index < len(captions)):
            raise ValueError(f"字幕条目不存在: {clip_id}[{index}]")
        captions[index]["start"] = float(start)
        captions[index]["end"] = float(end)
        self._save()
        return {"status": "ok", "clip_id": clip_id, "index": index,
                "start": captions[index]["start"], "end": captions[index]["end"]}

    def align_mouth(self, clip_id: str, voice_path: str | Path) -> dict[str, Any]:
        """换音重算：按新配音重算口型曲线，并把字幕时间戳对齐到曲线段。

        对齐规则：按每条字幕的 start 时间戳落到对应曲线段（时间对齐，而非索引对齐）。
        """
        curve = compute_mouth_curve(voice_path)
        captions = self._timelines.get(clip_id)
        if captions is None:
            raise ValueError(f"字幕不存在: {clip_id}")
        segment_sec = curve["segment_sec"]
        points = curve["curve"]
        aligned: list[dict[str, Any]] = []
        for item in captions:
            segment_index = min(
                len(points) - 1, max(0, int(item["start"] / segment_sec))
            )
            point = points[segment_index]
            aligned.append(
                {
                    "start": item["start"],
                    "end": item["end"],
                    "text": item["text"],
                    "mouth": "open" if point["open"] else "closed",
                }
            )
        self._timelines[clip_id] = aligned
        self._save()
        return {"status": "ok", "clip_id": clip_id, "count": len(aligned),
                "open_ratio": curve["open_ratio"]}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._timelines, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
