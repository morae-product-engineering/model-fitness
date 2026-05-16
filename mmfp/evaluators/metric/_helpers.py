"""Shared normalisation + context-extraction helpers for the metric family.

The two helpers below pin two contracts the family depends on:

1. `normalise_lower_better(raw, reference)` — the higher-is-better-inverted
   normalisation: at or below the reference scores 100; above decays
   harmonically (2× → 50, 4× → 25). The shape is documented on the AC.

2. `require_*(context, ...)` — extract typed values from the per-call
   context dict. The engine populates context with `dimension_id`,
   `evaluator_id`, `evaluator_config`, plus envelope fields (`latency_ms`,
   `cost_usd`). Missing or out-of-range values raise ValueError with the
   key name in the message so the wrapping engine error is debuggable.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

# Two decimal places is enough resolution for a 0–100 score and keeps the
# JSON-blob persisted score human-readable (e.g. "33.33", not 33.333...3).
_SCORE_QUANTUM = Decimal("0.01")


def normalise_lower_better(raw: Decimal, reference: Decimal) -> Decimal:
    """Score a lower-is-better raw against a reference.

    At raw <= reference, returns 100 (no marginal reward for over-shooting).
    Above reference, returns 100 * reference / raw (harmonic decay).
    Raw values of 0 or below short-circuit to 100 — never punish a free /
    instant invocation.
    """
    if reference <= Decimal("0"):
        raise ValueError("reference must be > 0")
    if raw <= Decimal("0"):
        return Decimal("100")
    if raw <= reference:
        return Decimal("100")
    return (Decimal("100") * reference / raw).quantize(_SCORE_QUANTUM)


def require_config(context: dict[str, Any]) -> dict[str, Any]:
    """Return `context['evaluator_config']` or an empty dict.

    The downstream `require_*_from_config` helpers raise on missing keys,
    so the "no config block at all" case surfaces the same error as
    "config block with missing key" — one failure mode, one message shape.
    """
    cfg = context.get("evaluator_config") or {}
    if not isinstance(cfg, dict):
        raise ValueError(
            f"evaluator_config must be a dict; got {type(cfg).__name__}"
        )
    return cfg


def require_positive_decimal(value: Any, *, name: str) -> Decimal:
    """Coerce `value` to Decimal and enforce > 0."""
    d = _coerce_decimal(value, name=name)
    if d <= Decimal("0"):
        raise ValueError(f"{name} must be > 0; got {d}")
    return d


def require_non_negative_decimal(value: Any, *, name: str) -> Decimal:
    """Coerce `value` to Decimal and enforce >= 0."""
    d = _coerce_decimal(value, name=name)
    if d < Decimal("0"):
        raise ValueError(f"{name} must be >= 0; got {d}")
    return d


def require_non_negative_int(value: Any, *, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be int; got {type(value).__name__}")
    if value < 0:
        raise ValueError(f"{name} must be >= 0; got {value}")
    return value


def require_positive_int(value: Any, *, name: str, minimum: int = 1) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be int; got {type(value).__name__}")
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}; got {value}")
    return value


def _coerce_decimal(value: Any, *, name: str) -> Decimal:
    """Accept Decimal, int, or float; reject everything else.

    Float is accepted because upstream cost computation (cost = tokens ×
    price-per-token) is float arithmetic; the evaluator converts via
    str(value) so the float's printed representation round-trips into a
    Decimal without inheriting binary-float noise.
    """
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise TypeError(f"{name} must be numeric; got bool")
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    raise TypeError(f"{name} must be Decimal/int/float; got {type(value).__name__}")
