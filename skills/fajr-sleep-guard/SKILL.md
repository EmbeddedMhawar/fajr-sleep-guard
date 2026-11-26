---
name: fajr-sleep-guard
description: >-
  Design and deploy an automated, data-driven sleep-consistency and Fajr wake-up
  system across the user's PC and phone. Use when setting up sleep tracking
  ingestion, adaptive Isha-to-Fajr scheduling, pure-black screen-off enforcement
  with 1:1 proportional emergency hold-to-unlock, or Fajr alarm automation on any
  PC OS (Linux, macOS, Windows) and phone OS (Android, iOS).
---

# Fajr Sleep Guard

Set up a complete, platform-adapted sleep-consistency and Fajr wake-up system on the user's actual devices, guided by a clear behavioral contract rather than a single hardcoded OS stack.

## Step 1: Confirm Defaults vs. Custom Rules

Before writing any code, present the recommended contract below and ask the user whether to:
1. **Use the recommended defaults** (can be modified anytime later in `config.json`), or
2. **Customize from scratch** (override any parameter below).

### Recommended Contract (Defaults)
- **Wake Target:** `Fajr - 10 min`, with an auto-scheduled alarm on the phone (and optional PC wake sound).
- **Bedtime Goal (Isha-to-Fajr Maximization):** Maximize sleep between `Isha + 30 min` (prayer & wind-down buffer) and `Fajr - 10 min`, capped at a healthy ceiling (default `8h 30m` before wake target when nights are long in winter). When nights between Isha and Fajr are shorter in summer, bedtime anchors right after Isha so total sleep is maximized.
- **1-Hour Pre-Sleep Screen Lock:** PC and phone lock **1 hour before desired sleep time** (`pre_sleep_lock_min = 60`, never earlier than `Isha + 30 min`) to guarantee a screen-free wind-down hour before sleep onset.
- **Effortless Gradual Shift:** Step target sleep onset earlier by `15–20 min/night` from the user's recent 7-day median sleep onset until converged—never forcing an abrupt multi-hour jump.
- **Pure-Black Single-Button Lock (Phone & PC):** Right when the sleep window begins, both screens go **off / pure black** showing only **one button** for emergency unlock (no nagging popups, clocks, or menus).
- **1:1 Proportional Emergency Unlock:** Holding the single button earns **1 second of unlocked usage per 1 second held** (minimum `3s` hold to ignore accidental taps; **max `10 min`** per hold), **maximum `2` emergency uses per night**. Releasing resets the hold counter and immediately starts the earned countdown; when earned seconds expire, screens lock/turn off again until `Fajr - 10 min`.
- **Exceptions:** Incoming phone calls and the Fajr alarm always ring through.

**Completion criterion:** User has either accepted defaults or specified overrides.

---

## Step 2: Probe the User's Environment

Inspect the machine and ask only what cannot be detected automatically:
1. **PC OS & Display:** Detect Linux (Wayland/Hyprland/Sway/GNOME/KDE or X11), macOS, or Windows, and check brightness/DPMS/lock capabilities.
2. **Phone & Wearable Ecosystem:** Ask/check whether the user runs **Android** or **iOS**, and where sleep data lives (`Zepp Life`, `Health Connect`, `Apple Health`, `Garmin`, `Fitbit`, `Oura`, or manual/screen-time inference).
3. **Location & Prayer Method:** Detect timezone/city (confirm with user) and select the appropriate prayer calculation method (e.g., `Method 21` Morocco Habous, `ISNA`, `MWL`, `Umm al-Qura`, `Egyptian`, etc.).

**Completion criterion:** Exact PC adapter, Phone adapter, Sleep source, and City/Method are identified.

---

## Step 3: Load the Algorithm & Platform Recipes

Read the disclosed reference files before implementing:
- Scheduling math, prayer-time caching, and `config.json` schema: [`references/algorithm.md`](references/algorithm.md)
- Per-platform lock/brightness/alarm/sleep-sync patterns: [`references/platform-adapters.md`](references/platform-adapters.md)

If the user is on **Omarchy/Hyprland + Android + Zepp Life**, inspect the working reference implementation under `../../reference-omarchy-android/` and reuse or adapt it directly.

**Completion criterion:** Both reference specs are loaded for the chosen platforms.

---

## Step 4: Implement & Deploy

Build four cleanly separated components for the user's platforms:
1. **Sleep Data Collector:** Pulls recent sleep history (90-day seed if available, then daily delta sync) into normalized JSON (`date`, `bedtime`, `wake_time`, `sleep_duration_min`, `sleep_score`).
2. **Adaptive Fajr Scheduler:** Computes daily `isha`, `fajr`, `wake_at`, and `bedtime` using `references/algorithm.md`, caches 30 days of prayer times locally (plus astronomical fallback), and writes `schedule.json` + `config.json`.
3. **PC Lock Guard:** Background service (`systemd --user` / `launchd` / Task Scheduler) that turns brightness to `0` (or DPMS off) at `bedtime`, traps wake/input on a pure-black fullscreen overlay with the single 1:1 proportional hold button (max `10 min`, `2` uses/night), and restores brightness at `wake_at`.
4. **Phone Lock & Fajr Alarm:** Native app or OS automation enforcing the same pure-black single-button 1:1 proportional lock, syncing `schedule.json` (with standalone offline prayer calculation fallback), and scheduling the `Fajr - 10 min` alarm.

**Completion criterion:** Scheduler generates valid tonight/tomorrow windows from real sleep data + prayer times, daily sync automation is registered, and both PC and phone locks are verified in a live test (including 1:1 proportional hold, 2-use limit, and screen-off).
