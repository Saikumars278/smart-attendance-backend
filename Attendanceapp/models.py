

import datetime
import pytz
from django.db import models
from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone


# ----------------------------
# Custom User Manager
# ----------------------------
class UserManager(BaseUserManager):
    def create_user(self, email, name, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user = self.model(email=email, name=name, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, name, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_admin", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, name, password, **extra_fields)


# ----------------------------
# Custom User Model
# ----------------------------
class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_admin = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    def __str__(self):
        return self.email


# ----------------------------
# Department Model
# ----------------------------
class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


# ----------------------------
# Employee Model
# ----------------------------
class Employee(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    employee_id = models.CharField(max_length=20, unique=True, editable=False)
    phone = models.CharField(max_length=15, blank=True, null=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)
    raw_password = models.CharField(max_length=50, blank=True, null=True)
    
    # New Fields based on reference UI
    joining_date = models.DateField(null=True, blank=True)
    account_number = models.CharField(max_length=25, null=True, blank=True)
    ifsc_code = models.CharField(max_length=20, null=True, blank=True)
    bank_name = models.CharField(max_length=100, null=True, blank=True)
    pan_number = models.CharField(max_length=15, null=True, blank=True)
    aadhaar_card_number = models.CharField(max_length=20, null=True, blank=True)
    address = models.TextField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.employee_id and self.department:
            prefix_map = {
                "HR": "NIMH",
                "Developer": "NIMD",
                "Intern": "NIMI",
                "UI/UX Designer": "NIMU",
                "Sales": "NIMS",
                "Marketing": "NIMM",
                "Developer Intern": "NIMDI",
                "HR Intern": "NIMHI",
                "Sales Intern": "NIMSI",
                "Marketing Intern": "NIMMI",
                "UI/UX Designer Intern": "NIMUI"
            }
            prefix = prefix_map.get(self.department.name, "NIMX")
            
            # Find the last employee in this department to determine the next sequence number
            last_in_dept = Employee.objects.filter(department=self.department).order_by("-id").first()
            
            if last_in_dept and last_in_dept.employee_id.startswith(prefix):
                try:
                    # Extracts the numeric part following the prefix
                    last_num_str = last_in_dept.employee_id[len(prefix):]
                    next_num = int(last_num_str) + 1
                except (ValueError, IndexError):
                    next_num = 1
            else:
                next_num = 1
                
            self.employee_id = f"{prefix}{next_num:03d}"
        
        # Absolute fallback if still no employee_id
        if not self.employee_id:
            last_emp = Employee.objects.order_by("-id").first()
            next_val = (last_emp.id + 1) if last_emp else 1
            self.employee_id = f"EMP{next_val:05d}"
            
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.employee_id} - {self.user.name}"


# ----------------------------
# Helper function for default date
# ----------------------------
def default_date():
    return timezone.now().date()


# ----------------------------
# Permission Model
# ----------------------------
class Permission(models.Model):
    STATUS_CHOICES = [
        ("Pending", "Pending"),
        ("Approved", "Approved"),
        ("Rejected", "Rejected"),
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    date = models.DateField(default=default_date)
    start_time = models.TimeField()
    end_time = models.TimeField()
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="Pending")

    def __str__(self):
        return f"{self.employee.user.name} - {self.date} ({self.status})"

    @property
    def duration_hours(self):
        """Safe duration calculation (handles both str and datetime.time)."""
        start_time = self.start_time
        end_time = self.end_time

        if isinstance(start_time, str):
            start_time = datetime.datetime.strptime(start_time, "%H:%M").time()
        if isinstance(end_time, str):
            end_time = datetime.datetime.strptime(end_time, "%H:%M").time()

        start = datetime.datetime.combine(self.date, start_time)
        end = datetime.datetime.combine(self.date, end_time)

        return round((end - start).total_seconds() / 3600, 2)


# ----------------------------
# LeaveRequest Model
# ----------------------------
class LeaveRequest(models.Model):
    STATUS_CHOICES = [
        ("Pending", "Pending"),
        ("Approved", "Approved"),
        ("Rejected", "Rejected"),
    ]
    LEAVE_TYPE_CHOICES = [
        ("Sick Leave", "Sick Leave"),
        ("Casual Leave", "Casual Leave"),
        ("Loss of Pay", "Loss of Pay"),
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    leave_type = models.CharField(max_length=20, choices=LEAVE_TYPE_CHOICES)
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="Pending")
    requested_type = models.CharField(max_length=20, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.employee.user.name} - {self.leave_type} ({self.start_date} to {self.end_date})"


# ----------------------------
# Notification Model
# ----------------------------
class Notification(models.Model):
    TYPE_CHOICES = [
        ("info", "Info"),
        ("success", "Success"),
        ("warning", "Warning"),
        ("danger", "Danger"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    message = models.TextField()
    notification_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default="info")
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.name} - {self.title} ({self.notification_type})"


# ----------------------------
# Attendance Model
# ----------------------------
class Attendance(models.Model):
    STATUS_CHOICES = [
        ("Present", "Present"),
        ("Absent", "Absent"),
        ("Late", "Late"),
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, db_index=True)
    date = models.DateField(default=default_date, db_index=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="Absent")
    check_in = models.DateTimeField(null=True, blank=True)
    check_out = models.DateTimeField(null=True, blank=True)
    remarks = models.TextField(null=True, blank=True)
    work_mode = models.CharField(max_length=50, default="Office")

    class Meta:
        unique_together = ("employee", "date")

    def save(self, *args, **kwargs):
        """Auto-assign status and remarks based on check-in time."""
        IST = pytz.timezone("Asia/Kolkata")

        # If WFH, status is always WFH regardless of time
        if self.work_mode == "WFH":
            self.status = "WFH"
            if self.check_in and not self.remarks:
                check_in_ist = self.check_in.astimezone(IST)
                self.remarks = f"Remote check-in at {check_in_ist.strftime('%I:%M %p')} IST (WFH)"
            elif not self.check_in:
                self.remarks = "WFH - No check-in yet"
            super().save(*args, **kwargs)
            return

        if self.check_in:
            check_in_ist = self.check_in.astimezone(IST)
            check_in_time = check_in_ist.time()

            # Before 9:45: Present (including early)
            if check_in_time <= datetime.time(9, 45):
                self.status = "Present"
                if not self.remarks:
                    self.remarks = f"Checked in at {check_in_ist.strftime('%I:%M %p')} IST (Present)"
            # 9:46 - 11:00: Late
            elif check_in_time <= datetime.time(11, 0):
                self.status = "Late"
                if not self.remarks:
                    self.remarks = f"Checked in at {check_in_ist.strftime('%I:%M %p')} IST (Late)"
            # After 11:00: Absent
            else:
                self.status = "Absent"
                if not self.remarks:
                    self.remarks = f"Checked in at {check_in_ist.strftime('%I:%M %p')} IST (Absent - After 11:00 AM)"
        else:
            self.status = "Absent"
            if not self.remarks:
                self.remarks = "No check-in recorded"

        super().save(*args, **kwargs)

    @property
    def working_hours(self):
        """Calculate working hours after subtracting approved permissions."""
        if self.check_in and self.check_out:
            total_time = self.check_out - self.check_in

            # Subtract approved permission hours (if any)
            permissions = Permission.objects.filter(
                employee=self.employee,
                date=self.date,
                status="Approved",
            )
            for p in permissions:
                start = datetime.datetime.combine(self.date, p.start_time)
                end = datetime.datetime.combine(self.date, p.end_time)
                total_time -= (end - start)

            return round(total_time.total_seconds() / 3600, 2)
        return 0

# ----------------------------
# UserSession Model
# ----------------------------
class UserSession(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sessions')
    token = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    user_agent = models.TextField(null=True, blank=True)

    def is_valid(self):
        return self.expires_at > timezone.now()

    def __str__(self):
        return f"{self.user.email} - {self.token[:8]}..."
