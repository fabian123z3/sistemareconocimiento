from django.db import models
import uuid

class Employee(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee_id = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    email = models.EmailField()
    department = models.CharField(max_length=50)
    position = models.CharField(max_length=50)
    is_active = models.BooleanField(default=True)
    
    # Campos para reconocimiento facial
    face_encoding = models.TextField(blank=True, null=True)  # JSON con encodings
    has_face_registered = models.BooleanField(default=False)
    face_quality_score = models.FloatField(default=0)  # Calidad del registro facial (0-1)
    face_registration_date = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.employee_id}"
    
    class Meta:
        verbose_name = "Empleado"
        verbose_name_plural = "Empleados"
        ordering = ['name']

class AttendanceRecord(models.Model):
    ATTENDANCE_TYPES = [
        ('entrada', 'Entrada'),
        ('salida', 'Salida'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='attendance_records')
    attendance_type = models.CharField(max_length=10, choices=ATTENDANCE_TYPES)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    # Ubicación
    location_lat = models.FloatField(null=True, blank=True)
    location_lng = models.FloatField(null=True, blank=True)
    address = models.TextField(blank=True)
    
    # Verificación facial
    face_confidence = models.FloatField(default=0)  # Confianza de la verificación facial (0-1)
    
    # Otros campos
    notes = models.TextField(blank=True)
    is_offline_sync = models.BooleanField(default=False)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Registro de Asistencia"
        verbose_name_plural = "Registros de Asistencia"

    def __str__(self):
        return f"{self.employee.name} - {self.attendance_type} - {self.timestamp}"
    
    @property
    def verification_method(self):
        """Retorna el método de verificación usado"""
        if self.face_confidence > 0:
            return f"Facial ({self.face_confidence:.1%})"
        return "Manual/GPS"