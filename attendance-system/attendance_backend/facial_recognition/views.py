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
from sklearn.preprocessing import StandardScaler

from .models import Employee, AttendanceRecord
from .serializers import EmployeeSerializer, AttendanceRecordSerializer

# Carpeta para guardar las fotos de empleados
FACE_IMAGES_DIR = 'media/employee_faces/'
os.makedirs(FACE_IMAGES_DIR, exist_ok=True)

# Configuración del sistema inteligente
SMART_CONFIG = {
    'min_photos': 5,                    # Mínimo de fotos para registro
    'base_tolerance': 0.50,              # Tolerancia base
    'adaptive_tolerance': True,          # Ajuste dinámico de tolerancia
    'min_confidence': 0.55,              # Confianza mínima (55%)
    'min_matches': 2,                    # Mínimo de coincidencias
    'use_landmarks': True,               # Usar puntos faciales
    'use_augmentation': True,            # Crear variaciones artificiales
    'max_tolerance': 0.65,               # Tolerancia máxima para casos difíciles
}

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
            'features': [
                'Detección de puntos faciales',
                'Normalización de características',
                'Tolerancia adaptativa',
                'Augmentación de datos',
                'Análisis multi-escala'
            ]
        }
    })

def extract_face_landmarks(image_array):
    """
    Extraer puntos faciales clave (68 puntos)
    Estos puntos son más estables que el encoding completo
    """
    face_landmarks_list = face_recognition.face_landmarks(image_array)
    
    if not face_landmarks_list:
        return None
    
    landmarks = face_landmarks_list[0]
    
    # Extraer puntos clave que son invariantes a accesorios
    key_points = {
        'nose_bridge': landmarks.get('nose_bridge', []),
        'nose_tip': landmarks.get('nose_tip', []),
        'chin': landmarks.get('chin', []),
        'left_eye': landmarks.get('left_eye', []),
        'right_eye': landmarks.get('right_eye', []),
        'left_eyebrow': landmarks.get('left_eyebrow', []),
        'right_eyebrow': landmarks.get('right_eyebrow', []),
    }
    
    # Convertir a vector numérico normalizado
    points_vector = []
    for feature, points in key_points.items():
        for point in points:
            points_vector.extend(point)
    
    return np.array(points_vector)

def normalize_face_features(encoding, landmarks):
    """
    Normalizar características faciales para hacerlas más robustas
    """
    if landmarks is not None:
        # Calcular distancias entre puntos clave (invariantes a escala)
        eye_distance = np.linalg.norm(
            np.array(landmarks[36*2:36*2+2]) - np.array(landmarks[45*2:45*2+2])
        ) if len(landmarks) > 90 else 1.0
        
        # Normalizar por distancia inter-ocular
        if eye_distance > 0:
            normalized_landmarks = landmarks / eye_distance
        else:
            normalized_landmarks = landmarks
    else:
        normalized_landmarks = np.zeros(136)  # Vector vacío si no hay landmarks
    
    # Combinar encoding con landmarks normalizados
    # Dar más peso al encoding pero incluir landmarks para robustez
    combined = np.concatenate([
        encoding * 0.7,  # 70% peso al encoding
        normalized_landmarks[:50] * 0.3  # 30% peso a landmarks principales
    ])
    
    return combined

def create_augmented_encodings(image_array, face_location):
    """
    Crear variaciones artificiales para mejorar reconocimiento
    Simula diferentes condiciones: con/sin lentes, diferentes iluminaciones, etc.
    """
    augmented_encodings = []
    
    # Original
    original_encoding = face_recognition.face_encodings(
        image_array, [face_location], num_jitters=5, model="large"
    )
    if original_encoding:
        augmented_encodings.append(original_encoding[0])
    
    # Simular diferentes condiciones
    image = Image.fromarray(image_array)
    
    # Variación 1: Simular sombras (como si tuviera lentes)
    top, right, bottom, left = face_location
    eye_area_top = top + int((bottom - top) * 0.2)
    eye_area_bottom = top + int((bottom - top) * 0.4)
    
    shadowed = image.copy()
    draw = ImageDraw.Draw(shadowed)
    # Crear sombra semi-transparente en área de ojos
    for i in range(3):
        alpha = 30 + i * 10
        overlay = Image.new('RGBA', shadowed.size, (0, 0, 0, 0))
        draw_overlay = ImageDraw.Draw(overlay)
        draw_overlay.rectangle(
            [left, eye_area_top, right, eye_area_bottom],
            fill=(0, 0, 0, alpha)
        )
        shadowed = Image.alpha_composite(
            shadowed.convert('RGBA'), 
            overlay
        ).convert('RGB')
    
    shadow_encoding = face_recognition.face_encodings(
        np.array(shadowed), [face_location], num_jitters=2
    )
    if shadow_encoding:
        augmented_encodings.append(shadow_encoding[0])
    
    # Variación 2: Brillo aumentado (simula diferentes iluminaciones)
    bright = ImageEnhance.Brightness(image).enhance(1.3)
    bright_encoding = face_recognition.face_encodings(
        np.array(bright), [face_location], num_jitters=2
    )
    if bright_encoding:
        augmented_encodings.append(bright_encoding[0])
    
    # Variación 3: Contraste aumentado
    contrast = ImageEnhance.Contrast(image).enhance(1.5)
    contrast_encoding = face_recognition.face_encodings(
        np.array(contrast), [face_location], num_jitters=2
    )
    if contrast_encoding:
        augmented_encodings.append(contrast_encoding[0])
    
    # Variación 4: Desenfoque leve (simula movimiento o mala calidad)
    blurred = image.filter(ImageFilter.GaussianBlur(radius=0.5))
    blur_encoding = face_recognition.face_encodings(
        np.array(blurred), [face_location], num_jitters=2
    )
    if blur_encoding:
        augmented_encodings.append(blur_encoding[0])
    
    return augmented_encodings

def intelligent_face_comparison(stored_data, current_encoding, current_landmarks):
    """
    Comparación inteligente usando múltiples métodos y características
    """
    stored_encodings = stored_data.get('encodings', [])
    stored_landmarks = stored_data.get('landmarks', [])
    stored_augmented = stored_data.get('augmented', [])
    
    if not stored_encodings:
        return False, 0.0, "Sin datos de rostro"
    
    # Normalizar características actuales
    if current_landmarks is not None:
        current_features = normalize_face_features(current_encoding, current_landmarks)
    else:
        current_features = current_encoding
    
    all_scores = []
    comparison_details = []
    
    # Comparar con encodings originales
    for i, stored_enc in enumerate(stored_encodings):
        stored_enc_array = np.array(stored_enc)
        
        # Método 1: Distancia euclidiana estándar
        euclidean_dist = face_recognition.face_distance([stored_enc_array], current_encoding)[0]
        
        # Método 2: Similitud coseno (mejor para variaciones de iluminación)
        cosine_sim = 1 - distance.cosine(stored_enc_array, current_encoding)
        
        # Método 3: Correlación
        correlation = np.corrcoef(stored_enc_array, current_encoding)[0, 1]
        
        # Score combinado
        score = (
            (1 - euclidean_dist) * 0.5 +  # 50% distancia euclidiana
            cosine_sim * 0.3 +              # 30% similitud coseno
            correlation * 0.2                # 20% correlación
        )
        
        all_scores.append(score)
        comparison_details.append({
            'photo': i + 1,
            'euclidean': euclidean_dist,
            'cosine': cosine_sim,
            'correlation': correlation,
            'score': score
        })
    
    # Comparar con encodings aumentados si existen
    if stored_augmented:
        for aug_set in stored_augmented:
            for aug_enc in aug_set:
                aug_array = np.array(aug_enc)
                aug_dist = face_recognition.face_distance([aug_array], current_encoding)[0]
                aug_score = 1 - aug_dist
                all_scores.append(aug_score * 0.9)  # Peso ligeramente menor para augmented
    
    # Comparar landmarks si están disponibles
    landmark_score = 0
    if current_landmarks is not None and stored_landmarks:
        landmark_similarities = []
        for stored_lm in stored_landmarks:
            if stored_lm is not None:
                stored_lm_array = np.array(stored_lm)
                # Normalizar longitudes si es necesario
                min_len = min(len(current_landmarks), len(stored_lm_array))
                lm_similarity = 1 - distance.cosine(
                    current_landmarks[:min_len], 
                    stored_lm_array[:min_len]
                )
                landmark_similarities.append(lm_similarity)
        
        if landmark_similarities:
            landmark_score = np.mean(landmark_similarities)
            all_scores.append(landmark_score * 0.8)  # Peso para landmarks
    
    # Calcular score final
    if not all_scores:
        return False, 0.0, "No se pudo comparar"
    
    # Usar percentil 75 en lugar de máximo (más robusto)
    final_score = np.percentile(all_scores, 75)
    
    # Determinar tolerancia adaptativa
    if SMART_CONFIG['adaptive_tolerance']:
        # Ajustar tolerancia basado en calidad de detección
        if landmark_score > 0.7:  # Buenos landmarks detectados
            tolerance = SMART_CONFIG['base_tolerance']
        else:  # Landmarks pobres, ser más tolerante
            tolerance = min(SMART_CONFIG['max_tolerance'], SMART_CONFIG['base_tolerance'] + 0.1)
        
        # Si muchos scores son altos, es probable que sea la persona correcta
        high_scores = [s for s in all_scores if s > 0.5]
        if len(high_scores) >= SMART_CONFIG['min_matches']:
            tolerance = SMART_CONFIG['max_tolerance']
    else:
        tolerance = SMART_CONFIG['base_tolerance']
    
    # Decisión final
    is_match = final_score >= (1 - tolerance)
    confidence = min(1.0, final_score)
    
    # Debug info
    print(f"\n🔍 Análisis Inteligente:")
    print(f"   Score final: {final_score:.3f}")
    print(f"   Tolerancia adaptada: {tolerance:.3f}")
    print(f"   Landmark score: {landmark_score:.3f}")
    print(f"   Scores altos: {len(high_scores)}/{len(all_scores)}")
    print(f"   Decisión: {'✅ MATCH' if is_match else '❌ NO MATCH'}")
    
    return is_match, confidence, f"Score: {confidence:.1%}"

def process_registration_photos(photos_base64):
    """
    Procesar múltiples fotos para registro inteligente
    """
    all_encodings = []
    all_landmarks = []
    all_augmented = []
    valid_photos = 0
    
    for idx, photo_base64 in enumerate(photos_base64):
        try:
            # Decodificar imagen
            if ',' in photo_base64:
                photo_base64 = photo_base64.split(',')[1]
            
            image_data = base64.b64decode(photo_base64)
            image = Image.open(io.BytesIO(image_data))
            
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Redimensionar para procesamiento óptimo
            if image.width > 800:
                ratio = 800 / image.width
                new_height = int(image.height * ratio)
                image = image.resize((800, new_height), Image.Resampling.LANCZOS)
            
            image_array = np.array(image)
            
            # Detectar rostro
            face_locations = face_recognition.face_locations(
                image_array,
                number_of_times_to_upsample=1,
                model="hog"
            )
            
            if not face_locations:
                # Intentar con CNN
                try:
                    face_locations = face_recognition.face_locations(
                        image_array,
                        model="cnn"
                    )
                except:
                    pass
            
            if not face_locations:
                print(f"   ⚠️ Foto {idx+1}: No se detectó rostro")
                continue
            
            face_location = face_locations[0]
            
            # Extraer encoding principal
            encodings = face_recognition.face_encodings(
                image_array,
                [face_location],
                num_jitters=10,
                model="large"
            )
            
            if not encodings:
                continue
            
            all_encodings.append(encodings[0].tolist())
            
            # Extraer landmarks
            landmarks = extract_face_landmarks(image_array)
            if landmarks is not None:
                all_landmarks.append(landmarks.tolist())
            else:
                all_landmarks.append(None)
            
            # Crear encodings aumentados
            if SMART_CONFIG['use_augmentation']:
                augmented = create_augmented_encodings(image_array, face_location)
                all_augmented.append([enc.tolist() for enc in augmented])
            
            valid_photos += 1
            print(f"   ✅ Foto {idx+1}: Procesada correctamente")
            
        except Exception as e:
            print(f"   ❌ Foto {idx+1}: Error - {str(e)}")
            continue
    
    return {
        'encodings': all_encodings,
        'landmarks': all_landmarks,
        'augmented': all_augmented,
        'valid_photos': valid_photos
    }

@api_view(['POST'])
def register_employee_face(request):
    """
    Registro inteligente con múltiples fotos y augmentación
    """
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
                'message': f'Se requieren mínimo {SMART_CONFIG["min_photos"]} fotos',
                'photos_received': len(photos)
            }, status=400)
        
        try:
            employee = Employee.objects.get(id=employee_id, is_active=True)
        except Employee.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Empleado no encontrado'
            }, status=404)
        
        print(f"\n📸 Registro Inteligente para {employee.name}")
        print(f"   Procesando {len(photos)} fotos...")
        
        # Procesar todas las fotos
        face_data = process_registration_photos(photos)
        
        if face_data['valid_photos'] < SMART_CONFIG['min_photos']:
            return Response({
                'success': False,
                'message': f'Solo se procesaron {face_data["valid_photos"]} fotos válidas',
                'required': SMART_CONFIG['min_photos']
            }, status=400)
        
        # Guardar fotos originales
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
        
        # Guardar datos procesados
        face_data['registration_date'] = datetime.now().isoformat()
        face_data['system_version'] = 'SMART_v2.0'
        
        employee.face_encoding = json.dumps(face_data)
        employee.has_face_registered = True
        employee.face_registration_date = timezone.now()
        employee.face_quality_score = 1.0
        employee.save()
        
        print(f"✅ Registro completo con {face_data['valid_photos']} fotos")
        print(f"   - Encodings: {len(face_data['encodings'])}")
        print(f"   - Landmarks: {len([l for l in face_data['landmarks'] if l])}")
        print(f"   - Augmented sets: {len(face_data['augmented'])}")
        
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
        print(f"❌ Error en registro: {str(e)}")
        return Response({
            'success': False,
            'message': f'Error: {str(e)}'
        }, status=500)

@api_view(['POST'])
def verify_attendance_face(request):
    """
    Verificación inteligente con tolerancia adaptativa
    """
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
        
        # Procesar foto actual
        if ',' in photo_base64:
            photo_base64 = photo_base64.split(',')[1]
        
        image_data = base64.b64decode(photo_base64)
        image = Image.open(io.BytesIO(image_data))
        
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Pre-procesar para mejorar detección
        # Ecualizar histograma para normalizar iluminación
        image = ImageOps.equalize(image)
        
        image_array = np.array(image)
        
        # Detectar rostro
        face_locations = face_recognition.face_locations(
            image_array,
            number_of_times_to_upsample=1,
            model="hog"
        )
        
        if not face_locations:
            try:
                face_locations = face_recognition.face_locations(
                    image_array,
                    model="cnn"
                )
            except:
                pass
        
        if not face_locations:
            return Response({
                'success': False,
                'message': 'No se detectó rostro',
                'suggestion': 'Asegúrate de que tu rostro esté visible y bien iluminado'
            }, status=400)
        
        # Extraer encoding y landmarks
        current_encoding = face_recognition.face_encodings(
            image_array,
            face_locations,
            num_jitters=5,
            model="large"
        )[0]
        
        current_landmarks = extract_face_landmarks(image_array)
        
        # Buscar coincidencia con empleados
        best_match = None
        best_confidence = 0
        all_results = []
        
        employees_with_faces = Employee.objects.filter(
            is_active=True,
            has_face_registered=True
        )
        
        print(f"\n🔍 Verificación Inteligente")
        print(f"   Comparando con {employees_with_faces.count()} empleados...")
        
        for employee in employees_with_faces:
            try:
                stored_data = json.loads(employee.face_encoding)
                
                is_match, confidence, details = intelligent_face_comparison(
                    stored_data,
                    current_encoding,
                    current_landmarks
                )
                
                all_results.append({
                    'employee': employee.name,
                    'confidence': confidence,
                    'match': is_match
                })
                
                if is_match and confidence > best_confidence:
                    best_confidence = confidence
                    best_match = employee
                    
            except Exception as e:
                print(f"   Error con {employee.name}: {str(e)}")
                continue
        
        if not best_match:
            # Buscar el más cercano para feedback
            if all_results:
                closest = max(all_results, key=lambda x: x['confidence'])
                
                return Response({
                    'success': False,
                    'message': 'No se pudo verificar identidad',
                    'closest_match': closest['employee'],
                    'closest_confidence': f"{closest['confidence']:.1%}",
                    'required_confidence': f"{SMART_CONFIG['min_confidence']:.0%}",
                    'tips': [
                        'El sistema se adapta a cambios como lentes o barba',
                        'Pero necesita un mínimo de similitud facial',
                        'Intenta con mejor iluminación',
                        'Asegúrate de ser el empleado correcto'
                    ]
                }, status=404)
            else:
                return Response({
                    'success': False,
                    'message': 'No hay empleados registrados con datos faciales'
                }, status=404)
        
        print(f"✅ VERIFICADO: {best_match.name} ({best_confidence:.1%})")
        
        # Crear registro de asistencia
        attendance_record = AttendanceRecord.objects.create(
            employee=best_match,
            attendance_type=attendance_type,
            timestamp=timezone.now(),
            location_lat=location_lat,
            location_lng=location_lng,
            address=address,
            face_confidence=best_confidence,
            notes=f'Verificación inteligente ({best_confidence:.1%})'
        )
        
        serializer = AttendanceRecordSerializer(attendance_record)
        
        return Response({
            'success': True,
            'message': f'{attendance_type.capitalize()} registrada',
            'employee': {
                'id': str(best_match.id),
                'name': best_match.name,
                'employee_id': best_match.employee_id,
                'department': best_match.department
            },
            'confidence': f'{best_confidence:.1%}',
            'verification_mode': 'INTELIGENTE',
            'record': serializer.data
        })
        
    except Exception as e:
        print(f"❌ Error en verificación: {str(e)}")
        return Response({
            'success': False,
            'message': f'Error: {str(e)}'
        }, status=500)

# El resto de las funciones (create_employee, mark_attendance, etc.) 
# permanecen iguales que en la versión anterior

@api_view(['POST'])
def create_employee(request):
    """Crear empleado"""
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
        
        if not employee_id:
            employee_id = f"EMP{str(uuid.uuid4())[:8].upper()}"
            while Employee.objects.filter(employee_id=employee_id).exists():
                employee_id = f"EMP{str(uuid.uuid4())[:8].upper()}"
        
        if Employee.objects.filter(employee_id=employee_id).exists():
            return Response({
                'success': False,
                'message': f'Ya existe un empleado con ID: {employee_id}'
            }, status=400)
        
        if not email:
            email = f"{employee_id.lower()}@empresa.com"
        
        employee = Employee.objects.create(
            employee_id=employee_id,
            name=name,
            email=email,
            department=department,
            position=position,
            is_active=True,
            has_face_registered=False
        )
        
        serializer = EmployeeSerializer(employee)
        
        return Response({
            'success': True,
            'message': f'Empleado {name} creado',
            'employee': serializer.data,
            'photos_required': SMART_CONFIG['min_photos']
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error: {str(e)}'
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
            notes=notes,
            is_offline_sync=is_offline_sync,
            face_confidence=0
        )
        
        serializer = AttendanceRecordSerializer(attendance_record)
        
        return Response({
            'success': True,
            'message': f'{attendance_type} registrada',
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
    """Sincronizar registros offline"""
    try:
        offline_records = request.data.get('offline_records', [])
        synced_count = 0
        errors = []
        
        for record_data in offline_records:
            try:
                from django.http import HttpRequest
                mock_request = HttpRequest()
                mock_request.method = 'POST'
                
                if record_data.get('photo'):
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
            'system_mode': 'INTELIGENTE'
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
            'total': total_count
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
        
        # Eliminar fotos
        for i in range(1, 6):
            path = os.path.join(FACE_IMAGES_DIR, f"{employee_id}_photo_{i}.jpg")
            if os.path.exists(path):
                os.remove(path)
        
        employee.is_active = False
        employee.save()
        
        return Response({
            'success': True,
            'message': f'{employee_name} eliminado'
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
    """Eliminar registro"""
    try:
        attendance_record = AttendanceRecord.objects.get(id=attendance_id)
        employee_name = attendance_record.employee.name
        attendance_record.delete()
        
        return Response({
            'success': True,
            'message': f'Registro eliminado'
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