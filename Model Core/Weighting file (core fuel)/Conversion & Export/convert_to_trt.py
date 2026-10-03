"""Convert a local transformers model to TensorRT.

Pipeline: transformers model -> ONNX -> TensorRT engine.

- The ONNX step reuses the same export path as ``convert_to_onnx``.
- The ONNX -> TensorRT step uses either ``trtexec`` (CLI) or the Python
  ``tensorrt`` package; at least one of them must be installed.

Dependencies are loaded lazily and the script prints exact install commands
when they are missing.
"""

from __future__ import annotations

import argparse
import importlib.util
import shutil
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
            "TensorRT export requires torch and transformers; install with: "
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
        description="Export a transformers model to a TensorRT engine (via ONNX).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--model-path", required=True, help="transformers model directory")
    parser.add_argument("--output", default=None, help="output .engine path")
    parser.add_argument("--quantize", default=None, help="optional: fp16 (or leave empty for fp32)")
    parser.add_argument("--device", default="cpu", help="cuda | mps | cpu")
    parser.add_argument("--max-length", type=int, default=512, help="static sequence length for TRT")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    _require_ml()
    model_path = Path(args.model_path).expanduser()
    if not model_path.is_dir():
        raise SystemExit(f"模型目录不存在: {model_path}")
    output = Path(args.output or (model_path.parent / "model.engine"))
    onnx_file = output.with_suffix(".onnx")

    print(f"步骤 1/2：导出 ONNX -> {onnx_file}")
    _export_onnx(model_path, onnx_file, args.device)

    print("步骤 2/2：ONNX -> TensorRT engine")
    trtexec = shutil.which("trtexec")
    if trtexec:
        command = [
            trtexec,
            f"--onnx={onnx_file}",
            f"--saveEngine={output}",
            f"--maxShapes=input_ids:1x{args.max_length},attention_mask:1x{args.max_length}",
        ]
        if (args.quantize or "").lower() == "fp16":
            command.append("--fp16")
        result = subprocess.run(command, check=False)
        if result.returncode != 0:
            raise SystemExit(f"trtexec 失败，返回码 {result.returncode}")
    elif importlib.util.find_spec("tensorrt"):
        import tensorrt as trt

        logger = trt.Logger(trt.Logger.WARNING)
        builder = trt.Builder(logger)
        network = builder.create_network(1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH))
        parser = trt.OnnxParser(network, logger)
        if not parser.parse_from_file(str(onnx_file)):
            errors = [parser.get_error(index) for index in range(parser.num_errors)]
            raise SystemExit(f"TensorRT ONNX 解析失败: {errors}")
        config = builder.create_builder_config()
        if (args.quantize or "").lower() == "fp16" and builder.platform_has_fast_fp16:
            config.set_flag(trt.BuilderFlag.FP16)
        engine = builder.build_engine(network, config)
        if engine is None:
            raise SystemExit("TensorRT 引擎构建失败")
        with open(output, "wb") as handle:
            handle.write(engine.serialize())
    else:
        raise SystemExit(
            "未找到 TensorRT 转换工具。请安装：\n"
            "  1) NVIDIA TensorRT 并确保 trtexec 在 PATH 中；或\n"
            "  2) pip install tensorrt（需匹配本机 CUDA 版本）"
        )
    print(f"TensorRT engine: {output}")


if __name__ == "__main__":
    main()
