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
        'message': 'Sistema ultra rápido para cámaras malas funcionando',
        'timestamp': datetime.now().isoformat()
    })

@api_view(['POST'])
def ultra_fast_register(request):
    """
    ⚡ REGISTRO ULTRA RÁPIDO - Optimizado para cámaras MUY MALAS
    """
    print("⚡ REGISTRO ULTRA RÁPIDO PARA CÁMARAS MALAS")
    
    try:
        data = request.data
        name = data.get('name', '').strip()
        image_data = data.get('image')
        ultra_fast = data.get('ultra_fast', False)
        attempt = data.get('attempt', 0)
        
        if not name or not image_data or not ultra_fast:
            return Response({
                'processing': True,
                'message': 'Datos incompletos'
            })
        
        print(f"⚡ Intento {attempt} - Registrando: {name}")
        
        # Generar ID automático
        employee_id = f"EMP{str(uuid.uuid4())[:6].upper()}"
        while Employee.objects.filter(employee_id=employee_id).exists():
            employee_id = f"EMP{str(uuid.uuid4())[:6].upper()}"
        
        # Validación mínima para cámaras malas
        try:
            image_bytes = base64.b64decode(image_data.split(',')[1] if ',' in image_data else image_data)
            image = Image.open(io.BytesIO(image_bytes))
            
            if image.width < 20 or image.height < 20:
                return Response({
                    'processing': True,
                    'message': f'Intento {attempt}: Imagen muy pequeña'
                })
            
            print(f"⚡ Imagen válida: {image.width}x{image.height}")
            
        except Exception as e:
            return Response({
                'processing': True,
                'message': f'Intento {attempt}: Imagen corrupta'
            })
        
        # Procesamiento ultra rápido
        face_service = FaceRecognitionService()
        encoding, msg = face_service.ultra_fast_encoding(image_data)
        
        if not encoding:
            print(f"⚡ Sin rostro en intento {attempt}: {msg}")
            return Response({
                'processing': True,
                'message': f'Intento {attempt}: Buscando rostro...'
            })
        
        print(f"⚡ Encoding generado en intento {attempt}")
        
        # Guardar inmediatamente
        with transaction.atomic():
            user = User.objects.create_user(
                username=employee_id,
                email=f"{employee_id.lower()}@rapido.com",
                first_name=name.split()[0],
                last_name=' '.join(name.split()[1:]) if len(name.split()) > 1 else ''
            )
            
            employee = Employee.objects.create(
                user=user,
                employee_id=employee_id,
                name=name,
                email=f"{employee_id.lower()}@rapido.com",
                department='General',
                position='Empleado',
                is_active=True
            )
            
            FaceEncoding.objects.create(
                employee=employee,
                encoding_data=json.dumps(encoding),
                is_active=True
            )
        
        print(f"✅ REGISTRADO ULTRA RÁPIDO: {name} ({employee_id})")
        
        return Response({
            'success': True,
            'message': f'{name} registrado exitosamente',
            'employee': {
                'id': str(employee.id),
                'name': employee.name,
                'employee_id': employee.employee_id
            },
            'attempt': attempt
        })
        
    except Exception as e:
        print(f"❌ Error ultra rápido: {str(e)}")
        return Response({
            'processing': True,
            'message': f'Intento {attempt}: Error procesando'
        })

@api_view(['POST'])
def ultra_fast_verify(request):
    """
    ⚡ VERIFICACIÓN ULTRA RÁPIDA - Para cámaras MUY MALAS
    """
    print("⚡ VERIFICACIÓN ULTRA RÁPIDA PARA CÁMARAS MALAS")
    
    try:
        data = request.data
        image_data = data.get('image')
        attendance_type = data.get('type')
        ultra_fast = data.get('ultra_fast', False)
        attempt = data.get('attempt', 0)
        
        if not image_data or not attendance_type or not ultra_fast:
            return Response({
                'processing': True,
                'message': 'Datos incompletos'
            })
        
        print(f"⚡ Intento {attempt} - Verificando {attendance_type}")
        
        # Procesamiento ultra rápido
        face_service = FaceRecognitionService()
        unknown_encoding, msg = face_service.ultra_fast_encoding(image_data)
        
        if not unknown_encoding:
            print(f"⚡ Sin rostro en intento {attempt}: {msg}")
            return Response({
                'processing': True,
                'message': f'Intento {attempt}: Analizando...'
            })
        
        print(f"⚡ Rostro detectado en intento {attempt}")
        
        # Obtener empleados
        active_encodings = FaceEncoding.objects.filter(
            is_active=True,
            employee__is_active=True
        ).select_related('employee')
        
        if not active_encodings.exists():
            return Response({
                'success': False,
                'message': 'No hay empleados registrados'
            })
        
        # Comparación ultra rápida
        print(f"⚡ Comparando con {active_encodings.count()} empleados...")
        best_match = None
        best_confidence = 0.0
        
        for face_encoding in active_encodings:
            try:
                stored_encoding = json.loads(face_encoding.encoding_data)
                confidence = face_service.ultra_fast_compare(stored_encoding, unknown_encoding)
                
                print(f"   ⚡ {face_encoding.employee.name}: {confidence:.3f}")
                
                if confidence > best_confidence:
                    best_match = face_encoding.employee
                    best_confidence = confidence
                    
            except Exception:
                continue
        
        # Umbral ultra bajo para cámaras malas
        MIN_CONFIDENCE = 0.15
        
        if not best_match or best_confidence < MIN_CONFIDENCE:
            print(f"⚡ No reconocido en intento {attempt}: {best_confidence:.3f}")
            return Response({
                'processing': True,
                'message': f'Intento {attempt}: Buscando empleado...'
            })
        
        print(f"✅ RECONOCIDO ULTRA RÁPIDO: {best_match.name} ({best_confidence:.1%})")
        
        # Validación básica de reglas
        today = timezone.now().date()
        last_record = AttendanceRecord.objects.filter(
            employee=best_match,
            timestamp__date=today
        ).order_by('-timestamp').first()
        
        if attendance_type == 'entrada' and last_record and last_record.attendance_type == 'entrada':
            time_diff = (timezone.now() - last_record.timestamp).seconds
            if time_diff < 180:  # 3 minutos para ultra rápido
                return Response({
                    'success': False,
                    'message': f'Entrada ya registrada hace {time_diff//60} minutos'
                })
        
        elif attendance_type == 'salida' and (not last_record or last_record.attendance_type == 'salida'):
            return Response({
                'success': False,
                'message': 'Registra entrada primero'
            })
        
        # Registro ultra rápido
        attendance_record = AttendanceRecord.objects.create(
            employee=best_match,
            attendance_type=attendance_type,
            confidence=best_confidence,
            notes=f'Ultra rápido - Intento {attempt} - {best_confidence:.1%}'
        )
        
        print(f"✅ ASISTENCIA ULTRA RÁPIDA: {attendance_record.id}")
        
        return Response({
            'success': True,
            'message': f'{best_match.name} reconocido',
            'employee': {
                'id': str(best_match.id),
                'name': best_match.name,
                'employee_id': best_match.employee_id
            },
            'attendance': {
                'id': str(attendance_record.id),
                'type': attendance_type,
                'timestamp': attendance_record.timestamp.isoformat(),
                'confidence': f"{best_confidence:.1%}",
                'attempt': attempt
            }
        })
        
    except Exception as e:
        print(f"❌ Error verificación ultra rápida: {str(e)}")
        return Response({
            'processing': True,
            'message': f'Intento {attempt}: Error, reintentando'
        })

@api_view(['GET'])
def get_employees(request):
    """
    Lista de empleados registrados
    """
    try:
        employees = Employee.objects.filter(is_active=True).order_by('name')
        serializer = EmployeeSerializer(employees, many=True)
        
        return Response({
            'success': True,
            'employees': serializer.data
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error: {str(e)}'
        })

@api_view(['DELETE'])
def delete_employee(request, employee_id):
    """
    🗑️ ELIMINAR EMPLEADO COMPLETAMENTE
    """
    try:
        print(f"🗑️ Eliminando empleado: {employee_id}")
        
        employee = Employee.objects.get(id=employee_id)
        employee_name = employee.name
        
        # Eliminar completamente (no soft delete)
        FaceEncoding.objects.filter(employee=employee).delete()
        AttendanceRecord.objects.filter(employee=employee).delete()
        employee.user.delete()  # Esto también elimina el Employee por CASCADE
        
        print(f"✅ Empleado eliminado completamente: {employee_name}")
        
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
        attendance_record.delete()
        
        return Response({
            'success': True,
            'message': 'Registro eliminado'
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