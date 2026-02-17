"""
Named Entity Recognition and geolocation extraction from news text.

Uses spaCy for NER and pycountry for ISO-2 country code resolution.
Extracts countries, organizations, and people from article text.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pycountry
import spacy

logger = logging.getLogger(__name__)

# Lazy-loaded spaCy model
_nlp = None


def _get_nlp():
    global _nlp
    if _nlp is None:
        _nlp = spacy.load("en_core_web_sm", disable=["parser", "lemmatizer"])
    return _nlp


# ── Country name → ISO-2 resolution ──────────────────────────────────────

# Pre-built lookup: lowercase name/alias → ISO-2 code
_COUNTRY_LOOKUP: Dict[str, str] = {}


def _build_country_lookup() -> Dict[str, str]:
    """Build comprehensive country name → ISO-2 lookup from pycountry + manual aliases."""
    if _COUNTRY_LOOKUP:
        return _COUNTRY_LOOKUP

    # From pycountry (official names)
    for c in pycountry.countries:
        code = c.alpha_2
        _COUNTRY_LOOKUP[c.name.lower()] = code
        if hasattr(c, "common_name"):
            _COUNTRY_LOOKUP[c.common_name.lower()] = code
        if hasattr(c, "official_name"):
            _COUNTRY_LOOKUP[c.official_name.lower()] = code

    # Manual aliases for common shorthand / news terms
    aliases = {
        "usa": "US", "u.s.": "US", "u.s.a.": "US", "america": "US", "united states": "US",
        "uk": "GB", "britain": "GB", "england": "GB", "great britain": "GB",
        "russia": "RU", "china": "CN", "taiwan": "TW", "north korea": "KP",
        "south korea": "KR", "iran": "IR", "iraq": "IQ", "syria": "SY",
        "gaza": "PS", "palestine": "PS", "west bank": "PS",
        "israel": "IL", "ukraine": "UA", "yemen": "YE", "libya": "LY",
        "turkey": "TR", "türkiye": "TR", "egypt": "EG", "india": "IN",
        "pakistan": "PK", "afghanistan": "AF", "myanmar": "MM", "burma": "MM",
        "venezuela": "VE", "mexico": "MX", "brazil": "BR", "congo": "CD",
        "drc": "CD", "ivory coast": "CI", "south sudan": "SS",
        "czech republic": "CZ", "czechia": "CZ", "uae": "AE",
        "saudi": "SA", "saudi arabia": "SA",
    }
    for name, code in aliases.items():
        _COUNTRY_LOOKUP[name] = code

    return _COUNTRY_LOOKUP


def resolve_country_code(name: str) -> Optional[str]:
    """Resolve a country name/alias to ISO-2 code."""
    lookup = _build_country_lookup()
    raw = name.strip()
    key = raw.lower()

    # Strip leading "the " for matching
    clean = key.removeprefix("the ")

    # Direct match
    if clean in lookup:
        return lookup[clean]
    if key in lookup:
        return lookup[key]

    # Try pycountry fuzzy search as fallback (but validate result)
    try:
        results = pycountry.countries.search_fuzzy(raw)
        if results:
            # Only accept fuzzy match if similarity is high enough
            matched_name = results[0].name.lower()
            if clean in matched_name or matched_name in clean:
                return results[0].alpha_2
    except LookupError:
        pass

    return None


# ── Entity Extraction ────────────────────────────────────────────────────

@dataclass
class ExtractedEntities:
    """Entities extracted from text via NER."""
    countries: List[Tuple[str, str]] = field(default_factory=list)  # [(name, ISO-2), ...]
    organizations: List[str] = field(default_factory=list)
    persons: List[str] = field(default_factory=list)
    locations: List[str] = field(default_factory=list)
    primary_country: Optional[str] = None  # ISO-2 of most-mentioned country

    def to_dict(self) -> dict:
        return {
            "countries": [{"name": n, "code": c} for n, c in self.countries],
            "organizations": self.organizations[:10],
            "persons": self.persons[:10],
            "locations": self.locations[:10],
            "primary_country": self.primary_country,
        }


def extract_entities(text: str, max_length: int = 5000) -> ExtractedEntities:
    """
    Extract named entities from text using spaCy NER.

    Returns countries (with ISO-2 codes), organizations, persons, and locations.
    Identifies the primary country (most frequently mentioned).
    """
    if not text or not text.strip():
        return ExtractedEntities()

    nlp = _get_nlp()
    # Truncate to avoid slow processing on very long texts
    doc = nlp(text[:max_length])

    result = ExtractedEntities()
    country_counts: Dict[str, int] = {}
    seen_countries: set = set()
    seen_orgs: set = set()
    seen_persons: set = set()
    seen_locs: set = set()

    for ent in doc.ents:
        label = ent.label_
        text_val = ent.text.strip()

        if not text_val or len(text_val) < 2:
            continue

        if label == "GPE":
            code = resolve_country_code(text_val)
            if code and code not in seen_countries:
                seen_countries.add(code)
                result.countries.append((text_val, code))
            if code:
                country_counts[code] = country_counts.get(code, 0) + 1
            elif text_val.lower() not in seen_locs:
                seen_locs.add(text_val.lower())
                result.locations.append(text_val)

        elif label == "LOC":
            if text_val.lower() not in seen_locs:
                seen_locs.add(text_val.lower())
                result.locations.append(text_val)

        elif label == "ORG":
            if text_val.lower() not in seen_orgs:
                seen_orgs.add(text_val.lower())
                result.organizations.append(text_val)

        elif label == "PERSON":
            if text_val.lower() not in seen_persons:
                seen_persons.add(text_val.lower())
                result.persons.append(text_val)

    # Primary country = most mentioned
    if country_counts:
        result.primary_country = max(country_counts, key=country_counts.get)

    return result


def extract_countries_from_text(text: str) -> List[str]:
    """Quick helper: extract just ISO-2 country codes from text."""
    entities = extract_entities(text)
    return [code for _, code in entities.countries]
