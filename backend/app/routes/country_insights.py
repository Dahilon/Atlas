"""
Fast country insights endpoint. Uses DB-first data + Valyu search (not slow /v1/answer).
Returns rich insights for any country in <5 seconds.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..country_centroids import COUNTRY_CENTROIDS
from ..db import get_db
from ..models import DailyMetric, Event
from .. import valyu_client

logger = logging.getLogger(__name__)
router = APIRouter()

# Try importing ML modules (may not be available in all environments)
try:
    from ..ml.entity_extractor import extract_entities
    from ..ml.event_classifier import classify_event, ensure_model_trained
    from ..ml.severity_scorer import score_severity
    HAS_ML = True
except ImportError:
    HAS_ML = False

# Country name lookup from centroids (ISO-2 -> full name via pycountry)
_CODE_TO_NAME: Dict[str, str] = {}
try:
    import pycountry
    for code in COUNTRY_CENTROIDS:
        c = pycountry.countries.get(alpha_2=code)
        if c:
            _CODE_TO_NAME[code] = c.name
except ImportError:
    pass


def _country_name(code: str) -> str:
    """Get human-readable country name from ISO-2 code."""
    return _CODE_TO_NAME.get(code, code)


def _build_risk_context(
    country_name: str,
    events: List[Dict],
    metrics_summary: Dict,
    news: List[Dict],
) -> str:
    """Generate a text summary of the country's risk profile."""
    parts = []

    tier = metrics_summary.get("risk_tier")
    severity = metrics_summary.get("severity")
    trend = metrics_summary.get("trend")
    event_count = metrics_summary.get("event_count", 0)

    if tier and tier != "none":
        parts.append(
            f"{country_name} is currently assessed at **{tier.upper()}** risk "
            f"(severity index: {severity:.1f}/100)."
            if severity else
            f"{country_name} is currently assessed at **{tier.upper()}** risk."
        )
    else:
        parts.append(f"{country_name} has no active risk events in our database.")

    if trend and trend != "stable":
        direction = "increasing" if trend == "rising" else "decreasing"
        parts.append(f"The 7-day trend is **{direction}**.")

    if event_count > 0:
        # Category breakdown
        cats = Counter(e.get("category", "Unknown") for e in events)
        top_cats = cats.most_common(3)
        cat_str = ", ".join(f"{cat} ({n})" for cat, n in top_cats)
        parts.append(f"Tracked {event_count} events across categories: {cat_str}.")

    if news:
        parts.append(f"Recent news coverage includes {len(news)} articles.")
        # Highlight top severity article
        top_news = max(news, key=lambda n: n.get("severity", 0), default=None)
        if top_news and top_news.get("title"):
            parts.append(f'Top headline: "{top_news["title"][:120]}"')

    if not parts:
        parts.append(f"No significant risk intelligence available for {country_name} at this time.")

    return " ".join(parts)


@router.get("/countries/{country_code}/insights")
def get_country_insights(
    country_code: str,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Fast country insights. DB-first with optional Valyu search enrichment.
    Returns in <5s for any country.
    """
    code = country_code.upper().strip()
    name = _country_name(code)

    # ── 1. DB events for this country (last 14 days) ──
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=14)
    db_events_raw = db.execute(
        select(Event)
        .where(Event.country == code, Event.date >= cutoff)
        .order_by(Event.date.desc())
        .limit(50)
    ).scalars().all()

    recent_events = []
    for e in db_events_raw:
        entities = None
        if e.entities_json:
            try:
                entities = json.loads(e.entities_json)
            except (json.JSONDecodeError, TypeError):
                pass
        recent_events.append({
            "id": str(e.id),
            "title": e.title or f"{e.category or 'Event'} in {name}",
            "category": e.category,
            "threat_level": e.threat_level or "medium",
            "severity": e.severity_index,
            "sentiment": e.sentiment_score,
            "date": str(e.date),
            "source_url": e.source_url,
            "entities": entities,
        })

    # ── 2. Daily metrics summary ──
    latest_date = db.execute(
        select(DailyMetric.date)
        .where(DailyMetric.country == code)
        .order_by(DailyMetric.date.desc())
        .limit(1)
    ).scalars().first()

    metrics_summary = {
        "risk_tier": "none",
        "severity": 0.0,
        "trend": "stable",
        "event_count": len(recent_events),
        "avg_sentiment": None,
    }

    category_breakdown: Dict[str, int] = {}

    if latest_date:
        metrics_rows = db.execute(
            select(DailyMetric)
            .where(DailyMetric.country == code, DailyMetric.date == latest_date)
        ).scalars().all()

        if metrics_rows:
            top = max(metrics_rows, key=lambda m: m.severity_index or 0)
            metrics_summary.update({
                "risk_tier": top.risk_tier or "none",
                "severity": top.severity_index or 0.0,
                "trend": top.trend_7d or "stable",
                "avg_sentiment": top.avg_sentiment,
            })
            for m in metrics_rows:
                if m.category:
                    category_breakdown[m.category] = (
                        category_breakdown.get(m.category, 0) + (m.event_count or 0)
                    )

    # If no category breakdown from metrics, build from events
    if not category_breakdown and recent_events:
        for e in recent_events:
            cat = e.get("category", "Unknown")
            category_breakdown[cat] = category_breakdown.get(cat, 0) + 1

    # ── 3. Valyu search for recent news (fast, ~3-5s) ──
    recent_news: List[Dict[str, Any]] = []
    try:
        start_date = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
        search_results = valyu_client.search(
            f"{name} conflict security threat crisis",
            max_num_results=5,
            start_date=start_date,
        )

        for item in search_results[:5]:
            news_entry: Dict[str, Any] = {
                "title": item.get("title", "Untitled"),
                "url": item.get("url", ""),
                "date": item.get("publishedDate"),
                "source": item.get("source"),
            }

            # Quick ML classification if available
            if HAS_ML:
                try:
                    ensure_model_trained()
                    text = f"{item.get('title', '')} {item.get('content', '')[:500]}"
                    cat, conf, _ = classify_event(text)
                    sev = score_severity(text, cat, 0, None)
                    news_entry["category"] = cat
                    news_entry["confidence"] = round(conf, 2)
                    news_entry["severity"] = round(sev.get("severity_index", 0), 1)
                    news_entry["threat_level"] = sev.get("threat_level", "medium")
                except Exception:
                    news_entry["category"] = "Unknown"
                    news_entry["severity"] = 0
            else:
                news_entry["category"] = "Unknown"
                news_entry["severity"] = 0

            recent_news.append(news_entry)
    except Exception as exc:
        logger.warning("Valyu search failed for %s: %s", code, exc)

    # ── 4. Related countries (from entities in events) ──
    related_countries: List[str] = []
    seen = {code}
    for e in recent_events[:20]:
        ents = e.get("entities")
        if isinstance(ents, dict):
            for c in ents.get("countries", []):
                cc = c.get("code") if isinstance(c, dict) else None
                if cc and cc not in seen:
                    seen.add(cc)
                    related_countries.append(cc)
    # Also check news entities
    for n in recent_news:
        ents = n.get("entities")
        if isinstance(ents, dict):
            for c in ents.get("countries", []):
                cc = c.get("code") if isinstance(c, dict) else None
                if cc and cc not in seen:
                    seen.add(cc)
                    related_countries.append(cc)

    # ── 5. Risk context text ──
    risk_context = _build_risk_context(name, recent_events, metrics_summary, recent_news)

    # ── 6. Metrics over time (for sparkline / mini chart) ──
    metrics_history = []
    history_rows = db.execute(
        select(DailyMetric.date, func.max(DailyMetric.severity_index), func.sum(DailyMetric.event_count))
        .where(DailyMetric.country == code)
        .group_by(DailyMetric.date)
        .order_by(DailyMetric.date.desc())
        .limit(14)
    ).all()
    for d, sev, ec in reversed(history_rows):
        metrics_history.append({
            "date": str(d),
            "severity": float(sev) if sev else 0,
            "events": int(ec) if ec else 0,
        })

    return {
        "country": code,
        "country_name": name,
        "summary": metrics_summary,
        "risk_context": risk_context,
        "recent_events": recent_events[:20],
        "recent_news": recent_news,
        "category_breakdown": category_breakdown,
        "related_countries": related_countries[:10],
        "metrics_history": metrics_history,
    }
