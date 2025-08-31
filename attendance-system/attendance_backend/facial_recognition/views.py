# facial_recognition/views.py - VERSIÓN COMPLETA CON SINCRONIZACIÓN Y 85% CONFIANZA
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from datetime import datetime, timedelta
import json
import base64
import io
import uuid
from PIL import Image
import numpy as np

from .models import Employee, FaceEncoding, AttendanceRecord
from .serializers import EmployeeSerializer, AttendanceRecordSerializer
from .face_recognition_utils import FaceRecognitionService

@api_view(['GET'])
def health_check(request):
    return Response({
        'status': 'OK',
        'message': 'Sistema de asistencia funcionando',
        'timestamp': datetime.now().isoformat(),
        'employees_count': Employee.objects.filter(is_active=True).count(),
        'attendance_today': AttendanceRecord.objects.filter(
            timestamp__date=timezone.now().date()
        ).count()
    })

@api_view(['POST'])
def register_employee_photo(request):
    """
    📸 REGISTRO DE EMPLEADO CON RECONOCIMIENTO FACIAL
    """
    print("📸 INICIANDO REGISTRO DE EMPLEADO")
    
    try:
        data = request.data
        name = data.get('name', '').strip()
        employee_id = data.get('employee_id', '').strip()
        email = data.get('email', '').strip()
        department = data.get('department', 'General').strip()
        position = data.get('position', 'Empleado').strip()
        image_data = data.get('image')
        
        # Validaciones básicas
        if not name or len(name) < 2:
            return Response({
                'success': False,
                'message': 'Nombre debe tener al menos 2 caracteres'
            })
        
        if not image_data:
            return Response({
                'success': False,
                'message': 'Se requiere una imagen para el registro'
            })
        
        # Generar employee_id si no se proporciona
        if not employee_id:
            employee_id = f"EMP{str(uuid.uuid4())[:6].upper()}"
            while Employee.objects.filter(employee_id=employee_id).exists():
                employee_id = f"EMP{str(uuid.uuid4())[:6].upper()}"
        
        # Verificar si ya existe
        if Employee.objects.filter(employee_id=employee_id).exists():
            return Response({
                'success': False,
                'message': f'Ya existe un empleado con ID: {employee_id}'
            })
        
        # Generar email si no se proporciona
        if not email:
            email = f"{employee_id.lower()}@empresa.com"
        
        print(f"📸 Procesando imagen para: {name} ({employee_id})")
        
        # Procesar imagen
        face_service = FaceRecognitionService()
        
        # Validar calidad de imagen
        is_valid, validation_msg = face_service.validate_image_quality(image_data)
        if not is_valid:
            return Response({
                'success': False,
                'message': f'Imagen no válida: {validation_msg}'
            })
        
        # Generar encoding facial
        encoding_result, encoding_msg = face_service.tolerant_photo_encoding(image_data)
        
        if not encoding_result:
            return Response({
                'success': False,
                'message': f'No se pudo detectar rostro: {encoding_msg}'
            })
        
        print(f"✅ Encoding facial generado exitosamente")
        
        # Verificar si ya existe un empleado con rostro similar
        existing_encodings = FaceEncoding.objects.filter(
            is_active=True,
            employee__is_active=True
        ).select_related('employee')
        
        for existing_encoding in existing_encodings:
            try:
                stored_encoding_data = json.loads(existing_encoding.encoding_data)
                stored_main = stored_encoding_data.get('main', stored_encoding_data)
                
                confidence = face_service.ultra_tolerant_compare(stored_main, encoding_result['main'])
                
                if confidence >= 0.85:  # 85% de similitud
                    return Response({
                        'success': False,
                        'message': f'Esta persona ya está registrada como: {existing_encoding.employee.name} (similitud: {confidence:.1%})'
                    })
            except Exception:
                continue
        
        # Crear empleado
        with transaction.atomic():
            # Crear usuario de Django
            user = User.objects.create_user(
                username=employee_id,
                email=email,
                first_name=name.split()[0],
                last_name=' '.join(name.split()[1:]) if len(name.split()) > 1 else ''
            )
            
            # Crear empleado
            employee = Employee.objects.create(
                user=user,
                employee_id=employee_id,
                name=name,
                email=email,
                department=department,
                position=position,
                is_active=True
            )
            
            # Crear encoding facial
            FaceEncoding.objects.create(
                employee=employee,
                encoding_data=json.dumps(encoding_result),
                is_active=True
            )
        
        print(f"✅ EMPLEADO REGISTRADO: {name} ({employee_id})")
        
        return Response({
            'success': True,
            'message': f'{name} registrado exitosamente',
            'employee': {
                'id': str(employee.id),
                'name': employee.name,
                'employee_id': employee.employee_id,
                'email': employee.email,
                'department': employee.department,
                'position': employee.position
            }
        })
        
    except Exception as e:
        print(f"❌ Error en registro: {str(e)}")
        return Response({
            'success': False,
            'message': f'Error interno del servidor: {str(e)}'
        })

@api_view(['POST'])
def verify_attendance_photo(request):
    """
    🔍 VERIFICACIÓN DE ASISTENCIA CON RECONOCIMIENTO FACIAL - 85% CONFIANZA
    """
    print("🔍 VERIFICANDO ASISTENCIA")
    
    try:
        data = request.data
        image_data = data.get('image')
        attendance_type = data.get('type', 'entrada').lower()
        location_lat = data.get('latitude')
        location_lng = data.get('longitude')
        notes = data.get('notes', '')
        is_offline_sync = data.get('is_offline_sync', False)
        offline_timestamp = data.get('offline_timestamp')
        
        if not image_data:
            return Response({
                'success': False,
                'message': 'Se requiere una imagen'
            })
        
        if attendance_type not in ['entrada', 'salida']:
            return Response({
                'success': False,
                'message': 'Tipo de asistencia inválido'
            })
        
        print(f"🔍 Verificando para: {attendance_type}")
        
        # Procesar imagen
        face_service = FaceRecognitionService()
        
        # Validar imagen
        is_valid, validation_msg = face_service.validate_image_quality(image_data)
        if not is_valid:
            return Response({
                'success': False,
                'message': f'Imagen no válida: {validation_msg}'
            })
        
        # Generar encoding
        unknown_encoding_result, encoding_msg = face_service.tolerant_photo_encoding(image_data)
        
        if not unknown_encoding_result:
            return Response({
                'success': False,
                'message': f'No se detectó rostro: {encoding_msg}'
            })
        
        unknown_encoding = unknown_encoding_result['main']
        print("✅ Rostro detectado y procesado")
        
        # Obtener empleados activos
        active_encodings = FaceEncoding.objects.filter(
            is_active=True,
            employee__is_active=True
        ).select_related('employee')
        
        if not active_encodings.exists():
            return Response({
                'success': False,
                'message': 'No hay empleados registrados'
            })
        
        # Buscar coincidencia con 85% de confianza
        print(f"🔍 Comparando con {active_encodings.count()} empleados...")
        best_match = None
        best_confidence = 0.0
        
        for face_encoding in active_encodings:
            try:
                stored_encoding_data = json.loads(face_encoding.encoding_data)
                stored_main = stored_encoding_data.get('main', stored_encoding_data)
                
                confidence = face_service.ultra_tolerant_compare(stored_main, unknown_encoding)
                
                print(f"   🔍 {face_encoding.employee.name}: {confidence:.3f} ({confidence:.1%})")
                
                if confidence > best_confidence:
                    best_match = face_encoding.employee
                    best_confidence = confidence
                    
            except Exception as e:
                print(f"   ❌ Error comparando con {face_encoding.employee.name}: {str(e)}")
                continue
        
        # Verificar umbral de 85% de confianza
        MIN_CONFIDENCE = 0.85  # 85% de similitud requerida
        
        if not best_match or best_confidence < MIN_CONFIDENCE:
            print(f"❌ No reconocido. Mejor confianza: {best_confidence:.3f} ({best_confidence:.1%})")
            return Response({
                'success': False,
                'message': f'Persona no reconocida. Se requiere al menos 85% de similitud. (Confianza actual: {best_confidence:.1%})'
            })
        
        print(f"✅ EMPLEADO RECONOCIDO: {best_match.name} ({best_confidence:.1%})")
        
        # Validar reglas de negocio
        today = timezone.now().date()
        last_record = AttendanceRecord.objects.filter(
            employee=best_match,
            timestamp__date=today
        ).order_by('-timestamp').first()
        
        # Validación para entrada
        if attendance_type == 'entrada':
            if last_record and last_record.attendance_type == 'entrada':
                time_diff = (timezone.now() - last_record.timestamp).seconds
                if time_diff < 300:  # 5 minutos
                    return Response({
                        'success': False,
                        'message': f'Entrada ya registrada hace {time_diff//60} minutos'
                    })
        
        # Validación para salida
        elif attendance_type == 'salida':
            if not last_record or last_record.attendance_type == 'salida':
                return Response({
                    'success': False,
                    'message': 'Debe registrar entrada primero'
                })
        
        # Determinar timestamp
        if is_offline_sync and offline_timestamp:
            try:
                record_timestamp = datetime.fromisoformat(offline_timestamp.replace('Z', '+00:00'))
                if record_timestamp.tzinfo is None:
                    record_timestamp = timezone.make_aware(record_timestamp)
                notes = f"Sync offline - {notes}" if notes else "Sync offline"
            except:
                record_timestamp = timezone.now()
                notes = f"Sync offline (timestamp error) - {notes}"
        else:
            record_timestamp = timezone.now()
        
        # Crear registro de asistencia
        attendance_record = AttendanceRecord.objects.create(
            employee=best_match,
            attendance_type=attendance_type,
            timestamp=record_timestamp,
            confidence=best_confidence,
            location_lat=location_lat,
            location_lng=location_lng,
            notes=notes
        )
        
        print(f"✅ ASISTENCIA REGISTRADA: {attendance_record.id}")
        
        return Response({
            'success': True,
            'message': f'{best_match.name} - {attendance_type} registrada',
            'employee': {
                'id': str(best_match.id),
                'name': best_match.name,
                'employee_id': best_match.employee_id,
                'department': best_match.department,
                'position': best_match.position
            },
            'attendance': {
                'id': str(attendance_record.id),
                'type': attendance_type,
                'timestamp': attendance_record.timestamp.isoformat(),
                'confidence': f"{best_confidence:.1%}",
                'location_lat': location_lat,
                'location_lng': location_lng
            }
        })
        
    except Exception as e:
        print(f"❌ Error en verificación: {str(e)}")
        return Response({
            'success': False,
            'message': f'Error interno: {str(e)}'
        })

@api_view(['POST'])
def sync_offline_records(request):
    """
    🔄 SINCRONIZACIÓN DE REGISTROS OFFLINE
    """
    print("🔄 INICIANDO SINCRONIZACIÓN OFFLINE")
    
    try:
        offline_records = request.data.get('offline_records', [])
        synced_count = 0
        errors = []
        synced_records = []
        
        for record_data in offline_records:
            try:
                # Verificar asistencia offline como una verificación normal
                verify_data = {
                    'image': record_data.get('image'),
                    'type': record_data.get('type'),
                    'latitude': record_data.get('latitude'),
                    'longitude': record_data.get('longitude'),
                    'notes': record_data.get('notes', ''),
                    'is_offline_sync': True,
                    'offline_timestamp': record_data.get('timestamp')
                }
                
                # Usar el endpoint de verificación
                from django.test import RequestFactory
                factory = RequestFactory()
                sync_request = factory.post('/api/verify-photo/', verify_data, format='json')
                sync_request.data = verify_data
                
                sync_response = verify_attendance_photo(sync_request)
                
                if sync_response.data.get('success'):
                    synced_count += 1
                    synced_records.append({
                        'local_id': record_data.get('local_id'),
                        'employee_name': sync_response.data['employee']['name'],
                        'type': sync_response.data['attendance']['type'],
                        'confidence': sync_response.data['attendance']['confidence']
                    })
                    print(f"✅ Sincronizado: {sync_response.data['employee']['name']}")
                else:
                    errors.append({
                        'local_id': record_data.get('local_id'),
                        'error': sync_response.data.get('message', 'Error desconocido')
                    })
                    print(f"❌ Error sincronizando: {sync_response.data.get('message')}")
                
            except Exception as e:
                errors.append({
                    'local_id': record_data.get('local_id', 'unknown'),
                    'error': str(e)
                })
                print(f"❌ Error procesando registro offline: {str(e)}")
        
        print(f"🔄 SINCRONIZACIÓN COMPLETADA: {synced_count} registros, {len(errors)} errores")
        
        return Response({
            'success': True,
            'synced_count': synced_count,
            'error_count': len(errors),
            'errors': errors[:5],  # Solo primeros 5 errores
            'synced_records': synced_records,
            'message': f'Sincronizados {synced_count} de {len(offline_records)} registros'
        })
        
    except Exception as e:
        print(f"❌ Error en sincronización: {str(e)}")
        return Response({
            'success': False,
            'message': f'Error en sincronización: {str(e)}'
        })

@api_view(['GET'])
def get_employees(request):
    """
    👥 OBTENER LISTA DE EMPLEADOS
    """
    try:
        employees = Employee.objects.filter(is_active=True).order_by('name')
        serializer = EmployeeSerializer(employees, many=True)
        
        return Response({
            'success': True,
            'employees': serializer.data,
            'count': employees.count()
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error: {str(e)}'
        })

@api_view(['GET'])
def get_attendance_records(request):
    """
    📋 OBTENER REGISTROS DE ASISTENCIA
    """
    try:
        # Parámetros de filtro
        days = int(request.GET.get('days', 7))
        employee_id = request.GET.get('employee_id')
        limit = int(request.GET.get('limit', 100))
        
        # Query base - últimos N días
        date_from = timezone.now().date() - timedelta(days=days)
        queryset = AttendanceRecord.objects.select_related('employee').filter(
            timestamp__date__gte=date_from
        ).order_by('-timestamp')
        
        # Filtro por empleado específico
        if employee_id:
            try:
                employee = Employee.objects.get(id=employee_id)
                queryset = queryset.filter(employee=employee)
            except Employee.DoesNotExist:
                pass
        
        # Contar total antes de limitar
        total_count = queryset.count()
        
        # Limitar resultados
        records = queryset[:limit]
        serializer = AttendanceRecordSerializer(records, many=True)
        
        return Response({
            'success': True,
            'records': serializer.data,
            'count': len(serializer.data),
            'total': total_count,
            'days_filter': days
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error: {str(e)}'
        })

@api_view(['DELETE'])
def delete_employee(request, employee_id):
    """
    🗑️ ELIMINAR EMPLEADO
    """
    try:
        employee = Employee.objects.get(id=employee_id)
        employee_name = employee.name
        
        # Soft delete
        employee.is_active = False
        employee.save()
        
        # Desactivar encodings
        FaceEncoding.objects.filter(employee=employee).update(is_active=False)
        
        print(f"🗑️ Empleado desactivado: {employee_name}")
        
        return Response({
            'success': True,
            'message': f'{employee_name} eliminado del sistema'
        })
        
    except Employee.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Empleado no encontrado'
        }, status=404)
    except Exception as e:
        print(f"❌ Error eliminando empleado: {str(e)}")
        return Response({
            'success': False,
            'message': 'Error eliminando empleado'
        })

@api_view(['DELETE'])
def delete_attendance(request, attendance_id):
    """
    🗑️ ELIMINAR REGISTRO DE ASISTENCIA
    """
    try:
        attendance_record = AttendanceRecord.objects.get(id=attendance_id)
        employee_name = attendance_record.employee.name
        attendance_record.delete()
        
        return Response({
            'success': True,
            'message': f'Registro de {employee_name} eliminado'
        })
        
    except AttendanceRecord.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Registro no encontrado'
        }, status=404)
    except Exception as e:
        return Response({
            'success': False,
            'message': 'Error eliminando registro'
        })

@csrf_exempt
def attendance_panel(request):
    """
    📊 PANEL WEB DE ASISTENCIAS
    """
    return render(request, 'attendance_panel.html')

# Mantener compatibilidad con endpoints existentes
@api_view(['POST'])
def register_employee(request):
    """Compatibilidad - redirige al nuevo endpoint"""
    return register_employee_photo(request)

@api_view(['POST'])
def verify_attendance(request):
    """Compatibilidad - redirige al nuevo endpoint"""
    return verify_attendance_photo(request)