"""
NLP-based severity scoring for news articles.

Computes a composite severity index (0-100) from:
  - 25% conflict-aware sentiment (keyword lexicon, not TextBlob)
  - 25% keyword intensity (TF-IDF weighted crisis terms)
  - 20% category weight (Armed Conflict > Crime/Terror > Civil Unrest > ...)
  - 10% entity density (more named entities = more significant)
  - 10% recency (newer articles scored higher)
  - 10% geopolitical context (known conflict zones, sanctions targets)
  + urgency boost (0.0-0.15)
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

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
    "world war": 3.0, "war crimes": 3.0, "mass grave": 3.0,
    # High severity (weight 2.0)
    "war": 2.0, "airstrike": 2.0, "bombing": 2.0, "missile": 2.0,
    "terrorism": 2.0, "hostage": 2.0, "assassination": 2.0, "casualties": 2.0,
    "killed": 2.0, "deaths": 2.0, "explosion": 2.0, "suicide bomb": 2.0,
    "mass shooting": 2.0, "famine": 2.0, "pandemic": 2.0, "catastrophe": 2.0,
    "artillery": 2.0, "shelling": 2.0, "ballistic": 2.0, "drone strike": 2.0,
    "occupation": 2.0, "siege": 2.0, "execution": 2.0, "torture": 2.0,
    "beheading": 2.0, "proxy war": 2.0, "civil war": 2.0, "ethnic conflict": 2.0,
    # Medium severity (weight 1.5)
    "attack": 1.5, "conflict": 1.5, "crisis": 1.5, "threat": 1.5,
    "sanctions": 1.5, "military": 1.5, "troops": 1.5, "combat": 1.5,
    "insurgent": 1.5, "militant": 1.5, "extremist": 1.5, "violence": 1.5,
    "coup": 1.5, "martial law": 1.5, "emergency": 1.5, "evacuation": 1.5,
    "rebel": 1.5, "militia": 1.5, "warlord": 1.5, "paramilitary": 1.5,
    "displaced": 1.5, "refugee": 1.5, "blockade": 1.5, "escalation": 1.5,
    # Lower severity (weight 1.0)
    "protest": 1.0, "demonstration": 1.0, "unrest": 1.0, "tension": 1.0,
    "dispute": 1.0, "strike": 1.0, "riot": 1.0, "arrest": 1.0,
    "humanitarian": 1.0, "shortage": 1.0,
    "blackout": 1.0, "cyber": 1.0, "sabotage": 1.0, "embargo": 1.0,
}

# ── Negative sentiment lexicon (conflict-domain-specific) ────────────────
# Words that indicate negative/dangerous situations in geopolitical context
# Score: higher = more negative

_NEGATIVE_LEXICON: Dict[str, float] = {
    # Extreme negative (1.0)
    "killed": 1.0, "dead": 1.0, "deaths": 1.0, "massacre": 1.0,
    "genocide": 1.0, "slaughter": 1.0, "carnage": 1.0, "atrocity": 1.0,
    "annihilate": 1.0, "destroy": 1.0, "devastate": 1.0,
    # High negative (0.85)
    "war": 0.85, "invasion": 0.85, "bombing": 0.85, "shelling": 0.85,
    "airstrike": 0.85, "missile": 0.85, "casualties": 0.85, "wounded": 0.85,
    "explosion": 0.85, "attack": 0.85, "siege": 0.85, "torture": 0.85,
    "terrorism": 0.85, "hostage": 0.85, "assassination": 0.85,
    "famine": 0.85, "starvation": 0.85, "catastrophe": 0.85,
    # Medium negative (0.65)
    "conflict": 0.65, "crisis": 0.65, "threat": 0.65, "violence": 0.65,
    "danger": 0.65, "risk": 0.65, "instability": 0.65, "collapse": 0.65,
    "escalation": 0.65, "confrontation": 0.65, "aggression": 0.65,
    "militant": 0.65, "insurgent": 0.65, "extremist": 0.65,
    "sanction": 0.65, "embargo": 0.65, "blockade": 0.65,
    "displaced": 0.65, "refugee": 0.65, "fled": 0.65, "evacuate": 0.65,
    "coup": 0.65, "overthrow": 0.65, "crackdown": 0.65,
    # Low negative (0.4)
    "tension": 0.4, "concern": 0.4, "worry": 0.4, "unrest": 0.4,
    "protest": 0.4, "dispute": 0.4, "arrest": 0.4, "detain": 0.4,
    "condemn": 0.4, "accuse": 0.4, "warn": 0.4, "reject": 0.4,
    "shortage": 0.4, "disruption": 0.4, "damage": 0.4,
}

_POSITIVE_LEXICON: Dict[str, float] = {
    "peace": 0.8, "ceasefire": 0.7, "agreement": 0.6, "treaty": 0.6,
    "cooperation": 0.6, "diplomatic": 0.5, "negotiate": 0.5, "resolve": 0.5,
    "aid": 0.4, "humanitarian aid": 0.5, "recovery": 0.4, "rebuild": 0.4,
    "stabilize": 0.5, "deescalation": 0.6, "withdraw": 0.4, "truce": 0.6,
}

# ── Known conflict zones / high-risk countries (ISO-2 codes) ─────────────
# These get a geopolitical boost to severity scoring
# Source: ACLED, UCDP, US State Dept travel advisories, UNHCR

CONFLICT_ZONE_SCORES: Dict[str, float] = {
    # Active war zones (1.0)
    "UA": 1.0,  # Ukraine - active war
    "SD": 1.0,  # Sudan - civil war
    "PS": 1.0,  # Palestine - active conflict
    "MM": 1.0,  # Myanmar - civil war
    "YE": 1.0,  # Yemen - civil war
    "SO": 1.0,  # Somalia - insurgency
    # High-risk conflict & instability (0.85)
    "SY": 0.85,  # Syria - post-war instability
    "AF": 0.85,  # Afghanistan - Taliban rule, ISIS-K
    "IQ": 0.85,  # Iraq - militia activity
    "LY": 0.85,  # Libya - factional conflict
    "CD": 0.85,  # DRC - eastern insurgency
    "ET": 0.85,  # Ethiopia - multiple conflicts
    "ML": 0.85,  # Mali - Sahel insurgency
    "BF": 0.85,  # Burkina Faso - jihadi insurgency
    "HT": 0.85,  # Haiti - gang violence / state collapse
    # Elevated threat / sanctions targets (0.7)
    "IR": 0.70,  # Iran - sanctions, proxy wars, nuclear tensions
    "KP": 0.70,  # North Korea - nuclear threat, sanctions
    "RU": 0.70,  # Russia - war aggressor, sanctions
    "IL": 0.70,  # Israel - active military operations
    "LB": 0.70,  # Lebanon - Hezbollah, economic collapse
    "NE": 0.70,  # Niger - coup, Sahel crisis
    "TD": 0.70,  # Chad - Sahel instability
    "MZ": 0.70,  # Mozambique - Cabo Delgado insurgency
    "NG": 0.70,  # Nigeria - Boko Haram, banditry
    "PK": 0.70,  # Pakistan - TTP, sectarian violence
    "CM": 0.70,  # Cameroon - Anglophone crisis
    # Moderate risk (0.5)
    "VE": 0.50,  # Venezuela - political crisis
    "CN": 0.50,  # China - Taiwan tensions, South China Sea
    "BY": 0.50,  # Belarus - authoritarian, sanctions
    "ER": 0.50,  # Eritrea - authoritarian, border tensions
    "CF": 0.50,  # Central African Republic - conflict
    "SS": 0.50,  # South Sudan - fragile peace
    "CO": 0.50,  # Colombia - FARC remnants, narco violence
    "MX": 0.50,  # Mexico - cartel violence
    "TW": 0.50,  # Taiwan - cross-strait tensions
    "KR": 0.40,  # South Korea - North Korea threat proximity
    "EG": 0.40,  # Egypt - Sinai insurgency, authoritarianism
    "TH": 0.35,  # Thailand - southern insurgency
    "PH": 0.35,  # Philippines - NPA, Abu Sayyaf
    "IN": 0.35,  # India - Kashmir, Maoist insurgency
}

# ── Urgency signal words ─────────────────────────────────────────────────

URGENCY_WORDS = {
    "breaking", "urgent", "just in", "developing", "alert",
    "imminent", "escalating", "surging", "unprecedented", "emergency",
}


def _compute_sentiment_score(text: str) -> Tuple[float, float]:
    """
    Compute conflict-aware sentiment using domain-specific lexicons.
    Returns (severity_component_0_to_1, raw_polarity_neg1_to_pos1).

    Unlike TextBlob (trained on movie reviews), this uses a curated lexicon
    of geopolitical/conflict terms that accurately scores war/crisis text.
    """
    text_lower = text.lower()
    words = re.findall(r'\b\w+\b', text_lower)
    total_words = max(len(words), 1)

    # Also check multi-word phrases
    neg_score = 0.0
    neg_hits = 0
    for term, weight in _NEGATIVE_LEXICON.items():
        count = text_lower.count(term)
        if count > 0:
            neg_score += weight * min(count, 5)
            neg_hits += count

    pos_score = 0.0
    pos_hits = 0
    for term, weight in _POSITIVE_LEXICON.items():
        count = text_lower.count(term)
        if count > 0:
            pos_score += weight * min(count, 5)
            pos_hits += count

    # Density-normalized scores
    neg_density = neg_score / max(1, total_words / 50)
    pos_density = pos_score / max(1, total_words / 50)

    # Polarity: -1 (very negative) to +1 (very positive)
    total = neg_density + pos_density
    if total == 0:
        polarity = 0.0
    else:
        polarity = (pos_density - neg_density) / total

    # Severity: higher for more negative text
    # neg_density of 3+ is extremely negative; normalize to 0-1
    severity = min(1.0, neg_density / 3.0)

    # Boost severity if there are many negative hits relative to positive
    if neg_hits > 0 and neg_hits > pos_hits * 2:
        severity = min(1.0, severity * 1.2)

    return severity, round(polarity, 4)


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

    # Normalize: a single high-weight keyword (war=2.0) should score ~0.3,
    # 3-4 crisis keywords should approach 0.8-1.0
    normalized = min(1.0, total_weight / 8.0)
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


def _compute_geopolitical_score(
    country_code: Optional[str],
    text: str,
) -> float:
    """
    Score based on geopolitical context:
    - Known conflict zones get a base score
    - Text mentioning multiple conflict zones gets boosted
    Returns 0-1 score.
    """
    base = 0.0

    # Direct country match
    if country_code and country_code.upper() in CONFLICT_ZONE_SCORES:
        base = CONFLICT_ZONE_SCORES[country_code.upper()]

    # Check if text mentions other high-risk zones (by common name)
    text_lower = text.lower()
    _COUNTRY_NAMES_TO_SCORES = {
        "ukraine": 1.0, "gaza": 1.0, "sudan": 1.0, "myanmar": 1.0,
        "yemen": 1.0, "somalia": 1.0, "syria": 0.85, "afghanistan": 0.85,
        "iraq": 0.85, "libya": 0.85, "congo": 0.85, "ethiopia": 0.85,
        "mali": 0.85, "haiti": 0.85, "iran": 0.70, "north korea": 0.70,
        "russia": 0.70, "hezbollah": 0.70, "hamas": 0.85, "taliban": 0.85,
        "isis": 1.0, "al-qaeda": 0.85, "boko haram": 0.85,
        "pakistan": 0.70, "nigeria": 0.70, "lebanon": 0.70,
        "burkina faso": 0.85, "niger": 0.70, "mozambique": 0.70,
    }

    mention_scores = []
    for name, score in _COUNTRY_NAMES_TO_SCORES.items():
        if name in text_lower:
            mention_scores.append(score)

    if mention_scores:
        # Use the highest mention score if no direct country match
        mention_max = max(mention_scores)
        base = max(base, mention_max * 0.8)  # slightly discount text-based

    return base


def score_severity(
    text: str,
    category: str = "Civil Unrest",
    entity_count: int = 0,
    published_date: Optional[str] = None,
    country_code: Optional[str] = None,
    goldstein_scale: Optional[float] = None,
    quad_class: Optional[int] = None,
) -> Dict:
    """
    Compute composite severity index (0-100) for an article.

    New in v2: conflict-aware sentiment (replaces TextBlob), geopolitical
    context scoring, optional GDELT signal integration.

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
    geo_score = _compute_geopolitical_score(country_code, text)

    # Integrate GDELT signals if available
    gdelt_boost = 0.0
    if goldstein_scale is not None:
        # Goldstein: -10 (conflict) to +10 (cooperation)
        # Map to 0-1 severity: -10 → 1.0, 0 → 0.5, +10 → 0.0
        gdelt_boost = max(0.0, min(1.0, (10.0 - goldstein_scale) / 20.0))
        # Replace sentiment with GDELT signal since it's more calibrated
        sentiment_score = max(sentiment_score, gdelt_boost)

    if quad_class is not None:
        # QuadClass: 1=verbal coop, 2=material coop, 3=verbal conflict, 4=material conflict
        quad_severity = {1: 0.1, 2: 0.2, 3: 0.6, 4: 0.9}.get(quad_class, 0.3)
        sentiment_score = max(sentiment_score, quad_severity)

    # Weighted composite (0-1)
    # Weights: keywords + sentiment drive 45%, category 15%, geopolitical 15%,
    # entity + recency 10% each, plus urgency boost
    composite = (
        0.20 * sentiment_score
        + 0.25 * keyword_score
        + 0.15 * category_score
        + 0.05 * entity_score
        + 0.05 * recency_score
        + 0.15 * geo_score
        + urgency_boost
    )
    # Floor boost: active war zones with negative sentiment should score high
    if geo_score >= 0.85 and sentiment_score >= 0.3:
        composite = max(composite, 0.65)  # active war zone + conflict text = at least high
    elif geo_score >= 0.70 and sentiment_score >= 0.3:
        composite = max(composite, 0.50)  # high-risk zone + conflict text = at least medium-high

    # Scale to 0-100
    severity_index = min(100.0, max(0.0, composite * 100.0))

    # Default threat level (will be overridden by Jenks tiers when available)
    if severity_index >= 75:
        threat_level = "critical"
    elif severity_index >= 55:
        threat_level = "high"
    elif severity_index >= 35:
        threat_level = "medium"
    elif severity_index >= 18:
        threat_level = "low"
    else:
        threat_level = "info"

    return {
        "severity_index": round(severity_index, 2),
        "threat_level": threat_level,
        "sentiment_polarity": polarity,
        "components": {
            "sentiment": round(sentiment_score, 4),
            "keyword_intensity": round(keyword_score, 4),
            "category_weight": round(category_score, 4),
            "entity_density": round(entity_score, 4),
            "recency": round(recency_score, 4),
            "geopolitical": round(geo_score, 4),
            "urgency_boost": round(urgency_boost, 4),
        },
    }
