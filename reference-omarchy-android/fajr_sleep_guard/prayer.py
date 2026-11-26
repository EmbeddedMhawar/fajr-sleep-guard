"""Prayer time resolution (Aladhan Method 21 + offline astronomical fallback)."""

from __future__ import annotations

import datetime as dt
import json
import math
import urllib.parse
import urllib.request
from typing import Any
from zoneinfo import ZoneInfo

from .config import PRAYER_CACHE_PATH, load_json, save_json


def _strip_tz_suffix(raw: str) -> dt.datetime:
    # Aladhan iso8601=true returns e.g. "2026-11-26T05:40:00+00:00"
    return dt.datetime.fromisoformat(raw)


def fetch_aladhan_month(year: int, month: int, cfg: dict[str, Any]) -> dict[str, dict[str, str]]:
    lat = cfg["latitude"]
    lon = cfg["longitude"]
    method = cfg.get("prayer_method", 21)
    tz = cfg.get("timezone", "Africa/Casablanca")
    params = urllib.parse.urlencode({
        "latitude": lat,
        "longitude": lon,
        "method": method,
        "timezonestring": tz,
        "iso8601": "true",
    })
    url = f"https://api.aladhan.com/v1/calendar/{year}/{month}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "fajr-sleep-guard/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    out: dict[str, dict[str, str]] = {}
    for day in payload.get("data", []):
        greg = day["date"]["gregorian"]["date"]  # DD-MM-YYYY
        d_iso = dt.datetime.strptime(greg, "%d-%m-%Y").strftime("%Y-%m-%d")
        timings = day["timings"]
        out[d_iso] = {
            "fajr": timings["Fajr"].split(" ")[0],
            "sunrise": timings["Sunrise"].split(" ")[0],
            "maghrib": timings["Maghrib"].split(" ")[0],
            "isha": timings["Isha"].split(" ")[0],
            "source": f"aladhan-method-{method}",
        }
    return out


def compute_solar_twilight(date_obj: dt.date, lat: float, lon: float, tz_name: str,
                           fajr_angle: float = 19.0, isha_angle: float = 17.0) -> dict[str, str]:
    """Pure-Python astronomical fallback matching Morocco Method 21 twilight angles (19 deg / 17 deg)."""
    tz = ZoneInfo(tz_name)
    # Julian day at 0h UT
    a = (14 - date_obj.month) // 12
    y = date_obj.year + 4800 - a
    m = date_obj.month + 12 * a - 3
    jd = date_obj.day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045
    d = jd - 2451545.0

    g = math.radians((357.529 + 0.98560028 * d) % 360.0)
    q = (280.459 + 0.98564736 * d) % 360.0
    L = math.radians((q + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g)) % 360.0)
    e = math.radians(23.439 - 0.00000036 * d)

    ra = math.degrees(math.atan2(math.cos(e) * math.sin(L), math.cos(L))) / 15.0
    ra %= 24.0
    decl = math.asin(math.sin(e) * math.sin(L))
    eq_t = (q / 15.0) - ra
    if eq_t > 12:
        eq_t -= 24
    elif eq_t < -12:
        eq_t += 24

    solar_noon_utc = 12.0 - eq_t - (lon / 15.0)

    def hour_angle(angle_deg: float) -> float:
        lat_r = math.radians(lat)
        num = -math.sin(math.radians(angle_deg)) - math.sin(lat_r) * math.sin(decl)
        den = math.cos(lat_r) * math.cos(decl)
        cos_h = max(-1.0, min(1.0, num / den))
        return math.degrees(math.acos(cos_h)) / 15.0

    fajr_utc = solar_noon_utc - hour_angle(fajr_angle)
    sunrise_utc = solar_noon_utc - hour_angle(0.833)
    maghrib_utc = solar_noon_utc + hour_angle(0.833)
    isha_utc = solar_noon_utc + hour_angle(isha_angle)

    def to_local_iso(utc_hours: float) -> str:
        base = dt.datetime(date_obj.year, date_obj.month, date_obj.day, tzinfo=dt.timezone.utc)
        return (base + dt.timedelta(hours=utc_hours)).astimezone(tz).replace(microsecond=0).isoformat()

    return {
        "fajr": to_local_iso(fajr_utc),
        "sunrise": to_local_iso(sunrise_utc),
        "maghrib": to_local_iso(maghrib_utc),
        "isha": to_local_iso(isha_utc),
        "source": "offline-astronomical",
    }


def ensure_prayer_cache(cfg: dict[str, Any], days_ahead: int = 30) -> dict[str, dict[str, str]]:
    cache = load_json(PRAYER_CACHE_PATH, default={})
    if not isinstance(cache, dict):
        cache = {}

    tz = ZoneInfo(cfg.get("timezone", "Africa/Casablanca"))
    today = dt.datetime.now(tz).date()
    needed_dates = [(today + dt.timedelta(days=i)) for i in range(-1, days_ahead + 1)]
    missing = [d for d in needed_dates if d.strftime("%Y-%m-%d") not in cache]

    if missing:
        months = sorted({(d.year, d.month) for d in missing})
        for y, m in months:
            try:
                month_data = fetch_aladhan_month(y, m, cfg)
                cache.update(month_data)
            except Exception:
                pass
        save_json(PRAYER_CACHE_PATH, cache)

    # Fill any still-missing dates via offline astronomical formula (not persisted as authoritative)
    for d in needed_dates:
        key = d.strftime("%Y-%m-%d")
        if key not in cache:
            cache[key] = compute_solar_twilight(
                d, cfg["latitude"], cfg["longitude"], cfg.get("timezone", "Africa/Casablanca")
            )
    return cache


def get_day_prayers(date_obj: dt.date, cfg: dict[str, Any], cache: dict[str, dict[str, str]] | None = None) -> dict[str, dt.datetime]:
    if cache is None:
        cache = ensure_prayer_cache(cfg)
    key = date_obj.strftime("%Y-%m-%d")
    entry = cache.get(key) or compute_solar_twilight(
        date_obj, cfg["latitude"], cfg["longitude"], cfg.get("timezone", "Africa/Casablanca")
    )
    return {
        "fajr": _strip_tz_suffix(entry["fajr"]),
        "sunrise": _strip_tz_suffix(entry["sunrise"]),
        "maghrib": _strip_tz_suffix(entry["maghrib"]),
        "isha": _strip_tz_suffix(entry["isha"]),
        "source": entry.get("source", "unknown"),
    }
