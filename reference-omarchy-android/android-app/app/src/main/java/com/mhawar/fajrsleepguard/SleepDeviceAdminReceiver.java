package com.mhawar.fajrsleepguard;

import android.app.admin.DeviceAdminReceiver;
import android.content.Context;
import android.content.Intent;

public class SleepDeviceAdminReceiver extends DeviceAdminReceiver {
    @Override
    public void onEnabled(Context context, Intent intent) {
        super.onEnabled(context, intent);
    }
}
