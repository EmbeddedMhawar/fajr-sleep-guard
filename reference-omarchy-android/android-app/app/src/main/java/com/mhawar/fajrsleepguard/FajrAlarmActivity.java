package com.mhawar.fajrsleepguard;

import android.app.Activity;
import android.content.Context;
import android.graphics.Color;
import android.media.AudioAttributes;
import android.media.Ringtone;
import android.media.RingtoneManager;
import android.net.Uri;
import android.os.Bundle;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.view.Gravity;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

public class FajrAlarmActivity extends Activity {
    private Ringtone ringtone;
    private Vibrator vibrator;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setShowWhenLocked(true);
        setTurnScreenOn(true);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);

        SleepScheduleStore.setAlarmRinging(this, true);
        SleepScheduleStore.clearTestLock(this);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER);
        root.setBackgroundColor(Color.BLACK);
        root.setPadding(64, 64, 64, 64);

        TextView title = new TextView(this);
        title.setText("Fajr Wake-Up");
        title.setTextColor(Color.WHITE);
        title.setTextSize(28f);
        title.setGravity(Gravity.CENTER);

        TextView sub = new TextView(this);
        sub.setText("10 minutes before Fajr");
        sub.setTextColor(Color.parseColor("#888888"));
        sub.setTextSize(15f);
        sub.setGravity(Gravity.CENTER);
        sub.setPadding(0, 16, 0, 64);

        Button dismiss = new Button(this);
        dismiss.setText("Dismiss");
        dismiss.setAllCaps(false);
        dismiss.setTextSize(18f);
        dismiss.setPadding(80, 40, 80, 40);
        dismiss.setOnClickListener(v -> stopAndFinish());

        root.addView(title);
        root.addView(sub);
        root.addView(dismiss);
        setContentView(root);

        startAlarmSound();
    }

    private void startAlarmSound() {
        try {
            Uri uri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM);
            if (uri == null) uri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION);
            ringtone = RingtoneManager.getRingtone(this, uri);
            if (ringtone != null) {
                ringtone.setAudioAttributes(new AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_ALARM)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                        .build());
                ringtone.play();
            }
        } catch (Exception ignored) {}

        try {
            vibrator = (Vibrator) getSystemService(Context.VIBRATOR_SERVICE);
            if (vibrator != null) {
                vibrator.vibrate(VibrationEffect.createWaveform(new long[]{0, 600, 400}, 0));
            }
        } catch (Exception ignored) {}
    }

    private void stopAndFinish() {
        if (ringtone != null) {
            try { ringtone.stop(); } catch (Exception ignored) {}
        }
        if (vibrator != null) {
            try { vibrator.cancel(); } catch (Exception ignored) {}
        }
        SleepScheduleStore.setAlarmRinging(this, false);
        SleepGuardService.scheduleNextFajrAlarm(this);
        finish();
    }

    @Override
    protected void onDestroy() {
        if (ringtone != null) {
            try { ringtone.stop(); } catch (Exception ignored) {}
        }
        if (vibrator != null) {
            try { vibrator.cancel(); } catch (Exception ignored) {}
        }
        SleepScheduleStore.setAlarmRinging(this, false);
        super.onDestroy();
    }
}
