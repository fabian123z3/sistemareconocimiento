from django.contrib import admin
from .models import Employee, FaceEncoding, AttendanceRecord

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('name', 'employee_id', 'department', 'position', 'is_active', 'created_at')
    list_filter = ('department', 'is_active', 'created_at')
    search_fields = ('name', 'employee_id', 'email')
    readonly_fields = ('id', 'created_at', 'updated_at')

@admin.register(FaceEncoding)
class FaceEncodingAdmin(admin.ModelAdmin):
    list_display = ('employee', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    readonly_fields = ('id', 'encoding_data', 'created_at')

@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ('employee', 'attendance_type', 'timestamp', 'confidence')
    list_filter = ('attendance_type', 'timestamp')
    search_fields = ('employee__name', 'employee__employee_id')
    readonly_fields = ('id', 'timestamp')
    date_hierarchy = 'timestamp'