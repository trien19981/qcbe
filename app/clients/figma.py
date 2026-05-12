"""Figma REST API client — thin async wrapper."""

from __future__ import annotations

import asyncio
import re
import time
import threading
from urllib.parse import unquote, urlparse, parse_qs
from functools import partial

import requests

_BASE = "https://api.figma.com/v1"
_TIMEOUT = 60
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}
_MAX_RETRIES = 5

# Simple TTL cache cho list_file_components — cùng file_key thì dùng chung
_components_cache: dict[str, tuple[list, float]] = {}
_components_cache_ttl = 300.0  # 5 phút
_components_lock = threading.Lock()


def _get(url: str, headers: dict, params: dict | None = None) -> requests.Response:
    """GET với retry tự động khi gặp 429, tôn trọng Retry-After header."""
    for attempt in range(_MAX_RETRIES):
        resp = requests.get(url, headers=headers, params=params, timeout=_TIMEOUT)
        if resp.status_code != 429:
            return resp
        # Figma rate limit window là 60s — default wait tăng dần
        retry_after = float(resp.headers.get("Retry-After", 60 + 30 * attempt))
        retry_after = min(retry_after, 120)
        time.sleep(retry_after)
    return resp  # trả về response 429 cuối nếu vẫn bị limit


# ---------------------------------------------------------------------------
# URL parser helpers
# ---------------------------------------------------------------------------

def parse_figma_url(url: str) -> tuple[str, str]:
    """Parse a Figma share URL → (file_key, node_id).

    Supports formats:
      https://www.figma.com/file/{key}/Title?node-id=123:456
      https://www.figma.com/design/{key}/Title?node-id=123-456
    """
    parsed = urlparse(url)
    # file_key is the segment after /file/ or /design/
    m = re.search(r"/(?:file|design)/([A-Za-z0-9_-]+)", parsed.path)
    if not m:
        raise ValueError(f"Cannot extract Figma file key from URL: {url}")
    file_key = m.group(1)

    qs = parse_qs(parsed.query)
    node_id_raw = qs.get("node-id", [None])[0]
    if not node_id_raw:
        raise ValueError(f"No node-id query param in Figma URL: {url}")

    # URL may encode colon as '-' in newer share links
    node_id = unquote(node_id_raw).replace("-", ":", 1)
    return file_key, node_id


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------

def _fetch_node_sync(file_key: str, node_id: str, token: str) -> dict:
    headers = {**_HEADERS, "X-Figma-Token": token}
    resp = _get(f"{_BASE}/files/{file_key}/nodes", headers, {"ids": node_id, "depth": 5})
    if not resp.ok:
        raise RuntimeError(f"Figma API {resp.status_code} for {resp.url}\nBody: {resp.text[:500]}")
    data = resp.json()
    nodes = data.get("nodes", {})
    key = node_id if node_id in nodes else node_id.replace(":", "-")
    if key not in nodes:
        raise ValueError(f"Node '{node_id}' not found in Figma response. Available: {list(nodes.keys())}")
    node_data = nodes[key]
    if node_data is None:
        raise ValueError(f"Node '{node_id}' exists but has no content (null) — frame có thể bị ẩn hoặc trống.")
    return node_data["document"]


async def fetch_node(file_key: str, node_id: str, token: str) -> dict:
    return await asyncio.to_thread(_fetch_node_sync, file_key, node_id, token)


def _list_top_frames_sync(file_key: str, token: str) -> list[dict]:
    headers = {**_HEADERS, "X-Figma-Token": token}
    resp = _get(f"{_BASE}/files/{file_key}", headers, {"depth": 2})
    if not resp.ok:
        raise RuntimeError(f"Figma API {resp.status_code} for {resp.url}\nBody: {resp.text[:500]}")
    data = resp.json()
    frames = []
    for page in data.get("document", {}).get("children", []):
        for child in page.get("children", []):
            if child.get("type") in ("FRAME", "COMPONENT", "COMPONENT_SET"):
                frames.append({
                    "page": page.get("name", ""),
                    "name": child.get("name", ""),
                    "node_id": child.get("id", ""),
                })
    return frames


async def list_top_frames(file_key: str, token: str) -> list[dict]:
    return await asyncio.to_thread(_list_top_frames_sync, file_key, token)


def _list_file_components_sync(file_key: str, token: str) -> list[dict]:
    cache_key = f"{file_key}:{token[:8]}"
    with _components_lock:
        cached = _components_cache.get(cache_key)
        if cached and (time.time() - cached[1]) < _components_cache_ttl:
            return cached[0]

    headers = {**_HEADERS, "X-Figma-Token": token}
    resp = _get(f"{_BASE}/files/{file_key}/components", headers)
    if not resp.ok:
        raise RuntimeError(f"Figma API {resp.status_code} for {resp.url}\nBody: {resp.text[:500]}")
    data = resp.json()
    result = (data.get("meta", {}) or {}).get("components", []) or []

    with _components_lock:
        _components_cache[cache_key] = (result, time.time())
    return result


async def list_file_components(file_key: str, token: str) -> list[dict]:
    """Return all components in a file (for mapping instance -> component name)."""
    return await asyncio.to_thread(_list_file_components_sync, file_key, token)


def _export_node_images_sync(
    *,
    file_key: str,
    node_ids: list[str],
    token: str,
    format: str,
    scale: float | None,
) -> dict[str, str]:
    headers = {**_HEADERS, "X-Figma-Token": token}
    params: dict[str, str] = {
        "ids": ",".join(node_ids),
        "format": format,
    }
    if scale is not None:
        params["scale"] = str(scale)

    resp = _get(f"{_BASE}/images/{file_key}", headers, params)
    if not resp.ok:
        raise RuntimeError(f"Figma API {resp.status_code} for {resp.url}\nBody: {resp.text[:500]}")
    data = resp.json()
    images = data.get("images", {}) or {}

    out: dict[str, str] = {}
    for nid in node_ids:
        if nid in images and images[nid]:
            out[nid] = images[nid]
            continue
        alt = nid.replace(":", "-")
        if alt in images and images[alt]:
            out[nid] = images[alt]
    return out


async def export_node_images(
    *,
    file_key: str,
    node_ids: list[str],
    token: str,
    format: str = "png",
    scale: float | None = None,
) -> dict[str, str]:
    """Export one or more nodes as images and return a node_id -> image_url map."""
    if not node_ids:
        return {}
    return await asyncio.to_thread(
        partial(
            _export_node_images_sync,
            file_key=file_key,
            node_ids=node_ids,
            token=token,
            format=format,
            scale=scale,
        )
    )
