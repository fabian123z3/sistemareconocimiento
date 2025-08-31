from django.urls import path
from . import views

urlpatterns = [
    # Salud del sistema
    path('health/', views.health_check, name='health_check'),
    
    # 📸 SISTEMA BASADO EN FOTOS
    path('register-photo/', views.register_employee_photo, name='register_employee_photo'),
    path('verify-photo/', views.verify_attendance_photo, name='verify_attendance_photo'),
    
    # 🔄 SINCRONIZACIÓN OFFLINE
    path('sync-offline/', views.sync_offline_records, name='sync_offline_records'),
    
    # 📋 GESTIÓN DE DATOS
    path('employees/', views.get_employees, name='get_employees'),
    path('attendance-records/', views.get_attendance_records, name='get_attendance_records'),
    
    # 🗑️ ELIMINACIÓN
    path('delete-employee/<uuid:employee_id>/', views.delete_employee, name='delete_employee'),
    path('delete-attendance/<uuid:attendance_id>/', views.delete_attendance, name='delete_attendance'),
    
    # 🌐 PANEL WEB
    path('panel/', views.attendance_panel, name='attendance_panel'),
]