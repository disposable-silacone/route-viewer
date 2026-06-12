from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


DEFAULT_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
DEFAULT_TIMEOUT_S = 120
RETRYABLE_HTTP_CODES = {429, 502, 503, 504}


def overpass_url() -> str:
    return os.getenv("OVERPASS_URL", DEFAULT_OVERPASS_URL).rstrip("/")


def _max_retries() -> int:
    return max(1, int(os.getenv("OVERPASS_MAX_RETRIES", "4")))


def _retry_backoff_s() -> float:
    return max(1.0, float(os.getenv("OVERPASS_RETRY_BACKOFF_S", "5")))


def build_highway_query(
    *,
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> str:
    """Fetch full highway ways intersecting bbox plus all referenced nodes."""
    south, west, north, east = min_lat, min_lon, max_lat, max_lon
    return f"""
[out:json][timeout:{timeout_s}];
(
  way["highway"]({south},{west},{north},{east});
);
(._;>;);
out body;
""".strip()


def _overpass_http_message(code: int, detail: str) -> str:
    if code == 429:
        return "Overpass HTTP 429: rate limited (too many requests)"
    if code in (502, 503, 504):
        return f"Overpass HTTP {code}: server busy or unavailable"
    snippet = detail.strip()
    if snippet.startswith("<?xml") or snippet.startswith("<!DOCTYPE"):
        return f"Overpass HTTP {code}"
    return f"Overpass HTTP {code}: {snippet[:300]}"


def _fetch_overpass_once(
    query: str,
    *,
    timeout_s: int,
) -> dict[str, Any]:
    payload = urllib.parse.urlencode({"data": query}).encode("utf-8")
    req = urllib.request.Request(
        overpass_url(),
        data=payload,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": "RouteViewer/1.0 (FinishLine catalog build)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s + 30) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(_overpass_http_message(exc.code, detail)) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Overpass request failed: {exc}") from exc

    data = json.loads(body)
    if "elements" not in data:
        raise RuntimeError(f"Unexpected Overpass response: {body[:500]}")
    return data


def fetch_overpass_bbox(
    *,
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> dict[str, Any]:
    query = build_highway_query(
        min_lat=min_lat,
        min_lon=min_lon,
        max_lat=max_lat,
        max_lon=max_lon,
        timeout_s=timeout_s,
    )
    last_error: RuntimeError | None = None
    for attempt in range(_max_retries()):
        try:
            return _fetch_overpass_once(query, timeout_s=timeout_s)
        except RuntimeError as exc:
            last_error = exc
            msg = str(exc)
            retryable = any(f"HTTP {code}" in msg for code in RETRYABLE_HTTP_CODES)
            if not retryable or attempt >= _max_retries() - 1:
                raise
            time.sleep(_retry_backoff_s() * (2**attempt))
    if last_error:
        raise last_error
    raise RuntimeError("Overpass request failed")
