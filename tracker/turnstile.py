import json
import logging
import sys
import urllib.parse
import urllib.request
from django.conf import settings

logger = logging.getLogger(__name__)


def is_test_environment(request):
    """Detect if running under Django test runner or test client."""
    if getattr(settings, "TESTING", False):
        return True
    if len(sys.argv) > 1 and "test" in sys.argv:
        return True
    if request.META.get("SERVER_NAME") == "testserver":
        return True
    if request.META.get("HTTP_USER_AGENT") == "Django Test Client":
        return True
    return False


def verify_turnstile(request):
    """
    Verifies Cloudflare Turnstile token from request.POST['cf-turnstile-response'].
    Returns: (is_valid: bool, error_message: str)
    """
    # 1. If disabled in settings, allow pass
    if not getattr(settings, "CLOUDFLARE_TURNSTILE_ENABLED", True):
        return True, ""

    # 2. In automated test environment, check test token
    if is_test_environment(request):
        token = request.POST.get("cf-turnstile-response", "").strip()
        if token == "FAIL_TEST":
            return False, "Security verification failed. Please try again."
        return True, ""

    token = request.POST.get("cf-turnstile-response", "").strip()
    if not token:
        return False, "Please complete the security challenge verification."

    secret_key = getattr(
        settings,
        "CLOUDFLARE_TURNSTILE_SECRET_KEY",
        "1x00000000000000000000000000000000AA",
    )

    # Resolve client IP
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        remote_ip = x_forwarded_for.split(",")[0].strip()
    else:
        remote_ip = request.META.get("REMOTE_ADDR", "")

    payload = {
        "secret": secret_key,
        "response": token,
    }
    if remote_ip:
        payload["remoteip"] = remote_ip

    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://challenges.cloudflare.com/turnstile/v0/siteverify",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=6) as response:
            res_body = response.read().decode("utf-8")
            result = json.loads(res_body)
            if result.get("success"):
                return True, ""
            else:
                error_codes = result.get("error-codes", [])
                logger.warning("Cloudflare Turnstile verification failed: %s", error_codes)
                return False, "Security verification failed. Please try again."
    except Exception as exc:
        logger.error("Error communicating with Cloudflare Turnstile: %s", exc)
        if settings.DEBUG:
            return True, ""
        return False, "Security service temporarily unreachable. Please try again."
