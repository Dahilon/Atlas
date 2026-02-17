"""
Valyu ingestion pipeline: fetch → classify → score → store → aggregate.

Fetches news articles from Valyu API, runs NLP classification and severity
scoring, stores enriched events, and aggregates into daily metrics.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db, SessionLocal
from ..models import DailyMetric, Event
from ..country_centroids import get_centroid
from .. import valyu_client
from ..ml.entity_extractor import extract_entities
from ..ml.event_classifier import classify_event, ensure_model_trained
from ..ml.severity_scorer import score_severity
from ..ml.risk_classifier import RiskTierClassifier
from ..ml.trend_detector import detect_trend

logger = logging.getLogger(__name__)

# Diverse threat queries for broad coverage
INGESTION_QUERIES = [
    "armed conflict military operations war",
    "terrorism attack bombing security threat",
    "protest demonstration civil unrest riot",
    "sanctions diplomacy international relations treaty",
    "economic crisis recession market crash inflation",
    "infrastructure attack pipeline cyberattack power grid",
    "missile strike drone attack shelling",
    "coup revolution political crisis regime change",
    "refugee crisis humanitarian emergency displacement",
    "nuclear threat ballistic missile weapons proliferation",
    "border conflict territorial dispute military buildup",
    "extremism radicalization insurgency guerrilla",
]


def _event_id(url: str, title: str) -> str:
    """Generate deterministic ID for dedup."""
    raw = f"valyu:{url}:{title}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def fetch_and_classify(
    queries: Optional[List[str]] = None,
    days_back: int = 7,
    max_results_per_query: int = 15,
) -> List[Dict[str, Any]]:
    """
    Fetch articles from Valyu, run ML classification + severity scoring + NER.

    Returns list of enriched event dicts ready for DB insertion.
    """
    ensure_model_trained()

    queries = queries or INGESTION_QUERIES
    start_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")

    all_items: List[Dict[str, Any]] = []
    seen_urls: set = set()

    for query in queries:
        try:
            results = valyu_client.search(
                query, max_num_results=max_results_per_query, start_date=start_date,
            )
            for item in results:
                url = (item.get("url") or "").strip()
                if url and url in seen_urls:
                    continue
                if url:
                    seen_urls.add(url)
                all_items.append(item)
        except Exception as e:
            logger.warning("Query '%s' failed: %s", query[:40], e)
            continue

    logger.info("Fetched %d unique articles from Valyu", len(all_items))

    # Process each article through ML pipeline
    enriched: List[Dict[str, Any]] = []
    for item in all_items:
        title = item.get("title") or "Untitled"
        content = item.get("content") or ""
        url = item.get("url") or ""
        published = item.get("publishedDate")

        text = f"{title}. {content}"

        # 1. Entity extraction (NER)
        entities = extract_entities(text)

        # 2. Category classification
        category, cat_confidence, cat_probs = classify_event(text)

        # 3. Severity scoring
        severity = score_severity(
            text,
            category=category,
            entity_count=len(entities.countries) + len(entities.organizations),
            published_date=published,
        )

        # 4. Determine country
        country_code = None
        # Try Valyu-provided country first
        for key in ("country_code", "country"):
            val = item.get(key)
            if val and isinstance(val, str) and len(val) == 2:
                country_code = val.upper()
                break
        # Fallback to NER primary country
        if not country_code and entities.primary_country:
            country_code = entities.primary_country

        # 5. Determine coordinates
        lat = item.get("latitude") or item.get("lat")
        lon = item.get("longitude") or item.get("lon")
        if (lat is None or lon is None) and country_code:
            centroid = get_centroid(country_code)
            if centroid:
                lat, lon = centroid[0], centroid[1]

        # 6. Parse timestamp
        ts = None
        if published:
            for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
                try:
                    ts = datetime.strptime(str(published)[:19], fmt)
                    break
                except ValueError:
                    continue
        if ts is None:
            ts = datetime.now(timezone.utc).replace(tzinfo=None)

        event_date = ts.date() if hasattr(ts, "date") else date.today()

        enriched.append({
            "id": _event_id(url, title),
            "ts": ts,
            "date": event_date,
            "country": country_code,
            "lat": float(lat) if lat is not None else None,
            "lon": float(lon) if lon is not None else None,
            "source": "valyu",
            "title": title,
            "content": content[:2000],  # truncate for DB
            "source_url": url,
            "category": category,
            "category_confidence": cat_confidence,
            "severity_index": severity["severity_index"],
            "sentiment_score": severity["sentiment_polarity"],
            "threat_level": severity["threat_level"],
            "entities_json": json.dumps(entities.to_dict()),
            "avg_tone": severity["sentiment_polarity"],  # map sentiment to tone field
        })

    return enriched


def store_events(enriched_events: List[Dict[str, Any]], session: Session) -> int:
    """
    Upsert enriched events into the events table.
    Returns number of new events inserted.
    """
    inserted = 0
    for evt in enriched_events:
        existing = session.get(Event, evt["id"])
        if existing:
            # Update ML fields on existing event
            existing.category = evt["category"]
            existing.category_confidence = evt["category_confidence"]
            existing.severity_index = evt["severity_index"]
            existing.sentiment_score = evt["sentiment_score"]
            existing.threat_level = evt["threat_level"]
            existing.entities_json = evt["entities_json"]
        else:
            event = Event(
                id=evt["id"],
                ts=evt["ts"],
                date=evt["date"],
                country=evt["country"],
                lat=evt["lat"],
                lon=evt["lon"],
                source=evt["source"],
                title=evt["title"],
                content=evt["content"],
                source_url=evt["source_url"],
                category=evt["category"],
                category_confidence=evt["category_confidence"],
                severity_index=evt["severity_index"],
                sentiment_score=evt["sentiment_score"],
                threat_level=evt["threat_level"],
                entities_json=evt["entities_json"],
                avg_tone=evt["avg_tone"],
            )
            session.add(event)
            inserted += 1

    session.commit()
    logger.info("Stored %d new events, updated %d existing", inserted, len(enriched_events) - inserted)
    return inserted


def aggregate_daily_metrics(session: Session, target_date: Optional[date] = None) -> int:
    """
    Aggregate events into daily_metrics by (date, country, category).
    Returns number of metrics upserted.
    """
    if target_date is None:
        target_date = date.today()

    # Query events for the target date
    stmt = (
        select(
            Event.date,
            Event.country,
            Event.category,
            func.count(Event.id).label("event_count"),
            func.avg(Event.avg_tone).label("avg_tone"),
            func.avg(Event.severity_index).label("avg_severity"),
            func.avg(Event.sentiment_score).label("avg_sentiment"),
        )
        .where(Event.date == target_date)
        .where(Event.country.isnot(None))
        .where(Event.category.isnot(None))
        .group_by(Event.date, Event.country, Event.category)
    )

    rows = session.execute(stmt).all()
    upserted = 0

    for row in rows:
        existing = session.execute(
            select(DailyMetric).where(
                DailyMetric.date == row.date,
                DailyMetric.country == row.country,
                DailyMetric.category == row.category,
            )
        ).scalars().first()

        if existing:
            existing.event_count = row.event_count
            existing.avg_tone = row.avg_tone
            existing.severity_index = row.avg_severity
            existing.avg_sentiment = row.avg_sentiment
            existing.computed_at = datetime.now(timezone.utc)
        else:
            metric = DailyMetric(
                date=row.date,
                country=row.country,
                category=row.category,
                event_count=row.event_count,
                avg_tone=row.avg_tone,
                severity_index=row.avg_severity,
                avg_sentiment=row.avg_sentiment,
                computed_at=datetime.now(timezone.utc),
                pipeline_version="valyu_ml_v1",
            )
            session.add(metric)
        upserted += 1

    session.commit()
    logger.info("Aggregated %d daily metrics for %s", upserted, target_date)
    return upserted


def compute_risk_and_trends(session: Session) -> None:
    """
    Compute risk tiers + trend detection on aggregated daily metrics.
    """
    # Get all severity scores for risk tier fitting
    scores = session.execute(
        select(DailyMetric.severity_index).where(DailyMetric.severity_index.isnot(None))
    ).scalars().all()

    if not scores:
        logger.warning("No severity scores to classify")
        return

    # Fit risk tiers
    classifier = RiskTierClassifier(method="jenks")
    tier_config = classifier.fit([float(s) for s in scores])
    logger.info("Risk tiers: %s", tier_config.get("tier_ranges", {}))

    # Apply risk tiers to all metrics
    metrics = session.execute(select(DailyMetric)).scalars().all()
    for m in metrics:
        if m.severity_index is not None:
            tier, percentile = classifier.classify(m.severity_index)
            m.risk_tier = tier
            m.risk_percentile = percentile
            m.risk_score = m.severity_index  # use severity as risk for now

    # Compute trends per country
    country_series: Dict[str, List] = defaultdict(list)
    country_metrics = session.execute(
        select(DailyMetric).order_by(DailyMetric.date.asc())
    ).scalars().all()

    for m in country_metrics:
        if m.severity_index is not None:
            country_series[m.country].append((m.date, m.severity_index))

    for country, series in country_series.items():
        if len(series) < 4:
            continue
        values = [v for _, v in series]
        trend_7d = detect_trend(values[-7:] if len(values) >= 7 else values)
        trend_30d = detect_trend(values[-30:] if len(values) >= 30 else values)

        # Apply to latest metrics for this country
        latest_date = series[-1][0]
        for m in metrics:
            if m.country == country and m.date == latest_date:
                m.trend_7d = trend_7d.direction
                m.trend_30d = trend_30d.direction
                m.trend_slope = trend_7d.slope
                m.trend_confidence = trend_7d.confidence

    session.commit()
    logger.info("Computed risk tiers and trends for %d countries", len(country_series))


def run_valyu_pipeline(days_back: int = 7) -> Dict[str, Any]:
    """
    Run the full Valyu ingestion pipeline:
      1. Fetch & classify articles
      2. Store enriched events
      3. Aggregate daily metrics
      4. Compute risk tiers + trends

    Returns summary stats.
    """
    logger.info("Starting Valyu ingestion pipeline (days_back=%d)", days_back)

    # Fetch and classify
    enriched = fetch_and_classify(days_back=days_back)
    if not enriched:
        logger.warning("No articles fetched from Valyu")
        return {"events_fetched": 0, "events_stored": 0, "metrics_aggregated": 0}

    session = SessionLocal()
    try:
        # Store events
        stored = store_events(enriched, session)

        # Aggregate daily metrics for each date
        dates = set(e["date"] for e in enriched)
        total_metrics = 0
        for d in sorted(dates):
            total_metrics += aggregate_daily_metrics(session, d)

        # Compute risk tiers and trends
        compute_risk_and_trends(session)

        summary = {
            "events_fetched": len(enriched),
            "events_stored": stored,
            "dates_processed": len(dates),
            "metrics_aggregated": total_metrics,
        }
        logger.info("Pipeline complete: %s", summary)
        return summary
    finally:
        session.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Load env
    from dotenv import load_dotenv
    import sys
    from pathlib import Path

    # Try multiple .env locations
    for env_path in [
        Path(__file__).resolve().parent.parent.parent.parent / ".env",
        Path(__file__).resolve().parent.parent.parent.parent / "frontend" / ".env",
    ]:
        if env_path.exists():
            load_dotenv(env_path)
            break

    result = run_valyu_pipeline()
    print(json.dumps(result, indent=2))
