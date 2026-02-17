"""
Combined events endpoint: serves ML-enriched events from DB for map and feed.

Events are pre-classified by the Valyu ingestion pipeline (ingest_valyu.py)
with NLP category classification, severity scoring, and entity extraction.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..country_centroids import get_centroid
from ..db import get_db
from ..models import Event
from ..schemas import CombinedEventsResponse, MapEventLocation, ValyuEventResponse

router = APIRouter()


def _event_to_response(e: Event) -> ValyuEventResponse:
    """Convert a DB Event (ML-enriched) to API response."""
    lat = e.lat
    lon = e.lon
    if (lat is None or lon is None) and e.country:
        centroid = get_centroid(e.country)
        if centroid:
            lat, lon = centroid[0], centroid[1]
    lat = lat if lat is not None else 0.0
    lon = lon if lon is not None else 0.0

    title = e.title or f"{e.category or 'Event'} in {e.country or 'Unknown'}"
    content = e.content or ""
    summary = (content[:500] + "…") if len(content) > 500 else content

    # Parse entities if available
    entities = None
    if e.entities_json:
        try:
            entities = json.loads(e.entities_json)
        except (json.JSONDecodeError, TypeError):
            pass

    return ValyuEventResponse(
        id=str(e.id),
        source=e.source or "valyu",
        title=title,
        summary=summary,
        category=e.category or "event",
        threatLevel=e.threat_level or "medium",
        location=MapEventLocation(
            latitude=lat,
            longitude=lon,
            placeName=e.admin1 or e.country,
            country=e.country,
        ),
        timestamp=e.ts.isoformat() if isinstance(e.ts, datetime) else str(e.ts),
        sourceUrl=e.source_url,
        severity_index=e.severity_index,
        risk_score=e.severity_index,  # use severity as risk score
        event_count=None,
        category_confidence=e.category_confidence,
        sentiment_polarity=e.sentiment_score,
        entities=entities,
    )


@router.get("/events/combined", response_model=CombinedEventsResponse)
def get_combined_events(
    date_param: Optional[date] = Query(default=None, alias="date"),
    limit: int = Query(default=500, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> CombinedEventsResponse:
    """
    ML-enriched events for map and feed. Events are pre-classified with:
    - NLP category (TF-IDF + LogReg)
    - Severity index (sentiment + keyword intensity + entity density)
    - Threat level (K-means risk tiers)
    - Named entities (spaCy NER)
    """
    stmt = select(Event).order_by(Event.date.desc(), Event.ts.desc())

    if date_param:
        stmt = stmt.where(Event.date == date_param)
    else:
        cutoff = datetime.now(timezone.utc).date() - timedelta(days=14)
        stmt = stmt.where(Event.date >= cutoff)

    stmt = stmt.limit(limit)
    rows = db.execute(stmt).scalars().all()

    events = [_event_to_response(e) for e in rows]

    # Sort by threat level (critical first)
    threat_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    events.sort(key=lambda x: threat_order.get(x.threatLevel, 5))

    # Count by source
    counts: Dict[str, int] = {}
    for e in events:
        counts[e.source] = counts.get(e.source, 0) + 1

    return CombinedEventsResponse(events=events, count=len(events), sources=counts)
