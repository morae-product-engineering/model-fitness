"""Rubric write endpoint — PUT /api/products/{product}/rubric (MLI-273).

The single path by which a steward updates a product's rubric. Validates
the payload through `Rubric.model_validate` (so every invariant the model
enforces — active-weight sum, draft weight = 0, dimension uniqueness —
holds in the persisted YAML), writes the YAML to disk, bumps the
`version` field, and commits via git. The git commit *is* the audit log:
author = steward identity, timestamp = commit date, message = note +
version delta. There is no separate audit-log table; that's the MLI-273
governance posture (lighter than SQLite, heavier than free-text edits).

Architectural inputs surfaced on MLI-267 by this sub-task:
  * Actor-identity placeholder: trusted `X-Steward-Identity` HTTP header
    with the literal `Unknown Steward <steward@unknown.local>` as the
    fallback when the header is absent. Picked over a single hardcoded
    default so the deployed SSO upstream (when it lands) can populate
    the header without code change.
  * Concurrency: 409 on `expected_version` mismatch (last-write-loses,
    not last-write-wins). The Editor in Slice 4 will re-fetch and merge
    in the UI; the server stays a check-and-commit primitive.

Out of scope (documented in the MLI-273 closing comment):
  * Deployment plumbing: the running API process needs write access to
    the rubric YAML on disk and a configured git committer identity.
  * Pushing to the remote — commit is local; a separate mechanism (CI
    sync or a follow-up sub-task) is responsible for propagation.
  * CLI parity — `mmfp rubric set` is a follow-up.

MLI-194 reconciliation
-----------------------
MLI-194's acceptance overlaps this endpoint, shipped earlier under MLI-273.
MLI-194 reconciled what was here rather than rebuilding it: added the
in-process concurrency lock (below) and confirmed the version-bump rule.
Three points of record for a future reader:

  * Versioning (AC2): the PATCH/MINOR/MAJOR classification AC2 describes is
    intentionally DEFERRED. The `Rubric.version` format is 2-component
    `vMAJOR.MINOR` and cannot carry a PATCH component, and `tier.id` is a
    fixed `Literal["tier_1","tier_2","tier_3"]` so a tier-structure (MAJOR)
    change is unreachable today. Minor-bump-on-any-content-change (see
    `_bump_minor`) is the reconciled behaviour. Revisit when tiers stop
    being a fixed Literal.
  * Durability: the commit is LOCAL to the container's non-durable
    filesystem; `git push` to a remote is deferred (the MLI-190
    durable-evidence thread). A "successful save" persists only until the
    container revision restarts — this is not yet durable persistence.
  * Concurrency (AC4): an in-process per-product `threading.Lock` serialises
    the read->validate->write->commit critical section. It serialises within
    a single replica only — correct for the single-replica R1 deployment.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import threading
from pathlib import Path
from typing import Annotated, Any

import yaml
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

from mmfp.models.rubric import Rubric

logger = logging.getLogger(__name__)

router = APIRouter(tags=["rubric"])

# Product slug pattern: lowercase letters, digits, dashes, underscores. Mirrors
# the directory layout in products/ and forbids path-traversal segments.
_PRODUCT_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

# Version-field pattern matches `Rubric.version` in mmfp/models/rubric.py
# (`r"^v\d+\.\d+$"`). The endpoint auto-bumps the minor; major stays where
# the steward last set it. (Choice noted in MLI-273 closing comment — the
# steward never edits `version` directly, so SemVer-as-monotonic-minor keeps
# the audit trail human-readable without putting another field in the form.)
_VERSION_RE = re.compile(r"^v(\d+)\.(\d+)$")

# Placeholder identity per the actor-identity architectural-input on MLI-267.
# Exposed at module level so tests can pin the exact string.
PLACEHOLDER_STEWARD = "Unknown Steward <steward@unknown.local>"

# Header carrying the steward's identity in the trust-the-edge model. When
# SSO lands the deployment puts a verifying proxy in front of the API and
# populates this header server-side; the FastAPI process never sees the
# user's credentials. Until then, callers (the dev UI, a steward's local
# `curl`) set it themselves. See MLI-267 architectural-input.
_STEWARD_HEADER = "X-Steward-Identity"

# Per-product locks serialise the read->validate->write->commit critical
# section so the `expected_version` handshake (the 409 path) actually holds
# under concurrency (AC4, MLI-194). Correct for the single-replica R1
# deployment: the rubric repo lives on the container's own non-durable
# filesystem, so a single replica is the unit of consistency. This is NOT a
# distributed lock — a multi-replica or shared-volume topology would need the
# durable-store decision tracked on the MLI-190 durable-evidence thread.
# ASSUMES the dev Container App is pinned minReplicas=maxReplicas=1; a future
# scale-out without that pin silently reintroduces the race.
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
            "rubric on disk or the write is rejected with 409"
        ),
    )
    note: str | None = Field(
        default=None,
        description="Optional one-line note recorded in the commit message",
    )


class RubricWriteResponse(BaseModel):
    """Returned on 200."""

    previous_version: str
    new_version: str
    commit_sha: str


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def get_products_dir() -> Path:
    """Where the endpoint reads and writes rubric YAML.

    Defaults to `${MMFP_PRODUCTS_DIR:-products}` — matches the convention
    established by the scoreboard endpoint (MLI-174).
    """
    return Path(os.environ.get("MMFP_PRODUCTS_DIR", "products"))


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _bump_minor(version: str) -> str:
    """`v0.1` → `v0.2`. Raises if the current version doesn't match the
    pattern enforced by the `Rubric` model — but that's unreachable as long
    as the on-disk YAML loads through `Rubric.model_validate` somewhere."""
    match = _VERSION_RE.match(version)
    if not match:
        # Defensive — the file on disk should never reach this state.
        raise ValueError(f"unparseable rubric version on disk: {version!r}")
    major, minor = match.group(1), int(match.group(2))
    return f"v{major}.{minor + 1}"


def _commit_message(note: str | None, old: str, new: str) -> str:
    return f"rubric: {note or 'weight adjustment'} [{old}->{new}]"


def _git(*args: str, cwd: Path, env_overrides: dict[str, str] | None = None) -> str:
    """Run git, capture stdout, raise on non-zero exit.

    Errors surface as RuntimeError with stderr included so the API handler
    can map them to a 500 with useful detail (deployment misconfig usually).
    """
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"git {' '.join(args)} failed (exit {exc.returncode}): {exc.stderr.strip()}"
        ) from exc
    return result.stdout


def _resolve_repo_root(start: Path) -> Path:
    """Find the git repo root containing `start`. Raises if not in a repo."""
    try:
        out = _git("rev-parse", "--show-toplevel", cwd=start)
    except RuntimeError as exc:
        raise RuntimeError(f"products directory {start} is not inside a git repo") from exc
    return Path(out.strip())


def _split_author(identity: str) -> tuple[str, str]:
    """Parse `Name <email>` (or `email`) into (name, email)."""
    identity = identity.strip()
    match = re.match(r"^(?P<name>.*?)\s*<(?P<email>[^>]+)>\s*$", identity)
    if match:
        name = match.group("name").strip() or match.group("email")
        return name, match.group("email").strip()
    # Bare email or freeform string: use it for both fields so git accepts it.
    return identity, identity


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.put(
    "/api/products/{product}/rubric",
    response_model=RubricWriteResponse,
    summary="Steward-write a product's rubric YAML",
)
def put_rubric(
    product: str,
    request: Request,
    payload: RubricWriteRequest,
    products_dir: Annotated[Path, Depends(get_products_dir)],
    x_steward_identity: Annotated[str | None, Header(alias=_STEWARD_HEADER)] = None,
) -> RubricWriteResponse | JSONResponse:
    if not _PRODUCT_SLUG_RE.match(product):
        # Bad slug → either a typo or a traversal attempt. Treat as 404 to
        # match the unknown-product path on a real miss.
        raise HTTPException(status_code=404, detail=f"Unknown product '{product}'")

    rubric_path = products_dir / product / "rubric.yaml"
    if not rubric_path.exists():
        raise HTTPException(status_code=404, detail=f"Unknown product '{product}'")

    # Hold the per-product lock across the whole read-version -> 409-check ->
    # validate -> write -> commit section so the `expected_version` handshake
    # is atomic w.r.t. concurrent writers within this replica (AC4, MLI-194).
    # The `with` block releases the lock on every exit path: the 409 `return`,
    # the 422 `raise`, the 500 `raise`, and the happy fall-through.
    with _lock_for(product):
        # Load current rubric to discover the live version. We deliberately read
        # the YAML rather than trusting `payload.rubric["version"]` — the steward
        # may have edited the version field, and `expected_version` is the
        # authoritative "what I thought was live" handshake.
        current_raw = yaml.safe_load(rubric_path.read_text(encoding="utf-8"))
        current_version = current_raw.get("version")

        if payload.expected_version != current_version:
            # 409 with both versions so the client can show a useful diff dialog.
            # Per the MLI-267 concurrency architectural-input this is last-write-
            # *loses* — the second writer rebases their edit on top of the new
            # current_version themselves. Returned as a top-level body (not under
            # `detail`) because the UI editor needs `current_version` to refetch.
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
            # Surface the structured errors directly. FastAPI's default 422
            # body shape is `{"detail": [{loc, msg, type}, ...]}`; we mirror it
            # so the UI has one error shape to render. `include_context=False`
            # strips Pydantic's raw-exception payloads that aren't JSON-safe.
            raise HTTPException(
                status_code=422,
                detail=exc.errors(include_url=False, include_context=False, include_input=False),
            ) from exc

        # YAML write + git commit. If anything past this point fails, restore
        # the YAML from HEAD so disk and HEAD don't diverge.
        #
        # MLI-365: the whole persistence section is wrapped so a failure becomes
        # a structured HTTPException, not an unhandled raise. The original
        # `_resolve_repo_root` call sat OUTSIDE any try/except, so on the
        # deployed (non-git) container it raised an unhandled RuntimeError ->
        # FastAPI's bare 500 -> which, because it's generated above CORSMiddleware
        # by ServerErrorMiddleware, carries NO Access-Control-Allow-Origin header
        # -> the browser reports the missing CORS header as "Failed to fetch"
        # and never surfaces the real error. An HTTPException, by contrast, is a
        # normal response that flows back down through CORSMiddleware and DOES
        # get CORS headers, so the UI shows a real message. (Durable persistence
        # that removes the .git dependency entirely lands separately in MLI-365.)
        try:
            repo_root = _resolve_repo_root(products_dir)
            relative_path = rubric_path.resolve().relative_to(repo_root)

            rubric_path.write_text(
                yaml.safe_dump(new_rubric_raw, sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )

            try:
                commit_sha = _commit_rubric(
                    repo_root=repo_root,
                    relative_path=relative_path,
                    author=x_steward_identity or PLACEHOLDER_STEWARD,
                    message=_commit_message(payload.note, str(current_version), new_version),
                )
            except RuntimeError:
                # Roll back the YAML so the on-disk state matches HEAD.
                _git("checkout", "--", str(relative_path), cwd=repo_root)
                raise HTTPException(status_code=500, detail="failed to commit rubric change")
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001 — any persistence failure must surface with CORS
            logger.error(
                "rubric.write.persist_failed",
                extra={"product": product, "error_type": type(exc).__name__, "error": str(exc)},
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
            "commit_sha": commit_sha,
            "actor": x_steward_identity or PLACEHOLDER_STEWARD,
            "note": payload.note,
            "request_path": request.url.path,
        },
    )

    return RubricWriteResponse(
        previous_version=str(current_version),
        new_version=new_version,
        commit_sha=commit_sha,
    )


def _commit_rubric(
    *, repo_root: Path, relative_path: Path, author: str, message: str
) -> str:
    """Stage the rubric file, commit with the steward as author, return SHA.

    Committer identity comes from `user.name`/`user.email` configured on
    the running git process — that's a deployment concern (documented in
    the MLI-273 closing comment). Author identity is the steward, set
    per-commit via `--author`.
    """
    name, email = _split_author(author)

    _git("add", str(relative_path), cwd=repo_root)
    _git(
        "commit",
        "-m",
        message,
        f"--author={name} <{email}>",
        cwd=repo_root,
        # Also set committer to the steward so a deployment without
        # global git config doesn't fall over. Author and committer agree
        # in the common case; only diverges when git has its own config.
        env_overrides={
            "GIT_COMMITTER_NAME": name,
            "GIT_COMMITTER_EMAIL": email,
        },
    )
    sha = _git("rev-parse", "HEAD", cwd=repo_root).strip()
    return sha


