"""
Pipeline management endpoints: re-enrich events, run Valyu pipeline, etc.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Event, DailyMetric
from ..ml.severity_scorer import score_severity
from ..ml.risk_classifier import RiskTierClassifier

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/pipeline/re-enrich")
def re_enrich_events(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Re-score all existing events with the latest severity algorithm.
    Updates severity_index, threat_level, sentiment_score on all events.
    Then recomputes risk tiers on daily_metrics.
    """
    events = db.execute(select(Event)).scalars().all()
    updated = 0

    for e in events:
        # Build text from available data
        text = ""
        if e.title:
            text = e.title
        if e.content:
            text = f"{text}. {e.content}" if text else e.content
        if not text:
            text = f"{e.category or 'Event'} in {e.country or 'unknown'}"

        severity = score_severity(
            text,
            category=e.category or "Civil Unrest",
            entity_count=0,
            published_date=str(e.date) if e.date else None,
            country_code=e.country,
            goldstein_scale=e.goldstein,
            quad_class=e.quad_class,
        )

        e.severity_index = severity["severity_index"]
        e.threat_level = severity["threat_level"]
        e.sentiment_score = severity["sentiment_polarity"]
        updated += 1

    db.commit()
    logger.info("Re-enriched %d events", updated)

    # Now recompute daily_metrics severity from events
    from ..pipeline.ingest_valyu import aggregate_daily_metrics, compute_risk_and_trends
    import collections

    # Get all distinct dates
    dates = db.execute(
        select(Event.date).distinct().where(Event.date.isnot(None))
    ).scalars().all()

    metrics_updated = 0
    for d in dates:
        metrics_updated += aggregate_daily_metrics(db, d)

    # Recompute risk tiers
    compute_risk_and_trends(db)

    return {
        "events_re_enriched": updated,
        "dates_recomputed": len(dates),
        "metrics_updated": metrics_updated,
    }


@router.post("/pipeline/run-valyu")
def run_valyu(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Trigger a full Valyu ingestion pipeline run.
    Fetches new articles, classifies, scores, stores, and recomputes metrics.
    """
    from ..pipeline.ingest_valyu import run_valyu_pipeline
    result = run_valyu_pipeline(days_back=7)
    return result
