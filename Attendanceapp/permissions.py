from rest_framework import permissions
from django.utils import timezone
from .models import UserSession

class IsWithinSessionLimit(permissions.BasePermission):
    """
    Allows access only if the user has 6 or fewer active sessions.
    This ensures users manually logout of old sessions once they reach the limit.
    """
    message = "Device limit reached. Please manage your active sessions to continue."
    code = "session_limit_exceeded"

    def has_permission(self, request, view):
        # 1. Access is always allowed if the request is not authenticated yet (e.g., Login)
        if not request.user or not request.user.is_authenticated:
            return True

        # 2. Check the flag set by UserSessionAuthentication
        # If the flag is not set, we calculate it here as a fallback
        limit_exceeded = getattr(request, '_session_limit_exceeded', None)
        
        if limit_exceeded is None:
            active_count = UserSession.objects.filter(
                user=request.user, 
                expires_at__gt=timezone.now()
            ).count()
            limit_exceeded = active_count > 6

        # 3. Block access if over 6 sessions
        return not limit_exceeded
