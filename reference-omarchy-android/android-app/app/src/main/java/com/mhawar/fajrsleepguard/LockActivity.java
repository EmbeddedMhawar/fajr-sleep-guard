package com.mhawar.fajrsleepguard;

import android.app.Activity;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.FrameLayout;
import android.window.OnBackInvokedDispatcher;

import java.util.Locale;

public class LockActivity extends Activity {
    public static volatile boolean isActive = false;

    private final Handler handler = new Handler(Looper.getMainLooper());
    private Button emergencyBtn;
    private boolean holding = false;
    private long holdStartMs = 0L;
    private long lastInteractionMs = 0L;
    private String activeNightOf = "";

    private final Runnable tickRunnable = new Runnable() {
        @Override
        public void run() {
            if (!LockController.shouldEnforceLock(LockActivity.this)) {
                finish();
                return;
            }
            long now = System.currentTimeMillis();
            SleepScheduleStore.NightWindow w = SleepScheduleStore.getActiveWindow(LockActivity.this, now);
            if (w == null) {
                finish();
                return;
            }
            activeNightOf = w.nightOf;
            SleepScheduleStore.EmergencyConfig em = SleepScheduleStore.getEmergencyConfig(LockActivity.this);
            int usesLeft = SleepScheduleStore.getUsesRemaining(LockActivity.this, activeNightOf, em.maxUsesPerNight);

            if (holding) {
                long heldMs = now - holdStartMs;
                int heldSec = (int) (heldMs / 1000L);
                if (heldSec >= em.maxGrantSec) {
                    completeHold(em.maxGrantSec);
                    return;
                }
                emergencyBtn.setEnabled(true);
                emergencyBtn.setText(String.format(Locale.US, "%d:%02d / %d:%02d",
                        heldSec / 60, heldSec % 60, em.maxGrantSec / 60, em.maxGrantSec % 60));
            } else {
                if (usesLeft <= 0) {
                    emergencyBtn.setEnabled(false);
                    emergencyBtn.setText("");
                    emergencyBtn.setVisibility(View.INVISIBLE);
                    LockController.turnScreenOffNow(LockActivity.this);
                } else {
                    emergencyBtn.setVisibility(View.VISIBLE);
                    emergencyBtn.setEnabled(true);
                    emergencyBtn.setText("Hold for Emergency");
                    if (now - lastInteractionMs > 4000L) {
                        LockController.turnScreenOffNow(LockActivity.this);
                    }
                }
            }
            handler.postDelayed(this, 100L);
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setShowWhenLocked(true);
        setTurnScreenOn(true);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_FULLSCREEN);

        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.TIRAMISU) {
            getOnBackInvokedDispatcher().registerOnBackInvokedCallback(
                    OnBackInvokedDispatcher.PRIORITY_DEFAULT, () -> {}
            );
        }

        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.BLACK);
        root.setSystemUiVisibility(
                View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                        | View.SYSTEM_UI_FLAG_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
        );

        emergencyBtn = new Button(this);
        emergencyBtn.setText("Hold for Emergency");
        emergencyBtn.setAllCaps(false);
        emergencyBtn.setTextColor(Color.parseColor("#555555"));
        emergencyBtn.setTextSize(15f);
        emergencyBtn.setPadding(64, 36, 64, 36);

        GradientDrawable bg = new GradientDrawable();
        bg.setColor(Color.parseColor("#0A0A0A"));
        bg.setStroke(2, Color.parseColor("#1F1F1F"));
        bg.setCornerRadius(999f);
        emergencyBtn.setBackground(bg);

        FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.WRAP_CONTENT,
                FrameLayout.LayoutParams.WRAP_CONTENT,
                Gravity.CENTER
        );
        root.addView(emergencyBtn, lp);

        root.setOnTouchListener((v, ev) -> {
            lastInteractionMs = System.currentTimeMillis();
            return false;
        });

        emergencyBtn.setOnTouchListener((v, ev) -> {
            lastInteractionMs = System.currentTimeMillis();
            int action = ev.getActionMasked();
            if (action == MotionEvent.ACTION_DOWN) {
                SleepScheduleStore.EmergencyConfig em = SleepScheduleStore.getEmergencyConfig(this);
                int left = SleepScheduleStore.getUsesRemaining(this, activeNightOf, em.maxUsesPerNight);
                if (left > 0 && !holding) {
                    holding = true;
                    holdStartMs = System.currentTimeMillis();
                    emergencyBtn.setTextColor(Color.parseColor("#CCCCCC"));
                }
                return true;
            } else if (action == MotionEvent.ACTION_UP || action == MotionEvent.ACTION_CANCEL) {
                if (holding) {
                    int heldSec = (int) Math.round((System.currentTimeMillis() - holdStartMs) / 1000.0);
                    completeHold(heldSec);
                }
                return true;
            }
            return false;
        });

        setContentView(root);
        lastInteractionMs = System.currentTimeMillis();
    }

    private void completeHold(int heldSec) {
        holding = false;
        emergencyBtn.setTextColor(Color.parseColor("#555555"));
        emergencyBtn.setText("Hold for Emergency");
        SleepScheduleStore.EmergencyConfig em = SleepScheduleStore.getEmergencyConfig(this);
        if (heldSec >= em.minHoldSec && !activeNightOf.isEmpty()) {
            long granted = SleepScheduleStore.grantEmergencyUnlock(this, activeNightOf, heldSec, em);
            if (granted > 0) {
                finish();
                return;
            }
        }
        lastInteractionMs = System.currentTimeMillis();
    }

    @Override
    protected void onResume() {
        super.onResume();
        isActive = true;
        lastInteractionMs = System.currentTimeMillis();
        handler.removeCallbacks(tickRunnable);
        handler.post(tickRunnable);
    }

    @Override
    protected void onPause() {
        isActive = false;
        holding = false;
        handler.removeCallbacks(tickRunnable);
        super.onPause();
        if (LockController.shouldEnforceLock(this)) {
            handler.postDelayed(() -> {
                if (LockController.shouldEnforceLock(LockActivity.this)) {
                    LockController.showLockScreen(LockActivity.this);
                }
            }, 200L);
        }
    }

    @Override
    public void onBackPressed() {
        // Blocked during sleep lock
    }
}
