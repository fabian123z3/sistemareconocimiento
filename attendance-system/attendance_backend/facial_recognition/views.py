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
from PIL import Image
import io
import face_recognition
import numpy as np

from .models import Employee, AttendanceRecord
from .serializers import EmployeeSerializer, AttendanceRecordSerializer

# Carpeta para guardar las fotos de empleados
FACE_IMAGES_DIR = 'media/employee_faces/'
os.makedirs(FACE_IMAGES_DIR, exist_ok=True)

@api_view(['GET'])
def health_check(request):
    """Estado de salud del sistema"""
    return Response({
        'status': 'OK',
        'message': 'Sistema de asistencia con reconocimiento facial funcionando',
        'timestamp': datetime.now().isoformat(),
        'employees_count': Employee.objects.filter(is_active=True).count(),
        'attendance_today': AttendanceRecord.objects.filter(
            timestamp__date=timezone.now().date()
        ).count(),
        'mode': 'Reconocimiento Facial + GPS',
        'face_recognition': {
            'enabled': True,
            'tolerance': 0.6,  # Tolerancia para caras (más alto = más tolerante)
            'model': 'face_recognition en servidor'
        }
    })

def process_and_save_face_image(photo_base64, employee_id):
    """
    Procesa y guarda la imagen del empleado
    Retorna: (success, message, encoding)
    """
    try:
        # Decodificar base64
        if ',' in photo_base64:
            photo_base64 = photo_base64.split(',')[1]
        
        image_data = base64.b64decode(photo_base64)
        image = Image.open(io.BytesIO(image_data))
        
        # Convertir a RGB si es necesario
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Guardar imagen original
        image_path = os.path.join(FACE_IMAGES_DIR, f"{employee_id}_original.jpg")
        image.save(image_path, 'JPEG', quality=95)
        
        # Convertir a numpy array para face_recognition
        image_array = np.array(image)
        
        # Detectar caras con múltiples métodos para mayor tolerancia
        face_locations = face_recognition.face_locations(image_array, model="hog")
        
        if not face_locations:
            # Intentar con CNN si HOG no funciona
            face_locations = face_recognition.face_locations(image_array, model="cnn")
        
        if not face_locations:
            # Último intento con diferentes parámetros
            face_locations = face_recognition.face_locations(
                image_array, 
                number_of_times_to_upsample=2
            )
        
        if not face_locations:
            return False, "No se detectó ningún rostro en la imagen", None
        
        if len(face_locations) > 1:
            # Si hay múltiples caras, usar la más grande
            face_sizes = [(bottom-top)*(right-left) for top, right, bottom, left in face_locations]
            biggest_face_index = face_sizes.index(max(face_sizes))
            face_locations = [face_locations[biggest_face_index]]
        
        # Generar encoding con múltiples jitters para mejor precisión
        face_encodings = face_recognition.face_encodings(
            image_array, 
            face_locations, 
            num_jitters=10  # Más jitters = más precisión pero más lento
        )
        
        if not face_encodings:
            return False, "No se pudo procesar el rostro", None
        
        # Guardar también versiones procesadas para mejorar reconocimiento
        # Versión con brillo ajustado
        from PIL import ImageEnhance
        
        # Versión más brillante
        enhancer = ImageEnhance.Brightness(image)
        bright_image = enhancer.enhance(1.3)
        bright_path = os.path.join(FACE_IMAGES_DIR, f"{employee_id}_bright.jpg")
        bright_image.save(bright_path, 'JPEG', quality=95)
        
        # Versión con más contraste
        enhancer = ImageEnhance.Contrast(image)
        contrast_image = enhancer.enhance(1.5)
        contrast_path = os.path.join(FACE_IMAGES_DIR, f"{employee_id}_contrast.jpg")
        contrast_image.save(contrast_path, 'JPEG', quality=95)
        
        # Generar encodings de las versiones procesadas también
        bright_array = np.array(bright_image)
        contrast_array = np.array(contrast_image)
        
        bright_encoding = face_recognition.face_encodings(bright_array, face_locations)
        contrast_encoding = face_recognition.face_encodings(contrast_array, face_locations)
        
        # Combinar todos los encodings
        all_encodings = {
            'main': face_encodings[0].tolist(),
            'bright': bright_encoding[0].tolist() if bright_encoding else None,
            'contrast': contrast_encoding[0].tolist() if contrast_encoding else None
        }
        
        return True, "Rostro procesado exitosamente", all_encodings
        
    except Exception as e:
        print(f"Error procesando imagen: {str(e)}")
        return False, f"Error procesando imagen: {str(e)}", None

def verify_face_from_photo(photo_base64, employee):
    """
    Verifica si la foto corresponde al empleado
    Retorna: (is_match, confidence, message)
    """
    try:
        # Decodificar foto actual
        if ',' in photo_base64:
            photo_base64 = photo_base64.split(',')[1]
        
        image_data = base64.b64decode(photo_base64)
        image = Image.open(io.BytesIO(image_data))
        
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        current_image_array = np.array(image)
        
        # Detectar cara en imagen actual con tolerancia
        current_face_locations = face_recognition.face_locations(current_image_array, model="hog")
        
        if not current_face_locations:
            current_face_locations = face_recognition.face_locations(current_image_array, model="cnn")
        
        if not current_face_locations:
            return False, 0, "No se detectó rostro en la imagen"
        
        # Generar encoding de la imagen actual
        current_face_encodings = face_recognition.face_encodings(
            current_image_array, 
            current_face_locations,
            num_jitters=2  # Menos jitters para velocidad
        )
        
        if not current_face_encodings:
            return False, 0, "No se pudo procesar el rostro"
        
        current_encoding = current_face_encodings[0]
        
        # Cargar encodings guardados del empleado
        if not employee.face_encoding:
            return False, 0, "Empleado sin registro facial"
        
        stored_encodings = json.loads(employee.face_encoding)
        
        # Comparar con todos los encodings guardados
        best_match = False
        best_distance = 1.0
        
        # Tolerancia ajustable según calidad de cámara
        TOLERANCE = 0.65  # Más alto = más tolerante (default es 0.6)
        
        # Comparar con encoding principal
        if stored_encodings.get('main'):
            known_encoding = np.array(stored_encodings['main'])
            face_distance = face_recognition.face_distance([known_encoding], current_encoding)[0]
            
            if face_distance < best_distance:
                best_distance = face_distance
                best_match = face_distance <= TOLERANCE
        
        # Comparar con encodings alternativos si no hay match fuerte
        if best_distance > 0.5:  # Si no es muy buena coincidencia
            for key in ['bright', 'contrast']:
                if stored_encodings.get(key):
                    alt_encoding = np.array(stored_encodings[key])
                    alt_distance = face_recognition.face_distance([alt_encoding], current_encoding)[0]
                    
                    if alt_distance < best_distance:
                        best_distance = alt_distance
                        best_match = alt_distance <= TOLERANCE
        
        # Calcular confianza (inverso de la distancia)
        confidence = max(0, min(1, 1 - best_distance))
        
        # Para cámaras de baja calidad, ser más permisivo
        if confidence > 0.35:  # 35% de confianza mínima
            return True, confidence, f"Verificación exitosa ({confidence:.1%})"
        else:
            return False, confidence, f"No coincide (confianza: {confidence:.1%})"
            
    except Exception as e:
        print(f"Error verificando rostro: {str(e)}")
        return False, 0, f"Error: {str(e)}"

@api_view(['POST'])
def register_employee_face(request):
    """Registrar rostro de empleado con foto"""
    try:
        data = request.data
        employee_id = data.get('employee_id')
        photo_base64 = data.get('photo')
        
        if not employee_id or not photo_base64:
            return Response({
                'success': False,
                'message': 'Se requiere ID de empleado y foto'
            }, status=400)
        
        # Buscar empleado
        try:
            employee = Employee.objects.get(id=employee_id, is_active=True)
        except Employee.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Empleado no encontrado'
            }, status=404)
        
        # Procesar y guardar imagen
        success, message, encodings = process_and_save_face_image(photo_base64, str(employee.id))
        
        if not success:
            return Response({
                'success': False,
                'message': message,
                'tips': [
                    'Asegúrate de que haya buena iluminación',
                    'Mira directamente a la cámara',
                    'Evita sombras en el rostro',
                    'Quítate gafas oscuras si las tienes',
                    'Asegúrate de que tu rostro esté completo en la foto'
                ]
            }, status=400)
        
        # Guardar encodings en el empleado
        employee.face_encoding = json.dumps(encodings)
        employee.has_face_registered = True
        employee.face_registration_date = timezone.now()
        employee.save()
        
        return Response({
            'success': True,
            'message': f'Rostro registrado exitosamente para {employee.name}',
            'employee': {
                'id': str(employee.id),
                'name': employee.name,
                'has_face': True
            }
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error registrando rostro: {str(e)}'
        }, status=500)

@api_view(['POST'])
def verify_attendance_face(request):
    """Verificar rostro y marcar asistencia"""
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
                'message': 'Se requiere foto para verificación'
            }, status=400)
        
        # Buscar coincidencia con todos los empleados
        best_match = None
        best_confidence = 0
        
        employees_with_faces = Employee.objects.filter(
            is_active=True,
            has_face_registered=True
        )
        
        if not employees_with_faces.exists():
            return Response({
                'success': False,
                'message': 'No hay empleados con registro facial'
            }, status=404)
        
        for employee in employees_with_faces:
            is_match, confidence, message = verify_face_from_photo(photo_base64, employee)
            
            if confidence > best_confidence:
                best_confidence = confidence
                if is_match:
                    best_match = employee
        
        if not best_match:
            return Response({
                'success': False,
                'message': 'No se encontró coincidencia facial',
                'best_confidence': f'{best_confidence:.1%}',
                'required_confidence': '35%',
                'suggestions': [
                    'Mejora la iluminación',
                    'Acércate más a la cámara',
                    'Mira directamente a la cámara',
                    'Evita movimientos durante la captura'
                ]
            }, status=404)
        
        # Verificar registro reciente
        today = timezone.now().date()
        recent_record = AttendanceRecord.objects.filter(
            employee=best_match,
            attendance_type=attendance_type,
            timestamp__date=today
        ).order_by('-timestamp').first()
        
        if recent_record:
            time_diff = (timezone.now() - recent_record.timestamp).total_seconds()
            if time_diff < 300:  # 5 minutos
                return Response({
                    'success': False,
                    'message': f'{attendance_type.capitalize()} ya registrada hace {int(time_diff/60)} minutos',
                    'employee': best_match.name
                }, status=400)
        
        # Crear registro de asistencia
        attendance_record = AttendanceRecord.objects.create(
            employee=best_match,
            attendance_type=attendance_type,
            timestamp=timezone.now(),
            location_lat=location_lat,
            location_lng=location_lng,
            address=address,
            face_confidence=best_confidence,
            notes=f'Verificación facial ({best_confidence:.1%})'
        )
        
        serializer = AttendanceRecordSerializer(attendance_record)
        
        return Response({
            'success': True,
            'message': f'{attendance_type.capitalize()} registrada correctamente',
            'employee': {
                'id': str(best_match.id),
                'name': best_match.name,
                'employee_id': best_match.employee_id,
                'department': best_match.department
            },
            'confidence': f'{best_confidence:.1%}',
            'record': serializer.data
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error en verificación: {str(e)}'
        }, status=500)

@api_view(['POST'])
def create_employee(request):
    """Crear empleado con opción de registro facial inmediato"""
    try:
        data = request.data
        name = data.get('name', '').strip()
        employee_id = data.get('employee_id', '').strip()
        email = data.get('email', '').strip()
        department = data.get('department', 'General').strip()
        position = data.get('position', 'Empleado').strip()
        photo_base64 = data.get('photo')  # Foto opcional
        
        if not name:
            return Response({
                'success': False,
                'message': 'El nombre es requerido'
            }, status=400)
        
        # Auto generar employee_id si no se proporciona
        if not employee_id:
            employee_id = f"EMP{str(uuid.uuid4())[:8].upper()}"
            while Employee.objects.filter(employee_id=employee_id).exists():
                employee_id = f"EMP{str(uuid.uuid4())[:8].upper()}"
        
        # Verificar si ya existe
        if Employee.objects.filter(employee_id=employee_id).exists():
            return Response({
                'success': False,
                'message': f'Ya existe un empleado con ID: {employee_id}'
            }, status=400)
        
        # Generar email si no se proporciona
        if not email:
            email = f"{employee_id.lower()}@empresa.com"
        
        # Crear empleado
        employee = Employee.objects.create(
            employee_id=employee_id,
            name=name,
            email=email,
            department=department,
            position=position,
            is_active=True,
            has_face_registered=False
        )
        
        # Si se proporciona foto, registrar rostro
        face_registered = False
        if photo_base64:
            success, message, encodings = process_and_save_face_image(photo_base64, str(employee.id))
            if success:
                employee.face_encoding = json.dumps(encodings)
                employee.has_face_registered = True
                employee.face_registration_date = timezone.now()
                employee.save()
                face_registered = True
        
        serializer = EmployeeSerializer(employee)
        
        return Response({
            'success': True,
            'message': f'Empleado {name} creado exitosamente',
            'employee': serializer.data,
            'face_registered': face_registered
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error creando empleado: {str(e)}'
        }, status=500)

@api_view(['POST'])
def mark_attendance(request):
    """Marcar asistencia - compatible con facial y manual"""
    try:
        data = request.data
        
        # Si viene con foto, usar verificación facial
        if data.get('photo'):
            return verify_attendance_face(request)
        
        # Si no, usar sistema tradicional
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
        
        # Buscar empleado
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
                    'message': f'Múltiples empleados encontrados con "{employee_name}"'
                }, status=400)
        
        if not employee:
            return Response({
                'success': False,
                'message': f'Empleado no encontrado: {employee_name or employee_id}'
            }, status=404)
        
        # Crear registro
        if is_offline_sync and offline_timestamp:
            try:
                record_timestamp = datetime.fromisoformat(offline_timestamp.replace('Z', '+00:00'))
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
            notes=notes,
            is_offline_sync=is_offline_sync,
            face_confidence=0
        )
        
        serializer = AttendanceRecordSerializer(attendance_record)
        
        return Response({
            'success': True,
            'message': f'{employee.name} - {attendance_type} registrada',
            'record': serializer.data,
            'employee': {
                'id': str(employee.id),
                'name': employee.name,
                'employee_id': employee.employee_id,
                'department': employee.department
            }
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error: {str(e)}'
        }, status=500)

@api_view(['POST'])
def sync_offline_records(request):
    """Sincronizar registros offline con soporte para fotos"""
    try:
        offline_records = request.data.get('offline_records', [])
        synced_count = 0
        errors = []
        
        for record_data in offline_records:
            try:
                # Si tiene foto, verificar con facial
                if record_data.get('photo'):
                    # Crear request simulado para verify_attendance_face
                    from django.http import HttpRequest
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
                    
                    if response.status_code == 200:
                        synced_count += 1
                    else:
                        errors.append({
                            'local_id': record_data.get('local_id'),
                            'error': response.data.get('message', 'Error desconocido')
                        })
                else:
                    # Sin foto, usar método tradicional
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
                    
                    if response.status_code == 200:
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
            'message': f'Error en sincronización: {str(e)}'
        }, status=500)

@api_view(['GET'])
def get_employees(request):
    """Obtener lista de empleados"""
    try:
        employees = Employee.objects.filter(is_active=True).order_by('name')
        serializer = EmployeeSerializer(employees, many=True)
        
        return Response({
            'success': True,
            'employees': serializer.data,
            'count': employees.count(),
            'with_face': employees.filter(has_face_registered=True).count()
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error: {str(e)}'
        }, status=500)

@api_view(['GET'])
def get_attendance_records(request):
    """Obtener registros de asistencia"""
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
            'days_filter': days
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error: {str(e)}'
        }, status=500)

@api_view(['DELETE'])
def delete_employee(request, employee_id):
    """Eliminar empleado y sus fotos"""
    try:
        employee = Employee.objects.get(id=employee_id)
        employee_name = employee.name
        
        # Eliminar fotos guardadas
        for suffix in ['original', 'bright', 'contrast']:
            image_path = os.path.join(FACE_IMAGES_DIR, f"{employee_id}_{suffix}.jpg")
            if os.path.exists(image_path):
                os.remove(image_path)
        
        employee.is_active = False
        employee.save()
        
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
            'message': f'Error: {str(e)}'
        }, status=500)

def attendance_panel(request):
    """Panel web de asistencia"""
    return render(request, 'attendance_panel.html')