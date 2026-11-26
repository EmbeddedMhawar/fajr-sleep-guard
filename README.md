# Fajr Sleep Guard

An agent-driven sleep-consistency and Fajr wake-up system designed as a **portable Skill** (`skills/fajr-sleep-guard/`) so anyone—regardless of OS, phone, or sleep tracker—can have their coding agent build and configure it for their exact environment.

## For Viewers (Any OS / Phone / Wearable)

Give `skills/fajr-sleep-guard/SKILL.md` to your AI coding agent (Antigravity, Claude Code, Codex, etc.).

1. **Defaults or Custom:** The agent presents the system defaults (modifiable anytime via `config.json`) or lets you customize from scratch:
   - **Wake target:** `Fajr - 10 min` with auto-scheduled alarm.
   - **Bedtime goal:** Maximize sleep between `Isha + 30 min` and `Fajr - 10 min`, stepping earlier gradually (`15–20 min/night`) from your recent sleep data.
   - **Pure-black single-button lock (PC & Phone):** At bedtime, screens go off / pure black with one button.
   - **1:1 proportional emergency unlock:** Holding the button earns 1 second of usage per 1 second held (3s min, 10 min max), up to **2 uses per night**.
2. **Environment Probe:** Your agent detects your PC OS (Linux, macOS, Windows), phone OS (Android, iOS), sleep tracker (Zepp Life, Health Connect, Apple Health, Garmin, etc.), and city/prayer method, then generates and installs the matching adapters.

## Reference Implementation (`reference-omarchy-android/`)

Includes a complete working implementation for **Omarchy / Hyprland (`brightnessctl` + `gtk4-layer-shell`)** + **Android (`com.mhawar.fajrsleepguard`)** + **Zepp Life ADB sync**:

- `bin/fajr-sleep-sync`: Pulls delta sleep history via `adb-wifi-ensure`, updates `schedule.json`, and pushes it to Android.
- `bin/fajr-sleep-guard`: Pure-black fullscreen Wayland overlay + `brightnessctl set 0` daemon (`systemd --user`).
- `bin/fajr-sleep-status`: Shows tonight's Isha/Bedtime/Wake/Fajr window and emergency state.
- `reference-omarchy-android/android-app/`: Native Android APK enforcing pure-black screen-off lock, 1:1 proportional hold, and `Fajr - 10 min` wake alarm.
