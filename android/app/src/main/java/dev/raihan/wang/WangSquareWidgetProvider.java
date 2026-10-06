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

            RemoteViews views = new RemoteViews(context.getPackageName(), R.layout.widget_today_square);

            // 1. Current Live Date (e.g. "Wed, 06 Oct 2026")
            SimpleDateFormat sdf = new SimpleDateFormat("EEE, dd MMM yyyy", Locale.getDefault());
            views.setTextViewText(R.id.tv_widget_date, sdf.format(new Date()));

            // 2. Total Balance
            views.setTextViewText(R.id.tv_widget_balance, balance != null && !balance.isEmpty() ? balance : "Rp0");

            // 3. Today's Expenses & Income
            views.setTextViewText(R.id.tv_widget_today_expenses, todaySpent != null && !todaySpent.isEmpty() ? todaySpent : "Rp0");
            views.setTextViewText(R.id.tv_widget_today_income, todayIncome != null && !todayIncome.isEmpty() ? todayIncome : "Rp0");

            // 4. PendingIntent: Dashboard
            Intent dashIntent = new Intent(context, MainActivity.class);
            dashIntent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
            PendingIntent dashPendingIntent = PendingIntent.getActivity(
                    context,
                    201,
                    dashIntent,
                    PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M ? PendingIntent.FLAG_IMMUTABLE : 0)
            );
            views.setOnClickPendingIntent(R.id.widget_square_top_area, dashPendingIntent);
            views.setOnClickPendingIntent(R.id.widget_square_balance_area, dashPendingIntent);

            // 5. PendingIntent: Add Expense
            Intent expenseIntent = new Intent(context, MainActivity.class);
            expenseIntent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
            expenseIntent.putExtra("shortcut_action", "new_expense");
            PendingIntent expensePendingIntent = PendingIntent.getActivity(
                    context,
                    202,
                    expenseIntent,
                    PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M ? PendingIntent.FLAG_IMMUTABLE : 0)
            );
            views.setOnClickPendingIntent(R.id.btn_widget_square_expense, expensePendingIntent);

            // 6. PendingIntent: Add Income
            Intent incomeIntent = new Intent(context, MainActivity.class);
            incomeIntent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
            incomeIntent.putExtra("shortcut_action", "new_income");
            PendingIntent incomePendingIntent = PendingIntent.getActivity(
                    context,
                    203,
                    incomeIntent,
                    PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M ? PendingIntent.FLAG_IMMUTABLE : 0)
            );
            views.setOnClickPendingIntent(R.id.btn_widget_square_income, incomePendingIntent);

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
