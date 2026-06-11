from __future__ import annotations

from pathlib import Path
import tempfile

from app.core.ingest_paths import collect_ingest_paths, is_activity_file


def test_is_activity_file_recognizes_gz_suffixes():
    assert is_activity_file(Path("run.fit.gz"))
    assert is_activity_file(Path("track.gpx.gz"))
    assert is_activity_file(Path("run.tcx.gz"))
    assert is_activity_file(Path("run.fit"))
    assert is_activity_file(Path("track.gpx"))
    assert is_activity_file(Path("track.tcx"))
    assert not is_activity_file(Path("notes.txt"))


def test_collect_ingest_paths_finds_fit_gz(tmp_path: Path):
    (tmp_path / "a.gpx").write_text("x", encoding="utf-8")
    (tmp_path / "b.fit.gz").write_bytes(b"not-a-real-fit")
    (tmp_path / "c.tcx.gz").write_bytes(b"not-a-real-tcx")
    found = collect_ingest_paths(tmp_path, tmp_path / "extract")
    names = {p.name for p in found}
    assert "a.gpx" in names
    assert "b.fit.gz" in names
    assert "c.tcx.gz" in names
