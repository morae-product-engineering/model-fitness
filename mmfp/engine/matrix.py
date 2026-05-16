"""MatrixEngine — orchestrates (rubric × datasets × candidates) → MatrixRun.

For each (candidate × dataset_example × dimension) cell, the engine:
  1. Invokes the candidate's binding once per (candidate × example) — one
     model response is scored along every dimension defined by the example's
     tier.
  2. Routes the binding response's `content` or `reasoning_content` to each
     evaluator per `EvaluatorPlugin.scores_field` (MLI-165 §2; MLI-170).
  3. Records a `MatrixRunResult`.

Tier filtering
--------------
A candidate is scored only against the tiers it claims via `Candidate.tiers`
(MLI-165 single-source-of-truth rule). `(candidate, tier)` pairs where
`tier.id not in candidate.tiers` are skipped wholesale: no binding call, no
LangSmith span, no `MatrixRunResult`. Each run emits one INFO log
summarising the skipped-pair counts as an audit trail (MLI-259).

Concurrency
-----------
Per-candidate `ThreadPoolExecutor` (default `max_workers=4`). Within a
candidate, examples and dimensions run sequentially: provider rate limits
are per-deployment, so cross-candidate parallelism is the right axis.
Threads (not asyncio) because the binding ABC is sync at v1.

Failure isolation
-----------------
Per MLI-171: a single (candidate × example) failure produces an errored
`MatrixRunResult` for every dimension that example covers; the run
continues. No full-matrix abort.

Retry policy (in `_retry.py`)
-----------------------------
Exponential backoff on 429 / 5xx (default 1s → 2s → 4s, max 3 attempts).
Other 4xx are non-retriable. After exhaustion: cell marked errored.

Dimension → evaluator dispatch
------------------------------
Engine takes an explicit `dimension_evaluators: Mapping[str, str]` at
`run()` time. The Rubric model deliberately doesn't carry this binding yet
— subtask 2.8 (rubric YAML loader) will likely add it to `Dimension`, but
this PR keeps the model untouched. Validated up-front: missing or unknown
evaluator names raise before any model is called.

Only `status='active'` dimensions are dispatched. `draft` dimensions are
declared in the rubric so its shape matches the v0.1 reference document
but they emit no binding call, no evaluator, no `MatrixRunResult` —
activation is by status flip when their evaluator family ships (MLI-269,
MLI-267).

LangSmith tracing
-----------------
Every binding invoke and every evaluator scoring is a traceable span,
tagged with `run_id`, `rubric_version`, `tier_id`, `candidate_id`,
`candidate_deployment`. The langsmith SDK auto no-ops when
`LANGSMITH_API_KEY` is unset, so unit tests don't need to mock tracing.

Persistence
-----------
By default returns an in-memory `MatrixRun`; pass `repository=` and
`product=` to `run()` to persist on success. Persistence is opt-in
because the unit-test path doesn't need a DB. See MLI-258 and
ADRs/0001-sqlite-persistence.md for the storage contract.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from langsmith import traceable

from mmfp.bindings import _registry as binding_registry
from mmfp.engine._retry import invoke_with_retry
from mmfp.evaluators import _registry as evaluator_registry
from mmfp.models.binding_response import BindingResponse
from mmfp.models.candidate import Candidate
from mmfp.models.dataset import Dataset, DatasetExample
from mmfp.models.matrix_run import (
    EvaluatorScore,
    MatrixRun,
    MatrixRunResult,
    SourceField,
)
from mmfp.models.rubric import Dimension, Rubric, Tier
from mmfp.persistence import MatrixRunRepository
from mmfp.plugins.binding import BindingPlugin
from mmfp.plugins.evaluator import EvaluatorPlugin

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_run_id() -> str:
    return uuid.uuid4().hex


def _to_prompt(example_input: dict[str, Any] | str) -> str:
    """Coerce a `DatasetExample.input` into the v1 binding's single-prompt shape.

    The binding signature accepts only `prompt: str` for v1 (multi-turn /
    system support broadens later, non-breakingly — see binding ABC).
    Strings are passed through; dicts are JSON-serialised so the engine
    runs end-to-end against any reasonable dataset shape and we evolve
    when tier_2 / multi-turn data lands.
    """
    if isinstance(example_input, str):
        return example_input
    return json.dumps(example_input, sort_keys=True, ensure_ascii=False)


class MatrixEngine:
    """Drives a matrix run and emits a `MatrixRun`.

    All I/O-touching collaborators (binding factory, evaluator factory,
    sleep, clock, run id factory) are constructor-injected so tests can
    swap them. Defaults pull bindings/evaluators from the registries
    populated by `mmfp.bindings` / `mmfp.evaluators`.
    """

    def __init__(
        self,
        *,
        max_workers: int = 4,
        retry_attempts: int = 3,
        retry_base_delay_s: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] = _utc_now,
        run_id_factory: Callable[[], str] = _new_run_id,
        binding_factory: Callable[[str], BindingPlugin] | None = None,
        evaluator_factory: Callable[[str], EvaluatorPlugin] | None = None,
    ) -> None:
        self._max_workers = max_workers
        self._retry_attempts = retry_attempts
        self._retry_base_delay_s = retry_base_delay_s
        self._sleep = sleep
        self._clock = clock
        self._run_id_factory = run_id_factory
        self._binding_factory = binding_factory or _default_binding_factory
        self._evaluator_factory = evaluator_factory or _default_evaluator_factory

    def run(
        self,
        rubric: Rubric,
        datasets: Sequence[Dataset],
        candidates: Sequence[Candidate],
        *,
        dimension_evaluators: Mapping[str, str],
        repository: MatrixRunRepository | None = None,
        product: str | None = None,
    ) -> MatrixRun:
        """Execute the matrix and return a populated `MatrixRun`.

        Validates dimension → evaluator coverage and resolves all evaluators
        before any model is called, so misconfiguration fails fast rather
        than burning a candidate's quota.

        Persistence is opt-in: when `repository` is provided, `product`
        must also be supplied (and vice versa) — see MLI-258 / ADR-0001
        for why `product` lives on the row but not on `MatrixRun`. The
        save happens after the run completes successfully; a partial run
        is not persisted (engine still returns the in-memory run with
        errored cells, but that artefact stays out of the DB).
        """
        if (repository is None) != (product is None):
            raise ValueError(
                "repository and product must be provided together "
                "(persistence requires both, or neither)"
            )

        self._validate_coverage(rubric, dimension_evaluators)

        run_id = self._run_id_factory()
        started_at = self._clock()

        # Cache binding instances per provider — sharing the httpx.Client
        # across candidates is cheaper, and keeps connection pooling effective.
        binding_cache: dict[str, BindingPlugin] = {}
        evaluator_cache: dict[str, EvaluatorPlugin] = {}

        def get_binding(provider: str) -> BindingPlugin:
            if provider not in binding_cache:
                binding_cache[provider] = self._binding_factory(provider)
            return binding_cache[provider]

        def get_evaluator(name: str) -> EvaluatorPlugin:
            if name not in evaluator_cache:
                evaluator_cache[name] = self._evaluator_factory(name)
            return evaluator_cache[name]

        # Pre-resolve every evaluator referenced by the rubric. Only active
        # dimensions are dispatched (MLI-269: draft dimensions are declared
        # for shape but not measured), so the registry lookup is also active-
        # only — drafts need no evaluator binding.
        for tier in rubric.tiers:
            for dimension in tier.active_dimensions():
                get_evaluator(dimension_evaluators[dimension.id])

        datasets_by_tier: dict[str, list[Dataset]] = defaultdict(list)
        for dataset in datasets:
            datasets_by_tier[dataset.tier_id].append(dataset)

        self._log_tier_filter_summary(
            run_id=run_id, rubric=rubric, candidates=candidates
        )

        try:
            results = self._traced_run(
                rubric=rubric,
                candidates=candidates,
                datasets_by_tier=datasets_by_tier,
                dimension_evaluators=dimension_evaluators,
                get_binding=get_binding,
                get_evaluator=get_evaluator,
                run_id=run_id,
                langsmith_extra={
                    "metadata": {
                        "run_id": run_id,
                        "rubric_version": rubric.version,
                    },
                    "tags": [f"rubric:{rubric.version}", f"run:{run_id}"],
                },
            )
        finally:
            for binding in binding_cache.values():
                close = getattr(binding, "close", None)
                if callable(close):
                    with suppress(Exception):
                        close()

        completed_at = self._clock()
        run = MatrixRun(
            id=run_id,
            rubric_version=rubric.version,
            started_at=started_at,
            completed_at=completed_at,
            results=results,
        )
        if repository is not None and product is not None:
            repository.save(run, product=product)
        return run

    @staticmethod
    def _validate_coverage(
        rubric: Rubric, dimension_evaluators: Mapping[str, str]
    ) -> None:
        # Active dimensions must have an evaluator (they will run). Drafts
        # don't need one — they're declared in the YAML so the rubric shape
        # matches the v0.1 reference doc, but the engine skips them until
        # status flips to active (MLI-269 / MLI-267).
        missing = [
            d.id
            for tier in rubric.tiers
            for d in tier.active_dimensions()
            if d.id not in dimension_evaluators
        ]
        if missing:
            raise ValueError(
                f"dimension_evaluators missing entries for: {sorted(missing)}. "
                f"Every active rubric dimension must declare an evaluator."
            )

    @staticmethod
    def _log_tier_filter_summary(
        *, run_id: str, rubric: Rubric, candidates: Sequence[Candidate]
    ) -> None:
        # Single INFO line per run so the next live Foundry run can prove
        # tier-filtering was applied (MLI-259 acceptance + MLI-178 cost-leak
        # audit trail). Emitted unconditionally — "ran 19, skipped 0" is just
        # as useful as the skip-everything case.
        skipped_by_tier: dict[str, int] = defaultdict(int)
        ran_by_tier: dict[str, int] = defaultdict(int)
        for candidate in candidates:
            for tier in rubric.tiers:
                if tier.id in candidate.tiers:
                    ran_by_tier[tier.id] += 1
                else:
                    skipped_by_tier[tier.id] += 1
        tier_order = [tier.id for tier in rubric.tiers]
        skipped_breakdown = {t: skipped_by_tier.get(t, 0) for t in tier_order}
        ran_breakdown = {t: ran_by_tier.get(t, 0) for t in tier_order}
        logger.info(
            "matrix run %s tier filter: skipped %d (candidate, tier) pairs %s, "
            "ran %d %s across %d candidate(s)",
            run_id,
            sum(skipped_breakdown.values()),
            skipped_breakdown,
            sum(ran_breakdown.values()),
            ran_breakdown,
            len(candidates),
        )

    @traceable(name="MatrixEngine.run", run_type="chain")
    def _traced_run(
        self,
        *,
        rubric: Rubric,
        candidates: Sequence[Candidate],
        datasets_by_tier: Mapping[str, list[Dataset]],
        dimension_evaluators: Mapping[str, str],
        get_binding: Callable[[str], BindingPlugin],
        get_evaluator: Callable[[str], EvaluatorPlugin],
        run_id: str,
    ) -> list[MatrixRunResult]:
        def _run_one(candidate: Candidate) -> list[MatrixRunResult]:
            return self._run_candidate(
                candidate=candidate,
                rubric=rubric,
                datasets_by_tier=datasets_by_tier,
                dimension_evaluators=dimension_evaluators,
                get_binding=get_binding,
                get_evaluator=get_evaluator,
                run_id=run_id,
            )

        # ThreadPoolExecutor.map preserves submission order, which keeps
        # the results list deterministic — useful for snapshot tests and
        # for humans reading run output.
        with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            per_candidate = list(pool.map(_run_one, candidates))

        flat: list[MatrixRunResult] = []
        for chunk in per_candidate:
            flat.extend(chunk)
        return flat

    def _run_candidate(
        self,
        *,
        candidate: Candidate,
        rubric: Rubric,
        datasets_by_tier: Mapping[str, list[Dataset]],
        dimension_evaluators: Mapping[str, str],
        get_binding: Callable[[str], BindingPlugin],
        get_evaluator: Callable[[str], EvaluatorPlugin],
        run_id: str,
    ) -> list[MatrixRunResult]:
        binding = get_binding(candidate.binding.provider)
        out: list[MatrixRunResult] = []
        for tier in rubric.tiers:
            # MLI-259: a candidate is only scored against the tiers it claims.
            # Cells for unclaimed tiers were real measurements but never fed any
            # routing decision — pure cost leak on Foundry. Skip emits no result,
            # no binding call, no LangSmith span. Per-run audit summary logged
            # once up-front in run().
            if tier.id not in candidate.tiers:
                continue
            for dataset in datasets_by_tier.get(tier.id, ()):
                for example in dataset.examples:
                    out.extend(
                        self._run_cell(
                            tier=tier,
                            dataset=dataset,
                            example=example,
                            candidate=candidate,
                            binding=binding,
                            dimension_evaluators=dimension_evaluators,
                            get_evaluator=get_evaluator,
                            run_id=run_id,
                            rubric_version=rubric.version,
                        )
                    )
        return out

    def _run_cell(
        self,
        *,
        tier: Tier,
        dataset: Dataset,
        example: DatasetExample,
        candidate: Candidate,
        binding: BindingPlugin,
        dimension_evaluators: Mapping[str, str],
        get_evaluator: Callable[[str], EvaluatorPlugin],
        run_id: str,
        rubric_version: str,
    ) -> list[MatrixRunResult]:
        prompt = _to_prompt(example.input)
        response, binding_error = self._invoke_traced(
            binding=binding,
            candidate=candidate,
            prompt=prompt,
            tier_id=tier.id,
            run_id=run_id,
            rubric_version=rubric_version,
            example_id=example.id,
        )

        results: list[MatrixRunResult] = []
        for dimension in tier.active_dimensions():
            evaluator = get_evaluator(dimension_evaluators[dimension.id])
            results.append(
                self._score_dimension(
                    tier=tier,
                    dimension=dimension,
                    evaluator=evaluator,
                    candidate=candidate,
                    dataset=dataset,
                    example=example,
                    response=response,
                    binding_error=binding_error,
                    run_id=run_id,
                    rubric_version=rubric_version,
                )
            )
        return results

    def _invoke_traced(
        self,
        *,
        binding: BindingPlugin,
        candidate: Candidate,
        prompt: str,
        tier_id: str,
        run_id: str,
        rubric_version: str,
        example_id: str,
    ) -> tuple[BindingResponse | None, str | None]:
        @traceable(name="binding.invoke", run_type="llm")
        def _invoke() -> BindingResponse:
            return invoke_with_retry(
                binding,
                candidate,
                prompt,
                candidate.max_tokens,
                max_attempts=self._retry_attempts,
                base_delay_s=self._retry_base_delay_s,
                sleep=self._sleep,
            )

        try:
            response = _invoke(
                langsmith_extra={
                    "metadata": {
                        "run_id": run_id,
                        "rubric_version": rubric_version,
                        "tier_id": tier_id,
                        "candidate_id": candidate.id,
                        "candidate_deployment": candidate.binding.deployment,
                        "example_id": example_id,
                    },
                    "tags": [
                        f"run:{run_id}",
                        f"tier:{tier_id}",
                        f"candidate:{candidate.id}",
                    ],
                }
            )
            return response, None
        except Exception as e:
            # The retry helper has already exhausted backoff. Surface a
            # short reason; LangSmith holds the full trace.
            return None, f"{type(e).__name__}: {e}"

    def _score_dimension(
        self,
        *,
        tier: Tier,
        dimension: Dimension,
        evaluator: EvaluatorPlugin,
        candidate: Candidate,
        dataset: Dataset,
        example: DatasetExample,
        response: BindingResponse | None,
        binding_error: str | None,
        run_id: str,
        rubric_version: str,
    ) -> MatrixRunResult:
        if response is None:
            # Binding failure cascades: every dimension this example
            # would have scored becomes an errored cell.
            score = self._errored_score(
                dimension=dimension,
                evaluator_id=evaluator.name,
                source_field=evaluator.scores_field,
                error=f"binding error: {binding_error}",
            )
            return MatrixRunResult(
                tier_id=tier.id,
                candidate_id=candidate.id,
                dataset_id=dataset.id,
                example_id=example.id,
                score=score,
            )

        candidate_output = self._extract_field(response, evaluator.scores_field)
        if candidate_output is None:
            # Reasoning-content evaluator on a chat-only model. MLI-165 §2
            # — surfaces as an errored cell so it's visible at score time.
            score = self._errored_score(
                dimension=dimension,
                evaluator_id=evaluator.name,
                source_field=evaluator.scores_field,
                error=(
                    f"evaluator '{evaluator.name}' scores "
                    f"{evaluator.scores_field.value} but response had none "
                    f"(candidate family={candidate.family.value})"
                ),
            )
        else:
            score = self._evaluate_traced(
                evaluator=evaluator,
                candidate_output=candidate_output,
                expected=self._coerce_expected(example.expected),
                dimension=dimension,
                run_id=run_id,
                rubric_version=rubric_version,
                tier_id=tier.id,
                candidate=candidate,
                example_id=example.id,
                response=response,
            )

        return MatrixRunResult(
            tier_id=tier.id,
            candidate_id=candidate.id,
            dataset_id=dataset.id,
            example_id=example.id,
            score=score,
            completion_tokens=response.usage.completion_tokens,
            prompt_tokens=response.usage.prompt_tokens,
            finish_reason=response.finish_reason,
        )

    @staticmethod
    def _extract_field(
        response: BindingResponse, source_field: SourceField
    ) -> str | None:
        if source_field is SourceField.CONTENT:
            return response.content
        if response.reasoning_content is None:
            return None
        return response.reasoning_content

    @staticmethod
    def _coerce_expected(expected: Any) -> dict[str, Any]:
        # The deterministic-trio evaluators expect a dict shape
        # (`expected["value"]`, `expected["pattern"]`, `expected["schema"]`).
        # `DatasetExample.expected` is `Any` — non-dict values would only
        # appear from a malformed dataset, but coercing to a dict keeps the
        # error a clean ValueError from the evaluator rather than a
        # TypeError out of attribute access.
        if isinstance(expected, dict):
            return expected
        return {"value": expected}

    def _evaluate_traced(
        self,
        *,
        evaluator: EvaluatorPlugin,
        candidate_output: str,
        expected: dict[str, Any],
        dimension: Dimension,
        run_id: str,
        rubric_version: str,
        tier_id: str,
        candidate: Candidate,
        example_id: str,
        response: BindingResponse,
    ) -> EvaluatorScore:
        # MLI-272: metric / envelope evaluators read from `context`, not from
        # `candidate_output` — populated here so a dimension never has to know
        # the binding shape. `cost_usd` is a defensive 0 placeholder: the
        # binding doesn't emit cost today (KNOWN_GAPS tracks the open work).
        # The 0 value means `cost_per_call` returns "≤ reference → 100" for
        # every candidate; that flattens the cost dimension's discrimination
        # until a cost sensor/binding extension lands.
        eval_context: dict[str, Any] = {
            "dimension_id": dimension.id,
            "evaluator_id": evaluator.name,
            "evaluator_config": dimension.evaluator_config or {},
            "latency_ms": response.latency_ms,
            "candidate_context_window": candidate.context_window,
            "cost_usd": Decimal("0"),
        }

        @traceable(name="evaluator.evaluate", run_type="tool")
        def _do_eval() -> EvaluatorScore:
            return evaluator.evaluate(candidate_output, expected, eval_context)

        try:
            return _do_eval(
                langsmith_extra={
                    "metadata": {
                        "run_id": run_id,
                        "rubric_version": rubric_version,
                        "tier_id": tier_id,
                        "dimension_id": dimension.id,
                        "candidate_id": candidate.id,
                        "candidate_deployment": candidate.binding.deployment,
                        "example_id": example_id,
                        "evaluator": evaluator.name,
                    },
                    "tags": [
                        f"run:{run_id}",
                        f"tier:{tier_id}",
                        f"dimension:{dimension.id}",
                    ],
                }
            )
        except Exception as e:
            return self._errored_score(
                dimension=dimension,
                evaluator_id=evaluator.name,
                source_field=evaluator.scores_field,
                error=f"{type(e).__name__}: {e}",
            )

    @staticmethod
    def _errored_score(
        *,
        dimension: Dimension,
        evaluator_id: str,
        source_field: SourceField,
        error: str,
    ) -> EvaluatorScore:
        return EvaluatorScore(
            dimension_id=dimension.id,
            evaluator_id=evaluator_id,
            raw_value=None,
            normalized_score=Decimal("0"),
            passed=None,
            source_field=source_field,
            error=error,
        )


def _default_binding_factory(provider: str) -> BindingPlugin:
    return binding_registry.get(provider)()


def _default_evaluator_factory(name: str) -> EvaluatorPlugin:
    return evaluator_registry.get(name)()


__all__ = ["MatrixEngine"]
