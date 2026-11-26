"""Configuration and state persistence for Fajr Sleep Guard."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DATA_DIR = Path(os.environ.get("FAJR_SLEEP_DATA_DIR", Path.home() / ".local/share/fajr-sleep-guard"))
CONFIG_PATH = DATA_DIR / "config.json"
HISTORY_PATH = DATA_DIR / "sleep_history.json"
PRAYER_CACHE_PATH = DATA_DIR / "prayer_cache.json"
SCHEDULE_PATH = DATA_DIR / "schedule.json"
GUARD_STATE_PATH = DATA_DIR / "guard_state.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "city": "Casablanca",
    "country": "Morocco",
    "latitude": 33.5883,
    "longitude": -7.6114,
    "timezone": "Africa/Casablanca",
    "prayer_method": 21,
    "wake_offset_before_fajr_min": 10,
    "isha_wind_down_min": 30,
    "pre_sleep_lock_min": 60,     # lock screens 1 hour before desired sleep time
    "max_target_sleep_min": 510,  # 8h 30m ceiling when night is long
    "min_target_sleep_min": 360,  # 6h floor
    "max_daily_shift_min": 20,    # gradual step earlier per night
    "adb_serial": "any",
    "android_package": "com.mhawar.fajrsleepguard",
    "emergency": {
        "ratio": 1.0,
        "min_hold_sec": 3,
        "max_grant_sec": 600,     # 10 min max
        "max_uses_per_night": 2,
    },
}


def ensure_data_dir() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, payload: Any) -> None:
    ensure_data_dir()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def load_config() -> dict[str, Any]:
    ensure_data_dir()
    cfg = load_json(CONFIG_PATH)
    if not isinstance(cfg, dict):
        save_json(CONFIG_PATH, DEFAULT_CONFIG)
        return dict(DEFAULT_CONFIG)
    merged = dict(DEFAULT_CONFIG)
    merged.update(cfg)
    if isinstance(cfg.get("emergency"), dict):
        em = dict(DEFAULT_CONFIG["emergency"])
        em.update(cfg["emergency"])
        merged["emergency"] = em
    return merged
