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

from .models import Employee, AttendanceRecord
from .serializers import EmployeeSerializer, AttendanceRecordSerializer

# Carpeta para guardar las fotos de empleados
FACE_IMAGES_DIR = 'media/employee_faces/'
os.makedirs(FACE_IMAGES_DIR, exist_ok=True)

# Configuración del sistema inteligente
SMART_CONFIG = {
    'min_photos': 5,
    'base_tolerance': 0.40,
    'adaptive_tolerance': True,
    'min_confidence': 0.70,
    'min_matches': 3,
    'use_landmarks': True,
    'use_augmentation': True,
    'max_tolerance': 0.45,
    'verification_timeout': 10,
    'strict_mode': True,
    'require_full_face': True,
    'min_face_size': 80,
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

def verify_face_quality(image_array, face_location):
    """Verificar que el rostro sea de calidad suficiente y esté completo"""
    top, right, bottom, left = face_location
    
    face_width = right - left
    face_height = bottom - top
    
    if face_width < SMART_CONFIG['min_face_size'] or face_height < SMART_CONFIG['min_face_size']:
        return False, "Rostro muy pequeño - acércate más a la cámara"
    
    image_height, image_width = image_array.shape[:2]
    
    margin = 15
    if (left < margin or right > image_width - margin or 
        top < margin or bottom > image_height - margin):
        return False, "Rostro parcialmente cortado - centra tu cara"
    
    aspect_ratio = face_height / face_width
    if aspect_ratio < 1.0 or aspect_ratio > 2.0:
        return False, "Ángulo del rostro incorrecto"
    
    face_landmarks = face_recognition.face_landmarks(image_array, [face_location])
    
    if not face_landmarks:
        return False, "No se detectaron características faciales"
    
    landmarks = face_landmarks[0]
    
    required_features = ['chin', 'left_eye', 'right_eye', 'nose_bridge', 'nose_tip']
    missing_features = []
    
    for feature in required_features:
        if feature not in landmarks or not landmarks[feature]:
            missing_features.append(feature)
    
    if missing_features:
        return False, f"Características faltantes: {', '.join(missing_features)}"
    
    if len(landmarks.get('left_eye', [])) < 4 or len(landmarks.get('right_eye', [])) < 4:
        return False, "Ambos ojos deben estar visibles"
    
    chin_points = landmarks.get('chin', [])
    if len(chin_points) < 15:
        return False, "Barbilla no visible completa"
    
    return True, "Rostro válido"

def extract_face_landmarks(image_array):
    """Extraer puntos faciales clave (68 puntos)"""
    face_landmarks_list = face_recognition.face_landmarks(image_array)
    
    if not face_landmarks_list:
        return None
    
    landmarks = face_landmarks_list[0]
    
    key_points = {
        'nose_bridge': landmarks.get('nose_bridge', []),
        'nose_tip': landmarks.get('nose_tip', []),
        'chin': landmarks.get('chin', []),
        'left_eye': landmarks.get('left_eye', []),
        'right_eye': landmarks.get('right_eye', []),
        'left_eyebrow': landmarks.get('left_eyebrow', []),
        'right_eyebrow': landmarks.get('right_eyebrow', []),
    }
    
    points_vector = []
    for feature, points in key_points.items():
        for point in points:
            points_vector.extend(point)
    
    return np.array(points_vector)

def normalize_face_features(encoding, landmarks):
    """Normalizar características faciales"""
    if landmarks is not None:
        eye_distance = np.linalg.norm(
            np.array(landmarks[36*2:36*2+2]) - np.array(landmarks[45*2:45*2+2])
        ) if len(landmarks) > 90 else 1.0
        
        if eye_distance > 0:
            normalized_landmarks = landmarks / eye_distance
        else:
            normalized_landmarks = landmarks
    else:
        normalized_landmarks = np.zeros(136)
    
    combined = np.concatenate([
        encoding * 0.7,
        normalized_landmarks[:50] * 0.3
    ])
    
    return combined

def create_augmented_encodings(image_array, face_location):
    """Crear variaciones artificiales"""
    augmented_encodings = []
    
    original_encoding = face_recognition.face_encodings(
        image_array, [face_location], num_jitters=5, model="large"
    )
    if original_encoding:
        augmented_encodings.append(original_encoding[0])
    
    image = Image.fromarray(image_array)
    
    top, right, bottom, left = face_location
    eye_area_top = top + int((bottom - top) * 0.2)
    eye_area_bottom = top + int((bottom - top) * 0.4)
    
    # Variación con sombras
    shadowed = image.copy()
    draw = ImageDraw.Draw(shadowed)
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
    
    # Variación con brillo
    bright = ImageEnhance.Brightness(image).enhance(1.3)
    bright_encoding = face_recognition.face_encodings(
        np.array(bright), [face_location], num_jitters=2
    )
    if bright_encoding:
        augmented_encodings.append(bright_encoding[0])
    
    # Variación con contraste
    contrast = ImageEnhance.Contrast(image).enhance(1.5)
    contrast_encoding = face_recognition.face_encodings(
        np.array(contrast), [face_location], num_jitters=2
    )
    if contrast_encoding:
        augmented_encodings.append(contrast_encoding[0])
    
    # Variación con desenfoque
    blurred = image.filter(ImageFilter.GaussianBlur(radius=0.5))
    blur_encoding = face_recognition.face_encodings(
        np.array(blurred), [face_location], num_jitters=2
    )
    if blur_encoding:
        augmented_encodings.append(blur_encoding[0])
    
    return augmented_encodings

def intelligent_face_comparison(stored_data, current_encoding, current_landmarks, quick_mode=False):
    """Comparación inteligente ESTRICTA"""
    stored_encodings = stored_data.get('encodings', [])
    stored_landmarks = stored_data.get('landmarks', [])
    stored_augmented = stored_data.get('augmented', [])
    
    if not stored_encodings:
        return False, 0.0, "Sin datos de rostro"
    
    if SMART_CONFIG['strict_mode'] and current_landmarks is None:
        return False, 0.0, "No se detectaron puntos faciales"
    
    all_scores = []
    high_quality_scores = []
    
    for i, stored_enc in enumerate(stored_encodings):
        if stored_enc is None:
            continue
            
        stored_enc_array = np.array(stored_enc)
        
        euclidean_dist = face_recognition.face_distance([stored_enc_array], current_encoding)[0]
        
        if SMART_CONFIG['strict_mode'] and euclidean_dist > 0.6:
            continue
        
        if not quick_mode:
            cosine_sim = 1 - distance.cosine(stored_enc_array, current_encoding)
            correlation = np.corrcoef(stored_enc_array, current_encoding)[0, 1]
            
            score = (
                (1 - euclidean_dist) * 0.6 +
                cosine_sim * 0.25 +
                correlation * 0.15
            )
            
            if score > 0.5:
                high_quality_scores.append(score)
        else:
            score = 1 - euclidean_dist
        
        all_scores.append(score)
    
    if SMART_CONFIG['strict_mode']:
        if len(high_quality_scores) < SMART_CONFIG['min_matches']:
            return False, 0.0, f"Insuficientes coincidencias ({len(high_quality_scores)}/{SMART_CONFIG['min_matches']})"
    
    landmark_match = False
    if current_landmarks is not None and stored_landmarks:
        landmark_similarities = []
        
        for stored_lm in stored_landmarks:
            if stored_lm is not None:
                stored_lm_array = np.array(stored_lm)
                min_len = min(len(current_landmarks), len(stored_lm_array))
                
                if min_len > 100:
                    lm_similarity = 1 - distance.cosine(
                        current_landmarks[:min_len], 
                        stored_lm_array[:min_len]
                    )
                    landmark_similarities.append(lm_similarity)
        
        if landmark_similarities:
            landmark_score = np.mean(landmark_similarities)
            
            if SMART_CONFIG['strict_mode']:
                landmark_match = landmark_score > 0.65
                if not landmark_match:
                    return False, 0.0, f"Geometría facial no coincide ({landmark_score:.1%})"
    
    if not all_scores:
        return False, 0.0, "No hay coincidencias"
    
    if SMART_CONFIG['strict_mode'] and high_quality_scores:
        final_score = np.mean(high_quality_scores)
    else:
        final_score = np.percentile(all_scores, 60)
    
    if SMART_CONFIG['strict_mode']:
        tolerance = SMART_CONFIG['base_tolerance']
    else:
        tolerance = SMART_CONFIG['max_tolerance']
    
    if final_score < SMART_CONFIG['min_confidence']:
        return False, final_score, f"Confianza insuficiente ({final_score:.1%} < {SMART_CONFIG['min_confidence']:.0%})"
    
    is_match = final_score >= (1 - tolerance) and final_score >= SMART_CONFIG['min_confidence']
    confidence = min(1.0, final_score)
    
    print(f"\n🔒 Verificación ESTRICTA:")
    print(f"   Score final: {final_score:.3f}")
    print(f"   Coincidencias de alta calidad: {len(high_quality_scores)}")
    print(f"   Decisión: {'✅ AUTORIZADO' if is_match else '❌ RECHAZADO'}")
    
    return is_match, confidence, f"Score: {confidence:.1%}"

def process_registration_photos(photos_base64):
    """Procesar múltiples fotos para registro"""
    all_encodings = []
    all_landmarks = []
    all_augmented = []
    valid_photos = 0
    failed_photos = []
    
    print(f"\n📸 Iniciando procesamiento de {len(photos_base64)} fotos...")
    
    for idx, photo_base64 in enumerate(photos_base64):
        try:
            print(f"   Procesando foto {idx+1}/{len(photos_base64)}...")
            
            if ',' in photo_base64:
                photo_base64 = photo_base64.split(',')[1]
            
            image_data = base64.b64decode(photo_base64)
            image = Image.open(io.BytesIO(image_data))
            
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            if image.width > 800:
                ratio = 800 / image.width
                new_height = int(image.height * ratio)
                image = image.resize((800, new_height), Image.Resampling.LANCZOS)
            
            image_array = np.array(image)
            
            face_locations = []
            
            face_locations = face_recognition.face_locations(
                image_array,
                number_of_times_to_upsample=1,
                model="hog"
            )
            
            if not face_locations:
                face_locations = face_recognition.face_locations(
                    image_array,
                    number_of_times_to_upsample=2,
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
                try:
                    enhanced = ImageEnhance.Contrast(image).enhance(1.5)
                    enhanced_array = np.array(enhanced)
                    face_locations = face_recognition.face_locations(
                        enhanced_array,
                        number_of_times_to_upsample=1,
                        model="hog"
                    )
                    if face_locations:
                        image_array = enhanced_array
                except:
                    pass
            
            if not face_locations:
                print(f"   ⚠️ Foto {idx+1}: No se detectó rostro")
                failed_photos.append(idx+1)
                all_encodings.append(None)
                all_landmarks.append(None)
                all_augmented.append([])
                continue
            
            face_location = face_locations[0]
            
            encodings = face_recognition.face_encodings(
                image_array,
                [face_location],
                num_jitters=10,
                model="large"
            )
            
            if not encodings:
                encodings = face_recognition.face_encodings(
                    image_array,
                    [face_location],
                    num_jitters=5,
                    model="large"
                )
            
            if not encodings:
                encodings = face_recognition.face_encodings(
                    image_array,
                    [face_location],
                    num_jitters=2,
                    model="small"
                )
            
            if encodings:
                all_encodings.append(encodings[0].tolist())
                valid_photos += 1
                print(f"     - Encoding extraído")
            else:
                all_encodings.append(None)
                failed_photos.append(idx+1)
            
            try:
                landmarks = extract_face_landmarks(image_array)
                if landmarks is not None:
                    all_landmarks.append(landmarks.tolist())
                else:
                    all_landmarks.append(None)
            except:
                all_landmarks.append(None)
            
            if encodings and SMART_CONFIG['use_augmentation']:
                try:
                    augmented = create_augmented_encodings(image_array, face_location)
                    all_augmented.append([enc.tolist() for enc in augmented])
                except:
                    all_augmented.append([])
            else:
                all_augmented.append([])
                
        except Exception as e:
            print(f"   ❌ Foto {idx+1}: Error - {str(e)}")
            all_encodings.append(None)
            all_landmarks.append(None)
            all_augmented.append([])
            failed_photos.append(idx+1)
    
    valid_encodings = [enc for enc in all_encodings if enc is not None]
    valid_landmarks = [lm for lm in all_landmarks if lm is not None]
    valid_augmented = [aug for aug in all_augmented if aug and len(aug) > 0]
    
    return {
        'encodings': valid_encodings,
        'landmarks': valid_landmarks,
        'augmented': valid_augmented,
        'valid_photos': len(valid_encodings),
        'total_photos': len(photos_base64),
        'failed_photos': failed_photos
    }

def process_verification_with_timeout(photo_base64, timeout=10):
    """Procesar verificación con timeout"""
    def verify_process():
        try:
            start_time = time.time()
            
            if ',' in photo_base64:
                photo_data = photo_base64.split(',')[1]
            else:
                photo_data = photo_base64
            
            image_data = base64.b64decode(photo_data)
            image = Image.open(io.BytesIO(image_data))
            
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            image = ImageOps.equalize(image)
            image_array = np.array(image)
            
            face_locations = []
            
            if time.time() - start_time < 2:
                face_locations = face_recognition.face_locations(
                    image_array,
                    number_of_times_to_upsample=1,
                    model="hog"
                )
            
            if not face_locations and (time.time() - start_time < timeout/2):
                try:
                    face_locations = face_recognition.face_locations(
                        image_array,
                        model="cnn"
                    )
                except:
                    pass
            
            if not face_locations:
                return {'success': False, 'error': 'No se detectó rostro'}
            
            if SMART_CONFIG.get('require_full_face', True):
                face_valid, face_message = verify_face_quality(image_array, face_locations[0])
                if not face_valid:
                    return {'success': False, 'error': f'Rostro inválido: {face_message}'}
            
            current_encoding = face_recognition.face_encodings(
                image_array,
                face_locations,
                num_jitters=2,
                model="large"
            )[0]
            
            current_landmarks = None
            if time.time() - start_time < timeout * 0.8:
                try:
                    current_landmarks = extract_face_landmarks(image_array)
                except:
                    pass
            
            best_match = None
            best_confidence = 0
            all_results = []
            
            employees_with_faces = Employee.objects.filter(
                is_active=True,
                has_face_registered=True
            )
            
            for employee in employees_with_faces:
                if time.time() - start_time > timeout * 0.9:
                    break
                
                try:
                    stored_data = json.loads(employee.face_encoding)
                    
                    if time.time() - start_time > timeout * 0.7:
                        if stored_data.get('encodings'):
                            stored_enc = np.array(stored_data['encodings'][0])
                            distance_val = face_recognition.face_distance([stored_enc], current_encoding)[0]
                            confidence = 1 - distance_val
                            
                            if confidence > 0.45:
                                all_results.append({
                                    'employee': employee,
                                    'confidence': confidence,
                                    'match': confidence > 0.5
                                })
                                
                                if confidence > best_confidence:
                                    best_confidence = confidence
                                    best_match = employee
                    else:
                        is_match, confidence, details = intelligent_face_comparison(
                            stored_data,
                            current_encoding,
                            current_landmarks
                        )
                        
                        all_results.append({
                            'employee': employee,
                            'confidence': confidence,
                            'match': is_match
                        })
                        
                        if is_match and confidence > best_confidence:
                            best_confidence = confidence
                            best_match = employee
                        
                except Exception as e:
                    continue
            
            return {
                'success': True,
                'data': {
                    'best_match': best_match,
                    'best_confidence': best_confidence,
                    'all_results': all_results
                }
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(verify_process)
        
        try:
            result = future.result(timeout=timeout)
            return result.get('data'), result.get('error')
        except FutureTimeoutError:
            future.cancel()
            return None, "Timeout: La verificación excedió los 10 segundos"
        except Exception as e:
            return None, f"Error en verificación: {str(e)}"

@api_view(['POST'])
def create_employee(request):
    """Crear empleado con registro facial"""
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
        
        face_data = process_registration_photos(photos)
        
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
        
        face_data = process_registration_photos(photos)
        
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
        
        verification_result, error = process_verification_with_timeout(
            photo_base64, 
            timeout=SMART_CONFIG['verification_timeout']
        )
        
        elapsed_time = time.time() - start_time
        
        if error == "Timeout: La verificación excedió los 10 segundos":
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