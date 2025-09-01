from django.contrib import admin
from .models import Employee, AttendanceRecord

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('name', 'employee_id', 'department', 'position', 'is_active', 'created_at')
    list_filter = ('department', 'is_active', 'created_at')
    search_fields = ('name', 'employee_id', 'email')
    readonly_fields = ('id', 'created_at', 'updated_at')
    ordering = ('name',)
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('name', 'employee_id', 'email')
        }),
        ('Información Laboral', {
            'fields': ('department', 'position', 'is_active')
        }),
        ('Metadatos', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ('employee', 'attendance_type', 'timestamp', 'location_display', 'is_offline_sync')
    list_filter = ('attendance_type', 'is_offline_sync', 'timestamp')
    search_fields = ('employee__name', 'employee__employee_id', 'address')
    readonly_fields = ('id', 'timestamp')
    date_hierarchy = 'timestamp'
    ordering = ('-timestamp',)
    
    def location_display(self, obj):
        if obj.location_lat and obj.location_lng:
            return f"{obj.location_lat:.6f}, {obj.location_lng:.6f}"
        return "Sin ubicación"
    location_display.short_description = 'Coordenadas'
    
    fieldsets = (
        ('Información de Asistencia', {
            'fields': ('employee', 'attendance_type', 'timestamp')
        }),
        ('Ubicación', {
            'fields': ('location_lat', 'location_lng', 'address')
        }),
        ('Detalles', {
            'fields': ('notes', 'is_offline_sync')
        }),
        ('Metadatos', {
            'fields': ('id',),
            'classes': ('collapse',)
        }),
    )