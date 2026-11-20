from django.conf import settings
from .models import UserProfile


def wang_context(request):
    """
    Wang global context processor for template rendering.
    Provides Cloudflare Turnstile keys, admin badge notifications, and Turbo Frame request detection.
    """
    # Only strip #sheet-root-container and #wang-svg-sprite-holder on sub-frame (<turbo-frame>) requests,
    # NEVER on full-URL page requests. If a full-URL response omits #sheet-root-container, the browser or
    # Android WebView HTTP disk cache overwrites the cached HTML for that URL with an empty sheet container,
    # breaking the Add Transaction bottom sheet on offline cold-start!
    is_turbo_frame = bool(getattr(request, "headers", {}).get("Turbo-Frame"))
    ctx = {
        "TURNSTILE_SITE_KEY": getattr(
            settings,
            "CLOUDFLARE_TURNSTILE_SITE_KEY",
            "1x00000000000000000000AA",
        ),
        "TURNSTILE_ENABLED": getattr(settings, "CLOUDFLARE_TURNSTILE_ENABLED", True),
        "pending_approvals_count": 0,
        "is_turbo_request": is_turbo_frame,
        "is_turbo_frame": is_turbo_frame,
        "APP_VERSION": getattr(settings, "APP_VERSION", "2.1.0"),
    }

    if hasattr(request, "user") and request.user.is_authenticated:
        if request.user.is_staff or request.user.is_superuser:
            ctx["pending_approvals_count"] = UserProfile.objects.filter(
                is_approved=False,
                approval_status="pending",
            ).count()

    return ctx
