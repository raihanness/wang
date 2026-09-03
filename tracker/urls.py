from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("wallets/", views.wallet_list, name="wallet_list"),
    path("wallets/new/", views.wallet_create, name="wallet_create"),
    path("wallets/<int:pk>/edit/", views.wallet_edit, name="wallet_edit"),
    path("wallets/<int:pk>/toggle/", views.wallet_toggle_archive, name="wallet_toggle_archive"),
    path("categories/", views.category_list, name="category_list"),
    path("categories/new/", views.category_create, name="category_create"),
    path("categories/<int:pk>/edit/", views.category_edit, name="category_edit"),
    path("categories/<int:pk>/delete/", views.category_delete, name="category_delete"),
    path("transactions/", views.transaction_list, name="transaction_list"),
    path("transactions/new/", views.transaction_create, name="transaction_create"),
    path("transactions/<int:pk>/edit/", views.transaction_edit, name="transaction_edit"),
    path("transactions/<int:pk>/delete/", views.transaction_delete, name="transaction_delete"),
]
