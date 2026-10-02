from django.urls import path
from . import views

urlpatterns = [
    path("", views.signup_view, name="signup"),
    path("pending/", views.signup_pending_view, name="signup_pending"),
]
