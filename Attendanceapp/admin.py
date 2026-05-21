from django.contrib import admin
from .models import Employee, Department

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("employee_id", "get_name", "phone", "department", "raw_password")

    def get_name(self, obj):
        return obj.user.first_name
    get_name.short_description = "Employee Name"

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
