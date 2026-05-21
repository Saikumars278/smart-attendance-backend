from rest_framework import authentication
from rest_framework import exceptions
from django.utils import timezone
from .models import UserSession

class UserSessionAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        auth_header = request.META.get('HTTP_AUTHORIZATION')
        if not auth_header:
            return None


        # Standard "Token <key>" format
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != 'token':
            return None

        token_key = parts[1]
        try:
            session = UserSession.objects.select_related('user').get(token=token_key)
        except UserSession.DoesNotExist:
            raise exceptions.AuthenticationFailed('Invalid session token')

        if not session.is_valid():
            # Cleanup expired session if hit
            session.delete()
            raise exceptions.AuthenticationFailed('Session has expired')

        if not session.user.is_active:
            raise exceptions.PermissionDenied('Your account has been blocked. Please contact your administrator.')

        # Tag the request with the session limit status
        active_count = UserSession.objects.filter(user=session.user, expires_at__gt=timezone.now()).count()
        request._session_limit_exceeded = active_count > 6

        return (session.user, session)
