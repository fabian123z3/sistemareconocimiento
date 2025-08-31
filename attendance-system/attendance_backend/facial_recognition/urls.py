# facial_recognition/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # Endpoint de salud
    path('health/', views.health_check, name='health_check'),
    
    # ENDPOINTS QUE FALTAN - CRÍTICO
    path('register-employee/', views.register_employee_face, name='register_employee_face'),
    path('verify-attendance/', views.verify_attendance, name='verify_attendance'),
    path('attendance-history/', views.get_attendance_history, name='get_attendance_history'),
    path('attendance-history/<uuid:employee_id>/', views.get_attendance_history, name='get_attendance_history_by_employee'),
    path('employees/', views.get_employees, name='get_employees'),
    path('employees/<uuid:employee_id>/delete/', views.delete_employee, name='delete_employee'),
]