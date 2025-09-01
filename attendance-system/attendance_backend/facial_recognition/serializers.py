from rest_framework import serializers
from .models import Employee, AttendanceRecord

class EmployeeSerializer(serializers.ModelSerializer):
    attendance_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Employee
        fields = [
            'id', 'employee_id', 'name', 'email', 
            'department', 'position', 'is_active',
            'has_face_registered', 'face_quality_score',
            'face_registration_date',
            'created_at', 'updated_at', 'attendance_count'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'face_registration_date']
    
    def get_attendance_count(self, obj):
        return obj.attendance_records.count()

class AttendanceRecordSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.name', read_only=True)
    employee_id = serializers.CharField(source='employee.employee_id', read_only=True)
    employee_department = serializers.CharField(source='employee.department', read_only=True)
    formatted_timestamp = serializers.SerializerMethodField()
    verification_method = serializers.SerializerMethodField()
    
    class Meta:
        model = AttendanceRecord
        fields = [
            'id', 'employee_name', 'employee_id', 'employee_department',
            'attendance_type', 'timestamp', 'formatted_timestamp', 
            'location_lat', 'location_lng', 'address',
            'face_confidence', 'verification_method',
            'notes', 'is_offline_sync'
        ]
        read_only_fields = ['id', 'timestamp', 'verification_method']
    
    def get_formatted_timestamp(self, obj):
        return obj.timestamp.strftime('%d/%m/%Y %H:%M:%S')
    
    def get_verification_method(self, obj):
        return obj.verification_method