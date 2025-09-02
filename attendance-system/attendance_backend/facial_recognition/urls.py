from django.urls import path
from . import views

urlpatterns = [
    # Estado del sistema
    path('health/', views.health_check, name='health_check'),
    
    # Gestión de empleados
    path('employees/', views.get_employees, name='get_employees'),
    path('create-employee/', views.create_employee, name='create_employee'),
    path('delete-employee/<uuid:employee_id>/', views.delete_employee, name='delete_employee'),
    
    # Reconocimiento facial (procesado en servidor)
    path('register-face/', views.register_employee_face, name='register_employee_face'),
    path('verify-face/', views.verify_attendance_face, name='verify_attendance_face'),
    
    # Marcado de asistencia (compatible con ambos métodos)
    path('mark-attendance/', views.mark_attendance, name='mark_attendance'),
    
    # Sincronización offline
    path('sync-offline/', views.sync_offline_records, name='sync_offline_records'),
    
    # Reportes
    path('attendance-records/', views.get_attendance_records, name='get_attendance_records'),
    path('delete-attendance/<uuid:attendance_id>/', views.delete_attendance, name='delete_attendance'),
    
    # Panel web
    path('panel/', views.attendance_panel, name='attendance_panel'),

    # Nuevas rutas para video
    path('register-face-video/', views.register_face_video, name='register-face-video'),
    path('create-employee-with-video/', views.create_employee_with_video, name='create-employee-with-video'),
]