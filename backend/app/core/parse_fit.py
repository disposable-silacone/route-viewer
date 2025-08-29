from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import math

from fitparse import FitFile

from app.core.parse_gpx import ParsedTrack


def _semicircles_to_deg(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value) * (180.0 / (2 ** 31))
    except Exception:
        return None


def _haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def _normalize_dt(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _map_sport_to_type(sport: Optional[str], sub_sport: Optional[str]) -> Optional[str]:
    s = (sport or '').lower()
    sub = (sub_sport or '').lower()
    if s in {"running"} or sub in {"track_running", "trail_running"}:
        return "run"
    if s in {"cycling", "biking"} or sub in {"road_biking", "mountain_biking"}:
        return "ride"
    if s in {"walking"}:
        return "walk"
    if s in {"hiking"}:
        return "walk"
    if s in {"swimming"}:
        return "swim"
    return s or None


def parse_fit_file(path: Path) -> Optional[ParsedTrack]:
    fit = FitFile(str(path))

    points: list[tuple[float, float]] = []  # (lon, lat)
    timestamps: list[datetime] = []
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    last_distance_m: Optional[float] = None

    session_name: Optional[str] = None
    sport: Optional[str] = None
    sub_sport: Optional[str] = None

    # Try to collect high-level metadata from session messages first
    for msg in fit.get_messages("session"):
        try:
            if session_name is None:
                session_name = msg.get_value("name")
            if sport is None:
                sport = msg.get_value("sport")
            if sub_sport is None:
                sub_sport = msg.get_value("sub_sport")
        except Exception:
            continue

    # Fallback to sport from sport messages if session absent
    if sport is None:
        for msg in fit.get_messages("sport"):
            try:
                sport = sport or msg.get_value("sport")
                sub_sport = sub_sport or msg.get_value("sub_sport")
            except Exception:
                continue

    # Iterate over records for points and timing
    prev_lon: Optional[float] = None
    prev_lat: Optional[float] = None
    for msg in fit.get_messages("record"):
        try:
            ts = _normalize_dt(msg.get_value("timestamp"))
            if ts is not None:
                timestamps.append(ts)
                if start is None or ts < start:
                    start = ts
                if end is None or ts > end:
                    end = ts
            else:
                timestamps.append(None)

            lon = _semicircles_to_deg(msg.get_value("position_long"))
            lat = _semicircles_to_deg(msg.get_value("position_lat"))
            if lon is not None and lat is not None:
                points.append((lon, lat))
                if prev_lon is not None and prev_lat is not None and last_distance_m is None:
                    # Only compute if cumulative distance not available
                    pass
                prev_lon, prev_lat = lon, lat

            dist = msg.get_value("distance")
            if dist is not None:
                try:
                    last_distance_m = float(dist)
                except Exception:
                    pass
        except Exception:
            continue

    if not points or start is None or end is None:
        return None

    # Compute distance if not provided
    if last_distance_m is None:
        total = 0.0
        for i in range(1, len(points)):
            lon1, lat1 = points[i - 1]
            lon2, lat2 = points[i]
            total += _haversine_m(lon1, lat1, lon2, lat2)
        last_distance_m = total

    return ParsedTrack(
        name=(str(session_name).strip() if session_name else None),
        activity_type=_map_sport_to_type(sport, sub_sport),
        start_time_utc=start,
        end_time_utc=end,
        duration_sec=int((end - start).total_seconds()),
        distance_m=int(last_distance_m or 0),
        elev_gain_m=None,
        coordinates=points,
        timestamps=timestamps if any(t is not None for t in timestamps) else None,
    )


