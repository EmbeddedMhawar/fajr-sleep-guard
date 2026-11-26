# Platform Adapter Recipes

Use the adapter matching the user's detected environment while keeping the `schedule.json` and 1:1 emergency hold contract identical.

## A. Sleep Data Collectors

1. **Android + Zepp Life (`com.xiaomi.hm.health`):**
   - Connect via `adb` (or `adb-wifi-ensure`).
   - Open `ChannelMainTabActivity` → Sleep card → Day view (`sleepSwitchDateTime`), swipe left-to-right across the header to step backward day-by-day, parse `uiautomator dump` XML.
   - Delta sync stops as soon as `date` already exists in `sleep_history.json` (with 2-day overlap to refresh today/yesterday).
2. **Android + Health Connect:**
   - Companion Android app requests `READ_SLEEP` permission via `HealthConnectClient` and reads `SleepSessionRecord` directly on-device.
3. **iPhone + Apple Health / Apple Watch:**
   - Apple Shortcuts automation ("When waking up / daily at 9 AM") exports the last 7 days of Health Sleep Samples to iCloud Drive / local HTTP endpoint / Pushcut, OR a minimal SwiftUI companion app reads `HKCategoryTypeIdentifier.sleepAnalysis` via HealthKit.
4. **Garmin / Fitbit / Oura / Whoop:**
   - Pull sleep sessions via their official REST API or OAuth token on the PC scheduler and normalize to `sleep_history.json`.
5. **No wearable (Manual / Screen-Time Fallback):**
   - Infer last sleep onset/wake from PC/Phone last-lock & first-unlock timestamps, or prompt once daily.

---

## B. PC Screen-Off & Lock Adapters

| Platform | Screen-Off Mechanism | Pure-Black Single-Button Overlay |
|---|---|---|
| **Linux (Hyprland / wlroots Wayland)** | `brightnessctl set 0` (backlights) and/or `hyprctl dispatch dpms off` | `gtk4` + `gtk4-layer-shell` (`Layer.OVERLAY`, `KeyboardMode.EXCLUSIVE`, all monitors). Briefly raise brightness minimally (e.g. `5%`) only on input for `3s`, dropping back to `0` if button is not held. |
| **Linux (GNOME / KDE / X11)** | `brightnessctl set 0` or `xset dpms force off` / D-Bus screen blank | Fullscreen `always-on-top` undecorated GTK4/Qt window grabbing keyboard/pointer + `systemd --user` watchdog. |
| **macOS** | `pmset displaysleepnow` / CoreGraphics `CGDisplaySetBrightness` / `brightness` CLI | Fullscreen SwiftUI / AppKit `NSWindow` at `CGShieldingWindowLevel()` covering all `NSScreen.screens` (`launchd` `KeepAlive` agent). |
| **Windows** | `SendMessage(HWND_BROADCAST, WM_SYSCOMMAND, SC_MONITORPOWER, 2)` + WMI `WmiSetMonitorBrightness(0)` | Fullscreen topmost borderless WinUI/WPF/Tkinter window with low-level keyboard hook blocking `Alt+Tab`/`Win` (Scheduled Task / service). |

---

## C. Phone Lock & Fajr Alarm Adapters

1. **Android (Native Kotlin/Java Companion App):**
   - **Screen-off & Lock:** `DevicePolicyManager.lockNow()` (Device Admin) or `AccessibilityService.performGlobalAction(GLOBAL_ACTION_LOCK_SCREEN)`.
   - **Pure-black overlay:** Fullscreen `TYPE_ACCESSIBILITY_OVERLAY` or `SHOW_WHEN_LOCKED` Activity with `0xFF000000` background and one centered hold button. Blocks leaving to Home/Recents/Settings during active sleep window; exempts `TelecomManager` active calls and the alarm Activity.
   - **Fajr Alarm:** `AlarmManager.setAlarmClock()` scheduled at `wake_at` (`Fajr - 10 min`) from synced `schedule.json` (plus built-in offline astronomical fallback).
2. **iOS (iPhone):**
   - Note iOS sandbox limits: apps cannot forcibly turn off the screen like Android `DevicePolicyManager`. Implement via **Screen Time / FamilyControls (`ManagedSettings` + `DeviceActivitySchedule`)** shielding all distracting app categories during `[bedtime, wake_at)` combined with a **Guided Access / Focus Mode** automation + `UNNotificationRequest` / AlarmKit at `Fajr - 10 min`, OR a SwiftUI app implementing the 1:1 hold-to-unshield `ManagedSettingsStore` flow.
