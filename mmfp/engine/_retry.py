"""Engine-level retry helper for transient binding errors.

Policy (per MLI-171 closing comment):
  * 429 (rate-limit): exponential backoff, retry up to `max_attempts`
  * 5xx: exponential backoff, retry up to `max_attempts`
  * Other 4xx: no retry — caller's request is wrong, retrying won't fix it
  * Network errors (timeout / connection): retry up to `max_attempts`
  * After exhaustion: re-raise so the caller can mark the cell errored

Hand-rolled rather than pulling `tenacity` — the surface is small and the
policy is bespoke (only some HTTP status codes are retriable). The `sleep`
parameter is the test seam: unit tests inject a no-op so they don't actually
sleep.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

import httpx

from mmfp.models.binding_response import BindingResponse
from mmfp.models.candidate import Candidate
from mmfp.plugins.binding import BindingPlugin

T = TypeVar("T")


def _is_retriable_status(status: int) -> bool:
    return status == 429 or 500 <= status < 600


def invoke_with_retry(
    binding: BindingPlugin,
    candidate: Candidate,
    prompt: str,
    max_tokens: int,
    *,
    max_attempts: int = 3,
    base_delay_s: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> BindingResponse:
    """Invoke `binding` with exp-backoff retry on transient failures.

    Re-raises the last exception when retries are exhausted; the caller
    (the matrix engine) is responsible for converting that into an errored
    MatrixRunResult — this helper does not swallow.
    """
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return binding.invoke(candidate, prompt, max_tokens)
        except httpx.HTTPStatusError as e:
            if not _is_retriable_status(e.response.status_code):
                raise
            last_exc = e
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            last_exc = e
        if attempt < max_attempts:
            sleep(base_delay_s * (2 ** (attempt - 1)))
    assert last_exc is not None
    raise last_exc
