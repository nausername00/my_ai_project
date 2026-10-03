"""Convert a local transformers model to GGUF (llama.cpp format).

GGUF conversion needs the llama.cpp toolchain:

- ``convert_hf_to_gguf.py``  (HF -> GGUF)
- ``llama-quantize`` / ``llama-quantize.exe``  (optional quantization)

Set ``LLAMA_CPP_DIR`` to the llama.cpp checkout, or pass ``--llama-cpp-dir``.
If the toolchain is not found, the script prints the exact setup commands and
exits nonzero — it never fabricates a converted file.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from inference import ModelUnavailableError


def _find_llama_cpp(directory: str | None) -> Path:
    candidates: list[Path] = []
    if directory:
        candidates.append(Path(directory).expanduser())
    if os.getenv("LLAMA_CPP_DIR"):
        candidates.append(Path(os.getenv("LLAMA_CPP_DIR") or "").expanduser())
    for candidate in candidates:
        converter = candidate / "convert_hf_to_gguf.py"
        if converter.is_file():
            return candidate
    raise ModelUnavailableError(
        "llama.cpp 工具链未找到。请先获取 llama.cpp：\n"
        "  git clone https://github.com/ggml-org/llama.cpp\n"
        "  或将 LLAMA_CPP_DIR 环境变量指向 llama.cpp 目录（需包含 convert_hf_to_gguf.py）"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export a transformers model to GGUF via llama.cpp.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--model-path", required=True, help="transformers model directory")
    parser.add_argument("--output", default=None, help="output .gguf path")
    parser.add_argument("--quantize", default=None, help="quantization preset, e.g. q8_0 / q4_k_m")
    parser.add_argument("--llama-cpp-dir", default=None, help="path to a llama.cpp checkout")
    parser.add_argument("--device", default="cpu", help="unused; kept for export.py dispatch")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    llama_dir = _find_llama_cpp(args.llama_cpp_dir)
    model_path = Path(args.model_path).expanduser()
    if not model_path.is_dir():
        raise SystemExit(f"模型目录不存在: {model_path}")
    default_output = llama_dir / f"{model_path.name}.gguf"
    output = Path(args.output or default_output)
    output.parent.mkdir(parents=True, exist_ok=True)

    converter = llama_dir / "convert_hf_to_gguf.py"
    print(f"步骤 1/2：HF -> GGUF（{converter}）")
    command = [sys.executable, str(converter), str(model_path), "--outfile", str(output)]
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        raise SystemExit(f"convert_hf_to_gguf.py 失败，返回码 {result.returncode}")

    if args.quantize:
        quantizer = shutil.which("llama-quantize") or str(llama_dir / "llama-quantize.exe")
        quantized = output.with_name(f"{output.stem}-{args.quantize.lower()}.gguf")
        print(f"步骤 2/2：量化（{args.quantize}）-> {quantized}")
        result = subprocess.run([quantizer, str(output), str(quantized), args.quantize], check=False)
        if result.returncode != 0:
            raise SystemExit(f"llama-quantize 失败，返回码 {result.returncode}")
        print(f"量化模型: {quantized}")
    else:
        print(f"GGUF 模型: {output}")


if __name__ == "__main__":
    main()
