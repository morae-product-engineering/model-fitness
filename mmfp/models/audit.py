"""Audit log model — the production-decision evidence trail (MLI-201).

A candidate-status change (promote to primary/fallback, reject, revert) is
recorded as one immutable `AuditLogEntry`. This is SOC-2 evidence material: it
is cited in audits, not just "a log". See the MLI-199 / MLI-201
architectural-reality comments (2026-06-02) for the decisions baked in here.

Two shapes, split by who owns each field:

  * `StatusChange` — the decision *content* a caller supplies (action, tier,
    candidate, status delta, rationale, the rubric/run pinned at decision time).
    The API layer (MLI-202) builds this from the request.
  * `AuditLogEntry` — the persisted record. It extends `StatusChange` with the
    fields the persistence layer assigns and owns: the server-side `id`,
    `timestamp`, monotonic `sequence`, and the `prev_hash` / `entry_hash` that
    form the tamper-evidence chain. Callers never set these;
    `AuditLogRepository.append` does.

`rationale` is the system of record (MLI-199 rationale-storage decision = B): the
written justification lives here, on the normalised log, not denormalised on the
candidate row.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from mmfp.models._common import (
    MMFP_MODEL_CONFIG,
    SCHEMA_VERSION,
    SchemaVersion,
    UTCDatetime,
)
from mmfp.models.candidate import CandidateStatus, TierId

# One reconciled placeholder actor until SSO populates a real identity — the
# same string MLI-365 settled on for the rubric steward, kept identical on
# purpose so the two logs reconcile to one identity when SSO lands.
PLACEHOLDER_ACTOR = "Unknown Steward <steward@unknown.local>"


class AuditAction(str, Enum):
    """The status-change actions this log records (MLI-201 field list)."""

    PROMOTE_PRIMARY = "promote_primary"
    PROMOTE_FALLBACK = "promote_fallback"
    REJECT = "reject"
    REVERT = "revert"


class StatusChange(BaseModel):
    """The decision content a caller records — everything that is NOT
    server-assigned. `AuditLogRepository.append` stamps the server + chain
    fields around this."""

    model_config = MMFP_MODEL_CONFIG

    action: AuditAction
    tier_id: TierId
    candidate_deployment: str = Field(
        min_length=1,
        description="Provider-side deployment the decision concerns (Candidate.binding.deployment)",
    )
    previous_status: CandidateStatus
    new_status: CandidateStatus
    rationale: str = Field(
        min_length=1,
        description=(
            "Required written justification. The system of record (MLI-199 "
            "rationale-storage = B): rationale lives on this log, not on the "
            "candidate row."
        ),
    )
    rubric_version_at_time: str = Field(
        pattern=r"^v\d+\.\d+$",
        description="Rubric.version in force when the decision was made",
    )
    run_id_at_time: str = Field(
        min_length=1,
        description="MatrixRun.id whose scores informed the decision",
    )
    actor: str = Field(
        default=PLACEHOLDER_ACTOR,
        min_length=1,
        description="Who made the decision; one reconciled placeholder until SSO",
    )


class AuditLogEntry(StatusChange):
    """One immutable, hash-chained audit record.

    Server fields (`id`, `sequence`, `timestamp`) and chain fields
    (`prev_hash`, `entry_hash`) are assigned by `AuditLogRepository.append`,
    never by the caller. `entry_hash` defaults empty only as a construction
    placeholder — the repository computes it over the canonical content (every
    field except `entry_hash` itself) and a persisted record always carries it.
    """

    schema_version: SchemaVersion = SCHEMA_VERSION
    id: str = Field(min_length=1, description="Record identifier (UUID hex)")
    sequence: int = Field(
        ge=0,
        description=(
            "Per-product monotonic position. Doubles as the hash-chain index and "
            "as the tie-breaker that orders entries sharing a millisecond "
            "timestamp."
        ),
    )
    timestamp: UTCDatetime = Field(description="Server-side decision time, UTC")
    prev_hash: str = Field(
        min_length=1,
        description="entry_hash of the prior record; a genesis constant for the first",
    )
    entry_hash: str = Field(
        default="",
        description="sha256 over canonical content incl prev_hash; set by the repository",
    )


class ChainVerification(BaseModel):
    """Result of `AuditLogRepository.verify_chain` — tamper-evidence, detection
    only. `ok` is False the moment any link, sequence, or content hash fails."""

    model_config = MMFP_MODEL_CONFIG

    ok: bool
    entries_verified: int = 0
    broken_at_sequence: int | None = None
    detail: str | None = None
