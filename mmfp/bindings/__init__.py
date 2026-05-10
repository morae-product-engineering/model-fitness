"""Binding registry and concrete-binding re-exports.

Importing this package triggers registration of every concrete binding via
side-effect imports. The matrix engine looks up binding classes via
`get(name)` against `candidate.binding.provider`.
"""

from mmfp.bindings._registry import get, names, register

# Side-effect import — registers AzureFoundryBinding under 'azure_foundry'.
from mmfp.bindings.foundry import binding as _foundry_binding  # noqa: E402, F401
from mmfp.plugins.binding import BindingPlugin

__all__ = ["BindingPlugin", "get", "names", "register"]
