"""Generative evaluation: run prompts through a backend and score the outputs.

Reads a JSON Lines file of evaluation items, where each line is either

- ``{"prompt": "...", "reference": "..."}`` (expected answer), or
- ``{"prompt": "...", "completion": "..."}`` (expected continuation).

Every prompt is sent to the configured backend and the generated text is
scored against the reference with exact-match / token accuracy / F1 / BLEU.
The ``placeholder`` backend exercises the whole pipeline with zero ML
dependencies; use ``--backend ollama`` or ``--backend transformers`` for a
real model.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from inference import GenerationRequest, InferenceEngine, ModelUnavailableError

from metrics import summarize_metrics


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a generative evaluation set through a backend.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("dataset", help="JSON Lines evaluation file")
    parser.add_argument("--backend", default=None, help="placeholder | ollama | transformers")
    parser.add_argument("--model-path", default=None, help="transformers model directory")
    parser.add_argument("--ollama-model", default=None, help="Ollama model name")
    parser.add_argument("--ollama-url", default=None, help="Ollama base URL")
    parser.add_argument("--max-tokens", type=int, default=128)
    parser.add_argument("--limit", type=int, default=None, help="only evaluate the first N items")
    parser.add_argument("--output", default=None, help="write the full per-item JSON report here")
    return parser


def load_items(path: str) -> list[dict[str, Any]]:
    dataset = Path(path)
    if not dataset.is_file():
        raise FileNotFoundError(f"evaluation file not found: {dataset}")
    items: list[dict[str, Any]] = []
    with dataset.open(encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSON on line {line_number}: {error}") from error
            if not isinstance(record, dict) or not record.get("prompt"):
                raise ValueError(f"line {line_number} must be an object with a 'prompt' field")
            items.append(record)
    return items


def main() -> None:
    args = build_parser().parse_args()
    items = load_items(args.dataset)
    if args.limit is not None:
        items = items[: args.limit]
    if not items:
        raise SystemExit("no evaluation items")

    backend = (args.backend or os.getenv("MODEL_BACKEND", "placeholder")).strip().lower()
    if backend == "transformers":
        from inference import TransformersBackend

        model_path = args.model_path or os.getenv("MODEL_PATH", "").strip()
        if not model_path:
            raise ModelUnavailableError("transformers backend requires --model-path or $MODEL_PATH")
        engine = InferenceEngine(TransformersBackend(model_path))
    elif backend == "ollama":
        from inference import OllamaBackend

        model = args.ollama_model or os.getenv("OLLAMA_MODEL", "").strip()
        url = args.ollama_url or os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").strip()
        engine = InferenceEngine(OllamaBackend(model, url))
    elif backend == "placeholder":
        engine = InferenceEngine()
    else:
        raise SystemExit(f"unsupported --backend: {backend!r}")

    references: list[str] = []
    hypotheses: list[str] = []
    per_item: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        prompt = str(item["prompt"])
        reference = str(item.get("reference", item.get("completion", "")))
        request = GenerationRequest(prompt=prompt, max_tokens=args.max_tokens)
        try:
            generated = engine.generate(request)
        except (ModelUnavailableError, ValueError, TypeError) as error:
            print(f"[错误] 第 {index} 项生成失败: {error}")
            generated = ""
        references.append(reference)
        hypotheses.append(generated)
        per_item.append({"prompt": prompt, "reference": reference, "generated": generated})

    summary = summarize_metrics(references, hypotheses)
    report = {"backend": engine.model_name, "items": len(per_item), "metrics": summary}
    if args.output:
        report["details"] = per_item
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"报告已写入: {output}")
    else:
        print(json.dumps({"backend": engine.model_name, "items": len(per_item), "metrics": summary},
                         ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
