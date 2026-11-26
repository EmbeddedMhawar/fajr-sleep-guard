package com.mhawar.fajrsleepguard;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

public class ScheduleSyncReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        SleepScheduleStore.syncFromExternalFiles(context);
        SleepGuardService.scheduleNextFajrAlarm(context);
        SleepGuardService.ensureStarted(context);
    }
}
