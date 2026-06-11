from __future__ import annotations

import gzip
import io
import zipfile
from pathlib import Path


ACTIVITY_SUFFIXES = (".gpx", ".fit", ".tcx", ".gpx.gz", ".fit.gz", ".tcx.gz")


def is_activity_file(path: Path) -> bool:
    name = path.name.lower()
    return name.endswith(ACTIVITY_SUFFIXES)


def _extract_zip(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(dest)


def _walk_for_activities(root: Path, extract_root: Path, out: list[Path]) -> None:
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if zipfile.is_zipfile(p):
            dest = extract_root / f"{p.stem}_{abs(hash(str(p.resolve()))) % 10_000_000}"
            _extract_zip(p, dest)
            _walk_for_activities(dest, extract_root, out)
        elif is_activity_file(p):
            out.append(p)


def collect_ingest_paths(source: Path, extract_root: Path) -> list[Path]:
    """Return all ingestable activity files, extracting .zip archives as needed."""
    extract_root.mkdir(parents=True, exist_ok=True)
    results: list[Path] = []

    if source.is_file():
        if zipfile.is_zipfile(source):
            dest = extract_root / source.stem
            _extract_zip(source, dest)
            _walk_for_activities(dest, extract_root, results)
        elif is_activity_file(source):
            results.append(source)
    else:
        _walk_for_activities(source, extract_root, results)

    return results
