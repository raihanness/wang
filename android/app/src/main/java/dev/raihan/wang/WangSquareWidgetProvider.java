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

public class WangSquareWidgetProvider extends AppWidgetProvider {

    public static final String ACTION_TOGGLE_PRIVACY = "dev.raihan.wang.ACTION_TOGGLE_PRIVACY";

    @Override
    public void onReceive(Context context, Intent intent) {
        super.onReceive(context, intent);
        if (ACTION_TOGGLE_PRIVACY.equals(intent.getAction())) {
            SharedPreferences prefs = context.getSharedPreferences(MainActivity.PREFS_NAME, Context.MODE_PRIVATE);
            boolean current = prefs.getBoolean("widget_balance_hidden", false);
            prefs.edit().putBoolean("widget_balance_hidden", !current).apply();

            WangSquareWidgetProvider.updateAllWidgets(context);
            WangBalanceWidgetProvider.updateAllWidgets(context);
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

            RemoteViews views = new RemoteViews(context.getPackageName(), R.layout.widget_today_square);

            // 1. Current Live Date (e.g. "Wed, 06 Oct 2026")
            SimpleDateFormat sdf = new SimpleDateFormat("EEE, dd MMM yyyy", Locale.getDefault());
            views.setTextViewText(R.id.tv_widget_date, sdf.format(new Date()));

            // 2. Hero Section: Today's Expense
            views.setTextViewText(R.id.tv_widget_hero_label, context.getString(R.string.widget_today_expenses_label));
            views.setTextViewText(R.id.tv_widget_hero_amount, todaySpent != null && !todaySpent.isEmpty() ? todaySpent : "Rp0");

            // 3. Bottom Column 1: Remaining Budget (fallback to Today's Income if no budget set)
            if (budgetRemaining != null && !budgetRemaining.trim().isEmpty()) {
                String lbl = (budgetLabel != null && !budgetLabel.trim().isEmpty())
                        ? budgetLabel.toUpperCase(Locale.getDefault())
                        : context.getString(R.string.widget_daily_budget_label);
                views.setTextViewText(R.id.tv_widget_square_col1_label, lbl);
                views.setTextViewText(R.id.tv_widget_square_col1_val, budgetRemaining);
            } else {
                views.setTextViewText(R.id.tv_widget_square_col1_label, context.getString(R.string.widget_today_income_label));
                views.setTextViewText(R.id.tv_widget_square_col1_val, todayIncome != null && !todayIncome.isEmpty() ? todayIncome : "Rp0");
            }

            // 4. Bottom Column 2: Total Balance with Privacy Toggle
            views.setTextViewText(R.id.tv_widget_square_col2_label, context.getString(R.string.widget_total_balance_label));
            if (isBalanceHidden) {
                views.setTextViewText(R.id.tv_widget_square_balance, "••••••");
                views.setImageViewResource(R.id.btn_widget_square_privacy, R.drawable.ic_widget_visibility_off);
            } else {
                views.setTextViewText(R.id.tv_widget_square_balance, balance != null && !balance.isEmpty() ? balance : "Rp0");
                views.setImageViewResource(R.id.btn_widget_square_privacy, R.drawable.ic_widget_visibility);
            }

            int flagImmutable = Build.VERSION.SDK_INT >= Build.VERSION_CODES.M ? PendingIntent.FLAG_IMMUTABLE : 0;

            // 5. PendingIntent: Dashboard (Top Area)
            Intent dashIntent = new Intent(context, MainActivity.class);
            dashIntent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
            PendingIntent dashPendingIntent = PendingIntent.getActivity(
                    context,
                    201,
                    dashIntent,
                    PendingIntent.FLAG_UPDATE_CURRENT | flagImmutable
            );
            views.setOnClickPendingIntent(R.id.widget_square_top_area, dashPendingIntent);

            // 6. PendingIntent: Hero Expense Area -> Log New Expense
            Intent expenseIntent = new Intent(context, MainActivity.class);
            expenseIntent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
            expenseIntent.putExtra("shortcut_action", "new_expense");
            PendingIntent expensePendingIntent = PendingIntent.getActivity(
                    context,
                    202,
                    expenseIntent,
                    PendingIntent.FLAG_UPDATE_CURRENT | flagImmutable
            );
            views.setOnClickPendingIntent(R.id.widget_square_balance_area, expensePendingIntent);

            // 7. PendingIntent: Column 1 Click -> Add Expense / Income depending on budget presence
            Intent col1Intent = new Intent(context, MainActivity.class);
            col1Intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
            if (budgetRemaining != null && !budgetRemaining.trim().isEmpty()) {
                col1Intent.putExtra("shortcut_action", "new_expense");
            } else {
                col1Intent.putExtra("shortcut_action", "new_income");
            }
            PendingIntent col1PendingIntent = PendingIntent.getActivity(
                    context,
                    203,
                    col1Intent,
                    PendingIntent.FLAG_UPDATE_CURRENT | flagImmutable
            );
            views.setOnClickPendingIntent(R.id.btn_widget_square_col1, col1PendingIntent);

            // 8. PendingIntent: Column 2 (Balance) Click -> Open Wallets view
            Intent walletsIntent = new Intent(context, MainActivity.class);
            walletsIntent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
            walletsIntent.putExtra("shortcut_action", "wallets");
            PendingIntent walletsPendingIntent = PendingIntent.getActivity(
                    context,
                    204,
                    walletsIntent,
                    PendingIntent.FLAG_UPDATE_CURRENT | flagImmutable
            );
            views.setOnClickPendingIntent(R.id.btn_widget_square_col2, walletsPendingIntent);

            // 9. PendingIntent: Privacy Eye Toggle -> Broadcast ACTION_TOGGLE_PRIVACY
            Intent privacyIntent = new Intent(context, WangSquareWidgetProvider.class);
            privacyIntent.setAction(ACTION_TOGGLE_PRIVACY);
            PendingIntent privacyPendingIntent = PendingIntent.getBroadcast(
                    context,
                    205,
                    privacyIntent,
                    PendingIntent.FLAG_UPDATE_CURRENT | flagImmutable
            );
            views.setOnClickPendingIntent(R.id.btn_widget_square_privacy, privacyPendingIntent);

            appWidgetManager.updateAppWidget(appWidgetId, views);
        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    public static void updateAllWidgets(Context context) {
        try {
            AppWidgetManager appWidgetManager = AppWidgetManager.getInstance(context);
            ComponentName thisWidget = new ComponentName(context, WangSquareWidgetProvider.class);
            int[] allWidgetIds = appWidgetManager.getAppWidgetIds(thisWidget);
            for (int widgetId : allWidgetIds) {
                updateAppWidget(context, appWidgetManager, widgetId);
            }
        } catch (Exception ignored) {}
    }
}
