from rest_framework import serializers
from .models import Employee, AttendanceRecord, FaceEncoding

class EmployeeSerializer(serializers.ModelSerializer):
    face_encodings_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Employee
        fields = [
            'id', 'employee_id', 'name', 'email', 
            'department', 'position', 'is_active', 
            'created_at', 'updated_at', 'face_encodings_count'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_face_encodings_count(self, obj):
        return obj.face_encodings.filter(is_active=True).count()

class AttendanceRecordSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.name', read_only=True)
    employee_id = serializers.CharField(source='employee.employee_id', read_only=True)
    employee_department = serializers.CharField(source='employee.department', read_only=True)
    confidence_percentage = serializers.SerializerMethodField()
    
    class Meta:
        model = AttendanceRecord
        fields = [
            'id', 'employee_name', 'employee_id', 'employee_department',
            'attendance_type', 'timestamp', 'confidence', 'confidence_percentage',
            'location_lat', 'location_lng', 'notes'
        ]
        read_only_fields = ['id', 'timestamp']
    
    def get_confidence_percentage(self, obj):
        return f"{obj.confidence:.1%}"

class FaceEncodingSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.name', read_only=True)
    
    class Meta:
        model = FaceEncoding
        fields = [
            'id', 'employee_name', 'created_at', 'is_active'
        ]
        read_only_fields = ['id', 'encoding_data', 'created_at']