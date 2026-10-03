"""Training script for the local AI service.

Trains (or continues training) a Hugging Face causal language model on a
local dataset.  ``torch`` / ``transformers`` are loaded lazily: without them
the script prints a clear install hint and exits nonzero.

Dataset formats:

- JSON Lines: each line is ``{"text": "..."}`` (self-supervised) or
  ``{"prompt": "...", "completion": "..."}`` (instruction pairs).
- CSV: a ``text`` column, one document per row.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from typing import Any

from inference import ModelUnavailableError


def _require_ml() -> tuple[Any, Any, Any]:
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
    except ImportError as error:
        raise ModelUnavailableError(
            "training requires torch and transformers; install with: "
            "pip install -e \"Model Core/Weighting file (core fuel)/Engineering Config[model]\""
        ) from error
    from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments

    return torch, (AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Train a local causal language model.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--model-path", required=True, help="base transformers model directory")
    parser.add_argument("--dataset", required=True, help="JSON Lines or CSV dataset path")
    parser.add_argument("--output-dir", default="checkpoints", help="checkpoint output directory")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--max-length", type=int, default=512, help="token truncation length")
    parser.add_argument("--device", default=None, help="cuda | mps | cpu (auto when omitted)")
    parser.add_argument("--save-steps", type=int, default=500, help="save a checkpoint every N steps")
    parser.add_argument("--seed", type=int, default=42)
    return parser


def load_texts(path: str) -> list[str]:
    """Load ``text`` documents from a JSON Lines or CSV file.

    For JSON Lines, either ``text`` (self-supervised) or the
    ``prompt``+``completion`` pair (instruction) is supported.
    """
    dataset_path = Path(path)
    if not dataset_path.is_file():
        raise FileNotFoundError(f"dataset not found: {dataset_path}")
    texts: list[str] = []
    if dataset_path.suffix.lower() == ".csv":
        with dataset_path.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                value = (row.get("text") or "").strip()
                if value:
                    texts.append(value)
    else:
        with dataset_path.open(encoding="utf-8-sig") as handle:
            for line_number, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(f"invalid JSON on line {line_number}: {error}") from error
                if not isinstance(record, dict):
                    raise ValueError(f"line {line_number} must be a JSON object")
                if record.get("text"):
                    texts.append(str(record["text"]).strip())
                elif record.get("prompt") and record.get("completion"):
                    texts.append(f"{record['prompt']}\n{record['completion']}".strip())
    if not texts:
        raise ValueError("dataset contains no usable text documents")
    return texts


def main() -> None:
    args = build_parser().parse_args()
    torch, (AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments) = _require_ml()
    from model import resolve_device

    device = resolve_device(args.device)
    texts = load_texts(args.dataset)
    print(f"已加载 {len(texts)} 条文本，设备: {device}")

    model = AutoModelForCausalLM.from_pretrained(args.model_path)
    tokenizer = AutoTokenizer.from_pretrained(args.model_path)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model.train()

    encoded = tokenizer(
        texts,
        truncation=True,
        max_length=args.max_length,
        padding=True,
        return_tensors="pt",
    )

    dataset = torch.utils.data.TensorDataset(
        encoded["input_ids"],
        encoded["attention_mask"],
        encoded["input_ids"],  # labels = input_ids for causal LM
    )

    training_args = TrainingArguments(
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        save_steps=args.save_steps,
        save_total_limit=3,
        logging_steps=25,
        seed=args.seed,
        report_to=[],
        fp16=(device == "cuda" and torch.cuda.is_available()),
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
        tokenizer=tokenizer,
    )
    trainer.train()
    final_dir = os.path.join(args.output_dir, "final")
    trainer.save_model(final_dir)
    tokenizer.save_pretrained(final_dir)
    print(f"训练完成，模型已保存到: {final_dir}")


if __name__ == "__main__":
    main()
