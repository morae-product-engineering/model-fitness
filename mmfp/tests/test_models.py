# @jira: MLI-169
"""Unit tests for the v1 MMFP data model.

Round-trip, validation failure, and schema-version handling. Engine and
plugin behaviour live in their own modules' tests.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from mmfp.models import (
    Candidate,
    CandidateBinding,
    CandidateFamily,
    CandidateStatus,
    Dataset,
    DatasetExample,
    Dimension,
    EvaluationMode,
    EvaluatorScore,
    Gate,
    JudgeConfig,
    MatrixRun,
    MatrixRunResult,
    Method,
    Rubric,
    SourceField,
    Tier,
)

# --- fixtures ---------------------------------------------------------------


def _tier_1() -> Tier:
    return Tier(
        id="tier_1",
        name="Classification & Routing",
        intent="Reliability instrument — bounded structured output",
        mode=EvaluationMode.SINGLE_TURN,
        dimensions=[
            Dimension(
                id="classification_accuracy",
                name="Classification accuracy",
                description="Proportion of inputs classified correctly",
                weight=Decimal("60"),
                method=Method.DETERMINISTIC,
                evaluator="exact_match",
            ),
            Dimension(
                id="latency_p95",
                name="Latency p95",
                description="95th percentile latency",
                weight=Decimal("40"),
                method=Method.METRIC,
                direction="lower_is_better",
                evaluator="regex_match",
            ),
        ],
    )


def _judge() -> JudgeConfig:
    return JudgeConfig(
        model="claude-sonnet-4-5",
        provider="azure_foundry",
        version_pin="2025-10-01",
        calibration_set="shared/datasets/judge_calibration_v1.jsonl",
    )


def _rubric() -> Rubric:
    return Rubric(
        version="v0.1",
        tiers=[_tier_1()],
        gates=[
            Gate(
                id="gate.compliance.soc2",
                description="Provider holds SOC 2 Type II",
            )
        ],
        judge=_judge(),
    )


def _candidate() -> Candidate:
    return Candidate(
        id="kimi-k2-6",
        display_name="Kimi K2.6",
        family=CandidateFamily.REASONING,
        max_tokens=4096,
        tiers=["tier_1"],
        binding=CandidateBinding(
            provider="azure_foundry",
            endpoint="https://example-models.cognitiveservices.azure.com",
            deployment="Kimi-K2.6",
            key_vault_secret_name="kimi-api-key",
        ),
    )


# --- round-trip -------------------------------------------------------------


def test_rubric_round_trips_through_json() -> None:
    original = _rubric()
    payload = json.loads(original.model_dump_json())
    restored = Rubric.model_validate(payload)
    assert restored == original


def test_candidate_round_trips_through_json() -> None:
    original = _candidate()
    payload = json.loads(original.model_dump_json())
    restored = Candidate.model_validate(payload)
    assert restored == original


def test_dataset_round_trips_through_json() -> None:
    original = Dataset(
        id="mli_classification_golden",
        name="MLI classification golden set",
        version="v0.1",
        tier_id="tier_1",
        examples=[
            DatasetExample(
                id="ex-001",
                input={"user": "Classify this ticket"},
                expected="billing",
                tags=["smoke"],
            )
        ],
    )
    payload = json.loads(original.model_dump_json())
    assert Dataset.model_validate(payload) == original


def test_matrix_run_round_trips_through_json() -> None:
    started = datetime.now(timezone.utc)
    run = MatrixRun(
        id="run-abc",
        rubric_version="v0.1",
        started_at=started,
        completed_at=started + timedelta(minutes=5),
        results=[
            MatrixRunResult(
                tier_id="tier_1",
                candidate_id="kimi-k2-6",
                dataset_id="mli_classification_golden",
                example_id="ex-001",
                score=EvaluatorScore(
                    dimension_id="classification_accuracy",
                    evaluator_id="exact_match",
                    raw_value=1.0,
                    normalized_score=Decimal("100"),
                    passed=True,
                    source_field=SourceField.CONTENT,
                ),
            )
        ],
    )
    payload = json.loads(run.model_dump_json())
    assert MatrixRun.model_validate(payload) == run


# --- validation failures ----------------------------------------------------


def test_tier_dimension_weights_must_sum_to_100() -> None:
    with pytest.raises(ValidationError, match="must sum to 100"):
        Tier(
            id="tier_1",
            name="x",
            intent="x",
            mode=EvaluationMode.SINGLE_TURN,
            dimensions=[
                Dimension(
                    id="a",
                    name="a",
                    description="a",
                    weight=Decimal("70"),
                    method=Method.DETERMINISTIC,
                    evaluator="exact_match",
                ),
                Dimension(
                    id="b",
                    name="b",
                    description="b",
                    weight=Decimal("20"),
                    method=Method.DETERMINISTIC,
                    evaluator="exact_match",
                ),
            ],
        )


def test_tier_dimension_ids_must_be_unique() -> None:
    with pytest.raises(ValidationError, match="duplicate dimension ids"):
        Tier(
            id="tier_1",
            name="x",
            intent="x",
            mode=EvaluationMode.SINGLE_TURN,
            dimensions=[
                Dimension(
                    id="dup",
                    name="a",
                    description="a",
                    weight=Decimal("50"),
                    method=Method.DETERMINISTIC,
                    evaluator="exact_match",
                ),
                Dimension(
                    id="dup",
                    name="b",
                    description="b",
                    weight=Decimal("50"),
                    method=Method.DETERMINISTIC,
                    evaluator="exact_match",
                ),
            ],
        )


def test_candidate_max_tokens_required() -> None:
    with pytest.raises(ValidationError, match="max_tokens"):
        Candidate(
            id="c",
            display_name="c",
            family=CandidateFamily.CHAT,
            tiers=["tier_1"],
            binding=CandidateBinding(
                provider="azure_foundry",
                endpoint="https://example.com",
                deployment="d",
                key_vault_secret_name="k",
            ),
        )  # type: ignore[call-arg]


def test_naive_datetime_rejected_on_matrix_run() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        MatrixRun(
            id="r",
            rubric_version="v0.1",
            started_at=datetime(2026, 1, 1, 12, 0, 0),  # naive
        )


def test_completed_after_started() -> None:
    started = datetime.now(timezone.utc)
    with pytest.raises(ValidationError, match="completed_at must be"):
        MatrixRun(
            id="r",
            rubric_version="v0.1",
            started_at=started,
            completed_at=started - timedelta(seconds=1),
        )


def test_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        Candidate.model_validate(
            {
                "id": "c",
                "display_name": "c",
                "family": "chat",
                "max_tokens": 100,
                "tiers": ["tier_1"],
                "binding": {
                    "provider": "azure_foundry",
                    "endpoint": "https://example.com",
                    "deployment": "d",
                    "key_vault_secret_name": "k",
                },
                "unexpected": "should reject",
            }
        )


def test_portfolio_thresholds_must_be_ordered() -> None:
    with pytest.raises(ValidationError, match="must be ordered"):
        Rubric(
            version="v0.1",
            tiers=[_tier_1()],
            judge=_judge(),
            thresholds={  # type: ignore[arg-type]
                "approved_primary_min": Decimal("60"),
                "approved_fallback_min": Decimal("70"),
                "rejected_max": Decimal("80"),
            },
        )


# --- schema_version handling ------------------------------------------------


def test_schema_version_default_is_v1() -> None:
    assert _rubric().schema_version == "v1"
    assert _candidate().schema_version == "v1"


def test_schema_version_v2_rejected_under_v1_models() -> None:
    payload = _candidate().model_dump()
    payload["schema_version"] = "v2"
    with pytest.raises(ValidationError):
        Candidate.model_validate(payload)


def test_status_defaults_to_under_evaluation() -> None:
    assert _candidate().status is CandidateStatus.UNDER_EVALUATION


# --- derived view -----------------------------------------------------------


def test_matrix_run_scores_for_tier_aggregates_per_candidate() -> None:
    started = datetime.now(timezone.utc)
    run = MatrixRun(
        id="run",
        rubric_version="v0.1",
        started_at=started,
        results=[
            MatrixRunResult(
                tier_id="tier_1",
                candidate_id="cand-a",
                dataset_id="ds",
                example_id="ex-1",
                score=EvaluatorScore(
                    dimension_id="classification_accuracy",
                    evaluator_id="exact_match",
                    raw_value=1.0,
                    normalized_score=Decimal("80"),
                ),
            ),
            MatrixRunResult(
                tier_id="tier_1",
                candidate_id="cand-a",
                dataset_id="ds",
                example_id="ex-2",
                score=EvaluatorScore(
                    dimension_id="classification_accuracy",
                    evaluator_id="exact_match",
                    raw_value=1.0,
                    normalized_score=Decimal("60"),
                ),
            ),
            MatrixRunResult(
                tier_id="tier_1",
                candidate_id="cand-b",
                dataset_id="ds",
                example_id="ex-1",
                score=EvaluatorScore(
                    dimension_id="classification_accuracy",
                    evaluator_id="exact_match",
                    raw_value=1.0,
                    normalized_score=Decimal("90"),
                ),
            ),
            MatrixRunResult(
                tier_id="tier_2",
                candidate_id="cand-b",
                dataset_id="ds",
                example_id="ex-3",
                score=EvaluatorScore(
                    dimension_id="other",
                    evaluator_id="exact_match",
                    raw_value=1.0,
                    normalized_score=Decimal("50"),
                ),
            ),
        ],
    )
    cards = run.scores_for_tier("tier_1")
    by_id = {c.candidate_id: c for c in cards}
    # cand-a: mean(80, 60) = 70
    assert by_id["cand-a"].weighted_score == Decimal("70")
    # cand-b: only one tier_1 row, normalised 90
    assert by_id["cand-b"].weighted_score == Decimal("90")
    # ranking: highest first
    assert [c.candidate_id for c in cards] == ["cand-b", "cand-a"]
    # tier_2 row not in tier_1 view
    assert all(c.tier_id == "tier_1" for c in cards)
