"""
Map endpoint: per-country aggregates with lat/lon, risk tiers, and trends.
Optionally includes ALL countries from centroids for full globe coverage.
"""
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..country_centroids import COUNTRY_CENTROIDS, get_centroid
from ..db import get_db
from ..models import DailyMetric
from ..schemas import MapCountryResponse


router = APIRouter()


@router.get("/map", response_model=List[MapCountryResponse])
def get_map(
    date_param: Optional[date] = Query(default=None, alias="date", description="Date (YYYY-MM-DD); default latest"),
    include_all: bool = Query(default=True, description="Include all countries (not just those with data)"),
    db: Session = Depends(get_db),
) -> List[MapCountryResponse]:
    """
    Per-country aggregates with ML-enriched fields:
    severity, risk_tier, risk_percentile, trend_7d, trend_30d, avg_sentiment, top_category.
    When include_all=true, also includes countries without data at severity=0.
    """
    target = date_param
    if target is None:
        latest = db.execute(
            select(DailyMetric.date).order_by(DailyMetric.date.desc()).limit(1)
        ).scalars().first()
        if not latest:
            # No data at all — return all countries at baseline if requested
            if include_all:
                return _all_countries_baseline()
            return []
        target = latest

    # Get per-country aggregates with ML fields
    subq = (
        select(
            DailyMetric.country,
            func.max(DailyMetric.severity_index).label("severity_index"),
            func.max(DailyMetric.risk_score).label("risk_score"),
            func.sum(DailyMetric.event_count).label("event_count"),
            func.avg(DailyMetric.avg_sentiment).label("avg_sentiment"),
        )
        .where(DailyMetric.date == target)
        .group_by(DailyMetric.country)
    )
    rows = db.execute(subq).all()

    # Get risk tiers and trends (from the metric with highest severity per country)
    tier_data = {}
    for m in db.execute(
        select(DailyMetric)
        .where(DailyMetric.date == target)
        .order_by(DailyMetric.severity_index.desc())
    ).scalars().all():
        if m.country and m.country not in tier_data:
            tier_data[m.country] = {
                "risk_tier": m.risk_tier,
                "risk_percentile": m.risk_percentile,
                "trend_7d": m.trend_7d,
                "trend_30d": m.trend_30d,
                "top_category": m.category,
            }

    countries_with_data = set()
    out: List[MapCountryResponse] = []
    for country, severity_index, risk_score, event_count, avg_sentiment in rows:
        if not country:
            continue
        centroid = get_centroid(country)
        if centroid is None:
            continue
        lat, lon = centroid[0], centroid[1]
        countries_with_data.add(country)

        extra = tier_data.get(country, {})
        out.append(
            MapCountryResponse(
                country=country,
                lat=lat,
                lon=lon,
                severity_index=float(severity_index) if severity_index is not None else None,
                risk_score=float(risk_score) if risk_score is not None else None,
                event_count=int(event_count) if event_count is not None else None,
                risk_tier=extra.get("risk_tier"),
                risk_percentile=float(extra["risk_percentile"]) if extra.get("risk_percentile") is not None else None,
                trend_7d=extra.get("trend_7d"),
                trend_30d=extra.get("trend_30d"),
                avg_sentiment=float(avg_sentiment) if avg_sentiment is not None else None,
                top_category=extra.get("top_category"),
            )
        )

    # Add remaining countries at baseline
    if include_all:
        for code, coords in COUNTRY_CENTROIDS.items():
            if code not in countries_with_data:
                out.append(
                    MapCountryResponse(
                        country=code,
                        lat=coords[0],
                        lon=coords[1],
                        severity_index=0,
                        risk_score=0,
                        event_count=0,
                        risk_tier="none",
                        risk_percentile=None,
                        trend_7d=None,
                        trend_30d=None,
                        avg_sentiment=None,
                        top_category=None,
                    )
                )

    return out


def _all_countries_baseline() -> List[MapCountryResponse]:
    """Return all countries with no data at baseline severity."""
    return [
        MapCountryResponse(
            country=code,
            lat=coords[0],
            lon=coords[1],
            severity_index=0,
            risk_score=0,
            event_count=0,
            risk_tier="none",
            risk_percentile=None,
            trend_7d=None,
            trend_30d=None,
            avg_sentiment=None,
            top_category=None,
        )
        for code, coords in COUNTRY_CENTROIDS.items()
    ]
