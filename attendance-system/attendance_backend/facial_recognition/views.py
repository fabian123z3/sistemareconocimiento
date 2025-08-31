from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth.models import User
from django.db import transaction
import json
import uuid
from datetime import datetime

from .models import Employee, FaceEncoding, AttendanceRecord
from .face_recognition_utils import FaceRecognitionService
from .serializers import EmployeeSerializer, AttendanceRecordSerializer

# Instancia global del servicio de reconocimiento
face_service = FaceRecognitionService()

@api_view(['POST'])
def register_employee_face(request):
    """
    Registra un nuevo empleado con su encoding facial
    """
    try:
        data = request.data
        name = data.get('name')
        employee_id = data.get('employee_id')
        email = data.get('email', '')
        department = data.get('department', 'General')
        position = data.get('position', 'Empleado')
        base64_image = data.get('image')

        # Validaciones básicas
        if not name or not employee_id or not base64_image:
            return Response({
                'success': False,
                'message': 'Faltan datos requeridos: name, employee_id, image'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Verificar que no existe empleado con mismo ID
        if Employee.objects.filter(employee_id=employee_id).exists():
            return Response({
                'success': False,
                'message': 'Ya existe un empleado con ese ID'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validar calidad de imagen
        is_valid, quality_message = face_service.validate_image_quality(base64_image)
        if not is_valid:
            return Response({
                'success': False,
                'message': f'Calidad de imagen insuficiente: {quality_message}'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Preprocesar imagen
        processed_image = face_service.preprocess_image(base64_image)

        # Generar encoding facial
        encoding_data, encoding_message = face_service.encode_face_from_base64(processed_image)
        
        if encoding_data is None:
            return Response({
                'success': False,
                'message': f'Error en reconocimiento facial: {encoding_message}'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Crear empleado y encoding en transacción
        with transaction.atomic():
            # Crear usuario Django
            user = User.objects.create_user(
                username=employee_id,
                email=email,
                first_name=name
            )

            # Crear empleado
            employee = Employee.objects.create(
                user=user,
                employee_id=employee_id,
                name=name,
                email=email,
                department=department,
                position=position
            )

            # Crear encoding facial
            face_encoding = FaceEncoding.objects.create(
                employee=employee,
                encoding_data=json.dumps(encoding_data)
            )

        return Response({
            'success': True,
            'message': 'Empleado registrado exitosamente',
            'employee_id': str(employee.id),
            'confidence_message': encoding_message
        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error interno del servidor: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
def verify_attendance(request):
    """
    Verifica rostro y registra asistencia
    """
    try:
        data = request.data
        base64_image = data.get('image')
        attendance_type = data.get('type', 'entrada')  # 'entrada' o 'salida'
        location_lat = data.get('latitude')
        location_lng = data.get('longitude')

        # Validaciones
        if not base64_image:
            return Response({
                'success': False,
                'message': 'Imagen requerida'
            }, status=status.HTTP_400_BAD_REQUEST)

        if attendance_type not in ['entrada', 'salida']:
            return Response({
                'success': False,
                'message': 'Tipo de asistencia debe ser "entrada" o "salida"'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validar calidad de imagen
        is_valid, quality_message = face_service.validate_image_quality(base64_image)
        if not is_valid:
            return Response({
                'success': False,
                'message': f'Calidad de imagen insuficiente: {quality_message}'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Preprocesar imagen
        processed_image = face_service.preprocess_image(base64_image)

        # Generar encoding de la imagen recibida
        unknown_encoding, encoding_message = face_service.encode_face_from_base64(processed_image)
        
        if unknown_encoding is None:
            return Response({
                'success': False,
                'message': f'Error en reconocimiento facial: {encoding_message}'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Obtener todos los encodings registrados
        known_encodings = {}
        face_encodings = FaceEncoding.objects.filter(is_active=True).select_related('employee')
        
        if not face_encodings.exists():
            return Response({
                'success': False,
                'message': 'No hay empleados registrados en el sistema'
            }, status=status.HTTP_404_NOT_FOUND)

        for face_encoding in face_encodings:
            known_encodings[str(face_encoding.employee.id)] = face_encoding.encoding_data

        # Buscar mejor coincidencia
        best_match_id, confidence = face_service.find_best_match(known_encodings, unknown_encoding)

        # Verificar si se encontró coincidencia válida
        minimum_confidence = 0.6  # 60% de confianza mínima
        
        if best_match_id is None or confidence < minimum_confidence:
            return Response({
                'success': False,
                'message': f'Rostro no reconocido. Confianza: {confidence:.2%}',
                'confidence': confidence
            }, status=status.HTTP_404_NOT_FOUND)

        # Obtener empleado reconocido
        try:
            employee = Employee.objects.get(id=best_match_id, is_active=True)
        except Employee.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Empleado no encontrado o inactivo'
            }, status=status.HTTP_404_NOT_FOUND)

        # Crear registro de asistencia
        attendance_record = AttendanceRecord.objects.create(
            employee=employee,
            attendance_type=attendance_type,
            confidence=confidence,
            location_lat=location_lat,
            location_lng=location_lng
        )

        return Response({
            'success': True,
            'message': f'Asistencia registrada: {attendance_type}',
            'employee': {
                'id': str(employee.id),
                'name': employee.name,
                'employee_id': employee.employee_id,
                'department': employee.department,
                'position': employee.position
            },
            'attendance': {
                'id': str(attendance_record.id),
                'type': attendance_type,
                'timestamp': attendance_record.timestamp.isoformat(),
                'confidence': f"{confidence:.2%}"
            }
        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error interno del servidor: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
def get_attendance_history(request, employee_id=None):
    """
    Obtiene historial de asistencia
    """
    try:
        # Filtrar por empleado específico si se proporciona
        if employee_id:
            try:
                employee = Employee.objects.get(id=employee_id)
                records = AttendanceRecord.objects.filter(employee=employee)
            except Employee.DoesNotExist:
                return Response({
                    'success': False,
                    'message': 'Empleado no encontrado'
                }, status=status.HTTP_404_NOT_FOUND)
        else:
            records = AttendanceRecord.objects.all()

        # Limitar a últimos 50 registros
        records = records[:50]
        
        serializer = AttendanceRecordSerializer(records, many=True)
        
        return Response({
            'success': True,
            'records': serializer.data,
            'count': len(serializer.data)
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error interno del servidor: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
def get_employees(request):
    """
    Lista todos los empleados registrados
    """
    try:
        employees = Employee.objects.filter(is_active=True)
        serializer = EmployeeSerializer(employees, many=True)
        
        return Response({
            'success': True,
            'employees': serializer.data,
            'count': len(serializer.data)
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error interno del servidor: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['DELETE'])
def delete_employee(request, employee_id):
    """
    Elimina un empleado (soft delete)
    """
    try:
        employee = Employee.objects.get(id=employee_id)
        employee.is_active = False
        employee.save()
        
        # Desactivar encodings faciales
        FaceEncoding.objects.filter(employee=employee).update(is_active=False)
        
        return Response({
            'success': True,
            'message': f'Empleado {employee.name} desactivado exitosamente'
        }, status=status.HTTP_200_OK)

    except Employee.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Empleado no encontrado'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error interno del servidor: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)