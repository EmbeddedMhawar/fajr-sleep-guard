# Adaptive Isha-to-Fajr Scheduling Algorithm

## 1. Configuration Schema (`config.json`)

```json
{
  "city": "Casablanca",
  "country": "Morocco",
  "latitude": 33.5731,
  "longitude": -7.5898,
  "timezone": "Africa/Casablanca",
  "prayer_method": 21,
  "wake_offset_before_fajr_min": 10,
  "isha_wind_down_min": 30,
  "pre_sleep_lock_min": 60,
  "max_target_sleep_min": 510,
  "min_target_sleep_min": 360,
  "max_daily_shift_min": 20,
  "emergency": {
    "ratio": 1.0,
    "min_hold_sec": 3,
    "max_grant_sec": 600,
    "max_uses_per_night": 2
  }
}
```

Every parameter above is editable anytime in `config.json`.

---

## 2. Daily Prayer Time Resolution

1. Fetch 30 days ahead from the Aladhan API (`https://api.aladhan.com/v1/calendarByCity/{year}/{month}?city=...&country=...&method={prayer_method}`) and store in `prayer_cache.json`.
2. Refresh cache whenever `< 7` future days remain.
3. **Offline fallback:** If network is unavailable and a date is missing from `prayer_cache.json`, compute `Fajr` and `Isha` locally using solar declination / equation-of-time astronomical formulas for `(latitude, longitude)` and the configured twilight angles (e.g., Morocco Habous Method 21: Fajr `19°`, Isha `17°`).

---

## 3. Computing Tonight's Window

Given tonight's `isha_dt` and tomorrow morning's `fajr_dt`:

1. **Target Wake Time:**
   `wake_dt = fajr_dt - timedelta(minutes=wake_offset_before_fajr_min)`
2. **Ideal Bedtime (Maximize Isha-to-Fajr Sleep):**
   - Earliest realistic bedtime: `earliest_bed = isha_dt + timedelta(minutes=isha_wind_down_min)`
   - Desired ceiling bedtime: `ceiling_bed = wake_dt - timedelta(minutes=max_target_sleep_min)`
   - `ideal_bed = max(earliest_bed, ceiling_bed)`
   *(In winter, `ceiling_bed` is later than `earliest_bed`, giving up to `max_target_sleep_min` e.g. 8h30m before `Fajr - 10m`. In summer, `earliest_bed` is later, so you sleep right after Isha to capture every available minute before Fajr.)*
3. **Adaptive Gradual Shift (from Zepp / Sleep Data):**
   - Take the last `7` nights with valid `sleep_duration_min > 0` from `sleep_history.json`.
   - Convert each night's `bedtime` to minutes relative to midnight (e.g., `23:30` = `-30`, `01:30` = `+90`) and compute the **median** (`recent_median_bed`).
   - Also compute the **weighted baseline** if the user slept slightly earlier yesterday (`yesterday_bed`).
   - Anchor `current_anchor = min(recent_median_bed, yesterday_bed)` when improving, or `recent_median_bed` if erratic, clamped so we never shift *later* than `recent_median_bed` and never shift *earlier* faster than `max_daily_shift_min` (`20 min/night`) from yesterday's target/actual:
     - If `current_anchor <= ideal_bed`: `desired_sleep = ideal_bed` (already converged!).
     - Else: `desired_sleep = max(ideal_bed, current_anchor - max_daily_shift_min)`.
4. **1-Hour Pre-Sleep Lock Time (`bedtime` / `lock_at`):**
   - `lock_at = max(earliest_bed, desired_sleep - timedelta(minutes=pre_sleep_lock_min))` (locks screens **1 hour before desired sleep time**, never earlier than `Isha + 30 min`).
5. **Output (`schedule.json`):**
   ```json
   {
     "generated_at": "2026-11-26T13:10:00+01:00",
     "night_of": "2026-11-26",
     "isha": "2026-11-26T19:22:00+01:00",
     "fajr": "2026-11-27T06:41:00+01:00",
     "bedtime": "2026-11-26T23:39:00+01:00",
     "ideal_bedtime": "2026-11-26T22:01:00+01:00",
     "wake_at": "2026-11-27T06:31:00+01:00",
     "expected_sleep_min": 412,
     "days_to_converge_est": 5,
     "upcoming_7d": [...]
   }
   ```
   Including `upcoming_7d` lets the PC and Phone operate autonomously for up to a week even if sync is offline.

---

## 4. 1:1 Proportional Emergency Hold State Machine

Shared identically by PC and Phone adapters:
- **State per night (`night_of`):** `uses_remaining = 2` (reset when transitioning past `wake_at`), `unlocked_until = null`.
- **Locked state** (`now in [bedtime, wake_at)` and `(unlocked_until is null or now >= unlocked_until)`):
  - Screen is off / pure black (`brightness = 0` or `lockNow()`).
  - If `uses_remaining == 0`: button is disabled (pure black screen; on PC brightness returns to `0` within `2s`).
  - If `uses_remaining > 0`: holding the single button starts `hold_ms` timer (`min_hold_sec = 3s`, `max_grant_sec = 600s`).
    - On release (or reaching `600s`):
      - If `hold_sec < min_hold_sec`: reset `hold_sec = 0`, do NOT consume a use, turn screen off.
      - Else: `grant = min(int(hold_sec), 600)`, `uses_remaining -= 1`, `unlocked_until = now + grant`, dismiss lock overlay / restore normal brightness.
- **When `unlocked_until` expires** (and still `< wake_at`): immediately re-lock and turn screen off/black.
- **When `now >= wake_at`**: end sleep lock, restore brightness, fire Fajr alarm (phone).
