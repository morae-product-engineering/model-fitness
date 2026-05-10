"""Integration tests for AzureFoundryBinding against a live deployment.

Skipped unless `FOUNDRY_ACCOUNT_KEY` and `FOUNDRY_ACCOUNT_ENDPOINT` are
present in the environment. Runs only when the `integration` marker is
selected (CI's standard unit-test job runs `-m "not integration"`).
"""

from __future__ import annotations

import os

import pytest

from mmfp.bindings.foundry.binding import API_KEY_ENV, AzureFoundryBinding
from mmfp.models.candidate import Candidate, CandidateBinding, CandidateFamily

INTEGRATION_ENDPOINT = os.environ.get("FOUNDRY_ACCOUNT_ENDPOINT")
INTEGRATION_DEPLOYMENT = os.environ.get(
    "FOUNDRY_INTEGRATION_DEPLOYMENT", "gpt-4o-mini"
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (os.environ.get(API_KEY_ENV) and INTEGRATION_ENDPOINT),
        reason=(
            "set FOUNDRY_ACCOUNT_KEY and FOUNDRY_ACCOUNT_ENDPOINT to run"
        ),
    ),
]


def test_invokes_real_deployment():
    candidate = Candidate(
        id="integration-test",
        display_name=INTEGRATION_DEPLOYMENT,
        family=CandidateFamily.CHAT,
        max_tokens=64,
        binding=CandidateBinding(
            provider="azure_foundry",
            endpoint=INTEGRATION_ENDPOINT,
            deployment=INTEGRATION_DEPLOYMENT,
            key_vault_secret_name="foundry-account-key",
        ),
    )
    binding = AzureFoundryBinding()
    try:
        response = binding.invoke(candidate, "Reply with exactly: pong", 200)
    finally:
        binding.close()
    assert response.content
    assert response.usage.prompt_tokens > 0
    assert response.latency_ms > 0
