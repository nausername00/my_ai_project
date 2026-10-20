"""Application entry point for the local AI service."""

import argparse
import ipaddress
import os
import ssl
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
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.split("%", 1)[0]).is_loopback
    except ValueError:
        return False


def validate_listener_security(
    host: str,
    *,
    api_token: str,
    tls_configured: bool,
    allow_insecure_lan: bool = False,
) -> None:
    """Require authentication and encrypted transport for non-loopback listeners."""
    if _is_loopback_host(host):
        return
    if not api_token.strip():
        raise ValueError("非本机监听必须设置 MOLING_API_TOKEN。")
    if not tls_configured and not allow_insecure_lan:
        raise ValueError(
            "非本机监听必须配置 TLS；如仅在可信局域网临时使用明文连接，"
            "请显式传入 --allow-insecure-lan。"
        )


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


def wrap_tls(server: ThreadingHTTPServer) -> ThreadingHTTPServer:
    """T4 系统层：TLS 挂载（默认关，零配置即明文 HTTP）。

    仅当同时配置 MOLING_TLS_CERT 与 MOLING_TLS_KEY（PEM 路径）时启用，
    证书生成见 scripts/setup_https.ps1（自签名 + 本机信任库）。
    """
    cert = os.environ.get("MOLING_TLS_CERT", "").strip()
    key = os.environ.get("MOLING_TLS_KEY", "").strip()
    if not cert or not key:
        if cert or key:
            raise ValueError("MOLING_TLS_CERT 与 MOLING_TLS_KEY 必须同时配置。")
        return server
    if not (Path(cert).is_file() and Path(key).is_file()):
        raise FileNotFoundError(
            f"TLS 证书/私钥不存在：{cert!r} / {key!r}（可运行 scripts\\setup_https.ps1 生成）"
        )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=cert, keyfile=key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local AI service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    parser.add_argument(
        "--allow-insecure-lan",
        action="store_true",
        help="显式允许非本机监听使用明文 HTTP（令牌与数据不会加密）",
    )
    args = parser.parse_args()
    tls_configured = bool(
        os.environ.get("MOLING_TLS_CERT", "").strip()
        and os.environ.get("MOLING_TLS_KEY", "").strip()
    )
    try:
        validate_listener_security(
            args.host,
            api_token=os.environ.get("MOLING_API_TOKEN", ""),
            tls_configured=tls_configured,
            allow_insecure_lan=args.allow_insecure_lan,
        )
    except ValueError as exc:
        parser.error(str(exc))
    if not _is_loopback_host(args.host) and not tls_configured:
        print(
            "[!] 明文局域网模式已显式启用：令牌和对话内容不会加密，请仅在可信网络使用。",
            flush=True,
        )
    server = wrap_tls(create_server(args.host, args.port))
    tls = os.environ.get("MOLING_TLS_CERT", "").strip() and os.environ.get(
        "MOLING_TLS_KEY", ""
    ).strip()
    scheme = "https" if tls else "http"
    print(f"AI service listening on {scheme}://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
