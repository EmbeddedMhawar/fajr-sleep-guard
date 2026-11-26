package com.mhawar.fajrsleepguard;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.util.ArrayList;
import java.util.List;

public final class SleepScheduleStore {
    private static final String PREFS = "fsg_prefs";
    private static final String KEY_NIGHT_OF = "night_of";
    private static final String KEY_USES_LEFT = "uses_left";
    private static final String KEY_UNLOCKED_UNTIL = "unlocked_until_ms";
    private static final String KEY_TEST_UNTIL = "test_until_ms";
    private static final String KEY_ALARM_RINGING = "alarm_ringing";

    public static final class EmergencyConfig {
        public double ratio = 1.0;
        public int minHoldSec = 3;
        public int maxGrantSec = 600;
        public int maxUsesPerNight = 2;
    }

    public static final class NightWindow {
        public String nightOf;
        public long ishaMs;
        public long bedtimeMs;
        public long wakeAtMs;
        public long fajrMs;
    }

    private SleepScheduleStore() {}

    public static void syncFromExternalFiles(Context ctx) {
        File extDir = ctx.getExternalFilesDir(null);
        if (extDir == null) return;
        for (String name : new String[]{"schedule.json", "config.json"}) {
            File src = new File(extDir, name);
            if (src.exists() && src.isFile() && src.length() > 0) {
                copyFile(src, new File(ctx.getFilesDir(), name));
            }
        }
    }

    private static void copyFile(File src, File dst) {
        try (FileInputStream in = new FileInputStream(src);
             FileOutputStream out = new FileOutputStream(dst)) {
            byte[] buf = new byte[4096];
            int n;
            while ((n = in.read(buf)) > 0) {
                out.write(buf, 0, n);
            }
        } catch (Exception ignored) {}
    }

    private static String readJsonText(Context ctx, String name) {
        File extDir = ctx.getExternalFilesDir(null);
        if (extDir != null) {
            File ext = new File(extDir, name);
            if (ext.exists() && ext.length() > 0) {
                String s = readFile(ext);
                if (s != null) return s;
            }
        }
        File internal = new File(ctx.getFilesDir(), name);
        return internal.exists() ? readFile(internal) : null;
    }

    private static String readFile(File f) {
        try (FileInputStream in = new FileInputStream(f);
             ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buf = new byte[4096];
            int n;
            while ((n = in.read(buf)) > 0) {
                out.write(buf, 0, n);
            }
            return out.toString(StandardCharsets.UTF_8.name());
        } catch (Exception e) {
            return null;
        }
    }

    public static EmergencyConfig getEmergencyConfig(Context ctx) {
        EmergencyConfig em = new EmergencyConfig();
        try {
            String raw = readJsonText(ctx, "schedule.json");
            if (raw != null) {
                JSONObject root = new JSONObject(raw);
                JSONObject e = root.optJSONObject("emergency");
                if (e != null) {
                    em.ratio = e.optDouble("ratio", 1.0);
                    em.minHoldSec = e.optInt("min_hold_sec", 3);
                    em.maxGrantSec = e.optInt("max_grant_sec", 600);
                    em.maxUsesPerNight = e.optInt("max_uses_per_night", 2);
                }
            }
        } catch (Exception ignored) {}
        return em;
    }

    public static List<NightWindow> loadWindows(Context ctx) {
        List<NightWindow> out = new ArrayList<>();
        try {
            String raw = readJsonText(ctx, "schedule.json");
            if (raw != null) {
                JSONObject root = new JSONObject(raw);
                JSONArray arr = root.optJSONArray("nights");
                if (arr != null) {
                    for (int i = 0; i < arr.length(); i++) {
                        JSONObject o = arr.getJSONObject(i);
                        NightWindow w = new NightWindow();
                        w.nightOf = o.getString("night_of");
                        w.ishaMs = Instant.parse(o.getString("isha")).toEpochMilli();
                        w.bedtimeMs = Instant.parse(o.getString("bedtime")).toEpochMilli();
                        w.wakeAtMs = Instant.parse(o.getString("wake_at")).toEpochMilli();
                        w.fajrMs = Instant.parse(o.getString("fajr")).toEpochMilli();
                        out.add(w);
                    }
                }
            }
        } catch (Exception ignored) {}

        if (out.isEmpty()) {
            out.addAll(computeOfflineFallbackWindows(ctx));
        }
        return out;
    }

    private static List<NightWindow> computeOfflineFallbackWindows(Context ctx) {
        double lat = 33.5883;
        double lon = -7.6114;
        String tzId = "Africa/Casablanca";
        int wakeOffsetMin = 10;
        int ishaWindDownMin = 30;
        int maxSleepMin = 510;
        try {
            String cfgRaw = readJsonText(ctx, "config.json");
            if (cfgRaw != null) {
                JSONObject cfg = new JSONObject(cfgRaw);
                lat = cfg.optDouble("latitude", lat);
                lon = cfg.optDouble("longitude", lon);
                tzId = cfg.optString("timezone", tzId);
                wakeOffsetMin = cfg.optInt("wake_offset_before_fajr_min", wakeOffsetMin);
                ishaWindDownMin = cfg.optInt("isha_wind_down_min", ishaWindDownMin);
                maxSleepMin = cfg.optInt("max_target_sleep_min", maxSleepMin);
            }
        } catch (Exception ignored) {}

        ZoneId tz = ZoneId.of(tzId);
        LocalDate today = LocalDate.now(tz);
        List<NightWindow> list = new ArrayList<>();
        for (int offset = -1; offset <= 2; offset++) {
            LocalDate nd = today.plusDays(offset);
            long[] tonight = computeSolarTwilightEpoch(nd, lat, lon);
            long[] morning = computeSolarTwilightEpoch(nd.plusDays(1), lat, lon);
            long ishaMs = tonight[1];
            long fajrMs = morning[0];
            long wakeMs = fajrMs - wakeOffsetMin * 60_000L;
            long earliestBed = ishaMs + ishaWindDownMin * 60_000L;
            long ceilingBed = wakeMs - maxSleepMin * 60_000L;
            NightWindow w = new NightWindow();
            w.nightOf = nd.toString();
            w.ishaMs = ishaMs;
            w.fajrMs = fajrMs;
            w.wakeAtMs = wakeMs;
            w.bedtimeMs = Math.max(earliestBed, ceilingBed);
            list.add(w);
        }
        return list;
    }

    /** Returns [fajrUtcMs, ishaUtcMs] matching Morocco Method 21 (19 deg / 17 deg). */
    private static long[] computeSolarTwilightEpoch(LocalDate date, double lat, double lon) {
        int a = (14 - date.getMonthValue()) / 12;
        int y = date.getYear() + 4800 - a;
        int m = date.getMonthValue() + 12 * a - 3;
        int jd = date.getDayOfMonth() + (153 * m + 2) / 5 + 365 * y + y / 4 - y / 100 + y / 400 - 32045;
        double d = jd - 2451545.0;
        double g = Math.toRadians((357.529 + 0.98560028 * d) % 360.0);
        double q = (280.459 + 0.98564736 * d) % 360.0;
        double L = Math.toRadians((q + 1.915 * Math.sin(g) + 0.020 * Math.sin(2 * g)) % 360.0);
        double e = Math.toRadians(23.439 - 0.00000036 * d);
        double ra = (Math.toDegrees(Math.atan2(Math.cos(e) * Math.sin(L), Math.cos(L))) / 15.0) % 24.0;
        if (ra < 0) ra += 24.0;
        double decl = Math.asin(Math.sin(e) * Math.sin(L));
        double eqT = (q / 15.0) - ra;
        if (eqT > 12) eqT -= 24;
        else if (eqT < -12) eqT += 24;
        double solarNoonUtc = 12.0 - eqT - (lon / 15.0);

        double fajrH = solarNoonUtc - hourAngle(lat, decl, 19.0);
        double ishaH = solarNoonUtc + hourAngle(lat, decl, 17.0);

        long baseUtc = ZonedDateTime.of(date.getYear(), date.getMonthValue(), date.getDayOfMonth(),
                0, 0, 0, 0, ZoneId.of("UTC")).toInstant().toEpochMilli();
        return new long[]{
                baseUtc + Math.round(fajrH * 3600_000.0),
                baseUtc + Math.round(ishaH * 3600_000.0)
        };
    }

    private static double hourAngle(double latDeg, double declRad, double angleDeg) {
        double latR = Math.toRadians(latDeg);
        double num = -Math.sin(Math.toRadians(angleDeg)) - Math.sin(latR) * Math.sin(declRad);
        double den = Math.cos(latR) * Math.cos(declRad);
        double cosH = Math.max(-1.0, Math.min(1.0, num / den));
        return Math.toDegrees(Math.acos(cosH)) / 15.0;
    }

    public static NightWindow getActiveWindow(Context ctx, long nowMs) {
        SharedPreferences sp = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        long testUntil = sp.getLong(KEY_TEST_UNTIL, 0L);
        if (nowMs < testUntil) {
            NightWindow tw = new NightWindow();
            tw.nightOf = "test-" + LocalDate.now().toString();
            tw.bedtimeMs = nowMs - 60_000L;
            tw.wakeAtMs = testUntil;
            tw.fajrMs = testUntil;
            tw.ishaMs = nowMs - 120_000L;
            return tw;
        }
        for (NightWindow w : loadWindows(ctx)) {
            if (nowMs >= w.bedtimeMs && nowMs < w.wakeAtMs) {
                return w;
            }
        }
        return null;
    }

    public static NightWindow getNextWakeWindow(Context ctx, long nowMs) {
        NightWindow best = null;
        for (NightWindow w : loadWindows(ctx)) {
            if (w.wakeAtMs > nowMs && (best == null || w.wakeAtMs < best.wakeAtMs)) {
                best = w;
            }
        }
        return best;
    }

    public static void ensureNightState(Context ctx, String nightOf, int maxUses) {
        SharedPreferences sp = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        if (!nightOf.equals(sp.getString(KEY_NIGHT_OF, ""))) {
            sp.edit()
                    .putString(KEY_NIGHT_OF, nightOf)
                    .putInt(KEY_USES_LEFT, maxUses)
                    .putLong(KEY_UNLOCKED_UNTIL, 0L)
                    .apply();
        }
    }

    public static int getUsesRemaining(Context ctx, String nightOf, int maxUses) {
        ensureNightState(ctx, nightOf, maxUses);
        return ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getInt(KEY_USES_LEFT, maxUses);
    }

    public static boolean isInEmergencyUnlock(Context ctx, String nightOf, long nowMs, int maxUses) {
        ensureNightState(ctx, nightOf, maxUses);
        long until = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getLong(KEY_UNLOCKED_UNTIL, 0L);
        return nowMs < until;
    }

    public static long grantEmergencyUnlock(Context ctx, String nightOf, int heldSec, EmergencyConfig em) {
        ensureNightState(ctx, nightOf, em.maxUsesPerNight);
        SharedPreferences sp = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        int left = sp.getInt(KEY_USES_LEFT, em.maxUsesPerNight);
        if (left <= 0 || heldSec < em.minHoldSec) return 0L;
        int grantSec = Math.min(em.maxGrantSec, Math.max(1, (int) Math.round(heldSec * em.ratio)));
        long until = System.currentTimeMillis() + grantSec * 1000L;
        sp.edit()
                .putInt(KEY_USES_LEFT, left - 1)
                .putLong(KEY_UNLOCKED_UNTIL, until)
                .apply();
        return grantSec;
    }

    public static void startTestLock(Context ctx, int seconds) {
        long until = System.currentTimeMillis() + seconds * 1000L;
        SharedPreferences sp = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        sp.edit()
                .putLong(KEY_TEST_UNTIL, until)
                .putString(KEY_NIGHT_OF, "")
                .apply();
    }

    public static void clearTestLock(Context ctx) {
        ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putLong(KEY_TEST_UNTIL, 0L).apply();
    }

    public static void setAlarmRinging(Context ctx, boolean ringing) {
        ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putBoolean(KEY_ALARM_RINGING, ringing).apply();
    }

    public static boolean isAlarmRinging(Context ctx) {
        return ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getBoolean(KEY_ALARM_RINGING, false);
    }
}
