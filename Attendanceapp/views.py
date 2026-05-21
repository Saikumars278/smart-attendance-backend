from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q
from datetime import datetime, date, time, timedelta
from io import BytesIO
import openpyxl
import string, secrets
import pytz
import calendar
import traceback
from datetime import datetime, date, time, timedelta

# DRF imports
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from .authentication import UserSessionAuthentication
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from rest_framework import serializers
from .permissions import IsWithinSessionLimit

# Models and serializers
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from .models import Employee, Department, Attendance, Permission, User, LeaveRequest, Notification, UserSession
from .serializers import EmployeeSerializer, PermissionSerializer, LeaveRequestSerializer, NotificationSerializer
import secrets

User = get_user_model()
IST = pytz.timezone("Asia/Kolkata")


CUTOFF_TIME = time(9, 45)  
ABSENT_TIME = time(11, 0)   



# def login_page(request):
#     if request.method == "POST":
#         email = request.POST.get("username")
#         password = request.POST.get("password")
        
#         # Check if user exists but is inactive
#         try:
#             temp_user = User.objects.get(email=email)
#             if not temp_user.is_active:
#                 messages.error(request, "Your account has been blocked. Please contact your administrator.")
#                 return redirect("login")
#         except User.DoesNotExist:
#             pass

#         user = authenticate(request, username=email, password=password)
#         if user and user.is_admin:
#             login(request, user)
#             return redirect("home_page")
        
#         messages.error(request, "Invalid credentials or not an admin user.")
#         return redirect("login")
#     return render(request, "login.html")


def login_page(request):
    if request.method == "POST":
        email = request.POST.get("username")
        password = request.POST.get("password")

        try:
            temp_user = User.objects.get(email=email)
            if not temp_user.is_active:
                messages.error(request, "Your account has been blocked.")
                return redirect("login")
        except User.DoesNotExist:
            pass

        user = authenticate(request, username=email, password=password)

        if user and getattr(user, "is_admin", False):
            login(request, user)
            return redirect("home_page")

        messages.error(request, "Invalid credentials or not an admin user.")
        return redirect("login")

    return render(request, "login.html")


@login_required(login_url="login")
def logout_page(request):
    logout(request)
    return redirect("login")



@login_required(login_url="login")
def attendance_dashboard(request):
    # ✅ FIX 1: Safe check for is_admin to prevent 500 on AnonymousUser
    if not getattr(request.user, 'is_admin', False):
        messages.error(request, "Admin access only")
        return redirect("login")

    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    employee_filter = request.GET.get("employee", "")
    department_filter = request.GET.get("department", "")

    # ✅ Safe date parsing
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else date.today()
        end = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else start
    except (ValueError, TypeError):
        start = end = date.today()

    attendance_qs = Attendance.objects.select_related(
        "employee__user", "employee__department"
    ).filter(date__range=(start, end))

    if employee_filter:
        attendance_qs = attendance_qs.filter(
            Q(employee__employee_id__icontains=employee_filter) |
            Q(employee__user__name__icontains=employee_filter)
        )

    if department_filter:
        attendance_qs = attendance_qs.filter(employee__department_id=department_filter)

    # ✅ FIX 2: correct key (employee.id, not employee_id)
    attendance_map = {(a.employee.id, a.date): a for a in attendance_qs}

    updated_attendance = []
    employees = Employee.objects.select_related("user", "department").all()

    if department_filter:
        employees = employees.filter(department_id=department_filter)

    current_date = start
    while current_date <= end:
        for emp in employees:
            record = attendance_map.get((emp.id, current_date))

            if record:
                record.permissions_list = list(
                    Permission.objects.filter(employee=emp, date=current_date)
                )

                record.calculated_hours = None

                if not record.check_in:
                    record.status = "Absent"
                    record.check_in_str = "-"
                    record.check_out_str = "-"
                else:
                    if record.work_mode == "WFH":
                        record.status = "WFH"
                    else:
                        local_checkin = record.check_in.astimezone(IST).time()

                        if local_checkin <= time(9, 45):
                            record.status = "Present"
                        elif local_checkin <= time(11, 0):
                            record.status = "Late"
                        else:
                            record.status = "Absent"

                    record.check_in_str = record.check_in.astimezone(IST).strftime("%I:%M %p")

                    if record.check_out:
                        record.check_out_str = record.check_out.astimezone(IST).strftime("%I:%M %p")
                        record.calculated_hours = record.working_hours
                    else:
                        record.check_out_str = "-"

                updated_attendance.append(record)

            else:
                # No attendance → Absent
                temp = type("TempAttendance", (), {})()
                temp.employee = emp
                temp.date = current_date
                temp.status = "Absent"
                temp.work_mode = "Office"
                temp.check_in_str = "-"
                temp.check_out_str = "-"
                temp.calculated_hours = None
                temp.permissions_list = list(
                    Permission.objects.filter(employee=emp, date=current_date)
                )
                updated_attendance.append(temp)

        current_date += timedelta(days=1)

    # ✅ FIX 3: safe totals (no None crash)
    total_employees = employees.count()
    present_count = sum(1 for r in updated_attendance if r.status == "Present")
    absent_count = sum(1 for r in updated_attendance if r.status == "Absent")
    late_count = sum(1 for r in updated_attendance if r.status == "Late")
    wfh_count = sum(1 for r in updated_attendance if r.status == "WFH")
    
    # ✅ Safe total working hours calculation
    try:
        total_working_hours = sum(getattr(r, "calculated_hours", 0) or 0 for r in updated_attendance)
    except (AttributeError, TypeError):
        total_working_hours = 0

    # ✅ Safe department filter for context
    safe_dept_filter = ""
    if department_filter:
        try:
            safe_dept_filter = int(department_filter)
        except (ValueError, TypeError):
            safe_dept_filter = ""

    context = {
        "attendance": updated_attendance,
        "start_date": start_date or "",
        "end_date": end_date or "",
        "employee_filter": employee_filter,
        "department_filter": safe_dept_filter,
        "departments": Department.objects.all(),
        "total_employees": total_employees,
        "present_count": present_count,
        "absent_count": absent_count,
        "late_count": late_count,
        "wfh_count": wfh_count,
        "total_working_hours": round(total_working_hours, 2),
        "pending_leaves_count": LeaveRequest.objects.filter(status="Pending").count(),
    }

    return render(request, "home.html", context)



# -------------------------------
# Export Attendance Excel
# -------------------------------

@login_required(login_url="login")
def export_attendance_excel(request):
    if not getattr(request.user, 'is_admin', False):
        messages.error(request, "Admin access only")
        return redirect("login")
        
    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date")
    employee_filter = request.GET.get("employee", "")
    department_filter = request.GET.get("department", "")

    try:
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date() if start_date_str else date.today()
    except ValueError:
        start_date = date.today()

    try:
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date() if end_date_str else start_date
    except ValueError:
        end_date = start_date

    attendance_qs = Attendance.objects.filter(
        date__range=(start_date, end_date)
    ).select_related("employee__user", "employee__department")

    if employee_filter:
        attendance_qs = attendance_qs.filter(
            Q(employee__employee_id__icontains=employee_filter) |
            Q(employee__user__name__icontains=employee_filter)
        )

    if department_filter:
        attendance_qs = attendance_qs.filter(employee__department_id=department_filter)

    # ✅ FIX HERE
    attendance_map = {(a.employee.id, a.date): a for a in attendance_qs}

    employees = Employee.objects.select_related("user", "department").all()
    if department_filter:
        employees = employees.filter(department_id=department_filter)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Attendance Report"
    ws.append([
        "Date", "Employee ID", "Employee Name", "Department",
        "Check In", "Check Out", "Status", "Working Hours", "Permissions", "Remarks"
    ])

    current = start_date
    while current <= end_date:
        for emp in employees:
            record = attendance_map.get((emp.id, current))

            if record:
                if not record.check_in:
                    status = "Absent"
                else:
                    local_checkin = record.check_in.astimezone(IST).time()
                    if local_checkin <= time(9, 45):
                        status = "Present"
                    elif local_checkin <= time(11, 0):
                        status = "Late"
                    else:
                        status = "Absent"

                total_hours = record.working_hours or ""

                permissions_qs = Permission.objects.filter(
                    employee=record.employee,
                    date=record.date
                )

                permission_str = "\n".join(
                    f"{p.start_time.strftime('%I:%M %p') if p.start_time else '-'}-"
                    f"{p.end_time.strftime('%I:%M %p') if p.end_time else '-'} ({p.status})"
                    for p in permissions_qs
                )

                ws.append([
                    record.date.strftime("%Y-%m-%d"),
                    record.employee.employee_id,
                    record.employee.user.name,
                    record.employee.department.name if record.employee.department else "",
                    record.check_in.astimezone(IST).strftime("%I:%M %p") if record.check_in else "",
                    record.check_out.astimezone(IST).strftime("%I:%M %p") if record.check_out else "",
                    status,
                    total_hours,
                    permission_str.strip(),
                    record.remarks or "",
                ])
            else:
                ws.append([
                    current.strftime("%Y-%m-%d"),
                    emp.employee_id,
                    emp.user.name,
                    emp.department.name if emp.department else "",
                    "-", "-", "Absent", "", "", "",
                ])
        current += timedelta(days=1)

    for col in ws.columns:
        max_length = max(len(str(cell.value)) for cell in col if cell.value) + 5
        ws.column_dimensions[col[0].column_letter].width = max_length

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"attendance_report_{start_date:%Y%m%d}_to_{end_date:%Y%m%d}.xlsx"
    response = HttpResponse(
        output,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f"attachment; filename={filename}"
    return response

# -------------------------------
# Export Leave Excel
# -------------------------------
@login_required(login_url="login")
def export_leave_excel(request):
    if not getattr(request.user, 'is_admin', False):
        messages.error(request, "Admin access only")
        return redirect("login")

    status_filter = request.GET.get("status", "Pending")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    leave_requests = LeaveRequest.objects.select_related("employee__user", "employee__department").all().order_by("-created_at")

    if status_filter:
        leave_requests = leave_requests.filter(status=status_filter)
    if start_date:
        leave_requests = leave_requests.filter(start_date__gte=start_date)
    if end_date:
        leave_requests = leave_requests.filter(end_date__lte=end_date)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Leave Requests"
    ws.append([
        "Employee ID", "Employee Name", "Department",
        "Leave Type", "Start Date", "End Date", "Total Days", "Status", "Reason",
        "Yearly Sick Used", "Yearly Casual Used", "Yearly LOP Used", "Available Paid Balance (14 Max)"
    ])

    # Calculate current year stats for all employees proactively for the export
    current_year = timezone.now().year
    approved_this_year = LeaveRequest.objects.filter(
        status="Approved", 
        start_date__year=current_year
    ).select_related("employee")
    
    stats_map = {}
    for r in approved_this_year:
        emp_id = r.employee.id
        if emp_id not in stats_map:
            stats_map[emp_id] = {'Sick Leave': 0, 'Casual Leave': 0, 'Loss of Pay': 0}
        
        days_count = (r.end_date - r.start_date).days + 1
        l_type = r.leave_type or r.requested_type
        if l_type in stats_map[emp_id]:
            stats_map[emp_id][l_type] += days_count

    for req in leave_requests:
        days = (req.end_date - req.start_date).days + 1
        dept_name = req.employee.department.name if req.employee.department else ""
        emp_id = req.employee.id
        
        emp_stats = stats_map.get(emp_id, {'Sick Leave': 0, 'Casual Leave': 0, 'Loss of Pay': 0})
        sick_used = emp_stats['Sick Leave']
        casual_used = emp_stats['Casual Leave']
        lop_used = emp_stats['Loss of Pay']
        yearly_used_paid = sick_used + casual_used
        available_balance = 14 - yearly_used_paid

        ws.append([
            req.employee.employee_id,
            req.employee.user.name,
            dept_name,
            req.leave_type or req.requested_type,
            req.start_date.strftime("%Y-%m-%d"),
            req.end_date.strftime("%Y-%m-%d"),
            days,
            req.status,
            req.reason,
            sick_used,
            casual_used,
            lop_used,
            available_balance
        ])

    for col in ws.columns:
        max_length = max(len(str(cell.value)) for cell in col if cell.value) + 5
        ws.column_dimensions[col[0].column_letter].width = max_length

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"leave_requests_{status_filter}.xlsx"
    response = HttpResponse(
        output,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f"attachment; filename={filename}"
    return response


# -------------------------------
# Employee Management Views
# -------------------------------

@login_required(login_url="login")
def employeemanagement(request):
    if not getattr(request.user, 'is_admin', False):
        messages.error(request, "Admin access only")
        return redirect("login")

    search_query = request.GET.get('search', '')
    dept_id = request.GET.get('department', '')
    
    employees = Employee.objects.select_related("user", "department").all()
    
    if search_query:
        from django.db.models import Q
        employees = employees.filter(
            Q(user__name__icontains=search_query) |
            Q(employee_id__icontains=search_query) |
            Q(user__email__icontains=search_query)
        )
        
    if dept_id:
        employees = employees.filter(department_id=dept_id)
        
    departments = Department.objects.all().order_by('name')
    
    context = {
        "employees": employees,
        "departments": departments,
        "search_query": search_query,
        "selected_dept": dept_id
    }
    return render(request, "Employeemanagement.html", context)

def generate_random_password(length=6):
    characters = string.ascii_letters + string.digits + "ayowev"
    return "".join(secrets.choice(characters) for _ in range(length))

@login_required(login_url="login")
def add_employee(request):
    if not getattr(request.user, 'is_admin', False):
        messages.error(request, "Admin access only")
        return redirect("login")

    # Create departments if not exist as per the new Role layout
    roles_meta = {
        "Employee": ["HR", "Developer", "Marketing", "UI/UX Designer", "Sales"],
        "Intern": ["Developer Intern", "HR Intern", "Sales Intern", "Marketing Intern", "UI/UX Designer Intern"]
    }
    
    for category, roles in roles_meta.items():
        for role_name in roles:
            Department.objects.get_or_create(name=role_name)
    
    # Fetch all for grouping
    departments_qs = Department.objects.all()
    employee_roles = departments_qs.filter(name__in=roles_meta["Employee"])
    intern_roles = departments_qs.filter(name__in=roles_meta["Intern"])
    
    success_message = None

    if request.method == "POST":
        first_name = request.POST.get("first_name")
        last_name = request.POST.get("last_name")
        email = request.POST.get("email")
        phone = request.POST.get("phone")
        department_id = request.POST.get("department")
        joining_date = request.POST.get("joining_date")
        account_number = request.POST.get("account_number")
        ifsc_code = request.POST.get("ifsc_code")
        bank_name = request.POST.get("bank_name")
        pan_number = request.POST.get("pan_number")
        aadhaar_card_number = request.POST.get("aadhaar_card_number")
        address = request.POST.get("address")

        if not all([first_name, last_name, email, phone, department_id]):
            messages.error(request, "Please fill all required fields.")
            return render(request, "add_employee.html", {
                "employee_roles": employee_roles,
                "intern_roles": intern_roles,
            })

        # Validate Email Format
        try:
            validate_email(email)
        except ValidationError:
            messages.error(request, "Invalid email format. Please enter a valid email address.")
            return render(request, "add_employee.html", {
                "employee_roles": employee_roles,
                "intern_roles": intern_roles,
            })

        # Validate Phone Format (Standard 10-digit check)
        if not (phone.isdigit() and len(phone) == 10):
            messages.error(request, "Invalid phone number. Please enter exactly 10 digits.")
            return render(request, "add_employee.html", {
                "employee_roles": employee_roles,
                "intern_roles": intern_roles,
            })

        if User.objects.filter(email=email).exists():
            messages.error(request, "User with this email already exists.")
            return render(request, "add_employee.html", {
                "employee_roles": employee_roles,
                "intern_roles": intern_roles,
            })

        generated_password = generate_random_password()
        user = User(email=email, name=f"{first_name} {last_name}")
        user.set_password(generated_password)
        user.save()

        department = Department.objects.get(id=int(department_id))
        emp = Employee.objects.create(
            user=user,
            phone=phone,
            department=department,
            raw_password=generated_password,
            joining_date=joining_date if joining_date else None,
            account_number=account_number,
            ifsc_code=ifsc_code,
            bank_name=bank_name,
            pan_number=pan_number,
            aadhaar_card_number=aadhaar_card_number,
            address=address,
        )

        success_message = f"Employee {first_name} {last_name} added! ID: {emp.employee_id} | Password: {generated_password}"

    return render(request, "add_employee.html", {
        "employee_roles": employee_roles, 
        "intern_roles": intern_roles, 
        "success_message": success_message
    })

@login_required(login_url="login")
def edit_employee(request, employee_id):
    if not getattr(request.user, 'is_admin', False):
        messages.error(request, "Admin access only")
        return redirect("login")

    employee = get_object_or_404(Employee, id=employee_id)
    departments_qs = Department.objects.all()
    
    # Category metadata
    roles_meta = {
        "Employee": ["HR", "Developer", "Marketing", "UI/UX Designer", "Sales"],
        "Intern": ["Developer Intern", "HR Intern", "Sales Intern", "Marketing Intern", "UI/UX Designer Intern"]
    }
    employee_roles = departments_qs.filter(name__in=roles_meta["Employee"])
    intern_roles = departments_qs.filter(name__in=roles_meta["Intern"])

    if request.method == "POST":
        name = request.POST.get("name")
        email = request.POST.get("email")
        phone = request.POST.get("phone")
        department_id = request.POST.get("department")
        joining_date = request.POST.get("joining_date")
        account_number = request.POST.get("account_number")
        ifsc_code = request.POST.get("ifsc_code")
        bank_name = request.POST.get("bank_name")
        pan_number = request.POST.get("pan_number")
        aadhaar_card_number = request.POST.get("aadhaar_card_number")
        address = request.POST.get("address")

        if not all([name, email, department_id]):
            messages.error(request, "Please fill all required fields.")
        else:
            user = employee.user
            user.name = name
            user.email = email
            user.username = email
            user.save()
            employee.phone = phone
            employee.department = Department.objects.get(id=int(department_id))
            employee.joining_date = joining_date if joining_date else None
            employee.account_number = account_number
            employee.ifsc_code = ifsc_code
            employee.bank_name = bank_name
            employee.pan_number = pan_number
            employee.aadhaar_card_number = aadhaar_card_number
            employee.address = address
            employee.save()
            messages.success(request, f"Employee {name} updated successfully!")

    return render(request, "edit_employee.html", {
        "employee": employee, 
        "employee_roles": employee_roles,
        "intern_roles": intern_roles
    })


@login_required(login_url="login")
def delete_employee(request, employee_id):
    if not getattr(request.user, 'is_admin', False):
        messages.error(request, "Admin access only")
        return redirect("login")

    employee = get_object_or_404(Employee, id=employee_id)
    if request.method == "POST":
        employee.user.delete()
        employee.delete()
        messages.success(request, f"Employee {employee.user.name} deleted successfully!")
        return redirect("employeemanagement")
    return render(request, "delete_employee.html", {"employee": employee})


@login_required(login_url="login")
def toggle_employee_block(request, employee_id):
    """Block or Unblock an employee's login access. Prevent admins from self-blocking."""
    if not getattr(request.user, 'is_admin', False):
        messages.error(request, "Admin access only")
        return redirect("login")

    employee = get_object_or_404(Employee, id=employee_id)
    if request.method == "POST":
        user = employee.user
        
        # Safety Check: Prevent admin from blocking themselves
        if user == request.user:
            messages.error(request, "Error: You cannot block your own account.")
            return redirect("employeemanagement")

        if user.is_active:
            # Block the user
            user.is_active = False
            user.save()
            # Invalidate all their active sessions immediately
            UserSession.objects.filter(user=user).delete()
            messages.warning(request, f"Employee {user.name} has been blocked. All active sessions have been terminated.")
        else:
            # Unblock the user
            user.is_active = True
            user.save()
            messages.success(request, f"Employee {user.name} has been unblocked and can now log in.")
    return redirect("employeemanagement")

# -------------------------------
# DRF APIs for Login / Logout / Attendance / Permissions
# -------------------------------

@csrf_exempt
@api_view(["POST"])
@permission_classes([AllowAny])
@authentication_classes([])
def login_view(request):
    employee_id = request.data.get("employee_id")
    password = request.data.get("password")
    if not employee_id or not password:
        return Response({"error": "Employee ID and password required"}, status=400)
    try:
        employee = Employee.objects.get(employee_id=employee_id)
        user = employee.user
        if not user.check_password(password):
            return Response({"error": "Invalid credentials"}, status=401)
        
        # Check if user is blocked by admin
        if not user.is_active:
            return Response({"error": "Your account has been blocked. Please contact your administrator."}, status=403)
        
        # --- Persistent Sessions & Concurrent Limit Logic ---
        # 1. Cleanup expired sessions
        UserSession.objects.filter(user=user, expires_at__lt=timezone.now()).delete()
        
        # 2. Check active session count
        active_count = UserSession.objects.filter(user=user, expires_at__gt=timezone.now()).count()
        
        # 3. Enforce Limit: Max 6 devices
        if active_count >= 6:
            return Response({
                "error": "Device limit reached (Max 6). Please manually logout from one of your existing devices to continue.",
                "limit_reached": True
            }, status=403)
            
        # 4. Create new session (90 days)
        token_key = secrets.token_hex(32)
        expiry_date = timezone.now() + timedelta(days=90)
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        
        session = UserSession.objects.create(
            user=user,
            token=token_key,
            expires_at=expiry_date,
            user_agent=user_agent
        )
        
        return Response({
            "token": session.token,
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "employee_id": employee.employee_id,
                "is_admin": user.is_admin
            }
        })
    except Employee.DoesNotExist:
        return Response({"error": "Employee does not exist"}, status=404)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_active_sessions(request):
    """List all active sessions for the current user."""
    sessions = UserSession.objects.filter(user=request.user, expires_at__gt=timezone.now()).order_by('-created_at')
    
    data = []
    for s in sessions:
        data.append({
            "id": s.id,
            "user_agent": s.user_agent,
            "created_at": s.created_at.astimezone(IST).strftime("%Y-%m-%d %I:%M %p"),
            "is_current": s.token == request.auth.token if hasattr(request, 'auth') and isinstance(request.auth, UserSession) else False
        })
    
    return Response({
        "sessions": data,
        "limit": 6,
        "current_count": len(data)
    })

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def terminate_session(request):
    """Terminate a specific session by ID."""
    session_id = request.data.get("session_id")
    if not session_id:
        return Response({"error": "Session ID required"}, status=400)
        
    try:
        session = UserSession.objects.get(id=session_id, user=request.user)
        session.delete()
        return Response({"message": "Session terminated successfully"})
    except UserSession.DoesNotExist:
        return Response({"error": "Session not found or not owned by you"}, status=404)

@api_view(["POST"])
@authentication_classes([UserSessionAuthentication])
@permission_classes([IsAuthenticated])
def logout_view(request):
    try:
        # request.auth now holds our UserSession instance (returned by UserSessionAuthentication)
        if hasattr(request, 'auth') and isinstance(request.auth, UserSession):
            request.auth.delete()
        return Response({"message": "Logged out successfully"})
    except Exception as e:
        print(f"Logout error: {e}")
        return Response({"error": "Logout failed"}, status=400)

@api_view(["GET"])
@permission_classes([IsAuthenticated, IsWithinSessionLimit])
def today_attendance(request):
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        return Response({"error": "Employee profile not found. If you are an admin, you don't have attendance records."}, status=404)
        
    today = timezone.now().astimezone(IST).date()
    attendance, _ = Attendance.objects.get_or_create(employee=employee, date=today)
    return Response({
        "employee": {"name": request.user.name, "email": request.user.email},
        "attendance": {
            "date": str(attendance.date),
            "check_in": attendance.check_in.astimezone(IST).strftime("%H:%M") if attendance.check_in else None,
            "check_out": attendance.check_out.astimezone(IST).strftime("%H:%M") if attendance.check_out else None,
            "status": attendance.status,
            "work_mode": attendance.work_mode,
        },
    })

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_employee_details(request):
    try:
        employee = Employee.objects.get(user=request.user)
        return Response(EmployeeSerializer(employee).data)
    except Employee.DoesNotExist:
        return Response({"error": "Employee profile not found."}, status=404)

@api_view(["POST"])
@permission_classes([IsAuthenticated, IsWithinSessionLimit])
def create_permission_request(request):
    employee = Employee.objects.get(user=request.user)
    data = request.data
    if not all([data.get("start_time"), data.get("end_time"), data.get("reason")]):
        return Response({"error": "All fields are required."}, status=400)
    permission = Permission.objects.create(
        employee=employee,
        date=timezone.now().date(),
        start_time=data["start_time"],
        end_time=data["end_time"],
        reason=data["reason"],
        status="Pending",
    )
    return Response(PermissionSerializer(permission).data, status=201)

@api_view(["GET"])
@permission_classes([IsAuthenticated, IsWithinSessionLimit])
def list_permissions(request):
    employee = Employee.objects.get(user=request.user)
    permissions = Permission.objects.filter(employee=employee).exclude(status="Pending").order_by("-date")
    return Response(PermissionSerializer(permissions, many=True).data)

# --- Check-in API ---
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.utils import timezone

IST = timezone.get_fixed_timezone(330)  # +5:30 IST

@api_view(["POST"])
@permission_classes([IsAuthenticated, IsWithinSessionLimit])
def check_in(request):
    import math
    from django.conf import settings as django_settings

    # --- Step 1: Get work mode and location ---
    work_mode = request.data.get("work_mode", "Office")
    user_lat = request.data.get("latitude")
    user_lng = request.data.get("longitude")

    if work_mode == "Office":
        if user_lat is None or user_lng is None:
            return Response({"error": "Location (latitude, longitude) is required for office check-in."}, status=400)
        try:
            user_lat = float(user_lat)
            user_lng = float(user_lng)
        except (ValueError, TypeError):
            return Response({"error": "Invalid latitude or longitude."}, status=400)
    else:
        # For WFH, location is optional. If provided, try to parse it.
        if user_lat is not None and user_lng is not None:
            try:
                user_lat = float(user_lat)
                user_lng = float(user_lng)
            except:
                pass # Ignore invalid location for WFH
        else:
            # Set to 0 if not provided for WFH so calculations don't crash
            user_lat = user_lng = 0.0

    # --- Step 2: Office coordinates from settings ---
    office_lat = django_settings.OFFICE_LATITUDE
    office_lng = django_settings.OFFICE_LONGITUDE
    max_radius_m = django_settings.GEOFENCE_RADIUS_METERS

    # --- Step 3: Haversine distance calculation ---
    R = 6371000  # Earth radius in meters
    phi1 = math.radians(user_lat)
    phi2 = math.radians(office_lat)
    dphi = math.radians(office_lat - user_lat)
    dlambda = math.radians(office_lng - user_lng)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    a = min(1, max(0, a)) # Clamp to [0, 1] to avoid domain error
    distance_m = R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    # --- Step 4: Enforce geo-fence (Skip if WFH) ---
    if work_mode == "Office":
        if distance_m > max_radius_m:
            return Response({
                "error": f"You are {round(distance_m)} meters away from the office. Check-in is only allowed within {max_radius_m} meters.",
                "distance_meters": round(distance_m),
            }, status=403)

    # --- Step 5: Proceed with check-in ---
    try:
        try:
            employee = Employee.objects.select_related('user').get(user=request.user)
        except Employee.DoesNotExist:
            return Response({"error": "Employee profile not found."}, status=404)

        today = timezone.now().astimezone(IST).date()
        attendance = Attendance.objects.filter(employee=employee, date=today).first()

        if attendance and attendance.check_in:
            return Response({"error": "Already checked in"}, status=400)

        now_utc = timezone.now()
        now_ist = now_utc.astimezone(IST)
        current_time = now_ist.time()

        is_wfh = work_mode == "WFH"

        # Time rules
        if is_wfh:
            status = "WFH"
        elif current_time <= CUTOFF_TIME:
            status = "Present"
        elif current_time <= ABSENT_TIME:
            status = "Late"
        else:
            return Response({"error": "Check-in closed after 11:00 AM."}, status=400)

        if not attendance:
            attendance = Attendance(employee=employee, date=today)
            
        attendance.work_mode = work_mode
        attendance.check_in = now_utc
        attendance.status = status
        attendance.save()

        return Response({
            "message": "Checked in successfully",
            "check_in_time": now_ist.strftime("%I:%M %p"),
            "status": status,
            "distance_meters": round(distance_m),
        })
    except Exception as e:
        import traceback
        return Response({
            "error": f"Server Error: {str(e)}",
            "traceback": traceback.format_exc()
        }, status=500)



@api_view(["POST"])
@permission_classes([IsAuthenticated, IsWithinSessionLimit])
def check_out(request):
    try:
        employee = Employee.objects.select_related('user').get(user=request.user)
    except Employee.DoesNotExist:
        return Response({"error": "Employee profile not found."}, status=404)
        
    today = timezone.now().astimezone(IST).date()

    # Optimization: Use filter().first() to avoid exceptions and speed up lookup
    attendance = Attendance.objects.filter(employee=employee, date=today).first()
    
    if not attendance:
        return Response({"error": "No check-in record found for today"}, status=400)

    if attendance.check_out:
        return Response({"error": "Already checked out"}, status=400)

    utc_now = timezone.now()
    attendance.check_out = utc_now
    attendance.save()

    return Response({
        "message": "Checked out",
        "check_out_time": attendance.check_out.astimezone(IST).strftime("%I:%M %p")
    })

@api_view(["GET"])
@permission_classes([IsAuthenticated, IsWithinSessionLimit])
def attendance_history(request):
    employee = Employee.objects.get(user=request.user)

    month = request.GET.get("month")
    records = Attendance.objects.filter(employee=employee)

    if month:
        try:
            year, month_num = map(int, month.split("-"))
            records = records.filter(date__year=year, date__month=month_num)
        except ValueError:
            return Response({"error": "Invalid month format"}, status=400)

    class AttendanceSerializer(serializers.ModelSerializer):
        check_in = serializers.SerializerMethodField()
        check_out = serializers.SerializerMethodField()

        class Meta:
            model = Attendance
            fields = ["date", "check_in", "check_out", "status", "work_mode", "remarks"]

        def get_check_in(self, obj):
            return obj.check_in.astimezone(IST).strftime("%I:%M %p") if obj.check_in else None

        def get_check_out(self, obj):
            return obj.check_out.astimezone(IST).strftime("%I:%M %p") if obj.check_out else None

    return Response(
        AttendanceSerializer(records.order_by("-date"), many=True).data
    )




# -------------------------------
# Password Management API
# -------------------------------

@csrf_exempt
@api_view(["POST"])
@permission_classes([AllowAny])
def forgot_password(request):
    identifier = request.data.get("employee_id")  # ID, email, or name
    current_password = request.data.get("current_password")
    new_password = request.data.get("new_password")
    confirm_password = request.data.get("confirm_password")

    if not all([identifier, current_password, new_password, confirm_password]):
        return Response({"error": "All fields are required."}, status=400)

    if new_password != confirm_password:
        return Response({"error": "New password and confirm password do not match."}, status=400)

    try:
        employee = Employee.objects.get(
            Q(employee_id=identifier) |
            Q(user__email=identifier) |
            Q(user__name=identifier)
        )
        user = employee.user

        if not user.check_password(current_password):
            return Response({"error": "Current password is incorrect."}, status=400)

        user.set_password(new_password)
        user.save()

        # Optionally store raw password for admin reference
        employee.raw_password = new_password
        employee.save()

        return Response({"message": "Password updated successfully!"}, status=200)

    except Employee.DoesNotExist:
        return Response({"error": "Employee not found."}, status=404)


# -------------------------------
# Admin HTML Interface Views
# -------------------------------

@login_required(login_url="login")
def admin_leave_approval(request):
    if not request.user.is_admin:
        messages.error(request, "Admin access required.")
        return redirect("login")
    
    # Filters
    status_filter = request.GET.get("status", "Pending")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    
    leave_requests = LeaveRequest.objects.select_related("employee__user", "employee__department").all().order_by("-created_at")
    
    if status_filter:
        leave_requests = leave_requests.filter(status=status_filter)
    if start_date:
        leave_requests = leave_requests.filter(start_date__gte=start_date)
    if end_date:
        leave_requests = leave_requests.filter(end_date__lte=end_date)

    # Stats
    pending_count = LeaveRequest.objects.filter(status="Pending").count()
    approved_lop_count = LeaveRequest.objects.filter(status="Approved", leave_type="Loss of Pay").count()
    approved_count = LeaveRequest.objects.filter(status="Approved").exclude(leave_type="Loss of Pay").count()
    rejected_count = LeaveRequest.objects.filter(status="Rejected").count()

    # ✅ High-Speed Statistics (Cross-DB Compatible)
    current_year = timezone.now().year
    
    # Yearly Used (Sick + Casual) 
    # We filter to ONLY the current year to keep it extremely fast
    yearly_approved = LeaveRequest.objects.filter(
        status="Approved", 
        start_date__year=current_year,
        leave_type__in=['Sick Leave', 'Casual Leave']
    ).select_related("employee")
    
    yearly_map = {}
    for req in yearly_approved:
        days = (req.end_date - req.start_date).days + 1
        emp_id = req.employee.id
        yearly_map[emp_id] = yearly_map.get(emp_id, 0) + days

    # Monthly Stats for sidebars
    # We'll stick to a slightly more efficient manual map for the monthly view to keep cross-DB compatibility
    # but we filter specifically to ONLY the current month or target month if provided.
    target_month = int(start_date.split('-')[1]) if start_date else timezone.now().month
    target_year = int(start_date.split('-')[0]) if start_date else timezone.now().year

    monthly_approved = LeaveRequest.objects.filter(
        status="Approved", 
        start_date__year=target_year,
        start_date__month=target_month
    ).select_related("employee")
    
    stats_map = {} # (emp_id) -> {type: {days, count}}
    for req in monthly_approved:
        days = (req.end_date - req.start_date).days + 1
        emp_id = req.employee.id
        if emp_id not in stats_map:
            stats_map[emp_id] = {
                'Sick_Leave': {'days': 0, 'count': 0},
                'Casual_Leave': {'days': 0, 'count': 0},
                'Loss_of_Pay': {'days': 0, 'count': 0}
            }
        
        template_key = req.leave_type.replace(' ', '_')
        if template_key in stats_map[emp_id]:
            stats_map[emp_id][template_key]['days'] += days
            stats_map[emp_id][template_key]['count'] += 1

    # Group the filtered leave requests by Employee
    grouped_data_dict = {}
    
    # Determine target month for stats (defaults to current month if no filter)
    now = timezone.now()
    target_month_num = now.month
    target_year_num = now.year

    try:
        if start_date:
            dt = datetime.strptime(start_date, '%Y-%m-%d')
            target_month_num = dt.month
            target_year_num = dt.year
            target_month_name = f"{calendar.month_name[target_month_num]} {target_year_num}"
        else:
            target_month_name = now.strftime('%B %Y')
    except:
        target_month_name = now.strftime('%B %Y')

    for req in leave_requests:
        emp_id = req.employee.id
        if emp_id not in grouped_data_dict:
            sm = stats_map.get(emp_id, {
                'Sick_Leave': {'days': 0, 'count': 0},
                'Casual_Leave': {'days': 0, 'count': 0},
                'Loss_of_Pay': {'days': 0, 'count': 0}
            })
            
            grouped_data_dict[emp_id] = {
                'employee': req.employee,
                'leaves': [],
                'yearly_used': yearly_map.get(emp_id, 0),
                'yearly_total': yearly_map.get(emp_id, 0), # Alias for template
                'yearly_limit': 14,
                'stats': sm
            }
        
        grouped_data_dict[emp_id]['leaves'].append(req)

    # Convert to list and sort
    grouped_requests = list(grouped_data_dict.values())
    grouped_requests.sort(key=lambda x: x['employee'].user.name.lower() if x['employee'].user.name else "")

    return render(request, "leave_approval.html", {
        "grouped_requests": grouped_requests,
        "current_status": status_filter,
        "start_date": start_date,
        "end_date": end_date,
        "pending_count": pending_count,
        "lop_count": approved_lop_count,
        "paid_count": approved_count,
        "rejected_count": rejected_count,
        "pending_leaves_count": pending_count,
        "target_month_name": target_month_name,
    })

@login_required(login_url="login")
def admin_update_leave(request):
    # ✅ Defensive check for admin access
    if request.method == "POST" and getattr(request.user, 'is_admin', False):
        leave_id = request.POST.get("leave_id")
        new_status = request.POST.get("status")
        force_type = request.POST.get("force_type") 

        if not leave_id or not new_status:
            messages.error(request, "Invalid request: Missing leave ID or status.")
            return redirect("admin_leave_approval")

        if new_status == "Approved_LOP":
            new_status = "Approved"
            force_type = "Loss of Pay"
            
        try:
            leave = LeaveRequest.objects.get(id=leave_id)
            leave.status = new_status
            if force_type:
                leave.leave_type = force_type
            leave.save()
            
            # Record Notification for Employee
            type_text = f" as {leave.leave_type}" if force_type else ""
            Notification.objects.create(
                user=leave.employee.user,
                title=f"Leave {new_status}",
                message=f"Your {leave.requested_type or leave.leave_type} request ({leave.start_date} - {leave.end_date}) has been {new_status.lower()}{type_text}."
            )
            
            status_msg = f"{new_status.lower()}{type_text}"
            
            # ✅ AJAX Success Response
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                from django.http import JsonResponse
                
                # Fetch updated summary counts for the response
                pending_count = LeaveRequest.objects.filter(status="Pending").count()
                lop_count = LeaveRequest.objects.filter(leave_type="Loss of Pay", status="Approved").count()
                paid_count = LeaveRequest.objects.filter(status="Approved").exclude(leave_type="Loss of Pay").count()
                rejected_count = LeaveRequest.objects.filter(status="Rejected").count()
                
                # Recalculate employee's specific stats for instant header update
                current_year = timezone.now().year
                current_month = timezone.now().month
                
                # Yearly Total (Sick + Casual)
                yearly_total = LeaveRequest.objects.filter(
                    employee=leave.employee,
                    status="Approved",
                    start_date__year=current_year,
                    leave_type__in=['Sick Leave', 'Casual Leave']
                ).count()
                
                # Monthly stats for pills
                monthly_leaves = LeaveRequest.objects.filter(
                    employee=leave.employee,
                    status="Approved",
                    start_date__month=current_month,
                    start_date__year=current_year
                )
                
                stats = {
                    'Sick_Leave': monthly_leaves.filter(leave_type='Sick Leave').count(),
                    'Casual_Leave': monthly_leaves.filter(leave_type='Casual Leave').count(),
                    'Loss_of_Pay': monthly_leaves.filter(leave_type='Loss of Pay').count()
                }

                return JsonResponse({
                    'status': 'success', 
                    'message': f"Request for {leave.employee.user.name} {status_msg}",
                    'new_status': new_status,
                    'new_type': leave.leave_type,
                    'pending_count': pending_count,
                    'lop_count': lop_count,
                    'paid_count': paid_count,
                    'rejected_count': rejected_count,
                    'employee_yearly_total': yearly_total,
                    'employee_stats': stats
                })
            
            messages.success(request, f"Leave request for {leave.employee.user.name} has been {status_msg}.")
        except LeaveRequest.DoesNotExist:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'message': "Leave request not found"}, status=404)
            messages.error(request, "Leave request not found.")
        except Exception as e:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
            messages.error(request, f"Update failed: {str(e)}")
            
        return redirect("admin_leave_approval")
    return redirect("home_page")

@login_required(login_url="login")
def admin_permission_approval(request):
    if not request.user.is_admin:
        messages.error(request, "Admin access required.")
        return redirect("login")
    
    # Filters
    status_filter = request.GET.get("status", "Pending")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    
    permission_requests = Permission.objects.select_related("employee__user", "employee__department").all().order_by("-date")
    
    if status_filter:
        permission_requests = permission_requests.filter(status=status_filter)
    if start_date:
        permission_requests = permission_requests.filter(date__gte=start_date)
    if end_date:
        permission_requests = permission_requests.filter(date__lte=end_date)

    # Stats
    pending_count = Permission.objects.filter(status="Pending").count()
    
    # Approved MTD (Month to Date)
    current_month = timezone.now().month
    current_year = timezone.now().year
    approved_count = Permission.objects.filter(status="Approved", date__month=current_month, date__year=current_year).count()
    rejected_count = Permission.objects.filter(status="Rejected", date__month=current_month, date__year=current_year).count()

    return render(request, "permission_approval.html", {
        "requests": permission_requests,
        "current_status": status_filter,
        "start_date": start_date,
        "end_date": end_date,
        "pending_count": pending_count,
        "approved_count": approved_count,
        "rejected_count": rejected_count,
    })

@login_required(login_url="login")
def admin_update_permission(request):
    if request.method == "POST" and request.user.is_admin:
        permission_id = request.POST.get("permission_id")
        new_status = request.POST.get("status")
        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

        try:
            permission = Permission.objects.get(id=permission_id)
            permission.status = new_status
            permission.save()

            # Record Notification for Employee
            Notification.objects.create(
                user=permission.employee.user,
                title=f"Permission {new_status}",
                message=f"Your permission request for {permission.date} ({permission.start_time.strftime('%I:%M %p')} - {permission.end_time.strftime('%I:%M %p')}) has been {new_status.lower()}."
            )

            if is_ajax:
                # Return updated stat counts so the frontend can update without a full page reload
                current_month = timezone.now().month
                current_year = timezone.now().year
                updated_pending  = Permission.objects.filter(status="Pending").count()
                updated_approved = Permission.objects.filter(status="Approved", date__month=current_month, date__year=current_year).count()
                updated_rejected = Permission.objects.filter(status="Rejected", date__month=current_month, date__year=current_year).count()
                
                # Fetch updated working hours for this specific attendance record
                attendance = Attendance.objects.filter(employee=permission.employee, date=permission.date).first()
                updated_hours = attendance.working_hours if attendance else 0

                return JsonResponse({
                    "status": "success",
                    "message": f"Permission {new_status.lower()} successfully.",
                    "new_status": new_status,
                    "permission_id": permission_id,
                    "pending_count": updated_pending,
                    "approved_count": updated_approved,
                    "rejected_count": updated_rejected,
                    "updated_hours": updated_hours,
                })

            messages.success(request, f"Permission request for {permission.employee.user.name} has been {new_status.lower()}.")
        except Permission.DoesNotExist:
            if is_ajax:
                return JsonResponse({"status": "error", "message": "Permission request not found."}, status=404)
            messages.error(request, "Permission request not found.")

        return redirect("admin_permission_approval")
    return redirect("home_page")

@login_required(login_url="login")
def admin_notifications(request):
    if not request.user.is_admin:
        messages.error(request, "Admin access required.")
        return redirect("login")
    
    if request.method == "POST":
        title = request.POST.get("title")
        message = request.POST.get("message")
        notif_type = request.POST.get("notification_type", "info")
        recipient_id = request.POST.get("recipient")  # "all" or employee_id

        if not title or not message:
            messages.error(request, "Title and message are required.")
        else:
            if recipient_id == "all":
                # Broadcast only to users associated with an employee profile
                employees = Employee.objects.select_related("user").all()
                Notification.objects.bulk_create([
                    Notification(user=emp.user, title=title, message=message, notification_type=notif_type)
                    for emp in employees
                ])
                messages.success(request, f"Broadcast notification sent to all {employees.count()} employees.")
            else:
                try:
                    employee = Employee.objects.get(id=recipient_id)
                    Notification.objects.create(
                        user=employee.user,
                        title=title,
                        message=message,
                        notification_type=notif_type
                    )
                    messages.success(request, f"Notification sent to {employee.user.name}.")
                except Employee.DoesNotExist:
                    messages.error(request, "Invalid recipient selected.")

        return redirect("admin_notifications")

    # Fetch data for the page
    employees = Employee.objects.select_related("user").all().order_by("user__name")
    
    # NEW: Fetch recently sent notifications for the history table
    recent_notifications = Notification.objects.select_related("user").all().order_by("-created_at")[:15]
    
    return render(request, "admin_notifications.html", {
        "employees": employees,
        "recent_notifications": recent_notifications
    })


# -------------------------------
# Leave Request APIs (Employee)
# -------------------------------

@api_view(["POST"])
@permission_classes([IsAuthenticated, IsWithinSessionLimit])
def create_leave_request(request):
    try:
        employee = Employee.objects.get(user=request.user)
        serializer = LeaveRequestSerializer(data=request.data)
        if serializer.is_valid():
            # Automatically set requested_type to the initial leave_type
            serializer.save(
                employee=employee, 
                status="Pending", 
                requested_type=request.data.get("leave_type")
            )
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)
    except Employee.DoesNotExist:
        return Response({"error": "Employee profile not found."}, status=404)

@api_view(["GET"])
@permission_classes([IsAuthenticated, IsWithinSessionLimit])
def list_employee_leaves(request):
    try:
        employee = Employee.objects.get(user=request.user)
        leaves = LeaveRequest.objects.filter(employee=employee).order_by("-created_at")
        serializer = LeaveRequestSerializer(leaves, many=True)
        return Response(serializer.data)
    except Employee.DoesNotExist:
        return Response({"error": "Employee profile not found."}, status=404)


# -------------------------------
# Leave Approval APIs (Admin Only)
# -------------------------------

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_all_leave_requests(request):
    # Only Admin (Staff) can see all requests
    if not request.user.is_admin:
        return Response({"error": "Admin access required."}, status=403)
    
    status_filter = request.GET.get("status", "Pending")
    leaves = LeaveRequest.objects.filter(status=status_filter).order_by("-created_at")
    serializer = LeaveRequestSerializer(leaves, many=True)
    return Response(serializer.data)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def update_leave_status(request):
    if not request.user.is_admin:
        return Response({"error": "Admin access required."}, status=403)
    
    leave_id = request.data.get("leave_id")
    new_status = request.data.get("status") # 'Approved' or 'Rejected'
    
    if new_status not in ["Approved", "Rejected"]:
        return Response({"error": "Invalid status choice."}, status=400)
    
    try:
        leave = LeaveRequest.objects.get(id=leave_id)
        leave.status = new_status
        leave.save()
        
        # Create a notification for the employee
        Notification.objects.create(
            user=leave.employee.user,
            title=f"Leave {new_status}",
            message=f"Your {leave.leave_type} request for {leave.start_date} to {leave.end_date} has been {new_status.lower()}."
        )
        
        return Response({"message": f"Leave request {new_status.lower()} successfully!"})
    except LeaveRequest.DoesNotExist:
        return Response({"error": "Leave request not found."}, status=404)


# -------------------------------
# Notification APIs (General)
# -------------------------------

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_notifications(request):
    notifications = Notification.objects.filter(user=request.user).order_by("-created_at")
    serializer = NotificationSerializer(notifications, many=True)
    return Response(serializer.data)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mark_notification_read(request):
    notif_id = request.data.get("notification_id")
    try:
        notification = Notification.objects.get(id=notif_id, user=request.user)
        notification.is_read = True
        notification.save()
        return Response({"message": "Notification marked as read."})
    except Notification.DoesNotExist:
        return Response({"error": "Notification not found."}, status=404)

@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_notification(request, notif_id):
    try:
        notification = Notification.objects.get(id=notif_id, user=request.user)
        notification.delete()
        return Response({"message": "Notification deleted successfully."}, status=204)
    except Notification.DoesNotExist:
        return Response({"error": "Notification not found."}, status=404)


# -------------------------------
# Admin Notification Management APIs
# -------------------------------

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_all_employees_api(request):
    """Returns a list of all employees for admin to select from."""
    if not request.user.is_admin:
        return Response({"error": "Admin access required."}, status=403)
    
    employees = Employee.objects.select_related("user", "department").all().order_by("user__name")
    serializer = EmployeeSerializer(employees, many=True)
    return Response(serializer.data)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def admin_send_notification_api(request):
    """Allows admin to send a notification to a specific employee or all employees."""
    if not request.user.is_admin:
        return Response({"error": "Admin access required."}, status=403)
    
    title = request.data.get("title")
    message = request.data.get("message")
    notification_type = request.data.get("notification_type", "info")
    recipient_ids = request.data.get("recipient_ids") # Expecting a list of employee_id strings or ["all"]
    
    if not title or not message or not recipient_ids:
        return Response({"error": "Title, message, and recipient_ids are required."}, status=400)
    
    if "all" in recipient_ids:
        # Broadcast to all active users
        users = User.objects.filter(is_active=True)
        notifications = [
            Notification(user=user, title=title, message=message, notification_type=notification_type)
            for user in users
        ]
        Notification.objects.bulk_create(notifications)
        return Response({"message": f"Broadcast notification sent to {len(notifications)} users."})
    else:
        # Send to specific employees
        employees = Employee.objects.filter(employee_id__in=recipient_ids).select_related("user")
        if not employees.exists():
            return Response({"error": "No valid employees found for the provided IDs."}, status=404)
        
        notifications = [
            Notification(user=emp.user, title=title, message=message, notification_type=notification_type)
            for emp in employees
        ]
        Notification.objects.bulk_create(notifications)
        return Response({"message": f"Notification sent to {len(notifications)} employees."})


# @login_required
# @require_POST
# def reject_permission(request, pk):
#     try:
#         permission = Permission.objects.get(id=pk)
#         permission.status = "Rejected"
#         permission.save()

#         return JsonResponse({
#             "success": True,
#             "status": "Rejected"
#         })

#     except Permission.DoesNotExist:
#         return JsonResponse({"success": False, "error": "Permission not found"})