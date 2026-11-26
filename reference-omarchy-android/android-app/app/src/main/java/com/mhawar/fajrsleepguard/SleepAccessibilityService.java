package com.mhawar.fajrsleepguard;

import android.accessibilityservice.AccessibilityService;
import android.view.accessibility.AccessibilityEvent;

public class SleepAccessibilityService extends AccessibilityService {
    private static volatile SleepAccessibilityService instance;

    public static SleepAccessibilityService getInstance() {
        return instance;
    }

    @Override
    protected void onServiceConnected() {
        super.onServiceConnected();
        instance = this;
    }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        if (event == null || event.getPackageName() == null) return;
        String pkg = event.getPackageName().toString();
        if (pkg.equals(getPackageName())) return;
        if (pkg.contains("dialer") || pkg.contains("incallui") || pkg.contains("deskclock")) return;

        if (LockController.shouldEnforceLock(this)) {
            LockController.showLockScreen(this);
        }
    }

    @Override
    public void onInterrupt() {}

    @Override
    public void onDestroy() {
        instance = null;
        super.onDestroy();
    }

    public boolean lockScreenGlobal() {
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.P) {
            return performGlobalAction(GLOBAL_ACTION_LOCK_SCREEN);
        }
        return false;
    }
}
