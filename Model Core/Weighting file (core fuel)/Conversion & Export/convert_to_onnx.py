"""Convert a local transformers model to ONNX.

Uses ``torch.onnx.export`` with dynamic sequence length so the exported graph
accepts arbitrary input lengths.  ``torch`` / ``transformers`` are loaded
lazily; without them the script prints an install hint and exits nonzero.

Typical usage::

    py -3 convert_to_onnx.py --model-path "C:/models/my-model" --output model.onnx
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from inference import ModelUnavailableError


def _require_ml() -> tuple[Any, Any]:
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
    except ImportError as error:
        raise ModelUnavailableError(
            "ONNX export requires torch and transformers; install with: "
            "pip install -e \"Model Core/Weighting file (core fuel)/Engineering Config[model]\""
        ) from error
    return torch, transformers


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export a transformers causal LM to ONNX.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--model-path", required=True, help="transformers model directory")
    parser.add_argument("--output", default=None, help="output .onnx path")
    parser.add_argument("--max-length", type=int, default=512, help="static max sequence length")
    parser.add_argument("--opset", type=int, default=14, help="ONNX opset version")
    parser.add_argument("--device", default="cpu", help="cuda | mps | cpu")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    torch, transformers = _require_ml()
    from model import load_model

    model_path = Path(args.model_path).expanduser()
    output = Path(args.output or (model_path.parent / "model.onnx"))
    output.parent.mkdir(parents=True, exist_ok=True)

    print(f"正在加载模型: {model_path} ...")
    model, tokenizer = load_model(model_path, device=args.device)
    model.to(args.device).eval()

    dummy_input = tokenizer("示例输入", return_tensors="pt").to(args.device)
    input_names = list(dummy_input.keys())
    dynamic_axes = {
        name: {0: "batch", 1: "sequence"}
        for name in input_names
        if dummy_input[name].dim() > 1
    }

    print(f"正在导出 ONNX（opset {args.opset}）...")
    with torch.no_grad():
        torch.onnx.export(
            model,
            tuple(dummy_input.values()),
            str(output),
            input_names=input_names,
            output_names=["logits"],
            dynamic_axes=dynamic_axes,
            opset_version=args.opset,
            do_constant_folding=True,
        )
    print(f"导出完成: {output} ({output.stat().st_size / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    main()
