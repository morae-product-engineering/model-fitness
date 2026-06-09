"""LangSmithSampler — fetches and normalises live-traffic runs (MFP-94).

The concrete LiveSampleSource implementation for Slice 7. Reads scored runs
from a LangSmith project, filters by candidate/tier from run metadata, and
returns normalised LiveSample dicts the SensorPlugin boundary can hand to
detect(). Read-only: no writes to LangSmith.

R1 source: a seeded LangSmith project whose runs mirror the shape real products
will emit once telemetry is wired. The seam (this class) stays unchanged when
live traffic replaces the seed — only the project_name changes.

LiveSample shape (what fetch() returns per matching run):
    {
        "run_id":           str     — LangSmith run ID
        "candidate_id":     str     — from run.extra.metadata["candidate_id"]
        "tier_id":          str     — from run.extra.metadata["tier_id"]
        "dimension_id":     str     — from run.extra.metadata["dimension_id"]
        "normalized_score": Decimal — from run.outputs["normalized_score"], 0–100
    }
This satisfies the contract the MFP-92 acceptance test pins:
    {"dimension_id", "candidate_id", "tier_id", "normalized_score"}

Seed (R1 reproducibility):
    mmfp/sensors/tests/fixtures/langsmith_seed.json documents the expected
    run shape and representative values. To seed a real LangSmith project,
    upload runs matching that fixture to the project named in LANGSMITH_PROJECT
    (or the project_name constructor argument). Tests mock HTTP using this
    fixture directly so they are deterministic without LangSmith credentials.

DECISION flagged for Wayne: seed lives as a committed fixture (deterministic,
no credentials required in CI) rather than a named LangSmith dataset. A named
dataset would more closely mirror production but would require credentials in
CI. Recommend fixture for R1; revisit when production telemetry is wired.

LangSmith credentials:
    LANGSMITH_API_KEY  — required at fetch time. In production, wired from
                         Key Vault secret 'langsmith-api-key' via the
                         Container App env-var mapping.
    LANGSMITH_ENDPOINT — optional; defaults to the EU instance per Morae's
                         data residency policy (ObservabilityConfig default).
                         Override in non-EU environments.
"""

from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

LANGSMITH_API_KEY_ENV = "LANGSMITH_API_KEY"
LANGSMITH_ENDPOINT_ENV = "LANGSMITH_ENDPOINT"
DEFAULT_ENDPOINT = "https://eu.api.smith.langchain.com"
DEFAULT_LIMIT = 20
_DEFAULT_TIMEOUT_S = 30.0

# LiveSample is the normalised dict shape this sampler produces.
# sensor.py defers the concrete definition to MFP-94 (see TODO comment there);
# we own it here. dict[str, Any] rather than TypedDict so downstream code
# (including the MFP-92 acceptance test) can treat it as a plain dict.
LiveSample = dict[str, Any]


class LangSmithSampler:
    """Fetches scored runs from a LangSmith project and normalises them.

    Intended as the LiveSampleSource passed to SensorPlugin.sample() in
    Slice 7 sensors. Inject a client for tests; production code calls
    LangSmithSampler(project_name=...) and owns the httpx.Client lifecycle
    via close().
    """

    def __init__(
        self,
        *,
        project_name: str,
        api_key: str | None = None,
        endpoint: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._project_name = project_name
        self._api_key = api_key
        self._endpoint = (
            endpoint
            or os.environ.get(LANGSMITH_ENDPOINT_ENV)
            or DEFAULT_ENDPOINT
        ).rstrip("/")
        self._client = client or httpx.Client(timeout=_DEFAULT_TIMEOUT_S)
        self._owns_client = client is None

    def fetch(
        self,
        candidate_id: str,
        tier_id: str,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> list[LiveSample]:
        """Fetch and normalise runs for a candidate/tier within a window.

        candidate_id, tier_id: filter runs by these metadata fields.
        start_time, end_time: optional ISO-8601 window. Omit either bound
            for an open-ended query (LangSmith defaults apply).
        limit: max raw runs to retrieve from the API before client-side
            filtering. The returned sample count may be lower if not all
            runs match the candidate/tier filter.

        Returns an empty list when no matching runs exist — never raises on
        an empty window. Raises RuntimeError when credentials are absent,
        httpx.HTTPStatusError on a non-2xx LangSmith response.
        """
        api_key = self._api_key or os.environ.get(LANGSMITH_API_KEY_ENV)
        if not api_key:
            raise RuntimeError(
                f"Missing {LANGSMITH_API_KEY_ENV} in environment. "
                "In production this is wired from Key Vault secret "
                "'langsmith-api-key' via the Container App env-var mapping."
            )

        params: dict[str, str | int] = {
            "session": self._project_name,
            "limit": limit,
        }
        if start_time is not None:
            params["start_time"] = start_time.isoformat()
        if end_time is not None:
            params["end_time"] = end_time.isoformat()

        url = f"{self._endpoint}/api/v1/runs"
        response = self._client.get(url, params=params, headers={"x-api-key": api_key})
        response.raise_for_status()

        body = response.json()
        # LangSmith may return a plain list or {"runs": [...]} depending on
        # API version. Handle both so the sampler is resilient to minor API
        # shape variations between SDK versions.
        raw_runs: list[dict[str, Any]] = (
            body if isinstance(body, list) else body.get("runs", [])
        )

        samples: list[LiveSample] = []
        for run in raw_runs:
            sample = self._normalise(run, candidate_id, tier_id)
            if sample is not None:
                samples.append(sample)
        return samples

    def _normalise(
        self,
        run: dict[str, Any],
        candidate_id: str,
        tier_id: str,
    ) -> LiveSample | None:
        """Normalise one raw run dict to a LiveSample, or return None.

        Returns None when the run is not for the requested candidate/tier,
        or when outputs["normalized_score"] is absent or un-parseable as
        Decimal. Silently drops malformed runs rather than failing the whole
        fetch — a single bad trace should not block the sensor.
        """
        metadata: dict[str, Any] = (run.get("extra") or {}).get("metadata") or {}
        run_candidate = metadata.get("candidate_id") or ""
        run_tier = metadata.get("tier_id") or ""

        if run_candidate != candidate_id or run_tier != tier_id:
            return None

        outputs: dict[str, Any] = run.get("outputs") or {}
        raw_score = outputs.get("normalized_score")
        if raw_score is None:
            return None

        try:
            score = Decimal(str(raw_score))
        except InvalidOperation:
            return None

        return {
            "run_id": run.get("id", ""),
            "candidate_id": run_candidate,
            "tier_id": run_tier,
            "dimension_id": metadata.get("dimension_id", ""),
            "normalized_score": score,
        }

    def close(self) -> None:
        """Close the owned httpx client. No-op if a client was injected."""
        if self._owns_client:
            self._client.close()
