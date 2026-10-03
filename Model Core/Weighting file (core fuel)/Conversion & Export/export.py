"""Unified model export entry point.

Dispatches to the per-format converters:

- ``onnx``  -> ``convert_to_onnx`` (torch.onnx export)
- ``gguf``  -> ``convert_to_gguf`` (llama.cpp toolchain)
- ``tflite``-> ``convert_to_tflite`` (ONNX -> TFLite toolchain)
- ``trt``   -> ``convert_to_trt``   (TensorRT toolchain)

Each converter loads ``torch`` / ``transformers`` lazily and prints a clear
install hint when dependencies are missing.
"""

from __future__ import annotations

import argparse
import importlib
import sys

from inference import ModelUnavailableError

_CONVERTERS = ("onnx", "gguf", "tflite", "trt")


def _load_converter(name: str):
    try:
        return importlib.import_module(f"convert_to_{name}")
    except ImportError as error:
        raise ModelUnavailableError(f"converter module convert_to_{name} is unavailable: {error}") from error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export a local transformers model to a deployment format.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("format", choices=_CONVERTERS, help="target format")
    parser.add_argument("--model-path", required=True, help="transformers model directory")
    parser.add_argument("--output", default=None, help="output file or directory (per-format default)")
    parser.add_argument("--quantize", default=None, help="quantization preset, e.g. q8_0 for gguf")
    parser.add_argument("--device", default="cpu", help="device used during conversion (cuda/mps/cpu)")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    converter = _load_converter(args.format)
    entry = getattr(converter, "main", None)
    if entry is None:
        raise SystemExit(f"converter {args.format} does not expose main()")
    # Re-parse with the sub-converter's own parser while passing shared args.
    sys.argv = [
        sys.argv[0],
        "--model-path", args.model_path,
    ]
    if args.output:
        sys.argv += ["--output", args.output]
    if args.quantize:
        sys.argv += ["--quantize", args.quantize]
    sys.argv += ["--device", args.device]
    entry()


if __name__ == "__main__":
    main()
