# @jira: MLI-192 — scoring engine that re-scores an existing MatrixRun under a
#         (possibly newer) Rubric without re-invoking models.
#
# These are unit tests (next-to-code per CLAUDE.md): pure model construction,
# no fixtures, no IO. The four AC cases are identical-rubric, weight-change,
# dimension-removed, and dimension-added (the coverage-gap / P9 case), plus
# provenance, purity/idempotency, multi-tier orchestration, and the refused
# schema-version mismatch.

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from mmfp.engine.scoring import ScoringEngine
from mmfp.models.matrix_run import EvaluatorScore, MatrixRun, MatrixRunResult
from mmfp.models.rubric import (
    Dimension,
    EvaluationMode,
    JudgeConfig,
    Method,
    Rubric,
    Tier,
)


def _dim(id: str, weight: str, status: str = "active") -> Dimension:
    return Dimension(
        id=id,
        name=id,
        description=id,
        weight=Decimal(weight),
        status=status,  # type: ignore[arg-type]
        method=Method.METRIC,
        evaluator="latency_p95",
    )


def _tier(id: str, dims: list[Dimension]) -> Tier:
    return Tier(id=id, name=id, intent="x", mode=EvaluationMode.SINGLE_TURN, dimensions=dims)  # type: ignore[arg-type]


def _rubric(version: str, tiers: list[Tier]) -> Rubric:
    return Rubric(
        version=version,
        tiers=tiers,
        judge=JudgeConfig(
            model="claude-sonnet-4-5",
            provider="anthropic",
            version_pin="2025-10-01",
            calibration_set="cal.jsonl",
        ),
    )


def _result(tier_id: str, candidate_id: str, dimension_id: str, score: str) -> MatrixRunResult:
    return MatrixRunResult(
        tier_id=tier_id,
        candidate_id=candidate_id,
        dataset_id="ds",
        example_id="ex-1",
        score=EvaluatorScore(
            dimension_id=dimension_id,
            evaluator_id="e",
            raw_value=1.0,
            normalized_score=Decimal(score),
        ),
    )


def _run(results: list[MatrixRunResult], version: str = "v0.1", id: str = "run-1") -> MatrixRun:
    return MatrixRun(
        id=id,
        rubric_version=version,
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        results=results,
    )


# Real tier_3 active pair (rubric v0.1): latency_p95 + cost_per_completed_interaction.
_LAT = "latency_p95"
_COST = "cost_per_completed_interaction"


def test_identical_rubric_reproduces_weighted_score() -> None:
    # Re-scoring under the same rubric must reproduce scores_for_tier's number
    # exactly — one weighting code path, not two.
    rubric = _rubric("v0.1", [_tier("tier_3", [_dim(_LAT, "10"), _dim(_COST, "10")])])
    run = _run([_result("tier_3", "cand-a", _LAT, "80"), _result("tier_3", "cand-a", _COST, "60")])

    cards = ScoringEngine().score(run, rubric)

    assert len(cards) == 1
    card = cards[0]
    # (80*10 + 60*10) / 20 = 70
    assert card.weighted_score == Decimal("70")
    assert card.rubric_version == "v0.1"
    assert card.source_run_id == "run-1"
    assert card.has_complete_coverage is True
    assert card.weighted_score == run.scores_for_tier("tier_3", rubric.tiers[0])[0].weighted_score


def test_simple_weight_change_reweights() -> None:
    run = _run([_result("tier_3", "cand-a", _LAT, "80"), _result("tier_3", "cand-a", _COST, "60")])
    v2 = _rubric("v0.2", [_tier("tier_3", [_dim(_LAT, "30"), _dim(_COST, "10")])])

    card = ScoringEngine().score(run, v2)[0]

    # (80*30 + 60*10) / 40 = 75
    assert card.weighted_score == Decimal("75")
    assert card.rubric_version == "v0.2"
    assert card.has_complete_coverage is True


def test_dimension_removed_from_rubric_is_ignored() -> None:
    # Run measured both dims; the newer rubric only weights latency. The
    # unmeasured-by-the-new-rubric dimension (cost) is simply not weighted —
    # coverage stays complete.
    run = _run([_result("tier_3", "cand-a", _LAT, "80"), _result("tier_3", "cand-a", _COST, "60")])
    slim = _rubric("v0.2", [_tier("tier_3", [_dim(_LAT, "10")])])

    card = ScoringEngine().score(run, slim)[0]

    assert card.weighted_score == Decimal("80")  # cost dropped from the rubric
    assert card.has_complete_coverage is True


def test_dimension_added_to_rubric_flags_coverage_gap() -> None:
    # P9: the newer rubric demands an active dimension (cost) the historical run
    # never measured. The gap is surfaced as data — has_complete_coverage=False
    # and a depressed score — never fabricated.
    run = _run([_result("tier_3", "cand-a", _LAT, "80")])  # cost never measured
    v2 = _rubric("v0.2", [_tier("tier_3", [_dim(_LAT, "10"), _dim(_COST, "10")])])

    card = ScoringEngine().score(run, v2)[0]

    assert card.has_complete_coverage is False
    # Missing active dim contributes 0 to the numerator but its weight to the
    # denominator: (80*10 + 0*10) / 20 = 40, not fabricated up to 80.
    assert card.weighted_score == Decimal("40")


def test_scores_all_tiers_in_rubric_grouped_and_ranked() -> None:
    rubric = _rubric(
        "v0.1",
        [
            _tier("tier_1", [_dim("classification_accuracy", "100")]),
            _tier("tier_3", [_dim(_LAT, "10"), _dim(_COST, "10")]),
        ],
    )
    run = _run(
        [
            _result("tier_1", "cand-a", "classification_accuracy", "90"),
            _result("tier_1", "cand-b", "classification_accuracy", "50"),
            _result("tier_3", "cand-a", _LAT, "80"),
            _result("tier_3", "cand-a", _COST, "60"),
        ]
    )

    cards = ScoringEngine().score(run, rubric)

    t1 = [c for c in cards if c.tier_id == "tier_1"]
    t3 = [c for c in cards if c.tier_id == "tier_3"]
    assert [c.candidate_id for c in t1] == ["cand-a", "cand-b"]  # ranked desc within tier
    assert len(t3) == 1
    assert all(c.rubric_version == "v0.1" and c.source_run_id == "run-1" for c in cards)


def test_score_is_idempotent_and_pure() -> None:
    rubric = _rubric("v0.1", [_tier("tier_3", [_dim(_LAT, "10"), _dim(_COST, "10")])])
    run = _run([_result("tier_3", "cand-a", _LAT, "80"), _result("tier_3", "cand-a", _COST, "60")])
    before = run.model_dump()

    first = ScoringEngine().score(run, rubric)
    second = ScoringEngine().score(run, rubric)

    assert first == second  # idempotent
    assert run.model_dump() == before  # pure: run not mutated


def test_schema_version_mismatch_is_refused() -> None:
    # Only "v1" is a valid schema_version Literal today, so a genuine mismatch
    # is unconstructable — bypass validation to simulate an artefact from a
    # future schema this code predates. The engine refuses rather than migrates.
    rubric = _rubric("v0.1", [_tier("tier_3", [_dim(_LAT, "10")])])
    good = _run([_result("tier_3", "cand-a", _LAT, "80")])
    stale = good.model_copy(update={"schema_version": "v0-legacy"})

    with pytest.raises(ValueError, match="schema_version"):
        ScoringEngine().score(stale, rubric)
