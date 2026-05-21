
from django.contrib import admin
from django.urls import path
from Attendanceapp import views
from Attendanceapp.views import attendance_history

urlpatterns = [
    path("admin/", admin.site.urls),                
    path("login/", views.login_page, name="login"), 
    path("", views.login_page, name="home"), 
    path("home/", views.attendance_dashboard, name="home_page"),
    path("employeemanagement/", views.employeemanagement, name="employeemanagement"),
    path("employee/add/", views.add_employee, name="add_employee"),
    path("employee/<int:employee_id>/edit/", views.edit_employee, name="edit_employee"),
    path("employee/<int:employee_id>/delete/", views.delete_employee, name="delete_employee"),
    path("employee/<int:employee_id>/toggle-block/", views.toggle_employee_block, name="toggle_employee_block"),
    path("logout/", views.logout_page, name="admin_logout"),
    path("export-attendance/", views.export_attendance_excel, name="export_attendance_excel"),
    path("export-leaves/", views.export_leave_excel, name="export_leave_excel"),

    # ✅ Admin HTML UI (Templates)
    path("leave-approvals/", views.admin_leave_approval, name="admin_leave_approval"),
    path("leave-approvals/update/", views.admin_update_leave, name="admin_update_leave"),
    path("permission-approvals/", views.admin_permission_approval, name="admin_permission_approval"),
    path("permission-approvals/update/", views.admin_update_permission, name="admin_update_permission"),
    path("system-notifications/", views.admin_notifications, name="admin_notifications"),

    # ✅ API Endpoints
    path("api/accounts/login/", views.login_view, name="api_login"),
    path("api/accounts/logout/", views.logout_view, name="api_logout"),
    path("api/attendance/today/", views.today_attendance, name="today_attendance"),
    path("api/attendance/checkin/", views.check_in, name="check_in"),
    path("api/attendance/checkout/", views.check_out, name="check_out"),
    path("api/attendance/history/", attendance_history, name="attendance-history"),

    # ✅ Missing API routes for employee + permission
    path("api/employee/me/", views.get_employee_details, name="employee-details"),
    path("api/permission/create/", views.create_permission_request, name="create-permission"),
    path("api/permission/list/", views.list_permissions, name="list-permissions"),
    path("api/accounts/forgot-password/", views.forgot_password, name="forgot_password"),

    # ✅ Leave APIs
    path("api/leave/request/", views.create_leave_request, name="create-leave"),
    path("api/leave/history/", views.list_employee_leaves, name="leave-history"),

    # ✅ Admin Leave Approval APIs
    path("api/admin/leave/requests/", views.get_all_leave_requests, name="admin-leave-list"),
    path("api/admin/leave/approve/", views.update_leave_status, name="admin-leave-approve"),

    # ✅ Notification APIs
    path("api/notifications/", views.get_notifications, name="notifications-list"),
    path("api/notifications/read/", views.mark_notification_read, name="notification-read"),
    path("api/notifications/<int:notif_id>/delete/", views.delete_notification, name="notification-delete"),

    # ✅ Admin Notification Management APIs
    path("api/admin/employees/", views.get_all_employees_api, name="admin-employee-list"),
    path("api/admin/notifications/send/", views.admin_send_notification_api, name="admin-send-notification"),
]
