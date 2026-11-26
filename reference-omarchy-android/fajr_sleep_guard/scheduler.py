"""Adaptive Isha-to-Fajr sleep scheduler."""

from __future__ import annotations

import datetime as dt
import statistics
from typing import Any
from zoneinfo import ZoneInfo

from .config import HISTORY_PATH, SCHEDULE_PATH, load_config, load_json, save_json
from .prayer import ensure_prayer_cache, get_day_prayers


def _parse_bedtime_rel_min(bed_str: str) -> int | None:
    """Minutes relative to midnight: 22:30 -> -90, 01:59 AM -> +119."""
    if not bed_str:
        return None
    for fmt in ("%I:%M %p", "%H:%M"):
        try:
            t = dt.datetime.strptime(bed_str.strip(), fmt).time()
            mins = t.hour * 60 + t.minute
            # Afternoon/evening (15:00..23:59) is before midnight -> negative offset
            return mins - 1440 if mins >= 15 * 60 else mins
        except ValueError:
            pass
    return None


def _compute_recent_anchor_rel_min(history: list[dict[str, Any]]) -> int | None:
    valid = [
        r for r in history
        if isinstance(r, dict) and (r.get("sleep_duration_min") or 0) > 0 and r.get("bedtime")
    ][:7]
    rels = [m for m in (_parse_bedtime_rel_min(r["bedtime"]) for r in valid) if m is not None]
    if not rels:
        return None
    med = round(statistics.median(rels))
    # Reward if yesterday was already earlier than the 7-day median
    latest = rels[0]
    if latest < med:
        return latest
    return med


def build_night_window(
    night_date: dt.date,
    cfg: dict[str, Any],
    cache: dict[str, dict[str, str]],
    anchor_rel_min: int | None,
    tz: ZoneInfo,
) -> dict[str, Any]:
    prayers_tonight = get_day_prayers(night_date, cfg, cache)
    prayers_morning = get_day_prayers(night_date + dt.timedelta(days=1), cfg, cache)

    isha_dt = prayers_tonight["isha"]
    fajr_dt = prayers_morning["fajr"]
    wake_dt = fajr_dt - dt.timedelta(minutes=int(cfg.get("wake_offset_before_fajr_min", 10)))

    earliest_after_isha = isha_dt + dt.timedelta(minutes=int(cfg.get("isha_wind_down_min", 30)))
    ceiling_sleep = wake_dt - dt.timedelta(minutes=int(cfg.get("max_target_sleep_min", 510)))
    ideal_sleep = max(earliest_after_isha, ceiling_sleep)

    max_shift = int(cfg.get("max_daily_shift_min", 20))
    if anchor_rel_min is None:
        desired_sleep = ideal_sleep
    else:
        midnight_next = dt.datetime.combine(night_date + dt.timedelta(days=1), dt.time(0, 0), tzinfo=tz)
        anchor_dt = midnight_next + dt.timedelta(minutes=anchor_rel_min)
        if anchor_dt <= ideal_sleep:
            desired_sleep = ideal_sleep
        else:
            desired_sleep = max(ideal_sleep, anchor_dt - dt.timedelta(minutes=max_shift))

    pre_lock_min = int(cfg.get("pre_sleep_lock_min", 60))
    lock_dt = max(earliest_after_isha, desired_sleep - dt.timedelta(minutes=pre_lock_min))
    ideal_lock_dt = max(earliest_after_isha, ideal_sleep - dt.timedelta(minutes=pre_lock_min))

    expected_sleep_min = max(0, int((wake_dt - desired_sleep).total_seconds() // 60))
    return {
        "night_of": night_date.strftime("%Y-%m-%d"),
        "isha": isha_dt.replace(microsecond=0).isoformat(),
        "fajr": fajr_dt.replace(microsecond=0).isoformat(),
        "ideal_sleep_at": ideal_sleep.replace(microsecond=0).isoformat(),
        "desired_sleep_at": desired_sleep.replace(microsecond=0).isoformat(),
        "ideal_bedtime": ideal_lock_dt.replace(microsecond=0).isoformat(),
        "bedtime": lock_dt.replace(microsecond=0).isoformat(),
        "wake_at": wake_dt.replace(microsecond=0).isoformat(),
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

    anchor_rel = _compute_recent_anchor_rel_min(history)

    # Determine active night: if we are before today's wake_at, keep yesterday's night active too
    today = now.date()
    nights: list[dict[str, Any]] = []
    cur_anchor = anchor_rel
    max_shift = int(cfg.get("max_daily_shift_min", 20))

    for offset in range(-1, 7):
        nd = today + dt.timedelta(days=offset)
        w = build_night_window(nd, cfg, cache, cur_anchor, tz)
        nights.append(w)
        if offset >= 0 and cur_anchor is not None:
            # Project gradual shift forward across upcoming 7 offline days
            sleep_dt = dt.datetime.fromisoformat(w["desired_sleep_at"])
            ideal_dt = dt.datetime.fromisoformat(w["ideal_sleep_at"])
            if sleep_dt > ideal_dt:
                cur_anchor -= max_shift

    # Active primary window: yesterday's night if now < yesterday's wake_at, else tonight
    yesterday_win = nights[0]
    tonight_win = nights[1]
    primary = yesterday_win if now < dt.datetime.fromisoformat(yesterday_win["wake_at"]) else tonight_win

    sleep_dt = dt.datetime.fromisoformat(tonight_win["desired_sleep_at"])
    ideal_dt = dt.datetime.fromisoformat(tonight_win["ideal_sleep_at"])
    gap_min = max(0, int((sleep_dt - ideal_dt).total_seconds() // 60))
    days_to_converge = (gap_min + max_shift - 1) // max_shift if max_shift > 0 and gap_min > 0 else 0

    schedule = {
        "generated_at": now.replace(microsecond=0).isoformat(),
        "timezone": cfg.get("timezone", "Africa/Casablanca"),
        "city": cfg.get("city", "Casablanca"),
        "country": cfg.get("country", "Morocco"),
        "recent_anchor_bedtime_rel_min": anchor_rel,
        "days_to_converge_est": days_to_converge,
        "emergency": cfg["emergency"],
        "active_window": primary,
        "tonight": tonight_win,
        "nights": nights,
    }
    save_json(SCHEDULE_PATH, schedule)
    return schedule
