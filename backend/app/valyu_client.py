"""
Valyu API client: search and answer. Uses VALYU_API_KEY from env.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import requests

VALYU_BASE = "https://api.valyu.ai"
HEADER_API_KEY = "x-api-key"


def _api_key() -> Optional[str]:
    return os.environ.get("VALYU_API_KEY")


def search(
    query: str,
    *,
    search_type: str = "news",
    max_num_results: int = 20,
    start_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Call Valyu /v1/search. Returns list of { title, url, content, publishedDate, source }.
    """
    key = _api_key()
    if not key:
        return []

    payload: Dict[str, Any] = {
        "query": query,
        "search_type": search_type,
        "max_num_results": max_num_results,
    }
    if start_date:
        payload["start_date"] = start_date

    try:
        r = requests.post(
            f"{VALYU_BASE}/v1/search",
            json=payload,
            headers={"Content-Type": "application/json", HEADER_API_KEY: key},
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
    except Exception:
        return []

    results = data.get("results") or []
    out = []
    for item in results:
        date_val = item.get("date") or item.get("publication_date")
        pub = str(date_val) if date_val else None
        row = {
            "title": item.get("title") or "Untitled",
            "url": item.get("url") or "",
            "content": item.get("content") if isinstance(item.get("content"), str) else "",
            "publishedDate": pub,
            "source": item.get("source"),
        }
        if item.get("country_code"):
            row["country_code"] = item.get("country_code")
        if item.get("country"):
            row["country"] = item.get("country")
        for key in ("latitude", "longitude", "lat", "lon"):
            if item.get(key) is not None:
                row[key] = item[key]
        out.append(row)
    return out


def answer(query: str, *, excluded_sources: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Call Valyu /v1/answer. Returns { contents: str, search_results: [{ title, url }] }.
    """
    key = _api_key()
    if not key:
        return {"contents": "", "search_results": []}

    payload: Dict[str, Any] = {"query": query}
    if excluded_sources:
        payload["excluded_sources"] = excluded_sources

    try:
        r = requests.post(
            f"{VALYU_BASE}/v1/answer",
            json=payload,
            headers={"Content-Type": "application/json", HEADER_API_KEY: key},
            timeout=90,
        )
        r.raise_for_status()
        data = r.json()
    except Exception:
        return {"contents": "", "search_results": []}

    raw_sources = data.get("search_results") or []
    search_results = [
        {"title": s.get("title") or "Source", "url": s.get("url") or ""}
        for s in raw_sources
    ]
    return {
        "contents": data.get("contents") or "",
        "search_results": search_results,
    }


def get_country_conflicts(country: str) -> Dict[str, Any]:
    """
    Fetch past and current conflicts for a country. Returns
    { past: { conflicts: str, sources: [...] }, current: { conflicts: str, sources: [...] } }.
    """
    past_query = (
        f"List all major historical wars, conflicts, and military engagements that {country} "
        "has been involved in throughout history (excluding any ongoing conflicts). "
        "Include the dates, opposing parties, and brief outcomes for each conflict. Focus on conflicts that have ended."
    )
    current_query = (
        f"List all current, ongoing, or brewing conflicts, wars, military tensions, and security threats "
        f"involving {country} as of 2025-2026. Include active military operations, border disputes, "
        "civil unrest, terrorism threats, and geopolitical tensions. If there are no current conflicts, state that clearly."
    )
    excluded = ["wikipedia.org"]

    past = answer(past_query, excluded_sources=excluded)
    current = answer(current_query, excluded_sources=excluded)

    return {
        "past": {
            "conflicts": past.get("contents") or "No historical conflict information found.",
            "sources": past.get("search_results") or [],
        },
        "current": {
            "conflicts": current.get("contents") or "No current conflict information found.",
            "sources": current.get("search_results") or [],
        },
    }
