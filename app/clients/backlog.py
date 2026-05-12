"""Nulab Backlog REST API client — thin async wrapper."""

from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx

_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=5.0)


# ---------------------------------------------------------------------------
# URL parser helpers
# ---------------------------------------------------------------------------

def parse_backlog_url(url: str) -> tuple[str, str]:
    """Parse a Backlog issue URL → (space_url, issue_key).

    Supports: https://{space}.backlog.com/view/{PROJECT}-{number}
              https://{space}.backlog.jp/view/{PROJECT}-{number}
    """
    parsed = urlparse(url)
    m = re.search(r"/view/([A-Z0-9_]+-\d+)", parsed.path, re.IGNORECASE)
    if not m:
        raise ValueError(f"Cannot extract issue key from Backlog URL: {url}")
    issue_key = m.group(1).upper()
    space_url = f"{parsed.scheme}://{parsed.netloc}"
    return space_url, issue_key


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------

async def fetch_issue(space_url: str, api_key: str, issue_key: str) -> dict:
    """Fetch a single Backlog issue by key (e.g. 'PROJ-42')."""
    url = f"{space_url.rstrip('/')}/api/v2/issues/{issue_key}"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(url, params={"apiKey": api_key})
        resp.raise_for_status()
    return resp.json()


async def fetch_issue_comments(space_url: str, api_key: str, issue_key: str) -> list[dict]:
    """Fetch all comments for a Backlog issue."""
    url = f"{space_url.rstrip('/')}/api/v2/issues/{issue_key}/comments"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(url, params={"apiKey": api_key, "count": 100})
        resp.raise_for_status()
    return resp.json()
