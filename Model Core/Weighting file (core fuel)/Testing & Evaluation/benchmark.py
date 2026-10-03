"""Latency / throughput benchmark for the local AI service.

Runs ``--runs`` generations through a backend and reports p50 / p95 latency
and approximate tokens-per-second.  Works with every backend; the
``placeholder`` backend exercises the full measurement path without needing
an ML runtime.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time

from inference import GenerationRequest, InferenceEngine, ModelUnavailableError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Benchmark generation latency and throughput.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--backend", default=None, help="placeholder | ollama | transformers")
    parser.add_argument("--model-path", default=None, help="transformers model directory")
    parser.add_argument("--ollama-model", default=None, help="Ollama model name")
    parser.add_argument("--ollama-url", default=None, help="Ollama base URL")
    parser.add_argument("--prompt", default="你好，请简单介绍一下你自己。", help="benchmark prompt")
    parser.add_argument("--runs", type=int, default=5, help="number of generation runs")
    parser.add_argument("--max-tokens", type=int, default=64)
    parser.add_argument("--warmup", action="store_true", help="do one warm-up run first")
    parser.add_argument("--json", action="store_true", help="emit a JSON report")
    return parser


def _resolve_engine(args: argparse.Namespace) -> InferenceEngine:
    backend = (args.backend or os.getenv("MODEL_BACKEND", "placeholder")).strip().lower()
    if backend == "transformers":
        from inference import TransformersBackend

        model_path = args.model_path or os.getenv("MODEL_PATH", "").strip()
        if not model_path:
            raise ModelUnavailableError("transformers backend requires --model-path or $MODEL_PATH")
        return InferenceEngine(TransformersBackend(model_path))
    if backend == "ollama":
        from inference import OllamaBackend

        model = args.ollama_model or os.getenv("OLLAMA_MODEL", "").strip()
        url = args.ollama_url or os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").strip()
        return InferenceEngine(OllamaBackend(model, url))
    if backend == "placeholder":
        return InferenceEngine()
    raise ValueError(f"unsupported --backend: {backend!r}")


def main() -> None:
    args = build_parser().parse_args()
    if args.runs < 1:
        raise SystemExit("--runs must be >= 1")
    engine = _resolve_engine(args)
    request = GenerationRequest(prompt=args.prompt, max_tokens=args.max_tokens)

    if args.warmup:
        try:
            engine.generate(request)
        except Exception as error:  # noqa: BLE001 - benchmark must not abort on warmup failure
            print(f"[警告] warmup 失败（继续）：{error}")

    latencies: list[float] = []
    outputs: list[str] = []
    for index in range(args.runs):
        start = time.perf_counter()
        try:
            text = engine.generate(request)
        except (ModelUnavailableError, ValueError, TypeError) as error:
            print(f"[错误] 第 {index + 1} 次运行失败: {error}")
            continue
        latencies.append((time.perf_counter() - start) * 1000.0)
        outputs.append(text)

    if not latencies:
        raise SystemExit("没有成功的运行，无法生成报告")

    characters = sum(len(text) for text in outputs)
    # 中文文本按空格分词会严重低估 token 数（整段中文只算 1-2 个"词"）。
    # 改用字符数估算：中文近似 1.5 字符/token，且每轮不超过 --max-tokens
    # （后端实际生成上限），避免估算超过真实输出。
    estimated_tokens = sum(
        min(args.max_tokens, max(1, round(len(text) / 1.5))) for text in outputs
    )
    total_seconds = sum(latencies) / 1000.0
    tokens_per_second = estimated_tokens / total_seconds if total_seconds > 0 else 0.0
    report = {
        "backend": engine.model_name,
        "runs": len(latencies),
        "latency_ms": {
            "p50": round(statistics.median(latencies), 2),
            "p95": round(sorted(latencies)[int(len(latencies) * 0.95) - 1], 2)
            if len(latencies) >= 20
            else round(max(latencies), 2),
            "mean": round(statistics.fmean(latencies), 2),
            "min": round(min(latencies), 2),
            "max": round(max(latencies), 2),
        },
        "output_stats": {
            "characters": characters,
            "estimated_tokens": estimated_tokens,
            "token_estimate_rule": "chars/1.5 per run, capped at --max-tokens",
        },
        "tokens_per_second": round(tokens_per_second, 2),
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"后端: {report['backend']}  运行次数: {report['runs']}")
        print(f"延迟(ms): p50={report['latency_ms']['p50']}  "
              f"p95={report['latency_ms']['p95']}  mean={report['latency_ms']['mean']}  "
              f"min={report['latency_ms']['min']}  max={report['latency_ms']['max']}")
        print(f"输出统计: {report['output_stats']}")
        print(f"吞吐(估算): {report['tokens_per_second']} tokens/s")


if __name__ == "__main__":
    main()
