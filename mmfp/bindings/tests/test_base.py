"""ABC contract tests for BindingPlugin and the registry."""

from __future__ import annotations

import pytest

from mmfp.bindings import BindingPlugin, get, names, register
from mmfp.bindings._registry import _REGISTRY
from mmfp.plugins.binding import BindingPlugin as ABCBinding


def test_binding_plugin_is_abstract():
    with pytest.raises(TypeError):
        BindingPlugin()  # type: ignore[abstract]


def test_azure_foundry_registered():
    assert "azure_foundry" in names()


def test_get_returns_class_and_is_subclass_of_abc():
    cls = get("azure_foundry")
    assert issubclass(cls, ABCBinding)
    assert cls.name == "azure_foundry"


def test_get_raises_keyerror_for_unknown():
    with pytest.raises(KeyError) as exc:
        get("definitely_not_a_real_binding")
    msg = str(exc.value)
    assert "azure_foundry" in msg


def test_register_rejects_collision():
    @register
    class _A(ABCBinding):
        name = "_collision_test_binding"

        def invoke(self, candidate, prompt, max_tokens):
            raise NotImplementedError

    try:
        with pytest.raises(ValueError, match="already registered"):

            @register
            class _B(ABCBinding):  # noqa: F841
                name = "_collision_test_binding"

                def invoke(self, candidate, prompt, max_tokens):
                    raise NotImplementedError
    finally:
        _REGISTRY.pop("_collision_test_binding", None)


def test_register_idempotent_for_same_class():
    @register
    class _C(ABCBinding):
        name = "_idempotent_test_binding"

        def invoke(self, candidate, prompt, max_tokens):
            raise NotImplementedError

    try:
        register(_C)
        assert get("_idempotent_test_binding") is _C
    finally:
        _REGISTRY.pop("_idempotent_test_binding", None)
