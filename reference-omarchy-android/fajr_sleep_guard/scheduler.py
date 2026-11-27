"""Adaptive Isha-to-Fajr sleep scheduler (gradual wake + 1h pre-sleep lock)."""

from __future__ import annotations

import datetime as dt
import statistics
from typing import Any
from zoneinfo import ZoneInfo

from .config import HISTORY_PATH, SCHEDULE_PATH, load_config, load_json, save_json
from .prayer import ensure_prayer_cache, get_day_prayers


def _parse_time_min(time_str: str) -> int | None:
    """Parse clock time like '09:14 AM' or '05:31' into minutes since midnight (0..1439)."""
    if not time_str:
        return None
    for fmt in ("%I:%M %p", "%H:%M"):
        try:
            t = dt.datetime.strptime(time_str.strip(), fmt).time()
            return t.hour * 60 + t.minute
        except ValueError:
            pass
    return None


def _compute_recent_wake_anchor_min(history: list[dict[str, Any]]) -> int | None:
    """Anchor wake-up time (minutes since midnight) from recent normal nights (>=4h sleep)."""
    valid = [
        r for r in history
        if isinstance(r, dict)
        and (r.get("sleep_duration_min") or 0) >= 240
        and r.get("wake_time")
    ][:7]
    wakes = [m for m in (_parse_time_min(r["wake_time"]) for r in valid) if m is not None]
    if not wakes:
        return None
    latest = wakes[0]
    med = round(statistics.median(wakes))
    # Use yesterday's wake time directly unless it was an extreme >2h outlier vs 7-day median
    if abs(latest - med) <= 120:
        return latest
    return med


def build_night_window(
    night_date: dt.date,
    cfg: dict[str, Any],
    cache: dict[str, dict[str, str]],
    wake_anchor_min: int | None,
    tz: ZoneInfo,
) -> dict[str, Any]:
    prayers_tonight = get_day_prayers(night_date, cfg, cache)
    prayers_morning = get_day_prayers(night_date + dt.timedelta(days=1), cfg, cache)

    isha_dt = prayers_tonight["isha"]
    fajr_dt = prayers_morning["fajr"]
    ideal_wake = fajr_dt - dt.timedelta(minutes=int(cfg.get("wake_offset_before_fajr_min", 10)))

    max_shift = int(cfg.get("max_daily_shift_min", 30))
    morning_midnight = dt.datetime.combine(night_date + dt.timedelta(days=1), dt.time(0, 0), tzinfo=tz)

    if wake_anchor_min is None:
        wake_dt = ideal_wake
    else:
        anchor_wake_dt = morning_midnight + dt.timedelta(minutes=wake_anchor_min)
        if anchor_wake_dt <= ideal_wake:
            wake_dt = ideal_wake
        else:
            wake_dt = max(ideal_wake, anchor_wake_dt - dt.timedelta(minutes=max_shift))

    earliest_after_isha = isha_dt + dt.timedelta(minutes=int(cfg.get("isha_wind_down_min", 30)))
    max_sleep = int(cfg.get("max_target_sleep_min", 510))
    pre_lock_min = int(cfg.get("pre_sleep_lock_min", 60))

    ideal_sleep = max(earliest_after_isha, ideal_wake - dt.timedelta(minutes=max_sleep))
    desired_sleep = max(earliest_after_isha, wake_dt - dt.timedelta(minutes=max_sleep))

    ideal_lock_dt = max(earliest_after_isha, ideal_sleep - dt.timedelta(minutes=pre_lock_min))
    lock_dt = max(earliest_after_isha, desired_sleep - dt.timedelta(minutes=pre_lock_min))

    expected_sleep_min = max(0, int((wake_dt - desired_sleep).total_seconds() // 60))
    return {
        "night_of": night_date.strftime("%Y-%m-%d"),
        "isha": isha_dt.replace(microsecond=0).isoformat(),
        "fajr": fajr_dt.replace(microsecond=0).isoformat(),
        "ideal_wake_at": ideal_wake.replace(microsecond=0).isoformat(),
        "wake_at": wake_dt.replace(microsecond=0).isoformat(),
        "ideal_sleep_at": ideal_sleep.replace(microsecond=0).isoformat(),
        "desired_sleep_at": desired_sleep.replace(microsecond=0).isoformat(),
        "ideal_bedtime": ideal_lock_dt.replace(microsecond=0).isoformat(),
        "bedtime": lock_dt.replace(microsecond=0).isoformat(),
        "expected_sleep_min": expected_sleep_min,
        "prayer_source": prayers_morning["source"],
    }


def generate_schedule(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    if cfg is None:
        cfg = load_config()
    tz = ZoneInfo(cfg.get("timezone", "Africa/Casablanca"))
    now = dt.datetime.now(tz)
    cache = ensure_prayer_cache(cfg, days_ahead=30)
    history = load_json(HISTORY_PATH, default=[])
    if not isinstance(history, list):
        history = []

    wake_anchor = _compute_recent_wake_anchor_min(history)

    today = now.date()
    nights: list[dict[str, Any]] = []
    cur_wake_anchor = wake_anchor
    max_shift = int(cfg.get("max_daily_shift_min", 30))

    for offset in range(-1, 10):
        nd = today + dt.timedelta(days=offset)
        w = build_night_window(nd, cfg, cache, cur_wake_anchor, tz)
        nights.append(w)
        if offset >= 0 and cur_wake_anchor is not None:
            wake_dt = dt.datetime.fromisoformat(w["wake_at"])
            ideal_wake_dt = dt.datetime.fromisoformat(w["ideal_wake_at"])
            if wake_dt > ideal_wake_dt:
                cur_wake_anchor = max(0, cur_wake_anchor - max_shift)

    yesterday_win = nights[0]
    tonight_win = nights[1]
    primary = yesterday_win if now < dt.datetime.fromisoformat(yesterday_win["wake_at"]) else tonight_win

    wake_dt = dt.datetime.fromisoformat(tonight_win["wake_at"])
    ideal_wake_dt = dt.datetime.fromisoformat(tonight_win["ideal_wake_at"])
    gap_min = max(0, int((wake_dt - ideal_wake_dt).total_seconds() // 60))
    days_to_converge = (gap_min + max_shift - 1) // max_shift if max_shift > 0 and gap_min > 0 else 0

    schedule = {
        "generated_at": now.replace(microsecond=0).isoformat(),
        "timezone": cfg.get("timezone", "Africa/Casablanca"),
        "city": cfg.get("city", "Casablanca"),
        "country": cfg.get("country", "Morocco"),
        "recent_wake_anchor_min": wake_anchor,
        "days_to_converge_est": days_to_converge,
        "emergency": cfg["emergency"],
        "active_window": primary,
        "tonight": tonight_win,
        "nights": nights,
    }
    save_json(SCHEDULE_PATH, schedule)
    return schedule
