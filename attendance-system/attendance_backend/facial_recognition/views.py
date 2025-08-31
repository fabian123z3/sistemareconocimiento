from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from datetime import datetime, timedelta
import json
import base64
import io
from PIL import Image

from .models import Employee, FaceEncoding, AttendanceRecord
from .serializers import EmployeeSerializer, AttendanceRecordSerializer, FaceEncodingSerializer
from .face_recognition_utils import FaceRecognitionService

# Inicializar servicio de reconocimiento facial
face_service = FaceRecognitionService()

@api_view(['GET'])
def health_check(request):
    """
    Endpoint de salud para verificar que la API está funcionando
    """
    return Response({
        'status': 'OK',
        'message': 'Facial Recognition API is running',
        'timestamp': datetime.now().isoformat()
    }, status=status.HTTP_200_OK)

@api_view(['POST'])
def register_employee_face(request):
    """
    Registra un nuevo empleado con su encoding facial
    """
    try:
        data = request.data
        
        # Validar datos requeridos
        required_fields = ['name', 'employee_id', 'email', 'image']
        for field in required_fields:
            if not data.get(field):
                return Response({
                    'success': False,
                    'message': f'El campo {field} es requerido'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Verificar que el employee_id no exista
        if Employee.objects.filter(employee_id=data['employee_id']).exists():
            return Response({
                'success': False,
                'message': f'Ya existe un empleado con ID {data["employee_id"]}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validar calidad de imagen
        base64_image = data['image']
        is_valid, validation_message = face_service.validate_image_quality(base64_image)
        
        if not is_valid:
            return Response({
                'success': False,
                'message': f'Calidad de imagen insuficiente: {validation_message}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Preprocesar imagen
        processed_image = face_service.preprocess_image(base64_image)
        
        # Generar encoding facial
        encoding, encoding_message = face_service.encode_face_from_base64(processed_image)
        
        if not encoding:
            return Response({
                'success': False,
                'message': f'Error en reconocimiento facial: {encoding_message}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Crear usuario y empleado en transacción
        with transaction.atomic():
            # Crear usuario Django
            user = User.objects.create_user(
                username=data['employee_id'],
                email=data['email'],
                first_name=data['name'].split()[0],
                last_name=' '.join(data['name'].split()[1:]) if len(data['name'].split()) > 1 else ''
            )
            
            # Crear empleado
            employee = Employee.objects.create(
                user=user,
                employee_id=data['employee_id'],
                name=data['name'],
                email=data['email'],
                department=data.get('department', 'General'),
                position=data.get('position', 'Empleado'),
                is_active=True
            )
            
            # Crear encoding facial
            face_encoding = FaceEncoding.objects.create(
                employee=employee,
                encoding_data=json.dumps(encoding),
                is_active=True
            )
        
        # Serializar respuesta
        employee_data = EmployeeSerializer(employee).data
        
        return Response({
            'success': True,
            'message': f'Empleado {data["name"]} registrado exitosamente',
            'employee': employee_data,
            'encoding_id': str(face_encoding.id)
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error interno del servidor: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
def verify_attendance(request):
    """
    Verifica la asistencia usando reconocimiento facial
    """
    try:
        data = request.data
        
        # Validar datos requeridos
        if not data.get('image'):
            return Response({
                'success': False,
                'message': 'Se requiere una imagen para verificar'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if not data.get('type') or data.get('type') not in ['entrada', 'salida']:
            return Response({
                'success': False,
                'message': 'Tipo de asistencia debe ser "entrada" o "salida"'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        base64_image = data['image']
        attendance_type = data['type']
        
        # Validar calidad de imagen
        is_valid, validation_message = face_service.validate_image_quality(base64_image)
        if not is_valid:
            return Response({
                'success': False,
                'message': f'Calidad de imagen insuficiente: {validation_message}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Preprocesar imagen
        processed_image = face_service.preprocess_image(base64_image)
        
        # Generar encoding de la imagen actual
        unknown_encoding, encoding_message = face_service.encode_face_from_base64(processed_image)
        
        if not unknown_encoding:
            return Response({
                'success': False,
                'message': f'No se pudo procesar el rostro: {encoding_message}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Obtener todos los encodings activos
        active_encodings = FaceEncoding.objects.filter(
            is_active=True,
            employee__is_active=True
        ).select_related('employee')
        
        if not active_encodings.exists():
            return Response({
                'success': False,
                'message': 'No hay empleados registrados en el sistema'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Buscar mejor coincidencia
        best_match = None
        best_confidence = 0.0
        
        for face_encoding in active_encodings:
            try:
                stored_encoding = json.loads(face_encoding.encoding_data)
                is_match, confidence = face_service.compare_faces(
                    stored_encoding, 
                    unknown_encoding
                )
                
                if is_match and confidence > best_confidence:
                    best_match = face_encoding.employee
                    best_confidence = confidence
                    
            except Exception as e:
                continue
        
        # Verificar si se encontró una coincidencia válida
        if not best_match or best_confidence < 0.6:
            return Response({
                'success': False,
                'message': 'No se reconoció el rostro. Confianza insuficiente.'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Verificar reglas de asistencia
        today = timezone.now().date()
        last_record = AttendanceRecord.objects.filter(
            employee=best_match,
            timestamp__date=today
        ).order_by('-timestamp').first()
        
        # Validar lógica de entrada/salida
        if attendance_type == 'entrada' and last_record and last_record.attendance_type == 'entrada':
            # Verificar que no sea muy reciente (evitar duplicados)
            if (timezone.now() - last_record.timestamp).seconds < 300:  # 5 minutos
                return Response({
                    'success': False,
                    'message': 'Ya registraste entrada recientemente'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        elif attendance_type == 'salida' and (not last_record or last_record.attendance_type == 'salida'):
            return Response({
                'success': False,
                'message': 'Debes registrar entrada antes de la salida'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Crear registro de asistencia
        attendance_record = AttendanceRecord.objects.create(
            employee=best_match,
            attendance_type=attendance_type,
            confidence=best_confidence,
            location_lat=data.get('latitude'),
            location_lng=data.get('longitude'),
            notes=f'Reconocimiento automático - Confianza: {best_confidence:.1%}'
        )
        
        # Preparar respuesta
        employee_data = EmployeeSerializer(best_match).data
        attendance_data = {
            'id': str(attendance_record.id),
            'type': attendance_type,
            'timestamp': attendance_record.timestamp.isoformat(),
            'confidence': f"{best_confidence:.1%}",
            'location': {
                'latitude': attendance_record.location_lat,
                'longitude': attendance_record.location_lng
            } if attendance_record.location_lat else None
        }
        
        return Response({
            'success': True,
            'message': f'Asistencia registrada: {attendance_type.upper()}',
            'employee': employee_data,
            'attendance': attendance_data
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error interno del servidor: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
def get_attendance_history(request, employee_id=None):
    """
    Obtiene el historial de asistencia
    """
    try:
        # Filtros de query parameters
        days = int(request.GET.get('days', 30))  # Por defecto últimos 30 días
        attendance_type = request.GET.get('type')  # entrada/salida
        limit = int(request.GET.get('limit', 100))  # Máximo registros
        
        # Fecha desde
        date_from = timezone.now().date() - timedelta(days=days)
        
        # Query base
        queryset = AttendanceRecord.objects.filter(
            timestamp__date__gte=date_from
        ).select_related('employee')
        
        # Filtrar por empleado específico si se proporciona
        if employee_id:
            try:
                employee = Employee.objects.get(id=employee_id)
                queryset = queryset.filter(employee=employee)
            except Employee.DoesNotExist:
                return Response({
                    'success': False,
                    'message': 'Empleado no encontrado'
                }, status=status.HTTP_404_NOT_FOUND)
        
        # Filtrar por tipo de asistencia
        if attendance_type and attendance_type in ['entrada', 'salida']:
            queryset = queryset.filter(attendance_type=attendance_type)
        
        # Aplicar límite y orden
        records = queryset.order_by('-timestamp')[:limit]
        
        # Serializar datos
        serializer = AttendanceRecordSerializer(records, many=True)
        
        # Estadísticas adicionales
        stats = {
            'total_records': queryset.count(),
            'total_employees': queryset.values('employee').distinct().count(),
            'date_range': {
                'from': date_from.isoformat(),
                'to': timezone.now().date().isoformat()
            }
        }
        
        return Response({
            'success': True,
            'records': serializer.data,
            'stats': stats
        }, status=status.HTTP_200_OK)
        
    except ValueError:
        return Response({
            'success': False,
            'message': 'Parámetros de consulta inválidos'
        }, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error interno del servidor: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
def get_employees(request):
    """
    Obtiene la lista de empleados registrados
    """
    try:
        # Filtros opcionales
        active_only = request.GET.get('active_only', 'true').lower() == 'true'
        department = request.GET.get('department')
        search = request.GET.get('search')
        
        # Query base
        queryset = Employee.objects.all()
        
        # Aplicar filtros
        if active_only:
            queryset = queryset.filter(is_active=True)
        
        if department:
            queryset = queryset.filter(department__icontains=department)
        
        if search:
            queryset = queryset.filter(
                models.Q(name__icontains=search) |
                models.Q(employee_id__icontains=search) |
                models.Q(email__icontains=search)
            )
        
        # Serializar y retornar
        employees = queryset.order_by('name')
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
    Elimina un empleado del sistema (soft delete)
    """
    try:
        employee = Employee.objects.get(id=employee_id)
        
        # Desactivar empleado en lugar de eliminar
        employee.is_active = False
        employee.save()
        
        # Desactivar sus encodings faciales
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