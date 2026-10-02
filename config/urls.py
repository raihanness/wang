from django.conf import settings
from django.contrib import admin
from django.urls import path, include, re_path
from django.views.static import serve
from django.contrib.auth import views as auth_views
from tracker.views import (
    WangLoginView,
    signup_view,
    signup_pending_view,
    WangPasswordChangeView,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    # Authentication & Registration
    path("accounts/login/", WangLoginView.as_view(), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("accounts/signup/", signup_view, name="signup"),
    path("accounts/signup/pending/", signup_pending_view, name="signup_pending"),
    # In-App Password Change (Authenticated)
    path("accounts/password-change/", WangPasswordChangeView.as_view(), name="password_change"),
    # Tracker Application Routes
    path("", include("tracker.urls")),
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
]

