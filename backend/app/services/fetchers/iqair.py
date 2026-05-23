import logging
import os
import time
from datetime import datetime, date
from typing import List, Dict, Any, Optional, Tuple

import requests
from bs4 import BeautifulSoup  # type: ignore

from .normalize import make_row, parse_ts


logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AirQualityBot/1.0; +https://example.com/contact)",
}
TIMEOUT = 15
RETRIES = 2
CACHE_TTL_SECONDS = int(os.getenv("IQAIR_CACHE_TTL_SECONDS", "900"))
BACKOFF_SECONDS = float(os.getenv("IQAIR_BACKOFF_SECONDS", "1.0"))

_cache: Dict[Tuple[Any, ...], Tuple[float, List[Dict[str, Any]]]] = {}


def _cache_get(key: Tuple[Any, ...]) -> Optional[List[Dict[str, Any]]]:
    hit = _cache.get(key)
    if not hit:
        return None
    created_at, rows = hit
    if time.time() - created_at > CACHE_TTL_SECONDS:
        _cache.pop(key, None)
        return None
    return rows


def _cache_set(key: Tuple[Any, ...], rows: List[Dict[str, Any]]) -> None:
    _cache[key] = (time.time(), rows)


def _get(url: str) -> Optional[str]:
    for i in range(RETRIES + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            if r.status_code == 200:
                return r.text
            if r.status_code == 429:
                retry_after = None
                try:
                    retry_after = float(r.headers.get("Retry-After", ""))
                except Exception:
                    retry_after = None
                sleep_for = retry_after or (BACKOFF_SECONDS * (2 ** i))
                logger.warning("iqair_rate_limited", extra={"status": r.status_code, "attempt": i + 1, "sleep": sleep_for})
                time.sleep(sleep_for)
                continue
            if r.status_code in {403, 404}:
                logger.warning("iqair_unavailable", extra={"status": r.status_code, "url": url})
                return None
            logger.warning("iqair_non_200", extra={"status": r.status_code, "url": url, "attempt": i + 1})
        except Exception as e:
            logger.warning("iqair_request_failed", extra={"url": url, "attempt": i + 1, "error": str(e)})
        if i < RETRIES:
            time.sleep(BACKOFF_SECONDS * (2 ** i))
    return None


def _guess_city_path(city: str) -> str:
    # Basic slug guess; real implementation may need mapping
    slug = city.strip().lower().replace(" ", "-")
    return f"https://www.iqair.com/{slug}"


def fetch_iqair(city: str, start: date, end: date, lat: float = None, lon: float = None) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    cache_key = (city.strip().lower(), start.isoformat(), end.isoformat())
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.info("iqair_cache_hit", extra={"city": city, "rows": len(cached)})
        return list(cached)
    try:
        url = _guess_city_path(city)
        html = _get(url)
        if not html:
            return rows
        soup = BeautifulSoup(html, "html.parser")

        # Try to locate hourly/historical blocks; site structure may change
        # Fallback: parse current card
        candidates = []
        try:
            # Example selectors (subject to change):
            for card in soup.select('[data-testid="history"] [data-testid="hour"]'):
                ts_text = card.get("data-time") or card.get_text(" ")
                pm25 = None
                pm10 = None
                for pollutant in card.select('[data-testid="pollutant"]'):
                    label = pollutant.get_text(" ").lower()
                    val_text = pollutant.find("span")
                    val = None
                    if val_text:
                        try:
                            val = float(val_text.get_text(strip=True))
                        except Exception:
                            val = None
                    if "pm2.5" in label:
                        pm25 = val
                    elif "pm10" in label:
                        pm10 = val
                candidates.append((ts_text, pm25, pm10))
        except Exception:
            pass

        if not candidates:
            # parse current
            try:
                now_block = soup.select_one('[data-testid="current"]')
                if now_block:
                    ts_text = now_block.get("data-time") or datetime.utcnow().isoformat()
                    pm25 = None
                    pm10 = None
                    for pollutant in now_block.select('[data-testid="pollutant"]'):
                        label = pollutant.get_text(" ").lower()
                        val_tag = pollutant.find("span")
                        val = None
                        if val_tag:
                            try:
                                val = float(val_tag.get_text(strip=True))
                            except Exception:
                                val = None
                        if "pm2.5" in label:
                            pm25 = val
                        elif "pm10" in label:
                            pm10 = val
                    candidates = [(ts_text, pm25, pm10)]
            except Exception:
                pass

        for ts_text, pm25, pm10 in candidates:
            ts = parse_ts(ts_text) or datetime.utcnow()
            rows.append(make_row(ts=ts, city=city, latitude=lat, longitude=lon, pm25=pm25, pm10=pm10, source="iqair"))
    except Exception as e:
        logger.warning("fetch_iqair_failed", extra={"city": city, "error": str(e)})
        rows = []
    _cache_set(cache_key, rows)
    return rows



