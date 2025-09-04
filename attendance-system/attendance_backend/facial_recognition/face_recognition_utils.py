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
        # **CONFIGURACIÓN MÁS ESTRICTA PARA EVITAR FALSOS POSITIVOS**
        self.ADVANCED_CONFIG = {
            'min_photos': 8,
            'base_tolerance': 0.45,  # ✅ MÁS ESTRICTO (era 0.50)
            'adaptive_tolerance': True,
            'min_confidence': 0.85,  # ✅ MUCHO MÁS ESTRICTO (era 0.75)
            'strict_confidence_threshold': 0.90,  # ✅ NUEVO: Umbral ultra estricto
            'min_matches': 2,  # ✅ MÁS ESTRICTO: Requiere al menos 2 coincidencias buenas
            'use_landmarks': True,
            'use_environmental_adaptation': True,
            'max_tolerance': 0.60,  # ✅ MÁS ESTRICTO (era 0.76)
            'verification_timeout': 15,
            'strict_mode': True,  # ✅ ACTIVAR MODO ESTRICTO
            'min_face_size': 50,  # ✅ MÁS ESTRICTO (era 40)
            'brightness_adaptation': True,
            'contrast_enhancement': True,
            'blur_detection': True,
            'quality_threshold': 0.3,  # ✅ MÁS ESTRICTO (era 0.1)
            
            # ✅ NUEVOS PARÁMETROS DE SEGURIDAD
            'require_multiple_angle_matches': True,
            'min_quality_for_verification': 0.4,
            'max_euclidean_distance': 0.45,  # Distancia máxima permitida
            'min_cosine_similarity': 0.7,   # Similitud coseno mínima
            'face_area_threshold': 2500,    # Área mínima del rostro en píxeles
        }

    def detect_image_quality(self, image_array):
        """Detecta calidad - AHORA MÁS ESTRICTO"""
        try:
            pil_image = Image.fromarray(image_array)
            
            # Detección de desenfoque MÁS ESTRICTA
            gray = cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            blur_score = min(laplacian_var / 50.0, 1.0)  # ✅ MÁS EXIGENTE
            
            # Análisis de brillo MÁS ESTRICTO
            stat = ImageStat.Stat(pil_image)
            brightness = sum(stat.mean) / len(stat.mean) / 255.0
            # Penalizar imágenes muy oscuras o muy claras
            if brightness < 0.2 or brightness > 0.9:
                brightness_score = 0.3
            elif brightness < 0.3 or brightness > 0.8:
                brightness_score = 0.6
            else:
                brightness_score = 1.0
            
            # Análisis de contraste MÁS EXIGENTE
            contrast_std = np.std(np.array(pil_image))
            contrast_score = min(contrast_std / 80.0, 1.0)  # ✅ MÁS EXIGENTE
            
            # Puntaje general MÁS ESTRICTO
            quality_score = (blur_score * 0.4 + brightness_score * 0.3 + contrast_score * 0.3)
            
            # ✅ RECHAZO AUTOMÁTICO SI LA CALIDAD ES MUY BAJA
            is_acceptable = quality_score >= self.ADVANCED_CONFIG['quality_threshold']
            
            return {
                'overall_quality': quality_score,
                'blur_score': blur_score,
                'brightness': brightness,
                'contrast': contrast_score,
                'is_acceptable': is_acceptable
            }
        except:
            return {
                'overall_quality': 0.2,  # ✅ Valor por defecto MÁS BAJO
                'blur_score': 0.2,
                'brightness': 0.5,
                'contrast': 0.2,
                'is_acceptable': False
            }

    def enhance_image_quality(self, image):
        """Mejora la calidad de la imagen automáticamente"""
        enhanced_versions = []
        
        try:
            enhanced_versions.append(image)
            img_array = np.array(image)
            
            # Reducir número de versiones para ser más eficiente
            # CLAHE adaptativo
            lab = cv2.cvtColor(img_array, cv2.COLOR_RGB2LAB)
            clahe_configs = [(2.0, (8,8)), (3.0, (8,8))]  # Menos configuraciones
            
            for clip_limit, tile_grid in clahe_configs:
                try:
                    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid)
                    lab_copy = lab.copy()
                    lab_copy[:,:,0] = clahe.apply(lab_copy[:,:,0])
                    clahe_enhanced = cv2.cvtColor(lab_copy, cv2.COLOR_LAB2RGB)
                    enhanced_versions.append(Image.fromarray(clahe_enhanced))
                except:
                    continue
            
            # Menos variaciones gamma
            gamma_values = [0.7, 0.8, 1.2, 1.3]
            for gamma in gamma_values:
                try:
                    inv_gamma = 1.0 / gamma
                    table = np.array([((i / 255.0) ** inv_gamma) * 255 
                                    for i in np.arange(0, 256)]).astype("uint8")
                    gamma_corrected = cv2.LUT(img_array, table)
                    enhanced_versions.append(Image.fromarray(gamma_corrected))
                except:
                    continue
            
            return enhanced_versions[:12]  # Limitar a 12 versiones
            
        except Exception as e:
            logger.error(f"Error mejorando imagen: {e}")
            return [image]

    def create_environmental_adaptations(self, image_array, face_location):
        """Crea adaptaciones menos extensivas pero más precisas"""
        adaptations = []
        
        try:
            image = Image.fromarray(image_array)
            top, right, bottom, left = face_location
            
            # ✅ MENOS CONDICIONES PERO MÁS PRECISAS
            lighting_conditions = [
                {'brightness': 0.6, 'contrast': 1.4, 'name': 'low_light'},
                {'brightness': 0.8, 'contrast': 1.2, 'name': 'indoor_low'},
                {'brightness': 1.0, 'contrast': 1.0, 'name': 'neutral'},
                {'brightness': 1.2, 'contrast': 0.8, 'name': 'bright_light'},
                {'brightness': 0.7, 'contrast': 1.6, 'name': 'high_contrast'},
                {'brightness': 1.1, 'contrast': 0.7, 'name': 'outdoor_normal'}
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
                except:
                    continue
            
            return adaptations
            
        except Exception as e:
            logger.error(f"Error creando adaptaciones: {e}")
            return []

    def extract_detailed_landmarks(self, image_array):
        """Extrae landmarks faciales con manejo de errores robusto"""
        try:
            face_landmarks_list = face_recognition.face_landmarks(image_array)
            
            if not face_landmarks_list:
                return None
            
            landmarks = face_landmarks_list[0]
            
            features = {}
            
            if 'left_eye' in landmarks and 'right_eye' in landmarks:
                try:
                    left_eye_center = np.mean(landmarks['left_eye'], axis=0)
                    right_eye_center = np.mean(landmarks['right_eye'], axis=0)
                    eye_distance = np.linalg.norm(left_eye_center - right_eye_center)
                    features['eye_distance'] = float(eye_distance)
                except:
                    pass
            
            if 'nose_bridge' in landmarks:
                try:
                    nose_width = np.max(landmarks['nose_bridge'], axis=0)[0] - np.min(landmarks['nose_bridge'], axis=0)[0]
                    features['nose_width'] = float(nose_width)
                except:
                    pass
            
            if 'chin' in landmarks and 'nose_bridge' in landmarks:
                try:
                    chin_bottom = np.max(landmarks['chin'], axis=0)[1]
                    nose_top = np.min(landmarks['nose_bridge'], axis=0)[1]
                    face_height = chin_bottom - nose_top
                    features['face_height'] = float(face_height)
                except:
                    pass
            
            points_vector = []
            for feature in ['chin', 'left_eyebrow', 'right_eyebrow', 'nose_bridge', 
                          'nose_tip', 'left_eye', 'right_eye', 'top_lip', 'bottom_lip']:
                if feature in landmarks:
                    try:
                        for point in landmarks[feature]:
                            points_vector.extend(point)
                    except:
                        continue
            
            if not points_vector:
                return None
            
            return {
                'geometric_features': features,
                'points_vector': np.array(points_vector),
                'raw_landmarks': landmarks
            }
            
        except Exception as e:
            logger.error(f"Error extrayendo landmarks: {e}")
            return None

    def process_advanced_registration(self, photos_base64):
        """Procesa registro manteniendo estándares altos pero realistas"""
        all_encodings = []
        all_landmarks = []
        all_environmental_adaptations = []
        valid_photos = 0
        failed_reasons = []
        quality_scores = []
        
        print(f"\n📸 Iniciando registro estricto con {len(photos_base64)} fotos...")
        
        for idx, photo_base64 in enumerate(photos_base64):
            try:
                print(f"   Procesando foto {idx+1}/{len(photos_base64)}...")
                
                if ',' in photo_base64:
                    photo_base64 = photo_base64.split(',')[1]
                
                image_data = base64.b64decode(photo_base64)
                image = Image.open(io.BytesIO(image_data))
                
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                
                if image.width > 800 or image.height > 800:
                    image.thumbnail((800, 800), Image.Resampling.LANCZOS)
                
                image_array = np.array(image)
                
                quality_info = self.detect_image_quality(image_array)
                quality_scores.append(quality_info['overall_quality'])
                
                if not quality_info['is_acceptable']:
                    failed_reasons.append(f"Foto {idx+1}: Calidad insuficiente ({quality_info['overall_quality']:.1%})")
                    all_encodings.append(None)
                    all_landmarks.append(None)
                    all_environmental_adaptations.append([])
                    continue
                
                enhanced_versions = self.enhance_image_quality(image)
                
                face_location = None
                best_image_array = None
                
                for enhanced_img in enhanced_versions:
                    enhanced_array = np.array(enhanced_img)
                    
                    try:
                        face_locations = face_recognition.face_locations(
                            enhanced_array,
                            number_of_times_to_upsample=0,
                            model="hog"
                        )
                        
                        if face_locations:
                            face_location = face_locations[0]
                            best_image_array = enhanced_array
                            break
                    except:
                        continue
                    
                    try:
                        face_locations = face_recognition.face_locations(
                            enhanced_array,
                            model="cnn"
                        )
                        if face_locations:
                            face_location = face_locations[0]
                            best_image_array = enhanced_array
                            break
                    except:
                        continue
                
                if not face_location:
                    try:
                        face_locations = face_recognition.face_locations(
                            image_array,
                            number_of_times_to_upsample=1,
                            model="hog"
                        )
                        if face_locations:
                            face_location = face_locations[0]
                            best_image_array = image_array
                    except:
                        pass
                
                if not face_location:
                    failed_reasons.append(f"Foto {idx+1}: No se detectó rostro")
                    all_encodings.append(None)
                    all_landmarks.append(None)
                    all_environmental_adaptations.append([])
                    continue
                
                # Verificar tamaño del rostro
                top, right, bottom, left = face_location
                face_area = (right - left) * (bottom - top)
                
                if face_area < self.ADVANCED_CONFIG['face_area_threshold']:
                    failed_reasons.append(f"Foto {idx+1}: Rostro muy pequeño ({face_area} px²)")
                    all_encodings.append(None)
                    all_landmarks.append(None)
                    all_environmental_adaptations.append([])
                    continue
                
                # Extraer características con múltiples intentos
                encodings = None
                for num_jitters in [10, 15, 5]:
                    try:
                        encodings = face_recognition.face_encodings(
                            best_image_array,
                            [face_location],
                            num_jitters=num_jitters,
                            model="large"
                        )
                        if encodings:
                            break
                    except:
                        continue
                
                if encodings:
                    all_encodings.append(encodings[0].tolist())
                    valid_photos += 1
                    print(f"     ✅ Encoding extraído (calidad: {quality_info['overall_quality']:.2f})")
                else:
                    failed_reasons.append(f"Foto {idx+1}: Fallo en extracción de características")
                    all_encodings.append(None)
                
                landmarks = self.extract_detailed_landmarks(best_image_array)
                all_landmarks.append(landmarks.get('points_vector').tolist() if landmarks else None)
                
                if encodings:
                    adaptations = self.create_environmental_adaptations(best_image_array, face_location)
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
                    
            except Exception as e:
                print(f"   ❌ Error en foto {idx+1}: {str(e)}")
                failed_reasons.append(f"Foto {idx+1}: {str(e)}")
                all_encodings.append(None)
                all_landmarks.append(None)
                all_environmental_adaptations.append([])
        
        valid_encodings = [enc for enc in all_encodings if enc is not None]
        valid_landmarks = [lm for lm in all_landmarks if lm is not None]
        valid_adaptations = [ada for ada in all_environmental_adaptations if ada and len(ada) > 0]
        
        average_quality = np.mean(quality_scores) if quality_scores else 0.0
        
        print(f"✅ Registro completado: {len(valid_encodings)} fotos válidas de {len(photos_base64)}")
        print(f"📊 Calidad promedio: {average_quality:.2f}")
        
        return {
            'encodings': valid_encodings,
            'landmarks': valid_landmarks,
            'environmental_adaptations': valid_adaptations,
            'valid_photos': len(valid_encodings),
            'total_photos': len(photos_base64),
            'failed_reasons': failed_reasons,
            'average_quality': average_quality,
            'quality_scores': quality_scores
        }

    def advanced_face_comparison(self, stored_data, current_encoding, current_landmarks):
        """Comparación facial MÁS ESTRICTA - RECHAZA FALSOS POSITIVOS"""
        try:
            stored_encodings = stored_data.get('encodings', [])
            stored_landmarks = stored_data.get('landmarks', [])
            environmental_adaptations = stored_data.get('environmental_adaptations', [])
            
            if not stored_encodings:
                return False, 0.0, "Sin datos de rostro registrados"
            
            all_scores = []
            detailed_matches = []
            high_quality_matches = 0
            
            max_tolerance = self.ADVANCED_CONFIG['max_tolerance']
            max_euclidean = self.ADVANCED_CONFIG['max_euclidean_distance']
            min_cosine = self.ADVANCED_CONFIG['min_cosine_similarity']
            
            # ✅ VERIFICACIÓN ESTRICTA CON CADA ENCODING ALMACENADO
            for i, stored_enc in enumerate(stored_encodings):
                if stored_enc is None:
                    continue
                
                stored_enc_array = np.array(stored_enc)
                distances = face_recognition.face_distance([stored_enc_array], current_encoding)
                euclidean_dist = distances[0]
                
                # ✅ RECHAZO INMEDIATO SI LA DISTANCIA ES MUY ALTA
                if euclidean_dist > max_euclidean:
                    detailed_matches.append({
                        'photo_index': i,
                        'euclidean_distance': euclidean_dist,
                        'rejected_reason': 'Distancia euclidiana excesiva',
                        'combined': 0.0
                    })
                    continue
                
                euclidean_score = max(0, 1 - (euclidean_dist / self.ADVANCED_CONFIG['base_tolerance']))
                
                # Similitud coseno MÁS ESTRICTA
                try:
                    cosine_sim = 1 - distance.cosine(stored_enc_array, current_encoding)
                    if np.isnan(cosine_sim) or cosine_sim < min_cosine:
                        cosine_sim = 0
                    else:
                        cosine_sim = max(0, cosine_sim)
                except:
                    cosine_sim = 0
                
                # ✅ RECHAZO SI LA SIMILITUD COSENO ES MUY BAJA
                if cosine_sim < min_cosine:
                    detailed_matches.append({
                        'photo_index': i,
                        'euclidean_distance': euclidean_dist,
                        'cosine_similarity': cosine_sim,
                        'rejected_reason': 'Similitud coseno insuficiente',
                        'combined': 0.0
                    })
                    continue
                
                # Correlación
                try:
                    correlation = np.corrcoef(stored_enc_array, current_encoding)[0, 1]
                    if np.isnan(correlation):
                        correlation = 0
                    else:
                        correlation = max(0, correlation)
                except:
                    correlation = 0
                
                # Distancia Manhattan
                manhattan_dist = np.sum(np.abs(stored_enc_array - current_encoding)) / len(stored_enc_array)
                manhattan_score = max(0, 1 - (manhattan_dist / 2))
                
                # ✅ CÁLCULO MÁS ESTRICTO DEL PUNTAJE COMBINADO
                combined_score = (
                    euclidean_score * 0.5 +  # Mayor peso a la distancia euclidiana
                    cosine_sim * 0.4 +       # Mayor peso a la similitud coseno
                    correlation * 0.05 +     # Menor peso a la correlación
                    manhattan_score * 0.05   # Menor peso a Manhattan
                )
                
                # ✅ BONIFICACIONES MÁS CONSERVADORAS
                bonus_applied = 0
                if euclidean_dist < 0.35:  # Muy buena coincidencia
                    bonus_applied += 0.03
                    high_quality_matches += 1
                
                if euclidean_dist < max_tolerance and cosine_sim > 0.8:
                    bonus_applied += 0.02
                
                final_score = combined_score + bonus_applied
                all_scores.append(final_score)
                
                detailed_matches.append({
                    'photo_index': i,
                    'euclidean_distance': euclidean_dist,
                    'euclidean_score': euclidean_score,
                    'cosine': cosine_sim,
                    'correlation': correlation,
                    'manhattan': manhattan_score,
                    'combined': final_score,
                    'within_tolerance': euclidean_dist < max_tolerance,
                    'high_quality': euclidean_dist < 0.35
                })
            
            # ✅ PROCESAMIENTO ESTRICTO DE ADAPTACIONES AMBIENTALES
            adaptation_scores = []
            for adaptations in environmental_adaptations:
                for adaptation in adaptations:
                    if 'encoding' in adaptation:
                        try:
                            adapt_enc = np.array(adaptation['encoding'])
                            adapt_distances = face_recognition.face_distance([adapt_enc], current_encoding)
                            adapt_dist = adapt_distances[0]
                            
                            # ✅ SOLO CONSIDERAR ADAPTACIONES DE ALTA CALIDAD
                            if adapt_dist <= max_euclidean:
                                adapt_score = max(0, 1 - (adapt_dist / self.ADVANCED_CONFIG['base_tolerance']))
                                if adapt_score > 0.6:  # Solo adaptaciones buenas
                                    adaptation_scores.append(adapt_score)
                                    all_scores.append(adapt_score)
                        except:
                            continue
            
            if not all_scores:
                return False, 0.0, "No se encontraron coincidencias válidas"

            # ✅ VERIFICACIÓN DE LANDMARKS MÁS ESTRICTA
            landmark_bonus = 0
            if current_landmarks is not None and stored_landmarks:
                landmark_similarities = []
                current_lm_array = np.array(current_landmarks)
                
                for stored_lm in stored_landmarks:
                    if stored_lm is not None:
                        try:
                            stored_lm_array = np.array(stored_lm)
                            min_len = min(len(current_lm_array), len(stored_lm_array))
                            
                            if min_len > 30:  # ✅ MÁS EXIGENTE
                                lm_similarity = 1 - distance.cosine(
                                    current_lm_array[:min_len],
                                    stored_lm_array[:min_len]
                                )
                                if not np.isnan(lm_similarity) and lm_similarity > 0.7:  # ✅ MÁS EXIGENTE
                                    landmark_similarities.append(max(0, lm_similarity))
                        except:
                            continue
                
                if landmark_similarities:
                    landmark_score = np.mean(landmark_similarities)
                    landmark_bonus = min(landmark_score * 0.05, 0.05)  # ✅ BONUS MÁS CONSERVADOR

            # ✅ CÁLCULO FINAL MÁS ESTRICTO
            sorted_scores = sorted(all_scores, reverse=True)
            
            # Rechazar si no hay suficientes coincidencias de calidad
            if len(sorted_scores) < self.ADVANCED_CONFIG['min_matches']:
                return False, 0.0, f"Insuficientes coincidencias: {len(sorted_scores)} < {self.ADVANCED_CONFIG['min_matches']}"
            
            # Rechazar si no hay coincidencias de alta calidad
            if high_quality_matches == 0:
                return False, 0.0, "Sin coincidencias de alta calidad"
            
            # Calcular confianza basada en los mejores matches
            top_scores = sorted_scores[:min(3, len(sorted_scores))]
            base_confidence = np.mean(top_scores)
            
            # ✅ PENALIZACIÓN POR INCONSISTENCIA
            score_std = np.std(top_scores) if len(top_scores) > 1 else 0
            consistency_penalty = min(score_std * 0.5, 0.15)  # Penalizar inconsistencia
            
            # Confianza final MÁS CONSERVADORA
            final_confidence = base_confidence + landmark_bonus - consistency_penalty
            final_confidence = max(0.0, min(final_confidence, 1.0))
            
            # ✅ DOBLE VERIFICACIÓN CON UMBRALES ESTRICTOS
            min_confidence = self.ADVANCED_CONFIG['min_confidence']
            strict_threshold = self.ADVANCED_CONFIG['strict_confidence_threshold']
            
            is_match = (
                final_confidence >= min_confidence and 
                high_quality_matches >= 1 and
                len(sorted_scores) >= self.ADVANCED_CONFIG['min_matches']
            )
            
            # ✅ VERIFICACIÓN ULTRA ESTRICTA OPCIONAL
            if self.ADVANCED_CONFIG['strict_mode'] and final_confidence < strict_threshold:
                is_match = False
            
            details = (f"Confidence: {final_confidence:.1%}, "
                      f"High quality matches: {high_quality_matches}, "
                      f"Total matches: {len(all_scores)}, "
                      f"Consistency: {score_std:.3f}, "
                      f"Adaptations: {len(adaptation_scores)}")
            
            return is_match, final_confidence, details
            
        except Exception as e:
            logger.error(f"Error en comparación avanzada: {e}")
            return False, 0.0, f"Error de comparación: {str(e)}"

    def advanced_verify(self, photo_base64):
        """Verificación MÁS ESTRICTA - RECHAZA ROSTROS NO REGISTRADOS"""
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
                
                if image.width > 1000 or image.height > 1000:
                    image.thumbnail((1000, 1000), Image.Resampling.LANCZOS)
                
                image_array = np.array(image)
                
                # ✅ VERIFICACIÓN ESTRICTA DE CALIDAD
                quality_info = self.detect_image_quality(image_array)
                if not quality_info['is_acceptable']:
                    return {
                        'success': False, 
                        'error': f'Calidad de imagen insuficiente: {quality_info["overall_quality"]:.1%}'
                    }
                
                enhanced_versions = self.enhance_image_quality(image)
                
                face_location = None
                best_image_array = None
                
                # ✅ BÚSQUEDA MÁS CUIDADOSA DE ROSTROS
                for enhanced_img in enhanced_versions[:10]:  # Limitar versiones para ser más rápido
                    if time.time() - start_time > self.ADVANCED_CONFIG['verification_timeout'] * 0.5:
                        break
                    
                    enhanced_array = np.array(enhanced_img)
                    
                    try:
                        face_locations = face_recognition.face_locations(
                            enhanced_array,
                            number_of_times_to_upsample=1,
                            model="hog"
                        )
                        
                        if face_locations:
                            face_location = face_locations[0]
                            best_image_array = enhanced_array
                            
                            # ✅ VERIFICAR TAMAÑO DEL ROSTRO DETECTADO
                            top, right, bottom, left = face_location
                            face_area = (right - left) * (bottom - top)
                            if face_area >= self.ADVANCED_CONFIG['face_area_threshold']:
                                break
                            else:
                                face_location = None  # Rostro muy pequeño, seguir buscando
                    except:
                        continue
                
                if not face_location:
                    return {
                        'success': False, 
                        'error': 'No se detectó un rostro de tamaño suficiente para verificación segura'
                    }
                
                # ✅ EXTRACCIÓN DE CARACTERÍSTICAS MÁS RIGUROSA
                current_encoding = face_recognition.face_encodings(
                    best_image_array,
                    [face_location],
                    num_jitters=5,  # Más jitters para mayor precisión
                    model="large"
                )
                
                if not current_encoding:
                    return {
                        'success': False, 
                        'error': 'No se pudieron extraer características faciales confiables'
                    }
                
                current_encoding = current_encoding[0]
                
                # Extraer landmarks si hay tiempo
                current_landmarks = None
                if time.time() - start_time < self.ADVANCED_CONFIG['verification_timeout'] * 0.6:
                    landmark_data = self.extract_detailed_landmarks(best_image_array)
                    if landmark_data:
                        current_landmarks = landmark_data['points_vector']
                
                best_match = None
                best_confidence = 0
                all_results = []
                
                employees_with_faces = Employee.objects.filter(
                    is_active=True,
                    has_face_registered=True
                ).select_related()
                
                print(f"🔍 Verificando contra {employees_with_faces.count()} empleados registrados...")
                
                for employee in employees_with_faces:
                    if time.time() - start_time > self.ADVANCED_CONFIG['verification_timeout'] * 0.85:
                        break
                    
                    try:
                        stored_encodings_json = employee.face_encoding
                        if not stored_encodings_json:
                            continue
                        
                        stored_data = json.loads(stored_encodings_json)
                        
                        is_match, confidence, details = self.advanced_face_comparison(
                            stored_data,
                            current_encoding,
                            current_landmarks
                        )
                        
                        all_results.append({
                            'employee': employee,
                            'confidence': confidence,
                            'match': is_match,
                            'details': details
                        })
                        
                        print(f"   {employee.name}: {confidence:.1%} - {'✅' if is_match else '❌'}")
                        
                        if is_match and confidence > best_confidence:
                            best_confidence = confidence
                            best_match = employee
                            
                    except Exception as e:
                        logger.error(f"Error comparando con {employee.name}: {e}")
                        continue
                
                # ✅ LOG DETALLADO DEL RESULTADO
                if best_match:
                    print(f"✅ MATCH ENCONTRADO: {best_match.name} con {best_confidence:.1%} de confianza")
                else:
                    print(f"❌ NO MATCH: Mejor confianza fue {max([r['confidence'] for r in all_results], default=0):.1%}")
                    print(f"   Umbral requerido: {self.ADVANCED_CONFIG['min_confidence']:.1%}")
                
                return {
                    'success': True,
                    'data': {
                        'best_match': best_match,
                        'best_confidence': best_confidence,
                        'all_results': all_results,
                        'quality_info': quality_info,
                        'threshold_used': self.ADVANCED_CONFIG['min_confidence']
                    }
                }
                
            except Exception as e:
                logger.error(f"Error en verificación avanzada: {e}")
                return {'success': False, 'error': str(e)}
        
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(verify_process)
            
            try:
                result = future.result(timeout=self.ADVANCED_CONFIG['verification_timeout'])
                return result.get('data'), result.get('error')
            except FutureTimeoutError:
                future.cancel()
                return None, "Timeout: La verificación excedió el tiempo límite de seguridad."
            except Exception as e:
                logger.error(f"Error en executor: {e}")
                return None, f"Error en verificación: {str(e)}"