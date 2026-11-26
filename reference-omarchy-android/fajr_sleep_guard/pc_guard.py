"""Hyprland / Wayland GTK4 Layer-Shell pure-black lock guard with 1:1 proportional hold."""

from __future__ import annotations

import ctypes
import datetime as dt
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ctypes.CDLL("libgtk4-layer-shell.so")
import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gdk, GLib, Gtk, Gtk4LayerShell  # noqa: E402

from .config import GUARD_STATE_PATH, SCHEDULE_PATH, load_config, load_json, save_json  # noqa: E402
from .scheduler import generate_schedule  # noqa: E402

CSS = b"""
window, .lock-root {
    background-color: #000000;
}
button.emergency-btn {
    background-color: #0a0a0a;
    color: #555555;
    border: 1px solid #1f1f1f;
    border-radius: 999px;
    padding: 20px 36px;
    font-size: 16px;
    font-weight: 500;
    min-width: 240px;
    min-height: 72px;
    box-shadow: none;
}
button.emergency-btn:hover {
    background-color: #111111;
    color: #777777;
    border-color: #2e2e2e;
}
button.emergency-btn.holding {
    background-color: #161616;
    color: #cccccc;
    border-color: #555555;
}
button.emergency-btn:disabled {
    background-color: #000000;
    color: #151515;
    border-color: #0d0d0d;
}
"""


def _brightness_get() -> int | None:
    try:
        r = subprocess.run(["brightnessctl", "get"], capture_output=True, text=True, timeout=3)
        if r.returncode == 0:
            return int(r.stdout.strip())
    except Exception:
        pass
    return None


def _brightness_max() -> int:
    try:
        r = subprocess.run(["brightnessctl", "max"], capture_output=True, text=True, timeout=3)
        if r.returncode == 0:
            return max(1, int(r.stdout.strip()))
    except Exception:
        pass
    return 100


def _brightness_set(value: str | int) -> None:
    try:
        subprocess.run(["brightnessctl", "-q", "set", str(value)], check=False, timeout=3)
    except Exception:
        pass


class SleepLockDaemon:
    def __init__(self, app: Gtk.Application, test_seconds: int = 0) -> None:
        self.app = app
        self.test_seconds = test_seconds
        self.test_end_mono = time.monotonic() + test_seconds if test_seconds > 0 else 0.0
        self.windows: list[Gtk.Window] = []
        self.buttons: list[Gtk.Button] = []

        self.is_locked = False
        self.saved_brightness: int | None = None
        self.last_peek_mono = 0.0
        self.holding = False
        self.hold_start_mono = 0.0
        self.peek_brightness_pct = "8%"

        self._load_css()
        self._ensure_schedule()
        GLib.timeout_add(200, self._tick)

    def _load_css(self) -> None:
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        display = Gdk.Display.get_default()
        if display:
            Gtk.StyleContext.add_provider_for_display(
                display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

    def _ensure_schedule(self) -> dict[str, Any]:
        sched = load_json(SCHEDULE_PATH)
        if not isinstance(sched, dict) or not sched.get("nights"):
            sched = generate_schedule(load_config())
        return sched

    def _load_guard_state(self, night_of: str, max_uses: int) -> dict[str, Any]:
        st = load_json(GUARD_STATE_PATH, default={})
        if not isinstance(st, dict) or st.get("night_of") != night_of:
            st = {
                "night_of": night_of,
                "uses_remaining": max_uses,
                "unlocked_until": None,
                "saved_brightness": None,
            }
            save_json(GUARD_STATE_PATH, st)
        return st

    def _active_window_bounds(self, sched: dict[str, Any], now: dt.datetime) -> dict[str, Any] | None:
        if self.test_seconds > 0 and time.monotonic() < self.test_end_mono:
            return {
                "night_of": f"test-{now.strftime('%Y-%m-%d')}",
                "bedtime": (now - dt.timedelta(minutes=1)).isoformat(),
                "wake_at": (now + dt.timedelta(seconds=self.test_seconds)).isoformat(),
            }
        for w in sched.get("nights", []):
            bed = dt.datetime.fromisoformat(w["bedtime"])
            wake = dt.datetime.fromisoformat(w["wake_at"])
            if bed <= now < wake:
                return w
        return None

    def _build_windows(self) -> None:
        self._destroy_windows()
        display = Gdk.Display.get_default()
        monitors = display.get_monitors() if display else None
        n = monitors.get_n_items() if monitors else 1

        for idx in range(max(1, n)):
            win = Gtk.Window(application=self.app)
            win.set_decorated(False)
            win.add_css_class("lock-root")

            Gtk4LayerShell.init_for_window(win)
            Gtk4LayerShell.set_namespace(win, "fajr-sleep-guard")
            Gtk4LayerShell.set_layer(win, Gtk4LayerShell.Layer.OVERLAY)
            Gtk4LayerShell.set_keyboard_mode(win, Gtk4LayerShell.KeyboardMode.EXCLUSIVE)
            Gtk4LayerShell.set_exclusive_zone(win, -1)
            for edge in (
                Gtk4LayerShell.Edge.TOP,
                Gtk4LayerShell.Edge.BOTTOM,
                Gtk4LayerShell.Edge.LEFT,
                Gtk4LayerShell.Edge.RIGHT,
            ):
                Gtk4LayerShell.set_anchor(win, edge, True)
            if monitors and idx < monitors.get_n_items():
                Gtk4LayerShell.set_monitor(win, monitors.get_item(idx))

            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            box.set_valign(Gtk.Align.CENTER)
            box.set_halign(Gtk.Align.CENTER)
            box.add_css_class("lock-root")

            btn = Gtk.Button(label="Hold for Emergency")
            btn.add_css_class("emergency-btn")
            btn.set_focusable(True)

            gesture = Gtk.GestureClick.new()
            gesture.connect("pressed", self._on_hold_start)
            gesture.connect("released", self._on_hold_end)
            gesture.connect("stopped", self._on_hold_end)
            btn.add_controller(gesture)

            # Wake brightness minimally when user touches/moves/presses key on overlay
            motion = Gtk.EventControllerMotion.new()
            motion.connect("motion", self._on_user_activity)
            win.add_controller(motion)

            key_ctrl = Gtk.EventControllerKey.new()
            key_ctrl.connect("key-pressed", self._on_key_pressed)
            key_ctrl.connect("key-released", self._on_key_released)
            win.add_controller(key_ctrl)

            box.append(btn)
            win.set_child(box)
            win.present()
            self.windows.append(win)
            self.buttons.append(btn)

    def _destroy_windows(self) -> None:
        for w in self.windows:
            try:
                w.close()
                w.destroy()
            except Exception:
                pass
        self.windows.clear()
        self.buttons.clear()

    def _on_user_activity(self, *_args: Any) -> None:
        if not self.is_locked:
            return
        sched = self._ensure_schedule()
        em = sched.get("emergency", {})
        tz = ZoneInfo(sched.get("timezone", "Africa/Casablanca"))
        now = dt.datetime.now(tz)
        win_info = self._active_window_bounds(sched, now)
        if not win_info:
            return
        st = self._load_guard_state(win_info["night_of"], int(em.get("max_uses_per_night", 2)))
        if st.get("uses_remaining", 0) <= 0:
            return
        now_m = time.monotonic()
        if now_m - self.last_peek_mono > 1.0:
            _brightness_set(self.peek_brightness_pct)
        self.last_peek_mono = now_m

    def _on_key_pressed(self, _ctrl: Any, keyval: int, _keycode: int, _state: Any) -> bool:
        self._on_user_activity()
        if keyval in (Gdk.KEY_space, Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if not self.holding:
                self._on_hold_start()
            return True
        return True  # Swallow all other shortcuts/keys while locked

    def _on_key_released(self, _ctrl: Any, keyval: int, _keycode: int, _state: Any) -> None:
        if keyval in (Gdk.KEY_space, Gdk.KEY_Return, Gdk.KEY_KP_Enter) and self.holding:
            self._on_hold_end()

    def _on_hold_start(self, *_args: Any) -> None:
        sched = self._ensure_schedule()
        em = sched.get("emergency", {})
        tz = ZoneInfo(sched.get("timezone", "Africa/Casablanca"))
        now = dt.datetime.now(tz)
        win_info = self._active_window_bounds(sched, now)
        if not win_info:
            return
        st = self._load_guard_state(win_info["night_of"], int(em.get("max_uses_per_night", 2)))
        if st.get("uses_remaining", 0) <= 0:
            return
        if not self.holding:
            self.holding = True
            self.hold_start_mono = time.monotonic()
            self.last_peek_mono = self.hold_start_mono
            _brightness_set(self.peek_brightness_pct)
            for b in self.buttons:
                b.add_css_class("holding")

    def _on_hold_end(self, *_args: Any) -> None:
        if not self.holding:
            return
        self.holding = False
        held_sec = time.monotonic() - self.hold_start_mono
        for b in self.buttons:
            b.remove_css_class("holding")
            b.set_label("Hold for Emergency")

        sched = self._ensure_schedule()
        em = sched.get("emergency", {})
        min_hold = float(em.get("min_hold_sec", 3))
        max_grant = int(em.get("max_grant_sec", 600))
        ratio = float(em.get("ratio", 1.0))

        if held_sec < min_hold:
            self.last_peek_mono = time.monotonic()
            return

        tz = ZoneInfo(sched.get("timezone", "Africa/Casablanca"))
        now = dt.datetime.now(tz)
        win_info = self._active_window_bounds(sched, now)
        if not win_info:
            return
        st = self._load_guard_state(win_info["night_of"], int(em.get("max_uses_per_night", 2)))
        if st.get("uses_remaining", 0) <= 0:
            return

        grant_sec = min(max_grant, max(1, int(round(held_sec * ratio))))
        st["uses_remaining"] = max(0, int(st["uses_remaining"]) - 1)
        st["unlocked_until"] = (now + dt.timedelta(seconds=grant_sec)).isoformat()
        save_json(GUARD_STATE_PATH, st)
        self._exit_lock()

    def _enter_lock(self, st: dict[str, Any]) -> None:
        if self.is_locked:
            return
        cur = _brightness_get()
        if cur is not None and cur > 0:
            self.saved_brightness = cur
            st["saved_brightness"] = cur
            save_json(GUARD_STATE_PATH, st)
        elif st.get("saved_brightness"):
            self.saved_brightness = int(st["saved_brightness"])
        else:
            self.saved_brightness = int(_brightness_max() * 0.6)

        self.is_locked = True
        self.holding = False
        self.last_peek_mono = 0.0
        _brightness_set(0)
        self._build_windows()

    def _exit_lock(self) -> None:
        if not self.is_locked:
            return
        self.is_locked = False
        self.holding = False
        self._destroy_windows()
        restore = self.saved_brightness
        if restore is None or restore <= 0:
            restore = int(_brightness_max() * 0.6)
        _brightness_set(restore)

    def _tick(self) -> bool:
        try:
            sched = self._ensure_schedule()
            tz = ZoneInfo(sched.get("timezone", "Africa/Casablanca"))
            now = dt.datetime.now(tz)
            em = sched.get("emergency", {})
            max_uses = int(em.get("max_uses_per_night", 2))
            max_grant = int(em.get("max_grant_sec", 600))

            win_info = self._active_window_bounds(sched, now)
            if not win_info:
                if self.is_locked:
                    self._exit_lock()
                if self.test_seconds > 0 and time.monotonic() >= self.test_end_mono:
                    self.app.quit()
                    return False
                return True

            st = self._load_guard_state(win_info["night_of"], max_uses)
            unlocked_until_raw = st.get("unlocked_until")
            in_emergency = False
            if unlocked_until_raw:
                try:
                    in_emergency = now < dt.datetime.fromisoformat(unlocked_until_raw)
                except ValueError:
                    in_emergency = False

            if in_emergency:
                if self.is_locked:
                    self._exit_lock()
                return True

            if not self.is_locked:
                self._enter_lock(st)

            uses_left = int(st.get("uses_remaining", 0))
            if self.holding:
                held = time.monotonic() - self.hold_start_mono
                if held >= max_grant:
                    self._on_hold_end()
                    return True
                mm, ss = divmod(int(held), 60)
                cap_m, cap_s = divmod(max_grant, 60)
                label = f"{mm}:{ss:02d} / {cap_m}:{cap_s:02d}"
                for b in self.buttons:
                    b.set_sensitive(True)
                    b.set_label(label)
            else:
                for b in self.buttons:
                    b.set_sensitive(uses_left > 0)
                    b.set_label("Hold for Emergency" if uses_left > 0 else "")
                # Turn brightness back to 0 after 4s idle or immediately if 0 uses left
                if uses_left <= 0 or (time.monotonic() - self.last_peek_mono > 4.0):
                    cur_b = _brightness_get()
                    if cur_b is None or cur_b > 0:
                        _brightness_set(0)
        except Exception as exc:
            print(f"[pc_guard] tick error: {exc}", file=sys.stderr)
        return True


def run_guard(test_seconds: int = 0) -> int:
    app = Gtk.Application(application_id="com.mhawar.fajrsleepguard.pc")
    daemon_holder: list[SleepLockDaemon] = []

    def on_activate(a: Gtk.Application) -> None:
        if not daemon_holder:
            a.hold()  # Keep daemon alive even with zero visible windows during daytime
            daemon_holder.append(SleepLockDaemon(a, test_seconds=test_seconds))

    app.connect("activate", on_activate)
    return app.run(None)
