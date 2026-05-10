"""Shared building blocks for MMFP data models.

`schema_version` is a `Literal["v1"]` field on every persisted top-level model.
Keeping it Literal (rather than `str`) means a future v2 must broaden the type
deliberately — older artefacts won't be silently re-validated under a new
schema. Migrations are explicit.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal, TypeAlias

from pydantic import AfterValidator, ConfigDict

# Bumped when the schema_version field on persisted models changes.
SCHEMA_VERSION: Literal["v1"] = "v1"

SchemaVersion: TypeAlias = Literal["v1"]


def _require_tz_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError("datetime must be timezone-aware")
    # Normalise to UTC so equality / round-trip behaviour is stable across
    # producers that emit different offsets for the same instant.
    return value.astimezone(timezone.utc)


# Annotated alias every model uses for datetime fields. Rejects naive
# datetimes outright; converts non-UTC offsets to UTC.
UTCDatetime = Annotated[datetime, AfterValidator(_require_tz_aware_utc)]


# Default ConfigDict for every MMFP model.
#
# `extra="forbid"` is deliberate: a stray key is more often a bug (typo, drift
# from rubric YAML to code) than an intentional extension. v2 schemas can relax
# this if needed; v1 stays strict.
#
# `frozen=False` because runtime callers (matrix engine, evaluators) accumulate
# results on these structures by replacement rather than mutation, but we don't
# want to forbid the occasional in-place tweak in test fixtures.
MMFP_MODEL_CONFIG = ConfigDict(
    extra="forbid",
    str_strip_whitespace=True,
    validate_assignment=True,
    use_enum_values=False,
)
