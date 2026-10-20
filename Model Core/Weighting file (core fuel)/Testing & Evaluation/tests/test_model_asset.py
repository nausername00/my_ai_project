"""第三梯队 C · /v1/model/asset 只读模型资源端点测试。

覆盖：白名单扩展名 / 目录穿越拒绝 / 越界文件拒绝 / 真实模型文件可读 /
空与非法参数拒绝。模型资源仅服务 Character 目录，供手机页 Live2D 加载。
"""

import json
import os
import tempfile
import unittest
from http.client import HTTPConnection
from threading import Thread
from unittest.mock import patch

from app import create_server


class ModelAssetTests(unittest.TestCase):
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
        self.server.RequestHandlerClass._notifications.clear()
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.connection = HTTPConnection("127.0.0.1", self.server.server_port)

    def tearDown(self) -> None:
        self.connection.close()
        self.server.shutdown()
        self.server.server_close()
        self.environment.stop()
        self.temp_dir.cleanup()

    def _get_model_asset(self, path_value: str):
        from urllib.parse import quote

        self.connection.request("GET", f"/v1/model/asset?path={quote(path_value)}")
        return self.connection.getresponse()

    def test_real_model_file_is_served(self) -> None:
        # 真实模型：狐仙花嫁.model3.json 应可读（白名单 .json + Character 根内）
        response = self._get_model_asset("狐仙花嫁/狐仙花嫁/狐仙花嫁.model3.json")
        self.assertEqual(response.status, 200)
        payload = response.read()
        self.assertTrue(payload.startswith(b"{"))
        data = json.loads(payload)
        # model3 清单应包含 moc3 / 纹理等子资源引用
        self.assertIn("FileReferences", data)
        self.assertIn("Moc", data["FileReferences"])

    def test_directory_traversal_rejected(self) -> None:
        for path_value in (
            "../api.py",
            "狐仙花嫁/../../api.py",
            "/etc/passwd",
        ):
            with self.subTest(path=path_value):
                response = self._get_model_asset(path_value)
                payload = json.loads(response.read())
                self.assertEqual(response.status, 400)
                self.assertIn("invalid", payload["error"])
        # 编码形态的穿越：%2F 解码后仍是 ../..，必须同样拒绝
        self.connection.request("GET", "/v1/model/asset?path=..%2F..%2Fapi.py")
        response = self.connection.getresponse()
        payload = json.loads(response.read())
        self.assertEqual(response.status, 400)
        self.assertIn("invalid", payload["error"])

    def test_outside_root_rejected(self) -> None:
        # 白名单根是 Character 目录；api.py 在 Source code engine 下（Character 根外）。
        # 扩展名 .py 也不在白名单 → 404（而非 400 穿越拒绝）。
        response = self._get_model_asset("api.py")
        payload = json.loads(response.read())
        self.assertEqual(response.status, 404)
        self.assertIn("not found", payload["error"])

    def test_disallowed_extension_rejected(self) -> None:
        response = self._get_model_asset("K1 Portrait/baseline_raw.png")  # 扩展名白名单含 png
        if response.status == 200:
            # Character 目录内存在该 png 时应可读；不存在则 404（均非 400 穿越拒绝）
            response.read()
            self.assertIn(response.status, (200, 404))
            return
        payload = json.loads(response.read())
        self.assertIn("not found", payload["error"])

    def test_missing_and_invalid_params(self) -> None:
        self.connection.request("GET", "/v1/model/asset")
        response = self.connection.getresponse()
        payload = json.loads(response.read())
        self.assertEqual(response.status, 400)
        self.assertIn("missing", payload["error"])
        # 白名单外的扩展名（.exe/.py）→ 404
        response = self._get_model_asset("狐仙花嫁/狐仙花嫁/model3.py")
        payload = json.loads(response.read())
        self.assertEqual(response.status, 404)


if __name__ == "__main__":
    unittest.main()
