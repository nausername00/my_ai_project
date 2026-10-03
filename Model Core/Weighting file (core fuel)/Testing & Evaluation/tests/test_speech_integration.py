import json
import os
import tempfile
import unittest
from http.client import HTTPConnection
from threading import Thread
from unittest.mock import patch

from app import create_server


@unittest.skipUnless(
    os.getenv("RUN_SPEECH_INTEGRATION") == "1",
    "set RUN_SPEECH_INTEGRATION=1 to test installed local speech models",
)
class SpeechIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.environment = patch.dict(
            os.environ,
            {
                "MODEL_BACKEND": "placeholder",
                "CHARACTER_CARD_PATH": os.path.join(self.temp_dir.name, "character.json"),
                "CHARACTER_MEMORY_PATH": os.path.join(self.temp_dir.name, "memory.json"),
                "CHARACTER_ASSET_DIR": self.temp_dir.name,
                "CHARACTER_PRIVACY_PATH": os.path.join(self.temp_dir.name, "privacy.json"),
                "CHARACTER_AFFECT_PATH": os.path.join(self.temp_dir.name, "affect.json"),
            },
        )
        self.environment.start()
        self.server = create_server()
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.connection = HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=180
        )

    def tearDown(self) -> None:
        self.connection.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.environment.stop()
        self.temp_dir.cleanup()

    def test_local_piper_wav_is_transcribed_by_whisper_over_api(self) -> None:
        self.connection.request(
            "POST",
            "/v1/speech",
            json.dumps({"text": "你好，我是墨灵。今天我们测试本地语音识别。"}),
            {"Content-Type": "application/json"},
        )
        synthesis_response = self.connection.getresponse()
        audio = synthesis_response.read()
        self.assertEqual(synthesis_response.status, 200)
        self.assertEqual(synthesis_response.getheader("Content-Type"), "audio/wav")
        self.assertTrue(audio.startswith(b"RIFF"))

        self.connection.request(
            "POST",
            "/v1/transcribe",
            audio,
            {"Content-Type": "audio/wav"},
        )
        transcription_response = self.connection.getresponse()
        result = json.loads(transcription_response.read())
        self.assertEqual(transcription_response.status, 200, result)
        self.assertIn("今天我们测试本地语音识别", result["text"])
        self.assertEqual(result["language"], "zh")
        self.assertGreater(result["duration_seconds"], 0)
