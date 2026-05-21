from django.utils.cache import patch_cache_control

class DisableCachingMiddleware:
    """
    Middleware that adds 'Cache-Control: no-cache, no-store, must-revalidate'
    to every response. This ensures that browsers don't cache sensitive data
    and prevent the "Back" button from showing authenticated pages after logout.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        
        # Strict Cache-Control for all responses to prevent BFcache and local storage
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
        response['Pragma'] = 'no-cache'
        response['Expires'] = 'Fri, 01 Jan 1990 00:00:00 GMT'
        
        return response
class BlockStatusMiddleware:
    """
    Middleware that ensures any user who is blocked (is_active=False) 
    is immediately logged out of their current Django session.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.contrib.auth import logout
        from django.contrib import messages
        from django.shortcuts import redirect
        from django.urls import resolve, Resolver404

        # Use resolve to identify the view by its URL name
        try:
            view_name = resolve(request.path_info).url_name
        except Resolver404:
            view_name = None

        # Skip check for specific excluded URL names to avoid redirect loops or incorrect logout triggers
        excluded_view_names = ["login", "admin_logout", "api_login", "api_logout", "home"]
        if view_name in excluded_view_names:
            return self.get_response(request)

        if request.user.is_authenticated and not request.user.is_active:
            logout(request)
            messages.error(request, "Your account has been blocked. Please contact your administrator.")
            return redirect("login")

        response = self.get_response(request)
        return response




