"""Binding registry primitives.

Mirrors `mmfp.evaluators._registry`. Kept separate from
`mmfp.bindings.__init__` to avoid a circular import: concrete binding
classes import `register` from here; `__init__` imports the public API
from here AND triggers concrete-module imports for their side-effect
registrations.
"""

from __future__ import annotations

from mmfp.plugins.binding import BindingPlugin

_REGISTRY: dict[str, type[BindingPlugin]] = {}


def register(cls: type[BindingPlugin]) -> type[BindingPlugin]:
    """Class decorator: register `cls` under `cls.name`.

    Idempotent for the same class. Raises if a different class tries to
    claim a name already in use.
    """
    name = cls.name
    existing = _REGISTRY.get(name)
    if existing is not None and existing is not cls:
        raise ValueError(
            f"Binding name '{name}' already registered to "
            f"{existing.__module__}.{existing.__name__}; cannot reassign to "
            f"{cls.__module__}.{cls.__name__}"
        )
    _REGISTRY[name] = cls
    return cls


def get(name: str) -> type[BindingPlugin]:
    """Look up a binding class by name.

    Matched against `Candidate.binding.provider`. Error message lists
    known bindings so the matrix engine surfaces a useful diagnostic
    when a candidate references an unknown provider.
    """
    try:
        return _REGISTRY[name]
    except KeyError as e:
        known = sorted(_REGISTRY)
        raise KeyError(
            f"No binding registered under '{name}'. Known: {known}"
        ) from e


def names() -> list[str]:
    """Sorted list of registered binding names."""
    return sorted(_REGISTRY)
