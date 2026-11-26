package com.mhawar.fajrsleepguard;

import android.app.admin.DevicePolicyManager;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.telecom.TelecomManager;

public final class LockController {
    private LockController() {}

    public static boolean isInPhoneCall(Context ctx) {
        try {
            TelecomManager tm = (TelecomManager) ctx.getSystemService(Context.TELECOM_SERVICE);
            return tm != null && tm.isInCall();
        } catch (SecurityException e) {
            return false;
        }
    }

    public static boolean shouldEnforceLock(Context ctx) {
        if (SleepScheduleStore.isAlarmRinging(ctx)) return false;
        if (isInPhoneCall(ctx)) return false;
        long now = System.currentTimeMillis();
        SleepScheduleStore.NightWindow w = SleepScheduleStore.getActiveWindow(ctx, now);
        if (w == null) return false;
        SleepScheduleStore.EmergencyConfig em = SleepScheduleStore.getEmergencyConfig(ctx);
        return !SleepScheduleStore.isInEmergencyUnlock(ctx, w.nightOf, now, em.maxUsesPerNight);
    }

    public static void showLockScreen(Context ctx) {
        Intent i = new Intent(ctx, LockActivity.class);
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK
                | Intent.FLAG_ACTIVITY_SINGLE_TOP
                | Intent.FLAG_ACTIVITY_CLEAR_TOP
                | Intent.FLAG_ACTIVITY_NO_ANIMATION);
        ctx.startActivity(i);
    }

    public static boolean turnScreenOffNow(Context ctx) {
        try {
            DevicePolicyManager dpm = (DevicePolicyManager) ctx.getSystemService(Context.DEVICE_POLICY_SERVICE);
            ComponentName admin = new ComponentName(ctx, SleepDeviceAdminReceiver.class);
            if (dpm != null && dpm.isAdminActive(admin)) {
                dpm.lockNow();
                return true;
            }
        } catch (Exception ignored) {}

        SleepAccessibilityService acc = SleepAccessibilityService.getInstance();
        if (acc != null) {
            return acc.lockScreenGlobal();
        }
        return false;
    }
}
