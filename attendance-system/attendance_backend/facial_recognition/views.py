from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.db import transaction
from django.shortcuts import render
from datetime import datetime, timedelta
import uuid

from .models import Employee, AttendanceRecord
from .serializers import EmployeeSerializer, AttendanceRecordSerializer

@api_view(['GET'])
def health_check(request):
    """Estado de salud del sistema"""
    return Response({
        'status': 'OK',
        'message': 'Sistema de asistencia GPS funcionando',
        'timestamp': datetime.now().isoformat(),
        'employees_count': Employee.objects.filter(is_active=True).count(),
        'attendance_today': AttendanceRecord.objects.filter(
            timestamp__date=timezone.now().date()
        ).count(),
        'mode': 'GPS + Manual'
    })

@api_view(['POST'])
def create_employee(request):
    """Crear nuevo empleado"""
    try:
        data = request.data
        name = data.get('name', '').strip()
        employee_id = data.get('employee_id', '').strip()
        email = data.get('email', '').strip()
        department = data.get('department', 'General').strip()
        position = data.get('position', 'Empleado').strip()
        
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
            is_active=True
        )
        
        serializer = EmployeeSerializer(employee)
        
        return Response({
            'success': True,
            'message': f'Empleado {name} creado exitosamente',
            'employee': serializer.data
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error creando empleado: {str(e)}'
        }, status=500)

@api_view(['POST'])
def mark_attendance(request):
    """Marcar asistencia por empleado"""
    try:
        data = request.data
        employee_name = data.get('employee_name', '').strip()
        employee_id = data.get('employee_id', '').strip()
        attendance_type = data.get('type', 'entrada').lower()
        location_lat = data.get('latitude')
        location_lng = data.get('longitude')
        address = data.get('address', '')
        notes = data.get('notes', '')
        is_offline_sync = data.get('is_offline_sync', False)
        offline_timestamp = data.get('offline_timestamp')
        
        # Validaciones
        if not employee_name and not employee_id:
            return Response({
                'success': False,
                'message': 'Se requiere nombre o ID del empleado'
            }, status=400)
        
        if attendance_type not in ['entrada', 'salida']:
            return Response({
                'success': False,
                'message': 'Tipo de asistencia inválido (entrada/salida)'
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
                    'message': f'Múltiples empleados encontrados con el nombre "{employee_name}"'
                }, status=400)
        
        if not employee:
            return Response({
                'success': False,
                'message': f'Empleado no encontrado: {employee_name or employee_id}'
            }, status=404)
        
        # Verificar registros recientes para evitar duplicados
        today = timezone.now().date()
        recent_record = AttendanceRecord.objects.filter(
            employee=employee,
            attendance_type=attendance_type,
            timestamp__date=today
        ).order_by('-timestamp').first()
        
        if recent_record:
            time_diff = (timezone.now() - recent_record.timestamp).total_seconds()
            if time_diff < 300:  # 5 minutos
                return Response({
                    'success': False,
                    'message': f'{attendance_type.capitalize()} ya registrada hace {int(time_diff/60)} minutos'
                }, status=400)
        
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
            employee=employee,
            attendance_type=attendance_type,
            timestamp=record_timestamp,
            location_lat=location_lat,
            location_lng=location_lng,
            address=address,
            notes=notes,
            is_offline_sync=is_offline_sync
        )
        
        serializer = AttendanceRecordSerializer(attendance_record)
        
        return Response({
            'success': True,
            'message': f'{employee.name} - {attendance_type} registrada correctamente',
            'record': serializer.data,
            'employee': {
                'id': str(employee.id),
                'name': employee.name,
                'employee_id': employee.employee_id,
                'department': employee.department,
                'position': employee.position
            }
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error registrando asistencia: {str(e)}'
        }, status=500)

@api_view(['POST'])
def sync_offline_records(request):
    """Sincronizar registros offline"""
    try:
        offline_records = request.data.get('offline_records', [])
        synced_count = 0
        errors = []
        synced_records = []
        
        for record_data in offline_records:
            try:
                # Marcar asistencia offline
                mark_data = {
                    'employee_name': record_data.get('employee_name'),
                    'type': record_data.get('type'),
                    'latitude': record_data.get('latitude'),
                    'longitude': record_data.get('longitude'),
                    'address': record_data.get('address', ''),
                    'notes': record_data.get('notes', '') + ' (sync offline)',
                    'is_offline_sync': True,
                    'offline_timestamp': record_data.get('timestamp')
                }
                
                # Simular request para reutilizar la función
                from django.http import HttpRequest
                
                mock_request = HttpRequest()
                mock_request.method = 'POST'
                mock_request.data = mark_data
                
                sync_response = mark_attendance(mock_request)
                
                if sync_response.status_code == 200 and sync_response.data.get('success'):
                    synced_count += 1
                    synced_records.append({
                        'local_id': record_data.get('local_id'),
                        'employee_name': sync_response.data['record']['employee_name'],
                        'type': sync_response.data['record']['attendance_type'],
                        'timestamp': sync_response.data['record']['formatted_timestamp']
                    })
                else:
                    errors.append({
                        'local_id': record_data.get('local_id'),
                        'error': sync_response.data.get('message', 'Error desconocido')
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
            'errors': errors[:10],  # Solo primeros 10 errores
            'synced_records': synced_records,
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
            'count': employees.count()
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
    """Eliminar empleado"""
    try:
        employee = Employee.objects.get(id=employee_id)
        employee_name = employee.name
        
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
            'message': 'Error eliminando empleado'
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
            'message': 'Error eliminando registro'
        }, status=500)

def attendance_panel(request):
    """Panel web de asistencia"""
    return render(request, 'attendance_panel.html')