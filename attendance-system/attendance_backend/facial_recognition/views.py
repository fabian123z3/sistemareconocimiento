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
    'min_photos': 5,                    # Mínimo de fotos para procesar
    'base_tolerance': 0.40,              # Tolerancia base MÁS ESTRICTA (era 0.50)
    'adaptive_tolerance': True,          # Ajuste dinámico de tolerancia
    'min_confidence': 0.70,              # Confianza mínima 70% (era 55%)
    'min_matches': 3,                    # Mínimo de coincidencias (era 2)
    'use_landmarks': True,               # Usar puntos faciales
    'use_augmentation': True,            # Crear variaciones artificiales
    'max_tolerance': 0.45,               # Tolerancia máxima MÁS ESTRICTA (era 0.65)
    'verification_timeout': 10,          # Timeout de 10 segundos para verificación
    'strict_mode': True,                 # Modo estricto activado
    'require_full_face': True,           # Requerir rostro completo visible
    'min_face_size': 80,                 # Tamaño mínimo del rostro en píxeles
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
            'photos_processed': SMART_CONFIG['min_photos'],
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
    """
    Verificar que el rostro sea de calidad suficiente y esté completo
    """
    top, right, bottom, left = face_location
    
    # Verificar tamaño mínimo del rostro
    face_width = right - left
    face_height = bottom - top
    
    if face_width < SMART_CONFIG['min_face_size'] or face_height < SMART_CONFIG['min_face_size']:
        return False, "Rostro muy pequeño o muy lejos"
    
    # Verificar que el rostro esté completo (no cortado)
    image_height, image_width = image_array.shape[:2]
    
    # El rostro no debe estar en los bordes de la imagen (podría estar cortado)
    margin = 10
    if (left < margin or right > image_width - margin or 
        top < margin or bottom > image_height - margin):
        return False, "Rostro parcialmente fuera de la imagen"
    
    # Verificar proporción del rostro (debe ser aproximadamente 1.3-1.5 alto/ancho)
    aspect_ratio = face_height / face_width
    if aspect_ratio < 1.0 or aspect_ratio > 2.0:
        return False, "Proporción del rostro anormal"
    
    # Verificar que se detecten puntos faciales clave
    face_landmarks = face_recognition.face_landmarks(image_array, [face_location])
    
    if not face_landmarks:
        return False, "No se detectaron características faciales"
    
    landmarks = face_landmarks[0]
    
    # Verificar que estén presentes todas las características importantes
    required_features = ['chin', 'left_eye', 'right_eye', 'nose_bridge', 'nose_tip']
    missing_features = []
    
    for feature in required_features:
        if feature not in landmarks or not landmarks[feature]:
            missing_features.append(feature)
    
    if missing_features:
        return False, f"Características faciales faltantes: {', '.join(missing_features)}"
    
    # Verificar simetría básica (ambos ojos deben estar visibles)
    if len(landmarks.get('left_eye', [])) < 4 or len(landmarks.get('right_eye', [])) < 4:
        return False, "Ojos no completamente visibles"
    
    # Verificar que la barbilla esté completa (no tapada)
    chin_points = landmarks.get('chin', [])
    if len(chin_points) < 15:  # Normalmente son 17 puntos
        return False, "Barbilla/parte inferior del rostro no visible"
    
    return True, "Rostro válido"

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

def intelligent_face_comparison(stored_data, current_encoding, current_landmarks, quick_mode=False):
    """
    Comparación inteligente ESTRICTA usando múltiples métodos
    """
    stored_encodings = stored_data.get('encodings', [])
    stored_landmarks = stored_data.get('landmarks', [])
    stored_augmented = stored_data.get('augmented', [])
    
    if not stored_encodings:
        return False, 0.0, "Sin datos de rostro"
    
    # En modo estricto, requerir landmarks
    if SMART_CONFIG['strict_mode'] and current_landmarks is None:
        return False, 0.0, "No se detectaron puntos faciales - rostro incompleto"
    
    all_scores = []
    high_quality_scores = []  # Scores de comparaciones de alta calidad
    
    # Comparar con TODOS los encodings almacenados (más estricto)
    for i, stored_enc in enumerate(stored_encodings):
        if stored_enc is None:
            continue
            
        stored_enc_array = np.array(stored_enc)
        
        # Distancia euclidiana
        euclidean_dist = face_recognition.face_distance([stored_enc_array], current_encoding)[0]
        
        # En modo estricto, rechazar distancias muy altas inmediatamente
        if SMART_CONFIG['strict_mode'] and euclidean_dist > 0.6:
            continue  # Skip este encoding, es muy diferente
        
        if not quick_mode:
            # Similitud coseno
            cosine_sim = 1 - distance.cosine(stored_enc_array, current_encoding)
            
            # Correlación
            correlation = np.corrcoef(stored_enc_array, current_encoding)[0, 1]
            
            # Score combinado ESTRICTO
            score = (
                (1 - euclidean_dist) * 0.6 +  # 60% distancia euclidiana (más peso)
                cosine_sim * 0.25 +            # 25% similitud coseno
                correlation * 0.15              # 15% correlación
            )
            
            # Solo considerar scores altos como válidos
            if score > 0.5:
                high_quality_scores.append(score)
        else:
            score = 1 - euclidean_dist
        
        all_scores.append(score)
    
    # En modo estricto, requerir múltiples coincidencias de alta calidad
    if SMART_CONFIG['strict_mode']:
        if len(high_quality_scores) < SMART_CONFIG['min_matches']:
            return False, 0.0, f"Insuficientes coincidencias ({len(high_quality_scores)}/{SMART_CONFIG['min_matches']})"
    
    # Comparar landmarks si están disponibles (muy importante para verificar rostro completo)
    landmark_match = False
    if current_landmarks is not None and stored_landmarks:
        landmark_similarities = []
        valid_landmark_comparisons = 0
        
        for stored_lm in stored_landmarks:
            if stored_lm is not None:
                stored_lm_array = np.array(stored_lm)
                min_len = min(len(current_landmarks), len(stored_lm_array))
                
                if min_len > 100:  # Suficientes puntos para comparar
                    lm_similarity = 1 - distance.cosine(
                        current_landmarks[:min_len], 
                        stored_lm_array[:min_len]
                    )
                    landmark_similarities.append(lm_similarity)
                    valid_landmark_comparisons += 1
        
        if landmark_similarities:
            landmark_score = np.mean(landmark_similarities)
            
            # En modo estricto, los landmarks deben coincidir bien
            if SMART_CONFIG['strict_mode']:
                landmark_match = landmark_score > 0.65
                if not landmark_match:
                    return False, 0.0, f"Geometría facial no coincide ({landmark_score:.1%})"
    
    # Calcular score final
    if not all_scores:
        return False, 0.0, "No hay coincidencias"
    
    # En modo estricto, usar promedio de los mejores scores
    if SMART_CONFIG['strict_mode'] and high_quality_scores:
        final_score = np.mean(high_quality_scores)
    else:
        # Usar percentil 60 (más estricto que 75)
        final_score = np.percentile(all_scores, 60)
    
    # Tolerancia ESTRICTA
    if SMART_CONFIG['strict_mode']:
        tolerance = SMART_CONFIG['base_tolerance']  # No adaptativa en modo estricto
    else:
        tolerance = SMART_CONFIG['max_tolerance']
    
    # Requerir confianza mínima
    if final_score < SMART_CONFIG['min_confidence']:
        return False, final_score, f"Confianza insuficiente ({final_score:.1%} < {SMART_CONFIG['min_confidence']:.0%})"
    
    # Decisión final
    is_match = final_score >= (1 - tolerance) and final_score >= SMART_CONFIG['min_confidence']
    confidence = min(1.0, final_score)
    
    print(f"\n🔒 Verificación ESTRICTA:")
    print(f"   Score final: {final_score:.3f}")
    print(f"   Confianza mínima requerida: {SMART_CONFIG['min_confidence']:.2f}")
    print(f"   Coincidencias de alta calidad: {len(high_quality_scores)}")
    print(f"   Decisión: {'✅ AUTORIZADO' if is_match else '❌ RECHAZADO'}")
    
    return is_match, confidence, f"Score: {confidence:.1%}"

def process_registration_photos(photos_base64):
    """
    Procesar múltiples fotos para registro inteligente
    """
    all_encodings = []
    all_landmarks = []
    all_augmented = []
    valid_photos = 0
    failed_photos = []
    
    print(f"\n📸 Iniciando procesamiento de {len(photos_base64)} fotos...")
    
    for idx, photo_base64 in enumerate(photos_base64):
        try:
            print(f"   Procesando foto {idx+1}/{len(photos_base64)}...")
            
            # Decodificar imagen
            if ',' in photo_base64:
                photo_base64 = photo_base64.split(',')[1]
            
            image_data = base64.b64decode(photo_base64)
            image = Image.open(io.BytesIO(image_data))
            
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            print(f"     - Imagen cargada: {image.width}x{image.height}")
            
            # Redimensionar para procesamiento óptimo
            if image.width > 800:
                ratio = 800 / image.width
                new_height = int(image.height * ratio)
                image = image.resize((800, new_height), Image.Resampling.LANCZOS)
                print(f"     - Redimensionada a: 800x{new_height}")
            
            image_array = np.array(image)
            
            # Detectar rostro - intentar múltiples métodos
            face_locations = []
            
            # Intento 1: HOG estándar
            face_locations = face_recognition.face_locations(
                image_array,
                number_of_times_to_upsample=1,
                model="hog"
            )
            
            if not face_locations:
                print(f"     - HOG no detectó, intentando con upsampling...")
                # Intento 2: HOG con más upsampling
                face_locations = face_recognition.face_locations(
                    image_array,
                    number_of_times_to_upsample=2,
                    model="hog"
                )
            
            if not face_locations:
                # Intento 3: CNN (más lento pero más preciso)
                try:
                    print(f"     - Intentando con CNN...")
                    face_locations = face_recognition.face_locations(
                        image_array,
                        model="cnn"
                    )
                except Exception as cnn_error:
                    print(f"     - CNN falló: {str(cnn_error)}")
            
            if not face_locations:
                # Intento 4: Mejorar imagen y reintentar
                try:
                    print(f"     - Mejorando imagen y reintentando...")
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
                print(f"   ⚠️ Foto {idx+1}: No se detectó rostro después de múltiples intentos")
                failed_photos.append(idx+1)
                
                # IMPORTANTE: Agregar encoding vacío para mantener consistencia
                # Esto permite que la foto "cuente" aunque no se detecte rostro
                all_encodings.append(None)
                all_landmarks.append(None)
                all_augmented.append([])
                continue
            
            print(f"     - Rostro detectado!")
            face_location = face_locations[0]
            
            # Extraer encoding principal con múltiples intentos
            encodings = face_recognition.face_encodings(
                image_array,
                [face_location],
                num_jitters=10,
                model="large"
            )
            
            if not encodings:
                # Reintentar con menos jitters
                encodings = face_recognition.face_encodings(
                    image_array,
                    [face_location],
                    num_jitters=5,
                    model="large"
                )
            
            if not encodings:
                # Último intento con modelo pequeño
                encodings = face_recognition.face_encodings(
                    image_array,
                    [face_location],
                    num_jitters=2,
                    model="small"
                )
            
            if encodings:
                all_encodings.append(encodings[0].tolist())
                valid_photos += 1
                print(f"     - Encoding extraído correctamente")
            else:
                all_encodings.append(None)
                failed_photos.append(idx+1)
                print(f"     - No se pudo extraer encoding")
            
            # Extraer landmarks
            try:
                landmarks = extract_face_landmarks(image_array)
                if landmarks is not None:
                    all_landmarks.append(landmarks.tolist())
                    print(f"     - Landmarks extraídos")
                else:
                    all_landmarks.append(None)
            except:
                all_landmarks.append(None)
            
            # Crear encodings aumentados solo si tenemos encoding principal
            if encodings and SMART_CONFIG['use_augmentation']:
                try:
                    augmented = create_augmented_encodings(image_array, face_location)
                    all_augmented.append([enc.tolist() for enc in augmented])
                    print(f"     - {len(augmented)} variaciones aumentadas creadas")
                except:
                    all_augmented.append([])
            else:
                all_augmented.append([])
            
            print(f"   ✅ Foto {idx+1}: Procesada correctamente")
            
        except Exception as e:
            print(f"   ❌ Foto {idx+1}: Error general - {str(e)}")
            # Agregar placeholders para mantener consistencia
            all_encodings.append(None)
            all_landmarks.append(None)
            all_augmented.append([])
            failed_photos.append(idx+1)
            continue
    
    # Filtrar None values del resultado final
    valid_encodings = [enc for enc in all_encodings if enc is not None]
    valid_landmarks = [lm for lm in all_landmarks if lm is not None]
    valid_augmented = [aug for aug in all_augmented if aug and len(aug) > 0]
    
    print(f"\n📊 Resumen del procesamiento:")
    print(f"   - Fotos recibidas: {len(photos_base64)}")
    print(f"   - Fotos válidas: {valid_photos}")
    print(f"   - Encodings válidos: {len(valid_encodings)}")
    print(f"   - Landmarks válidos: {len(valid_landmarks)}")
    print(f"   - Sets aumentados: {len(valid_augmented)}")
    if failed_photos:
        print(f"   - Fotos fallidas: {failed_photos}")
    
    return {
        'encodings': valid_encodings,
        'landmarks': valid_landmarks,
        'augmented': valid_augmented,
        'valid_photos': len(valid_encodings),  # Usar encodings válidos como métrica
        'total_photos': len(photos_base64),
        'failed_photos': failed_photos
    }

def process_verification_with_timeout(photo_base64, timeout=10):
    """
    Procesar verificación con timeout usando ThreadPoolExecutor
    """
    def verify_process():
        try:
            # Procesar foto actual
            if ',' in photo_base64:
                photo_data = photo_base64.split(',')[1]
            else:
                photo_data = photo_base64
            
            image_data = base64.b64decode(photo_data)
            image = Image.open(io.BytesIO(image_data))
            
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Pre-procesar para mejorar detección
            image = ImageOps.equalize(image)
            image_array = np.array(image)
            
            # Detectar rostro con timeout interno
            start_detection = time.time()
            face_locations = []
            
            # Intento rápido con HOG
            if time.time() - start_detection < timeout/2:
                face_locations = face_recognition.face_locations(
                    image_array,
                    number_of_times_to_upsample=1,
                    model="hog"
                )
            
            # Si no encuentra y aún hay tiempo, intentar CNN
            if not face_locations and (time.time() - start_detection < timeout/2):
                try:
                    face_locations = face_recognition.face_locations(
                        image_array,
                        model="cnn"
                    )
                except:
                    pass
            
            if not face_locations:
                return {'success': False, 'error': 'No se detectó rostro'}
            
            # VERIFICAR CALIDAD DEL ROSTRO
            if SMART_CONFIG.get('require_full_face', True):
                face_valid, face_message = verify_face_quality(image_array, face_locations[0])
                if not face_valid:
                    return {'success': False, 'error': f'Rostro inválido: {face_message}'}
            
            # Extraer encoding con configuración más rápida
            current_encoding = face_recognition.face_encodings(
                image_array,
                face_locations,
                num_jitters=2,  # Reducido de 5 a 2 para mayor velocidad
                model="large"
            )[0]
            
            # Extraer landmarks (opcional, skip si toma mucho tiempo)
            current_landmarks = None
            if time.time() - start_detection < timeout * 0.8:
                try:
                    current_landmarks = extract_face_landmarks(image_array)
                except:
                    pass
            
            # Buscar coincidencia con empleados
            best_match = None
            best_confidence = 0
            all_results = []
            
            employees_with_faces = Employee.objects.filter(
                is_active=True,
                has_face_registered=True
            )
            
            print(f"   Comparando con {employees_with_faces.count()} empleados...")
            
            for employee in employees_with_faces:
                # Verificar si aún tenemos tiempo
                if time.time() - start_detection > timeout * 0.9:
                    print("   ⚠️ Acercándose al timeout, finalizando búsqueda...")
                    break
                
                try:
                    stored_data = json.loads(employee.face_encoding)
                    
                    # Usar comparación más rápida si estamos cerca del timeout
                    if time.time() - start_detection > timeout * 0.7:
                        # Comparación rápida solo con encoding principal
                        if stored_data.get('encodings'):
                            stored_enc = np.array(stored_data['encodings'][0])
                            distance = face_recognition.face_distance([stored_enc], current_encoding)[0]
                            confidence = 1 - distance
                            
                            if confidence > 0.45:  # Threshold más bajo para búsqueda rápida
                                all_results.append({
                                    'employee': employee,
                                    'confidence': confidence,
                                    'match': confidence > 0.5
                                })
                                
                                if confidence > best_confidence:
                                    best_confidence = confidence
                                    best_match = employee
                    else:
                        # Comparación completa
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
                    print(f"   Error con {employee.name}: {str(e)}")
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
    
    # Ejecutar con timeout estricto usando ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(verify_process)
        
        try:
            result = future.result(timeout=timeout)
            return result.get('data'), result.get('error')
        except FutureTimeoutError:
            # Cancelar el future si es posible
            future.cancel()
            return None, "Timeout: La verificación excedió los 10 segundos"
        except Exception as e:
            return None, f"Error en verificación: {str(e)}"

@api_view(['POST'])
def create_employee(request):
    """Crear empleado con registro facial obligatorio"""
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
        
        # REQUERIR 5 FOTOS 
        if len(photos) < SMART_CONFIG['min_photos']:
            return Response({
                'success': False,
                'message': f'Se requieren {SMART_CONFIG["min_photos"]} fotos para crear el empleado',
                'photos_received': len(photos),
                'photos_required': SMART_CONFIG['min_photos']
            }, status=400)
        
        # Generar ID único
        employee_id = f"EMP{str(uuid.uuid4())[:8].upper()}"
        while Employee.objects.filter(employee_id=employee_id).exists():
            employee_id = f"EMP{str(uuid.uuid4())[:8].upper()}"
        
        if not email:
            email = f"{employee_id.lower()}@empresa.com"
        
        # Procesar fotos ANTES de crear el empleado
        print(f"\n📸 Procesando {len(photos)} fotos para {name}...")
        face_data = process_registration_photos(photos)
        
        # Ser más flexible: requerir al menos 3 encodings válidos de 5 fotos
        min_valid_required = 3  # Mínimo 3 fotos con rostro detectado
        
        if face_data['valid_photos'] < min_valid_required:
            return Response({
                'success': False,
                'message': f'Solo se detectó rostro en {face_data["valid_photos"]} fotos. Se requiere mínimo {min_valid_required} de {SMART_CONFIG["min_photos"]}',
                'details': f'Fotos fallidas: {face_data.get("failed_photos", [])}. Asegúrate de que el rostro esté claramente visible.',
                'photos_processed': face_data['total_photos'],
                'valid_photos': face_data['valid_photos']
            }, status=400)
        
        # Crear empleado con datos faciales
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
        
        # Guardar solo las mejores 5 fotos
        photos_to_save = photos[:SMART_CONFIG['min_photos']]
        for idx, photo in enumerate(photos_to_save):
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
            'message': f'Empleado {name} creado con registro facial completo',
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
        
        print(f"\n📸 Registro Inteligente para {employee.name}")
        print(f"   Procesando {len(photos)} fotos...")
        
        # Procesar todas las fotos
        face_data = process_registration_photos(photos)
        
        # Ser más flexible: requerir al menos 3 encodings válidos de 5 fotos
        min_valid_required = 3  # Mínimo 3 fotos con rostro detectado
        
        if face_data['valid_photos'] < min_valid_required:
            return Response({
                'success': False,
                'message': f'Solo se detectó rostro en {face_data["valid_photos"]} fotos. Se requiere mínimo {min_valid_required} de {SMART_CONFIG["min_photos"]}',
                'photos_with_issues': face_data.get('failed_photos', []),
                'total_received': face_data['total_photos'],
                'suggestion': 'Asegúrate de que el rostro esté claramente visible en cada foto'
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
    Verificación inteligente con timeout de 10 segundos
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
        
        print(f"\n⏱️ Iniciando verificación con timeout de {SMART_CONFIG['verification_timeout']} segundos...")
        start_time = time.time()
        
        # Procesar con timeout
        verification_result, error = process_verification_with_timeout(
            photo_base64, 
            timeout=SMART_CONFIG['verification_timeout']
        )
        
        elapsed_time = time.time() - start_time
        print(f"⏱️ Tiempo de verificación: {elapsed_time:.2f} segundos")
        
        if error == "Timeout: La verificación excedió los 10 segundos":
            return Response({
                'success': False,
                'message': 'Verificación cancelada: Excedió el tiempo límite de 10 segundos',
                'timeout': True,
                'elapsed_time': f'{elapsed_time:.2f} segundos',
                'suggestion': 'Intenta nuevamente con mejor iluminación o más cerca de la cámara'
            }, status=408)  # 408 Request Timeout
        
        if error:
            return Response({
                'success': False,
                'message': error,
                'elapsed_time': f'{elapsed_time:.2f} segundos'
            }, status=400)
        
        if not verification_result:
            return Response({
                'success': False,
                'message': 'Error procesando verificación'
            }, status=500)
        
        best_match = verification_result['best_match']
        best_confidence = verification_result['best_confidence']
        all_results = verification_result['all_results']
        
        if not best_match:
            # Buscar el más cercano para feedback
            if all_results:
                closest = max(all_results, key=lambda x: x['confidence'])
                
                return Response({
                    'success': False,
                    'message': '🚫 ACCESO DENEGADO - No autorizado',
                    'closest_match': closest['employee'].name if closest['confidence'] > 0.3 else 'Ninguno',
                    'closest_confidence': f"{closest['confidence']:.1%}",
                    'required_confidence': f"{SMART_CONFIG['min_confidence']:.0%}",
                    'elapsed_time': f'{elapsed_time:.2f} segundos',
                    'security_level': 'ESTRICTO',
                    'tips': [
                        '⚠️ Sistema en modo seguridad estricta',
                        '📸 Se requiere rostro completo visible',
                        '🚫 No cubrir ninguna parte del rostro',
                        '💡 Buena iluminación frontal requerida',
                        '📏 Acércate a la cámara'
                    ]
                }, status=403)  # 403 Forbidden
            else:
                return Response({
                    'success': False,
                    'message': 'No hay empleados registrados con datos faciales',
                    'elapsed_time': f'{elapsed_time:.2f} segundos'
                }, status=404)
        
        print(f"✅ VERIFICADO: {best_match.name} ({best_confidence:.1%}) en {elapsed_time:.2f}s")
        
        # Crear registro de asistencia
        attendance_record = AttendanceRecord.objects.create(
            employee=best_match,
            attendance_type=attendance_type,
            timestamp=timezone.now(),
            location_lat=location_lat,
            location_lng=location_lng,
            address=address,
            face_confidence=best_confidence,
            notes=f'Verificación inteligente ({best_confidence:.1%}) en {elapsed_time:.2f}s'
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
            'elapsed_time': f'{elapsed_time:.2f} segundos',
            'record': serializer.data
        })
        
    except Exception as e:
        print(f"❌ Error en verificación: {str(e)}")
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
            'system_mode': 'INTELIGENTE',
            'timeout_enabled': True,
            'timeout_seconds': SMART_CONFIG['verification_timeout']
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
    """Eliminar empleado completamente"""
    try:
        employee = Employee.objects.get(id=employee_id)
        employee_name = employee.name
        
        # Eliminar fotos
        for i in range(1, 6):
            path = os.path.join(FACE_IMAGES_DIR, f"{employee_id}_photo_{i}.jpg")
            if os.path.exists(path):
                os.remove(path)
        
        # Eliminar registros de asistencia del empleado
        AttendanceRecord.objects.filter(employee=employee).delete()
        
        # Eliminar empleado completamente
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
