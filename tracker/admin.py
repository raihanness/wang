from django.contrib import admin
from .models import Wallet, Category, Transaction, Subscription, Budget

@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "type", "initial_balance", "archived")
    list_filter = ("type", "archived")

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "kind", "icon")
    list_filter = ("kind",)

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("date", "user", "kind", "amount", "wallet", "category", "from_wallet", "to_wallet")
    list_filter = ("kind", "date")

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "amount", "cycle", "active", "last_paid_date")
    list_filter = ("cycle", "active")

@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ("user", "category", "amount", "updated_at")
    list_filter = ("category",)

