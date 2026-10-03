"""Fine-tuning script for the local AI service.

Fine-tunes a causal language model on a local dataset, with two modes:

- LoRA (default): requires the optional ``peft`` package; only adapter
  weights are trained, so memory usage is much lower.
- full: trains all parameters.

``torch`` / ``transformers`` (and optionally ``peft``) are loaded lazily so
the module can be imported on machines without ML dependencies.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from inference import ModelUnavailableError

from train import load_texts


def _require_ml(full_only: bool = False) -> tuple[Any, Any, Any, Any]:
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
    except ImportError as error:
        raise ModelUnavailableError(
            "fine-tuning requires torch and transformers; install with: "
            "pip install -e \"Model Core/Weighting file (core fuel)/Engineering Config[model]\""
        ) from error
    from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments

    peft = None
    if not full_only:
        try:
            import peft
        except ImportError:
            print("[提示] 未安装 peft，将退化为全参数微调（LoRA 需安装 peft）。")
    return torch, (AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments), peft, None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fine-tune a local causal language model (LoRA or full).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--model-path", required=True, help="base transformers model directory")
    parser.add_argument("--dataset", required=True, help="JSON Lines or CSV dataset path")
    parser.add_argument("--output-dir", default="finetuned", help="adapter/model output directory")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--lora-r", type=int, default=8, help="LoRA rank (LoRA mode only)")
    parser.add_argument("--lora-alpha", type=int, default=16, help="LoRA alpha (LoRA mode only)")
    parser.add_argument("--lora-dropout", type=float, default=0.05, help="LoRA dropout (LoRA mode only)")
    parser.add_argument("--full", action="store_true", help="train all parameters instead of LoRA")
    parser.add_argument("--device", default=None, help="cuda | mps | cpu (auto when omitted)")
    parser.add_argument("--seed", type=int, default=42)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    torch, (AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments), peft, _ = _require_ml(
        full_only=args.full
    )
    from model import resolve_device

    device = resolve_device(args.device)
    texts = load_texts(args.dataset)
    print(f"已加载 {len(texts)} 条文本，模式: {'全参数' if args.full else 'LoRA'}，设备: {device}")

    model = AutoModelForCausalLM.from_pretrained(args.model_path)
    tokenizer = AutoTokenizer.from_pretrained(args.model_path)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    trainable_before = sum(1 for p in model.parameters() if p.requires_grad)
    if not args.full and peft is not None:
        from peft import LoraConfig, get_peft_model

        config = LoraConfig(
            r=args.lora_r,
            lora_alpha=args.lora_alpha,
            lora_dropout=args.lora_dropout,
            task_type="CAUSAL_LM",
        )
        model = get_peft_model(model, config)
        model.print_trainable_parameters()
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
        encoded["input_ids"],
    )

    training_args = TrainingArguments(
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        save_strategy="epoch",
        logging_steps=25,
        seed=args.seed,
        report_to=[],
        fp16=(device == "cuda" and torch.cuda.is_available()),
    )
    trainer = Trainer(model=model, args=training_args, train_dataset=dataset, tokenizer=tokenizer)
    trainer.train()

    target = Path(args.output_dir)
    target.mkdir(parents=True, exist_ok=True)
    if not args.full and peft is not None:
        model.save_pretrained(str(target))
        tokenizer.save_pretrained(str(target))
        print(f"LoRA 适配器已保存到: {target}（使用前需与基础模型 {args.model_path} 合并或加载）")
    else:
        trainer.save_model(str(target))
        tokenizer.save_pretrained(str(target))
        print(f"全参数微调模型已保存到: {target}")
    with (target / "finetune_meta.json").open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "base_model": args.model_path,
                "mode": "lora" if (not args.full and peft is not None) else "full",
                "dataset": args.dataset,
                "epochs": args.epochs,
            },
            handle,
            ensure_ascii=False,
            indent=2,
        )


if __name__ == "__main__":
    main()
