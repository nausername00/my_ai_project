"""Convert a local transformers model to TFLite.

Pipeline: transformers model -> ONNX -> TFLite flatbuffer.

- The ONNX step reuses the same export path as ``convert_to_onnx``.
- The ONNX -> TFLite step needs one of:
  - ``ai-edge-litert`` (Google's recommended converter), or
  - ``onnx2tf`` (converter that also handles dynamic shapes).

Dependencies are loaded lazily and the script prints exact install commands
when they are missing.
"""

from __future__ import annotations

import argparse
import importlib
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from inference import ModelUnavailableError


def _require_ml() -> tuple[Any, Any]:
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
    except ImportError as error:
        raise ModelUnavailableError(
            "TFLite export requires torch and transformers; install with: "
            "pip install -e \"Model Core/Weighting file (core fuel)/Engineering Config[model]\""
        ) from error
    return torch, transformers


def _export_onnx(model_path: Path, output: Path, device: str) -> None:
    """Run the shared ONNX export inside this package's converter."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from convert_to_onnx import main as onnx_main

    original_argv = sys.argv
    sys.argv = [
        "convert_to_onnx.py",
        "--model-path", str(model_path),
        "--output", str(output),
        "--device", device,
    ]
    try:
        onnx_main()
    finally:
        sys.argv = original_argv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export a transformers model to TFLite (via ONNX).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--model-path", required=True, help="transformers model directory")
    parser.add_argument("--output", default=None, help="output .tflite path")
    parser.add_argument("--quantize", default=None, help="optional: int8 (requires a calibration set)")
    parser.add_argument("--device", default="cpu", help="cuda | mps | cpu")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    _require_ml()
    model_path = Path(args.model_path).expanduser()
    if not model_path.is_dir():
        raise SystemExit(f"模型目录不存在: {model_path}")
    output = Path(args.output or (model_path.parent / "model.tflite"))
    onnx_file = output.with_suffix(".onnx")

    print(f"步骤 1/2：导出 ONNX -> {onnx_file}")
    _export_onnx(model_path, onnx_file, args.device)

    print("步骤 2/2：ONNX -> TFLite")
    if importlib.util.find_spec("onnx2tf"):
        result = subprocess.run(
            [sys.executable, "-m", "onnx2tf", "-i", str(onnx_file), "-o", str(output.parent)],
            check=False,
        )
        if result.returncode != 0:
            raise SystemExit(f"onnx2tf 失败，返回码 {result.returncode}")
    else:
        raise SystemExit(
            "未找到 ONNX->TFLite 转换器。请安装：\n"
            "  pip install onnx2tf onnx-graphsurgeon\n"
            "（或使用 Google 的 ai-edge-litert 转换器：pip install ai-edge-litert）"
        )
    print(f"TFLite 模型: {output}")


if __name__ == "__main__":
    main()
