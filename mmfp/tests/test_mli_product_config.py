# @jira: MLI-173 — validates that the MLI rubric / candidate / dataset YAML
# parses cleanly into the Pydantic models, and that the matrix engine can
# consume them and produce a non-empty matrix run. Binding is mocked so the
# test runs offline; evaluators are the real registered plugins.

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from mmfp.engine.matrix import MatrixEngine
from mmfp.evaluators import _registry as evaluator_registry
from mmfp.models.binding_response import BindingResponse, TokenUsage
from mmfp.models.candidate import Candidate, CandidateFamily
from mmfp.models.dataset import Dataset
from mmfp.models.rubric import Rubric
from mmfp.plugins.binding import BindingPlugin


def test_rubric_parses_cleanly(real_rubric: Rubric) -> None:
    assert real_rubric.version == "v0.1"
    assert {t.id for t in real_rubric.tiers} == {"tier_1", "tier_2", "tier_3"}
    # MLI-272: weight contract is now "active partition sums to (0, 100]"
    # rather than "all dimensions sum to 100". Draft dimensions carry
    # weight 0 per the MLI-269 architectural-input. v0.1 active totals:
    # tier_1=100 (5/5 active), tier_2=80 (5/7 active), tier_3=20 (2/7 active).
    expected_active_totals = {"tier_1": 100, "tier_2": 80, "tier_3": 20}
    for tier in real_rubric.tiers:
        active_total = sum(d.weight for d in tier.active_dimensions())
        assert active_total == expected_active_totals[tier.id], (
            f"tier {tier.id} active weights must sum to "
            f"{expected_active_totals[tier.id]}, got {active_total}"
        )


def test_dimension_evaluators_are_registered(real_rubric: Rubric) -> None:
    # MLI-272: only active dimensions must reference registered evaluators.
    # Draft dimensions name their intended future evaluator as documentary
    # intent (Slice 6's LLM-judge / composite families); the engine never
    # dispatches to them, so registry membership is enforced at load time
    # only for the active partition.
    known = set(evaluator_registry.names())
    referenced = {
        d.evaluator
        for tier in real_rubric.tiers
        for d in tier.active_dimensions()
    }
    missing = referenced - known
    assert not missing, f"rubric references unregistered evaluators: {sorted(missing)}"


def test_candidates_cover_every_tier(
    real_candidates: list[Candidate], real_rubric: Rubric
) -> None:
    tier_ids = {t.id for t in real_rubric.tiers}
    covered = {tier for c in real_candidates for tier in c.tiers}
    missing = tier_ids - covered
    assert not missing, f"no candidate assigned to tier(s): {sorted(missing)}"
    # Reasoning-class candidates need ≥ 4096 tokens per MLI-165 §1 (Kimi
    # was the trigger; rule generalised). Catch a regression at config load.
    for c in real_candidates:
        if c.family is CandidateFamily.REASONING:
            assert c.max_tokens >= 4096, (
                f"reasoning candidate {c.id} has max_tokens={c.max_tokens}; "
                "needs ≥ 4096 to cover the reasoning trace + visible content"
            )


def test_datasets_match_a_tier(
    real_dataset: list[Dataset], real_rubric: Rubric
) -> None:
    tier_ids = {t.id for t in real_rubric.tiers}
    for ds in real_dataset:
        assert ds.tier_id in tier_ids, (
            f"dataset {ds.id} declares tier {ds.tier_id}, not in rubric"
        )
        assert ds.examples, f"dataset {ds.id} has no examples"


class _StubBinding(BindingPlugin):
    """Returns a fixed response that satisfies one evaluator family per tier.

    Exists only to drive the engine end-to-end without network. The point
    of this test is `MatrixEngine.run()` produces a populated `MatrixRun`
    against real config files — not whether the candidates actually
    perform well.
    """

    name = "azure_foundry"

    _RESPONSE_CONTENT = (
        '{"summary": "stub synthesis — see Section 1 for details", '
        '"citations": ["Section 1"], '
        '"recommendations": ["follow up"], '
        '"effective_date": "2026-01-01", '
        '"parties": ["A", "B"], '
        '"governing_law": "England and Wales", '
        '"term_start": "2026-01-01", "term_months": 12, "monthly_rent_gbp": 100, '
        '"term_years": 1, "mutual": true, '
        '"case_name": "Doe v Roe", "year": 2026, "court": "Stub", "citation": "[2026] STUB 1", '
        '"title": "Stub Act", "section": "§ 1", "jurisdiction": "UK", '
        '"sow_number": "SOW-1", "kickoff_date": "2026-01-01", "duration_weeks": 1, "fee_gbp": 1, '
        '"matter_id": "MAT-1", "notice_date": "2026-01-01", "custodians": ["X"], '
        '"doc_id": "DOC-1", "date": "2026-01-01", "basis": "privilege", '
        '"regulator": "FCA", "filing_id": "FCA-1", "filed_on": "2026-01-01", "category": "Annual", '
        '"invoice_number": "INV-1", "invoice_date": "2026-01-01", "amount_gbp": 1, "client": "C"}'
    )

    def invoke(
        self, candidate: Candidate, prompt: str, max_tokens: int
    ) -> BindingResponse:
        return BindingResponse(
            content=self._RESPONSE_CONTENT,
            reasoning_content=None,
            usage=TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
            latency_ms=1,
            model_deployment=candidate.binding.deployment,
            finish_reason="stop",
        )


def test_engine_runs_with_real_config(
    real_rubric: Rubric,
    real_dataset: list[Dataset],
    real_candidates: list[Candidate],
    real_dimension_evaluators: Mapping[str, str],
) -> None:
    """End-to-end: real YAML → Rubric/Candidate/Dataset → MatrixEngine →
    non-empty MatrixRun. Binding is stubbed; evaluators are real."""

    engine = MatrixEngine(
        binding_factory=lambda _provider: _StubBinding(),
        # `max_workers=1` keeps the test deterministic and avoids the
        # ThreadPoolExecutor noise that ThreadPool surfaces on tiny matrices.
        max_workers=1,
    )

    run = engine.run(
        rubric=real_rubric,
        datasets=real_dataset,
        candidates=real_candidates,
        dimension_evaluators=real_dimension_evaluators,
    )

    assert run.rubric_version == real_rubric.version
    assert run.results, "engine produced no results"
    # Every tier has at least one scored cell — the AC for MLI-173.
    tiers_with_results = {r.tier_id for r in run.results}
    assert tiers_with_results == {"tier_1", "tier_2", "tier_3"}


def test_engine_validates_dimension_coverage_when_mapping_omits_a_dimension(
    real_rubric: Rubric,
    real_dataset: list[Dataset],
    real_candidates: list[Candidate],
) -> None:
    """Sanity check on the engine's coverage validation. If a future edit
    drops an evaluator off a dimension, the engine surfaces it before any
    binding is called — useful failure mode to lock in."""

    bad_mapping: dict[str, str] = {}  # missing every dimension
    engine = MatrixEngine(binding_factory=lambda _p: _StubBinding(), max_workers=1)
    with pytest.raises(ValueError, match="dimension_evaluators missing entries"):
        engine.run(
            rubric=real_rubric,
            datasets=real_dataset,
            candidates=real_candidates,
            dimension_evaluators=bad_mapping,
        )


def _all_evaluator_names_used_by(rubric: Rubric) -> set[str]:
    # MLI-272: scoped to active dimensions — drafts may reference future
    # evaluator names (LLM-judge, composite) that aren't registered yet.
    return {
        d.evaluator for tier in rubric.tiers for d in tier.active_dimensions()
    }


def test_rubric_evaluators_are_a_subset_of_registered(real_rubric: Rubric) -> None:
    # Tighter form of `test_dimension_evaluators_are_registered` — keeps a
    # single source of truth for "what evaluators may a rubric reference".
    referenced = _all_evaluator_names_used_by(real_rubric)
    registered = set(evaluator_registry.names())
    assert referenced.issubset(registered)


def test_candidate_unique_ids(real_candidates: list[Candidate]) -> None:
    ids = [c.id for c in real_candidates]
    assert len(set(ids)) == len(ids), f"duplicate candidate ids: {ids}"


def test_candidate_deployment_unique(real_candidates: list[Candidate]) -> None:
    """Two candidate rows mapping to the same Foundry deployment would
    silently double-bill against that deployment's quota; flag it."""
    deployments: dict[str, list[str]] = {}
    for c in real_candidates:
        deployments.setdefault(c.binding.deployment, []).append(c.id)
    dupes = {dep: ids for dep, ids in deployments.items() if len(ids) > 1}
    assert not dupes, f"deployments referenced by multiple candidates: {dupes}"


# Spot-check that our stub satisfies the runtime contract — keeps this file
# self-contained in the face of future BindingResponse field additions.
def test_stub_response_validates() -> None:
    stub = _StubBinding()
    candidate_stub: Any = type(
        "C",
        (),
        {"binding": type("B", (), {"deployment": "stub"})},
    )()
    response = stub.invoke(candidate_stub, "ping", 10)
    assert isinstance(response, BindingResponse)
    assert response.content
