from __future__ import annotations

from pathlib import Path
from typing import Iterable


GPX_EXT = {".gpx"}
FIT_EXT = {".fit"}


def iter_candidate_files(root: Path) -> Iterable[Path]:
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext in GPX_EXT or ext in FIT_EXT:
            yield p


