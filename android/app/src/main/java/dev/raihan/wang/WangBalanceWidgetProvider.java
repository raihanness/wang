package dev.raihan.wang;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;
import android.widget.RemoteViews;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

public class WangBalanceWidgetProvider extends AppWidgetProvider {

    @Override
    public void onUpdate(Context context, AppWidgetManager appWidgetManager, int[] appWidgetIds) {
        for (int appWidgetId : appWidgetIds) {
            updateAppWidget(context, appWidgetManager, appWidgetId);
        }
    }

    public static void updateAppWidget(Context context, AppWidgetManager appWidgetManager, int appWidgetId) {
        SharedPreferences prefs = context.getSharedPreferences(MainActivity.PREFS_NAME, Context.MODE_PRIVATE);
        String balance = prefs.getString("widget_balance", "Rp0");
        String todaySpent = prefs.getString("widget_today_spent", "");
        long lastUpdated = prefs.getLong("widget_last_updated", 0);

        RemoteViews views = new RemoteViews(context.getPackageName(), R.layout.widget_balance);

        // Update balance text
        views.setTextViewText(R.id.tv_widget_balance, balance != null && !balance.isEmpty() ? balance : "Rp0");

        // Update subtext
        if (todaySpent != null && !todaySpent.isEmpty()) {
            views.setTextViewText(R.id.tv_widget_today_spent, "Today's Spent: " + todaySpent);
        } else {
            views.setTextViewText(R.id.tv_widget_today_spent, context.getString(R.string.widget_tap_to_sync));
        }

        // Update status label
        if (lastUpdated > 0) {
            SimpleDateFormat sdf = new SimpleDateFormat("HH:mm", Locale.getDefault());
            views.setTextViewText(R.id.tv_widget_updated, "Synced " + sdf.format(new Date(lastUpdated)));
        } else {
            views.setTextViewText(R.id.tv_widget_updated, "Live");
        }

        // 1. Click Balance Area -> Open Dashboard
        Intent dashIntent = new Intent(context, MainActivity.class);
        dashIntent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent dashPendingIntent = PendingIntent.getActivity(
                context,
                101,
                dashIntent,
                PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M ? PendingIntent.FLAG_IMMUTABLE : 0)
        );
        views.setOnClickPendingIntent(R.id.widget_balance_click_area, dashPendingIntent);

        // 2. Click "+ Expense" -> Open Add Expense Sheet
        Intent expenseIntent = new Intent(context, MainActivity.class);
        expenseIntent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        expenseIntent.putExtra("shortcut_action", "new_expense");
        PendingIntent expensePendingIntent = PendingIntent.getActivity(
                context,
                102,
                expenseIntent,
                PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M ? PendingIntent.FLAG_IMMUTABLE : 0)
        );
        views.setOnClickPendingIntent(R.id.btn_widget_add_expense, expensePendingIntent);

        // 3. Click "+ Income" -> Open Add Income Sheet
        Intent incomeIntent = new Intent(context, MainActivity.class);
        incomeIntent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        incomeIntent.putExtra("shortcut_action", "new_income");
        PendingIntent incomePendingIntent = PendingIntent.getActivity(
                context,
                103,
                incomeIntent,
                PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M ? PendingIntent.FLAG_IMMUTABLE : 0)
        );
        views.setOnClickPendingIntent(R.id.btn_widget_add_income, incomePendingIntent);

        appWidgetManager.updateAppWidget(appWidgetId, views);
    }

    public static void updateAllWidgets(Context context) {
        try {
            AppWidgetManager appWidgetManager = AppWidgetManager.getInstance(context);
            ComponentName thisWidget = new ComponentName(context, WangBalanceWidgetProvider.class);
            int[] allWidgetIds = appWidgetManager.getAppWidgetIds(thisWidget);
            for (int widgetId : allWidgetIds) {
                updateAppWidget(context, appWidgetManager, widgetId);
            }
        } catch (Exception ignored) {}
    }
}
