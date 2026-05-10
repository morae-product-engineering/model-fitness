"""Integration test: MatrixEngine.run() persists to SQLite (MLI-258).

Real `MatrixRunRepository` against a `tmp_path` SQLite file; bindings
are mocked the same way as `test_matrix.py` because the unit boundary
under test is the engine→repo→DB wiring, not the provider call.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from mmfp.engine import MatrixEngine
from mmfp.models.binding_response import BindingResponse, TokenUsage
from mmfp.models.candidate import Candidate, CandidateBinding, CandidateFamily
from mmfp.models.dataset import Dataset, DatasetExample
from mmfp.models.rubric import (
    Dimension,
    Direction,
    EvaluationMode,
    JudgeConfig,
    Method,
    Rubric,
    Tier,
)
from mmfp.persistence import MatrixRunRepository
from mmfp.plugins.binding import BindingPlugin


@pytest.fixture(autouse=True)
def _disable_langsmith(monkeypatch):
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)


def _judge() -> JudgeConfig:
    return JudgeConfig(
        model="claude-sonnet-4-5",
        provider="anthropic",
        version_pin="2025-10-01",
        calibration_set="tests/calibration/judge.jsonl",
    )


def _rubric() -> Rubric:
    return Rubric(
        version="v0.1",
        tiers=[
            Tier(
                id="tier_1",
                name="Classification",
                intent="classify",
                mode=EvaluationMode.SINGLE_TURN,
                dimensions=[
                    Dimension(
                        id="t1.classification_accuracy",
                        name="Accuracy",
                        description="exact match",
                        weight=Decimal("100"),
                        method=Method.DETERMINISTIC,
                        direction=Direction.HIGHER_IS_BETTER,
                        evaluator="exact_match",
                    )
                ],
            ),
        ],
        judge=_judge(),
    )


def _dataset() -> Dataset:
    return Dataset(
        id="ds-tier1",
        name="tier_1 set",
        version="v0.1",
        tier_id="tier_1",
        examples=[DatasetExample(id="t1.e1", input="classify A", expected={"value": "A"})],
    )


def _candidate(id: str = "c1") -> Candidate:
    return Candidate(
        id=id,
        display_name=id,
        family=CandidateFamily.CHAT,
        max_tokens=256,
        tiers=["tier_1"],
        binding=CandidateBinding(
            provider="azure_foundry",
            endpoint="https://example.com",
            deployment="gpt-4o",
            key_vault_secret_name="foundry-account-key",
        ),
    )


class _FixedBinding(BindingPlugin):
    name = "mock"

    def invoke(self, candidate, prompt, max_tokens) -> BindingResponse:
        return BindingResponse(
            content="A",
            reasoning_content=None,
            usage=TokenUsage(prompt_tokens=5, completion_tokens=3, total_tokens=8),
            latency_ms=10,
            model_deployment=candidate.binding.deployment,
            finish_reason="stop",
        )


def _engine(binding: BindingPlugin) -> MatrixEngine:
    return MatrixEngine(
        max_workers=1,
        retry_attempts=1,
        retry_base_delay_s=0.0,
        sleep=lambda _: None,
        clock=lambda: datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc),
        run_id_factory=lambda: "deadbeef",
        binding_factory=lambda _provider: binding,
    )


_DEFAULT_EVALUATORS: dict[str, str] = {"t1.classification_accuracy": "exact_match"}


def test_run_persists_to_repository_when_provided(tmp_path: Path) -> None:
    repo = MatrixRunRepository(tmp_path / "mmfp.db")
    engine = _engine(_FixedBinding())

    run = engine.run(
        _rubric(),
        [_dataset()],
        [_candidate()],
        dimension_evaluators=_DEFAULT_EVALUATORS,
        repository=repo,
        product="mli",
    )

    loaded = repo.get(run.id)
    assert loaded == run
    listed = repo.list_for_product("mli")
    assert [r.id for r in listed] == [run.id]


def test_run_does_not_persist_without_repository(tmp_path: Path) -> None:
    """Persistence is opt-in: the default engine.run() path doesn't touch
    a DB, which keeps every existing unit test in `test_matrix.py` from
    needing a tmp_path fixture."""
    repo = MatrixRunRepository(tmp_path / "mmfp.db")
    engine = _engine(_FixedBinding())

    run = engine.run(
        _rubric(),
        [_dataset()],
        [_candidate()],
        dimension_evaluators=_DEFAULT_EVALUATORS,
    )

    assert run.id == "deadbeef"
    assert repo.list_for_product("mli") == []


def test_run_rejects_repository_without_product(tmp_path: Path) -> None:
    repo = MatrixRunRepository(tmp_path / "mmfp.db")
    engine = _engine(_FixedBinding())

    with pytest.raises(ValueError, match="repository and product"):
        engine.run(
            _rubric(),
            [_dataset()],
            [_candidate()],
            dimension_evaluators=_DEFAULT_EVALUATORS,
            repository=repo,
        )


def test_run_rejects_product_without_repository(tmp_path: Path) -> None:
    engine = _engine(_FixedBinding())

    with pytest.raises(ValueError, match="repository and product"):
        engine.run(
            _rubric(),
            [_dataset()],
            [_candidate()],
            dimension_evaluators=_DEFAULT_EVALUATORS,
            product="mli",
        )


def test_persisted_run_round_trips_with_decimal_score(tmp_path: Path) -> None:
    """End-to-end smoke: engine emits a Decimal('100') score for an exact
    match, that survives engine→repo→get with no precision drift. Belt
    and braces over the unit-level Decimal test in
    `test_matrix_run_repository.py`."""
    repo = MatrixRunRepository(tmp_path / "mmfp.db")
    engine = _engine(_FixedBinding())

    run = engine.run(
        _rubric(),
        [_dataset()],
        [_candidate()],
        dimension_evaluators=_DEFAULT_EVALUATORS,
        repository=repo,
        product="mli",
    )

    loaded = repo.get(run.id)
    assert loaded is not None
    assert isinstance(loaded.results[0].score.normalized_score, Decimal)
    assert loaded.results[0].score.normalized_score == Decimal("100")
