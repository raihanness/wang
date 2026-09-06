from django.urls import path
from django.shortcuts import redirect
from django.contrib import messages

def signup(request):
    messages.info(request, "Registration is disabled. Please contact the administrator for an account.")
    return redirect("login")

urlpatterns = [
    path("", signup, name="signup"),
]
