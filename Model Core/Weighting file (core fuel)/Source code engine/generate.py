"""Command-line generation tool for the local AI service.

Runs a single prompt (or an interactive session) through any configured
backend: ``placeholder`` (zero dependencies), ``ollama`` (local service), or
``transformers`` (local torch model).  ``transformers`` is loaded lazily so the
tool keeps working on machines without ML dependencies.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from inference import GenerationRequest, InferenceEngine, ModelUnavailableError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate text through the local AI service backends.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--backend", default=None, help="placeholder | ollama | transformers (defaults to $MODEL_BACKEND)")
    parser.add_argument("--model-path", default=None, help="transformers model directory (MODEL_PATH)")
    parser.add_argument("--ollama-model", default=None, help="Ollama model name (OLLAMA_MODEL)")
    parser.add_argument("--ollama-url", default=None, help="Ollama base URL (OLLAMA_URL)")
    parser.add_argument("--prompt", default=None, help="single prompt to generate; omit for interactive mode")
    parser.add_argument("--max-tokens", type=int, default=128, help="maximum tokens to generate (1-4096)")
    parser.add_argument("--system-prompt", default="", help="optional system prompt")
    parser.add_argument("--json-mode", action="store_true", help="request JSON-formatted output")
    parser.add_argument("--temperature", type=float, default=None, help="sampling temperature (model-dependent)")
    parser.add_argument("--image", default=None, help="path to an image for loopback vision models (max 10 MB)")
    return parser


def _resolve_engine(args: argparse.Namespace) -> InferenceEngine:
    """Build an engine honoring CLI overrides on top of the environment."""
    backend = (args.backend or os.getenv("MODEL_BACKEND", "placeholder")).strip().lower()
    if backend == "transformers":
        model_path = args.model_path or os.getenv("MODEL_PATH", "").strip()
        if not model_path:
            raise ModelUnavailableError("transformers backend requires --model-path or $MODEL_PATH")
        from inference import TransformersBackend

        return InferenceEngine(TransformersBackend(model_path))
    if backend == "ollama":
        from inference import OllamaBackend

        model = args.ollama_model or os.getenv("OLLAMA_MODEL", "").strip()
        url = args.ollama_url or os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").strip()
        return InferenceEngine(OllamaBackend(model, url))
    if backend == "placeholder":
        return InferenceEngine()
    raise ValueError(f"unsupported --backend: {backend!r} (expected placeholder, ollama, or transformers)")


def _read_image(path: str) -> bytes | None:
    if path is None:
        return None
    with open(path, "rb") as handle:
        data = handle.read()
    if len(data) > 10 * 1024 * 1024:
        raise ValueError("image exceeds the 10 MB analysis limit")
    return data


def run_once(engine: InferenceEngine, args: argparse.Namespace, prompt: str) -> None:
    image = _read_image(args.image)
    request = GenerationRequest(
        prompt=prompt,
        max_tokens=args.max_tokens,
        system_prompt=args.system_prompt,
        json_mode=args.json_mode,
        temperature=args.temperature,
    )
    text = engine.generate(request, image=image)
    if args.json_mode:
        try:
            print(json.dumps(json.loads(text), ensure_ascii=False, indent=2))
            return
        except (json.JSONDecodeError, TypeError):
            pass  # fall through: print raw text
    print(text)


def run_interactive(engine: InferenceEngine, args: argparse.Namespace) -> None:
    print(f"墨灵生成工具 — 后端: {engine.model_name}（输入 exit / Ctrl+C 退出）")
    while True:
        try:
            prompt = input("\nprompt> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not prompt or prompt.lower() in {"exit", "quit"}:
            return
        try:
            run_once(engine, args, prompt)
        except (ModelUnavailableError, ValueError, TypeError) as error:
            print(f"[错误] {error}", file=sys.stderr)


def main() -> None:
    args = build_parser().parse_args()
    if args.max_tokens < 1 or args.max_tokens > 4096:
        raise SystemExit("--max-tokens must be between 1 and 4096")
    try:
        engine = _resolve_engine(args)
    except (ModelUnavailableError, ValueError) as error:
        print(f"[错误] {error}", file=sys.stderr)
        raise SystemExit(1)
    if args.prompt is not None:
        try:
            run_once(engine, args, args.prompt)
        except (ModelUnavailableError, ValueError, TypeError) as error:
            print(f"[错误] {error}", file=sys.stderr)
            raise SystemExit(1)
    else:
        run_interactive(engine, args)


if __name__ == "__main__":
    main()
