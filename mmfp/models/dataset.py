"""Dataset model — golden test data for one tier.

A `DatasetExample.expected` holds evaluator-specific shape (label string for
classification, JSON object for structured-generation, query result for SQL).
That is the one place this package allows an unbounded `Any`; alternatives
considered (a discriminated union per tier, a stringly-typed expected) all
prematurely couple the dataset format to the evaluator implementation.
Documented inline at the field rather than scattered across this docstring so
future readers see it where they need it.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from mmfp.models._common import MMFP_MODEL_CONFIG, SCHEMA_VERSION, SchemaVersion


class DatasetExample(BaseModel):
    """One golden example: input plus expected outcome and tags."""

    model_config = MMFP_MODEL_CONFIG

    id: str = Field(min_length=1, description="Stable id within the dataset")
    input: dict[str, Any] | str = Field(
        description=(
            "Input as either a string prompt or a structured payload "
            "(e.g. {'system': ..., 'user': ..., 'tools': [...]})"
        )
    )
    # Bounded `Any`: evaluator-specific shape. Justification at module
    # docstring; keeping this typed as `Any` is deliberate, not lazy.
    expected: Any = Field(
        description=(
            "Evaluator-specific expected outcome — shape varies by dimension method "
            "(e.g. label string, JSON Schema fragment, SQL result-set)."
        )
    )
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Dataset(BaseModel):
    """A versioned collection of golden examples for one tier."""

    model_config = MMFP_MODEL_CONFIG

    schema_version: SchemaVersion = SCHEMA_VERSION
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(default="")
    version: str = Field(
        min_length=1,
        pattern=r"^v\d+\.\d+(?:\.\d+)?$",
        description="Dataset version, e.g. 'v0.1' or 'v0.1.0'",
    )
    tier_id: str = Field(min_length=1, description="Which tier this dataset feeds")
    examples: list[DatasetExample] = Field(min_length=1)
