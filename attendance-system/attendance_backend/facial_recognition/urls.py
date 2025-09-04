from django.urls import path
from . import views

urlpatterns = [
    # Estado del sistema
    path('health/', views.health_check, name='health_check'),
    
    # Gestión de empleados
    path('employees/', views.get_employees, name='get_employees'),
    path('create-employee-basic/', views.create_employee_basic, name='create_employee_basic'),
    path('delete-employee/<uuid:employee_id>/', views.delete_employee, name='delete_employee'),
    
    # Reconocimiento facial balanceado (5 fotos)
    path('register-face/', views.register_employee_face, name='register_employee_face'),
    path('verify-face/', views.verify_attendance_face, name='verify_attendance_face'),
    
    # Verificación por código QR
    path('verify-qr/', views.verify_qr, name='verify_qr'),
    
    # Marcado de asistencia (compatible con todos los métodos)
    path('mark-attendance/', views.mark_attendance, name='mark_attendance'),
    
    # Sincronización offline
    path('sync-offline/', views.sync_offline_records, name='sync_offline_records'),
    
    # Reportes
    path('attendance-records/', views.get_attendance_records, name='get_attendance_records'),
    path('delete-attendance/<uuid:attendance_id>/', views.delete_attendance, name='delete_attendance'),
    
    # Panel web
    path('panel/', views.attendance_panel, name='attendance_panel'),
]