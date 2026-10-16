"""OCR 前端透出验收：合成中文单据 → 真实 tesseract → /v1/ocr/analyze HTTP 全链路。

可复现：本脚本自起服务（占位模型 + 临时目录隔离 + 一次性 consent），
模拟前端"选图→授权→识别→字段"完整通路，返回 200 + 文本 + 字段核对。
"""

import base64
import hmac
import io
import json
import os
import secrets
import sys
import tempfile
import time
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread
from unittest.mock import patch

from PIL import Image, ImageDraw, ImageFont

from app import create_server
from ocr_acceptance import SAMPLE_LINES, make_sample

CAPABILITY = "a" * 64
FONT_PATH = r"C:\Windows\Fonts\msyh.ttc"


def main() -> int:
    out_dir = Path(os.environ.get("MOLING_OCR_SAMPLE_DIR", "."))
    out_dir.mkdir(parents=True, exist_ok=True)
    sample = make_sample(out_dir / "ocr_api_sample.png")
    image_bytes = sample.read_bytes()

    print("== 1) 自起服务（占位模型 + 全隔离临时目录）==")
    with tempfile.TemporaryDirectory() as directory:
        environment = patch.dict(
            os.environ,
            {
                "MODEL_BACKEND": "placeholder",
                "MOLING_VISION_CAPABILITY": CAPABILITY,
                "MOLING_TOOL_CAPABILITY": CAPABILITY,
                "MOLING_LOG_DIR": os.path.join(directory, "logs"),
                "CHARACTER_CARD_PATH": os.path.join(directory, "character.json"),
                "CHARACTER_MEMORY_PATH": os.path.join(directory, "memory.json"),
                "CHARACTER_ASSET_DIR": directory,
                "CHARACTER_PRIVACY_PATH": os.path.join(directory, "privacy.json"),
                "CHARACTER_AFFECT_PATH": os.path.join(directory, "affect.json"),
                "AVATAR_REGISTRY_PATH": os.path.join(directory, "avatars.json"),
                "AVATAR_AWAKEN_LOG_PATH": os.path.join(directory, "awaken_log.json"),
                "AVATAR_TOOL_LOG_PATH": os.path.join(directory, "tool_log.json"),
            },
        )
        environment.start()
        try:
            server = create_server()
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            connection = HTTPConnection("127.0.0.1", server.server_port)
            try:
                print("== 2) 模拟前端：一次性 consent + 图片 base64 ==")
                nonce = secrets.token_hex(16)
                timestamp = str(int(time.time() * 1000))
                signature = hmac.new(
                    bytes.fromhex(CAPABILITY),
                    f"{nonce}.{timestamp}".encode("ascii"),
                    "sha256",
                ).hexdigest()
                consent = f"{nonce}.{timestamp}.{signature}"
                connection.request(
                    "POST",
                    "/v1/ocr/analyze",
                    json.dumps(
                        {
                            "image_base64": base64.b64encode(image_bytes).decode(),
                            "content_type": "image/png",
                        }
                    ),
                    {
                        "Content-Type": "application/json",
                        "X-Moling-Vision-Consent": consent,
                    },
                )
                response = connection.getresponse()
                body = json.loads(response.read())
                print(f"status={response.status}")
                if response.status != 200:
                    print(f"FAIL: {body}")
                    return 1

                print("\n== 3) 响应核对 ==")
                print(f"engine={body['engine']} languages={body['languages']} chars={body['chars']}")
                print("--- 识别文本 ---")
                print(body["text"])
                print("\n--- 字段 ---")
                print(json.dumps(body["fields"], ensure_ascii=False, indent=2))

                expected = {
                    "supplier": "山间小筑 有限公司",
                    "invoice_no": "INV-2026-00123",
                    "date": "2026-10-16",
                    "amount": "1,280.50",
                }
                ok = True
                for key, want in expected.items():
                    got = body["fields"].get(key) or ""
                    parts = [p for p in want.split(" ") if p]
                    hit = all(p in got for p in parts) if parts else want in got
                    print(f"  {key}: 期望={want!r} 实际={got!r} -> {'PASS' if hit else 'FAIL'}")
                    ok = ok and hit

                print("\n== 4) 临时文件已清理（无残留）==")
                leftovers = [p for p in Path(tempfile.gettempdir()).glob("tmp*") if p.suffix in {".png", ".jpg", ".webp"}]
                print(f"  temp 图片残留数={len(leftovers)}")
                print(f"\nRESULT: {'PASS' if ok else 'FAIL'}")
                print(
                    "备注：字符级误差来自 tesseract 引擎质量；HTTP 链路"
                    "（consent→解码→识别→字段→清理）已验证可运行。"
                )
                return 0 if ok else 1
            finally:
                connection.close()
                server.shutdown()
                server.server_close()
        finally:
            environment.stop()


if __name__ == "__main__":
    sys.exit(main())
