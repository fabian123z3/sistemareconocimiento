from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.db import transaction
from django.shortcuts import render
from datetime import datetime, timedelta
import uuid
import json
import base64
import os
from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageDraw
import io
import face_recognition
import numpy as np
import cv2
from scipy.spatial import distance
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.http import HttpRequest

from .models import Employee, AttendanceRecord
from .serializers import EmployeeSerializer, AttendanceRecordSerializer
from .face_recognition_utils import ImprovedFaceRecognitionService

face_recognition_service = ImprovedFaceRecognitionService()
SMART_CONFIG = face_recognition_service.SMART_CONFIG

FACE_IMAGES_DIR = 'media/employee_faces/'
os.makedirs(FACE_IMAGES_DIR, exist_ok=True)


@api_view(['GET'])
def health_check(request):
    """Estado del sistema inteligente"""
    return Response({
        'status': 'OK',
        'message': 'Sistema de Reconocimiento Facial Inteligente',
        'timestamp': datetime.now().isoformat(),
        'employees_count': Employee.objects.filter(is_active=True).count(),
        'attendance_today': AttendanceRecord.objects.filter(
            timestamp__date=timezone.now().date()
        ).count(),
        'system_config': {
            'mode': 'INTELIGENTE - Vectores Faciales',
            'tolerance': f"{SMART_CONFIG['base_tolerance']} (adaptativo)",
            'min_confidence': f"{SMART_CONFIG['min_confidence']:.0%}",
            'photos_required': SMART_CONFIG['min_photos'],
            'verification_timeout': f"{SMART_CONFIG['verification_timeout']} segundos",
            'features': [
                'Detección de puntos faciales',
                'Normalización de características',
                'Tolerancia adaptativa',
                'Augmentación de datos',
                'Análisis multi-escala',
                'Timeout de verificación'
            ]
        }
    })


@api_view(['POST'])
def create_employee(request):
    """Crear empleado con registro facial (fotos)"""
    try:
        data = request.data
        name = data.get('name', '').strip()
        photos = data.get('photos', [])
        department = data.get('department', 'General').strip()
        position = data.get('position', 'Empleado').strip()
        email = data.get('email', '').strip()
        
        if not name:
            return Response({
                'success': False,
                'message': 'El nombre es requerido'
            }, status=400)
        
        if len(photos) < SMART_CONFIG['min_photos']:
            return Response({
                'success': False,
                'message': f'Se requieren {SMART_CONFIG["min_photos"]} fotos',
                'photos_received': len(photos),
                'photos_required': SMART_CONFIG['min_photos']
            }, status=400)
        
        employee_id = f"EMP{str(uuid.uuid4())[:8].upper()}"
        while Employee.objects.filter(employee_id=employee_id).exists():
            employee_id = f"EMP{str(uuid.uuid4())[:8].upper()}"
        
        if not email:
            email = f"{employee_id.lower()}@empresa.com"
        
        face_data = face_recognition_service.process_registration_photos(photos)
        
        min_valid_required = 3
        
        if face_data['valid_photos'] < min_valid_required:
            return Response({
                'success': False,
                'message': f'Solo {face_data["valid_photos"]} fotos válidas. Mínimo {min_valid_required}',
                'details': f'Fotos fallidas: {face_data.get("failed_photos", [])}',
                'photos_processed': face_data['total_photos'],
                'valid_photos': face_data['valid_photos']
            }, status=400)
        
        employee = Employee.objects.create(
            employee_id=employee_id,
            name=name,
            email=email,
            department=department,
            position=position,
            is_active=True,
            has_face_registered=True,
            face_encoding=json.dumps({
                **face_data,
                'registration_date': datetime.now().isoformat(),
                'system_version': 'SMART_v2.0'
            }),
            face_registration_date=timezone.now(),
            face_quality_score=1.0
        )
        
        for idx, photo in enumerate(photos[:SMART_CONFIG['min_photos']]):
            try:
                if ',' in photo:
                    photo = photo.split(',')[1]
                
                image_data = base64.b64decode(photo)
                image = Image.open(io.BytesIO(image_data))
                
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                
                path = os.path.join(FACE_IMAGES_DIR, f"{employee.id}_photo_{idx+1}.jpg")
                image.save(path, 'JPEG', quality=95)
            except:
                pass
        
        serializer = EmployeeSerializer(employee)
        
        return Response({
            'success': True,
            'message': f'Empleado {name} creado',
            'employee': serializer.data,
            'face_registered': True,
            'photos_processed': face_data['valid_photos']
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error: {str(e)}'
        }, status=500)

@api_view(['POST'])
def register_employee_face(request):
    """Registro inteligente con múltiples fotos"""
    try:
        data = request.data
        employee_id = data.get('employee_id')
        photos = data.get('photos', [])
        
        if not employee_id:
            return Response({
                'success': False,
                'message': 'Se requiere ID de empleado'
            }, status=400)
        
        if len(photos) < SMART_CONFIG['min_photos']:
            return Response({
                'success': False,
                'message': f'Se requieren {SMART_CONFIG["min_photos"]} fotos',
                'photos_received': len(photos),
                'photos_required': SMART_CONFIG['min_photos']
            }, status=400)
        
        try:
            employee = Employee.objects.get(id=employee_id, is_active=True)
        except Employee.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Empleado no encontrado'
            }, status=404)
        
        face_data = face_recognition_service.process_registration_photos(photos)
        
        min_valid_required = 3
        
        if face_data['valid_photos'] < min_valid_required:
            return Response({
                'success': False,
                'message': f'Solo {face_data["valid_photos"]} fotos válidas',
                'photos_with_issues': face_data.get('failed_photos', []),
                'total_received': face_data['total_photos'],
                'suggestion': 'Asegúrate de que el rostro esté visible'
            }, status=400)
        
        for idx, photo in enumerate(photos[:SMART_CONFIG['min_photos']]):
            try:
                if ',' in photo:
                    photo = photo.split(',')[1]
                
                image_data = base64.b64decode(photo)
                image = Image.open(io.BytesIO(image_data))
                
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                
                path = os.path.join(FACE_IMAGES_DIR, f"{employee_id}_photo_{idx+1}.jpg")
                image.save(path, 'JPEG', quality=95)
            except:
                pass
        
        face_data['registration_date'] = datetime.now().isoformat()
        face_data['system_version'] = 'SMART_v2.0'
        
        employee.face_encoding = json.dumps(face_data)
        employee.has_face_registered = True
        employee.face_registration_date = timezone.now()
        employee.face_quality_score = 1.0
        employee.save()
        
        return Response({
            'success': True,
            'message': f'Registro inteligente completado',
            'details': {
                'photos_processed': face_data['valid_photos'],
                'encodings_created': len(face_data['encodings']),
                'augmented_variations': sum(len(a) for a in face_data['augmented']),
                'landmarks_extracted': len([l for l in face_data['landmarks'] if l])
            },
            'employee': {
                'id': str(employee.id),
                'name': employee.name,
                'ready': True
            }
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error: {str(e)}'
        }, status=500)

@api_view(['POST'])
def verify_attendance_face(request):
    """Verificación inteligente con timeout de 10 segundos"""
    try:
        data = request.data
        photo_base64 = data.get('photo')
        attendance_type = data.get('type', 'entrada').lower()
        location_lat = data.get('latitude')
        location_lng = data.get('longitude')
        address = data.get('address', '')
        
        if not photo_base64:
            return Response({
                'success': False,
                'message': 'Se requiere foto'
            }, status=400)
        
        print(f"\n⏱️ Iniciando verificación con timeout de {SMART_CONFIG['verification_timeout']}s...")
        start_time = time.time()
        
        verification_result, error = face_recognition_service.intelligent_verify(
            photo_base64
        )
        
        elapsed_time = time.time() - start_time
        
        if error and "Timeout" in error:
            return Response({
                'success': False,
                'message': '⏱️ VERIFICACIÓN CANCELADA - Tiempo límite excedido',
                'timeout': True,
                'timeout_seconds': SMART_CONFIG['verification_timeout'],
                'elapsed_time': f'{elapsed_time:.1f}s',
                'error_type': 'TIMEOUT',
                'suggestions': [
                    "🚫 El rostro no es válido o el sistema está saturado",
                    "💡 Intenta nuevamente con mejor iluminación frontal",
                    "📱 Acércate más a la cámara",
                    "🎯 Centra tu rostro en la imagen",
                    "⚡ Evita sombras"
                ],
                'retry_instructions': [
                    "1. Mejora la iluminación de tu rostro",
                    "2. Mira directamente a la cámara",
                    "3. Rostro completamente visible",
                    "4. Intenta en un lugar con mejor señal"
                ]
            }, status=408)
        
        if error:
            return Response({
                'success': False,
                'message': f'❌ VERIFICACIÓN FALLIDA: {error}',
                'elapsed_time': f'{elapsed_time:.1f}s',
                'error_type': 'VERIFICATION_FAILED',
                'suggestions': [
                    "Asegúrate de que tu rostro esté bien iluminado",
                    "Mira directamente a la cámara",
                    "Verifica que no haya sombras"
                ]
            }, status=400)
        
        if not verification_result:
            return Response({
                'success': False,
                'message': 'Error interno procesando verificación',
                'elapsed_time': f'{elapsed_time:.1f}s'
            }, status=500)
        
        best_match = verification_result['best_match']
        best_confidence = verification_result['best_confidence']
        all_results = verification_result['all_results']
        
        if not best_match:
            if all_results:
                closest = max(all_results, key=lambda x: x['confidence'])
                
                return Response({
                    'success': False,
                    'message': '🚫 ACCESO DENEGADO - Rostro no autorizado',
                    'error_type': 'UNAUTHORIZED',
                    'closest_match': closest['employee'].name if closest['confidence'] > 0.3 else 'Ninguna coincidencia',
                    'closest_confidence': f"{closest['confidence']:.1%}",
                    'required_confidence': f"{SMART_CONFIG['min_confidence']:.0%}",
                    'elapsed_time': f'{elapsed_time:.1f}s',
                    'security_level': '🔒 MODO ESTRICTO ACTIVADO',
                    'security_tips': [
                        '⚠️ Sistema en modo seguridad máxima',
                        '📸 Rostro completo debe estar visible',
                        '🚫 No cubrir ninguna parte del rostro',
                        '💡 Iluminación frontal uniforme requerida',
                        '🎯 Mirar directamente a la cámara',
                        '📏 Acercarse para rostro más grande'
                    ],
                    'action_required': 'Verifica tu identidad o contacta al administrador'
                }, status=403)
            else:
                return Response({
                    'success': False,
                    'message': '❌ No hay empleados registrados',
                    'elapsed_time': f'{elapsed_time:.1f}s',
                    'action_required': 'Contacta al administrador'
                }, status=404)
        
        print(f"✅ VERIFICADO: {best_match.name} ({best_confidence:.1%}) en {elapsed_time:.1f}s")
        
        attendance_record = AttendanceRecord.objects.create(
            employee=best_match,
            attendance_type=attendance_type,
            timestamp=timezone.now(),
            location_lat=location_lat,
            location_lng=location_lng,
            address=address,
            face_confidence=best_confidence,
            notes=f'Verificación facial ({best_confidence:.1%}) - {elapsed_time:.1f}s'
        )
        
        serializer = AttendanceRecordSerializer(attendance_record)
        
        return Response({
            'success': True,
            'message': f'✅ {attendance_type.upper()} REGISTRADA',
            'employee': {
                'id': str(best_match.id),
                'name': best_match.name,
                'employee_id': best_match.employee_id,
                'department': best_match.department
            },
            'verification': {
                'confidence': f'{best_confidence:.1%}',
                'method': 'FACIAL_RECOGNITION_STRICT',
                'elapsed_time': f'{elapsed_time:.1f}s',
                'security_level': 'MÁXIMO'
            },
            'record': serializer.data,
            'timestamp': timezone.now().strftime('%d/%m/%Y %H:%M:%S')
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error crítico: {str(e)}',
            'error_type': 'SYSTEM_ERROR'
        }, status=500)

@api_view(['POST'])
def mark_attendance(request):
    """Marcar asistencia manual"""
    try:
        data = request.data
        
        if data.get('photo'):
            return verify_attendance_face(request)
        
        employee_name = data.get('employee_name', '').strip()
        employee_id = data.get('employee_id', '').strip()
        attendance_type = data.get('type', 'entrada').lower()
        location_lat = data.get('latitude')
        location_lng = data.get('longitude')
        address = data.get('address', '')
        notes = data.get('notes', '')
        is_offline_sync = data.get('is_offline_sync', False)
        offline_timestamp = data.get('offline_timestamp')
        
        if not employee_name and not employee_id:
            return Response({
                'success': False,
                'message': 'Se requiere nombre o ID del empleado'
            }, status=400)
        
        employee = None
        if employee_id:
            try:
                employee = Employee.objects.get(employee_id=employee_id, is_active=True)
            except Employee.DoesNotExist:
                pass
        
        if not employee and employee_name:
            try:
                employee = Employee.objects.get(name__icontains=employee_name, is_active=True)
            except Employee.DoesNotExist:
                pass
            except Employee.MultipleObjectsReturned:
                return Response({
                    'success': False,
                    'message': f'Múltiples empleados encontrados'
                }, status=400)
        
        if not employee:
            return Response({
                'success': False,
                'message': f'Empleado no encontrado'
            }, status=404)
        
        if is_offline_sync and offline_timestamp:
            try:
                record_timestamp = datetime.fromisoformat(
                    offline_timestamp.replace('Z', '+00:00')
                )
                if record_timestamp.tzinfo is None:
                    record_timestamp = timezone.make_aware(record_timestamp)
            except:
                record_timestamp = timezone.now()
        else:
            record_timestamp = timezone.now()
        
        attendance_record = AttendanceRecord.objects.create(
            employee=employee,
            attendance_type=attendance_type,
            timestamp=record_timestamp,
            location_lat=location_lat,
            location_lng=location_lng,
            address=address,
            notes=notes or 'Registro manual/GPS',
            is_offline_sync=is_offline_sync,
            face_confidence=0
        )
        
        serializer = AttendanceRecordSerializer(attendance_record)
        
        return Response({
            'success': True,
            'message': f'✅ {attendance_type.upper()} registrada manualmente',
            'record': serializer.data,
            'employee': {
                'id': str(employee.id),
                'name': employee.name,
                'employee_id': employee.employee_id,
                'department': employee.department
            },
            'method': 'MANUAL/GPS'
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error: {str(e)}'
        }, status=500)

@api_view(['POST'])
def sync_offline_records(request):
    """Sincronizar registros offline"""
    try:
        offline_records = request.data.get('offline_records', [])
        synced_count = 0
        errors = []
        
        for record_data in offline_records:
            try:
                if record_data.get('photo'):
                    mock_request = HttpRequest()
                    mock_request.method = 'POST'
                    mock_request.data = {
                        'photo': record_data['photo'],
                        'type': record_data.get('type', 'entrada'),
                        'latitude': record_data.get('latitude'),
                        'longitude': record_data.get('longitude'),
                        'address': record_data.get('address', ''),
                        'is_offline_sync': True,
                        'offline_timestamp': record_data.get('timestamp')
                    }
                    response = verify_attendance_face(mock_request)
                else:
                    mock_request = HttpRequest()
                    mock_request.method = 'POST'
                    mock_request.data = {
                        'employee_name': record_data.get('employee_name'),
                        'employee_id': record_data.get('employee_id'),
                        'type': record_data.get('type'),
                        'latitude': record_data.get('latitude'),
                        'longitude': record_data.get('longitude'),
                        'address': record_data.get('address', ''),
                        'notes': 'Sincronizado offline',
                        'is_offline_sync': True,
                        'offline_timestamp': record_data.get('timestamp')
                    }
                    response = mark_attendance(mock_request)
                
                if response.status_code in [200, 201]:
                    synced_count += 1
                else:
                    errors.append({
                        'local_id': record_data.get('local_id'),
                        'error': response.data.get('message')
                    })
                    
            except Exception as e:
                errors.append({
                    'local_id': record_data.get('local_id', 'unknown'),
                    'error': str(e)
                })
        
        return Response({
            'success': True,
            'synced_count': synced_count,
            'error_count': len(errors),
            'errors': errors[:10],
            'message': f'Sincronizados {synced_count} de {len(offline_records)} registros'
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error: {str(e)}'
        }, status=500)

@api_view(['GET'])
def get_employees(request):
    """Obtener empleados"""
    try:
        employees = Employee.objects.filter(is_active=True).order_by('name')
        serializer = EmployeeSerializer(employees, many=True)
        
        return Response({
            'success': True,
            'employees': serializer.data,
            'count': employees.count(),
            'system_mode': 'INTELIGENTE_CON_TIMEOUT',
            'timeout_enabled': True,
            'timeout_seconds': SMART_CONFIG['verification_timeout'],
            'security_level': 'MÁXIMO'
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error: {str(e)}'
        }, status=500)

@api_view(['GET'])
def get_attendance_records(request):
    """Obtener registros"""
    try:
        days = int(request.GET.get('days', 7))
        employee_id = request.GET.get('employee_id')
        limit = int(request.GET.get('limit', 100))
        
        date_from = timezone.now().date() - timedelta(days=days)
        queryset = AttendanceRecord.objects.select_related('employee').filter(
            timestamp__date__gte=date_from
        ).order_by('-timestamp')
        
        if employee_id:
            try:
                employee = Employee.objects.get(id=employee_id)
                queryset = queryset.filter(employee=employee)
            except Employee.DoesNotExist:
                pass
        
        total_count = queryset.count()
        records = queryset[:limit]
        serializer = AttendanceRecordSerializer(records, many=True)
        
        return Response({
            'success': True,
            'records': serializer.data,
            'count': len(serializer.data),
            'total': total_count,
            'system_info': {
                'timeout_enabled': True,
                'timeout_seconds': SMART_CONFIG['verification_timeout']
            }
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error: {str(e)}'
        }, status=500)

@api_view(['DELETE'])
def delete_employee(request, employee_id):
    """Eliminar empleado completamente"""
    try:
        employee = Employee.objects.get(id=employee_id)
        employee_name = employee.name
        
        for i in range(1, 6):
            path = os.path.join(FACE_IMAGES_DIR, f"{employee_id}_photo_{i}.jpg")
            if os.path.exists(path):
                os.remove(path)
        
        AttendanceRecord.objects.filter(employee=employee).delete()
        employee.delete()
        
        return Response({
            'success': True,
            'message': f'{employee_name} eliminado completamente'
        })
        
    except Employee.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Empleado no encontrado'
        }, status=404)
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error: {str(e)}'
        }, status=500)

@api_view(['DELETE'])
def delete_attendance(request, attendance_id):
    """Eliminar registro de asistencia"""
    try:
        attendance_record = AttendanceRecord.objects.get(id=attendance_id)
        employee_name = attendance_record.employee.name
        attendance_type = attendance_record.attendance_type
        timestamp = attendance_record.timestamp.strftime('%d/%m/%Y %H:%M')
        
        attendance_record.delete()
        
        return Response({
            'success': True,
            'message': f'Registro eliminado: {employee_name} - {attendance_type} - {timestamp}'
        })
        
    except AttendanceRecord.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Registro no encontrado'
        }, status=404)
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error: {str(e)}'
        }, status=500)

def attendance_panel(request):
    """Panel web"""
    return render(request, 'attendance_panel.html')


# Nuevas vistas para el registro de video
@api_view(['POST'])
def register_face_video(request):
    """Registro inteligente con un video"""
    try:
        employee_id = request.data.get('employee_id')
        video_file = request.FILES.get('video')

        if not employee_id or not video_file:
            return Response({'success': False, 'message': 'Faltan campos requeridos'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            employee = Employee.objects.get(id=employee_id, is_active=True)
        except Employee.DoesNotExist:
            return Response({'success': False, 'message': 'Empleado no encontrado'}, status=status.HTTP_404_NOT_FOUND)

        temp_path = default_storage.save(f"temp_videos/{uuid.uuid4()}.mp4", ContentFile(video_file.read()))
        full_path = default_storage.path(temp_path)

        encodings, message = face_recognition_service.process_video_for_encodings(full_path)

        default_storage.delete(temp_path)

        if not encodings:
            return Response({'success': False, 'message': message}, status=status.HTTP_400_BAD_REQUEST)
        
        employee.face_encoding = json.dumps(encodings)
        employee.has_face_registered = True
        employee.face_registration_date = timezone.now()
        employee.save()
        
        return Response({'success': True, 'message': 'Rostro registrado con éxito a partir de video'}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'success': False, 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def create_employee_with_video(request):
    """Crear empleado con registro facial por video"""
    try:
        name = request.data.get('name')
        department = request.data.get('department', 'General').strip()
        position = request.data.get('position', 'Empleado').strip()
        email = request.data.get('email', '').strip()
        video_file = request.FILES.get('video')
        
        if not name or not video_file:
            return Response({'success': False, 'message': 'Faltan campos requeridos'}, status=status.HTTP_400_BAD_REQUEST)

        employee_id = f"EMP{str(uuid.uuid4())[:8].upper()}"
        while Employee.objects.filter(employee_id=employee_id).exists():
            employee_id = f"EMP{str(uuid.uuid4())[:8].upper()}"

        if not email:
            email = f"{employee_id.lower()}@empresa.com"

        temp_path = default_storage.save(f"temp_videos/{uuid.uuid4()}.mp4", ContentFile(video_file.read()))
        full_path = default_storage.path(temp_path)
        
        encodings, message = face_recognition_service.process_video_for_encodings(full_path)

        default_storage.delete(temp_path)

        if not encodings:
            return Response({'success': False, 'message': message}, status=status.HTTP_400_BAD_REQUEST)
        
        employee = Employee.objects.create(
            name=name,
            employee_id=employee_id,
            department=department,
            position=position,
            email=email,
            is_active=True,
            has_face_registered=True,
            face_encoding=json.dumps(encodings),
            face_registration_date=timezone.now(),
        )
        
        serializer = EmployeeSerializer(employee)
        
        return Response({'success': True, 'message': 'Empleado creado y rostro registrado por video', 'employee': serializer.data}, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response({'success': False, 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)