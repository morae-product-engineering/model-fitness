#!/usr/bin/env python3
"""Sync architecture diagram SVGs to a Confluence page.

Phase 2 of the architecture documentation pipeline. Phase 1 renders
docs/architecture/workspace.dsl to SVG and commits the results back to main.
This script picks up those committed SVGs and pushes them to Confluence as page
attachments. The page body is edited ONCE (on first run) to add the embed
structure; on subsequent runs only the attachment data rotates.

Why REST and not the Atlassian MCP server: MCP is designed for interactive
agent use. CI does not need an agent layer over a documented REST API.

Why mix v1 and v2: the v2 API is the long-term direction but v1 is currently
better for attachment upload + storage-format body editing. Each call below
picks the API version that handles its operation cleanly. This is an
intentional, documented trade-off.

Body-edit-once contract: the first run sets a Confluence content property
(`architecture_diagrams_managed`) on the page after editing the body. Future
runs see the property and skip body edits entirely, even if a human deletes
the embed headings. The marker lives on the page's metadata rather than in
the body itself because HTML comments do not survive Confluence's storage
normalisation pass — content properties are designed for CI metadata and are
invisible to editors. To restore the embed structure, delete the property
via the REST API and re-trigger the workflow.

Required environment variables:
    CONFLUENCE_API_TOKEN  - API token (secret)
    CONFLUENCE_USER_EMAIL - Atlassian account email tied to the token
    CONFLUENCE_BASE_URL   - e.g. https://morae.atlassian.net
    CONFLUENCE_PAGE_ID    - target page id (e.g. 218530029)

Optional:
    GITHUB_STEP_SUMMARY   - path to a markdown file appended for the run
                            summary in GitHub Actions. Ignored if unset.
"""

from __future__ import annotations

import base64
import datetime
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

# The three rendered views we expect Phase 1 to have produced. Names match
# PlantUML's filename convention `structurizr-<ViewKey>.svg`. Renaming a view
# in workspace.dsl orphans its previous attachment until Confluence is cleaned
# up by hand — accepted trade-off.
EXPECTED_SVGS: tuple[str, ...] = (
    "structurizr-SystemContext.svg",
    "structurizr-Containers.svg",
    "structurizr-MatrixRun.svg",
)

SVG_DIR = Path("docs/architecture/exports/svg")

# Content-property key marking the page body as managed by this script. The
# property is invisible to editors and survives Confluence's storage
# normalisation, which an in-body HTML comment does not. Its mere existence is
# the body-edit-once signal; the value's timestamp is for human inspection.
MANAGED_PROPERTY_KEY = "architecture_diagrams_managed"

# Storage-format snippet inserted on first run. Uses Confluence's `<ac:image>`
# + `<ri:attachment>` macros to embed the page-attached SVGs by filename.
EMBED_BLOCK = (
    "<h2>Architecture diagrams</h2>"
    "<p>Source of truth: <code>docs/architecture/workspace.dsl</code> in the "
    "model-fitness repo. Diagrams below are auto-rendered and synced from CI.</p>"
    "<h3>System context</h3>"
    '<ac:image><ri:attachment ri:filename="structurizr-SystemContext.svg" /></ac:image>'
    "<h3>Containers</h3>"
    '<ac:image><ri:attachment ri:filename="structurizr-Containers.svg" /></ac:image>'
    "<h3>Matrix run (dynamic)</h3>"
    '<ac:image><ri:attachment ri:filename="structurizr-MatrixRun.svg" /></ac:image>'
)

# Heading text we replace on first run. Match is case-insensitive against
# the stripped text content of any <h2>, so attributes like
# `<h2 id="System-context">` or whitespace variations don't trip the swap.
HEADING_TEXT = "system context"


@dataclass(frozen=True)
class Config:
    """Runtime configuration drawn from environment. Validated at construction."""

    base_url: str
    page_id: str
    user_email: str
    api_token: str

    @classmethod
    def from_env(cls) -> "Config":
        missing: list[str] = []
        # Order matches the workflow's check; keep them aligned so error
        # messages from script and workflow are easy to reconcile.
        env = {
            "CONFLUENCE_BASE_URL": os.environ.get("CONFLUENCE_BASE_URL", "").strip(),
            "CONFLUENCE_PAGE_ID": os.environ.get("CONFLUENCE_PAGE_ID", "").strip(),
            "CONFLUENCE_USER_EMAIL": os.environ.get("CONFLUENCE_USER_EMAIL", "").strip(),
            "CONFLUENCE_API_TOKEN": os.environ.get("CONFLUENCE_API_TOKEN", "").strip(),
        }
        for key, value in env.items():
            if not value:
                missing.append(key)
        if missing:
            raise SystemExit(
                "Missing or empty required environment variables: "
                + ", ".join(missing)
                + ". Set them as repo secrets/variables and re-run."
            )
        # Strip trailing slash so we can concatenate paths without doubling up.
        return cls(
            base_url=env["CONFLUENCE_BASE_URL"].rstrip("/"),
            page_id=env["CONFLUENCE_PAGE_ID"],
            user_email=env["CONFLUENCE_USER_EMAIL"],
            api_token=env["CONFLUENCE_API_TOKEN"],
        )

    def auth_header(self) -> str:
        """Confluence Cloud uses Basic auth with email:token."""
        raw = f"{self.user_email}:{self.api_token}".encode("utf-8")
        return "Basic " + base64.b64encode(raw).decode("ascii")


class ConfluenceClient:
    """Thin wrapper around requests for the small surface area we need.

    Retries once on transient 5xx with short exponential backoff. Auth errors
    (401/403) are not retried — they need human attention, not patience.
    """

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.session = requests.Session()
        # Default headers used on JSON requests. Multipart uploads override
        # Content-Type per call (and add the no-check CSRF header).
        self.session.headers.update(
            {
                "Authorization": cfg.auth_header(),
                "Accept": "application/json",
            }
        )

    def _request(
        self,
        method: str,
        url: str,
        *,
        retry_on_5xx: bool = True,
        **kwargs: Any,
    ) -> requests.Response:
        # One retry at 1.5s for transient 5xx. Anything more aggressive risks
        # hammering Confluence on a real outage.
        attempts = 0
        last_exc: Exception | None = None
        while attempts < 2:
            attempts += 1
            try:
                response = self.session.request(method, url, timeout=30, **kwargs)
            except requests.RequestException as exc:
                last_exc = exc
                if attempts >= 2:
                    raise
                time.sleep(1.5)
                continue
            if 500 <= response.status_code < 600 and retry_on_5xx and attempts < 2:
                time.sleep(1.5)
                continue
            return response
        # Unreachable: loop returns or raises before falling through.
        raise RuntimeError(f"Request failed: {last_exc}")

    @staticmethod
    def _raise_for_status(response: requests.Response, action: str) -> None:
        if response.ok:
            return
        body = response.text
        # Truncate verbose HTML error pages so the log stays useful.
        if len(body) > 800:
            body = body[:800] + "...[truncated]"
        if response.status_code in (401, 403):
            raise SystemExit(
                f"{action} failed with HTTP {response.status_code}. The API "
                "token may lack edit permission on the target page, or the "
                "email/token pair may be invalid. Body: " + body
            )
        if response.status_code == 409:
            raise SystemExit(
                f"{action} failed with HTTP 409 (version conflict). The page "
                "was edited between our metadata read and our update. The "
                "next sync will pick up the new version. Body: " + body
            )
        raise SystemExit(
            f"{action} failed with HTTP {response.status_code}. Body: {body}"
        )

    def get_page_v2(self) -> dict[str, Any]:
        """v2 page metadata is the cleanest source for current version number."""
        url = f"{self.cfg.base_url}/wiki/api/v2/pages/{self.cfg.page_id}"
        response = self._request("GET", url)
        self._raise_for_status(response, "Fetch page metadata (v2)")
        return response.json()

    def get_page_storage_v1(self) -> dict[str, Any]:
        """v1 page expand=body.storage is what we need to edit body in storage XML."""
        url = (
            f"{self.cfg.base_url}/wiki/rest/api/content/{self.cfg.page_id}"
            "?expand=body.storage,version"
        )
        response = self._request("GET", url)
        self._raise_for_status(response, "Fetch page body (v1)")
        return response.json()

    def list_attachments_v1(self) -> list[dict[str, Any]]:
        """v1 attachments listing is more mature than v2's equivalent today."""
        url = (
            f"{self.cfg.base_url}/wiki/rest/api/content/{self.cfg.page_id}"
            "/child/attachment?limit=200"
        )
        response = self._request("GET", url)
        self._raise_for_status(response, "List attachments (v1)")
        return response.json().get("results", [])

    def upload_attachment_create_v1(self, svg_path: Path) -> dict[str, Any]:
        url = (
            f"{self.cfg.base_url}/wiki/rest/api/content/{self.cfg.page_id}"
            "/child/attachment"
        )
        return self._post_attachment(url, svg_path, action="Create attachment")

    def upload_attachment_update_v1(
        self, attachment_id: str, svg_path: Path
    ) -> dict[str, Any]:
        url = (
            f"{self.cfg.base_url}/wiki/rest/api/content/{self.cfg.page_id}"
            f"/child/attachment/{attachment_id}/data"
        )
        return self._post_attachment(url, svg_path, action="Update attachment data")

    def _post_attachment(
        self, url: str, svg_path: Path, *, action: str
    ) -> dict[str, Any]:
        # X-Atlassian-Token: no-check is the documented CSRF bypass for
        # attachment uploads. Without it Confluence Cloud rejects the POST.
        # minorEdit=true suppresses watcher email notifications.
        headers = {
            "X-Atlassian-Token": "no-check",
            # Drop the session's default Accept; multipart endpoints do not
            # require it and some setups echo unexpected JSON-Accept errors.
        }
        with svg_path.open("rb") as fh:
            files = {
                "file": (svg_path.name, fh, "image/svg+xml"),
                "minorEdit": (None, "true"),
            }
            response = self._request(
                "POST", url, headers=headers, files=files, retry_on_5xx=True
            )
        self._raise_for_status(response, action)
        return response.json()

    def update_page_body_v1(
        self,
        *,
        title: str,
        new_storage_value: str,
        next_version: int,
    ) -> None:
        url = f"{self.cfg.base_url}/wiki/rest/api/content/{self.cfg.page_id}"
        payload = {
            "id": self.cfg.page_id,
            "type": "page",
            "title": title,
            "version": {"number": next_version},
            "body": {
                "storage": {
                    "value": new_storage_value,
                    "representation": "storage",
                }
            },
        }
        response = self._request(
            "PUT",
            url,
            headers={"Content-Type": "application/json"},
            json=payload,
        )
        self._raise_for_status(response, "Update page body (v1)")

    def get_managed_property(self) -> bool:
        """True if the body-managed property is present and managed==True.

        404 is the explicit "absent" signal (first-run path). Any other
        non-2xx response is unexpected and surfaces via _raise_for_status.
        """
        url = (
            f"{self.cfg.base_url}/wiki/rest/api/content/{self.cfg.page_id}"
            f"/property/{MANAGED_PROPERTY_KEY}"
        )
        response = self._request("GET", url)
        if response.status_code == 404:
            return False
        self._raise_for_status(response, "Fetch managed content property")
        value = response.json().get("value", {})
        return bool(value.get("managed", False))

    def create_managed_property(self) -> None:
        """POST the body-managed content property. Only called on first run."""
        url = (
            f"{self.cfg.base_url}/wiki/rest/api/content/{self.cfg.page_id}"
            "/property"
        )
        payload = {
            "key": MANAGED_PROPERTY_KEY,
            "value": {
                "managed": True,
                "first_synced_at": datetime.datetime.now(datetime.UTC).isoformat(),
            },
        }
        response = self._request(
            "POST",
            url,
            headers={"Content-Type": "application/json"},
            json=payload,
        )
        self._raise_for_status(response, "Create managed content property")

    def verify_managed_property(self) -> None:
        """Re-fetch the property and assert managed==True. Raises on failure."""
        url = (
            f"{self.cfg.base_url}/wiki/rest/api/content/{self.cfg.page_id}"
            f"/property/{MANAGED_PROPERTY_KEY}"
        )
        response = self._request("GET", url)
        self._raise_for_status(response, "Verify managed content property")
        value = response.json().get("value", {})
        if not value.get("managed", False):
            raise SystemExit(
                "Body-edit-once contract violation: managed content property "
                f"'{MANAGED_PROPERTY_KEY}' was created but its readback value "
                f"is unexpected: {value!r}. Inspect the page's content "
                "properties via the REST API before re-running."
            )


def verify_svg_files() -> list[Path]:
    """Resolve and return the three expected SVG paths, or raise."""
    paths: list[Path] = []
    missing: list[str] = []
    for name in EXPECTED_SVGS:
        path = SVG_DIR / name
        if not path.is_file():
            missing.append(str(path))
        else:
            paths.append(path)
    if missing:
        raise SystemExit(
            "Expected rendered SVGs not found: "
            + ", ".join(missing)
            + ". Phase 1 (docs-architecture workflow) should produce these."
        )
    return paths


def insert_embed_block(body: str) -> tuple[str, bool]:
    """Insert the embed block in place of the System context heading.

    Parses the body with BeautifulSoup's html.parser and finds an <h2> whose
    stripped text equals "System context" (case-insensitive). When found, the
    h2 AND every following sibling up to (but not including) the next <h2>
    are removed, and the embed block is inserted at that position. If no such
    heading exists, the embed block is appended and the caller is expected to
    log a warning so a surprising layout doesn't pass silently.

    Why html.parser and not lxml-xml: Confluence's storage-format fragment
    returned by the API does not declare the `ac:` and `ri:` namespaces, so
    a strict XML parser refuses it without a synthetic-root wrap/unwrap
    dance. html.parser treats `ac:image` and `ri:attachment` as opaque tag
    names and round-trips them losslessly — that's all we need here. The
    only cosmetic side effect is that self-closing tags like
    `<ri:attachment ... />` are emitted as `<ri:attachment ...></ri:attachment>`,
    which Confluence accepts equivalently.

    Returns (new_body, replaced_in_place).
    """
    soup = BeautifulSoup(body, "html.parser")
    target = None
    for h2 in soup.find_all("h2"):
        if h2.get_text(strip=True).casefold() == HEADING_TEXT:
            target = h2
            break
    if target is None:
        return body + EMBED_BLOCK, False

    # Collect every sibling after the target heading up to (but not
    # including) the next h2. Snapshot first to avoid mutating during walk.
    to_remove: list[Any] = []
    sib = target.next_sibling
    while sib is not None:
        nxt = sib.next_sibling
        if getattr(sib, "name", None) == "h2":
            break
        to_remove.append(sib)
        sib = nxt

    # Parse the embed block as a fragment in the same parser so it slots in
    # as native nodes rather than a string blob.
    embed_fragment = BeautifulSoup(EMBED_BLOCK, "html.parser")
    for node in list(embed_fragment.children):
        target.insert_before(node)
    for node in to_remove:
        node.extract()
    target.extract()

    # formatter=None keeps the rest of the body byte-stable: no entity
    # munging, no pretty-printing of unrelated nodes.
    return soup.encode(formatter=None).decode("utf-8"), True


def write_step_summary(lines: list[str]) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    try:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    except OSError as exc:
        # Don't fail the job over a summary write — just log.
        print(f"warning: could not write step summary: {exc}", file=sys.stderr)


def main() -> int:
    cfg = Config.from_env()
    svgs = verify_svg_files()
    client = ConfluenceClient(cfg)

    print(f"Fetching page metadata for id={cfg.page_id}")
    page_v2 = client.get_page_v2()
    title = page_v2.get("title", "Architecture")

    # The managed-property check is the body-edit-once gate. Read it before
    # any body fetch so we don't pay for the body when we're going to skip.
    managed = client.get_managed_property()
    print(f"Managed content property '{MANAGED_PROPERTY_KEY}' present: {managed}")

    # Build a lookup of existing attachment titles -> id, so we know whether
    # to create or update each SVG.
    existing = {a["title"]: a["id"] for a in client.list_attachments_v1()}
    print(f"Existing attachments on page: {len(existing)}")

    summary_attachment_lines: list[str] = []
    for svg_path in svgs:
        if svg_path.name in existing:
            attachment_id = existing[svg_path.name]
            print(f"Updating attachment data for {svg_path.name} (id={attachment_id})")
            client.upload_attachment_update_v1(attachment_id, svg_path)
            summary_attachment_lines.append(f"- updated `{svg_path.name}`")
        else:
            print(f"Creating attachment {svg_path.name}")
            client.upload_attachment_create_v1(svg_path)
            summary_attachment_lines.append(f"- created `{svg_path.name}`")

    # Body-edit-once contract: only edit if the managed property is absent.
    body_action: str
    if managed:
        body_action = f"skipped (property `{MANAGED_PROPERTY_KEY}` present)"
        print(
            "Managed property present; skipping body edit per body-edit-once contract."
        )
    else:
        # v1 body fetch — needed for both the body content and the page
        # version (the v1 PUT requires version+1 atomically with the body).
        page_v1 = client.get_page_storage_v1()
        current_body = (
            page_v1.get("body", {}).get("storage", {}).get("value", "") or ""
        )
        current_version = int(page_v1.get("version", {}).get("number", 0))
        print(
            f"Page version (v1): {current_version}; body length: {len(current_body)}"
        )

        new_body, replaced_in_place = insert_embed_block(current_body)
        if not replaced_in_place:
            print(
                "warning: 'System context' heading not found in current body; "
                "appending embed block to end of body.",
                file=sys.stderr,
            )
        client.update_page_body_v1(
            title=title,
            new_storage_value=new_body,
            next_version=current_version + 1,
        )
        body_action = (
            "edited (replaced System context heading)"
            if replaced_in_place
            else "edited (appended; heading not found)"
        )
        print(f"Body updated to version {current_version + 1}.")

        # Create the body-managed content property after the body PUT
        # succeeds. The property's existence is the body-edit-once signal
        # for subsequent runs.
        client.create_managed_property()
        print(f"Created managed content property '{MANAGED_PROPERTY_KEY}'.")

        # Property-survival check. The fitness-function pattern from the
        # previous in-body sentinel design, applied to the new mechanism:
        # if the property cannot be read back as managed==True immediately
        # after creation, the contract is broken and the next run will
        # re-edit the body. Fail loudly so a human catches it on first run.
        client.verify_managed_property()
        print("Managed property verified present on re-fetch.")

    page_url = f"{cfg.base_url}/wiki/spaces/MLI/pages/{cfg.page_id}"
    if managed:
        body_summary_line = (
            f"- Body: unchanged (property `{MANAGED_PROPERTY_KEY}` present); "
            "attachments refreshed."
        )
    else:
        body_summary_line = (
            f"- Body: restructured + content property `{MANAGED_PROPERTY_KEY}` "
            f"created ({body_action})."
        )
    write_step_summary(
        [
            "## Confluence sync",
            f"- Page: [{title}]({page_url})",
            body_summary_line,
            "- Attachments:",
            *[f"  {line[2:]}" for line in summary_attachment_lines],
        ]
    )
    print("Confluence sync complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
