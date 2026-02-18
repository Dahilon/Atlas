from __future__ import annotations

import logging
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional, List

import pandas as pd
from sqlalchemy.orm import Session

from ..models import Event
from ..taxonomy import map_event_to_category
from ..ml.severity_scorer import score_severity

logger = logging.getLogger("events-risk-dashboard.normalize")


# Column indices for GDELT 1.0 daily export (58 columns tab-separated, no header)
# See: https://blog.gdeltproject.org/gdelt-2-0-our-global-world-in-realtime/
IDX_GLOBALEVENTID = 0
IDX_SQLDATE = 1
IDX_EVENTCODE = 26
IDX_QUADCLASS = 29
IDX_GOLDSTEIN = 30
IDX_AVGTONE = 34
IDX_ACTOR1_COUNTRY = 7
IDX_ACTOR2_COUNTRY = 17
IDX_ACTION_COUNTRY = 51
IDX_ACTION_ADM1 = 52
IDX_ACTION_LAT = 53
IDX_ACTION_LON = 54
IDX_SOURCEURL = 57


def _parse_date(sql_date: int) -> datetime:
    """
    Parse GDELT SQLDATE (YYYYMMDD int) into a datetime at midnight UTC.
    """
    s = str(sql_date)
    return datetime.strptime(s, "%Y%m%d")


def _safe_float(val) -> Optional[float]:
    """Convert to float or None; avoids crashing on URLs or empty strings in numeric columns."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _safe_int(val) -> Optional[int]:
    """Convert to int or None."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, int):
        return val
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return None


def _get(row, idx: int, default=None):
    """Safely get row value by index; return default if missing or out of range."""
    try:
        val = row.iloc[idx]
    except IndexError:
        return default
    if pd.isna(val) or val == "":
        return default
    return val


def _resolve_country(row) -> Optional[str]:
    """
    Resolve a best-effort ISO-2 country code from ActionGeo and actor fields.
    """
    for idx in (IDX_ACTION_COUNTRY, IDX_ACTOR1_COUNTRY, IDX_ACTOR2_COUNTRY):
        val = _get(row, idx)
        if isinstance(val, str) and val:
            return val
    return None


def normalize_zip_to_events(zip_path: Path, session: Session) -> int:
    """
    Normalize a single GDELT daily export ZIP into Event records.

    Returns the number of events inserted (new or updated).
    """
    if not zip_path.exists():
        logger.warning("zip file does not exist; skipping", extra={"path": str(zip_path)})
        return 0

    logger.info("normalizing gdelt zip", extra={"path": str(zip_path)})

    # Read inner TSV into pandas
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        if not names:
            logger.warning("zip file is empty", extra={"path": str(zip_path)})
            return 0
        inner_name = names[0]
        with zf.open(inner_name) as f:
            df = pd.read_csv(
                f,
                sep="\t",
                header=None,
                dtype={IDX_GLOBALEVENTID: str, IDX_SQLDATE: int},
                low_memory=False,
            )

    inserted = 0
    failed = 0

    for _, row in df.iterrows():
        try:
            event_id = _get(row, IDX_GLOBALEVENTID)
            if not event_id:
                continue
            event_id = str(event_id).strip()

            sql_date_val = _get(row, IDX_SQLDATE)
            if sql_date_val is None:
                failed += 1
                continue
            try:
                sql_date = int(float(sql_date_val))
            except (TypeError, ValueError):
                failed += 1
                continue
            try:
                dt = _parse_date(sql_date)
            except (TypeError, ValueError):
                failed += 1
                continue

            country = _resolve_country(row)
            admin1 = _get(row, IDX_ACTION_ADM1)
            admin1 = str(admin1).strip() if admin1 is not None else None

            lat = _safe_float(_get(row, IDX_ACTION_LAT))
            lon = _safe_float(_get(row, IDX_ACTION_LON))

            event_code = _get(row, IDX_EVENTCODE)
            event_code = str(event_code).strip() if event_code is not None else None
            quad_class = _safe_int(_get(row, IDX_QUADCLASS))
            goldstein = _safe_float(_get(row, IDX_GOLDSTEIN))
            avg_tone = _safe_float(_get(row, IDX_AVGTONE))
            source_url = _get(row, IDX_SOURCEURL)
            source_url = str(source_url).strip() if source_url is not None else None

            category = map_event_to_category(event_code, quad_class, goldstein)

            # Compute severity using GDELT structured signals
            # GDELT events don't have text, but have goldstein, quad_class, avg_tone
            # Build a minimal text from available data for keyword matching
            severity_text = f"{category or ''} event"
            severity = score_severity(
                severity_text,
                category=category or "Civil Unrest",
                entity_count=0,
                published_date=dt.strftime("%Y-%m-%d") if dt else None,
                country_code=country,
                goldstein_scale=goldstein,
                quad_class=quad_class,
            )
            severity_index = severity["severity_index"]
            threat_level = severity["threat_level"]
            sentiment_polarity = severity["sentiment_polarity"]

            # Idempotent upsert: update if exists, else insert
            existing: Optional[Event] = session.get(Event, event_id)
            if existing:
                existing.ts = dt
                existing.date = dt.date()
                existing.country = country
                existing.admin1 = admin1
                existing.lat = lat
                existing.lon = lon
                existing.event_code = event_code
                existing.quad_class = quad_class
                existing.goldstein = goldstein
                existing.avg_tone = avg_tone
                existing.source_url = source_url
                existing.category = category
                existing.severity_index = severity_index
                existing.threat_level = threat_level
                existing.sentiment_score = sentiment_polarity
            else:
                event = Event(
                    id=event_id,
                    ts=dt,
                    date=dt.date(),
                    country=country,
                    admin1=admin1,
                    lat=lat,
                    lon=lon,
                    event_code=event_code,
                    quad_class=quad_class,
                    goldstein=goldstein,
                    avg_tone=avg_tone,
                    source_url=source_url,
                    category=category,
                    severity_index=severity_index,
                    threat_level=threat_level,
                    sentiment_score=sentiment_polarity,
                )
                session.add(event)
                inserted += 1
        except Exception as exc:
            failed += 1
            if failed <= 5:
                logger.warning(
                    "failed to normalize row",
                    extra={"path": str(zip_path), "error": str(exc)},
                )
    if failed > 0:
        logger.info("rows skipped or failed", extra={"path": str(zip_path), "failed": failed})

    logger.info(
        "finished normalizing gdelt zip",
        extra={"path": str(zip_path), "inserted": inserted},
    )
    return inserted


def normalize_many(zips: Iterable[Path], session: Session) -> int:
    """
    Normalize multiple ZIP files in sequence.

    Returns the total number of events inserted.
    """
    total = 0
    for zp in zips:
        total += normalize_zip_to_events(zp, session=session)
    return total

