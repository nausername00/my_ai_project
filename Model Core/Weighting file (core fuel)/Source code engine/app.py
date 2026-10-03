"""Application entry point for the local AI service."""

import argparse
import os
from http.server import ThreadingHTTPServer
from pathlib import Path

from api import ApiHandler
from agent_tools import TOOL_CATALOG
from inference import InferenceEngine
from character import CharacterStore
from speech import SpeechService


def create_server(host: str = "127.0.0.1", port: int = 8000) -> ThreadingHTTPServer:
    ApiHandler.engine = InferenceEngine.from_environment()
    character_root = Path(__file__).resolve().parent.parent / "Character"
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
    ApiHandler.tool_catalog = TOOL_CATALOG
    ApiHandler.speech_service = SpeechService()
    return ThreadingHTTPServer((host, port), ApiHandler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local AI service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    args = parser.parse_args()
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