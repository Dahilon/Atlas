"""
Analytics endpoints: risk distribution, category breakdown, sparklines, decomposition.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Optional

import numpy as np
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import DailyMetric, Event
from ..schemas import (
    CategoryBreakdownResponse,
    DecompositionResponse,
    RiskDistributionResponse,
    RiskTiersResponse,
    SparklineResponse,
)
from ..ml.risk_classifier import RiskTierClassifier
from ..ml.time_series import compute_ewma, decompose_stl

router = APIRouter(prefix="/analytics")


@router.get("/risk-distribution", response_model=RiskDistributionResponse)
def get_risk_distribution(
    db: Session = Depends(get_db),
) -> RiskDistributionResponse:
    """Histogram of severity/risk score distribution across all recent metrics."""
    scores = db.execute(
        select(DailyMetric.severity_index)
        .where(DailyMetric.severity_index.isnot(None))
        .order_by(DailyMetric.date.desc())
        .limit(500)
    ).scalars().all()

    if not scores:
        return RiskDistributionResponse(bins=[], stats={})

    arr = np.array([float(s) for s in scores])

    # Build histogram bins
    bin_edges = [0, 20, 40, 60, 80, 100]
    bin_labels = ["0-20", "20-40", "40-60", "60-80", "80-100"]
    counts, _ = np.histogram(arr, bins=bin_edges)

    bins = [{"range": label, "count": int(c)} for label, c in zip(bin_labels, counts)]

    stats = {
        "mean": round(float(np.mean(arr)), 2),
        "median": round(float(np.median(arr)), 2),
        "std": round(float(np.std(arr)), 2),
        "min": round(float(np.min(arr)), 2),
        "max": round(float(np.max(arr)), 2),
        "count": len(arr),
    }

    return RiskDistributionResponse(bins=bins, stats=stats)


@router.get("/risk-tiers", response_model=RiskTiersResponse)
def get_risk_tiers(
    db: Session = Depends(get_db),
) -> RiskTiersResponse:
    """Current risk tier boundaries computed via Jenks Natural Breaks."""
    scores = db.execute(
        select(DailyMetric.severity_index)
        .where(DailyMetric.severity_index.isnot(None))
    ).scalars().all()

    classifier = RiskTierClassifier(method="jenks")
    if scores:
        config = classifier.fit([float(s) for s in scores])
    else:
        config = {"method": "jenks", "boundaries": [], "n_samples": 0}

    return RiskTiersResponse(
        method=classifier.method,
        boundaries=classifier.boundaries,
        tier_ranges={k: list(v) for k, v in classifier.tier_ranges.items()},
        n_samples=len(classifier.all_scores),
        fitted_at=classifier.fitted_at,
    )


@router.get("/category-breakdown", response_model=CategoryBreakdownResponse)
def get_category_breakdown(
    days: int = Query(default=7, ge=1, le=90),
    db: Session = Depends(get_db),
) -> CategoryBreakdownResponse:
    """Category distribution of events over last N days."""
    cutoff = date.today() - timedelta(days=days)
    rows = db.execute(
        select(Event.category, func.count(Event.id).label("cnt"))
        .where(Event.date >= cutoff)
        .where(Event.category.isnot(None))
        .group_by(Event.category)
        .order_by(func.count(Event.id).desc())
    ).all()

    total = sum(r.cnt for r in rows)
    categories = [
        {
            "name": r.category,
            "count": r.cnt,
            "percentage": round(r.cnt / total * 100, 1) if total > 0 else 0,
        }
        for r in rows
    ]

    return CategoryBreakdownResponse(categories=categories, total=total)


@router.get("/sparklines", response_model=List[SparklineResponse])
def get_sparklines(
    countries: str = Query(..., description="Comma-separated country codes"),
    days: int = Query(default=14, ge=3, le=90),
    db: Session = Depends(get_db),
) -> List[SparklineResponse]:
    """Mini time series of severity index per country for sparkline charts."""
    country_list = [c.strip().upper() for c in countries.split(",") if c.strip()]
    cutoff = date.today() - timedelta(days=days)

    results = []
    for country in country_list:
        rows = db.execute(
            select(DailyMetric.date, func.max(DailyMetric.severity_index).label("severity"))
            .where(DailyMetric.country == country)
            .where(DailyMetric.date >= cutoff)
            .group_by(DailyMetric.date)
            .order_by(DailyMetric.date.asc())
        ).all()

        dates = [str(r.date) for r in rows]
        values = [float(r.severity) if r.severity is not None else None for r in rows]

        results.append(SparklineResponse(country=country, dates=dates, values=values))

    return results


@router.get("/decomposition", response_model=Optional[DecompositionResponse])
def get_decomposition(
    country: str = Query(..., description="ISO-2 country code"),
    days: int = Query(default=30, ge=14, le=180),
    db: Session = Depends(get_db),
) -> Optional[DecompositionResponse]:
    """STL decomposition of severity time series for a country."""
    cutoff = date.today() - timedelta(days=days)

    rows = db.execute(
        select(DailyMetric.date, func.avg(DailyMetric.severity_index).label("severity"))
        .where(DailyMetric.country == country.upper())
        .where(DailyMetric.date >= cutoff)
        .where(DailyMetric.severity_index.isnot(None))
        .group_by(DailyMetric.date)
        .order_by(DailyMetric.date.asc())
    ).all()

    if len(rows) < 14:
        return None

    dates = [str(r.date) for r in rows]
    values = [float(r.severity) for r in rows]

    result = decompose_stl(values, dates=dates, period=7)
    if result is None:
        return None

    return DecompositionResponse(
        country=country.upper(),
        dates=result.dates,
        trend=result.trend,
        seasonal=result.seasonal,
        residual=result.residual,
        seasonal_strength=result.seasonal_strength,
    )


@router.get("/top-movers")
def get_top_movers(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> List[Dict]:
    """Top countries by severity with trends — for the movers table."""
    latest_date = db.execute(
        select(DailyMetric.date).order_by(DailyMetric.date.desc()).limit(1)
    ).scalars().first()

    if not latest_date:
        return []

    rows = db.execute(
        select(
            DailyMetric.country,
            func.max(DailyMetric.severity_index).label("severity"),
            func.max(DailyMetric.risk_tier).label("risk_tier"),
            func.max(DailyMetric.risk_percentile).label("percentile"),
            func.max(DailyMetric.trend_7d).label("trend_7d"),
            func.sum(DailyMetric.event_count).label("event_count"),
        )
        .where(DailyMetric.date == latest_date)
        .where(DailyMetric.country.isnot(None))
        .group_by(DailyMetric.country)
        .order_by(func.max(DailyMetric.severity_index).desc())
        .limit(limit)
    ).all()

    return [
        {
            "country": r.country,
            "severity_index": round(float(r.severity), 1) if r.severity else None,
            "risk_tier": r.risk_tier,
            "risk_percentile": round(float(r.percentile), 1) if r.percentile else None,
            "trend_7d": r.trend_7d,
            "event_count": int(r.event_count) if r.event_count else 0,
        }
        for r in rows
    ]
