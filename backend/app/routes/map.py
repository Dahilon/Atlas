"""
Map endpoint: per-country aggregates with lat/lon, risk tiers, and trends.
"""
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..country_centroids import get_centroid
from ..db import get_db
from ..models import DailyMetric
from ..schemas import MapCountryResponse


router = APIRouter()


@router.get("/map", response_model=List[MapCountryResponse])
def get_map(
    date_param: Optional[date] = Query(default=None, alias="date", description="Date (YYYY-MM-DD); default latest"),
    db: Session = Depends(get_db),
) -> List[MapCountryResponse]:
    """
    Per-country aggregates with ML-enriched fields:
    severity, risk_tier, risk_percentile, trend_7d, trend_30d, avg_sentiment, top_category.
    """
    target = date_param
    if target is None:
        latest = db.execute(
            select(DailyMetric.date).order_by(DailyMetric.date.desc()).limit(1)
        ).scalars().first()
        if not latest:
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

    out: List[MapCountryResponse] = []
    for country, severity_index, risk_score, event_count, avg_sentiment in rows:
        if not country:
            continue
        centroid = get_centroid(country)
        if centroid is None:
            continue
        lat, lon = centroid[0], centroid[1]

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
    return out
