"""Evaluator registry primitives.

Kept separate from `mmfp.evaluators.__init__` to avoid a circular import:
concrete evaluators import `register` from here; `__init__` imports the
public API from here AND triggers concrete-module imports for their
side-effect registrations.
"""

from __future__ import annotations

from mmfp.plugins.evaluator import EvaluatorPlugin

_REGISTRY: dict[str, type[EvaluatorPlugin]] = {}


def register(cls: type[EvaluatorPlugin]) -> type[EvaluatorPlugin]:
    """Class decorator: register `cls` under `cls.name`.

    Idempotent for the same class (re-registering the same class is a no-op).
    Raises if a different class tries to claim a name already in use.
    """
    name = cls.name
    existing = _REGISTRY.get(name)
    if existing is not None and existing is not cls:
        raise ValueError(
            f"Evaluator name '{name}' already registered to "
            f"{existing.__module__}.{existing.__name__}; cannot reassign to "
            f"{cls.__module__}.{cls.__name__}"
        )
    _REGISTRY[name] = cls
    return cls


def get(name: str) -> type[EvaluatorPlugin]:
    """Look up an evaluator class by name.

    Raises KeyError with the list of known names on miss — error messages
    written for the matrix engine, which reads this when iterating a rubric.
    """
    try:
        return _REGISTRY[name]
    except KeyError as e:
        known = sorted(_REGISTRY)
        raise KeyError(
            f"No evaluator registered under '{name}'. Known: {known}"
        ) from e


def names() -> list[str]:
    """Sorted list of registered evaluator names."""
    return sorted(_REGISTRY)
