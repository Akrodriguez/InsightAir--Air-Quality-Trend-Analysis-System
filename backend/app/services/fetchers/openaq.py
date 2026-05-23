import logging
import os
import time
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional, Tuple

import requests

from .normalize import make_row, parse_ts, safe_float


logger = logging.getLogger(__name__)

# OpenAQ v1/v2 retired their city-level measurements endpoint. v3 is organized
# around locations and sensors, so the migration flow is:
# 1. find nearby v3 locations by geocoded coordinates,
# 2. select PM2.5/PM10 sensors from those locations,
# 3. fetch hourly sensor measurements and merge them back into the old row shape.
BASE_URL = "https://api.openaq.org/v3"
TIMEOUT = int(os.getenv("OPENAQ_TIMEOUT_SECONDS", "20"))
RETRIES = int(os.getenv("OPENAQ_RETRIES", "2"))
BACKOFF_SECONDS = float(os.getenv("OPENAQ_BACKOFF_SECONDS", "0.75"))
CACHE_TTL_SECONDS = int(os.getenv("OPENAQ_CACHE_TTL_SECONDS", "900"))
LOCATION_CACHE_TTL_SECONDS = int(os.getenv("OPENAQ_LOCATION_CACHE_TTL_SECONDS", "21600"))
RADIUS_METERS = min(int(os.getenv("OPENAQ_RADIUS_METERS", "25000")), 25000)
MAX_LOCATIONS = int(os.getenv("OPENAQ_MAX_LOCATIONS", "5"))
MAX_SENSORS_PER_PARAMETER = int(os.getenv("OPENAQ_MAX_SENSORS_PER_PARAMETER", "2"))
HOURLY_LIMIT = min(int(os.getenv("OPENAQ_HOURLY_LIMIT", "1000")), 1000)

PARAM_ALIASES = {
    "pm25": {"pm25", "pm2.5", "pm2_5", "pm2-5"},
    "pm10": {"pm10", "pm10.0"},
}

_response_cache: Dict[Tuple[Any, ...], Tuple[float, List[Dict[str, Any]]]] = {}
_location_cache: Dict[Tuple[Any, ...], Tuple[float, List[Dict[str, Any]]]] = {}


def _cache_get(cache: Dict[Tuple[Any, ...], Tuple[float, Any]], key: Tuple[Any, ...], ttl: int) -> Optional[Any]:
    hit = cache.get(key)
    if not hit:
        return None
    created_at, value = hit
    if time.time() - created_at > ttl:
        cache.pop(key, None)
        return None
    return value


def _cache_set(cache: Dict[Tuple[Any, ...], Tuple[float, Any]], key: Tuple[Any, ...], value: Any) -> None:
    cache[key] = (time.time(), value)


def _headers() -> Dict[str, str]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "InsightAir/1.0 (+https://vercel.com)",
    }
    api_key = os.getenv("OPENAQ_API_KEY", "").strip()
    if api_key:
        headers["X-API-Key"] = api_key
    return headers


def _request_json(path: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    url = f"{BASE_URL}{path}"
    for attempt in range(RETRIES + 1):
        try:
            response = requests.get(url, params=params, headers=_headers(), timeout=TIMEOUT)
            if response.status_code == 200:
                return response.json()

            if response.status_code == 429:
                retry_after = safe_float(response.headers.get("Retry-After"))
                sleep_for = retry_after or (BACKOFF_SECONDS * (2 ** attempt))
                logger.warning(
                    "openaq_rate_limited",
                    extra={"status": response.status_code, "path": path, "attempt": attempt + 1, "sleep": sleep_for},
                )
                time.sleep(sleep_for)
                continue

            if response.status_code in {500, 502, 503, 504} and attempt < RETRIES:
                sleep_for = BACKOFF_SECONDS * (2 ** attempt)
                logger.warning(
                    "openaq_transient_error",
                    extra={"status": response.status_code, "path": path, "attempt": attempt + 1, "sleep": sleep_for},
                )
                time.sleep(sleep_for)
                continue

            logger.warning(
                "openaq_non_200",
                extra={"status": response.status_code, "path": path, "body": response.text[:300]},
            )
            return None
        except requests.Timeout:
            logger.warning("openaq_timeout", extra={"path": path, "attempt": attempt + 1, "timeout": TIMEOUT})
        except requests.RequestException as exc:
            logger.warning("openaq_request_failed", extra={"path": path, "attempt": attempt + 1, "error": str(exc)})

        if attempt < RETRIES:
            time.sleep(BACKOFF_SECONDS * (2 ** attempt))

    return None


def _parameter_key(parameter: Dict[str, Any]) -> Optional[str]:
    name = str(parameter.get("name") or parameter.get("displayName") or "").strip().lower()
    compact_name = name.replace(" ", "").replace("_", "").replace(".", "")
    if name in PARAM_ALIASES["pm25"] or compact_name in {"pm25", "pm25ugm3"}:
        return "pm25"
    if name in PARAM_ALIASES["pm10"] or compact_name in {"pm10", "pm10ugm3"}:
        return "pm10"
    return None


def _find_locations(lat: float, lon: float) -> List[Dict[str, Any]]:
    key = (round(lat, 4), round(lon, 4), RADIUS_METERS, MAX_LOCATIONS)
    cached = _cache_get(_location_cache, key, LOCATION_CACHE_TTL_SECONDS)
    if cached is not None:
        return cached

    params = {
        "coordinates": f"{lat:.4f},{lon:.4f}",
        "radius": RADIUS_METERS,
        "limit": MAX_LOCATIONS,
        "page": 1,
        # v3 uses parameter IDs instead of v2's parameter=pm25. Keep this broad
        # enough for providers whose metadata differs, then filter sensors locally.
        "parameters_id": "1,2",
    }
    data = _request_json("/locations", params)
    locations = (data or {}).get("results") or []
    _cache_set(_location_cache, key, locations)
    return locations


def _sensor_candidates(locations: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    candidates: Dict[str, List[Dict[str, Any]]] = {"pm25": [], "pm10": []}
    for location in locations:
        loc_coordinates = location.get("coordinates") or {}
        for sensor in location.get("sensors") or []:
            parameter_key = _parameter_key(sensor.get("parameter") or {})
            if not parameter_key:
                continue
            candidates[parameter_key].append(
                {
                    "id": sensor.get("id"),
                    "parameter": parameter_key,
                    "location_id": location.get("id"),
                    "distance": safe_float(location.get("distance")) or 0,
                    "latitude": loc_coordinates.get("latitude"),
                    "longitude": loc_coordinates.get("longitude"),
                }
            )

    for key in candidates:
        candidates[key] = sorted(
            [sensor for sensor in candidates[key] if sensor.get("id")],
            key=lambda item: item.get("distance") or 0,
        )[:MAX_SENSORS_PER_PARAMETER]
    return candidates


def _fetch_sensor_hours(sensor_id: int, start_dt: datetime, end_dt: datetime) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    page = 1
    while True:
        data = _request_json(
            f"/sensors/{sensor_id}/measurements/hourly",
            {
                "datetime_from": start_dt.isoformat() + "Z",
                "datetime_to": end_dt.isoformat() + "Z",
                "limit": HOURLY_LIMIT,
                "page": page,
            },
        )
        results = (data or {}).get("results") or []
        if not results:
            break
        rows.extend(results)
        if len(results) < HOURLY_LIMIT:
            break
        page += 1
        if page > 5:
            logger.warning("openaq_page_cap_reached", extra={"sensor_id": sensor_id, "page": page})
            break
    return rows


def _datetime_utc(value: Optional[Dict[str, Any]]) -> Optional[str]:
    if not isinstance(value, dict):
        return None
    return value.get("utc")


def fetch_openaq(city: str, start: date, end: date, lat: float = None, lon: float = None) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if lat is None or lon is None:
        logger.warning("openaq_skipped_missing_coordinates", extra={"city": city})
        return rows

    cache_key = (city.strip().lower(), start.isoformat(), end.isoformat(), round(float(lat), 4), round(float(lon), 4))
    cached_rows = _cache_get(_response_cache, cache_key, CACHE_TTL_SECONDS)
    if cached_rows is not None:
        logger.info("openaq_cache_hit", extra={"city": city, "rows": len(cached_rows)})
        return list(cached_rows)

    try:
        start_dt = datetime.combine(start, datetime.min.time())
        end_dt = datetime.combine(end + timedelta(days=1), datetime.min.time())
        locations = _find_locations(float(lat), float(lon))
        sensors_by_parameter = _sensor_candidates(locations)
        if not sensors_by_parameter["pm25"] and not sensors_by_parameter["pm10"]:
            logger.warning("openaq_no_pm_sensors", extra={"city": city, "lat": lat, "lon": lon})
            _cache_set(_response_cache, cache_key, rows)
            return rows

        by_ts: Dict[str, Dict[str, Any]] = {}
        for pollutant, sensors in sensors_by_parameter.items():
            for sensor in sensors:
                sensor_rows = _fetch_sensor_hours(int(sensor["id"]), start_dt, end_dt)
                for item in sensor_rows:
                    period = item.get("period") or {}
                    ts = parse_ts(_datetime_utc(period.get("datetimeFrom")))
                    ts = ts or parse_ts(_datetime_utc(item.get("datetimeFrom")))
                    if not ts:
                        continue
                    key = ts.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H:00:00")
                    ent = by_ts.setdefault(
                        key,
                        {
                            "lat": (item.get("coordinates") or {}).get("latitude") or sensor.get("latitude") or lat,
                            "lon": (item.get("coordinates") or {}).get("longitude") or sensor.get("longitude") or lon,
                            "pm25_values": [],
                            "pm10_values": [],
                        },
                    )
                    value = safe_float(item.get("value"))
                    if value is not None:
                        ent[f"{pollutant}_values"].append(value)

        for ts_key, ent in by_ts.items():
            pm25_values = ent.get("pm25_values") or []
            pm10_values = ent.get("pm10_values") or []
            rows.append(
                make_row(
                    ts=parse_ts(ts_key) or datetime.utcnow(),
                    city=city,
                    latitude=ent.get("lat"),
                    longitude=ent.get("lon"),
                    pm25=sum(pm25_values) / len(pm25_values) if pm25_values else None,
                    pm10=sum(pm10_values) / len(pm10_values) if pm10_values else None,
                    source="openaq",
                )
            )
        rows.sort(key=lambda row: row["ts"])
    except Exception:
        logger.exception("fetch_openaq_failed", extra={"city": city, "start": start.isoformat(), "end": end.isoformat()})
        rows = []

    _cache_set(_response_cache, cache_key, rows)
    return rows
