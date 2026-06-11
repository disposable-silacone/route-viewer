from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import math
import gpxpy


@dataclass
class ParsedTrack:
    name: str | None
    activity_type: str | None
    start_time_utc: datetime
    end_time_utc: datetime
    duration_sec: int
    distance_m: int
    elev_gain_m: int | None
    coordinates: list[tuple[float, float]]  # (lon, lat)
    timestamps: list[datetime] | None = None


def parse_gpx_file(path: Path) -> ParsedTrack | None:
    text = path.read_text(encoding="utf-8", errors="ignore")
    return parse_gpx_text(text)


def parse_gpx_text(text: str) -> ParsedTrack | None:
    gpx = gpxpy.parse(text)
    if not gpx.tracks:
        return None
    points: list[tuple[float, float]] = []
    timestamps: list[datetime] = []
    distances_m = 0.0
    start: datetime | None = None
    end: datetime | None = None

    inferred_type: str | None = None
    preferred_name: str | None = (str(gpx.name).strip() if getattr(gpx, "name", None) else None)
    for trk in gpx.tracks:
        if not preferred_name and getattr(trk, 'name', None):
            # Prefer <trk><name> when available
            try:
                preferred_name = str(trk.name).strip() or None
            except Exception:
                preferred_name = None
        if not inferred_type and getattr(trk, 'type', None):
            inferred_type = str(trk.type).lower()
        for seg in trk.segments:
            prev_lon: float | None = None
            prev_lat: float | None = None
            for p in seg.points:
                if p.longitude is None or p.latitude is None:
                    continue
                points.append((float(p.longitude), float(p.latitude)))
                
                # Collect timestamp if available
                if p.time:
                    t = p.time
                    if t.tzinfo is None:
                        t = t.replace(tzinfo=timezone.utc)
                    else:
                        t = t.astimezone(timezone.utc)
                    timestamps.append(t)
                    if start is None or t < start:
                        start = t
                    if end is None or t > end:
                        end = t
                else:
                    # If no timestamp, add None to maintain alignment
                    timestamps.append(None)
                
                if prev_lon is not None and prev_lat is not None:
                    distances_m += _haversine_m(prev_lon, prev_lat, float(p.longitude), float(p.latitude))
                prev_lon, prev_lat = float(p.longitude), float(p.latitude)

    if start is None or end is None or not points:
        return None

    duration = int((end - start).total_seconds())

    return ParsedTrack(
        name=preferred_name,
        activity_type=inferred_type,
        start_time_utc=start,
        end_time_utc=end,
        duration_sec=duration,
        distance_m=int(distances_m),
        elev_gain_m=None,
        coordinates=points,
        timestamps=timestamps if any(t is not None for t in timestamps) else None,
    )


def _haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle distance in meters between two lon/lat points."""
    r = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


