"""Rubric write endpoint — PUT /api/products/{product}/rubric (MLI-273, MLI-365).

The single path by which a steward updates a product's rubric. Validates the
payload through `Rubric.model_validate` (so every invariant the model enforces —
active-weight sum, draft weight = 0, dimension uniqueness — holds in the
persisted YAML), bumps the `version` field, and persists the new rubric plus an
audit record to durable storage.

MLI-365 — durable persistence, off git
--------------------------------------
The original design (MLI-273) used a git commit as the audit log. That was
incompatible with the deployed environment: the API runs in an ephemeral,
non-git Azure Container App, so `git rev-parse` raised and the save 500'd; and
even where git worked locally the write landed on a non-durable filesystem and
was lost on revision restart. Persistence now goes through `rubric_store`:

  * The rubric + an explicit `AuditRecord` (version delta, note, steward
    identity, timestamp) are written to a durable store (Azure Blob via managed
    identity in the deployed env; disk locally). The blob survives a revision
    restart — that's the durability the git design never had.
  * Any persistence failure is caught and returned as a structured
    `HTTPException`, which flows back through CORSMiddleware and carries CORS
    headers — so the UI shows a real error instead of an opaque "Failed to
    fetch". (An unhandled raise would be turned into a CORS-less 500 above the
    middleware; see the MLI-365 root-cause analysis.)

Concurrency (AC4, MLI-194): the per-product in-process `threading.Lock` still
serialises the read->validate->write critical section. It serialises within a
single replica only — correct for the single-replica dev deployment, which is
pinned `minReplicas=maxReplicas=1`. Cross-replica optimistic concurrency via
blob ETag / If-Match is a documented FAST-FOLLOW, not in this change.

Actor identity (MLI-267 architectural-input, reconciled in MLI-365): a trusted
`X-Steward-Identity` HTTP header, with the single placeholder
`Unknown Steward <steward@unknown.local>` as the fallback when the header is
absent. This is now the ONE placeholder across the stack — the UI sends the
same string (it previously sent a second, divergent `MMFP Editor` placeholder).
When SSO lands, a verifying proxy populates the header server-side.

Concurrency posture (MLI-267): 409 on `expected_version` mismatch
(last-write-loses). The Editor re-fetches and merges in the UI; the server stays
a check-and-write primitive.
"""

from __future__ import annotations

import logging
import re
import threading
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

from mmfp.api.rubric_store import AuditRecord, RubricNotFound, RubricStore, get_rubric_store
from mmfp.models.rubric import Rubric

logger = logging.getLogger(__name__)

router = APIRouter(tags=["rubric"])

# Product slug pattern: lowercase letters, digits, dashes, underscores. Mirrors
# the directory layout in products/ and forbids path-traversal segments.
_PRODUCT_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

# Version-field pattern matches `Rubric.version` in mmfp/models/rubric.py
# (`r"^v\d+\.\d+$"`). The endpoint auto-bumps the minor; major stays where the
# steward last set it. (The steward never edits `version` directly, so
# SemVer-as-monotonic-minor keeps the audit trail human-readable.)
_VERSION_RE = re.compile(r"^v(\d+)\.(\d+)$")

# The single reconciled placeholder steward identity (MLI-365). Until SSO lands,
# both the server fallback and the UI send this exact string; the steward is
# recorded as an explicit field on the audit record. Exposed at module level so
# tests can pin the exact value.
PLACEHOLDER_STEWARD = "Unknown Steward <steward@unknown.local>"

# Header carrying the steward's identity in the trust-the-edge model. When SSO
# lands the deployment puts a verifying proxy in front of the API and populates
# this header server-side; until then, callers (the dev UI, a steward's `curl`)
# set it themselves. See MLI-267 architectural-input.
_STEWARD_HEADER = "X-Steward-Identity"

# Per-product locks serialise the read->validate->write critical section so the
# `expected_version` handshake (the 409 path) holds under concurrency (AC4,
# MLI-194). Correct for the single-replica dev deployment only. This is NOT a
# distributed lock — cross-replica concurrency is the blob-ETag fast-follow.
# ASSUMES the dev Container App is pinned minReplicas=maxReplicas=1.
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


class RubricWriteRequest(BaseModel):
    """Payload for PUT /api/products/{product}/rubric."""

    rubric: dict[str, Any] = Field(
        description="The full rubric dict, in the YAML/JSON shape `Rubric` expects",
    )
    expected_version: str = Field(
        min_length=1,
        description=(
            "The version the steward thinks is currently live; must match the "
            "rubric in the store or the write is rejected with 409"
        ),
    )
    note: str | None = Field(
        default=None,
        description="Optional one-line note recorded in the audit record",
    )


class RubricWriteResponse(BaseModel):
    """Returned on 200."""

    previous_version: str
    new_version: str
    audit_ref: str = Field(
        description=(
            "Storage name of the immutable audit record written for this save "
            "(replaces the git commit_sha the pre-MLI-365 design returned)"
        ),
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _bump_minor(version: str) -> str:
    """`v0.1` → `v0.2`. Raises if the current version doesn't match the pattern
    enforced by the `Rubric` model — unreachable as long as the stored rubric
    loaded through `Rubric.model_validate` somewhere."""
    match = _VERSION_RE.match(version)
    if not match:
        # Defensive — the stored rubric should never reach this state.
        raise ValueError(f"unparseable rubric version in store: {version!r}")
    major, minor = match.group(1), int(match.group(2))
    return f"v{major}.{minor + 1}"


def _utcnow_iso() -> str:
    """Current UTC time as an ISO 8601 string for the audit record timestamp."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.put(
    "/api/products/{product}/rubric",
    response_model=RubricWriteResponse,
    summary="Steward-write a product's rubric",
)
def put_rubric(
    product: str,
    request: Request,
    payload: RubricWriteRequest,
    store: Annotated[RubricStore, Depends(get_rubric_store)],
    x_steward_identity: Annotated[str | None, Header(alias=_STEWARD_HEADER)] = None,
) -> RubricWriteResponse | JSONResponse:
    if not _PRODUCT_SLUG_RE.match(product):
        # Bad slug → either a typo or a traversal attempt. Treat as 404 to match
        # the unknown-product path on a real miss.
        raise HTTPException(status_code=404, detail=f"Unknown product '{product}'")

    # Hold the per-product lock across read-version -> 409-check -> validate ->
    # persist so the `expected_version` handshake is atomic w.r.t. concurrent
    # writers within this replica (AC4, MLI-194). The `with` block releases the
    # lock on every exit path: the 409 `return`, the 404/422/500 `raise`, and
    # the happy fall-through.
    with _lock_for(product):
        # Read the current rubric from the SAME durable store we write to, so
        # the version handshake reflects persisted state (not a stale on-disk
        # copy). On the deployed env this is the blob; a cold blob bootstraps
        # from the rubric shipped in the image.
        try:
            _current_raw, current_version = store.load(product)
        except RubricNotFound:
            raise HTTPException(status_code=404, detail=f"Unknown product '{product}'")

        if payload.expected_version != current_version:
            # 409 with both versions so the client can show a useful diff dialog.
            # Last-write-*loses* (MLI-267): the second writer rebases their edit
            # on the new current_version themselves. Returned as a top-level body
            # (not under `detail`) because the UI editor needs `current_version`
            # to refetch.
            return JSONResponse(
                status_code=409,
                content={
                    "error": "version_conflict",
                    "current_version": current_version,
                    "expected_version": payload.expected_version,
                },
            )

        # Compute the new version *before* validation so the validator sees the
        # rubric in the shape it will be persisted. The steward's submitted
        # `version` is overwritten — the server owns version assignment.
        new_version = _bump_minor(str(current_version))
        new_rubric_raw = dict(payload.rubric)
        new_rubric_raw["version"] = new_version

        try:
            Rubric.model_validate(new_rubric_raw)
        except ValidationError as exc:
            # Surface the structured errors directly. FastAPI's default 422 body
            # shape is `{"detail": [{loc, msg, type}, ...]}`; we mirror it so the
            # UI has one error shape to render.
            raise HTTPException(
                status_code=422,
                detail=exc.errors(include_url=False, include_context=False, include_input=False),
            ) from exc

        steward = x_steward_identity or PLACEHOLDER_STEWARD
        audit = AuditRecord(
            product=product,
            previous_version=str(current_version),
            new_version=new_version,
            note=payload.note,
            steward=steward,
            timestamp=_utcnow_iso(),
        )

        # Persist rubric + audit record durably. Any failure (blob unreachable,
        # auth, IO) is caught and returned as a structured HTTPException so the
        # response carries CORS headers and the UI shows a real error rather than
        # "Failed to fetch" (MLI-365 root cause).
        try:
            audit_ref = store.save(product, rubric_raw=new_rubric_raw, audit=audit)
        except Exception as exc:  # noqa: BLE001 — every persistence failure must surface with CORS
            logger.error(
                "rubric.write.persist_failed",
                extra={
                    "product": product,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            raise HTTPException(
                status_code=500, detail="failed to persist rubric change"
            ) from exc

    logger.info(
        "rubric.write",
        extra={
            "product": product,
            "previous_version": current_version,
            "new_version": new_version,
            "audit_ref": audit_ref,
            "actor": steward,
            "note": payload.note,
            "request_path": request.url.path,
        },
    )

    return RubricWriteResponse(
        previous_version=str(current_version),
        new_version=new_version,
        audit_ref=audit_ref,
    )
