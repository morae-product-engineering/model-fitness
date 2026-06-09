"""Tests for the dataset and judge-queue API endpoints (MFP-75).

Endpoints covered:
  GET  /api/products/{product}/datasets/{tier_id}
  POST /api/products/{product}/datasets/{tier_id}/examples
  GET  /api/products/{product}/judge-queue?status={pending|reviewed}
  POST /api/products/{product}/judge-queue/{sample_id}/mark

Uses FastAPI TestClient with dependency_overrides injecting a tmp-dir
products directory — same pattern as test_scoreboard.py and test_rubric_write.py.

Module-level imports of the new module are deferred into test bodies per
CLAUDE.md (pytest collection must succeed even if the module doesn't exist yet).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PRODUCT = "testproduct"


def _setup_product(tmp_path: Path, *, tier_ids: list[str] | None = None) -> Path:
    """Create a minimal product directory under tmp_path/products/.

    Returns the products root (tmp_path / "products").
    """
    products_root = tmp_path / "products"
    product_dir = products_root / _PRODUCT
    datasets_dir = product_dir / "datasets"
    datasets_dir.mkdir(parents=True)

    # Seed JSONL files for each requested tier.
    for tier_id in (tier_ids or []):
        tier_file = datasets_dir / f"{tier_id}.jsonl"
        tier_file.touch()

    return products_root


def _write_examples(products_root: Path, tier_id: str, examples: list[dict]) -> None:
    """Append example dicts as JSONL lines to the tier file."""
    tier_file = products_root / _PRODUCT / "datasets" / f"{tier_id}.jsonl"
    tier_file.parent.mkdir(parents=True, exist_ok=True)
    with tier_file.open("a", encoding="utf-8") as fh:
        for ex in examples:
            fh.write(json.dumps(ex) + "\n")


def _write_judge_samples(products_root: Path, samples: list[dict]) -> None:
    """Write judge sample dicts into the product's judge_samples.jsonl."""
    queue_file = products_root / _PRODUCT / "judge_samples.jsonl"
    queue_file.parent.mkdir(parents=True, exist_ok=True)
    with queue_file.open("w", encoding="utf-8") as fh:
        for s in samples:
            fh.write(json.dumps(s) + "\n")


def _make_client(products_root: Path) -> TestClient:
    """Build a TestClient with the curator router's products_dir overridden."""
    # Deferred import per CLAUDE.md.
    from mmfp.api import curator
    from mmfp.api.main import app

    app.dependency_overrides[curator.get_products_dir] = lambda: products_root
    return TestClient(app, raise_server_exceptions=True)


def _make_example(eid: str = "ex-001") -> dict:
    return {
        "id": eid,
        "input": "Classify: 'This is an NDA'",
        "expected": {"value": "NDA"},
        "tags": ["classification"],
    }


def _make_judge_sample(
    sample_id: str = "abc123",
    *,
    status: str | None = None,
    run_id: str = "run-1",
) -> dict:
    sample = {
        "sample_id": sample_id,
        "run_id": run_id,
        "dimension_id": "synthesis_quality",
        "candidate_id": "c1",
        "candidate_output": "Some output",
        "judge_score": 0.85,
        "judge_reasoning": "Good answer",
        "judge_confidence": "high",
        "created_at": "2026-06-09T10:00:00+00:00",
    }
    if status is not None:
        sample["status"] = status
    return sample


# ---------------------------------------------------------------------------
# Fixture: clear dependency_overrides after every test
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_overrides() -> None:
    yield
    from mmfp.api.main import app

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /api/products/{product}/datasets/{tier_id}
# ---------------------------------------------------------------------------


def test_list_examples_returns_200_with_examples(tmp_path: Path) -> None:
    """Happy path — tier file exists and has examples; returns them."""
    products_root = _setup_product(tmp_path)
    _write_examples(
        products_root,
        "tier_1",
        [_make_example("ex-001"), _make_example("ex-002")],
    )

    client = _make_client(products_root)
    resp = client.get(f"/api/products/{_PRODUCT}/datasets/tier_1")

    assert resp.status_code == 200
    body = resp.json()
    assert body["tier_id"] == "tier_1"
    assert body["product"] == _PRODUCT
    assert len(body["examples"]) == 2
    assert body["examples"][0]["id"] == "ex-001"
    assert body["examples"][1]["id"] == "ex-002"


def test_list_examples_returns_empty_list_for_empty_tier(tmp_path: Path) -> None:
    """Tier file exists but has no examples — returns empty list, not 404."""
    products_root = _setup_product(tmp_path, tier_ids=["tier_2"])
    client = _make_client(products_root)

    resp = client.get(f"/api/products/{_PRODUCT}/datasets/tier_2")

    assert resp.status_code == 200
    body = resp.json()
    assert body["examples"] == []


def test_list_examples_returns_empty_list_for_nonexistent_tier_file(tmp_path: Path) -> None:
    """Tier file doesn't exist — returns 200 with empty list (file may not yet exist)."""
    products_root = _setup_product(tmp_path)
    client = _make_client(products_root)

    resp = client.get(f"/api/products/{_PRODUCT}/datasets/tier_99")

    assert resp.status_code == 200
    assert resp.json()["examples"] == []


def test_list_examples_404_for_unknown_product(tmp_path: Path) -> None:
    """Product directory doesn't exist → 404."""
    products_root = tmp_path / "products"
    products_root.mkdir(parents=True)

    client = _make_client(products_root)
    resp = client.get("/api/products/ghost-product/datasets/tier_1")

    assert resp.status_code == 404
    assert "ghost-product" in resp.json()["detail"]


def test_list_examples_openapi_path_present(tmp_path: Path) -> None:
    """OpenAPI smoke — GET datasets path appears in schema."""
    products_root = _setup_product(tmp_path)
    client = _make_client(products_root)

    resp = client.get("/openapi.json")
    assert resp.status_code == 200

    paths = resp.json()["paths"]
    key = "/api/products/{product}/datasets/{tier_id}"
    assert key in paths
    assert "get" in paths[key]


# ---------------------------------------------------------------------------
# POST /api/products/{product}/datasets/{tier_id}/examples
# ---------------------------------------------------------------------------


def test_add_example_returns_201_and_persists(tmp_path: Path) -> None:
    """Happy path — example added, file written, 201 returned."""
    products_root = _setup_product(tmp_path)
    client = _make_client(products_root)

    payload = _make_example("new-001")
    resp = client.post(
        f"/api/products/{_PRODUCT}/datasets/tier_1/examples",
        json=payload,
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] == "new-001"

    # Verify the file was written.
    tier_file = products_root / _PRODUCT / "datasets" / "tier_1.jsonl"
    assert tier_file.exists()
    lines = [json.loads(ln) for ln in tier_file.read_text().splitlines() if ln.strip()]
    assert len(lines) == 1
    assert lines[0]["id"] == "new-001"
    assert lines[0]["input"] == "Classify: 'This is an NDA'"


def test_add_example_appends_to_existing_file(tmp_path: Path) -> None:
    """Second POST appends; file ends up with two JSONL rows."""
    products_root = _setup_product(tmp_path)
    _write_examples(products_root, "tier_1", [_make_example("ex-existing")])
    client = _make_client(products_root)

    resp = client.post(
        f"/api/products/{_PRODUCT}/datasets/tier_1/examples",
        json=_make_example("ex-new"),
    )
    assert resp.status_code == 201

    tier_file = products_root / _PRODUCT / "datasets" / "tier_1.jsonl"
    lines = [json.loads(ln) for ln in tier_file.read_text().splitlines() if ln.strip()]
    assert len(lines) == 2
    assert {ln["id"] for ln in lines} == {"ex-existing", "ex-new"}


def test_add_example_accepts_structured_input(tmp_path: Path) -> None:
    """input can be a dict (structured payload), not just a string."""
    products_root = _setup_product(tmp_path)
    client = _make_client(products_root)

    payload = {
        "id": "ex-structured",
        "input": {"system": "You are a classifier.", "user": "Classify this."},
        "expected": "NDA",
        "tags": [],
    }
    resp = client.post(
        f"/api/products/{_PRODUCT}/datasets/tier_1/examples",
        json=payload,
    )
    assert resp.status_code == 201

    tier_file = products_root / _PRODUCT / "datasets" / "tier_1.jsonl"
    line = json.loads(tier_file.read_text().splitlines()[0])
    assert isinstance(line["input"], dict)
    assert line["input"]["system"] == "You are a classifier."


def test_add_example_422_missing_required_fields(tmp_path: Path) -> None:
    """Body missing required fields → 422 validation error."""
    products_root = _setup_product(tmp_path)
    client = _make_client(products_root)

    # Missing 'input' and 'expected'
    resp = client.post(
        f"/api/products/{_PRODUCT}/datasets/tier_1/examples",
        json={"id": "bad-example", "tags": []},
    )
    assert resp.status_code == 422


def test_add_example_422_empty_id(tmp_path: Path) -> None:
    """Empty id string → 422 (DatasetExample requires min_length=1)."""
    products_root = _setup_product(tmp_path)
    client = _make_client(products_root)

    resp = client.post(
        f"/api/products/{_PRODUCT}/datasets/tier_1/examples",
        json={"id": "", "input": "test", "expected": "label", "tags": []},
    )
    assert resp.status_code == 422


def test_add_example_404_unknown_product(tmp_path: Path) -> None:
    """Unknown product directory → 404."""
    products_root = tmp_path / "products"
    products_root.mkdir(parents=True)
    client = _make_client(products_root)

    resp = client.post(
        "/api/products/ghost/datasets/tier_1/examples",
        json=_make_example(),
    )
    assert resp.status_code == 404


def test_add_example_openapi_path_present(tmp_path: Path) -> None:
    """OpenAPI smoke — POST examples path appears in schema."""
    products_root = _setup_product(tmp_path)
    client = _make_client(products_root)

    resp = client.get("/openapi.json")
    assert resp.status_code == 200

    paths = resp.json()["paths"]
    key = "/api/products/{product}/datasets/{tier_id}/examples"
    assert key in paths
    assert "post" in paths[key]


# ---------------------------------------------------------------------------
# GET /api/products/{product}/judge-queue?status={pending|reviewed}
# ---------------------------------------------------------------------------


def test_list_judge_queue_returns_all_when_no_status_filter(tmp_path: Path) -> None:
    """No status filter → returns all samples regardless of status."""
    products_root = _setup_product(tmp_path)
    _write_judge_samples(
        products_root,
        [
            _make_judge_sample("s1", status="pending"),
            _make_judge_sample("s2", status="reviewed"),
        ],
    )

    client = _make_client(products_root)
    resp = client.get(f"/api/products/{_PRODUCT}/judge-queue")

    assert resp.status_code == 200
    body = resp.json()
    assert body["product"] == _PRODUCT
    assert len(body["samples"]) == 2


def test_list_judge_queue_filters_by_pending(tmp_path: Path) -> None:
    """status=pending → only pending samples returned."""
    products_root = _setup_product(tmp_path)
    _write_judge_samples(
        products_root,
        [
            _make_judge_sample("s1", status="pending"),
            _make_judge_sample("s2", status="reviewed"),
            # Sample with no status field → treated as pending
            _make_judge_sample("s3"),
        ],
    )

    client = _make_client(products_root)
    resp = client.get(f"/api/products/{_PRODUCT}/judge-queue?status=pending")

    assert resp.status_code == 200
    samples = resp.json()["samples"]
    assert len(samples) == 2
    ids = {s["sample_id"] for s in samples}
    assert ids == {"s1", "s3"}


def test_list_judge_queue_filters_by_reviewed(tmp_path: Path) -> None:
    """status=reviewed → only reviewed samples returned."""
    products_root = _setup_product(tmp_path)
    _write_judge_samples(
        products_root,
        [
            _make_judge_sample("s1", status="pending"),
            _make_judge_sample("s2", status="reviewed"),
        ],
    )

    client = _make_client(products_root)
    resp = client.get(f"/api/products/{_PRODUCT}/judge-queue?status=reviewed")

    assert resp.status_code == 200
    samples = resp.json()["samples"]
    assert len(samples) == 1
    assert samples[0]["sample_id"] == "s2"


def test_list_judge_queue_returns_empty_when_no_file(tmp_path: Path) -> None:
    """No judge_samples.jsonl → 200 with empty samples list."""
    products_root = _setup_product(tmp_path)
    client = _make_client(products_root)

    resp = client.get(f"/api/products/{_PRODUCT}/judge-queue")

    assert resp.status_code == 200
    assert resp.json()["samples"] == []


def test_list_judge_queue_404_unknown_product(tmp_path: Path) -> None:
    """Unknown product → 404."""
    products_root = tmp_path / "products"
    products_root.mkdir(parents=True)
    client = _make_client(products_root)

    resp = client.get("/api/products/ghost/judge-queue")
    assert resp.status_code == 404


def test_list_judge_queue_422_invalid_status_param(tmp_path: Path) -> None:
    """status param with invalid value → 422."""
    products_root = _setup_product(tmp_path)
    client = _make_client(products_root)

    resp = client.get(f"/api/products/{_PRODUCT}/judge-queue?status=invalid")
    assert resp.status_code == 422


def test_list_judge_queue_openapi_path_present(tmp_path: Path) -> None:
    """OpenAPI smoke — GET judge-queue path appears in schema."""
    products_root = _setup_product(tmp_path)
    client = _make_client(products_root)

    resp = client.get("/openapi.json")
    assert resp.status_code == 200

    paths = resp.json()["paths"]
    key = "/api/products/{product}/judge-queue"
    assert key in paths
    assert "get" in paths[key]


# ---------------------------------------------------------------------------
# POST /api/products/{product}/judge-queue/{sample_id}/mark
# ---------------------------------------------------------------------------


def test_mark_sample_agree_sets_status_to_reviewed(tmp_path: Path) -> None:
    """Mark agree → status becomes 'reviewed', decision='agree' stored."""
    products_root = _setup_product(tmp_path)
    _write_judge_samples(products_root, [_make_judge_sample("s1")])
    client = _make_client(products_root)

    resp = client.post(
        f"/api/products/{_PRODUCT}/judge-queue/s1/mark",
        json={"decision": "agree"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["sample_id"] == "s1"
    assert body["status"] == "reviewed"
    assert body["decision"] == "agree"


def test_mark_sample_disagree_sets_status_to_reviewed(tmp_path: Path) -> None:
    """Mark disagree → status becomes 'reviewed', decision='disagree' stored."""
    products_root = _setup_product(tmp_path)
    _write_judge_samples(products_root, [_make_judge_sample("s1")])
    client = _make_client(products_root)

    resp = client.post(
        f"/api/products/{_PRODUCT}/judge-queue/s1/mark",
        json={"decision": "disagree", "note": "Wrong score"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["decision"] == "disagree"
    assert body["note"] == "Wrong score"


def test_mark_persists_and_subsequent_fetch_reflects_change(tmp_path: Path) -> None:
    """After marking, a GET reflects the updated status."""
    products_root = _setup_product(tmp_path)
    _write_judge_samples(products_root, [_make_judge_sample("s1")])
    client = _make_client(products_root)

    # Mark it
    mark_resp = client.post(
        f"/api/products/{_PRODUCT}/judge-queue/s1/mark",
        json={"decision": "agree"},
    )
    assert mark_resp.status_code == 200

    # Fetch reviewed — should now include s1
    get_resp = client.get(f"/api/products/{_PRODUCT}/judge-queue?status=reviewed")
    assert get_resp.status_code == 200
    samples = get_resp.json()["samples"]
    assert len(samples) == 1
    assert samples[0]["sample_id"] == "s1"
    assert samples[0]["decision"] == "agree"
    assert samples[0]["status"] == "reviewed"


def test_mark_pending_queue_empty_after_marking_all(tmp_path: Path) -> None:
    """Marking the only pending sample → pending queue becomes empty."""
    products_root = _setup_product(tmp_path)
    _write_judge_samples(products_root, [_make_judge_sample("s1")])
    client = _make_client(products_root)

    client.post(
        f"/api/products/{_PRODUCT}/judge-queue/s1/mark",
        json={"decision": "agree"},
    )

    get_resp = client.get(f"/api/products/{_PRODUCT}/judge-queue?status=pending")
    assert get_resp.status_code == 200
    assert get_resp.json()["samples"] == []


def test_mark_404_sample_not_found(tmp_path: Path) -> None:
    """sample_id doesn't exist in the queue → 404."""
    products_root = _setup_product(tmp_path)
    _write_judge_samples(products_root, [_make_judge_sample("s1")])
    client = _make_client(products_root)

    resp = client.post(
        f"/api/products/{_PRODUCT}/judge-queue/ghost-sample/mark",
        json={"decision": "agree"},
    )
    assert resp.status_code == 404
    assert "ghost-sample" in resp.json()["detail"]


def test_mark_404_unknown_product(tmp_path: Path) -> None:
    """Unknown product → 404."""
    products_root = tmp_path / "products"
    products_root.mkdir(parents=True)
    client = _make_client(products_root)

    resp = client.post(
        "/api/products/ghost/judge-queue/s1/mark",
        json={"decision": "agree"},
    )
    assert resp.status_code == 404


def test_mark_422_invalid_decision(tmp_path: Path) -> None:
    """Decision value not in allowed set → 422."""
    products_root = _setup_product(tmp_path)
    _write_judge_samples(products_root, [_make_judge_sample("s1")])
    client = _make_client(products_root)

    resp = client.post(
        f"/api/products/{_PRODUCT}/judge-queue/s1/mark",
        json={"decision": "maybe"},
    )
    assert resp.status_code == 422


def test_mark_openapi_path_present(tmp_path: Path) -> None:
    """OpenAPI smoke — POST mark path appears in schema."""
    products_root = _setup_product(tmp_path)
    client = _make_client(products_root)

    resp = client.get("/openapi.json")
    assert resp.status_code == 200

    paths = resp.json()["paths"]
    key = "/api/products/{product}/judge-queue/{sample_id}/mark"
    assert key in paths
    assert "post" in paths[key]
