"""Deterministic cost pricing helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PricedUsage:
    usd: float
    pricing_source: str


def price_usage(
    *,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    provider_usd: float | None = None,
) -> PricedUsage:
    """Return best-effort USD pricing without network calls."""
    if provider_usd is not None:
        return PricedUsage(usd=round(max(0.0, provider_usd), 8), pricing_source="provider")
    # Claude Code and Codex may expose cost in their output in the future.
    # Without that field, do not pretend current public pricing is known.
    _ = (provider, model, input_tokens, output_tokens)
    return PricedUsage(usd=0.0, pricing_source="unknown")
