from django.contrib import messages
from django.contrib.auth import logout as auth_logout
from django.shortcuts import redirect


class AccountApprovalMiddleware:
    """
    Ensures that active sessions for deactivated or unapproved accounts are immediately
    terminated mid-session rather than allowing them to persist until cookie expiry.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            # Bypass staff and superusers
            if not request.user.is_staff and not request.user.is_superuser:
                # 1. Deactivated user check
                if not request.user.is_active:
                    auth_logout(request)
                    messages.error(
                        request,
                        "Your account has been deactivated. Please contact an administrator.",
                    )
                    return redirect("login")

                # 2. Administrator approval check
                profile = getattr(request.user, "profile", None)
                if profile and not profile.is_approved:
                    status = profile.approval_status
                    auth_logout(request)
                    if status == "rejected":
                        messages.error(
                            request,
                            "Your account access was rejected by an administrator.",
                        )
                    else:
                        messages.warning(
                            request,
                            "Your account is pending administrator approval. Please wait for an admin to activate your access.",
                        )
                    return redirect("login")
        elif request.session.get("_auth_user_id"):
            # Session exists but user was rejected/deactivated (e.g., is_active=False rejected by auth backend)
            auth_logout(request)
            messages.error(
                request,
                "Your account has been deactivated. Please contact an administrator.",
            )
            return redirect("login")

        return self.get_response(request)
