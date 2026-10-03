"""Model utilities for the local AI service.

This module provides a small toolkit around Hugging Face ``transformers``
models: lazy dependency loading, model/tokenizer loading, device selection,
parameter counting, model description, and checkpoint saving.

The service remains dependency-light: ``torch`` / ``transformers`` are only
imported inside functions, and every entry point raises a clear error when
they are missing, so the rest of the project keeps working with zero ML
dependencies (placeholder / Ollama backends).
"""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
from typing import Any

from inference import ModelUnavailableError


def require_torch() -> tuple[Any, Any]:
    """Import ``torch`` and ``transformers`` lazily.

    Returns:
        A ``(torch, transformers)`` module pair.

    Raises:
        ModelUnavailableError: if either package is not installed; the
            message tells the user to install the ``model`` extra.
    """
    try:
        torch = importlib.import_module("torch")
        transformers = importlib.import_module("transformers")
    except ImportError as error:
        raise ModelUnavailableError(
            "torch and transformers are required for model operations; "
            "install them with:  pip install -e \"Model Core/Weighting file (core fuel)/Engineering Config[model]\""
        ) from error
    return torch, transformers


def resolve_device(preferred: str | None = None) -> str:
    """Pick the best available compute device.

    Order of preference: explicit argument, CUDA, Apple MPS, CPU.
    """
    torch, _ = require_torch()
    if preferred:
        device = preferred.strip().lower()
        if device in {"cuda", "mps", "cpu"}:
            if device == "cuda" and not torch.cuda.is_available():
                raise ModelUnavailableError("cuda was requested but torch.cuda.is_available() is False")
            if device == "mps" and not (hasattr(torch.backends, "mps") and torch.backends.mps.is_available()):
                raise ModelUnavailableError("mps was requested but is not available on this machine")
            return device
        raise ValueError(f"unsupported device: {preferred!r} (expected cuda, mps, or cpu)")
    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def load_model(
    model_path: str | os.PathLike[str],
    *,
    device: str | None = None,
    torch_dtype: str | None = None,
) -> tuple[Any, Any]:
    """Load a causal language model and its tokenizer from a directory.

    Args:
        model_path: path to a directory containing a transformers model
            (``config.json`` plus weights, or sharded ``model-*.safetensors``).
        device: optional ``cuda`` / ``mps`` / ``cpu``; auto-detected when None.
        torch_dtype: optional dtype name such as ``auto``, ``float16``, ``bfloat16``.
            ``auto`` resolves to the dtype stored in ``config.json``.

    Returns:
        A ``(model, tokenizer)`` tuple; the model is in evaluation mode.
    """
    path = Path(model_path).expanduser()
    if not path.exists():
        raise ModelUnavailableError(f"model path does not exist: {path}")
    if not path.is_dir():
        raise ModelUnavailableError(f"model path must be a directory: {path}")
    torch, transformers = require_torch()
    config_file = path / "config.json"
    if not config_file.is_file():
        raise ModelUnavailableError(
            f"model directory has no config.json: {path} (is this a transformers model directory?)"
        )
    resolved_device = resolve_device(device)
    try:
        tokenizer = transformers.AutoTokenizer.from_pretrained(str(path))
        dtype: Any = None
        if torch_dtype:
            dtype = {
                "auto": "auto",
                "float16": torch.float16,
                "bfloat16": torch.bfloat16,
                "float32": torch.float32,
            }.get(torch_dtype.strip().lower())
            if dtype is None:
                raise ValueError(f"unsupported torch_dtype: {torch_dtype!r}")
        kwargs: dict[str, Any] = {}
        if dtype is not None:
            kwargs["torch_dtype"] = dtype
        model = transformers.AutoModelForCausalLM.from_pretrained(str(path), **kwargs)
        if resolved_device == "cpu":
            model = model.to("cpu")
        model.eval()
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        raise ModelUnavailableError(f"failed to load model from {path}: {error}") from error
    return model, tokenizer


def count_parameters(model: Any) -> dict[str, Any]:
    """Return total/trainable parameter counts for a torch model."""
    require_torch()
    total = 0
    trainable = 0
    for parameter in model.parameters():
        count = parameter.numel()
        total += count
        if parameter.requires_grad:
            trainable += count
    return {
        "total": int(total),
        "trainable": int(trainable),
        "total_human": _human_count(total),
        "trainable_human": _human_count(trainable),
    }


def describe_model(model: Any) -> dict[str, Any]:
    """Build a plain-JSON summary of a loaded model for logs or API output."""
    require_torch()
    parameters = count_parameters(model)
    config = getattr(model, "config", None)
    return {
        "class": type(model).__name__,
        "parameters": parameters,
        "dtype": str(next(model.parameters()).dtype) if any(model.parameters()) else None,
        "device": str(next(model.parameters()).device) if any(model.parameters()) else None,
        "max_position_embeddings": getattr(config, "max_position_embeddings", None),
        "vocab_size": getattr(config, "vocab_size", None),
        "num_hidden_layers": getattr(config, "num_hidden_layers", None),
        "hidden_size": getattr(config, "hidden_size", None),
        "num_attention_heads": getattr(config, "num_attention_heads", None),
    }


def save_checkpoint(
    model: Any,
    tokenizer: Any,
    output_dir: str | os.PathLike[str],
    *,
    step: int | None = None,
    include_optimizer: bool = False,
    optimizer: Any = None,
) -> str:
    """Save model + tokenizer (and optionally optimizer state) to a directory.

    Returns the final output directory path.
    """
    torch, _ = require_torch()
    base = Path(output_dir).expanduser()
    target = base / f"checkpoint-{step}" if step is not None else base
    target.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(target), safe_serialization=True)
    tokenizer.save_pretrained(str(target))
    if include_optimizer and optimizer is not None:
        torch.save(optimizer.state_dict(), target / "optimizer.pt")
    with (target / "checkpoint_meta.json").open("w", encoding="utf-8") as handle:
        json.dump({"step": step, "framework": "transformers"}, handle, ensure_ascii=False, indent=2)
    return str(target)


def _human_count(count: int) -> str:
    """Format an integer count as 1.23B / 456.7M / 12.3K style."""
    if count >= 1_000_000_000:
        return f"{count / 1_000_000_000:.2f}B"
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count / 1_000:.1f}K"
    return str(count)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Describe a local transformers model directory")
    parser.add_argument("model_path", help="path to a transformers model directory")
    parser.add_argument("--device", default=None, help="cuda | mps | cpu (auto when omitted)")
    args = parser.parse_args()

    model, tokenizer = load_model(args.model_path, device=args.device)
    summary = describe_model(model)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
