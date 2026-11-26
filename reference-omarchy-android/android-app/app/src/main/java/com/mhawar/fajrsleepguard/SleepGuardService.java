package com.mhawar.fajrsleepguard;

import android.app.AlarmManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.PowerManager;

public class SleepGuardService extends Service {
    private static final String CHANNEL_ID = "fsg_guard_channel";
    private final Handler handler = new Handler(Looper.getMainLooper());
    private BroadcastReceiver screenReceiver;

    private final Runnable checkRunnable = new Runnable() {
        @Override
        public void run() {
            enforceIfNeeded();
            handler.postDelayed(this, 1500L);
        }
    };

    public static void ensureStarted(Context ctx) {
        Intent i = new Intent(ctx, SleepGuardService.class);
        ctx.startForegroundService(i);
    }

    public static void scheduleNextFajrAlarm(Context ctx) {
        SleepScheduleStore.NightWindow next = SleepScheduleStore.getNextWakeWindow(ctx, System.currentTimeMillis());
        if (next == null) return;
        AlarmManager am = (AlarmManager) ctx.getSystemService(Context.ALARM_SERVICE);
        if (am == null) return;
        Intent i = new Intent(ctx, AlarmReceiver.class);
        PendingIntent pi = PendingIntent.getBroadcast(
                ctx, 1001, i, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );
        Intent showIntent = new Intent(ctx, MainActivity.class);
        PendingIntent showPi = PendingIntent.getActivity(
                ctx, 1002, showIntent, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );
        AlarmManager.AlarmClockInfo info = new AlarmManager.AlarmClockInfo(next.wakeAtMs, showPi);
        try {
            am.setAlarmClock(info, pi);
        } catch (SecurityException ignored) {}
    }

    @Override
    public void onCreate() {
        super.onCreate();
        createNotificationChannel();
        Notification n = new Notification.Builder(this, CHANNEL_ID)
                .setContentTitle("Fajr Sleep Guard")
                .setContentText("Monitoring sleep schedule & Fajr wake alarm")
                .setSmallIcon(android.R.drawable.ic_lock_idle_alarm)
                .setOngoing(true)
                .build();
        startForeground(101, n);

        SleepScheduleStore.syncFromExternalFiles(this);
        scheduleNextFajrAlarm(this);

        screenReceiver = new BroadcastReceiver() {
            @Override
            public void onReceive(Context context, Intent intent) {
                enforceIfNeeded();
            }
        };
        IntentFilter filter = new IntentFilter();
        filter.addAction(Intent.ACTION_SCREEN_ON);
        filter.addAction(Intent.ACTION_USER_PRESENT);
        registerReceiver(screenReceiver, filter);

        handler.post(checkRunnable);
    }

    private void enforceIfNeeded() {
        if (!LockController.shouldEnforceLock(this)) return;
        PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
        if (pm != null && pm.isInteractive() && !LockActivity.isActive) {
            LockController.showLockScreen(this);
        }
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        SleepScheduleStore.syncFromExternalFiles(this);
        scheduleNextFajrAlarm(this);
        enforceIfNeeded();
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        handler.removeCallbacks(checkRunnable);
        if (screenReceiver != null) {
            try { unregisterReceiver(screenReceiver); } catch (Exception ignored) {}
        }
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private void createNotificationChannel() {
        NotificationChannel ch = new NotificationChannel(
                CHANNEL_ID, "Fajr Sleep Guard", NotificationManager.IMPORTANCE_LOW
        );
        NotificationManager nm = getSystemService(NotificationManager.class);
        if (nm != null) nm.createNotificationChannel(ch);
    }
}
