package dev.raihan.wang;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.widget.RemoteViews;

public class WangQuickActionsWidgetProvider extends AppWidgetProvider {

    @Override
    public void onUpdate(Context context, AppWidgetManager appWidgetManager, int[] appWidgetIds) {
        for (int appWidgetId : appWidgetIds) {
            updateAppWidget(context, appWidgetManager, appWidgetId);
        }
    }

    public static void updateAppWidget(Context context, AppWidgetManager appWidgetManager, int appWidgetId) {
        RemoteViews views = new RemoteViews(context.getPackageName(), R.layout.widget_quick_actions);

        // 1. Add Expense
        Intent expenseIntent = new Intent(context, MainActivity.class);
        expenseIntent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        expenseIntent.putExtra("shortcut_action", "new_expense");
        PendingIntent expensePendingIntent = PendingIntent.getActivity(
                context,
                201,
                expenseIntent,
                PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M ? PendingIntent.FLAG_IMMUTABLE : 0)
        );
        views.setOnClickPendingIntent(R.id.btn_bar_expense, expensePendingIntent);

        // 2. Add Income
        Intent incomeIntent = new Intent(context, MainActivity.class);
        incomeIntent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        incomeIntent.putExtra("shortcut_action", "new_income");
        PendingIntent incomePendingIntent = PendingIntent.getActivity(
                context,
                202,
                incomeIntent,
                PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M ? PendingIntent.FLAG_IMMUTABLE : 0)
        );
        views.setOnClickPendingIntent(R.id.btn_bar_income, incomePendingIntent);

        // 3. Graphs
        Intent graphsIntent = new Intent(context, MainActivity.class);
        graphsIntent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        graphsIntent.putExtra("shortcut_action", "graphs");
        PendingIntent graphsPendingIntent = PendingIntent.getActivity(
                context,
                203,
                graphsIntent,
                PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M ? PendingIntent.FLAG_IMMUTABLE : 0)
        );
        views.setOnClickPendingIntent(R.id.btn_bar_graphs, graphsPendingIntent);

        // 4. Wallets
        Intent walletsIntent = new Intent(context, MainActivity.class);
        walletsIntent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        walletsIntent.putExtra("shortcut_action", "wallets");
        PendingIntent walletsPendingIntent = PendingIntent.getActivity(
                context,
                204,
                walletsIntent,
                PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M ? PendingIntent.FLAG_IMMUTABLE : 0)
        );
        views.setOnClickPendingIntent(R.id.btn_bar_wallets, walletsPendingIntent);

        appWidgetManager.updateAppWidget(appWidgetId, views);
    }
}
