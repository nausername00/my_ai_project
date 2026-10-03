"""Score a predictions file against references.

Reads a JSON Lines file where each line contains a ``reference`` and a
``hypothesis`` (or ``prediction``) field, then writes a JSON report of
exact-match / token accuracy / F1 / BLEU aggregated over the whole set.

This tool is pure computation (no model calls) and depends only on the
standard library plus this package's ``metrics`` module.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from metrics import summarize_metrics


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Score hypotheses against references from a JSON Lines file.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("predictions", help="JSON Lines file with reference + hypothesis fields")
    parser.add_argument("--output", default=None, help="JSON report output path")
    parser.add_argument("--no-bleu", action="store_true", help="skip BLEU computation")
    return parser


def load_pairs(path: str) -> tuple[list[str], list[str]]:
    predictions = Path(path)
    if not predictions.is_file():
        raise FileNotFoundError(f"predictions file not found: {predictions}")
    references: list[str] = []
    hypotheses: list[str] = []
    with predictions.open(encoding="utf-8-sig") as handle:
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
            reference = record.get("reference")
            hypothesis = record.get("hypothesis", record.get("prediction"))
            if not isinstance(reference, str) or not isinstance(hypothesis, str):
                raise ValueError(
                    f"line {line_number} needs string fields 'reference' and 'hypothesis'/'prediction'"
                )
            references.append(reference)
            hypotheses.append(hypothesis)
    if not references:
        raise ValueError("no pairs found in predictions file")
    return references, hypotheses


def main() -> None:
    args = build_parser().parse_args()
    references, hypotheses = load_pairs(args.predictions)
    report = summarize_metrics(references, hypotheses, include_bleu=not args.no_bleu)
    report["pairs"] = len(references)
    output = Path(args.output) if args.output else None
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"报告已写入: {output}")
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
