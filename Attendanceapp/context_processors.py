from .models import LeaveRequest, Permission

def pending_counts(request):
    """
    Returns the count of pending leave and permission requests 
    to be displayed in the admin navbar badges.
    """
    if request.user.is_authenticated and request.user.is_admin:
        return {
            'pending_leaves_count': LeaveRequest.objects.filter(status='Pending').count(),
            'pending_permissions_count': Permission.objects.filter(status='Pending').count(),
        }
    return {
        'pending_leaves_count': 0,
        'pending_permissions_count': 0,
    }
