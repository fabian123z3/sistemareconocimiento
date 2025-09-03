from rest_framework import serializers
from .models import Employee, AttendanceRecord

class EmployeeSerializer(serializers.ModelSerializer):
    attendance_count = serializers.SerializerMethodField()
    face_quality_display = serializers.SerializerMethodField()
    
    class Meta:
        model = Employee
        fields = [
            'id', 'employee_id', 'name', 'rut', 'email', 
            'department', 'position', 'is_active',
            'has_face_registered', 'face_quality_score', 'face_quality_display',
            'face_registration_date', 'face_variations_count',
            'created_at', 'updated_at', 'attendance_count'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'face_registration_date']
    
    def get_attendance_count(self, obj):
        return obj.attendance_records.count()
    
    def get_face_quality_display(self, obj):
        if obj.face_quality_score > 0:
            return f"{obj.face_quality_score:.1%}"
        return "No registrado"

class AttendanceRecordSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.name', read_only=True)
    employee_id = serializers.CharField(source='employee.employee_id', read_only=True)
    employee_rut = serializers.CharField(source='employee.rut', read_only=True)
    employee_department = serializers.CharField(source='employee.department', read_only=True)
    formatted_timestamp = serializers.SerializerMethodField()
    verification_method_display = serializers.SerializerMethodField()
    
    class Meta:
        model = AttendanceRecord
        fields = [
            'id', 'employee_name', 'employee_id', 'employee_rut', 'employee_department',
            'attendance_type', 'timestamp', 'formatted_timestamp', 
            'location_lat', 'location_lng', 'address',
            'verification_method', 'verification_method_display',
            'face_confidence', 'qr_verified',
            'notes', 'is_offline_sync', 'device_info'
        ]
        read_only_fields = ['id', 'timestamp']
    
    def get_formatted_timestamp(self, obj):
        return obj.timestamp.strftime('%d/%m/%Y %H:%M:%S')
    
    def get_verification_method_display(self, obj):
        method_names = {
            'facial': '🔍 Reconocimiento Facial',
            'qr': '📱 Código QR',
            'manual': '📝 Manual/GPS'
        }
        return method_names.get(obj.verification_method, obj.verification_method)