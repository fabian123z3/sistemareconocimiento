# facial_recognition/urls.py - URLs ULTRA RÁPIDAS
from django.urls import path
from . import views

urlpatterns = [
    # Salud del sistema
    path('health/', views.health_check, name='health_check'),
    
    # ⚡ ENDPOINTS ULTRA RÁPIDOS PARA CÁMARAS MALAS
    path('ultra-fast-register/', views.ultra_fast_register, name='ultra_fast_register'),
    path('ultra-fast-verify/', views.ultra_fast_verify, name='ultra_fast_verify'),
    
    # Gestión de empleados
    path('employees/', views.get_employees, name='get_employees'),
    path('delete-employee/<uuid:employee_id>/', views.delete_employee, name='delete_employee'),
    
    # Gestión de asistencias
    path('delete-attendance/<uuid:attendance_id>/', views.delete_attendance, name='delete_attendance'),
]