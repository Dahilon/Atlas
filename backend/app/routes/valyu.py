"""
Valyu proxy and military bases. Requires VALYU_API_KEY in env for Valyu endpoints.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from .. import valyu_client
from ..country_centroids import get_centroid
from ..military_bases_data import MILITARY_BASES
from ..schemas import (
    CountryConflictsResponse,
    MapEventLocation,
    MilitaryBaseResponse,
    ValyuEventResponse,
)

router = APIRouter()

DEFAULT_THREAT_QUERIES = [
    "breaking news conflict military",
    "geopolitical crisis tensions",
    "protest demonstration unrest",
    "natural disaster emergency",
    "terrorism attack security",
    "military deployment troops mobilization",
    "nuclear threat ballistic missile test",
]


def _event_id(url: str, title: str, idx: int) -> str:
    raw = f"valyu:{url}:{title}:{idx}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _threat_from_content(content: str) -> str:
    c = (content or "").lower()
    if any(x in c for x in ("critical", "nuclear", "war", "invasion")):
        return "critical"
    if any(x in c for x in ("attack", "strike", "bombing", "terrorism")):
        return "high"
    if any(x in c for x in ("protest", "unrest", "tension")):
        return "medium"
    return "medium"


# Common country names (lowercase) -> ISO-2 for inferring location from content
_COUNTRY_NAME_TO_CODE: Dict[str, str] = {
    "ukraine": "UA", "russia": "RU", "china": "CN", "israel": "IL", "gaza": "PS",
    "syria": "SY", "iran": "IR", "iraq": "IQ", "afghanistan": "AF", "yemen": "YE",
    "libya": "LY", "egypt": "EG", "turkey": "TR", "india": "IN", "pakistan": "PK",
    "north korea": "KP", "south korea": "KR", "taiwan": "TW", "vietnam": "VN",
    "united states": "US", "usa": "US", "u.s.": "US", "uk": "GB",
    "united kingdom": "GB", "france": "FR", "germany": "DE", "poland": "PL",
    "ethiopia": "ET", "sudan": "SD", "nigeria": "NG", "mali": "ML", "niger": "NE",
    "myanmar": "MM", "venezuela": "VE", "mexico": "MX", "brazil": "BR",
}


def _infer_country_from_text(text: str) -> Optional[str]:
    if not text:
        return None
    t = (" " + (text or "").lower() + " ")
    for name, code in _COUNTRY_NAME_TO_CODE.items():
        if f" {name} " in t or f" {name}," in t or f" {name}." in t:
            return code
    return None


def _location_for_valyu_item(item: Dict[str, Any], idx: int) -> MapEventLocation:
    title = (item.get("title") or "")[:100]
    lat = item.get("latitude") or item.get("lat")
    lon = item.get("longitude") or item.get("lon")
    country_code = (item.get("country_code") or item.get("country") or "").strip()
    if isinstance(country_code, str) and len(country_code) == 2:
        country_code = country_code.upper()
    else:
        country_code = None
    if lat is not None and lon is not None:
        try:
            return MapEventLocation(
                latitude=float(lat), longitude=float(lon),
                placeName=title or None, country=country_code,
            )
        except (TypeError, ValueError):
            pass
    if country_code:
        centroid = get_centroid(country_code)
        if centroid:
            return MapEventLocation(
                latitude=centroid[0], longitude=centroid[1],
                placeName=title or None, country=country_code,
            )
    text = f"{item.get('title') or ''} {item.get('content') or ''}"[:2000]
    inferred = _infer_country_from_text(text)
    if inferred:
        centroid = get_centroid(inferred)
        if centroid:
            return MapEventLocation(
                latitude=centroid[0], longitude=centroid[1],
                placeName=title or None, country=inferred,
            )
    # Jitter by index so points don't stack at (0,0): spread in a grid
    row, col = idx // 5, idx % 5
    jitter_lat = 20.0 + (row - 2) * 4.0
    jitter_lon = (col - 2) * 8.0
    return MapEventLocation(
        latitude=jitter_lat, longitude=jitter_lon,
        placeName=title or "Location unknown", country=None,
    )


def _normalize_valyu_result(item: Dict[str, Any], idx: int) -> ValyuEventResponse:
    title = item.get("title") or "Untitled"
    url = item.get("url") or ""
    content = item.get("content") or ""
    summary = (content[:500] + "…") if len(content) > 500 else content
    pub = item.get("publishedDate")
    ts = pub if pub else datetime.now(timezone.utc).isoformat()
    threat = _threat_from_content(content)
    location = _location_for_valyu_item(item, idx)
    return ValyuEventResponse(
        id=_event_id(url, title, idx),
        source="valyu",
        title=title,
        summary=summary,
        category="news",
        threatLevel=threat,
        location=location,
        timestamp=ts,
        sourceUrl=url or None,
    )


class ValyuEventsBody(BaseModel):
    queries: Optional[List[str]] = None


@router.post("/valyu/events", response_model=Dict[str, Any])
def post_valyu_events(body: Optional[ValyuEventsBody] = None) -> Dict[str, Any]:
    """
    Proxy to Valyu search; returns events normalized to MapEvent shape.
    If body.queries is empty or omitted, uses default threat queries.
    """
    queries = (body.queries if body and body.queries else None) or DEFAULT_THREAT_QUERIES
    start_date = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    all_results: List[Dict[str, Any]] = []
    seen_urls: set = set()
    for q in queries[:12]:
        results = valyu_client.search(q, max_num_results=15, start_date=start_date)
        for i, item in enumerate(results):
            url = (item.get("url") or "").strip()
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            all_results.append(item)
    events = [ _normalize_valyu_result(r, i) for i, r in enumerate(all_results) ]
    return {"events": [e.model_dump() for e in events], "count": len(events)}


@router.get("/valyu/countries/conflicts", response_model=CountryConflictsResponse)
def get_valyu_country_conflicts(country: str = Query(..., description="Country name or code")) -> CountryConflictsResponse:
    """
    Proxy to Valyu answer for historical and current conflicts for the given country.
    """
    data = valyu_client.get_country_conflicts(country)
    return CountryConflictsResponse(
        country=country,
        past=data["past"],
        current=data["current"],
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


_bases_cache: Optional[List[Dict[str, Any]]] = None
_bases_cache_ts: Optional[float] = None
CACHE_SEC = 3600


@router.get("/military-bases", response_model=Dict[str, Any])
def get_military_bases() -> Dict[str, Any]:
    """
    Return static list of US and NATO military bases for the map layer. Cached 1h.
    """
    global _bases_cache, _bases_cache_ts
    import time
    now = time.time()
    if _bases_cache is not None and _bases_cache_ts is not None and (now - _bases_cache_ts) < CACHE_SEC:
        return {"bases": _bases_cache, "cached": True}
    out = [
        {
            "country": b["country"],
            "baseName": b["baseName"],
            "latitude": b["latitude"],
            "longitude": b["longitude"],
            "type": b["type"],
        }
        for b in MILITARY_BASES
    ]
    _bases_cache = out
    _bases_cache_ts = now
    return {"bases": out, "cached": False}
