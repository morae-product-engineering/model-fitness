"""Append-only, hash-chained audit log for candidate status changes (MLI-201).

Slice 5's production-decision trail: every promote / reject / revert is one
immutable record — an authoritative, tamper-evident account of who changed a
candidate's status and why, that downstream readers can trust to be complete and
unaltered. A data-integrity requirement; see the MLI-199 / MLI-201
architectural-reality comments (2026-06-02). Decisions ratified on MLI-201:

  * **Durable, off local SQLite (store shape C).** Records persist to a durable
    blob store on its OWN dedicated container (NOT ``mmfp-seed``), on the same
    Azure-Blob + managed-identity seam MLI-365 established for rubric writes. The
    deployed Container App filesystem is ephemeral; a local SQLite log would be
    lost on every revision restart, and an authoritative-looking log that
    silently vanishes is worse than none. The low-level wiring lives in
    ``blob_seam.py`` so a future shared rubric+audit primitive ("Option B") is a
    cheap refactor; this module does not touch the rubric save path.

  * **Append-only.** The public API is ``append`` + ``list`` + ``verify_chain``.
    No update, no delete. Entry blobs are written ``overwrite=False`` — a name
    collision raises rather than rewriting history.

  * **Tamper-EVIDENCE via hash chaining (decision B), not tamper-resistance.**
    Each entry carries ``prev_hash`` (the prior entry's ``entry_hash``) and its
    own ``entry_hash`` over canonical content. A retroactive edit, reorder,
    insertion, or deletion breaks the chain and is detected by ``verify_chain``.
    This is detection, NOT prevention: the API's managed identity holds
    ``Storage Blob Data Contributor``, which can delete, so a compromised
    identity could still destroy blobs — what it cannot do is silently alter one
    and have the chain still verify. WORM / immutability-policy on the dedicated
    container is the named infra fast-follow if we later need tamper-RESISTANCE,
    not just tamper-evidence. We do NOT claim WORM here.

  * **Key design for the History access pattern.** Entry names are
    ``<product>/promotion-audit/<tier_id>/<candidate>/<compact_ts>-<seq>-<id>.json``.
    The dominant History queries are bounded prefix scans, not list-everything:
    filter-by-tier is one prefix; filter-by-(tier, candidate) a tighter prefix;
    filter-by-candidate at most three prefixes (``TierId`` is a fixed Literal of
    three). The zero-padded compact timestamp + sequence make a prefix listing
    lexicographically chronological. Only the global recent view (merged with
    rubric history in the History panel) is a product-wide scan — acceptable at
    R1 volumes.

  * **Server-side timestamp + monotonic tie-breaker.** ``timestamp`` is stamped
    by this layer at append time (UTC); ``sequence`` is a per-product monotonic
    counter that doubles as the chain index and the same-millisecond tie-breaker.

  * **Actor is one reconciled placeholder** (``PLACEHOLDER_ACTOR``, identical to
    MLI-365's steward) until SSO populates a real identity.

Concurrency (mirrors MLI-365 / MLI-194): a per-product in-process
``threading.Lock`` serialises the read-head -> assign-sequence -> write critical
section. Correct within a single replica only — the deployed API must stay
pinned ``minReplicas=maxReplicas=1``. Cross-replica safety via blob ETag /
If-Match is a documented fast-follow, not implemented here.

Backend selection (``get_audit_log_repository``): blob when both
``MMFP_AUDIT_BLOB_ACCOUNT_URL`` and ``MMFP_AUDIT_BLOB_CONTAINER`` are set; disk
otherwise — EXCEPT that a missing durable config in the deployed environment
(detected via the auto-set ``CONTAINER_APP_NAME``) is a hard error, never a
silent fall-back to ephemeral disk (the MLI-365 footgun).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Callable

from mmfp.models.audit import (
    PLACEHOLDER_ACTOR,
    AuditLogEntry,
    ChainVerification,
    StatusChange,
)
from mmfp.models.candidate import TierId
from mmfp.persistence.blob_seam import AzureBlobSeam, BlobSeam, DiskBlobSeam

logger = logging.getLogger(__name__)

__all__ = [
    "PLACEHOLDER_ACTOR",
    "GENESIS_PREV_HASH",
    "AuditLogConfigError",
    "AuditLogRepository",
    "get_audit_log_repository",
]

# prev_hash of the first entry in a product's chain — no prior entry to link to.
GENESIS_PREV_HASH = "0" * 64

_AUDIT_PREFIX = "promotion-audit"
_IDEMPOTENCY_SEGMENT = "_idempotency"
# TierId is a fixed Literal of exactly three values, so "filter by candidate"
# (which spans a candidate's tiers) is at most three bounded prefix scans.
_TIER_IDS: tuple[TierId, ...] = ("tier_1", "tier_2", "tier_3")

# Env vars selecting + configuring the dedicated audit container.
ACCOUNT_URL_ENV = "MMFP_AUDIT_BLOB_ACCOUNT_URL"
CONTAINER_ENV = "MMFP_AUDIT_BLOB_CONTAINER"
LOCAL_DIR_ENV = "MMFP_AUDIT_LOCAL_DIR"
# Azure Container Apps sets this in every revision; its presence means "deployed".
DEPLOY_MARKER_ENV = "CONTAINER_APP_NAME"
_DEFAULT_LOCAL_DIR = "data/audit-log"


class AuditLogConfigError(RuntimeError):
    """Durable audit-log storage is required (deployed env) but unconfigured."""


# ---------------------------------------------------------------------------
# Hashing + blob naming
# ---------------------------------------------------------------------------


def _compute_entry_hash(entry: AuditLogEntry) -> str:
    """sha256 over the entry's canonical content — every field except
    ``entry_hash`` itself, including ``prev_hash`` (which chains it to its
    predecessor) and ``sequence`` / ``id`` / ``timestamp`` (so reorder,
    insertion, or deletion are detectable). Canonical = JSON with sorted keys
    and no incidental whitespace, so the hash is stable across producers."""
    payload = entry.model_dump(mode="json", exclude={"entry_hash"})
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _compact_ts(ts: datetime) -> str:
    """UTC, no separators, microsecond precision — lexicographically sortable so
    a prefix listing comes back in chronological order."""
    return ts.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%f")


def _product_prefix(product: str) -> str:
    return f"{product}/{_AUDIT_PREFIX}/"


def _tier_prefix(product: str, tier_id: str) -> str:
    return f"{product}/{_AUDIT_PREFIX}/{tier_id}/"


def _candidate_prefix(product: str, tier_id: str, candidate: str) -> str:
    return f"{product}/{_AUDIT_PREFIX}/{tier_id}/{candidate}/"


def _entry_name(product: str, entry: AuditLogEntry) -> str:
    return (
        f"{_candidate_prefix(product, entry.tier_id, entry.candidate_deployment)}"
        f"{_compact_ts(entry.timestamp)}-{entry.sequence:012d}-{entry.id}.json"
    )


def _idempotency_name(product: str, key: str) -> str:
    return f"{product}/{_AUDIT_PREFIX}/{_IDEMPOTENCY_SEGMENT}/{key}.json"


def _is_entry_name(name: str) -> bool:
    """True for audit entry blobs, False for the idempotency-marker index."""
    return f"/{_IDEMPOTENCY_SEGMENT}/" not in name


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class AuditLogRepository:
    """Append-only, hash-chained store for `AuditLogEntry` over a `BlobSeam`.

    Thread-safety: a per-product in-process lock serialises the
    read-head/assign-sequence/write critical section. Holding one instance
    across threads is fine; correctness across *replicas* needs the
    single-replica pin (see module docstring).
    """

    def __init__(
        self, seam: BlobSeam, *, clock: Callable[[], datetime] | None = None
    ) -> None:
        self._seam = seam
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def append(
        self,
        change: StatusChange,
        *,
        product: str,
        idempotency_key: str | None = None,
    ) -> AuditLogEntry:
        """Record one status change as the next link in the product's chain.

        `idempotency_key` makes a retried append a no-op: if the key was already
        used, the original entry is returned and nothing new is written — no
        double-write, sequence unbroken.
        """
        if not product:
            raise ValueError("product must be a non-empty string")
        with self._lock_for(product):
            if idempotency_key:
                existing = self._load_by_idempotency(product, idempotency_key)
                if existing is not None:
                    return existing

            entries = self._all_entries(product)
            prev = entries[-1] if entries else None
            sequence = prev.sequence + 1 if prev else 0
            prev_hash = prev.entry_hash if prev else GENESIS_PREV_HASH

            draft = AuditLogEntry(
                **change.model_dump(),
                id=uuid.uuid4().hex,
                sequence=sequence,
                timestamp=self._clock(),
                prev_hash=prev_hash,
            )
            entry = draft.model_copy(update={"entry_hash": _compute_entry_hash(draft)})

            # overwrite=False: an entry name collision is a genuine error, never
            # a silent rewrite of history.
            self._seam.write(
                _entry_name(product, entry),
                entry.model_dump_json().encode("utf-8"),
                overwrite=False,
            )
            if idempotency_key:
                self._seam.write(
                    _idempotency_name(product, idempotency_key),
                    _entry_name(product, entry).encode("utf-8"),
                    overwrite=False,
                )
            logger.info(
                "audit_log.append",
                extra={
                    "product": product,
                    "sequence": entry.sequence,
                    "action": entry.action.value,
                    "candidate": entry.candidate_deployment,
                    "tier": entry.tier_id,
                },
            )
            return entry

    def list(
        self,
        *,
        product: str,
        candidate: str | None = None,
        tier_id: TierId | None = None,
        limit: int | None = None,
        newest_first: bool = True,
    ) -> list[AuditLogEntry]:
        """Entries for a product, time-ordered, optionally filtered by candidate
        and/or tier. The filter chooses a bounded prefix set (see
        ``_query_prefixes``) so the dominant History queries do not scan the
        whole product."""
        if limit is not None and limit < 0:
            raise ValueError("limit must be non-negative")

        names: set[str] = set()
        for prefix in self._query_prefixes(product, candidate, tier_id):
            names.update(n for n in self._seam.list_names(prefix) if _is_entry_name(n))

        entries = [self._load_entry(n) for n in names]
        # The prefix set bounds the scan; an explicit in-memory filter keeps the
        # result exact regardless of which prefix dimension was used.
        if tier_id is not None:
            entries = [e for e in entries if e.tier_id == tier_id]
        if candidate is not None:
            entries = [e for e in entries if e.candidate_deployment == candidate]

        entries.sort(key=lambda e: (e.timestamp, e.sequence), reverse=newest_first)
        return entries[:limit] if limit is not None else entries

    def verify_chain(self, *, product: str) -> ChainVerification:
        """Walk the product's chain in sequence order and confirm every link.

        Detects (returns ``ok=False`` at the first failure): a content edit
        (recomputed hash ≠ stored), a broken link (``prev_hash`` ≠ prior
        ``entry_hash``), or a sequence gap from an insertion/deletion/reorder.
        """
        entries = self._all_entries(product)
        expected_prev = GENESIS_PREV_HASH
        for index, entry in enumerate(entries):
            if entry.sequence != index:
                return ChainVerification(
                    ok=False,
                    entries_verified=index,
                    broken_at_sequence=entry.sequence,
                    detail=f"sequence gap: expected {index}, found {entry.sequence}",
                )
            if entry.prev_hash != expected_prev:
                return ChainVerification(
                    ok=False,
                    entries_verified=index,
                    broken_at_sequence=entry.sequence,
                    detail="prev_hash does not match the prior entry's entry_hash",
                )
            if _compute_entry_hash(entry) != entry.entry_hash:
                return ChainVerification(
                    ok=False,
                    entries_verified=index,
                    broken_at_sequence=entry.sequence,
                    detail="entry_hash does not match content — record was altered",
                )
            expected_prev = entry.entry_hash
        return ChainVerification(ok=True, entries_verified=len(entries))

    # -- internals ----------------------------------------------------------

    def _lock_for(self, product: str) -> threading.Lock:
        with self._locks_guard:
            lock = self._locks.get(product)
            if lock is None:
                lock = threading.Lock()
                self._locks[product] = lock
            return lock

    def _load_entry(self, name: str) -> AuditLogEntry:
        data = self._seam.read(name)
        if data is None:
            # A name we just listed vanished — a concurrent delete, which the
            # single-replica + append-only contract does not permit.
            raise RuntimeError(f"audit entry disappeared during read: {name}")
        return AuditLogEntry.model_validate_json(data)

    def _all_entries(self, product: str) -> list[AuditLogEntry]:
        names = [
            n for n in self._seam.list_names(_product_prefix(product)) if _is_entry_name(n)
        ]
        entries = [self._load_entry(n) for n in names]
        entries.sort(key=lambda e: e.sequence)
        return entries

    def _load_by_idempotency(self, product: str, key: str) -> AuditLogEntry | None:
        locator = self._seam.read(_idempotency_name(product, key))
        if locator is None:
            return None
        return self._load_entry(locator.decode("utf-8"))

    @staticmethod
    def _query_prefixes(
        product: str, candidate: str | None, tier_id: TierId | None
    ) -> list[str]:
        """The bounded prefix set a filter resolves to — the load-bearing key
        design (MLI-201 EXPLAIN re-frame): a History query is a prefix scan, not
        a list-everything."""
        if tier_id is not None and candidate is not None:
            return [_candidate_prefix(product, tier_id, candidate)]
        if tier_id is not None:
            return [_tier_prefix(product, tier_id)]
        if candidate is not None:
            return [_candidate_prefix(product, t, candidate) for t in _TIER_IDS]
        return [_product_prefix(product)]


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------


def get_audit_log_repository(
    *, clock: Callable[[], datetime] | None = None
) -> AuditLogRepository:
    """Pick the backend from the environment: blob when configured, disk
    otherwise — but fail loud rather than silently use ephemeral disk when the
    durable config is absent in the deployed environment (the MLI-365 footgun).
    """
    account_url = os.environ.get(ACCOUNT_URL_ENV, "").strip()
    container = os.environ.get(CONTAINER_ENV, "").strip()
    if account_url and container:
        return AuditLogRepository(
            AzureBlobSeam(account_url=account_url, container=container), clock=clock
        )
    if os.environ.get(DEPLOY_MARKER_ENV):
        raise AuditLogConfigError(
            "Durable audit-log storage is not configured in the deployed "
            f"environment: set {ACCOUNT_URL_ENV} and {CONTAINER_ENV} on the "
            "Container App. Refusing to fall back to ephemeral local disk for "
            "the audit trail — an authoritative-looking log that vanishes on "
            "restart is worse than none."
        )
    local_dir = os.environ.get(LOCAL_DIR_ENV, _DEFAULT_LOCAL_DIR)
    return AuditLogRepository(DiskBlobSeam(local_dir), clock=clock)
