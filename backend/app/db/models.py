from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, DateTime, Text
from datetime import datetime


class Base(DeclarativeBase):
    pass


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_path: Mapped[str] = mapped_column(Text)
    source_format: Mapped[str] = mapped_column(String(8))
    activity_type: Mapped[str] = mapped_column(String(32))
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_time_utc: Mapped[datetime] = mapped_column(DateTime)
    end_time_utc: Mapped[datetime] = mapped_column(DateTime)
    duration_sec: Mapped[int] = mapped_column(Integer)
    distance_m: Mapped[int] = mapped_column(Integer)
    elev_gain_m: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_hr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_hr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    polyline_points: Mapped[bytes | None] = mapped_column(nullable=True)
    geojson_path: Mapped[str] = mapped_column(Text)
    bbox: Mapped[str] = mapped_column(Text)
    hash_sig: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime)


