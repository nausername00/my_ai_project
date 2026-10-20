from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import wave

from speech import SpeechInputError, SpeechService, SpeechUnavailableError


class SpeechServiceTests(unittest.TestCase):
    def test_synthesizes_wav_using_local_voice_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            voice_path = Path(directory) / "voice.onnx"
            voice_path.touch()
            voice_path.with_suffix(".onnx.json").write_text("{}", encoding="utf-8")

            class FakeVoice:
                def synthesize_wav(self, text: str, output: wave.Wave_write) -> None:
                    output.setnchannels(1)
                    output.setsampwidth(2)
                    output.setframerate(22050)
                    output.writeframes(b"\0\0" * 16)

            piper_module = SimpleNamespace(
                PiperVoice=SimpleNamespace(load=lambda *args, **kwargs: FakeVoice())
            )
            service = SpeechService(piper_voice_path=str(voice_path))
            with patch("speech.importlib.import_module", return_value=piper_module):
                result = service.synthesize_wav("hello")

        self.assertTrue(result.startswith(b"RIFF"))
        self.assertIn(b"WAVE", result[:12])

    def test_lists_speakers_and_passes_selected_speaker_to_piper(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            voice_path = Path(directory) / "multi.onnx"
            voice_path.touch()
            voice_path.with_suffix(".onnx.json").write_text(
                '{"num_speakers": 2, "speaker_id_map": {"A": 0, "B": 1}}',
                encoding="utf-8",
            )
            captured: dict[str, object] = {}

            class FakeVoice:
                def synthesize_wav(
                    self,
                    text: str,
                    output: wave.Wave_write,
                    syn_config: object = None,
                ) -> None:
                    captured["speaker_id"] = syn_config.speaker_id
                    output.setnchannels(1)
                    output.setsampwidth(2)
                    output.setframerate(22050)
                    output.writeframes(b"\0\0" * 16)

            piper_module = SimpleNamespace(
                PiperVoice=SimpleNamespace(load=lambda *args, **kwargs: FakeVoice()),
                SynthesisConfig=lambda **kwargs: SimpleNamespace(**kwargs),
            )
            service = SpeechService(piper_voice_path=str(voice_path))
            self.assertEqual(
                service.list_voices()[0]["speakers"],
                [{"id": 0, "name": "A"}, {"id": 1, "name": "B"}],
            )
            with patch("speech.importlib.import_module", return_value=piper_module):
                result = service.synthesize_wav("hello", speaker_id=1)

        self.assertTrue(result.startswith(b"RIFF"))
        self.assertEqual(captured["speaker_id"], 1)

    def test_rejects_missing_local_chinese_phoneme_resources_without_loading_piper(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            voice_path = Path(directory) / "chinese.onnx"
            voice_path.touch()
            voice_path.with_suffix(".onnx.json").write_text(
                '{"phoneme_type": "pinyin"}', encoding="utf-8"
            )
            service = SpeechService(
                piper_voice_path=str(voice_path),
                piper_data_dir=str(Path(directory) / "piper-data"),
            )
            with patch("speech.importlib.import_module") as load_runtime:
                with self.assertRaisesRegex(SpeechUnavailableError, "不会自动下载"):
                    service.synthesize_wav("你好")
            load_runtime.assert_not_called()

    def test_requires_complete_local_chinese_phoneme_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            voice_path = Path(directory) / "chinese.onnx"
            voice_path.touch()
            voice_path.with_suffix(".onnx.json").write_text(
                '{"phoneme_type": "pinyin"}', encoding="utf-8"
            )
            data_dir = Path(directory) / "piper-data"
            resource_dir = data_dir / "g2pW"
            resource_dir.mkdir(parents=True)
            for resource in SpeechService.PINYIN_REQUIRED_FILES:
                (resource_dir / resource).touch()
            service = SpeechService(
                piper_voice_path=str(voice_path),
                piper_data_dir=str(data_dir),
            )
            self.assertTrue(service.status()["pinyin_resources_available"])
            (resource_dir / "config.py").unlink()
            self.assertFalse(service.status()["pinyin_resources_available"])

    def test_transcribes_audio_with_local_whisper_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary_paths: list[Path] = []

            class FakeWhisperModel:
                def transcribe(self, path: str, **kwargs: object) -> tuple[object, object]:
                    self.assert_audio_exists(path)
                    with open(path, "rb") as audio_file:
                        if audio_file.read() != b"test audio bytes":
                            raise AssertionError("temporary audio contents changed")
                    temporary_paths.append(Path(path))
                    return (
                        iter([SimpleNamespace(text=" hello"), SimpleNamespace(text=" world")]),
                        SimpleNamespace(language="en", duration=1.234),
                    )

                @staticmethod
                def assert_audio_exists(path: str) -> None:
                    if not Path(path).is_file():
                        raise AssertionError("temporary audio file was not created")

            whisper_module = SimpleNamespace(WhisperModel=lambda *args, **kwargs: FakeWhisperModel())
            service = SpeechService(whisper_cache_dir=directory)
            with patch("speech.importlib.import_module", return_value=whisper_module):
                result = service.transcribe_audio(b"test audio bytes", ".wav")

        self.assertEqual(result, {"text": "hello world", "language": "en", "duration_seconds": 1.23})
        self.assertEqual(len(temporary_paths), 1)
        self.assertFalse(temporary_paths[0].exists())

    def test_removes_temporary_audio_when_transcription_fails(self) -> None:
        temporary_paths: list[Path] = []

        class FailedWhisperModel:
            def transcribe(self, path: str, **kwargs: object) -> tuple[object, object]:
                temporary_paths.append(Path(path))
                raise RuntimeError("decode failed")

        whisper_module = SimpleNamespace(
            WhisperModel=lambda *args, **kwargs: FailedWhisperModel()
        )
        with tempfile.TemporaryDirectory() as directory:
            service = SpeechService(whisper_cache_dir=directory)
            with patch("speech.importlib.import_module", return_value=whisper_module):
                with self.assertRaises(SpeechInputError):
                    service.transcribe_audio(b"test audio bytes", ".wav")

        self.assertEqual(len(temporary_paths), 1)
        self.assertFalse(temporary_paths[0].exists())

    def test_rejects_invalid_audio_before_loading_model(self) -> None:
        service = SpeechService()
        with self.assertRaises(SpeechInputError):
            service.transcribe_audio(b"", ".wav")
        with self.assertRaises(SpeechInputError):
            service.transcribe_audio(b"content", ".txt")

    def test_requires_local_voice_model_and_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = SpeechService(piper_voice_path=str(Path(directory) / "missing.onnx"))
            with self.assertRaises(SpeechUnavailableError):
                service.synthesize_wav("hello")
