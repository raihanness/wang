package dev.raihan.wang;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;

public class BootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        String action = intent.getAction();
        if (Intent.ACTION_BOOT_COMPLETED.equals(action) ||
            Intent.ACTION_MY_PACKAGE_REPLACED.equals(action) ||
            "android.intent.action.QUICKBOOT_POWERON".equals(action)) {

            SharedPreferences prefs = context.getSharedPreferences(DailyReminderReceiver.PREF_NAME, Context.MODE_PRIVATE);
            boolean isEnabled = prefs.getBoolean(DailyReminderReceiver.KEY_REMINDER_ENABLED, false);
            if (isEnabled) {
                int hour = prefs.getInt(DailyReminderReceiver.KEY_REMINDER_HOUR, 20);
                int minute = prefs.getInt(DailyReminderReceiver.KEY_REMINDER_MINUTE, 0);
                DailyReminderReceiver.scheduleReminder(context, hour, minute);
            }
        }
    }
}
