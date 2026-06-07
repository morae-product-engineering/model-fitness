"""Promote / reject / audit-log endpoints (MLI-202).

Three routes on one router:

  POST /api/products/{product}/candidates/{deployment}/promote
  POST /api/products/{product}/candidates/{deployment}/reject
  GET  /api/products/{product}/audit-log

The promote and reject routes share ``_apply_status_change``, which sources
evidence from the latest MatrixRun, builds the ``StatusChange`` for the audit
log, and then writes in audit-first order:

  1. ``audit_repo.append(change, product=product)`` — committed unconditionally.
  2. ``status_store.set(...)``                        — may fail or conflict.

Failure semantics are explicit (MLI-365 lesson — no unhandled raises above
CORSMiddleware):

  * ``CandidateStatusVersionConflict`` from status_store.set → 409. The audit
    entry already committed and STANDS as recorded intent. A 409 here means
    two concurrent callers raced; the winner's status won but both intentions
    are audited. The response body and the log note this.
  * Any other exception from status_store.set → 500, audit entry still stands.
    The audit entry records a *decision* that was made; if the durable write
    of the current-state record failed, the audit trail still has the evidence.

Actor identity: ``X-Steward-Identity`` HTTP header → actor; fallback
``PLACEHOLDER_ACTOR`` (the ONE reconciled placeholder across the stack, per
MLI-365).

Concurrency: per-product in-process ``threading.Lock`` on the promote/reject
critical section mirrors the approach in ``rubric_write.py`` and
``audit_log.py``. Single-replica correctness only — ASSUMES minReplicas=
maxReplicas=1. Cross-replica safety via blob ETag is the documented fast-follow.
"""

from __future__ import annotations

import logging
import re
import threading
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# Re-use the providers already defined in scoreboard.py — the endpoint needs
# the same MatrixRunRepository and candidate loader.
from mmfp.api.scoreboard import get_candidate_loader, get_repository
from mmfp.models.audit import (
    PLACEHOLDER_ACTOR,
    AuditAction,
    AuditLogEntry,
    StatusChange,
)
from mmfp.models.candidate import CandidateStatus, TierId
from mmfp.persistence import MatrixRunRepository
from mmfp.persistence.audit_log import AuditLogRepository
from mmfp.persistence.audit_log import get_audit_log_repository as _get_audit_log_repository
from mmfp.persistence.candidate_status import (
    CandidateStatusStore,
    CandidateStatusVersionConflict,
)
from mmfp.persistence.candidate_status import (
    get_candidate_status_store as _get_candidate_status_store,
)

# ---------------------------------------------------------------------------
# Thin no-args wrappers so FastAPI doesn't try to JSON-schema the ``clock``
# Callable parameter on the underlying factory functions (MLI-202). The
# wrappers are what dependency_overrides targets in tests.
# ---------------------------------------------------------------------------


def get_audit_log_repository() -> AuditLogRepository:
    """FastAPI Depends provider — thin wrapper so ``clock`` is not exposed."""
    return _get_audit_log_repository()


def get_candidate_status_store() -> CandidateStatusStore:
    """FastAPI Depends provider — thin wrapper so ``clock`` is not exposed."""
    return _get_candidate_status_store()

logger = logging.getLogger(__name__)

router = APIRouter(tags=["promotion"])

# Product slug pattern: matches rubric_write.py — lowercase letters, digits,
# dashes, underscores. Forbids path-traversal segments.
_PRODUCT_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

# Header carrying the actor's identity (same header name as the rubric-write
# steward — one identity scheme across the stack).
_STEWARD_HEADER = "X-Steward-Identity"

# Per-product locks for the promote/reject critical section (read-current-status
# → audit → status-write). Single-replica correctness only; see module docstring.
_locks_guard = threading.Lock()
_product_locks: dict[str, threading.Lock] = {}


def _lock_for(product: str) -> threading.Lock:
    with _locks_guard:
        lock = _product_locks.get(product)
        if lock is None:
            lock = threading.Lock()
            _product_locks[product] = lock
        return lock


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class PromoteRequest(BaseModel):
    tier_id: TierId
    role: Literal["primary", "fallback"]
    rationale: str = Field(
        min_length=1,
        description="Required written justification (system of record: audit log)",
    )


class RejectRequest(BaseModel):
    tier_id: TierId
    rationale: str = Field(
        min_length=1,
        description="Required written justification (system of record: audit log)",
    )


class StatusChangeResponse(BaseModel):
    """Minimal response for a successful promote/reject.

    ``audit_ref`` is the audit entry's ``id`` (a UUID hex) — use it with the
    GET audit-log endpoint to retrieve the full entry.
    """

    product: str
    tier_id: TierId
    candidate_deployment: str
    previous_status: CandidateStatus
    new_status: CandidateStatus
    version: int = Field(description="New version of the status record in the store")
    audit_ref: str = Field(description="id of the AuditLogEntry written for this decision")
    audit_sequence: int = Field(description="Monotonic sequence of the AuditLogEntry")


class AuditLogResponse(BaseModel):
    product: str
    entries: list[AuditLogEntry]


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------


def _apply_status_change(
    *,
    product: str,
    deployment: str,
    tier_id: TierId,
    action: AuditAction,
    new_status: CandidateStatus,
    rationale: str,
    actor: str,
    repo: MatrixRunRepository,
    candidate_loader,
    audit_repo: AuditLogRepository,
    status_store: CandidateStatusStore,
) -> StatusChangeResponse | JSONResponse:
    """Core promote/reject logic. Shared by both write endpoints.

    Returns a ``StatusChangeResponse`` (200) or a ``JSONResponse`` (409 on
    status version conflict). All other failures raise ``HTTPException``.

    Steps (in order):
      1. Validate product + load slate (404 on miss).
      2. Find candidate by deployment name (404 on miss).
      3. Validate tier_id ∈ candidate.tiers (422 — correctness guard).
      4. Source run_id + rubric_version from the latest MatrixRun (409 when absent).
      5. Read current per-tier status record (seed status when absent).
      6. Build StatusChange + append to audit log (committed before status write).
      7. Write new status record (version conflict → 409; other error → 500).
         Both failure modes leave the audit entry standing as recorded intent.
    """
    # Step 1: product slug + slate load
    if not _PRODUCT_SLUG_RE.match(product):
        raise HTTPException(status_code=404, detail=f"Unknown product '{product}'")

    try:
        candidates = candidate_loader(product)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Unknown product '{product}'")

    # Step 2: find the candidate by deployment name
    candidate = next(
        (c for c in candidates if c.binding.deployment == deployment), None
    )
    if candidate is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown candidate deployment '{deployment}' in product '{product}'",
        )

    # Step 3: tier must be in candidate.tiers (correctness guard — promoting a
    # candidate in a tier it isn't being evaluated in is invalid regardless of
    # its current status in that tier)
    if tier_id not in candidate.tiers:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Candidate '{deployment}' is not being evaluated in tier '{tier_id}'. "
                f"Valid tiers for this candidate: {candidate.tiers}"
            ),
        )

    # Step 4: source evidence from the latest MatrixRun
    runs = repo.list_for_product(product, limit=1)
    if not runs:
        return JSONResponse(
            status_code=409,
            content={
                "error": "no_matrix_run",
                "detail": (
                    f"No scored matrix run found for product '{product}'. "
                    "A promote/reject decision must reference a run whose scores "
                    "informed it. Run the matrix first."
                ),
            },
        )
    run = runs[0]
    run_id_at_time = run.id
    rubric_version_at_time = run.rubric_version

    # Hold the per-product lock from here to the status write so the
    # read-current-status → audit-append → status-set sequence is atomic
    # w.r.t. concurrent callers for the same product. Per-replica only.
    with _lock_for(product):
        # Step 5: read current per-tier status
        rec = status_store.get(product=product, tier_id=tier_id, candidate=deployment)
        previous_status = rec.status if rec else candidate.status
        expected_version = rec.version if rec else 0

        # Step 6: build and commit audit entry (audit-first — stands regardless)
        change = StatusChange(
            action=action,
            tier_id=tier_id,
            candidate_deployment=deployment,
            previous_status=previous_status,
            new_status=new_status,
            rationale=rationale,
            rubric_version_at_time=rubric_version_at_time,
            run_id_at_time=run_id_at_time,
            actor=actor,
        )
        # No idempotency_key: each call generates a distinct audit entry, even
        # if it's logically the same decision retried. The UI shows all entries.
        entry = audit_repo.append(change, product=product)

        logger.info(
            "promotion.audit_committed",
            extra={
                "product": product,
                "deployment": deployment,
                "tier_id": tier_id,
                "action": action.value,
                "audit_id": entry.id,
                "audit_sequence": entry.sequence,
            },
        )

        # Step 7: write new status record
        try:
            new_rec = status_store.set(
                product=product,
                tier_id=tier_id,
                candidate=deployment,
                status=new_status,
                expected_version=expected_version,
            )
        except CandidateStatusVersionConflict as exc:
            # A concurrent caller won the race. The audit entry already
            # committed and stands as recorded intent — two concurrent promotions
            # are both audited even if only one wins the status record. The
            # losing caller gets a 409 so they can retry with the current version.
            logger.warning(
                "promotion.status_version_conflict",
                extra={
                    "product": product,
                    "deployment": deployment,
                    "tier_id": tier_id,
                    "expected_version": exc.expected,
                    "actual_version": exc.actual,
                    "audit_id": entry.id,
                    "note": "audit entry committed and stands as recorded intent",
                },
            )
            return JSONResponse(
                status_code=409,
                content={
                    "error": "status_version_conflict",
                    "detail": (
                        "Concurrent modification: the status record changed between "
                        "the read and the write. The audit entry has been committed "
                        "as recorded intent. Retry with the current version."
                    ),
                    "expected_version": exc.expected,
                    "actual_version": exc.actual,
                    "audit_ref": entry.id,
                },
            )
        except Exception as exc:  # noqa: BLE001 — every persistence failure must surface with CORS
            # Audit entry committed and stands. The current-state record failed to
            # write — log and surface as a structured 500 so the response carries
            # CORS headers (MLI-365 lesson: unhandled raises produce CORS-less 500).
            logger.error(
                "promotion.status_persist_failed",
                extra={
                    "product": product,
                    "deployment": deployment,
                    "tier_id": tier_id,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "audit_id": entry.id,
                    "note": "audit entry committed and stands as recorded intent",
                },
            )
            raise HTTPException(
                status_code=500, detail="failed to persist candidate status change"
            ) from exc

    return StatusChangeResponse(
        product=product,
        tier_id=tier_id,
        candidate_deployment=deployment,
        previous_status=previous_status,
        new_status=new_status,
        version=new_rec.version,
        audit_ref=entry.id,
        audit_sequence=entry.sequence,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "/api/products/{product}/candidates/{deployment}/promote",
    response_model=StatusChangeResponse,
    summary="Promote a candidate to primary or fallback in a tier",
)
def promote_candidate(
    product: str,
    deployment: str,
    payload: PromoteRequest,
    repo: Annotated[MatrixRunRepository, Depends(get_repository)],
    candidate_loader: Annotated[object, Depends(get_candidate_loader)],
    audit_repo: Annotated[AuditLogRepository, Depends(get_audit_log_repository)],
    status_store: Annotated[CandidateStatusStore, Depends(get_candidate_status_store)],
    x_steward_identity: Annotated[str | None, Header(alias=_STEWARD_HEADER)] = None,
) -> StatusChangeResponse | JSONResponse:
    """Promote a candidate to primary or fallback for a given tier.

    Body: ``{tier_id, role: "primary"|"fallback", rationale}``
    role=primary  → action=PROMOTE_PRIMARY, new_status=APPROVED_PRIMARY
    role=fallback → action=PROMOTE_FALLBACK, new_status=APPROVED_FALLBACK
    """
    actor = x_steward_identity or PLACEHOLDER_ACTOR
    if payload.role == "primary":
        action = AuditAction.PROMOTE_PRIMARY
        new_status = CandidateStatus.APPROVED_PRIMARY
    else:
        action = AuditAction.PROMOTE_FALLBACK
        new_status = CandidateStatus.APPROVED_FALLBACK

    return _apply_status_change(
        product=product,
        deployment=deployment,
        tier_id=payload.tier_id,
        action=action,
        new_status=new_status,
        rationale=payload.rationale,
        actor=actor,
        repo=repo,
        candidate_loader=candidate_loader,
        audit_repo=audit_repo,
        status_store=status_store,
    )


@router.post(
    "/api/products/{product}/candidates/{deployment}/reject",
    response_model=StatusChangeResponse,
    summary="Reject a candidate in a tier",
)
def reject_candidate(
    product: str,
    deployment: str,
    payload: RejectRequest,
    repo: Annotated[MatrixRunRepository, Depends(get_repository)],
    candidate_loader: Annotated[object, Depends(get_candidate_loader)],
    audit_repo: Annotated[AuditLogRepository, Depends(get_audit_log_repository)],
    status_store: Annotated[CandidateStatusStore, Depends(get_candidate_status_store)],
    x_steward_identity: Annotated[str | None, Header(alias=_STEWARD_HEADER)] = None,
) -> StatusChangeResponse | JSONResponse:
    """Reject a candidate in a given tier.

    Body: ``{tier_id, rationale}``
    """
    actor = x_steward_identity or PLACEHOLDER_ACTOR
    return _apply_status_change(
        product=product,
        deployment=deployment,
        tier_id=payload.tier_id,
        action=AuditAction.REJECT,
        new_status=CandidateStatus.REJECTED,
        rationale=payload.rationale,
        actor=actor,
        repo=repo,
        candidate_loader=candidate_loader,
        audit_repo=audit_repo,
        status_store=status_store,
    )


@router.get(
    "/api/products/{product}/audit-log",
    response_model=AuditLogResponse,
    summary="Retrieve the promotion/rejection audit log for a product",
)
def get_audit_log(
    product: str,
    audit_repo: Annotated[AuditLogRepository, Depends(get_audit_log_repository)],
    candidate: str | None = Query(default=None),
    tier: TierId | None = Query(default=None),
    since: datetime | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1),
) -> AuditLogResponse:
    """Return audit log entries for a product, newest first.

    Query params:
      candidate — filter by deployment name
      tier      — filter by TierId (bad value → FastAPI 422 automatically)
      since     — return only entries with timestamp >= since (post-filter;
                  the audit repo has no built-in ``since`` param)
      limit     — max entries to return (ge=1)

    Implementation: call repo.list WITHOUT limit (so since-filtering works
    on the full result), apply the since post-filter, then slice to limit.
    Entries come back newest-first from the repo.
    """
    if not _PRODUCT_SLUG_RE.match(product):
        raise HTTPException(status_code=404, detail=f"Unknown product '{product}'")

    # Fetch without limit so since-filtering applies to all matching entries
    entries = audit_repo.list(
        product=product,
        candidate=candidate,
        tier_id=tier,
    )

    if since is not None:
        # Normalise since to UTC for comparison (UTCDatetime on entries is already UTC).
        # A naive `since` (no tzinfo) is treated as UTC — callers omitting offset
        # are almost always sending UTC when talking to this API.
        if since.tzinfo:
            since_utc = since.astimezone(timezone.utc)
        else:
            since_utc = since.replace(tzinfo=timezone.utc)
        entries = [e for e in entries if e.timestamp >= since_utc]

    if limit is not None:
        entries = entries[:limit]

    return AuditLogResponse(product=product, entries=entries)
