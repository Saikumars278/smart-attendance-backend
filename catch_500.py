import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Attendanceback.settings')
django.setup()

from django.test import RequestFactory
from django.contrib.auth import get_user_model
from Attendanceapp.views import admin_leave_approval

User = get_user_model()
admin_user = User.objects.filter(is_admin=True).first()

if not admin_user:
    print("No admin user found")
    sys.exit(1)

factory = RequestFactory()
request = factory.get('/leave-approvals/')
request.user = admin_user

try:
    response = admin_leave_approval(request)
    print("Status code:", response.status_code)
except Exception as e:
    import traceback
    traceback.print_exc()
