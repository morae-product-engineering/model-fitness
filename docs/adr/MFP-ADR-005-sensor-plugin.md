# MFP-ADR-005 — SensorPlugin boundary and DriftSignal model

- **Status:** Proposed
- **Date:** 2026-06-09
- **Sub-task:** MFP-93 (Slice 7, parent MFP-91)
- **Author:** senior-engineer (agent), for Wayne's review
- **Supersedes / relates to:** MFP-92 (Slice 7 acceptance test — pins the
  `DriftSignal` shape and proposes this interface in a non-asserted comment)

> ## Numbering note (needs a glance)
> The MFP-93 brief suggested the filename `MFP-ADR-004-sensor-plugin.md`. But
> `MFP-ADR-004` is **already in use** — it denotes the matrix-run storage /
> persistence contract, referenced from `mmfp/persistence/__init__.py`,
> `mmfp/persistence/matrix_run_repository.py`, `mmfp/engine/matrix.py`, and
> `mmfp/persistence/migrations/0001_initial.sql`. There are also references to
> `ADR-0001`. None of these ADRs exist as files in this repo — they live in
> Confluence (MMFP → Architecture Decision Records). This is the **first ADR
> committed as a repo file**, so there is no local series to read a "next
> number" from. I chose **005** to avoid colliding with the existing
> `MFP-ADR-004`. If the Confluence series already has a different next free
> number, renumber on review.

## Context

The MMFP scores LLM candidates against a versioned rubric and produces
scorecards. Today the platform has three P3 plug-in boundaries:

- `EvaluatorPlugin` — scores a candidate response against one rubric dimension.
- `BindingPlugin` — invokes a candidate model and normalises the response.
- (the rubric/dataset/matrix-run data contracts, persistence in MFP-ADR-004).

Slice 7 adds **post-promotion drift detection**: once a human promotes a
candidate to primary/fallback for a product, we want to notice when that
candidate's *live* behaviour diverges from the **baseline matrix run** it was
promoted on, and surface a signal a human can act on (Monitor UI, later 7.x).

Drift detection is a different lifecycle phase from evaluation, with different
inputs and outputs, so it does not fit `EvaluatorPlugin`:

| Aspect   | EvaluatorPlugin                         | Drift detection                              |
| -------- | --------------------------------------- | -------------------------------------------- |
| Phase    | Assessment (pre-promotion)              | Monitoring (post-promotion)                  |
| Question | "Good enough to promote?"               | "Still behaving as when promoted?"           |
| Inputs   | candidate output + dataset example      | baseline `MatrixRun` + live samples          |
| Output   | `EvaluatorScore` (always)               | `DriftSignal \| None` (only on material drift) |
| Purity   | Pure, deterministic                     | Acquisition may do IO; comparison is pure    |

Overloading `EvaluatorPlugin` would blur a stable P3 boundary (CLAUDE.md P3).
A fourth boundary keeps each contract single-purpose.

## Decision

### 1. `SensorPlugin` ABC (`mmfp/plugins/sensor.py`)

Two methods, splitting acquisition from comparison:

```python
class SensorPlugin(ABC):
    name: ClassVar[str]

    @abstractmethod
    def sample(self, candidate_id: str, tier_id: str,
               source: LiveSampleSource) -> list[LiveSample]: ...

    @abstractmethod
    def detect(self, candidate_id: str, tier_id: str,
               baseline: MatrixRun,
               live_samples: list[LiveSample]) -> DriftSignal | None: ...
```

- `sample` may touch IO (telemetry/storage); `detect` must be pure and
  deterministic. The split lets R1 use a seeded fixture source and later
  sub-tasks swap in live telemetry behind `LiveSampleSource` without changing
  `detect`.
- `LiveSample` / `LiveSampleSource` are **minimal `Any` aliases** with a
  `# TODO(MFP-94)` marker. The MFP-92 acceptance test feeds loosely-shaped
  telemetry dicts, so the concrete sample shape is deferred to the sampler
  sub-task that owns it. The boundary commits to the **method signatures**, not
  to the sample/source shapes.
- This mirrors the proposal MFP-92 left in a comment, unchanged in substance.

### 2. `DriftSignal` model (`mmfp/models/drift.py`)

Pydantic v2, `extra="forbid"`, pure and serialisable (no IO):

`product_id`, `candidate_id`, `tier_id`, `baseline_run_id`, `baseline_score`,
`observed_score`, `delta`, `severity (none|low|high)`, `detected_at`,
`status (active|acknowledged)`, `summary`.

- Scores and `delta` are `Decimal` on the same 0–100 scale the matrix engine
  emits. `delta = observed_score - baseline_score`; a regression is negative.
- `schema_version: Literal["v1"]` is added per the `_common` convention every
  persisted top-level model follows (e.g. `Candidate`, `MatrixRun`).
- `summary` is a non-empty human-readable line the Monitor view renders
  verbatim. It is in the brief's field list and asserted by MFP-92, though not
  in the brief's headline bullet list — included deliberately.
- JSON Schema published at `schemas/v1/driftsignal.json`, generated from the
  model (byte-identical to `model_json_schema()` under the exporter's
  `sort_keys=True, indent=2` convention). A unit test validates a dumped signal
  against it.

### 3. Severity thresholds live in the sensor, not the model

The `delta → {none, low, high}` mapping is **sensor configuration**, not part
of `DriftSignal` or `SensorPlugin`. The model carries the assigned `severity`
value; it does not compute it. Rationale: re-tuning thresholds must not
re-classify already-persisted signals, and different products may warrant
different bands. MFP-92's fixture implies a "high" band at a ≥ 20-point drop;
that specific number is **not** encoded anywhere in this sub-task.

## Decisions that need Wayne's sign-off

1. **The `SensorPlugin` method signature** — `sample` + `detect` two-method
   split, and the `candidate_id, tier_id, baseline, live_samples` argument
   shape of `detect`. As a P3 boundary, changing it later needs explicit
   approval, so freeze it deliberately now.
2. **Severity model** — three bands (`none | low | high`) and the decision to
   keep the thresholds out of the data model. If a continuous severity score or
   a richer band set is wanted, decide before MFP-94 builds the sensor.
3. **`status` lifecycle** — `active | acknowledged` only; no `resolved`. Confirm
   acknowledgement is the only operator action Slice 7 scopes.
4. **ADR number 005** — see the numbering note above.

## Consequences

- Later 7.x sub-tasks depend on this contract: the concrete `DriftSensor`
  (MFP-94+, `mmfp.sensors.drift`), the live-sample source/sampler, the signal
  store, the drift API, and the Monitor UI all read `DriftSignal` and implement
  or call `SensorPlugin`. Settling it first is the point of MFP-93.
- The MFP-92 acceptance test currently imports `DriftSignal` from
  `mmfp.sensors.drift`; that module does not exist yet (MFP-93 is headless).
  When MFP-94 lands `mmfp.sensors.drift`, it should re-export or define
  `DriftSignal` consistently with `mmfp.models.drift.DriftSignal` (the
  authoritative definition).
- `schemas/v1/driftsignal.json` is currently hand-committed and is **not**
  registered in `scripts/export_schemas.py` (that file is outside MFP-93's
  authorised scope). Follow-up: add `DriftSignal` to `TOP_LEVEL_MODELS` so the
  exporter keeps it in lock-step. Until then a unit test guards against drift.

## Alternatives considered

1. **Extend `EvaluatorPlugin` instead of a new boundary.** Rejected: different
   lifecycle, inputs, output, and purity profile (see Context table). Would
   overload a stable P3 contract.
2. **Single `detect`-only method, fold acquisition into the caller.** Rejected:
   couples every caller to live-telemetry plumbing and makes `detect` harder to
   test in isolation. The `sample`/`detect` split keeps the pure comparison
   independently testable (which MFP-92 relies on).
3. **Compute `severity` inside `DriftSignal` (a validator/computed field).**
   Rejected: bakes thresholds into the persisted data model, so re-tuning
   re-classifies history. Severity is a sensor decision; the model records it.
4. **Concrete `LiveSample` Pydantic model now.** Rejected (P1, earn
   complexity): MFP-92 feeds loose dicts and the sampler sub-task owns the
   shape. Defining it now would over-constrain and likely be rewritten.
