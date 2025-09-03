from django.db import models
import uuid

class Employee(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee_id = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    rut = models.CharField(max_length=12, unique=True, help_text="RUT con formato 12345678-9")
    email = models.EmailField()
    department = models.CharField(max_length=50)
    position = models.CharField(max_length=50)
    is_active = models.BooleanField(default=True)
    
    # Campos para reconocimiento facial avanzado
    face_encoding = models.TextField(blank=True, null=True)  # JSON con múltiples encodings
    has_face_registered = models.BooleanField(default=False)
    face_quality_score = models.FloatField(default=0)  # Calidad promedio del registro facial (0-1)
    face_registration_date = models.DateTimeField(null=True, blank=True)
    face_variations_count = models.IntegerField(default=0)  # Número de variaciones faciales registradas
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.rut}"
    
    def clean_rut(self):
        """Limpia y formatea el RUT"""
        if self.rut:
            # Remover caracteres especiales excepto el guión
            clean = ''.join(c for c in self.rut if c.isalnum() or c == '-')
            # Asegurar formato correcto
            if '-' not in clean and len(clean) > 1:
                clean = clean[:-1] + '-' + clean[-1]
            return clean.upper()
        return self.rut
    
    def validate_rut(self):
        """Valida el RUT chileno"""
        if not self.rut:
            return False
        
        clean_rut = self.clean_rut().replace('-', '').replace('.', '').upper()
        if len(clean_rut) < 2:
            return False
            
        rut_body = clean_rut[:-1]
        dv = clean_rut[-1]
        
        # Calcular dígito verificador
        multiplier = 2
        sum_total = 0
        
        for digit in reversed(rut_body):
            if not digit.isdigit():
                return False
            sum_total += int(digit) * multiplier
            multiplier = 7 if multiplier == 2 else multiplier + 1
            if multiplier > 7:
                multiplier = 2
        
        remainder = sum_total % 11
        expected_dv = 'K' if remainder == 10 else str((11 - remainder) % 11)
        
        return dv == expected_dv
    
    def save(self, *args, **kwargs):
        if self.rut:
            self.rut = self.clean_rut()
        super().save(*args, **kwargs)
    
    class Meta:
        verbose_name = "Empleado"
        verbose_name_plural = "Empleados"
        ordering = ['name']

class AttendanceRecord(models.Model):
    ATTENDANCE_TYPES = [
        ('entrada', 'Entrada'),
        ('salida', 'Salida'),
    ]
    
    VERIFICATION_METHODS = [
        ('facial', 'Reconocimiento Facial'),
        ('qr', 'Código QR'),
        ('manual', 'Manual/GPS'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='attendance_records')
    attendance_type = models.CharField(max_length=10, choices=ATTENDANCE_TYPES)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    # Ubicación
    location_lat = models.FloatField(null=True, blank=True)
    location_lng = models.FloatField(null=True, blank=True)
    address = models.TextField(blank=True)
    
    # Verificación
    verification_method = models.CharField(max_length=10, choices=VERIFICATION_METHODS, default='manual')
    face_confidence = models.FloatField(default=0)  # Confianza de la verificación facial (0-1)
    qr_verified = models.BooleanField(default=False)  # Si fue verificado por QR
    
    # Otros campos
    notes = models.TextField(blank=True)
    is_offline_sync = models.BooleanField(default=False)
    device_info = models.TextField(blank=True)  # Información del dispositivo usado

    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Registro de Asistencia"
        verbose_name_plural = "Registros de Asistencia"

    def __str__(self):
        return f"{self.employee.name} - {self.attendance_type} - {self.timestamp}"
    
    @property
    def verification_display(self):
        """Retorna una descripción detallada del método de verificación"""
        if self.verification_method == 'facial' and self.face_confidence > 0:
            return f"Facial ({self.face_confidence:.1%})"
        elif self.verification_method == 'qr' and self.qr_verified:
            return f"QR Verificado"
        elif self.verification_method == 'manual':
            return "Manual/GPS"
        else:
            return "Verificación pendiente"