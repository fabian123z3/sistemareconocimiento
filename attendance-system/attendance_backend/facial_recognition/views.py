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

def _create_manual_attendance_record(employee, attendance_type, location_lat, location_lng, address, notes, is_offline_sync, offline_timestamp):
    """
    Función auxiliar para crear un registro de asistencia manual.
    Centraliza la lógica para ser usada por múltiples vistas.
    """
    if is_offline_sync and offline_timestamp:
        try:
            # Intenta convertir el timestamp ISO del cliente a un objeto de zona horaria consciente
            record_timestamp = datetime.fromisoformat(offline_timestamp.replace('Z', '+00:00'))
            if record_timestamp.tzinfo is None:
                record_timestamp = timezone.make_aware(record_timestamp)
        except (ValueError, TypeError):
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
    return attendance_record

def validate_chilean_rut(rut):
    """Valida RUT chileno con formato flexible"""
    if not rut:
        return False
    
    clean_rut = re.sub(r'[^0-9kK]', '', str(rut).strip()).upper()
    
    if len(clean_rut) < 8 or len(clean_rut) > 9:
        return False
    
    rut_body = clean_rut[:-1]
    dv = clean_rut[-1]
    
    if not rut_body.isdigit():
        return False
    
    multiplier = 2
    sum_total = 0
    
    for digit in reversed(rut_body):
        sum_total += int(digit) * multiplier
        multiplier = multiplier + 1 if multiplier < 7 else 2
    
    remainder = sum_total % 11
    if remainder == 0:
        expected_dv = '0'
    elif remainder == 1:
        expected_dv = 'K'
    else:
        expected_dv = str(11 - remainder)
    
    return dv == expected_dv

def format_rut_for_storage(rut):
    """Formatea RUT para almacenamiento consistente"""
    if not rut:
        return rut
    
    clean_rut = re.sub(r'[^0-9kK]', '', str(rut).strip()).upper()
    
    if len(clean_rut) < 2:
        return clean_rut
    
    rut_body = clean_rut[:-1]
    dv = clean_rut[-1]
    
    return f"{rut_body}-{dv}"

def search_employee_by_rut(rut):
    """Busca empleado por RUT con diferentes formatos"""
    if not rut:
        return None
    
    clean_rut = re.sub(r'[^0-9kK]', '', str(rut).strip()).upper()
    
    if len(clean_rut) < 2:
        return None
    
    rut_body = clean_rut[:-1]
    dv = clean_rut[-1]
    formatted_rut = f"{rut_body}-{dv}"
    
    try:
        return Employee.objects.get(rut=formatted_rut, is_active=True)
    except Employee.DoesNotExist:
        try:
            return Employee.objects.get(rut=clean_rut, is_active=True)
        except Employee.DoesNotExist:
            employees = Employee.objects.filter(is_active=True)
            for emp in employees:
                if emp.rut:
                    emp_clean = re.sub(r'[^0-9kK]', '', emp.rut).upper()
                    if emp_clean == clean_rut:
                        return emp
            return None

@api_view(['GET'])
def health_check(request):
    """Estado del sistema balanceado"""
    return Response({
        'status': 'OK',
        'message': 'Sistema de Reconocimiento Facial Balanceado - 5 Fotos',
        'timestamp': datetime.now().isoformat(),
        'employees_count': Employee.objects.filter(is_active=True).count(),
        'employees_with_faces': Employee.objects.filter(is_active=True, has_face_registered=True).count(),
        'attendance_today': AttendanceRecord.objects.filter(
            timestamp__date=timezone.now().date()
        ).count(),
        'system_config': {
            'mode': 'BALANCEADO - Registro Facial de 5 Fotos',
            'photos_required': ADVANCED_CONFIG['min_photos'],  # 5 fotos
            'tolerance': f"{ADVANCED_CONFIG['base_tolerance']} (balanceado)",
            'min_confidence': f"{ADVANCED_CONFIG['min_confidence']:.0%}",  # 75%
            'verification_timeout': f"{ADVANCED_CONFIG['verification_timeout']} segundos",  # 12s
            'features': [
                'Registro básico de empleados (solo nombre y RUT)',
                'Registro facial optimizado con 5 fotos',
                'Detección balanceada para condiciones reales',
                'Tolerancia mejorada a variaciones de iluminación',
                'Verificación por código QR + RUT',
                'Procesamiento más rápido y eficiente',
                'Timeout inteligente reducido',
                'Sincronización offline optimizada'
            ],
            'improvements': [
                'Solo 5 fotos necesarias (era 8)',
                'Verificación más rápida (12s vs 15s)',
                'Mayor tolerancia a condiciones de luz',
                'Procesamiento optimizado',
                'Mejor experiencia de usuario'
            ]
        }
    })

@api_view(['POST'])
def create_employee_basic(request):
    """Crear empleado básico sin registro facial"""
    try:
        data = request.data
        name = data.get('name', '').strip()
        rut = data.get('rut', '').strip()
        department = data.get('department', 'General').strip()
        position = data.get('position', 'Empleado').strip()
        email = data.get('email', '').strip()
        
        if not name or not rut:
            return Response({
                'success': False,
                'message': 'Nombre y RUT son requeridos'
            }, status=400)
        
        formatted_rut = format_rut_for_storage(rut)
        
        if not validate_chilean_rut(formatted_rut):
            return Response({
                'success': False,
                'message': f'RUT inválido: {rut}. Verifica el formato y dígito verificador.'
            }, status=400)
        
        if Employee.objects.filter(rut=formatted_rut).exists():
            return Response({
                'success': False,
                'message': f'Ya existe un empleado con RUT {formatted_rut}'
            }, status=400)
        
        employee_id = f"EMP{str(uuid.uuid4())[:8].upper()}"
        while Employee.objects.filter(employee_id=employee_id).exists():
            employee_id = f"EMP{str(uuid.uuid4())[:8].upper()}"
        
        if not email:
            email = f"{employee_id.lower()}@empresa.com"
        
        employee = Employee.objects.create(
            employee_id=employee_id,
            name=name,
            rut=formatted_rut,
            email=email,
            department=department,
            position=position,
            is_active=True,
            has_face_registered=False,
            face_quality_score=0,
            face_variations_count=0
        )
        
        serializer = EmployeeSerializer(employee)
        
        return Response({
            'success': True,
            'message': f'Empleado {name} creado exitosamente',
            'employee': serializer.data,
            'face_registered': False,
            'next_step': f'Puedes registrar su rostro posteriormente (solo {ADVANCED_CONFIG["min_photos"]} fotos necesarias)'
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error: {str(e)}'
        }, status=500)

@api_view(['POST'])
def register_employee_face(request):
    """Registro facial balanceado con 5 fotos"""
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
        
        # Procesar con el servicio balanceado
        face_data = face_recognition_service.process_advanced_registration(photos)
        
        # Requisito más flexible: mínimo 3 de 5 fotos válidas
        min_valid_required = max(3, ADVANCED_CONFIG['min_photos'] - 2)
        
        if not face_data.get('success', True) or face_data['valid_photos'] < min_valid_required:
            return Response({
                'success': False,
                'message': f'Solo {face_data["valid_photos"]} fotos válidas de {len(photos)}. Mínimo {min_valid_required}',
                'details': f'Sistema balanceado requiere al menos {min_valid_required} fotos válidas',
                'photos_processed': face_data['total_photos'],
                'valid_photos': face_data['valid_photos'],
                'failed_reasons': face_data.get('failed_reasons', []),
                'suggestion': 'Toma las fotos con buena iluminación frontal y rostro completamente visible'
            }, status=400)
        
        # Guardar fotos de muestra
        for idx, photo in enumerate(photos[:ADVANCED_CONFIG['min_photos']]):
            try:
                if ',' in photo:
                    photo = photo.split(',')[1]
                
                image_data = base64.b64decode(photo)
                image = Image.open(io.BytesIO(image_data))
                
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                
                path = os.path.join(FACE_IMAGES_DIR, f"{employee_id}_variation_{idx+1}.jpg")
                image.save(path, 'JPEG', quality=90)
            except:
                pass
        
        # Actualizar empleado
        face_data['registration_date'] = datetime.now().isoformat()
        face_data['system_version'] = 'BALANCED_v1.0'
        face_data['rut'] = employee.rut
        face_data['config_used'] = {
            'photos_required': ADVANCED_CONFIG['min_photos'],
            'tolerance': ADVANCED_CONFIG['base_tolerance'],
            'min_confidence': ADVANCED_CONFIG['min_confidence']
        }
        
        employee.face_encoding = json.dumps(face_data)
        employee.has_face_registered = True
        employee.face_registration_date = timezone.now()
        employee.face_quality_score = face_data.get('average_quality', 0.8)
        employee.face_variations_count = face_data['valid_photos']
        employee.save()
        
        return Response({
            'success': True,
            'message': f'Registro facial balanceado completado para {employee.name}',
            'details': {
                'photos_processed': face_data['valid_photos'],
                'quality_score': f"{face_data.get('average_quality', 0.8):.1%}",
                'variations_count': face_data['valid_photos'],
                'features_extracted': len(face_data.get('encodings', [])),
                'system_mode': 'BALANCED',
                'processing_time': 'Optimizado para velocidad',
                'tolerance_level': 'Balanceado para uso real'
            },
            'employee': {
                'id': str(employee.id),
                'name': employee.name,
                'rut': employee.rut,
                'ready': True,
                'face_registered': True
            }
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error: {str(e)}'
        }, status=500)

@api_view(['POST'])
def verify_attendance_face(request):
    """Verificación facial balanceada con timeout reducido"""
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
        
        print(f"\n🔍 Iniciando verificación balanceada con timeout de {ADVANCED_CONFIG['verification_timeout']}s...")
        start_time = time.time()
        
        verification_result, error = face_recognition_service.advanced_verify(
            photo_base64
        )
        
        elapsed_time = time.time() - start_time
        
        if error and ("Timeout" in error or "TIMEOUT" in error):
            return Response({
                'success': False,
                'message': '⏱️ VERIFICACIÓN CANCELADA - Tiempo límite excedido',
                'timeout': True,
                'timeout_seconds': ADVANCED_CONFIG['verification_timeout'],
                'elapsed_time': f'{elapsed_time:.1f}s',
                'error_type': 'TIMEOUT',
                'suggestions': [
                    "💡 Sistema balanceado - verifica condiciones:",
                    "📸 Asegúrate de estar registrado en el sistema",
                    "💡 Mejora la iluminación frontal",
                    "📱 Acércate más a la cámara",
                    "🎯 Centra tu rostro en la imagen",
                    "👓 Si usas lentes, verifica que estén limpios"
                ]
            }, status=408)
        
        if error:
            return Response({
                'success': False,
                'message': f'❌ VERIFICACIÓN FALLIDA: {error}',
                'elapsed_time': f'{elapsed_time:.1f}s',
                'error_type': 'VERIFICATION_FAILED',
                'system_mode': 'BALANCED'
            }, status=400)
        
        if not verification_result:
            return Response({
                'success': False,
                'message': 'Error interno procesando verificación',
                'elapsed_time': f'{elapsed_time:.1f}s',
                'system_mode': 'BALANCED'
            }, status=500)
        
        best_match = verification_result.get('best_match')
        best_confidence = verification_result.get('best_confidence', 0)
        all_results = verification_result.get('all_results', [])
        
        if not best_match:
            return Response({
                'success': False,
                'message': '🚫 ACCESO DENEGADO - Rostro no autorizado',
                'error_type': 'UNAUTHORIZED',
                'elapsed_time': f'{elapsed_time:.1f}s',
                'required_confidence': f"{ADVANCED_CONFIG['min_confidence']:.0%}",
                'system_mode': 'BALANCED',
                'security_tips': [
                    '⚠️ Sistema en modo balanceado - más tolerante pero seguro',
                    '📸 Asegúrate de estar registrado en el sistema',
                    '💡 Iluminación frontal uniforme requerida',
                    '🎯 Mirar directamente a la cámara',
                    f'📊 Confianza mínima requerida: {ADVANCED_CONFIG["min_confidence"]:.0%}'
                ]
            }, status=403)
        
        print(f"✅ VERIFICADO: {best_match['name']} ({best_confidence:.1%}) en {elapsed_time:.1f}s")
        
        # Buscar el objeto Employee por el best_match
        try:
            employee_obj = Employee.objects.get(id=best_match['id'], is_active=True)
        except Employee.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Error: Empleado verificado no encontrado en base de datos',
                'error_type': 'DATA_INCONSISTENCY'
            }, status=500)
        
        attendance_record = AttendanceRecord.objects.create(
            employee=employee_obj,
            attendance_type=attendance_type,
            timestamp=timezone.now(),
            location_lat=location_lat,
            location_lng=location_lng,
            address=address,
            verification_method='facial',
            face_confidence=best_confidence,
            notes=f'Verificación facial balanceada ({best_confidence:.1%}) - {elapsed_time:.1f}s'
        )
        
        serializer = AttendanceRecordSerializer(attendance_record)
        
        return Response({
            'success': True,
            'message': f'✅ {attendance_type.upper()} REGISTRADA',
            'employee': {
                'id': str(employee_obj.id),
                'name': employee_obj.name,
                'employee_id': employee_obj.employee_id,
                'rut': employee_obj.rut,
                'department': employee_obj.department
            },
            'verification': {
                'confidence': f'{best_confidence:.1%}',
                'method': 'FACIAL_RECOGNITION_BALANCED',
                'elapsed_time': f'{elapsed_time:.1f}s',
                'security_level': 'BALANCEADO',
                'system_version': 'BALANCED_v1.0'
            },
            'record': serializer.data,
            'timestamp': timezone.now().strftime('%d/%m/%Y %H:%M:%S')
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error crítico: {str(e)}',
            'error_type': 'SYSTEM_ERROR',
            'system_mode': 'BALANCED'
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
        
        # Extraer RUT del código QR con múltiples estrategias
        rut_from_qr = None
        
        # Estrategia 1: Buscar patrón de RUT en el texto
        import re
        rut_pattern = r'(\d{7,8}[-]?[0-9kK])'
        rut_matches = re.findall(rut_pattern, qr_data, re.IGNORECASE)
        
        if rut_matches:
            rut_from_qr = rut_matches[0]
            print(f"RUT encontrado por patrón: {rut_from_qr}")
        else:
            # Estrategia 2: Intentar como JSON
            try:
                qr_json = json.loads(qr_data)
                rut_from_qr = qr_json.get('rut') or qr_json.get('RUT') or qr_json.get('run') or qr_json.get('RUN')
            except:
                # Estrategia 3: Asumir que el QR contiene directamente el RUT
                clean_data = re.sub(r'[^0-9kK-]', '', qr_data).upper()
                if len(clean_data) >= 8:
                    rut_from_qr = clean_data
                else:
                    # Estrategia 4: Buscar cualquier secuencia de números seguida de dígito
                    number_pattern = r'(\d{7,8}[0-9kK])'
                    number_matches = re.findall(number_pattern, qr_data, re.IGNORECASE)
                    if number_matches:
                        rut_from_qr = number_matches[0]
        
        if not rut_from_qr:
            return Response({
                'success': False,
                'message': f'No se pudo extraer RUT del código QR. Contenido: {qr_data[:50]}...'
            }, status=400)
        
        # Formatear RUT para búsqueda
        formatted_rut = format_rut_for_storage(rut_from_qr)
        print(f"RUT formateado: {formatted_rut}")
        
        # Validar RUT
        if not validate_chilean_rut(formatted_rut):
            return Response({
                'success': False,
                'message': f'RUT extraído del QR no es válido: {formatted_rut}'
            }, status=400)
        
        # Buscar empleado por RUT
        employee = search_employee_by_rut(formatted_rut)
        if not employee:
            return Response({
                'success': False,
                'message': f'Empleado con RUT {formatted_rut} no encontrado en el sistema'
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
            notes=f'Verificación QR exitosa - RUT: {formatted_rut}'
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
                'rut_verified': formatted_rut,
                'qr_content': qr_data[:100],
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
        
        if data.get('photo'):
            return verify_attendance_face(request)
        
        if data.get('qr_data'):
            return verify_qr(request)
        
        # Lógica de búsqueda de empleado
        employee_name = data.get('employee_name', '').strip()
        employee_id = data.get('employee_id', '').strip()
        
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
                    'message': 'Múltiples empleados encontrados con ese nombre. Por favor, especifique el ID.'
                }, status=400)
        
        if not employee:
            return Response({
                'success': False,
                'message': 'Se requiere nombre o ID del empleado'
            }, status=400)
        
        # Llamada a la función auxiliar
        attendance_record = _create_manual_attendance_record(
            employee=employee,
            attendance_type=data.get('type', 'entrada').lower(),
            location_lat=data.get('latitude'),
            location_lng=data.get('longitude'),
            address=data.get('address', ''),
            notes=data.get('notes', ''),
            is_offline_sync=data.get('is_offline_sync', False),
            offline_timestamp=data.get('offline_timestamp')
        )
        
        serializer = AttendanceRecordSerializer(attendance_record)
        
        return Response({
            'success': True,
            'message': f'✅ {attendance_record.attendance_type.upper()} registrada manualmente',
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
        return Response({'success': False, 'message': f'Error: {str(e)}'}, status=500)

@api_view(['POST'])
def sync_offline_records(request):
    """Sincronizar registros offline"""
    try:
        offline_records = request.data.get('offline_records', [])
        synced_count = 0
        errors = []

        print(f"🔄 Iniciando sincronización de {len(offline_records)} registros offline...")
        
        for record_data in offline_records:
            try:
                response = None
                
                if record_data.get('photo'):
                    print(f"   Procesando registro facial...")
                    mock_request = HttpRequest()
                    mock_request.method = 'POST'
                    mock_request._body = json.dumps(record_data).encode('utf-8')
                    mock_request.content_type = 'application/json'
                    response = verify_attendance_face(mock_request)

                elif record_data.get('qr_data'):
                    print(f"   Procesando registro QR...")
                    mock_request = HttpRequest()
                    mock_request.method = 'POST'
                    mock_request._body = json.dumps(record_data).encode('utf-8')
                    mock_request.content_type = 'application/json'
                    response = verify_qr(mock_request)
                
                else:
                    employee_id = record_data.get('employee_id')
                    employee_name = record_data.get('employee_name')
                    
                    employee_obj = None
                    if employee_id:
                        try:
                            employee_obj = Employee.objects.get(employee_id=employee_id, is_active=True)
                        except Employee.DoesNotExist:
                            pass
                    
                    if not employee_obj and employee_name:
                        try:
                            employee_obj = Employee.objects.get(name__icontains=employee_name, is_active=True)
                        except (Employee.DoesNotExist, Employee.MultipleObjectsReturned):
                            pass
                            
                    if not employee_obj:
                        error_msg = 'Empleado no encontrado para la sincronización'
                        errors.append({'local_id': record_data.get('local_id'), 'error': error_msg, 'data': record_data})
                        print(f"   ❌ Fallo al sincronizar: {error_msg} para ID/nombre {employee_id}/{employee_name}")
                        continue
                    
                    print(f"   Procesando registro manual de {employee_obj.name}...")
                    
                    _create_manual_attendance_record(
                        employee=employee_obj,
                        attendance_type=record_data.get('type', 'entrada'),
                        location_lat=record_data.get('latitude'),
                        location_lng=record_data.get('longitude'),
                        address=record_data.get('address', ''),
                        notes='Sincronizado offline',
                        is_offline_sync=True,
                        offline_timestamp=record_data.get('timestamp')
                    )
                    synced_count += 1
                    print(f"   ✅ Sincronizado exitosamente.")

                # Procesar la respuesta para los métodos de foto y QR
                if response:
                    if response.status_code in [200, 201]:
                        synced_count += 1
                        print(f"   ✅ Sincronizado exitosamente.")
                    else:
                        error_msg = response.data.get('message', 'Error desconocido')
                        errors.append({'local_id': record_data.get('local_id'), 'error': error_msg})
                        print(f"   ❌ Fallo al sincronizar: {error_msg}")

            except Exception as e:
                errors.append({'local_id': record_data.get('local_id', 'unknown'), 'error': f'Excepción: {str(e)}'})
                print(f"   ❌ Error al procesar registro: {str(e)}")
        
        print(f"🏁 Sincronización finalizada. Total: {synced_count}/{len(offline_records)} exitosos.")
        
        return Response({
            'success': True,
            'synced_count': synced_count,
            'error_count': len(errors),
            'errors': errors[:10],
            'message': f'Sincronizados {synced_count} de {len(offline_records)} registros',
            'system_mode': 'BALANCED'
        })
        
    except Exception as e:
        return Response({'success': False, 'message': f'Error crítico en la sincronización: {str(e)}'}, status=500)

@api_view(['GET'])
def get_employees(request):
    """Obtener empleados"""
    try:
        employees = Employee.objects.filter(is_active=True).order_by('name')
        serializer = EmployeeSerializer(employees, many=True)
        
        total_employees = employees.count()
        employees_with_faces = employees.filter(has_face_registered=True).count()
        
        return Response({
            'success': True,
            'employees': serializer.data,
            'count': total_employees,
            'employees_with_faces': employees_with_faces,
            'face_registration_rate': f"{(employees_with_faces/total_employees*100):.1f}%" if total_employees > 0 else "0%",
            'system_mode': 'BALANCED_FACIAL_RECOGNITION',
            'features': {
                'basic_registration': True,
                'balanced_facial_recognition': True,
                'photos_required': ADVANCED_CONFIG['min_photos'],
                'qr_verification': True,
                'offline_sync': True,
                'optimized_processing': True
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
        
        # Estadísticas adicionales
        facial_records = records.filter(verification_method='facial').count()
        qr_records = records.filter(verification_method='qr').count()
        manual_records = records.filter(verification_method='manual').count()
        
        return Response({
            'success': True,
            'records': serializer.data,
            'count': len(serializer.data),
            'total': total_count,
            'statistics': {
                'facial_recognitions': facial_records,
                'qr_verifications': qr_records,
                'manual_entries': manual_records
            },
            'system_info': {
                'balanced_face_registration': True,
                'photos_required': ADVANCED_CONFIG['min_photos'],
                'qr_support': True,
                'timeout_seconds': ADVANCED_CONFIG['verification_timeout'],
                'system_mode': 'BALANCED'
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
        
        # Eliminar fotos guardadas si existen
        for i in range(1, ADVANCED_CONFIG['min_photos'] + 1):
            path = os.path.join(FACE_IMAGES_DIR, f"{employee_id}_variation_{i}.jpg")
            if os.path.exists(path):
                os.remove(path)
        
        AttendanceRecord.objects.filter(employee=employee).delete()
        employee.delete()
        
        return Response({
            'success': True,
            'message': f'{employee_name} eliminado completamente del sistema'
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