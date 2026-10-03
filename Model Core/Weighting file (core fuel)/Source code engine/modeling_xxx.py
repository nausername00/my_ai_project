"""Experimental causal language model template.

This module contains a minimal, readable transformer implementation
(``TinyCausalLM``) intended as a teaching/experiment scaffold: it shows how a
causal language model is structured without depending on a model zoo.

For production use, load a pretrained model with ``transformers.AutoModelForCausalLM``
(see ``inference.TransformersBackend`` and ``model.load_model``) instead of
using this class.  ``torch`` is imported lazily; importing this module on a
machine without torch succeeds, and calling the model raises a clear error.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Any

from inference import ModelUnavailableError


def _require_torch() -> Any:
    try:
        return importlib.import_module("torch")
    except ImportError as error:
        raise ModelUnavailableError(
            "torch is required to instantiate TinyCausalLM; "
            "install it with:  pip install -e \"Model Core/Weighting file (core fuel)/Engineering Config[model]\""
        ) from error


@dataclass
class TinyConfig:
    """Configuration for :class:`TinyCausalLM`."""

    vocab_size: int = 512
    hidden_size: int = 128
    num_heads: int = 4
    num_layers: int = 1
    max_position_embeddings: int = 256
    dropout: float = 0.0
    _extra: dict[str, Any] = field(default_factory=dict)


class TinyCausalLM:
    """A minimal causal language model with masked self-attention.

    Wraps the real ``torch.nn.Module`` graph so that this module stays
    importable without torch.  The class exposes ``forward``/``generate``
    compatible shapes with ``transformers``-style ``CausalLMOutput``.

    This is a *template*, not a production architecture: single-layer
    attention, learned positional embeddings, and no KV-cache optimization.
    """

    def __init__(self, config: TinyConfig) -> None:
        torch = _require_torch()
        nn = torch.nn
        self.config = config
        self._module = _TinyModule(config, torch, nn)

    @property
    def parameters(self):
        return self._module.parameters()

    def forward(self, input_ids, attention_mask=None, labels=None):
        return self._module(input_ids, attention_mask=attention_mask, labels=labels)

    def generate(self, input_ids, max_new_tokens: int = 16, do_sample: bool = False) -> Any:
        """Greedy (or sampled) autoregressive generation over token ids."""
        torch = _require_torch()
        self._module.eval()
        generated = list(input_ids[0].tolist())
        with torch.no_grad():
            for _ in range(max_new_tokens):
                window = torch.tensor([generated[- self.config.max_position_embeddings:]])
                logits = self._module(window).logits
                next_logits = logits[0, -1]
                if do_sample:
                    probs = torch.softmax(next_logits, dim=-1)
                    next_id = int(torch.multinomial(probs, num_samples=1).item())
                else:
                    next_id = int(torch.argmax(next_logits).item())
                generated.append(next_id)
                if next_id == 0:  # stop token id 0 is a convention; adjust per tokenizer
                    break
        return torch.tensor([generated])


class _TinyModule:
    """The actual ``torch.nn.Module`` graph behind :class:`TinyCausalLM`."""

    def __init__(self, config: TinyConfig, torch: Any, nn: Any) -> None:
        self.config = config
        self.torch = torch
        class CausalLMOutput:
            def __init__(self, logits=None, loss=None):
                self.logits = logits
                self.loss = loss

        self.CausalLMOutput = CausalLMOutput
        embed_dim = config.hidden_size
        self.token_embedding = nn.Embedding(config.vocab_size, embed_dim)
        self.position_embedding = nn.Embedding(config.max_position_embeddings, embed_dim)
        self.attention = nn.MultiheadAttention(embed_dim, config.num_heads, batch_first=True)
        self.norm1 = nn.LayerNorm(embed_dim)
        self.ffn = nn.Sequential(
            nn.Linear(embed_dim, 4 * embed_dim),
            nn.GELU(),
            nn.Linear(4 * embed_dim, embed_dim),
        )
        self.norm2 = nn.LayerNorm(embed_dim)
        self.lm_head = nn.Linear(embed_dim, config.vocab_size, bias=False)
        self.dropout = nn.Dropout(config.dropout)

    def _forward(self, input_ids, attention_mask=None):
        torch = self.torch
        seq_len = input_ids.shape[1]
        positions = torch.arange(seq_len, device=input_ids.device).unsqueeze(0)
        hidden = self.token_embedding(input_ids) + self.position_embedding(positions)
        hidden = self.dropout(hidden)
        # Causal mask: block future tokens.
        causal_mask = torch.triu(
            torch.full((seq_len, seq_len), float("-inf"), device=input_ids.device), diagonal=1
        )
        attention_mask_2d = None
        if attention_mask is not None:
            attention_mask_2d = (attention_mask[:, None, :] * attention_mask[:, :, None]).float()
            attention_mask_2d = attention_mask_2d.masked_fill(attention_mask_2d == 0, float("-inf"))
        attn_out, _ = self.attention(hidden, hidden, hidden, attn_mask=causal_mask, need_weights=False)
        hidden = self.norm1(hidden + attn_out)
        hidden = self.norm2(hidden + self.ffn(hidden))
        return self.lm_head(hidden)

    def __call__(self, input_ids, attention_mask=None, labels=None):
        logits = self._forward(input_ids, attention_mask=attention_mask)
        loss = None
        if labels is not None:
            loss_fct = self.torch.nn.CrossEntropyLoss()
            loss = loss_fct(logits.view(-1, self.config.vocab_size), labels.view(-1))
        return self.CausalLMOutput(logits=logits, loss=loss)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Smoke-test the TinyCausalLM template")
    parser.add_argument("--steps", type=int, default=5, help="random training steps")
    args = parser.parse_args()

    torch = _require_torch()
    torch.manual_seed(0)
    config = TinyConfig(vocab_size=256, hidden_size=32, num_heads=2, max_position_embeddings=64)
    model = TinyCausalLM(config)
    optimizer = torch.optim.Adam(model.parameters, lr=1e-3)
    inputs = torch.randint(1, 255, (2, 16))
    for step in range(args.steps):
        optimizer.zero_grad()
        output = model(inputs, labels=inputs)
        output.loss.backward()
        optimizer.step()
        print(f"step {step + 1}: loss={output.loss.item():.4f}")
    sample = model.generate(inputs[:1], max_new_tokens=8)
    print("生成 token 序列长度:", sample.shape[1])
