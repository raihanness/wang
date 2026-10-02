from django.conf import settings
from .models import UserProfile


def wang_context(request):
    """
    Wang global context processor for template rendering.
    Provides Cloudflare Turnstile keys and admin badge notifications.
    """
    ctx = {
        "TURNSTILE_SITE_KEY": getattr(
            settings,
            "CLOUDFLARE_TURNSTILE_SITE_KEY",
            "1x00000000000000000000AA",
        ),
        "TURNSTILE_ENABLED": getattr(settings, "CLOUDFLARE_TURNSTILE_ENABLED", True),
        "pending_approvals_count": 0,
    }

    if hasattr(request, "user") and request.user.is_authenticated:
        if request.user.is_staff or request.user.is_superuser:
            ctx["pending_approvals_count"] = UserProfile.objects.filter(
                is_approved=False,
                approval_status="pending",
            ).count()

    return ctx
