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

    public static final String ACTION_TOGGLE_PRIVACY = "dev.raihan.wang.ACTION_TOGGLE_PRIVACY";

    @Override
    public void onReceive(Context context, Intent intent) {
        super.onReceive(context, intent);
        if (ACTION_TOGGLE_PRIVACY.equals(intent.getAction())) {
            SharedPreferences prefs = context.getSharedPreferences(MainActivity.PREFS_NAME, Context.MODE_PRIVATE);
            boolean current = prefs.getBoolean("widget_balance_hidden", false);
            prefs.edit().putBoolean("widget_balance_hidden", !current).apply();

            WangBalanceWidgetProvider.updateAllWidgets(context);
            WangSquareWidgetProvider.updateAllWidgets(context);
        }
    }

    @Override
    public void onUpdate(Context context, AppWidgetManager appWidgetManager, int[] appWidgetIds) {
        for (int appWidgetId : appWidgetIds) {
            updateAppWidget(context, appWidgetManager, appWidgetId);
        }
    }

    public static void updateAppWidget(Context context, AppWidgetManager appWidgetManager, int appWidgetId) {
        try {
            SharedPreferences prefs = context.getSharedPreferences(MainActivity.PREFS_NAME, Context.MODE_PRIVATE);
            String balance = prefs.getString("widget_balance", "Rp0");
            String todaySpent = prefs.getString("widget_today_spent", "Rp0");
            String todayIncome = prefs.getString("widget_today_income", "Rp0");
            String budgetRemaining = prefs.getString("widget_budget_remaining", "");
            String budgetLabel = prefs.getString("widget_budget_label", "");
            boolean isBalanceHidden = prefs.getBoolean("widget_balance_hidden", false);
            long lastUpdated = prefs.getLong("widget_last_updated", 0);

            RemoteViews views = new RemoteViews(context.getPackageName(), R.layout.widget_balance);

            // 1. Current Live Date (e.g. "Wed, 06 Oct 2026")
            SimpleDateFormat sdfDate = new SimpleDateFormat("EEE, dd MMM yyyy", Locale.getDefault());
            views.setTextViewText(R.id.tv_widget_date, sdfDate.format(new Date()));

            // 2. Hero Section: Today's Expense
            views.setTextViewText(R.id.tv_widget_hero_label, context.getString(R.string.widget_today_expenses_label));
            views.setTextViewText(R.id.tv_widget_hero_amount, todaySpent != null && !todaySpent.isEmpty() ? todaySpent : "Rp0");

            // 3. Bottom Column 1: Remaining Budget (fallback to Today's Income if no budget set)
            if (budgetRemaining != null && !budgetRemaining.trim().isEmpty()) {
                String lbl = (budgetLabel != null && !budgetLabel.trim().isEmpty())
                        ? budgetLabel.toUpperCase(Locale.getDefault())
                        : context.getString(R.string.widget_daily_budget_label);
                views.setTextViewText(R.id.tv_widget_balance_col1_label, lbl);
                views.setTextViewText(R.id.tv_widget_balance_col1_val, budgetRemaining);
            } else {
                views.setTextViewText(R.id.tv_widget_balance_col1_label, context.getString(R.string.widget_today_income_label));
                views.setTextViewText(R.id.tv_widget_balance_col1_val, todayIncome != null && !todayIncome.isEmpty() ? todayIncome : "Rp0");
            }

            // 4. Bottom Column 2: Total Balance with Privacy Toggle
            views.setTextViewText(R.id.tv_widget_balance_col2_label, context.getString(R.string.widget_total_balance_label));
            if (isBalanceHidden) {
                views.setTextViewText(R.id.tv_widget_balance_val, "••••••");
                views.setImageViewResource(R.id.btn_widget_balance_privacy, R.drawable.ic_widget_visibility_off);
            } else {
                views.setTextViewText(R.id.tv_widget_balance_val, balance != null && !balance.isEmpty() ? balance : "Rp0");
                views.setImageViewResource(R.id.btn_widget_balance_privacy, R.drawable.ic_widget_visibility);
            }

            // 5. Update sync timestamp label
            if (lastUpdated > 0) {
                SimpleDateFormat sdf = new SimpleDateFormat("HH:mm", Locale.getDefault());
                views.setTextViewText(R.id.tv_widget_updated, sdf.format(new Date(lastUpdated)));
            } else {
                views.setTextViewText(R.id.tv_widget_updated, "Live");
            }

            int flagImmutable = Build.VERSION.SDK_INT >= Build.VERSION_CODES.M ? PendingIntent.FLAG_IMMUTABLE : 0;

            // 6. Click Top Area -> Open Dashboard
            Intent dashIntent = new Intent(context, MainActivity.class);
            dashIntent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
            PendingIntent dashPendingIntent = PendingIntent.getActivity(
                    context,
                    101,
                    dashIntent,
                    PendingIntent.FLAG_UPDATE_CURRENT | flagImmutable
            );
            views.setOnClickPendingIntent(R.id.widget_balance_top_area, dashPendingIntent);

            // 7. Click Hero Expense Area -> Open Add Expense Sheet
            Intent expenseIntent = new Intent(context, MainActivity.class);
            expenseIntent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
            expenseIntent.putExtra("shortcut_action", "new_expense");
            PendingIntent expensePendingIntent = PendingIntent.getActivity(
                    context,
                    102,
                    expenseIntent,
                    PendingIntent.FLAG_UPDATE_CURRENT | flagImmutable
            );
            views.setOnClickPendingIntent(R.id.widget_balance_click_area, expensePendingIntent);

            // 8. Click Column 1 -> Add Expense / Income depending on budget
            Intent col1Intent = new Intent(context, MainActivity.class);
            col1Intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
            if (budgetRemaining != null && !budgetRemaining.trim().isEmpty()) {
                col1Intent.putExtra("shortcut_action", "new_expense");
            } else {
                col1Intent.putExtra("shortcut_action", "new_income");
            }
            PendingIntent col1PendingIntent = PendingIntent.getActivity(
                    context,
                    103,
                    col1Intent,
                    PendingIntent.FLAG_UPDATE_CURRENT | flagImmutable
            );
            views.setOnClickPendingIntent(R.id.btn_widget_balance_col1, col1PendingIntent);

            // 9. Click Column 2 (Balance) Area -> Open Wallets view
            Intent walletsIntent = new Intent(context, MainActivity.class);
            walletsIntent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
            walletsIntent.putExtra("shortcut_action", "wallets");
            PendingIntent walletsPendingIntent = PendingIntent.getActivity(
                    context,
                    104,
                    walletsIntent,
                    PendingIntent.FLAG_UPDATE_CURRENT | flagImmutable
            );
            views.setOnClickPendingIntent(R.id.btn_widget_balance_col2, walletsPendingIntent);

            // 10. Click Privacy Eye Toggle -> Broadcast ACTION_TOGGLE_PRIVACY
            Intent privacyIntent = new Intent(context, WangBalanceWidgetProvider.class);
            privacyIntent.setAction(ACTION_TOGGLE_PRIVACY);
            PendingIntent privacyPendingIntent = PendingIntent.getBroadcast(
                    context,
                    105,
                    privacyIntent,
                    PendingIntent.FLAG_UPDATE_CURRENT | flagImmutable
            );
            views.setOnClickPendingIntent(R.id.btn_widget_balance_privacy, privacyPendingIntent);

            appWidgetManager.updateAppWidget(appWidgetId, views);
        } catch (Exception e) {
            e.printStackTrace();
        }
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
