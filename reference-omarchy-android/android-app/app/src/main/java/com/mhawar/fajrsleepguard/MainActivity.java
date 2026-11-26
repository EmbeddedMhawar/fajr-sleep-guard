package com.mhawar.fajrsleepguard;

import android.app.Activity;
import android.app.admin.DevicePolicyManager;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.os.PowerManager;
import android.provider.Settings;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.List;
import java.util.Locale;

public class MainActivity extends Activity {
    private TextView statusView;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        SleepScheduleStore.syncFromExternalFiles(this);
        SleepGuardService.ensureStarted(this);

        ScrollView scroll = new ScrollView(this);
        scroll.setBackgroundColor(Color.parseColor("#111111"));

        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setPadding(48, 80, 48, 64);

        TextView header = new TextView(this);
        header.setText("Fajr Sleep Guard");
        header.setTextColor(Color.WHITE);
        header.setTextSize(24f);
        layout.addView(header);

        statusView = new TextView(this);
        statusView.setTextColor(Color.parseColor("#BBBBBB"));
        statusView.setTextSize(14f);
        statusView.setPadding(0, 24, 0, 36);
        layout.addView(statusView);

        addBtn(layout, "1. Enable Device Admin (Turn Screen Off)", v -> {
            ComponentName admin = new ComponentName(this, SleepDeviceAdminReceiver.class);
            Intent i = new Intent(DevicePolicyManager.ACTION_ADD_DEVICE_ADMIN);
            i.putExtra(DevicePolicyManager.EXTRA_DEVICE_ADMIN, admin);
            i.putExtra(DevicePolicyManager.EXTRA_ADD_EXPLANATION,
                    "Required to turn the screen off immediately during sleep hours.");
            startActivity(i);
        });

        addBtn(layout, "2. Enable Accessibility Guard", v ->
                startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)));

        addBtn(layout, "3. Allow Display Over Other Apps", v ->
                startActivity(new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                        Uri.parse("package:" + getPackageName()))));

        addBtn(layout, "4. Ignore Battery Optimizations", v ->
                startActivity(new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                        Uri.parse("package:" + getPackageName()))));

        addBtn(layout, "Test Pure-Black Lock (15s)", v -> {
            SleepScheduleStore.startTestLock(this, 15);
            LockController.showLockScreen(this);
        });

        scroll.addView(layout);
        setContentView(scroll);
    }

    private void addBtn(LinearLayout parent, String label, android.view.View.OnClickListener onClick) {
        Button b = new Button(this);
        b.setText(label);
        b.setAllCaps(false);
        b.setOnClickListener(onClick);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
        );
        lp.bottomMargin = 20;
        parent.addView(b, lp);
    }

    @Override
    protected void onResume() {
        super.onResume();
        refreshStatus();
    }

    private void refreshStatus() {
        SleepScheduleStore.syncFromExternalFiles(this);
        long now = System.currentTimeMillis();
        SleepScheduleStore.NightWindow next = SleepScheduleStore.getNextWakeWindow(this, now);
        SimpleDateFormat fmt = new SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.US);

        DevicePolicyManager dpm = (DevicePolicyManager) getSystemService(Context.DEVICE_POLICY_SERVICE);
        boolean adminOk = dpm != null && dpm.isAdminActive(new ComponentName(this, SleepDeviceAdminReceiver.class));
        boolean accOk = SleepAccessibilityService.getInstance() != null;
        boolean overlayOk = Settings.canDrawOverlays(this);
        PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
        boolean batteryOk = pm != null && pm.isIgnoringBatteryOptimizations(getPackageName());

        StringBuilder sb = new StringBuilder();
        if (next != null) {
            SleepScheduleStore.EmergencyConfig em = SleepScheduleStore.getEmergencyConfig(this);
            int left = SleepScheduleStore.getUsesRemaining(this, next.nightOf, em.maxUsesPerNight);
            sb.append("Night: ").append(next.nightOf).append("\n")
              .append("Bedtime lock: ").append(fmt.format(new Date(next.bedtimeMs))).append("\n")
              .append("Fajr wake alarm: ").append(fmt.format(new Date(next.wakeAtMs))).append("\n")
              .append("Emergency holds left: ").append(left).append("/").append(em.maxUsesPerNight).append("\n\n");
        } else {
            List<SleepScheduleStore.NightWindow> all = SleepScheduleStore.loadWindows(this);
            sb.append("Loaded windows: ").append(all.size()).append("\n\n");
        }
        sb.append("Device Admin: ").append(adminOk ? "ENABLED" : "needed").append("\n")
          .append("Accessibility Guard: ").append(accOk ? "ENABLED" : "needed").append("\n")
          .append("Overlay Permission: ").append(overlayOk ? "ENABLED" : "needed").append("\n")
          .append("Battery Unrestricted: ").append(batteryOk ? "ENABLED" : "needed");
        statusView.setText(sb.toString());
    }
}
