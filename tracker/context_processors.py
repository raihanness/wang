from django.conf import settings
from .models import UserProfile


def wang_context(request):
    """
    Wang global context processor for template rendering.
    Provides Cloudflare Turnstile keys, admin badge notifications, and Turbo request detection.
    """
    is_turbo = bool(
        getattr(request, "headers", {}).get("X-Turbo-Request") == "1"
        or getattr(request, "headers", {}).get("Turbo-Frame") is not None
    )
    ctx = {
        "TURNSTILE_SITE_KEY": getattr(
            settings,
            "CLOUDFLARE_TURNSTILE_SITE_KEY",
            "1x00000000000000000000AA",
        ),
        "TURNSTILE_ENABLED": getattr(settings, "CLOUDFLARE_TURNSTILE_ENABLED", True),
        "pending_approvals_count": 0,
        "is_turbo_request": is_turbo,
    }

    if hasattr(request, "user") and request.user.is_authenticated:
        if request.user.is_staff or request.user.is_superuser:
            ctx["pending_approvals_count"] = UserProfile.objects.filter(
                is_approved=False,
                approval_status="pending",
            ).count()

    return ctx
