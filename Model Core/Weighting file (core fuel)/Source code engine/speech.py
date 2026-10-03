"""Local speech recognition and synthesis services."""

from importlib.util import find_spec
import importlib
import io
import os
from pathlib import Path
import tempfile
from threading import RLock
import wave
from typing import Any


class SpeechInputError(ValueError):
    """Raised for invalid or unsupported audio input."""


class SpeechUnavailableError(RuntimeError):
    """Raised when an optional speech runtime or model is unavailable."""


class SpeechService:
    MAX_TEXT_LENGTH = 2000

    def __init__(
        self,
        whisper_model: str | None = None,
        whisper_cache_dir: str | None = None,
        piper_voice_path: str | None = None,
        language: str | None = None,
    ) -> None:
        local_data = Path(
            os.getenv(
                "LOCALAPPDATA",
                str(Path.home() / ".local" / "share"),
            )
        )
        self.whisper_model_name = whisper_model or os.getenv(
            "WHISPER_MODEL", "small"
        )
        self.whisper_cache_dir = Path(
            whisper_cache_dir
            or os.getenv(
                "WHISPER_CACHE_DIR",
                str(local_data / "CocoCompanion" / "models" / "whisper"),
            )
        )
        default_voice = (
            Path(__file__).resolve().parent.parent
            / "Character"
            / "assets"
            / "voices"
            / "zh_CN-huayan-medium.onnx"
        )
        self.piper_voice_path = Path(
            piper_voice_path
            or os.getenv("PIPER_VOICE_PATH", str(default_voice))
        ).expanduser()
        self.language = language or os.getenv("WHISPER_LANGUAGE", "zh")
        self._whisper: Any = None
        self._voice: Any = None
        self._load_lock = RLock()

    def status(self) -> dict[str, Any]:
        return {
            "recognition_runtime_installed": find_spec("faster_whisper") is not None,
            "synthesis_runtime_installed": find_spec("piper") is not None,
            "whisper_model": self.whisper_model_name,
            "whisper_model_loaded": self._whisper is not None,
            "voice_name": self.piper_voice_path.name,
            "voice_model_available": self.piper_voice_path.is_file()
            and self.piper_voice_path.with_suffix(
                self.piper_voice_path.suffix + ".json"
            ).is_file(),
            "processing": "local",
        }

    def transcribe_audio(self, audio: bytes, suffix: str) -> dict[str, Any]:
        if not audio:
            raise SpeechInputError("audio payload must not be empty")
        if suffix not in {".wav", ".webm", ".ogg", ".m4a", ".mp3"}:
            raise SpeechInputError("unsupported audio format")
        model = self._get_whisper()
        audio_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as audio_file:
                audio_path = audio_file.name
                audio_file.write(audio)
                audio_file.flush()
            if audio_path is None:
                raise SpeechInputError("could not create a temporary audio file")
            segments, info = model.transcribe(
                audio_path,
                language=self.language or None,
                vad_filter=True,
            )
            text = "".join(segment.text for segment in segments).strip()
        except (OSError, RuntimeError, ValueError) as error:
            raise SpeechInputError(f"could not process audio: {error}") from error
        finally:
            if audio_path is not None:
                try:
                    Path(audio_path).unlink(missing_ok=True)
                except OSError as error:
                    raise SpeechInputError(
                        f"could not remove temporary audio file: {error}"
                    ) from error
        return {
            "text": text,
            "language": info.language,
            "duration_seconds": round(info.duration, 2),
        }

    def synthesize_wav(self, text: str) -> bytes:
        if not isinstance(text, str):
            raise SpeechInputError("text must be a string")
        text = text.strip()
        if not text:
            raise SpeechInputError("text must not be empty")
        if len(text) > self.MAX_TEXT_LENGTH:
            raise SpeechInputError(
                f"text must not exceed {self.MAX_TEXT_LENGTH} characters"
            )
        voice = self._get_voice()
        output = io.BytesIO()
        try:
            with wave.open(output, "wb") as wav_file:
                voice.synthesize_wav(text, wav_file)
        except (OSError, RuntimeError, ValueError) as error:
            raise SpeechUnavailableError(f"local speech synthesis failed: {error}") from error
        return output.getvalue()

    def _get_whisper(self) -> Any:
        if self._whisper is not None:
            return self._whisper
        with self._load_lock:
            if self._whisper is not None:
                return self._whisper
            try:
                whisper_module = importlib.import_module("faster_whisper")
            except ImportError as error:
                raise SpeechUnavailableError(
                    "speech recognition dependencies are missing; install the 'speech' extra"
                ) from error
            self.whisper_cache_dir.mkdir(parents=True, exist_ok=True)
            try:
                self._whisper = whisper_module.WhisperModel(
                    self.whisper_model_name,
                    device="cpu",
                    compute_type="int8",
                    download_root=str(self.whisper_cache_dir),
                )
            except (OSError, RuntimeError, ValueError) as error:
                raise SpeechUnavailableError(
                    f"could not load Whisper model '{self.whisper_model_name}': {error}"
                ) from error
        return self._whisper

    def _get_voice(self) -> Any:
        if self._voice is not None:
            return self._voice
        config_path = self.piper_voice_path.with_suffix(
            self.piper_voice_path.suffix + ".json"
        )
        if not self.piper_voice_path.is_file() or not config_path.is_file():
            raise SpeechUnavailableError(
                "Piper voice model is missing; set PIPER_VOICE_PATH to a local "
                "Piper .onnx file with its matching .onnx.json config"
            )
        with self._load_lock:
            if self._voice is not None:
                return self._voice
            try:
                piper_module = importlib.import_module("piper")
            except ImportError as error:
                raise SpeechUnavailableError(
                    "speech synthesis dependencies are missing; install the 'speech' extra"
                ) from error
            try:
                self._voice = piper_module.PiperVoice.load(
                    self.piper_voice_path,
                    config_path=config_path,
                    use_cuda=False,
                )
            except (OSError, RuntimeError, ValueError) as error:
                raise SpeechUnavailableError(
                    f"could not load Piper voice '{self.piper_voice_path.name}': {error}"
                ) from error
        return self._voice

    # ------------------------------------------------------------------
    # Streaming / VAD loop (L0 real-time perception interface)
    # ------------------------------------------------------------------
    def start_vad_loop(
        self,
        *,
        approved: bool = False,
        purpose: str | None = None,
        callback=None,
        samplerate: int = 16000,
        block_duration_ms: int = 30,
        min_speech_seconds: float = 0.8,
        silence_seconds: float = 0.9,
        energy_threshold: float | None = None,
        stop_event=None,
        transcribe_after: bool = False,
    ) -> dict[str, Any]:
        """Start a background voice-activity loop.

        Permission gate – ``approved`` is the *first* kwarg (default
        ``False``) and raises :class:`PermissionDenied` before touching the
        microphone.  When the optional ``sounddevice`` extra is not
        installed the function still returns a :class:`VADLoopHandle` with
        ``status="unavailable"`` so callers can fall back gracefully.
        """
        from utils import PermissionDenied, ModuleUnavailableError, SingletonLock
        if not approved:
            detail = purpose and f" 目的：{purpose}" or ""
            raise PermissionDenied(
                f"用户尚未授权使用麦克风（start_vad_loop）。{detail}\n"
                "请通过权限对话框显式确认 approved=True。"
            )
        if callback is not None and not callable(callback):
            raise SpeechInputError("callback must be callable when provided")
        # Optional real-time dep: sounddevice.
        if find_spec("sounddevice") is None:
            raise ModuleUnavailableError(
                "start_vad_loop requires sounddevice; install the 'speech' extra "
                "(pip install .[speech])."
            )
        import importlib as _il, audioop, threading, time, queue
        sd = _il.import_module("sounddevice")
        vad_block_ms = max(10, int(block_duration_ms))
        frames_per_block = max(1, int(samplerate * vad_block_ms / 1000))
        audio_queue: "queue.Queue[bytes]" = queue.Queue()
        stop_now = stop_event if stop_event is not None else threading.Event()
        output_lock = SingletonLock()
        stats = {"segments": 0, "last_transcribed": "", "last_error": None}

        def audio_cb(indata, frames, time_info, status):
            # int16 PCM block; convert to bytes for audioop.
            try:
                import numpy as np
                arr = np.asarray(indata)
                if arr.dtype != np.int16:
                    arr = (np.clip(arr, -1.0, 1.0) * 32767).astype(np.int16)
                pcm = arr.tobytes(order="C")
            except Exception:
                pcm = b"\x00\x00" * max(1, frames)
            audio_queue.put(pcm)

        def worker_loop():
            silence_so_far = 0.0
            speech_so_far = 0.0
            speaking = False
            buffer = bytearray()
            try:
                threshold_local: float = energy_threshold if energy_threshold is not None else 300.0
            except Exception:
                threshold_local = 300.0
            try:
                while not stop_now.is_set():
                    try:
                        block = audio_queue.get(timeout=0.2)
                    except Exception:
                        continue
                    try:
                        rms = audioop.rms(block, 2) or 0
                    except Exception:
                        rms = 0
                    if energy_threshold is None:
                        # Auto-tune first 1.5s if caller gave no threshold.
                        threshold_local = 0.6 * max(threshold_local, rms * 0.4 + 180.0)
                    is_speech = float(rms) >= float(threshold_local)
                    dt_sec = vad_block_ms / 1000.0
                    if is_speech:
                        silence_so_far = 0.0
                        speech_so_far += dt_sec
                        if not speaking:
                            speaking = True
                            buffer.clear()
                        buffer.extend(block)
                    else:
                        if speaking:
                            silence_so_far += dt_sec
                            buffer.extend(block)
                            if (
                                silence_so_far >= silence_seconds
                                and speech_so_far >= min_speech_seconds
                            ):
                                # Emit speech segment.
                                pcm = bytes(buffer)
                                segment_sec = speech_so_far + silence_so_far
                                transcribed = None
                                if transcribe_after:
                                    try:
                                        wav_bytes = _encode_pcm16_wav(pcm, samplerate)
                                        transcribed = self.transcribe_audio(wav_bytes, ".wav")
                                    except Exception as exc:
                                        stats["last_error"] = str(exc)
                                event = {
                                    "type": "speech_segment",
                                    "speech_seconds": round(speech_so_far, 3),
                                    "segment_seconds": round(segment_sec, 3),
                                    "pcm_length": len(pcm),
                                    "peak_rms": rms,
                                    "transcribed": transcribed,
                                    "captured_at": _vad_utc_now_iso(),
                                }
                                with output_lock:
                                    stats["segments"] += 1
                                    if transcribed:
                                        stats["last_transcribed"] = transcribed.get("text", "")
                                try:
                                    if callback is not None:
                                        callback(event)
                                except Exception as exc:
                                    stats["last_error"] = str(exc)
                                speaking = False
                                speech_so_far = 0.0
                                silence_so_far = 0.0
                                buffer.clear()
                        else:
                            speech_so_far = max(0.0, speech_so_far - dt_sec * 0.5)
            except Exception as exc:  # pragma: no cover
                stats["last_error"] = str(exc)

        thread = threading.Thread(target=worker_loop, name="speech-vad-loop", daemon=True)
        try:
            stream = sd.InputStream(
                samplerate=samplerate,
                blocksize=frames_per_block,
                channels=1,
                dtype="int16",
                callback=audio_cb,
            )
        except Exception as exc:
            raise SpeechUnavailableError(f"failed to open microphone stream: {exc}") from exc
        stream.start()
        thread.start()

        def stop():
            try:
                stop_now.set()
            finally:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass

        handle = {
            "status": "running",
            "samplerate": int(samplerate),
            "block_ms": int(vad_block_ms),
            "energy_threshold": float(energy_threshold if energy_threshold is not None else 300.0),
            "min_speech_seconds": float(min_speech_seconds),
            "silence_seconds": float(silence_seconds),
            "transcribe_after": bool(transcribe_after),
            "stop": stop,
            "stats": lambda: dict(stats),
        }
        return handle


def _encode_pcm16_wav(pcm_bytes: bytes, samplerate: int) -> bytes:
    """Wrap a raw PCM16 mono blob into a minimal in-memory RIFF/WAV so
    :meth:`SpeechService.transcribe_audio` can consume it without touching
    disk.
    """
    import io, wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(samplerate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


def _vad_utc_now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
