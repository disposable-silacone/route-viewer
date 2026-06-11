from __future__ import annotations

from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Customer(Base):
    """Map / ingest client — activities belong to a customer; catalog is global."""

    __tablename__ = "customers"

    customer_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    activities: Mapped[list["Activity"]] = relationship(back_populates="customer")


class Region(Base):
    """Geographic processing area (cluster of nearby activities)."""

    __tablename__ = "regions"

    region_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    centroid_lat: Mapped[float] = mapped_column(Float, nullable=False)
    centroid_lon: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_min_lat: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_min_lon: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_max_lat: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_max_lon: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    segments: Mapped[list["NetworkSegment"]] = relationship(back_populates="region")
    activities: Mapped[list["Activity"]] = relationship(back_populates="region")


class CatalogTile(Base):
    """Global OSM catalog build unit — coverage gate, shared across customers."""

    __tablename__ = "catalog_tiles"
    __table_args__ = (
        Index("ix_catalog_tiles_status", "status"),
        Index("ix_catalog_tiles_tile_scheme", "tile_scheme"),
    )

    tile_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    tile_scheme: Mapped[str] = mapped_column(String(64), nullable=False)
    catalog_version: Mapped[str] = mapped_column(String(16), nullable=False)
    lat_idx: Mapped[int] = mapped_column(Integer, nullable=False)
    lon_idx: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox_min_lon: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_min_lat: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_max_lon: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_max_lat: Mapped[float] = mapped_column(Float, nullable=False)
    fetch_min_lon: Mapped[float] = mapped_column(Float, nullable=False)
    fetch_min_lat: Mapped[float] = mapped_column(Float, nullable=False)
    fetch_max_lon: Mapped[float] = mapped_column(Float, nullable=False)
    fetch_max_lat: Mapped[float] = mapped_column(Float, nullable=False)
    fetch_margin_m: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    segment_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    built_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class NetworkSegment(Base):
    """Canonical street/path segment — drawn once, referenced by usage tables."""

    __tablename__ = "network_segments"
    __table_args__ = (
        Index("ix_network_segments_region_id", "region_id"),
        Index("ix_network_segments_osm_way_id", "osm_way_id"),
    )

    segment_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    region_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("regions.region_id"), nullable=False
    )
    osm_way_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    osm_start_node_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    osm_end_node_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    highway_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    surface: Mapped[str | None] = mapped_column(String(64), nullable=True)
    access: Mapped[str | None] = mapped_column(String(64), nullable=True)
    foot: Mapped[str | None] = mapped_column(String(16), nullable=True)
    bicycle: Mapped[str | None] = mapped_column(String(16), nullable=True)
    geometry = mapped_column(
        Geometry(geometry_type="LINESTRING", srid=4326), nullable=False
    )
    length_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    region: Mapped["Region"] = relationship(back_populates="segments")
    usage_rows: Mapped[list["ActivitySegmentUsage"]] = relationship(
        back_populates="segment"
    )
    stats: Mapped["SegmentStats | None"] = relationship(
        back_populates="segment", uselist=False
    )


class Activity(Base):
    """One row per uploaded/imported run."""

    __tablename__ = "activities"
    __table_args__ = (
        Index("ix_activities_region_id", "region_id"),
        Index("ix_activities_customer_id", "customer_id"),
        Index("ix_activities_customer_hash", "customer_id", "hash_sig", unique=True),
    )

    activity_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    customer_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("customers.customer_id"), nullable=False
    )
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_activity_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    region_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("regions.region_id"), nullable=True
    )
    raw_file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    match_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )
    match_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    # Presentation / cache fields — used until segment-centric viz replaces per-activity GeoJSON
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    activity_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    geojson_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    hash_sig: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bbox: Mapped[str | None] = mapped_column(Text, nullable=True)

    customer: Mapped["Customer"] = relationship(back_populates="activities")
    region: Mapped["Region | None"] = relationship(back_populates="activities")
    segment_usage: Mapped[list["ActivitySegmentUsage"]] = relationship(
        back_populates="activity"
    )


class ActivitySegmentUsage(Base):
    """Summarized segment traversals for one activity."""

    __tablename__ = "activity_segment_usage"
    __table_args__ = (
        Index("ix_activity_segment_usage_segment_id", "segment_id"),
    )

    activity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("activities.activity_id"), primary_key=True
    )
    segment_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("network_segments.segment_id"), primary_key=True
    )
    traversals: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    matched_length_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    first_seen_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_seen_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    activity: Mapped["Activity"] = relationship(back_populates="segment_usage")
    segment: Mapped["NetworkSegment"] = relationship(back_populates="usage_rows")


class SegmentStats(Base):
    """Aggregated usage counts per segment — refreshed after ingest/match."""

    __tablename__ = "segment_stats"

    segment_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("network_segments.segment_id"), primary_key=True
    )
    total_traversals: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unique_activities: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unique_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_activity_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    segment: Mapped["NetworkSegment"] = relationship(back_populates="stats")
