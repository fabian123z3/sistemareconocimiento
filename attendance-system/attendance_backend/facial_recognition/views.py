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
import re

from .models import Employee, AttendanceRecord
from .serializers import EmployeeSerializer, AttendanceRecordSerializer
from .face_recognition_utils import AdvancedFaceRecognitionService

face_recognition_service = AdvancedFaceRecognitionService()
ADVANCED_CONFIG = face_recognition_service.ADVANCED_CONFIG

FACE_IMAGES_DIR = 'media/employee_faces/'
os.makedirs(FACE_IMAGES_DIR, exist_ok=True)


def validate_chilean_rut(rut):
    """Valida RUT chileno"""
    if not rut:
        return False
    
    # Limpiar RUT
    clean_rut = re.sub(r'[^0-9kK]', '', str(rut)).upper()
    if len(clean_rut) < 2:
        return False
    
    rut_body = clean_rut[:-1]
    dv = clean_rut[-1]
    
    # Validar que el cuerpo sean solo números
    if not rut_body.isdigit():
        return False
    
    # Calcular dígito verificador
    multiplier = 2
    sum_total = 0
    
    for digit in reversed(rut_body):
        sum_total += int(digit) * multiplier
        multiplier = 7 if multiplier == 2 else multiplier + 1
        if multiplier > 7:
            multiplier = 2
    
    remainder = sum_total % 11
    expected_dv = 'K' if remainder == 10 else str((11 - remainder) % 11)
    
    return dv == expected_dv


@api_view(['GET'])
def health_check(request):
    """Estado del sistema inteligente avanzado"""
    return Response({
        'status': 'OK',
        'message': 'Sistema de Reconocimiento Facial Avanzado con QR',
        'timestamp': datetime.now().isoformat(),
        'employees_count': Employee.objects.filter(is_active=True).count(),
        'attendance_today': AttendanceRecord.objects.filter(
            timestamp__date=timezone.now().date()
        ).count(),
        'system_config': {
            'mode': 'AVANZADO - Múltiples Variaciones Faciales + QR',
            'photos_required': ADVANCED_CONFIG['min_photos'],
            'tolerance': f"{ADVANCED_CONFIG['base_tolerance']} (adaptativo)",
            'min_confidence': f"{ADVANCED_CONFIG['min_confidence']:.0%}",
            'verification_timeout': f"{ADVANCED_CONFIG['verification_timeout']} segundos",
            'features': [
                'Registro con 8 fotos (diferentes condiciones)',
                'Detección robusta con/sin lentes',
                'Adaptación a cambios de iluminación',
                'Verificación por código QR + RUT',
                'Análisis multi-escala de características',
                'Timeout inteligente de verificación',
                'Sincronización offline'
            ]
        }
    })


@api_view(['POST'])
def create_employee(request):
    """Crear empleado con registro facial avanzado (8 fotos)"""
    try:
        data = request.data
        name = data.get('name', '').strip()
        rut = data.get('rut', '').strip()
        photos = data.get('photos', [])
        department = data.get('department', 'General').strip()
        position = data.get('position', 'Empleado').strip()
        email = data.get('email', '').strip()
        
        if not name or not rut:
            return Response({
                'success': False,
                'message': 'Nombre y RUT son requeridos'
            }, status=400)
        
        # Validar RUT
        if not validate_chilean_rut(rut):
            return Response({
                'success': False,
                'message': 'RUT inválido. Verifica el formato y dígito verificador.'
            }, status=400)
        
        # Verificar RUT único
        if Employee.objects.filter(rut=rut).exists():
            return Response({
                'success': False,
                'message': 'Ya existe un empleado con este RUT'
            }, status=400)
        
        if len(photos) < ADVANCED_CONFIG['min_photos']:
            return Response({
                'success': False,
                'message': f'Se requieren {ADVANCED_CONFIG["min_photos"]} fotos',
                'photos_received': len(photos),
                'photos_required': ADVANCED_CONFIG['min_photos']
            }, status=400)
        
        employee_id = f"EMP{str(uuid.uuid4())[:8].upper()}"
        while Employee.objects.filter(employee_id=employee_id).exists():
            employee_id = f"EMP{str(uuid.uuid4())[:8].upper()}"
        
        if not email:
            email = f"{employee_id.lower()}@empresa.com"
        
        face_data = face_recognition_service.process_advanced_registration(photos)
        
        min_valid_required = 5  # Mínimo 5 de 8 fotos válidas
        
        if face_data['valid_photos'] < min_valid_required:
            return Response({
                'success': False,
                'message': f'Solo {face_data["valid_photos"]} fotos válidas de {len(photos)}. Mínimo {min_valid_required}',
                'details': 'Asegúrate de que el rostro esté visible y bien iluminado en cada foto',
                'photos_processed': face_data['total_photos'],
                'valid_photos': face_data['valid_photos'],
                'failed_reasons': face_data.get('failed_reasons', [])
            }, status=400)
        
        employee = Employee.objects.create(
            employee_id=employee_id,
            name=name,
            rut=rut,
            email=email,
            department=department,
            position=position,
            is_active=True,
            has_face_registered=True,
            face_encoding=json.dumps({
                **face_data,
                'registration_date': datetime.now().isoformat(),
                'system_version': 'ADVANCED_v3.0',
                'rut': rut
            }),
            face_registration_date=timezone.now(),
            face_quality_score=face_data.get('average_quality', 0.8),
            face_variations_count=face_data['valid_photos']
        )
        
        # Guardar fotos de muestra
        for idx, photo in enumerate(photos[:ADVANCED_CONFIG['min_photos']]):
            try:
                if ',' in photo:
                    photo = photo.split(',')[1]
                
                image_data = base64.b64decode(photo)
                image = Image.open(io.BytesIO(image_data))
                
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                
                path = os.path.join(FACE_IMAGES_DIR, f"{employee.id}_variation_{idx+1}.jpg")
                image.save(path, 'JPEG', quality=95)
            except:
                pass
        
        serializer = EmployeeSerializer(employee)
        
        return Response({
            'success': True,
            'message': f'Empleado {name} creado con registro facial avanzado',
            'employee': serializer.data,
            'face_registered': True,
            'photos_processed': face_data['valid_photos'],
            'quality_score': f"{face_data.get('average_quality', 0.8):.1%}",
            'variations_registered': face_data['valid_photos']
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error: {str(e)}'
        }, status=500)


@api_view(['POST'])
def register_employee_face(request):
    """Registro facial avanzado con múltiples fotos"""
    try:
        data = request.data
        employee_id = data.get('employee_id')
        photos = data.get('photos', [])
        
        if not employee_id:
            return Response({
                'success': False,
                'message': 'Se requiere ID de empleado'
            }, status=400)
        
        if len(photos) < ADVANCED_CONFIG['min_photos']:
            return Response({
                'success': False,
                'message': f'Se requieren {ADVANCED_CONFIG["min_photos"]} fotos',
                'photos_received': len(photos),
                'photos_required': ADVANCED_CONFIG['min_photos']
            }, status=400)
        
        try:
            employee = Employee.objects.get(id=employee_id, is_active=True)
        except Employee.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Empleado no encontrado'
            }, status=404)
        
        face_data = face_recognition_service.process_advanced_registration(photos)
        
        min_valid_required = 5
        
        if face_data['valid_photos'] < min_valid_required:
            return Response({
                'success': False,
                'message': f'Solo {face_data["valid_photos"]} fotos válidas de {len(photos)}',
                'suggestion': 'Toma las fotos con buena iluminación, rostro completo visible',
                'failed_reasons': face_data.get('failed_reasons', [])
            }, status=400)
        
        # Guardar fotos
        for idx, photo in enumerate(photos[:ADVANCED_CONFIG['min_photos']]):
            try:
                if ',' in photo:
                    photo = photo.split(',')[1]
                
                image_data = base64.b64decode(photo)
                image = Image.open(io.BytesIO(image_data))
                
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                
                path = os.path.join(FACE_IMAGES_DIR, f"{employee_id}_variation_{idx+1}.jpg")
                image.save(path, 'JPEG', quality=95)
            except:
                pass
        
        face_data['registration_date'] = datetime.now().isoformat()
        face_data['system_version'] = 'ADVANCED_v3.0'
        face_data['rut'] = employee.rut
        
        employee.face_encoding = json.dumps(face_data)
        employee.has_face_registered = True
        employee.face_registration_date = timezone.now()
        employee.face_quality_score = face_data.get('average_quality', 0.8)
        employee.face_variations_count = face_data['valid_photos']
        employee.save()
        
        return Response({
            'success': True,
            'message': f'Registro facial avanzado completado para {employee.name}',
            'details': {
                'photos_processed': face_data['valid_photos'],
                'quality_score': f"{face_data.get('average_quality', 0.8):.1%}",
                'variations_count': face_data['valid_photos'],
                'features_extracted': len(face_data.get('encodings', [])),
                'environmental_adaptations': len(face_data.get('enhanced_variations', []))
            },
            'employee': {
                'id': str(employee.id),
                'name': employee.name,
                'rut': employee.rut,
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
    """Verificación facial avanzada con timeout"""
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
        
        print(f"\n🔍 Iniciando verificación avanzada con timeout de {ADVANCED_CONFIG['verification_timeout']}s...")
        start_time = time.time()
        
        verification_result, error = face_recognition_service.advanced_verify(
            photo_base64
        )
        
        elapsed_time = time.time() - start_time
        
        if error and "Timeout" in error:
            return Response({
                'success': False,
                'message': '⏱️ VERIFICACIÓN CANCELADA - Tiempo límite excedido',
                'timeout': True,
                'timeout_seconds': ADVANCED_CONFIG['verification_timeout'],
                'elapsed_time': f'{elapsed_time:.1f}s',
                'error_type': 'TIMEOUT',
                'suggestions': [
                    "🚫 Verifica que tu rostro esté registrado en el sistema",
                    "💡 Mejora la iluminación frontal",
                    "📱 Acércate más a la cámara",
                    "🎯 Centra tu rostro en la imagen",
                    "👓 Si usas lentes, asegúrate de que estén limpios"
                ]
            }, status=408)
        
        if error:
            return Response({
                'success': False,
                'message': f'❌ VERIFICACIÓN FALLIDA: {error}',
                'elapsed_time': f'{elapsed_time:.1f}s',
                'error_type': 'VERIFICATION_FAILED'
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
            return Response({
                'success': False,
                'message': '🚫 ACCESO DENEGADO - Rostro no autorizado',
                'error_type': 'UNAUTHORIZED',
                'elapsed_time': f'{elapsed_time:.1f}s',
                'required_confidence': f"{ADVANCED_CONFIG['min_confidence']:.0%}",
                'security_tips': [
                    '⚠️ Sistema en modo seguridad avanzada',
                    '📸 Asegúrate de estar registrado en el sistema',
                    '💡 Iluminación frontal uniforme requerida',
                    '🎯 Mirar directamente a la cámara'
                ]
            }, status=403)
        
        print(f"✅ VERIFICADO: {best_match.name} ({best_confidence:.1%}) en {elapsed_time:.1f}s")
        
        attendance_record = AttendanceRecord.objects.create(
            employee=best_match,
            attendance_type=attendance_type,
            timestamp=timezone.now(),
            location_lat=location_lat,
            location_lng=location_lng,
            address=address,
            verification_method='facial',
            face_confidence=best_confidence,
            notes=f'Verificación facial avanzada ({best_confidence:.1%}) - {elapsed_time:.1f}s'
        )
        
        serializer = AttendanceRecordSerializer(attendance_record)
        
        return Response({
            'success': True,
            'message': f'✅ {attendance_type.upper()} REGISTRADA',
            'employee': {
                'id': str(best_match.id),
                'name': best_match.name,
                'employee_id': best_match.employee_id,
                'rut': best_match.rut,
                'department': best_match.department
            },
            'verification': {
                'confidence': f'{best_confidence:.1%}',
                'method': 'FACIAL_RECOGNITION_ADVANCED',
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
def verify_qr(request):
    """Verificar asistencia por código QR + RUT"""
    try:
        data = request.data
        qr_data = data.get('qr_data', '').strip()
        attendance_type = data.get('type', 'entrada').lower()
        location_lat = data.get('latitude')
        location_lng = data.get('longitude')
        address = data.get('address', '')
        
        if not qr_data:
            return Response({
                'success': False,
                'message': 'Código QR requerido'
            }, status=400)
        
        print(f"\n🆔 Verificando QR: {qr_data}")
        
        # Extraer RUT del código QR (asumiendo que el QR contiene el RUT)
        # El QR puede contener solo el RUT o datos estructurados
        rut_from_qr = None
        
        try:
            # Intentar como JSON
            qr_json = json.loads(qr_data)
            rut_from_qr = qr_json.get('rut') or qr_json.get('RUT')
        except:
            # Asumir que el QR contiene directamente el RUT
            rut_from_qr = qr_data
        
        if not rut_from_qr:
            return Response({
                'success': False,
                'message': 'No se pudo extraer RUT del código QR'
            }, status=400)
        
        # Limpiar y validar RUT
        clean_rut = re.sub(r'[^0-9kK.-]', '', str(rut_from_qr)).upper()
        
        if not validate_chilean_rut(clean_rut):
            return Response({
                'success': False,
                'message': 'RUT del código QR no es válido'
            }, status=400)
        
        # Buscar empleado por RUT (búsqueda flexible)
        try:
            employee = Employee.objects.get(rut__iexact=clean_rut, is_active=True)
        except Employee.DoesNotExist:
            return Response({
                'success': False,
                'message': f'Empleado con RUT {clean_rut} no encontrado o inactivo'
            }, status=404)
        
        # Crear registro de asistencia
        attendance_record = AttendanceRecord.objects.create(
            employee=employee,
            attendance_type=attendance_type,
            timestamp=timezone.now(),
            location_lat=location_lat,
            location_lng=location_lng,
            address=address,
            verification_method='qr',
            qr_verified=True,
            notes=f'Verificación QR exitosa - RUT: {clean_rut}'
        )
        
        serializer = AttendanceRecordSerializer(attendance_record)
        
        return Response({
            'success': True,
            'message': f'✅ {attendance_type.upper()} REGISTRADA VIA QR',
            'employee': {
                'id': str(employee.id),
                'name': employee.name,
                'employee_id': employee.employee_id,
                'rut': employee.rut,
                'department': employee.department
            },
            'verification': {
                'method': 'QR_CODE_VERIFIED',
                'rut_verified': clean_rut,
                'security_level': 'ALTO'
            },
            'record': serializer.data,
            'timestamp': timezone.now().strftime('%d/%m/%Y %H:%M:%S')
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error verificando QR: {str(e)}',
            'error_type': 'QR_VERIFICATION_ERROR'
        }, status=500)


@api_view(['POST'])
def mark_attendance(request):
    """Marcar asistencia manual o procesar verificación"""
    try:
        data = request.data
        
        # Si viene foto, usar verificación facial
        if data.get('photo'):
            return verify_attendance_face(request)
        
        # Si viene QR, usar verificación QR
        if data.get('qr_data'):
            return verify_qr(request)
        
        # Marcado manual
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
                    'message': f'Múltiples empleados encontrados con ese nombre'
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
            verification_method='manual',
            notes=notes or 'Registro manual/GPS',
            is_offline_sync=is_offline_sync
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
                'rut': employee.rut,
                'department': employee.department
            },
            'method': 'MANUAL/GPS'
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error: {str(e)}'
        }, status=500)


# [El resto de las funciones continúan igual: sync_offline_records, get_employees, get_attendance_records, delete_employee, delete_attendance, attendance_panel]

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
                elif record_data.get('qr_data'):
                    mock_request = HttpRequest()
                    mock_request.method = 'POST'
                    mock_request.data = {
                        'qr_data': record_data['qr_data'],
                        'type': record_data.get('type', 'entrada'),
                        'latitude': record_data.get('latitude'),
                        'longitude': record_data.get('longitude'),
                        'address': record_data.get('address', ''),
                        'is_offline_sync': True,
                        'offline_timestamp': record_data.get('timestamp')
                    }
                    response = verify_qr(mock_request)
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
            'system_mode': 'AVANZADO_CON_QR',
            'features': {
                'facial_recognition': True,
                'qr_verification': True,
                'offline_sync': True,
                'advanced_variations': True
            }
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
                'advanced_recognition': True,
                'qr_support': True,
                'timeout_seconds': ADVANCED_CONFIG['verification_timeout']
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
        
        # Eliminar fotos guardadas
        for i in range(1, ADVANCED_CONFIG['min_photos'] + 1):
            path = os.path.join(FACE_IMAGES_DIR, f"{employee_id}_variation_{i}.jpg")
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