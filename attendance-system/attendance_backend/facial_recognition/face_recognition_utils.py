import face_recognition
import cv2
import numpy as np
import json
import base64
from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageDraw, ImageStat
import io
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from scipy.spatial import distance
from .models import Employee
import logging

logger = logging.getLogger(__name__)

class AdvancedFaceRecognitionService:
    def __init__(self):
        # CONFIGURACIÓN BALANCEADA PARA USO REAL
        # Optimizada para un equilibrio entre precisión y usabilidad práctica
        self.ADVANCED_CONFIG = {
            'min_photos': 5,  # REDUCIDO: Solo 5 fotos para un registro más rápido
            
            # --- UMBRALES BALANCEADOS ---
            # Configuración más permisiva para condiciones del mundo real
            'base_tolerance': 0.50,                  # Tolerancia principal más flexible
            'min_confidence': 0.75,                  # Confianza mínima más realista (era 0.85)
            'strict_confidence_threshold': 0.85,     # Umbral secundario más accesible
            'max_euclidean_distance': 0.52,          # Distancia máxima más permisiva
            'min_cosine_similarity': 0.70,           # Similitud coseno menos exigente
            'max_tolerance': 0.58,                   # Tolerancia máxima aumentada
            
            # --- REQUISITOS DE COINCIDENCIAS MÁS REALISTAS ---
            'min_matches': 1,                        # Solo requiere 1 match bueno (era 2)
            'min_high_quality_matches': 1,           # 1 match de alta calidad
            'required_excellent_matches': 0,         # No requiere matches "perfectos"
            
            # --- CALIDAD DE IMAGEN MÁS PERMISIVA ---
            'quality_threshold': 0.25,               # Acepta imágenes de calidad más baja
            'face_area_threshold': 2000,             # Área de rostro más pequeña permitida
            'min_face_size': 40,                     # Tamaño mínimo de rostro reducido
            
            # --- CONFIGURACIONES DE SEGURIDAD FLEXIBLES ---
            'strict_mode': True,                     # Modo estricto general activado
            'ultra_strict_mode': False,              # Modo ultra estricto DESACTIVADO
            'reject_low_quality_immediately': False, # NO rechazar inmediatamente por calidad baja
            'reject_on_single_bad_match': False,     # NO rechazar por un solo match malo
            'require_multiple_angle_matches': False, # NO requiere múltiples ángulos
            'require_frontal_face': False,           # NO requiere rostro frontal estricto
            'min_quality_for_verification': 0.2,     # Calidad mínima muy permisiva
            
            # --- TIEMPOS Y PROCESAMIENTO ---
            'verification_timeout': 12,              # Tiempo más corto para verificación
            'use_landmarks': True,                   # Usar landmarks para mejor precisión
            'use_environmental_adaptation': True,    # Usar adaptaciones ambientales
            'brightness_adaptation': True,           # Adaptación de brillo
            'contrast_enhancement': True,            # Mejora de contraste
            'blur_detection': True,                  # Detección de desenfoque
            'adaptive_tolerance': True,              # Tolerancia adaptativa
            
            # --- PARÁMETROS FLEXIBLES ADICIONALES ---
            'min_landmark_similarity': 0.65,         # Similitud de landmarks más permisiva
            'consistency_threshold': 0.25,           # Mayor inconsistencia permitida
            'minimum_face_coverage': 0.08,           # Cobertura facial mínima reducida
            'allow_partial_occlusion': True,         # Permitir oclusión parcial (lentes, etc.)
            'lighting_variation_tolerance': True,    # Tolerancia a variaciones de luz
        }

    def detect_image_quality(self, image_array):
        """Detección de calidad más permisiva para uso real"""
        try:
            pil_image = Image.fromarray(image_array)
            
            # Detección de desenfoque más tolerante
            gray = cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            blur_score = min(laplacian_var / 30.0, 1.0)  # Umbral más bajo
            
            # Análisis de brillo más amplio
            stat = ImageStat.Stat(pil_image)
            brightness = sum(stat.mean) / len(stat.mean) / 255.0
            
            # Rangos de brillo muy amplios
            if brightness < 0.15 or brightness > 0.95:
                brightness_score = 0.5
            elif brightness < 0.25 or brightness > 0.85:
                brightness_score = 0.8
            else:
                brightness_score = 1.0
            
            # Análisis de contraste permisivo
            contrast_std = np.std(np.array(pil_image))
            contrast_score = min(contrast_std / 50.0, 1.0)  # Umbral muy bajo
            
            # Detección de ruido tolerante
            noise_level = np.std(gray)
            noise_score = max(0, 1 - (noise_level / 50.0))
            
            # Puntaje general balanceado
            quality_score = (
                blur_score * 0.3 +           # Menor peso al desenfoque
                brightness_score * 0.4 +     # Mayor peso al brillo
                contrast_score * 0.2 +       # Peso moderado al contraste
                noise_score * 0.1           # Menor peso al ruido
            )
            
            # Criterios de aceptación muy permisivos
            is_acceptable = (
                quality_score >= self.ADVANCED_CONFIG['quality_threshold'] and
                blur_score >= 0.2 and           # Mínimo desenfoque muy bajo
                brightness_score >= 0.3 and     # Mínimo brillo bajo
                contrast_score >= 0.15          # Mínimo contraste muy bajo
            )
            
            return {
                'overall_quality': quality_score,
                'blur_score': blur_score,
                'brightness': brightness,
                'brightness_score': brightness_score,
                'contrast': contrast_score,
                'noise_score': noise_score,
                'is_acceptable': is_acceptable
            }
        except Exception:
            return {
                'overall_quality': 0.3,  # Valor por defecto más alto
                'blur_score': 0.3,
                'brightness': 0.5,
                'brightness_score': 0.5,
                'contrast': 0.3,
                'noise_score': 0.3,
                'is_acceptable': True  # Por defecto aceptable
            }

    def is_frontal_face(self, face_landmarks):
        """Verificación de frontalidad muy permisiva"""
        try:
            if not face_landmarks or 'left_eye' not in face_landmarks or 'right_eye' not in face_landmarks:
                return True  # Si no hay landmarks, asumir que está bien
            
            left_eye = np.mean(face_landmarks['left_eye'], axis=0)
            right_eye = np.mean(face_landmarks['right_eye'], axis=0)
            
            eye_y_diff = abs(left_eye[1] - right_eye[1])
            eye_x_distance = abs(right_eye[0] - left_eye[0])
            
            if eye_x_distance == 0:
                return True  # Evitar división por cero, asumir válido
            
            asymmetry_ratio = eye_y_diff / eye_x_distance
            is_frontal = asymmetry_ratio < 0.35  # Muy permisivo con ángulos
            
            return is_frontal
            
        except Exception as e:
            logger.error(f"Error verificando rostro frontal: {e}")
            return True  # En caso de error, asumir válido

    def advanced_face_comparison(self, stored_data, current_encoding, current_landmarks):
        """Comparación facial balanceada para uso real"""
        try:
            stored_encodings = stored_data.get('encodings', [])
            stored_landmarks = stored_data.get('landmarks', [])
            environmental_adaptations = stored_data.get('environmental_adaptations', [])
            
            if not stored_encodings:
                return False, 0.0, "Sin datos de rostro registrados"
            
            # Contadores balanceados
            excellent_matches = 0       # Distancia < 0.35
            high_quality_matches = 0    # Distancia <= base_tolerance
            acceptable_matches = 0      # Dentro de tolerancia máxima
            
            all_scores = []
            all_distances = []
            detailed_matches = []
            
            max_euclidean = self.ADVANCED_CONFIG['max_euclidean_distance']
            min_cosine = self.ADVANCED_CONFIG['min_cosine_similarity']
            base_tolerance = self.ADVANCED_CONFIG['base_tolerance']
            
            for i, stored_enc in enumerate(stored_encodings):
                if stored_enc is None:
                    continue
                
                stored_enc_array = np.array(stored_enc)
                distances = face_recognition.face_distance([stored_enc_array], current_encoding)
                euclidean_dist = distances[0]
                all_distances.append(euclidean_dist)
                
                # Categorización más permisiva
                if euclidean_dist <= 0.35:
                    excellent_matches += 1
                if euclidean_dist <= base_tolerance:
                    high_quality_matches += 1
                if euclidean_dist <= self.ADVANCED_CONFIG['max_tolerance']:
                    acceptable_matches += 1
                
                # Sin rechazo inmediato por distancia alta
                euclidean_score = max(0, 1 - (euclidean_dist / max_euclidean))
                
                # Similitud coseno más permisiva
                try:
                    cosine_sim = 1 - distance.cosine(stored_enc_array, current_encoding)
                    if np.isnan(cosine_sim):
                        cosine_sim = 0.5  # Valor neutro si hay NaN
                    cosine_sim = max(0, cosine_sim)
                except Exception:
                    cosine_sim = 0.5  # Valor neutro por defecto
                
                # Correlación con manejo de errores
                try:
                    correlation = np.corrcoef(stored_enc_array, current_encoding)[0, 1]
                    if np.isnan(correlation):
                        correlation = 0.5
                    correlation = max(0, correlation)
                except Exception:
                    correlation = 0.5
                
                # Cálculo de puntaje balanceado
                combined_score = (
                    euclidean_score * 0.5 +    # Peso principal a distancia euclidiana
                    cosine_sim * 0.3 +         # Peso a similitud coseno
                    correlation * 0.2          # Peso a correlación
                )
                
                # Bonificaciones más generosas
                bonus_applied = 0
                if euclidean_dist <= 0.35:
                    bonus_applied += 0.02
                if euclidean_dist <= base_tolerance and cosine_sim >= 0.75:
                    bonus_applied += 0.015
                if euclidean_dist <= 0.30:  # Bonus por excelente match
                    bonus_applied += 0.03
                
                final_score = min(combined_score + bonus_applied, 1.0)
                all_scores.append(final_score)
                
                detailed_matches.append({
                    'photo_index': i,
                    'euclidean_distance': euclidean_dist,
                    'euclidean_score': euclidean_score,
                    'cosine': cosine_sim,
                    'correlation': correlation,
                    'combined': final_score,
                    'category': 'excellent' if euclidean_dist <= 0.35 else 
                               'high' if euclidean_dist <= base_tolerance else 'acceptable'
                })
            
            # Análisis de adaptaciones ambientales más permisivo
            adaptation_scores = []
            for adaptations in environmental_adaptations:
                for adaptation in adaptations:
                    if 'encoding' in adaptation:
                        try:
                            adapt_enc = np.array(adaptation['encoding'])
                            adapt_distances = face_recognition.face_distance([adapt_enc], current_encoding)
                            adapt_dist = adapt_distances[0]
                            
                            if adapt_dist <= self.ADVANCED_CONFIG['max_tolerance']:
                                adapt_score = max(0, 1 - (adapt_dist / self.ADVANCED_CONFIG['max_tolerance']))
                                if adapt_score >= 0.6:  # Umbral más bajo
                                    adaptation_scores.append(adapt_score)
                                    all_scores.append(adapt_score)
                        except Exception:
                            continue
            
            # Criterios de rechazo más permisivos
            if not all_scores:
                return False, 0.0, "No se encontraron coincidencias válidas"
            
            # Solo verificar requisitos mínimos realmente necesarios
            if acceptable_matches < self.ADVANCED_CONFIG['min_matches']:
                return False, 0.0, f"Insuficientes matches aceptables: {acceptable_matches}"
            
            # Verificación de consistencia más tolerante
            distance_penalty = 0
            if len(all_distances) > 1:
                distance_std = np.std(all_distances)
                if distance_std > self.ADVANCED_CONFIG['consistency_threshold']:
                    distance_penalty = min(distance_std * 0.1, 0.05)  # Penalización mínima
            
            # Verificación de landmarks más flexible
            landmark_bonus = 0
            if current_landmarks is not None and stored_landmarks and self.ADVANCED_CONFIG['use_landmarks']:
                landmark_similarities = []
                current_lm_flat = np.array(current_landmarks).flatten()
                
                for stored_lm_list in stored_landmarks:
                    if stored_lm_list is not None:
                        try:
                            stored_lm_array = np.array(stored_lm_list).flatten()
                            min_len = min(len(current_lm_flat), len(stored_lm_array))
                            
                            if min_len > 60:  # Requisito mínimo de puntos
                                lm_similarity = 1 - distance.cosine(
                                    current_lm_flat[:min_len], 
                                    stored_lm_array[:min_len]
                                )
                                
                                if not np.isnan(lm_similarity) and lm_similarity >= 0.5:
                                    landmark_similarities.append(lm_similarity)
                        except Exception:
                            continue
                
                if landmark_similarities:
                    landmark_score = np.mean(landmark_similarities)
                    if landmark_score >= self.ADVANCED_CONFIG['min_landmark_similarity']:
                        landmark_bonus = min(landmark_score * 0.03, 0.03)
            
            # Cálculo final balanceado
            sorted_scores = sorted(all_scores, reverse=True)
            top_scores = sorted_scores[:min(3, len(sorted_scores))]
            base_confidence = np.mean(top_scores) if top_scores else 0.0
            
            # Bonificaciones por calidad de matches
            quality_bonus = 0
            if excellent_matches > 0:
                quality_bonus += 0.02 * excellent_matches
            if high_quality_matches > 0:
                quality_bonus += 0.01 * high_quality_matches
            
            # Confianza final
            final_confidence = min(
                base_confidence + landmark_bonus + quality_bonus - distance_penalty,
                1.0
            )
            final_confidence = max(0.0, final_confidence)
            
            # Verificación final balanceada
            min_confidence = self.ADVANCED_CONFIG['min_confidence']
            
            is_match = (
                final_confidence >= min_confidence and 
                acceptable_matches >= self.ADVANCED_CONFIG['min_matches']
            )
            
            # NO aplicar modo ultra estricto por defecto
            
            details = (f"Confianza: {final_confidence:.1%}, "
                       f"Matches aceptables: {acceptable_matches}, "
                       f"Alta calidad: {high_quality_matches}, "
                       f"Excelentes: {excellent_matches}, "
                       f"Total: {len(all_scores)}")
            
            return is_match, final_confidence, details
            
        except Exception as e:
            logger.error(f"Error en comparación facial: {e}")
            return False, 0.0, f"Error de comparación: {str(e)}"

    def enhance_image_quality(self, image):
        """Mejoras de imagen optimizadas y eficientes"""
        enhanced_versions = []
        
        try:
            enhanced_versions.append(image)  # Original siempre incluida
            img_array = np.array(image)
            
            # Solo las mejoras más efectivas
            # CLAHE para contraste adaptativo
            try:
                lab = cv2.cvtColor(img_array, cv2.COLOR_RGB2LAB)
                clahe_configs = [(2.5, (8,8))]  # Una sola configuración optimizada
                
                for clip_limit, tile_grid in clahe_configs:
                    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid)
                    lab_copy = lab.copy()
                    lab_copy[:,:,0] = clahe.apply(lab_copy[:,:,0])
                    clahe_enhanced = cv2.cvtColor(lab_copy, cv2.COLOR_LAB2RGB)
                    enhanced_versions.append(Image.fromarray(clahe_enhanced))
            except Exception:
                pass
            
            # Ajuste gamma simple
            try:
                gamma_values = [0.8, 1.3]  # Solo dos valores efectivos
                for gamma in gamma_values:
                    inv_gamma = 1.0 / gamma
                    table = np.array([((i / 255.0) ** inv_gamma) * 255 
                                      for i in np.arange(0, 256)]).astype("uint8")
                    gamma_corrected = cv2.LUT(img_array, table)
                    enhanced_versions.append(Image.fromarray(gamma_corrected))
            except Exception:
                pass
            
            # Mejora de brillo/contraste
            try:
                enhancer = ImageEnhance.Brightness(image)
                enhanced_versions.append(enhancer.enhance(1.1))
                enhancer = ImageEnhance.Contrast(image)
                enhanced_versions.append(enhancer.enhance(1.15))
            except Exception:
                pass
            
            return enhanced_versions[:6]  # Máximo 6 versiones para eficiencia
            
        except Exception as e:
            logger.error(f"Error mejorando imagen: {e}")
            return [image]

    def create_environmental_adaptations(self, image_array, face_location):
        """Adaptaciones ambientales esenciales"""
        adaptations = []
        
        try:
            image = Image.fromarray(image_array)
            
            # Solo condiciones esenciales para el mundo real
            lighting_conditions = [
                {'brightness': 0.8, 'contrast': 1.1, 'name': 'indoor_standard'},
                {'brightness': 1.15, 'contrast': 0.9, 'name': 'outdoor_bright'},
                {'brightness': 0.7, 'contrast': 1.25, 'name': 'low_light'}
            ]
            
            for condition in lighting_conditions:
                try:
                    adapted = ImageEnhance.Brightness(image).enhance(condition['brightness'])
                    adapted = ImageEnhance.Contrast(adapted).enhance(condition['contrast'])
                    
                    adapted_array = np.array(adapted)
                    encoding = face_recognition.face_encodings(
                        adapted_array, [face_location], num_jitters=1, model="large"
                    )
                    
                    if encoding:
                        adaptations.append({
                            'encoding': encoding[0],
                            'condition': condition['name'],
                            'brightness': condition['brightness'],
                            'contrast': condition['contrast']
                        })
                except Exception:
                    continue
            
            return adaptations
            
        except Exception as e:
            logger.error(f"Error creando adaptaciones: {e}")
            return []

    def extract_detailed_landmarks(self, image_array):
        """Extracción de landmarks con validación básica"""
        try:
            face_landmarks_list = face_recognition.face_landmarks(image_array)
            
            if not face_landmarks_list:
                return None
            
            landmarks = face_landmarks_list[0]
            
            # Validación básica de landmarks críticos
            required_features = ['left_eye', 'right_eye', 'nose_bridge']
            for feature in required_features:
                if feature not in landmarks or len(landmarks[feature]) == 0:
                    return None
            
            # Vector de puntos simplificado
            points_vector = []
            for feature in ['chin', 'left_eyebrow', 'right_eyebrow', 'nose_bridge', 
                            'nose_tip', 'left_eye', 'right_eye', 'top_lip', 'bottom_lip']:
                if feature in landmarks:
                    try:
                        for point in landmarks[feature]:
                            points_vector.extend(point)
                    except Exception:
                        continue
            
            if len(points_vector) < 60:  # Mínimo reducido
                return None
            
            return {
                'points_vector': np.array(points_vector),
                'raw_landmarks': landmarks
            }
            
        except Exception as e:
            logger.error(f"Error extrayendo landmarks: {e}")
            return None

    def process_advanced_registration(self, photos_base64):
        """Proceso de registro optimizado para 5 fotos"""
        all_encodings = []
        all_landmarks = []
        all_environmental_adaptations = []
        valid_photos = 0
        failed_reasons = []
        quality_scores = []
        
        print(f"\nIniciando registro balanceado con {len(photos_base64)} fotos...")
        
        for idx, photo_base64 in enumerate(photos_base64):
            try:
                print(f"Procesando foto {idx+1}/{len(photos_base64)}...")
                
                if ',' in photo_base64:
                    photo_base64 = photo_base64.split(',')[1]
                
                image_data = base64.b64decode(photo_base64)
                image = Image.open(io.BytesIO(image_data))
                
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                
                if image.width > 1000 or image.height > 1000:
                    image.thumbnail((1000, 1000), Image.Resampling.LANCZOS)
                
                image_array = np.array(image)
                
                # Verificación de calidad permisiva
                quality_info = self.detect_image_quality(image_array)
                quality_scores.append(quality_info['overall_quality'])
                
                # NO rechazar por calidad baja automáticamente
                if not quality_info['is_acceptable'] and quality_info['overall_quality'] < 0.15:
                    reason = f"Foto {idx+1}: Calidad extremadamente baja ({quality_info['overall_quality']:.1%})"
                    failed_reasons.append(reason)
                    all_encodings.append(None)
                    all_landmarks.append(None)
                    all_environmental_adaptations.append([])
                    continue
                
                # Detección de rostro con múltiples intentos
                enhanced_versions = self.enhance_image_quality(image)
                face_location = None
                best_image_array = None
                
                for enhanced_img in enhanced_versions:
                    enhanced_array = np.array(enhanced_img)
                    
                    try:
                        # Intentar HOG primero (más rápido)
                        face_locations = face_recognition.face_locations(
                            enhanced_array,
                            number_of_times_to_upsample=0,
                            model="hog"
                        )
                        
                        if face_locations:
                            for face_loc in face_locations:
                                top, right, bottom, left = face_loc
                                face_area = (right - left) * (bottom - top)
                                
                                if face_area >= self.ADVANCED_CONFIG['face_area_threshold']:
                                    face_location = face_loc
                                    best_image_array = enhanced_array
                                    break
                        
                        if face_location:
                            break
                            
                    except Exception:
                        continue
                    
                    # Si HOG falla, intentar CNN
                    try:
                        face_locations = face_recognition.face_locations(
                            enhanced_array, model="cnn"
                        )
                        if face_locations:
                            face_location = face_locations[0]
                            best_image_array = enhanced_array
                            break
                    except Exception:
                        continue
                
                if not face_location:
                    reason = f"Foto {idx+1}: No se detectó rostro válido"
                    failed_reasons.append(reason)
                    all_encodings.append(None)
                    all_landmarks.append(None)
                    all_environmental_adaptations.append([])
                    continue
                
                # Extracción de características con múltiples intentos
                encodings = None
                for num_jitters in [8, 5, 3]:  # Reducido para eficiencia
                    try:
                        encodings = face_recognition.face_encodings(
                            best_image_array,
                            [face_location],
                            num_jitters=num_jitters,
                            model="large"
                        )
                        if encodings:
                            break
                    except Exception:
                        continue
                
                if encodings:
                    all_encodings.append(encodings[0].tolist())
                    valid_photos += 1
                    print(f"   Características extraídas (calidad: {quality_info['overall_quality']:.2f})")
                else:
                    reason = f"Foto {idx+1}: Fallo en extracción de características"
                    failed_reasons.append(reason)
                    all_encodings.append(None)
                
                # Landmarks opcionales
                if self.ADVANCED_CONFIG['use_landmarks']:
                    landmarks_data = self.extract_detailed_landmarks(best_image_array)
                    if landmarks_data:
                        all_landmarks.append(landmarks_data.get('points_vector').tolist())
                    else:
                        all_landmarks.append(None)
                else:
                    all_landmarks.append(None)
                
                # Adaptaciones ambientales si están activadas
                if encodings and self.ADVANCED_CONFIG['use_environmental_adaptation']:
                    adaptations = self.create_environmental_adaptations(best_image_array, face_location)
                    if adaptations:
                        all_environmental_adaptations.append([
                            {
                                'encoding': adapt['encoding'].tolist(),
                                'condition': adapt['condition'],
                                'brightness': adapt['brightness'],
                                'contrast': adapt['contrast']
                            } for adapt in adaptations
                        ])
                    else:
                        all_environmental_adaptations.append([])
                else:
                    all_environmental_adaptations.append([])
                    
            except Exception as e:
                print(f"   Error en foto {idx+1}: {str(e)}")
                failed_reasons.append(f"Foto {idx+1}: Error - {str(e)}")
                all_encodings.append(None)
                all_landmarks.append(None)
                all_environmental_adaptations.append([])
        
        # Validación final más permisiva
        valid_encodings = [enc for enc in all_encodings if enc is not None]
        valid_landmarks = [lm for lm in all_landmarks if lm is not None]
        valid_adaptations = [ada for ada in all_environmental_adaptations if ada and len(ada) > 0]
        
        average_quality = np.mean(quality_scores) if quality_scores else 0.0
        
        print(f"Registro completado: {len(valid_encodings)} fotos válidas de {len(photos_base64)}")
        
        # Requisito mínimo más flexible: al menos 3 de 5 fotos
        min_required = max(3, self.ADVANCED_CONFIG['min_photos'] - 2)
        
        if len(valid_encodings) < min_required:
            return {
                'success': False,
                'error': f"Se necesitan al menos {min_required} fotos válidas. Obtenidas: {len(valid_encodings)}",
                'encodings': [], 'landmarks': [], 'environmental_adaptations': [],
                'valid_photos': len(valid_encodings), 'total_photos': len(photos_base64),
                'failed_reasons': failed_reasons, 'average_quality': average_quality
            }

        return {
            'success': True,
            'encodings': valid_encodings,
            'landmarks': valid_landmarks,
            'environmental_adaptations': valid_adaptations,
            'valid_photos': len(valid_encodings),
            'total_photos': len(photos_base64),
            'failed_reasons': failed_reasons,
            'average_quality': average_quality,
            'quality_scores': quality_scores
        }

    def advanced_verify(self, photo_base64):
        """Verificación balanceada y eficiente"""
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
                
                if image.width > 1200 or image.height > 1200:
                    image.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
                
                image_array = np.array(image)
                
                # Verificación de calidad más permisiva
                quality_info = self.detect_image_quality(image_array)
                
                # Solo rechazar si la calidad es extremadamente baja
                if quality_info['overall_quality'] < self.ADVANCED_CONFIG['min_quality_for_verification']:
                    return {
                        'success': False,
                        'error': f'Calidad de imagen demasiado baja: {quality_info["overall_quality"]:.1%}'
                    }
                
                # Detección de rostro con múltiples métodos
                enhanced_versions = self.enhance_image_quality(image)
                face_location = None
                best_image_array = None
                
                for enhanced_img in enhanced_versions:
                    if time.time() - start_time > self.ADVANCED_CONFIG['verification_timeout'] * 0.6:
                        break
                    
                    enhanced_array = np.array(enhanced_img)
                    
                    # Intentar HOG primero (más rápido)
                    try:
                        face_locations = face_recognition.face_locations(
                            enhanced_array,
                            number_of_times_to_upsample=0,
                            model="hog"
                        )
                        
                        if face_locations:
                            for face_loc in face_locations:
                                top, right, bottom, left = face_loc
                                face_area = (right - left) * (bottom - top)
                                
                                if face_area >= self.ADVANCED_CONFIG['face_area_threshold']:
                                    face_location = face_loc
                                    best_image_array = enhanced_array
                                    break
                        
                        if face_location:
                            break
                            
                    except Exception:
                        continue
                    
                    # Si HOG falla, intentar CNN como respaldo
                    try:
                        face_locations = face_recognition.face_locations(
                            enhanced_array, model="cnn"
                        )
                        if face_locations:
                            face_location = face_locations[0]
                            best_image_array = enhanced_array
                            break
                    except Exception:
                        continue
                
                if not face_location:
                    return {
                        'success': False,
                        'error': 'No se detectó rostro válido - Asegúrate de que esté bien iluminado y sea visible'
                    }
                
                # Extracción de características con timeouts
                current_encoding = face_recognition.face_encodings(
                    best_image_array,
                    [face_location],
                    num_jitters=3,  # Reducido para velocidad
                    model="large"
                )
                
                if not current_encoding:
                    return {
                        'success': False,
                        'error': 'No se pudieron extraer características faciales confiables'
                    }
                
                current_encoding = current_encoding[0]
                
                # Extraer landmarks si hay tiempo
                current_landmarks_vector = None
                if (self.ADVANCED_CONFIG['use_landmarks'] and 
                    time.time() - start_time < self.ADVANCED_CONFIG['verification_timeout'] * 0.7):
                    try:
                        landmark_data = self.extract_detailed_landmarks(best_image_array)
                        if landmark_data:
                            current_landmarks_vector = landmark_data['points_vector']
                    except Exception:
                        pass
                
                # Comparación con empleados registrados
                best_match_data = None
                best_confidence = 0
                all_results = []
                
                employees_with_faces = Employee.objects.filter(
                    is_active=True,
                    has_face_registered=True
                ).select_related()
                
                for employee in employees_with_faces:
                    if time.time() - start_time > self.ADVANCED_CONFIG['verification_timeout'] * 0.9:
                        break
                    
                    try:
                        stored_encodings_json = employee.face_encoding
                        if not stored_encodings_json:
                            continue
                        
                        stored_data = json.loads(stored_encodings_json)
                        
                        is_match, confidence, details = self.advanced_face_comparison(
                            stored_data,
                            current_encoding,
                            current_landmarks_vector
                        )
                        
                        all_results.append({
                            'employee_id': employee.id,
                            'employee_name': employee.name,
                            'confidence': confidence,
                            'match': is_match,
                            'details': details
                        })
                        
                        if is_match and confidence > best_confidence:
                            best_confidence = confidence
                            best_match_data = {
                                'id': employee.id,
                                'name': employee.name,
                                'employee_id': employee.employee_id,
                                'rut': employee.rut,
                                'department': employee.department,
                            }
                            
                    except Exception as e:
                        logger.error(f"Error comparando con {employee.name}: {e}")
                        continue
                
                # Resultado final
                elapsed_time = time.time() - start_time
                
                return {
                    'success': True,
                    'data': {
                        'best_match': best_match_data,
                        'best_confidence': best_confidence,
                        'all_results': all_results,
                        'quality_info': quality_info,
                        'threshold_used': self.ADVANCED_CONFIG['min_confidence'],
                        'elapsed_time': elapsed_time
                    }
                }
                
            except Exception as e:
                logger.error(f"Error en verificación: {e}")
                return {'success': False, 'error': str(e)}
        
        # Ejecutar con timeout
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(verify_process)
            
            try:
                result = future.result(timeout=self.ADVANCED_CONFIG['verification_timeout'])
                if result.get('success'):
                    return result.get('data'), None
                else:
                    return None, result.get('error')
            except FutureTimeoutError:
                future.cancel()
                return None, "TIMEOUT: Verificación cancelada por tiempo excedido"
            except Exception as e:
                logger.error(f"Error en executor: {e}")
                return None, f"Error durante la verificación: {str(e)}"