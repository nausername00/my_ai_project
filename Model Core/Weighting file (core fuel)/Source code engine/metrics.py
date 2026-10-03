"""Evaluation metrics for the local AI service.

Pure-Python implementations (no ML dependencies) so they can be reused by
``benchmark.py``, ``eval.py``, the API, and unit tests alike:

- perplexity from a sequence of log-likelihoods
- smoothed BLEU (n-gram precision with brevity penalty)
- exact match / token accuracy / F1
- corpus statistics helpers
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable, Sequence


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokenization used by the text metrics.

    Non-alphanumeric runs are treated as separators; empty results return
    an empty list (callers that need a single token should guard on this).
    """
    return re.findall(r"[a-z0-9]+", text.lower())


def perplexity(log_likelihoods: Sequence[float]) -> float:
    """Compute perplexity from per-token log-likelihoods.

    ``PPL = exp(-mean(log_likelihood))``; returns ``inf`` for an empty list.
    """
    if not log_likelihoods:
        return float("inf")
    mean = sum(float(value) for value in log_likelihoods) / len(log_likelihoods)
    return math.exp(-mean)


def _ngrams(tokens: Sequence[str], n: int) -> Counter[tuple[str, ...]]:
    if n <= 0 or len(tokens) < n:
        return Counter()
    return Counter(tuple(tokens[index : index + n]) for index in range(len(tokens) - n + 1))


def bleu(references: Sequence[str], hypothesis: str, max_n: int = 4) -> float:
    """Compute a smoothed BLEU score between one hypothesis and references.

    Uses additive smoothing for missing n-gram matches and a brevity penalty
    when the hypothesis is shorter than the shortest reference.  ``max_n``
    clips the n-gram order (1..max_n).
    """
    if not references:
        raise ValueError("references must not be empty")
    hyp = tokenize(hypothesis)
    refs = [tokenize(reference) for reference in references]
    if not hyp:
        return 0.0
    max_n = max(1, min(int(max_n), 4))
    precision_log_sum = 0.0
    for n in range(1, max_n + 1):
        hyp_counts = _ngrams(hyp, n)
        ref_counts = Counter()
        for ref in refs:
            counts = _ngrams(ref, n)
            for key, count in counts.items():
                if count > ref_counts[key]:
                    ref_counts[key] = count
        matches = sum(count for key, count in hyp_counts.items() if ref_counts[key] >= count)
        total = sum(hyp_counts.values())
        # Additive smoothing (avoid log(0)).
        precision = (matches + 1.0) / (total + 1.0) if total else 0.0
        precision_log_sum += math.log(max(precision, 1e-12))
    brevity = min(1.0, math.exp(1.0 - len(min(refs, key=len)) / max(len(hyp), 1)))
    return brevity * math.exp(precision_log_sum / max_n)


def exact_match(reference: str, hypothesis: str) -> float:
    """Return 1.0 when the hypothesis matches a reference exactly (1.0/0.0)."""
    return 1.0 if hypothesis.strip().lower() == reference.strip().lower() else 0.0


def token_accuracy(reference: str, hypothesis: str) -> float:
    """Ratio of correctly predicted tokens over the reference token count.

    Returns 0.0 when the reference has no tokens.
    """
    ref = tokenize(reference)
    hyp = tokenize(hypothesis)
    if not ref:
        return 0.0
    matches = sum(1 for index in range(min(len(ref), len(hyp))) if ref[index] == hyp[index])
    return matches / len(ref)


def f1_score(reference: str, hypothesis: str) -> float:
    """F1 over token sets (precision and recall between set intersections)."""
    ref = set(tokenize(reference))
    hyp = set(tokenize(hypothesis))
    if not ref or not hyp:
        return 0.0
    overlap = len(ref & hyp)
    precision = overlap / len(hyp)
    recall = overlap / len(ref)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def corpus_stats(texts: Iterable[str]) -> dict[str, int]:
    """Return character/token/unique-token statistics over a corpus."""
    characters = 0
    tokens = 0
    unique: Counter[str] = Counter()
    for text in texts:
        characters += len(text)
        tokens += len(tokenize(text))
        unique.update(tokenize(text))
    return {
        "characters": characters,
        "tokens": tokens,
        "unique_tokens": len(unique),
    }


def summarize_metrics(
    references: Sequence[str],
    hypotheses: Sequence[str],
    *,
    include_bleu: bool = True,
) -> dict[str, float]:
    """Aggregate exact-match / accuracy / F1 (and optionally BLEU) over pairs.

    ``references`` and ``hypotheses`` must have equal length.
    """
    if len(references) != len(hypotheses):
        raise ValueError("references and hypotheses must have equal length")
    if not references:
        raise ValueError("references must not be empty")
    em_values: list[float] = []
    acc_values: list[float] = []
    f1_values: list[float] = []
    bleu_values: list[float] = []
    for reference, hypothesis in zip(references, hypotheses):
        em_values.append(exact_match(reference, hypothesis))
        acc_values.append(token_accuracy(reference, hypothesis))
        f1_values.append(f1_score(reference, hypothesis))
        if include_bleu:
            bleu_values.append(bleu([reference], hypothesis))
    summary: dict[str, float] = {
        "exact_match": sum(em_values) / len(em_values),
        "token_accuracy": sum(acc_values) / len(acc_values),
        "f1": sum(f1_values) / len(f1_values),
        "count": float(len(references)),
    }
    if include_bleu:
        summary["bleu"] = sum(bleu_values) / len(bleu_values)
    return summary


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Quick metric sanity check on two texts")
    parser.add_argument("--reference", required=True, help="reference text")
    parser.add_argument("--hypothesis", required=True, help="hypothesis text")
    args = parser.parse_args()

    print("exact_match:", exact_match(args.reference, args.hypothesis))
    print("token_accuracy:", token_accuracy(args.reference, args.hypothesis))
    print("f1:", f1_score(args.reference, args.hypothesis))
    print("bleu:", bleu([args.reference], args.hypothesis))
