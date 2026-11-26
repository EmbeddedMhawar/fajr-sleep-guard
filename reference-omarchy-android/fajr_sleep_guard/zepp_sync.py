"""Zepp Life ADB delta sleep collector."""

from __future__ import annotations

import datetime as dt
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from .config import HISTORY_PATH, load_json, save_json


def _clean_str(s: str) -> str:
    return re.sub(r"[\s\xa0\u202f]+", " ", s or "").strip()


def _parse_duration_minutes(text: str) -> int | None:
    if not text:
        return None
    s = _clean_str(text)
    if s in ("--", "-", ""):
        return None
    mh = re.search(r"(\d+)\s*h", s, re.I)
    mm = re.search(r"(\d+)\s*m", s, re.I)
    if mh or mm:
        return (int(mh.group(1)) if mh else 0) * 60 + (int(mm.group(1)) if mm else 0)
    return None


def _parse_desc_list(desc: str) -> str:
    if not desc:
        return ""
    s = desc.strip()
    if s.startswith("[") and s.endswith("]"):
        s = s[1:-1]
    return _clean_str(" ".join(_clean_str(p) for p in s.split(",") if _clean_str(p)))


def parse_sleep_xml(xml_str: str) -> dict[str, Any]:
    idx = xml_str.find("<?xml")
    if idx == -1:
        raise ValueError("No XML found in uiautomator dump")
    root = ET.fromstring(xml_str[idx:])
    nodes = list(root.iter("node"))
    by_id: dict[str, list[ET.Element]] = {}
    for el in nodes:
        rid = el.attrib.get("resource-id", "").split("/")[-1]
        if rid:
            by_id.setdefault(rid, []).append(el)

    def get_text(rid: str) -> str:
        els = by_id.get(rid, [])
        return _clean_str(els[0].attrib.get("text", "")) if els else ""

    def get_desc(rid: str) -> str:
        els = by_id.get(rid, [])
        return _clean_str(els[0].attrib.get("content-desc", "")) if els else ""

    raw_date = get_text("sleepSwitchDateTime")
    iso_date = ""
    if raw_date:
        for fmt in ("%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d"):
            try:
                iso_date = dt.datetime.strptime(raw_date, fmt).strftime("%Y-%m-%d")
                break
            except ValueError:
                pass

    score_raw = _parse_desc_list(get_desc("chart_up_title"))
    score = int(score_raw) if score_raw.isdigit() else None

    stage_vals: dict[str, Any] = {}
    flat = []
    for el in nodes:
        rid = el.attrib.get("resource-id", "").split("/")[-1]
        t = _clean_str(el.attrib.get("text", ""))
        d = _parse_desc_list(el.attrib.get("content-desc", ""))
        if rid in ("unit_text", "title", "title2"):
            flat.append((rid, t, d))

    i = 0
    while i < len(flat):
        rid, t, d = flat[i]
        if rid == "unit_text":
            val_str = d or t
            label = flat[i + 1][1] if i + 1 < len(flat) and flat[i + 1][0] == "title" else ""
            extra = flat[i + 2][1] if i + 2 < len(flat) and flat[i + 2][0] == "title2" else ""
            low = label.lower()
            if "deep sleep" in low:
                mp = re.search(r"(\d+)\s*%", label)
                stage_vals["deep_sleep"] = val_str
                stage_vals["deep_sleep_min"] = _parse_duration_minutes(val_str)
                stage_vals["deep_sleep_pct"] = int(mp.group(1)) if mp else None
            elif "light sleep" in low:
                mp = re.search(r"(\d+)\s*%", label)
                stage_vals["light_sleep"] = val_str
                stage_vals["light_sleep_min"] = _parse_duration_minutes(val_str)
                stage_vals["light_sleep_pct"] = int(mp.group(1)) if mp else None
            elif "rem" in low:
                mp = re.search(r"(\d+)\s*%", label + " " + extra)
                stage_vals["rem"] = val_str
                stage_vals["rem_min"] = _parse_duration_minutes(val_str)
                stage_vals["rem_pct"] = int(mp.group(1)) if mp else None
            elif "awake" in low:
                stage_vals["awake"] = val_str
                stage_vals["awake_min"] = _parse_duration_minutes(val_str)
        i += 1

    dur_str = get_text("sleep_duration")
    nap_str = get_text("nap_time")
    bq_m = re.search(r"(\d+)", get_text("sleep_breath_quality_score"))

    return {
        "date": iso_date or raw_date,
        "raw_date": raw_date,
        "sleep_score": score,
        "percentile": get_text("chart_sub_title"),
        "bedtime": get_text("start_time"),
        "wake_time": get_text("stop_time"),
        "sleep_duration": dur_str,
        "sleep_duration_min": _parse_duration_minutes(dur_str),
        "deep_sleep": stage_vals.get("deep_sleep", ""),
        "deep_sleep_min": stage_vals.get("deep_sleep_min"),
        "deep_sleep_pct": stage_vals.get("deep_sleep_pct"),
        "light_sleep": stage_vals.get("light_sleep", ""),
        "light_sleep_min": stage_vals.get("light_sleep_min"),
        "light_sleep_pct": stage_vals.get("light_sleep_pct"),
        "rem": stage_vals.get("rem", ""),
        "rem_min": stage_vals.get("rem_min"),
        "rem_pct": stage_vals.get("rem_pct"),
        "awake": stage_vals.get("awake", ""),
        "awake_min": stage_vals.get("awake_min"),
        "naps": nap_str,
        "naps_min": _parse_duration_minutes(nap_str),
        "breathing_quality_score": int(bq_m.group(1)) if bq_m else None,
    }


def ensure_adb_target(serial: str = "any", timeout: int = 30) -> str | None:
    cmd = ["adb-wifi-ensure", "--serial", serial, "--timeout", str(timeout), "--app-name", "Fajr Sleep Guard", "-q"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 15)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip().splitlines()[-1].strip()
    except FileNotFoundError:
        pass
    # Fallback: check already-connected adb devices
    res = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=10)
    for line in res.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            return parts[0]
    return None


def _adb_shell(target: str, cmd: str, timeout: int = 25) -> str:
    res = subprocess.run(["adb", "-s", target, "shell", cmd], capture_output=True, text=True, timeout=timeout)
    return res.stdout


def _dump_ui(target: str) -> str:
    return _adb_shell(target, "uiautomator dump /sdcard/.fsg_ui.xml >/dev/null && cat /sdcard/.fsg_ui.xml")


def _find_node_center(xml_str: str, resource_id: str | None = None, text: str | None = None) -> tuple[int, int] | None:
    idx = xml_str.find("<?xml")
    if idx == -1:
        return None
    root = ET.fromstring(xml_str[idx:])
    for el in root.iter("node"):
        rid = el.attrib.get("resource-id", "").split("/")[-1]
        t = _clean_str(el.attrib.get("text", ""))
        if resource_id and rid != resource_id:
            continue
        if text and t != text:
            continue
        m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", el.attrib.get("bounds", ""))
        if m:
            x1, y1, x2, y2 = map(int, m.groups())
            return ((x1 + x2) // 2, (y1 + y2) // 2)
    return None


def sync_zepp_sleep(target: str, max_days: int = 14, overlap_days: int = 2) -> list[dict[str, Any]]:
    """Delta-sync recent sleep days from Zepp Life UI on the connected Android device."""
    existing = load_json(HISTORY_PATH, default=[])
    by_date: dict[str, dict[str, Any]] = {
        r["date"]: r for r in (existing if isinstance(existing, list) else []) if isinstance(r, dict) and r.get("date")
    }

    # Check if screen is locked by keyguard
    kg = _adb_shell(target, "dumpsys window policy | grep -E 'showing='")
    if "showing=true" in kg:
        raise RuntimeError("Phone keyguard is locked; cannot navigate Zepp Life UI until unlocked.")

    _adb_shell(target, "input keyevent 224 && am start -n com.xiaomi.hm.health/.activity.ChannelMainTabActivity")
    time.sleep(2.0)

    xml = _dump_ui(target)
    if "sleepSwitchDateTime" not in xml:
        # Tap Sleep card on home screen (find Sleep card_title)
        sleep_pt = _find_node_center(xml, text="Sleep")
        if sleep_pt:
            _adb_shell(target, f"input tap {sleep_pt[0]} {sleep_pt[1]}")
            time.sleep(2.0)
            xml = _dump_ui(target)

    if "sleepSwitchDateTime" not in xml:
        raise RuntimeError("Could not reach Zepp Life Sleep detail screen.")

    seen_known = 0
    last_raw = None
    for _ in range(max_days + 5):
        rec = parse_sleep_xml(xml)
        d = rec.get("date", "")
        raw = rec.get("raw_date", "")
        if not d:
            break
        if raw == last_raw:
            break
        last_raw = raw

        already_has_valid = d in by_date and (by_date[d].get("sleep_duration_min") or 0) > 0
        by_date[d] = rec

        if already_has_valid:
            seen_known += 1
            if seen_known >= overlap_days:
                break
        else:
            seen_known = 0

        _adb_shell(target, "input swipe 180 800 900 800 180")
        time.sleep(0.8)
        xml = _dump_ui(target)

    _adb_shell(target, "rm -f /sdcard/.fsg_ui.xml")
    merged = sorted(by_date.values(), key=lambda r: r["date"], reverse=True)
    save_json(HISTORY_PATH, merged)
    return merged


def seed_history_from_file(src_path: Path) -> int:
    data = load_json(src_path, default=[])
    if not isinstance(data, list) or not data:
        return 0
    existing = load_json(HISTORY_PATH, default=[])
    by_date = {r["date"]: r for r in (existing if isinstance(existing, list) else []) if r.get("date")}
    for r in data:
        if isinstance(r, dict) and r.get("date") and r["date"] not in by_date:
            by_date[r["date"]] = r
    merged = sorted(by_date.values(), key=lambda r: r["date"], reverse=True)
    save_json(HISTORY_PATH, merged)
    return len(merged)
