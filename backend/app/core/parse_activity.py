from __future__ import annotations

import gzip
from pathlib import Path

from app.core.parse_fit import parse_fit_bytes, parse_fit_file
from app.core.parse_gpx import parse_gpx_file, parse_gpx_text
from app.core.parse_gpx import ParsedTrack
from app.core.parse_tcx import parse_tcx_file, parse_tcx_text


def parse_activity(path: Path) -> tuple[ParsedTrack | None, str]:
    """Parse a GPX/FIT/TCX file, including gzip-compressed variants."""
    name = path.name.lower()
    if name.endswith(".gpx.gz"):
        with gzip.open(path, "rt", encoding="utf-8", errors="ignore") as handle:
            return parse_gpx_text(handle.read()), "GPX"
    if name.endswith(".fit.gz"):
        with gzip.open(path, "rb") as handle:
            return parse_fit_bytes(handle.read()), "FIT"
    if name.endswith(".tcx.gz"):
        with gzip.open(path, "rt", encoding="utf-8", errors="ignore") as handle:
            return parse_tcx_text(handle.read()), "TCX"
    if name.endswith(".gpx"):
        return parse_gpx_file(path), "GPX"
    if name.endswith(".fit"):
        return parse_fit_file(path), "FIT"
    if name.endswith(".tcx"):
        return parse_tcx_file(path), "TCX"
    return None, ""
