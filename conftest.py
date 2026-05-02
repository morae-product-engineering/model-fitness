"""Root conftest.py — loaded by pytest before any test collection.

Patches the `platform` entry in sys.modules to point at our `platform/`
package rather than the stdlib `platform` module. This is necessary because:
  1. Our top-level Python package is named `platform`, clashing with stdlib.
  2. pytest imports stdlib `platform` early (for `platform.python_version()`).
  3. Once stdlib `platform` is in sys.modules, Python won't re-import it from
     our `platform/` directory even if the repo root is on sys.path.

Strategy:
  - Keep all stdlib `platform` attributes (so pytest internal code keeps working).
  - Also register `platform` as a *package* (set __path__) so sub-imports like
    `platform.api.main` resolve to our files.
  - Reload stdlib attrs into the existing module object in-place; this avoids
    any reference-identity issues with code that already holds `import platform`.
"""

import importlib.machinery
import importlib.util
import os.path
import sys
from pathlib import Path

_repo_root = str(Path(__file__).parent)

# Step 1: ensure repo root is first on sys.path.
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

# Step 2: if the stdlib `platform` is already in sys.modules, patch it so
# Python treats it as a package whose __path__ points to our platform/ dir.
# We do NOT want to remove it — that would break callers holding a reference.
_plat_mod = sys.modules.get("platform")
if _plat_mod is not None and not hasattr(_plat_mod, "__path__"):
    # Annotate the stdlib module object as a package by adding __path__.
    # Python uses __path__ to locate sub-modules.
    _plat_mod.__path__ = [os.path.join(_repo_root, "platform")]
    _plat_mod.__package__ = "platform"
    # Leave all other stdlib attributes (python_version etc.) intact.

del _repo_root, _plat_mod
