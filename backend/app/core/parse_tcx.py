from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from app.core.geo import haversine_m
from app.core.parse_gpx import ParsedTrack

TCX_NS = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"


def parse_tcx_file(path: Path) -> ParsedTrack | None:
    text = path.read_text(encoding="utf-8", errors="ignore")
    return parse_tcx_text(text)


def parse_tcx_text(text: str) -> ParsedTrack | None:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return None

    activity = root.find(f".//{{{TCX_NS}}}Activity")
    if activity is None:
        return None

    sport = activity.get("Sport")
    name = _first_text(activity, "Name") or _first_text(activity, "Notes")

    points: list[tuple[float, float]] = []
    timestamps: list[datetime | None] = []
    start: datetime | None = None
    end: datetime | None = None
    distances_m = 0.0
    prev_lon: float | None = None
    prev_lat: float | None = None

    for trackpoint in activity.findall(f".//{{{TCX_NS}}}Trackpoint"):
        pos = trackpoint.find(f"{{{TCX_NS}}}Position")
        if pos is None:
            continue
        lat_el = pos.find(f"{{{TCX_NS}}}LatitudeDegrees")
        lon_el = pos.find(f"{{{TCX_NS}}}LongitudeDegrees")
        if lat_el is None or lon_el is None or not lat_el.text or not lon_el.text:
            continue

        lon = float(lon_el.text)
        lat = float(lat_el.text)
        points.append((lon, lat))

        t = _parse_time(_first_text(trackpoint, "Time"))
        timestamps.append(t)
        if t is not None:
            if start is None or t < start:
                start = t
            if end is None or t > end:
                end = t

        if prev_lon is not None and prev_lat is not None:
            distances_m += haversine_m(prev_lon, prev_lat, lon, lat)
        prev_lon, prev_lat = lon, lat

    if start is None or end is None or not points:
        return None

    return ParsedTrack(
        name=name,
        activity_type=_map_sport(sport),
        start_time_utc=start,
        end_time_utc=end,
        duration_sec=int((end - start).total_seconds()),
        distance_m=int(distances_m),
        elev_gain_m=None,
        coordinates=points,
        timestamps=timestamps if any(t is not None for t in timestamps) else None,
    )


def _first_text(parent: ET.Element, local: str) -> str | None:
    el = parent.find(f"{{{TCX_NS}}}{local}")
    if el is None or not el.text:
        return None
    text = el.text.strip()
    return text or None


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _map_sport(sport: str | None) -> str | None:
    if not sport:
        return None
    s = sport.lower()
    if s in {"running", "run"}:
        return "run"
    if s in {"biking", "cycling", "bike"}:
        return "ride"
    if s in {"walking", "walk"}:
        return "walk"
    if s in {"hiking", "hike"}:
        return "walk"
    if s in {"swimming", "swim"}:
        return "swim"
    return s
