"""Application entry point for the local AI service."""

import argparse
import os
from http.server import ThreadingHTTPServer
from pathlib import Path

from api import ApiHandler
from audit import AuditLog
from avatars import AvatarSystem
from agent_tools import TOOL_CATALOG
from inference import InferenceEngine
from character import CharacterStore
from speech import SpeechService


def _is_loopback_host(host: str) -> bool:
    return host.lower() in {"localhost", "127.0.0.1", "::1"}


def create_server(host: str = "127.0.0.1", port: int = 8000) -> ThreadingHTTPServer:
    ApiHandler.engine = InferenceEngine.from_environment()
    project_root = Path(__file__).resolve().parent.parent
    character_root = project_root / "Character"
    # 阶段 0 审计日志：默认落 Logs & Checkpoints/logs/，可用 MOLING_LOG_DIR 覆盖（测试隔离）。
    ApiHandler.audit_log = AuditLog(
        os.getenv("MOLING_LOG_DIR", str(project_root / "Logs & Checkpoints" / "logs"))
    )
    ApiHandler.character_store = CharacterStore(
        os.getenv(
            "CHARACTER_CARD_PATH",
            str(character_root / "characters" / "default.json"),
        ),
        os.getenv("CHARACTER_MEMORY_PATH", str(character_root / "memory.json")),
        os.getenv("CHARACTER_ASSET_DIR", str(character_root / "assets")),
        os.getenv("CHARACTER_PRIVACY_PATH", str(character_root / "privacy.json")),
        os.getenv("CHARACTER_AFFECT_PATH", str(character_root / "affect.json")),
    )
    ApiHandler.workspace_root = Path(
        os.getenv(
            "WORKSPACE_ROOT",
            str(Path(__file__).resolve().parents[3]),
        )
    ).resolve()
    ApiHandler.tool_capability = os.getenv("MOLING_TOOL_CAPABILITY", "")
    ApiHandler.vision_capability = os.getenv("MOLING_VISION_CAPABILITY", "")
    ApiHandler.tool_catalog = TOOL_CATALOG
    ApiHandler.speech_service = SpeechService()
    ApiHandler._avatar_system = AvatarSystem(
        os.getenv("AVATAR_REGISTRY_PATH", str(character_root / "avatars.json")),
        os.getenv("AVATAR_AWAKEN_LOG_PATH", str(character_root / "awaken_log.json")),
        os.getenv("AVATAR_TOOL_LOG_PATH", str(character_root / "tool_log.json")),
        ApiHandler.character_store,
    )
    return ThreadingHTTPServer((host, port), ApiHandler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local AI service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    args = parser.parse_args()
    if not _is_loopback_host(args.host):
        # 阶段 0 边界：显式远程监听必须单独配置认证，启动前给醒目警告。
        print(
            "[!] 警告：正在监听非回环地址，API 将对局域网/外部可达。"
            " 服务无内置认证，除本机外对任何来源都未授权；"
            " 建议仅在受信网络内使用，并自行加装认证/防火墙。",
            flush=True,
        )
    server = create_server(args.host, args.port)
    print(f"AI service listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()