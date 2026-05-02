# Makes `platform/` a proper Python package so it appears on sys.path before
# the stdlib `platform` module when the repo root is on PYTHONPATH.
#
# IMPORTANT: because the stdlib also has a `platform` module, we re-export its
# public attributes here so any code that does `import platform; platform.foo()`
# continues to work (pytest, uvicorn, and other tools use stdlib platform
# internally).
#
# In the Docker container (Python 3.12) the editable-install .pth hook fires
# correctly and this file only acts as a namespace anchor — the re-export is
# harmless but not strictly needed there.
#
# On Python 3.13 locally, macOS marks .pth files hidden, the hook is skipped,
# and we rely on PYTHONPATH=. + this __init__.py to make imports work.
#
# TODO(MLI-xxx): consider renaming the top-level package away from `platform`
# to eliminate this stdlib clash permanently.

import importlib.machinery as _machinery
import importlib.util as _util
import os.path as _osp
import sys as _sys

# Load stdlib platform by its absolute filesystem path, bypassing the name clash.
_stdlib_platform_path = _osp.join(_osp.dirname(_osp.__file__), "platform.py")
if _osp.exists(_stdlib_platform_path):
    _loader = _machinery.SourceFileLoader("_mmfp_stdlib_platform", _stdlib_platform_path)
    _spec = _util.spec_from_file_location(
        "_mmfp_stdlib_platform", _stdlib_platform_path, loader=_loader
    )
    _mod = _util.module_from_spec(_spec)
    _sys.modules["_mmfp_stdlib_platform"] = _mod
    _spec.loader.exec_module(_mod)
    # Re-export all public names so callers of `platform.python_version()` etc.
    # continue to work through this package's namespace.
    globals().update({k: v for k, v in vars(_mod).items() if not k.startswith("__")})
    del _mod, _spec, _loader

del _machinery, _util, _osp, _sys, _stdlib_platform_path
