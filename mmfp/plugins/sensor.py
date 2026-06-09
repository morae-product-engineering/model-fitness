"""SensorPlugin — the contract every drift sensor implements (MFP-93).

P3 plugin interface — the fourth stable boundary, joining `EvaluatorPlugin`
and `BindingPlugin`. The signature is the public boundary; modifications need
explicit human approval per CLAUDE.md. This signature is PROPOSED and awaits
Wayne's sign-off (see MFP-ADR-005); it is not yet frozen.

Where evaluation (EvaluatorPlugin) scores a candidate's response against a
rubric dimension at *assessment* time, a sensor watches an *already-promoted*
candidate's *live* behaviour and flags when it diverges from the baseline
matrix run it was promoted on. Evaluation answers "is this candidate good
enough to promote?"; drift detection answers "is the candidate we promoted
still behaving the way it did when we promoted it?". Different lifecycle phase,
different inputs (baseline run + live samples vs. dataset examples), different
output (`DriftSignal | None` vs. `EvaluatorScore`) — hence a distinct boundary
rather than an overload of EvaluatorPlugin.

The split into `sample` and `detect` keeps acquisition (which may touch live
telemetry later) separate from comparison (pure, deterministic). In R1 the
source is a seeded fixture; later sub-tasks swap in live telemetry behind the
same `LiveSampleSource` seam without changing `detect`. The concrete
`DriftSensor` lands in MFP-94+ under `mmfp.sensors.drift`; this module defines
the contract only.

ASSUMES: severity thresholds (the delta-to-band mapping) are sensor
configuration, NOT part of this interface or the `DriftSignal` model — so
re-tuning thresholds never re-classifies already-persisted signals. This needs
Wayne's sign-off before MFP-94 implements a concrete sensor.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar, TypeAlias

from mmfp.models.drift import DriftSignal

if TYPE_CHECKING:
    from mmfp.models.matrix_run import MatrixRun

# TODO(MFP-94): replace these stubs with the concrete live-sample types.
# The MFP-92 acceptance test feeds the sensor loosely-shaped telemetry dicts
# (`{"dimension_id", "candidate_id", "tier_id", "normalized_score"}`), so the
# concrete `LiveSample` shape is deliberately deferred to the sub-task that
# settles it. `LiveSampleSource` is the seam a sensor pulls samples from —
# a seeded fixture in R1, live telemetry later. Kept as aliases (not Protocols)
# so this boundary commits to the method *signatures* without prematurely
# freezing the sample/source shapes the sampler sub-task owns.
LiveSample: TypeAlias = Any
LiveSampleSource: TypeAlias = Any


class SensorPlugin(ABC):
    """Abstract base class for all drift sensors."""

    name: ClassVar[str]
    """Registry key — concrete subclasses must override."""

    @abstractmethod
    def sample(
        self,
        candidate_id: str,
        tier_id: str,
        source: LiveSampleSource,
    ) -> list[LiveSample]:
        """Pull live samples for a promoted candidate on a tier from `source`.

        candidate_id, tier_id: scope acquisition to one promoted candidate on
            one tier (the pair the CandidateStatus store records as promoted).
        source: where live samples come from — a seeded fixture in R1, live
            telemetry later. The seam that lets acquisition evolve without
            touching `detect`.

        Implementations may touch IO (telemetry, storage) here; `detect` must
        not. Returns the samples to hand to `detect`; an empty list is valid
        (no live traffic yet) and `detect([])` should return `None`.
        """
        ...

    @abstractmethod
    def detect(
        self,
        candidate_id: str,
        tier_id: str,
        baseline: "MatrixRun",
        live_samples: list[LiveSample],
    ) -> DriftSignal | None:
        """Compare live samples against the baseline run; emit a signal or not.

        candidate_id, tier_id: the promoted candidate/tier under watch.
        baseline: the `MatrixRun` the candidate was promoted on — the reference
            the live samples are measured against.
        live_samples: output of `sample` (or supplied directly in tests).

        Returns a `DriftSignal` when the divergence is material, else `None`.
        Must be pure and deterministic: same inputs return the same result, no
        IO, no wall-clock beyond the `detected_at` the sensor stamps from a
        clock the caller controls. The delta-to-severity thresholds are
        implementation configuration (see module docstring / MFP-ADR-005).
        """
        ...
