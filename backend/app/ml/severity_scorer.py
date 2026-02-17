"""
NLP-based severity scoring for news articles.

Computes a composite severity index (0-100) from:
  - 30% sentiment negativity (TextBlob polarity)
  - 25% keyword intensity (TF-IDF weighted crisis terms)
  - 20% category weight (Armed Conflict > Crime/Terror > Civil Unrest > ...)
  - 15% entity density (more named entities = more significant)
  - 10% recency (newer articles scored higher)
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

from textblob import TextBlob

# ── Category base weights (normalized 0-1) ───────────────────────────────

CATEGORY_WEIGHTS: Dict[str, float] = {
    "Armed Conflict": 1.0,
    "Crime / Terror": 0.85,
    "Civil Unrest": 0.65,
    "Infrastructure / Energy": 0.60,
    "Economic Disruption": 0.50,
    "Diplomacy / Sanctions": 0.35,
}

# ── Crisis keyword lexicon with intensity weights ────────────────────────

CRISIS_KEYWORDS: Dict[str, float] = {
    # Extreme severity (weight 3.0)
    "nuclear": 3.0, "invasion": 3.0, "genocide": 3.0, "massacre": 3.0,
    "chemical weapons": 3.0, "biological weapon": 3.0, "ethnic cleansing": 3.0,
    "world war": 3.0,
    # High severity (weight 2.0)
    "war": 2.0, "airstrike": 2.0, "bombing": 2.0, "missile": 2.0,
    "terrorism": 2.0, "hostage": 2.0, "assassination": 2.0, "casualties": 2.0,
    "killed": 2.0, "deaths": 2.0, "explosion": 2.0, "suicide bomb": 2.0,
    "mass shooting": 2.0, "famine": 2.0, "pandemic": 2.0, "catastrophe": 2.0,
    # Medium severity (weight 1.5)
    "attack": 1.5, "conflict": 1.5, "crisis": 1.5, "threat": 1.5,
    "sanctions": 1.5, "military": 1.5, "troops": 1.5, "combat": 1.5,
    "insurgent": 1.5, "militant": 1.5, "extremist": 1.5, "violence": 1.5,
    "coup": 1.5, "martial law": 1.5, "emergency": 1.5, "evacuation": 1.5,
    # Lower severity (weight 1.0)
    "protest": 1.0, "demonstration": 1.0, "unrest": 1.0, "tension": 1.0,
    "dispute": 1.0, "strike": 1.0, "riot": 1.0, "arrest": 1.0,
    "refugee": 1.0, "displaced": 1.0, "humanitarian": 1.0, "shortage": 1.0,
    "blackout": 1.0, "cyber": 1.0, "sabotage": 1.0, "embargo": 1.0,
}

# ── Urgency signal words ─────────────────────────────────────────────────

URGENCY_WORDS = {
    "breaking", "urgent", "just in", "developing", "alert",
    "imminent", "escalating", "surging", "unprecedented", "emergency",
}


def _compute_sentiment_score(text: str) -> Tuple[float, float]:
    """
    Compute sentiment-based severity component.
    Returns (severity_component_0_to_1, raw_polarity).
    More negative sentiment = higher severity.
    """
    blob = TextBlob(text[:3000])
    polarity = blob.sentiment.polarity  # -1 (negative) to +1 (positive)
    # Map: -1 → 1.0 severity, 0 → 0.5, +1 → 0.0
    severity = max(0.0, min(1.0, (1.0 - polarity) / 2.0))
    return severity, polarity


def _compute_keyword_intensity(text: str) -> float:
    """
    Compute weighted keyword intensity score (0-1).
    Based on presence of crisis-related terms with different weights.
    """
    text_lower = text.lower()
    total_weight = 0.0
    matches = 0

    for keyword, weight in CRISIS_KEYWORDS.items():
        count = text_lower.count(keyword)
        if count > 0:
            total_weight += weight * min(count, 3)  # Cap repeated mentions
            matches += 1

    if matches == 0:
        return 0.0

    # Normalize: theoretical max is ~30 (10 keywords × 3.0 weight)
    # Practical scores: 0-15 range, normalize to 0-1
    normalized = min(1.0, total_weight / 15.0)
    return normalized


def _compute_urgency_boost(text: str) -> float:
    """Check for urgency signal words. Returns 0.0-0.15 boost."""
    text_lower = text.lower()
    hits = sum(1 for w in URGENCY_WORDS if w in text_lower)
    return min(0.15, hits * 0.05)


def _compute_entity_density(entity_count: int, text_length: int) -> float:
    """
    More entities = more geopolitically significant event.
    Returns 0-1 score.
    """
    if text_length == 0:
        return 0.0
    # entities per 100 words (rough: 5 chars per word)
    words = text_length / 5.0
    density = entity_count / max(1.0, words / 100.0)
    # Normalize: 0-10 entities per 100 words → 0-1
    return min(1.0, density / 10.0)


def _compute_recency_score(published_date: Optional[str]) -> float:
    """
    Newer articles get higher scores.
    Returns 0-1 score (1.0 = today, decays over 30 days).
    """
    if not published_date:
        return 0.5  # unknown date → neutral

    try:
        # Handle various date formats
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%SZ"):
            try:
                dt = datetime.strptime(published_date[:19], fmt)
                break
            except ValueError:
                continue
        else:
            return 0.5

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        days_old = max(0, (now - dt).days)
        # Exponential decay: half-life of 7 days
        return math.exp(-0.1 * days_old)
    except Exception:
        return 0.5


def score_severity(
    text: str,
    category: str = "Civil Unrest",
    entity_count: int = 0,
    published_date: Optional[str] = None,
) -> Dict:
    """
    Compute composite severity index (0-100) for an article.

    Returns dict with:
        - severity_index: float (0-100)
        - threat_level: str (critical/high/medium/low/info)
        - components: dict of individual scores
        - sentiment_polarity: float (-1 to 1)
    """
    # Individual components (all 0-1)
    sentiment_score, polarity = _compute_sentiment_score(text)
    keyword_score = _compute_keyword_intensity(text)
    category_score = CATEGORY_WEIGHTS.get(category, 0.3)
    entity_score = _compute_entity_density(entity_count, len(text))
    recency_score = _compute_recency_score(published_date)
    urgency_boost = _compute_urgency_boost(text)

    # Weighted composite (0-1)
    composite = (
        0.30 * sentiment_score
        + 0.25 * keyword_score
        + 0.20 * category_score
        + 0.15 * entity_score
        + 0.10 * recency_score
        + urgency_boost
    )

    # Scale to 0-100
    severity_index = min(100.0, max(0.0, composite * 100.0))

    # Default threat level (will be overridden by K-means tiers when available)
    if severity_index >= 80:
        threat_level = "critical"
    elif severity_index >= 60:
        threat_level = "high"
    elif severity_index >= 40:
        threat_level = "medium"
    elif severity_index >= 20:
        threat_level = "low"
    else:
        threat_level = "info"

    return {
        "severity_index": round(severity_index, 2),
        "threat_level": threat_level,
        "sentiment_polarity": round(polarity, 4),
        "components": {
            "sentiment": round(sentiment_score, 4),
            "keyword_intensity": round(keyword_score, 4),
            "category_weight": round(category_score, 4),
            "entity_density": round(entity_score, 4),
            "recency": round(recency_score, 4),
            "urgency_boost": round(urgency_boost, 4),
        },
    }
