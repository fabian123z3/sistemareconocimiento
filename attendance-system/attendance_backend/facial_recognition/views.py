# facial_recognition/views.py - VERSIÓN COMPLETA CON SINCRONIZACIÓN
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
def register_employee(request):
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
        encoding, encoding_msg = face_service.encode_face_from_base64(image_data)
        
        if not encoding:
            return Response({
                'success': False,
                'message': f'No se pudo detectar rostro: {encoding_msg}'
            })
        
        print(f"✅ Encoding facial generado: {len(encoding)} características")
        
        # Verificar si ya existe un empleado con rostro similar
        existing_encodings = FaceEncoding.objects.filter(
            is_active=True,
            employee__is_active=True
        ).select_related('employee')
        
        for existing_encoding in existing_encodings:
            try:
                stored_encoding = json.loads(existing_encoding.encoding_data)
                is_match, confidence = face_service.compare_faces(stored_encoding, encoding)
                
                if is_match and confidence > 0.3:  # Umbral para detectar duplicados
                    return Response({
                        'success': False,
                        'message': f'Esta persona ya está registrada como: {existing_encoding.employee.name}'
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
                encoding_data=json.dumps(encoding),
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
def verify_attendance(request):
    """
    🔍 VERIFICACIÓN DE ASISTENCIA CON RECONOCIMIENTO FACIAL
    """
    print("🔍 VERIFICANDO ASISTENCIA")
    
    try:
        data = request.data
        image_data = data.get('image')
        attendance_type = data.get('type', 'entrada').lower()
        location_lat = data.get('latitude')
        location_lng = data.get('longitude')
        notes = data.get('notes', '')
        
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
        unknown_encoding, encoding_msg = face_service.encode_face_from_base64(image_data)
        
        if not unknown_encoding:
            return Response({
                'success': False,
                'message': f'No se detectó rostro: {encoding_msg}'
            })
        
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
        
        # Buscar coincidencia
        print(f"🔍 Comparando con {active_encodings.count()} empleados...")
        best_match = None
        best_confidence = 0.0
        
        for face_encoding in active_encodings:
            try:
                stored_encoding = json.loads(face_encoding.encoding_data)
                is_match, confidence = face_service.compare_faces(
                    stored_encoding, 
                    unknown_encoding,
                    tolerance=0.6
                )
                
                print(f"   🔍 {face_encoding.employee.name}: {confidence:.3f}")
                
                if confidence > best_confidence:
                    best_match = face_encoding.employee
                    best_confidence = confidence
                    
            except Exception as e:
                print(f"   ❌ Error comparando con {face_encoding.employee.name}: {str(e)}")
                continue
        
        # Verificar umbral de confianza
        MIN_CONFIDENCE = 0.25  # Umbral permisivo pero seguro
        
        if not best_match or best_confidence < MIN_CONFIDENCE:
            print(f"❌ No reconocido. Mejor confianza: {best_confidence:.3f}")
            return Response({
                'success': False,
                'message': f'Persona no reconocida (confianza: {best_confidence:.1%})'
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
        
        # Crear registro de asistencia
        attendance_record = AttendanceRecord.objects.create(
            employee=best_match,
            attendance_type=attendance_type,
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
def sync_offline_data(request):
    """
    🔄 SINCRONIZACIÓN DE DATOS OFFLINE
    """
    print("🔄 INICIANDO SINCRONIZACIÓN OFFLINE")
    
    try:
        offline_records = request.data.get('offline_records', [])
        synced_count = 0
        errors = []
        
        for record_data in offline_records:
            try:
                # Validar datos requeridos
                if not all(k in record_data for k in ['employee_id', 'attendance_type', 'timestamp', 'image']):
                    errors.append(f"Registro incompleto: {record_data.get('employee_id', 'unknown')}")
                    continue
                
                employee_id = record_data['employee_id']
                attendance_type = record_data['attendance_type']
                timestamp_str = record_data['timestamp']
                image_data = record_data['image']
                confidence = record_data.get('confidence', 0.5)
                
                # Buscar empleado
                try:
                    employee = Employee.objects.get(employee_id=employee_id, is_active=True)
                except Employee.DoesNotExist:
                    errors.append(f"Empleado no encontrado: {employee_id}")
                    continue
                
                # Convertir timestamp
                try:
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                except ValueError:
                    timestamp = timezone.now()
                
                # Verificar si ya existe este registro
                existing = AttendanceRecord.objects.filter(
                    employee=employee,
                    attendance_type=attendance_type,
                    timestamp__date=timestamp.date(),
                    timestamp__hour=timestamp.hour,
                    timestamp__minute=timestamp.minute
                ).exists()
                
                if existing:
                    print(f"⚠️ Registro duplicado omitido: {employee.name} - {timestamp}")
                    continue
                
                # Crear registro
                AttendanceRecord.objects.create(
                    employee=employee,
                    attendance_type=attendance_type,
                    timestamp=timestamp,
                    confidence=confidence,
                    location_lat=record_data.get('latitude'),
                    location_lng=record_data.get('longitude'),
                    notes=f"Sincronizado offline - {record_data.get('notes', '')}"
                )
                
                synced_count += 1
                print(f"✅ Sincronizado: {employee.name} - {attendance_type}")
                
            except Exception as e:
                errors.append(f"Error procesando registro: {str(e)}")
                print(f"❌ Error sincronizando registro: {str(e)}")
        
        print(f"🔄 SINCRONIZACIÓN COMPLETADA: {synced_count} registros, {len(errors)} errores")
        
        return Response({
            'success': True,
            'synced_count': synced_count,
            'error_count': len(errors),
            'errors': errors[:5],  # Solo primeros 5 errores
            'message': f'Sincronizados {synced_count} registros'
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
        date_from = request.GET.get('date_from')
        date_to = request.GET.get('date_to')
        employee_id = request.GET.get('employee_id')
        limit = int(request.GET.get('limit', 50))
        
        # Query base
        queryset = AttendanceRecord.objects.select_related('employee').order_by('-timestamp')
        
        # Aplicar filtros
        if date_from:
            try:
                date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
                queryset = queryset.filter(timestamp__date__gte=date_from_obj)
            except ValueError:
                pass
        
        if date_to:
            try:
                date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
                queryset = queryset.filter(timestamp__date__lte=date_to_obj)
            except ValueError:
                pass
        
        if employee_id:
            queryset = queryset.filter(employee__employee_id=employee_id)
        
        # Limitar resultados
        records = queryset[:limit]
        serializer = AttendanceRecordSerializer(records, many=True)
        
        return Response({
            'success': True,
            'records': serializer.data,
            'count': records.count(),
            'total_count': queryset.count()
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

# ===============================
# VISTAS PARA LA PÁGINA WEB
# ===============================

def attendance_dashboard(request):
    """
    📊 PÁGINA WEB DEL DASHBOARD DE ASISTENCIAS
    """
    return render(request, 'attendance_dashboard.html')

@api_view(['GET'])
def dashboard_data(request):
    """
    📊 DATOS PARA EL DASHBOARD WEB
    """
    try:
        today = timezone.now().date()
        
        # Empleados activos
        total_employees = Employee.objects.filter(is_active=True).count()
        
        # Asistencias de hoy
        today_records = AttendanceRecord.objects.filter(timestamp__date=today)
        present_today = today_records.filter(attendance_type='entrada').values('employee').distinct().count()
        
        # Últimos registros
        recent_records = AttendanceRecord.objects.select_related('employee').order_by('-timestamp')[:20]
        recent_serializer = AttendanceRecordSerializer(recent_records, many=True)
        
        # Estadísticas por departamento
        dept_stats = {}
        employees_by_dept = Employee.objects.filter(is_active=True).values('department').distinct()
        
        for dept in employees_by_dept:
            dept_name = dept['department']
            dept_employees = Employee.objects.filter(department=dept_name, is_active=True)
            dept_present = today_records.filter(
                employee__department=dept_name,
                attendance_type='entrada'
            ).values('employee').distinct().count()
            
            dept_stats[dept_name] = {
                'total': dept_employees.count(),
                'present': dept_present,
                'absent': dept_employees.count() - dept_present
            }
        
        # Empleados presentes actualmente
        present_employees = []
        for employee in Employee.objects.filter(is_active=True):
            last_record = today_records.filter(employee=employee).order_by('-timestamp').first()
            if last_record and last_record.attendance_type == 'entrada':
                # Verificar si no ha marcado salida
                salida_after = today_records.filter(
                    employee=employee,
                    attendance_type='salida',
                    timestamp__gt=last_record.timestamp
                ).exists()
                
                if not salida_after:
                    present_employees.append({
                        'name': employee.name,
                        'employee_id': employee.employee_id,
                        'department': employee.department,
                        'entry_time': last_record.timestamp.strftime('%H:%M'),
                        'confidence': f"{last_record.confidence:.1%}"
                    })
        
        return Response({
            'success': True,
            'stats': {
                'total_employees': total_employees,
                'present_today': present_today,
                'absent_today': total_employees - present_today,
                'attendance_rate': f"{(present_today/total_employees*100):.1f}%" if total_employees > 0 else "0%"
            },
            'department_stats': dept_stats,
            'recent_records': recent_serializer.data,
            'present_employees': present_employees,
            'last_updated': timezone.now().isoformat()
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error: {str(e)}'
        })

# Mantener compatibilidad con endpoints ultra rápidos existentes
@api_view(['POST'])
def ultra_fast_register(request):
    """Redirige al nuevo endpoint de registro"""
    return register_employee(request)

@api_view(['POST'])
def ultra_fast_verify(request):
    """Redirige al nuevo endpoint de verificación"""
    return verify_attendance(request)