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
        self.ADVANCED_CONFIG = {
            'min_photos': 8,
            'base_tolerance': 0.55, # Valor más estricto
            'adaptive_tolerance': True,
            'min_confidence': 0.60, # Umbral de confianza más seguro
            'min_matches': 1,
            'use_landmarks': True,
            'use_environmental_adaptation': True,
            'max_tolerance': 0.75,
            'verification_timeout': 15,
            'strict_mode': False,
            'min_face_size': 40,
            'brightness_adaptation': True,
            'contrast_enhancement': True,
            'blur_detection': True,
            'quality_threshold': 0.1,
        }

    def detect_image_quality(self, image_array):
        """Detecta calidad - ultra permisivo para cámaras malas"""
        try:
            pil_image = Image.fromarray(image_array)
            
            # Desenfoque ultra permisivo
            gray = cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            blur_score = min(laplacian_var / 20.0, 1.0)
            
            # Brillo ultra tolerante
            stat = ImageStat.Stat(pil_image)
            brightness = sum(stat.mean) / len(stat.mean) / 255.0
            brightness_score = 1.0
            
            # Contraste ultra permisivo
            contrast_score = min(np.std(np.array(pil_image)) / 64.0, 1.0)
            
            # Puntaje siempre aceptable
            quality_score = max(0.5, (blur_score * 0.3 + brightness_score * 0.3 + contrast_score * 0.4))
            
            return {
                'overall_quality': quality_score,
                'blur_score': blur_score,
                'brightness': brightness,
                'contrast': contrast_score,
                'is_acceptable': True
            }
        except:
            return {
                'overall_quality': 0.8,
                'blur_score': 0.8,
                'brightness': 0.5,
                'contrast': 0.8,
                'is_acceptable': True
            }

    def enhance_image_quality(self, image):
        """Mejora la calidad de la imagen automáticamente - versión extendida"""
        enhanced_versions = []
        
        try:
            enhanced_versions.append(image)
            img_array = np.array(image)
            lab = cv2.cvtColor(img_array, cv2.COLOR_RGB2LAB)
            clahe_configs = [(2.0, (8,8)), (3.0, (8,8)), (4.0, (8,8)), (2.0, (4,4))]
            
            for clip_limit, tile_grid in clahe_configs:
                try:
                    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid)
                    lab_copy = lab.copy()
                    lab_copy[:,:,0] = clahe.apply(lab_copy[:,:,0])
                    clahe_enhanced = cv2.cvtColor(lab_copy, cv2.COLOR_LAB2RGB)
                    enhanced_versions.append(Image.fromarray(clahe_enhanced))
                except:
                    continue
            
            gamma_values = [0.5, 0.6, 0.7, 0.8, 0.9, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6]
            for gamma in gamma_values:
                try:
                    inv_gamma = 1.0 / gamma
                    table = np.array([((i / 255.0) ** inv_gamma) * 255 
                                    for i in np.arange(0, 256)]).astype("uint8")
                    gamma_corrected = cv2.LUT(img_array, table)
                    enhanced_versions.append(Image.fromarray(gamma_corrected))
                except:
                    continue
            
            sharpening_kernels = [
                np.array([[-1,-1,-1], [-1, 9,-1], [-1,-1,-1]]),
                np.array([[0,-1,0], [-1, 5,-1], [0,-1,0]]),
                np.array([[-1,-1,-1], [-1,12,-1], [-1,-1,-1]]) / 4
            ]
            
            for kernel in sharpening_kernels:
                try:
                    sharpened = cv2.filter2D(img_array, -1, kernel)
                    sharpened = np.clip(sharpened, 0, 255).astype(np.uint8)
                    enhanced_versions.append(Image.fromarray(sharpened))
                except:
                    continue
            
            try:
                yuv = cv2.cvtColor(img_array, cv2.COLOR_RGB2YUV)
                yuv[:,:,0] = cv2.equalizeHist(yuv[:,:,0])
                hist_eq_yuv = cv2.cvtColor(yuv, cv2.COLOR_YUV2RGB)
                enhanced_versions.append(Image.fromarray(hist_eq_yuv))
                
                hsv = cv2.cvtColor(img_array, cv2.COLOR_RGB2HSV)
                hsv[:,:,2] = cv2.equalizeHist(hsv[:,:,2])
                hist_eq_hsv = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)
                enhanced_versions.append(Image.fromarray(hist_eq_hsv))
            except:
                pass
            
            try:
                bilateral = cv2.bilateralFilter(img_array, 9, 75, 75)
                enhanced_versions.append(Image.fromarray(bilateral))
                median = cv2.medianBlur(img_array, 5)
                enhanced_versions.append(Image.fromarray(median))
                gaussian = cv2.GaussianBlur(img_array, (3, 3), 0)
                enhanced_versions.append(Image.fromarray(gaussian))
            except:
                pass
            
            brightness_values = [-50, -30, -10, 10, 30, 50]
            contrast_values = [0.8, 0.9, 1.1, 1.2, 1.3, 1.4]
            
            for brightness in brightness_values[:3]:
                for contrast in contrast_values[:2]:
                    try:
                        enhanced = ImageEnhance.Brightness(image).enhance(1 + brightness/100)
                        enhanced = ImageEnhance.Contrast(enhanced).enhance(contrast)
                        enhanced_versions.append(enhanced)
                    except:
                        continue
            
            return enhanced_versions[:25]
            
        except Exception as e:
            logger.error(f"Error mejorando imagen: {e}")
            return [image]

    def create_environmental_adaptations(self, image_array, face_location):
        """Crea adaptaciones extensivas para condiciones variables"""
        adaptations = []
        
        try:
            image = Image.fromarray(image_array)
            top, right, bottom, left = face_location
            
            lighting_conditions = [
                {'brightness': 0.4, 'contrast': 1.6, 'name': 'extreme_low_light'},
                {'brightness': 0.5, 'contrast': 1.5, 'name': 'very_low_light'},
                {'brightness': 0.6, 'contrast': 1.4, 'name': 'low_light'},
                {'brightness': 0.7, 'contrast': 1.3, 'name': 'dim_light'},
                {'brightness': 0.8, 'contrast': 1.2, 'name': 'indoor_low'},
                {'brightness': 0.9, 'contrast': 1.1, 'name': 'indoor_normal'},
                {'brightness': 1.0, 'contrast': 1.0, 'name': 'neutral'},
                {'brightness': 1.1, 'contrast': 0.9, 'name': 'outdoor_normal'},
                {'brightness': 1.2, 'contrast': 0.8, 'name': 'bright_light'},
                {'brightness': 1.3, 'contrast': 0.7, 'name': 'very_bright'},
                {'brightness': 1.4, 'contrast': 0.6, 'name': 'extreme_bright'},
                {'brightness': 1.5, 'contrast': 0.5, 'name': 'overexposed'},
                {'brightness': 0.6, 'contrast': 1.8, 'name': 'high_contrast_dark'},
                {'brightness': 1.2, 'contrast': 1.6, 'name': 'high_contrast_bright'},
                {'brightness': 0.9, 'contrast': 0.6, 'name': 'low_contrast'},
                {'brightness': 1.1, 'contrast': 0.7, 'name': 'washed_out'}
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
        """Procesa registro con máxima permisividad para cámaras malas"""
        all_encodings = []
        all_landmarks = []
        all_environmental_adaptations = []
        valid_photos = 0
        failed_reasons = []
        quality_scores = []
        
        print(f"\n📸 Iniciando registro ultra permisivo con {len(photos_base64)} fotos...")
        
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
                
                top, right, bottom, left = face_location
                face_width = right - left
                face_height = bottom - top
                
                if face_width < self.ADVANCED_CONFIG['min_face_size'] or face_height < self.ADVANCED_CONFIG['min_face_size']:
                    print(f"     ⚠️ Rostro pequeño ({face_width}x{face_height}) pero se procesa")
                
                encodings = None
                for num_jitters in [10, 15, 5, 1]:
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
        
        average_quality = np.mean(quality_scores) if quality_scores else 0.5
        
        print(f"✅ Registro completado: {len(valid_encodings)} fotos válidas de {len(photos_base64)}")
        print(f"📊 Calidad promedio: {average_quality:.2f}")
        print(f"🔧 Adaptaciones creadas: {sum(len(ada) for ada in valid_adaptations)}")
        
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
        """Comparación facial ultra permisiva para cámaras de baja calidad"""
        try:
            stored_encodings = stored_data.get('encodings', [])
            stored_landmarks = stored_data.get('landmarks', [])
            environmental_adaptations = stored_data.get('environmental_adaptations', [])
            
            if not stored_encodings:
                return False, 0.0, "Sin datos de rostro registrados"
            
            all_scores = []
            detailed_matches = []
            
            max_tolerance = self.ADVANCED_CONFIG['max_tolerance']
            
            for i, stored_enc in enumerate(stored_encodings):
                if stored_enc is None:
                    continue
                
                stored_enc_array = np.array(stored_enc)
                distances = face_recognition.face_distance([stored_enc_array], current_encoding)
                euclidean_dist = distances[0]
                euclidean_score = max(0, 1 - (euclidean_dist / self.ADVANCED_CONFIG['base_tolerance'])) 
                
                try:
                    cosine_sim = 1 - distance.cosine(stored_enc_array, current_encoding)
                    if np.isnan(cosine_sim):
                        cosine_sim = 0
                    else:
                        cosine_sim = max(0, cosine_sim)
                except:
                    cosine_sim = 0
                
                try:
                    correlation = np.corrcoef(stored_enc_array, current_encoding)[0, 1]
                    if np.isnan(correlation):
                        correlation = 0
                    else:
                        correlation = max(0, correlation)
                except:
                    correlation = 0
                
                manhattan_dist = np.sum(np.abs(stored_enc_array - current_encoding)) / len(stored_enc_array)
                manhattan_score = max(0, 1 - (manhattan_dist / 2))
                
                combined_score = (
                    euclidean_score * 0.4 +
                    cosine_sim * 0.4 +
                    correlation * 0.1 +
                    manhattan_score * 0.1
                )
                
                # Reintroducir bonos controlados que no inflan en exceso el puntaje
                if euclidean_dist < max_tolerance:
                    combined_score += 0.05
                
                if euclidean_dist < 0.7:
                    combined_score += 0.02
                
                all_scores.append(combined_score)
                detailed_matches.append({
                    'photo_index': i,
                    'euclidean_distance': euclidean_dist,
                    'euclidean_score': euclidean_score,
                    'cosine': cosine_sim,
                    'correlation': correlation,
                    'manhattan': manhattan_score,
                    'combined': combined_score,
                    'within_tolerance': euclidean_dist < max_tolerance
                })
            
            adaptation_scores = []
            for adaptations in environmental_adaptations:
                for adaptation in adaptations:
                    if 'encoding' in adaptation:
                        try:
                            adapt_enc = np.array(adaptation['encoding'])
                            adapt_distances = face_recognition.face_distance([adapt_enc], current_encoding)
                            adapt_dist = adapt_distances[0]
                            adapt_score = max(0, 1 - (adapt_dist / self.ADVANCED_CONFIG['base_tolerance']))
                            adaptation_scores.append(adapt_score)
                            all_scores.append(adapt_score)
                        except:
                            continue
            
            if not all_scores:
                return False, 0.0, "No se pudieron calcular coincidencias"

            landmark_bonus = 0
            if current_landmarks is not None and stored_landmarks:
                landmark_similarities = []
                current_lm_array = np.array(current_landmarks)
                
                for stored_lm in stored_landmarks:
                    if stored_lm is not None:
                        try:
                            stored_lm_array = np.array(stored_lm)
                            min_len = min(len(current_lm_array), len(stored_lm_array))
                            
                            if min_len > 20:
                                lm_similarity = 1 - distance.cosine(
                                    current_lm_array[:min_len],
                                    stored_lm_array[:min_len]
                                )
                                if not np.isnan(lm_similarity) and lm_similarity > -0.5:
                                    landmark_similarities.append(max(0, lm_similarity))
                        except:
                            continue
                
                if landmark_similarities:
                    landmark_score = np.mean(landmark_similarities)
                    landmark_bonus = min(landmark_score * 0.10, 0.10)
            
            sorted_scores = sorted(all_scores, reverse=True)
            
            best_score = sorted_scores[0] if sorted_scores else 0
            
            # Lógica de bonificación por consistencia
            top_3_scores = sorted_scores[:min(3, len(sorted_scores))]
            score_std = np.std(top_3_scores) if len(top_3_scores) > 1 else 0
            
            consistency_bonus = 0
            if score_std < 0.15:
                consistency_bonus = 0.07

            # **Cambio clave: Cálculo del puntaje final para un mejor equilibrio**
            base_confidence = np.mean(sorted_scores[:min(5, len(sorted_scores))])
            if base_confidence > 0.5:
                final_confidence = base_confidence + 0.05 + landmark_bonus + consistency_bonus
            else:
                final_confidence = base_confidence + landmark_bonus + consistency_bonus
            
            final_confidence = min(final_confidence, 1.0)
            
            is_match = final_confidence >= self.ADVANCED_CONFIG['min_confidence']
            
            details = (f"Score: {final_confidence:.1%}, Matches: {len(all_scores)}, "
                       f"Consistency: {score_std:.2f}, "
                       f"Adaptations: {len(adaptation_scores)}")
            
            return is_match, final_confidence, details
            
        except Exception as e:
            logger.error(f"Error en comparación avanzada: {e}")
            return False, 0.0, f"Error de comparación: {str(e)}"

    def advanced_verify(self, photo_base64):
        """Verificación ultra permisiva con múltiples intentos"""
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
                
                quality_info = self.detect_image_quality(image_array)
                
                enhanced_versions = self.enhance_image_quality(image)
                
                face_location = None
                best_image_array = None
                
                for enhanced_img in enhanced_versions:
                    if time.time() - start_time > self.ADVANCED_CONFIG['verification_timeout'] * 0.6:
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
                            break
                    except:
                        continue
                    
                    if time.time() - start_time < self.ADVANCED_CONFIG['verification_timeout'] * 0.4:
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
                    return {'success': False, 'error': 'No se detectó rostro en ninguna versión mejorada'}
                
                current_encoding = face_recognition.face_encodings(
                    best_image_array,
                    [face_location],
                    num_jitters=3,
                    model="large"
                )
                
                if not current_encoding:
                    return {'success': False, 'error': 'No se pudieron extraer características faciales'}
                
                current_encoding = current_encoding[0]
                
                current_landmarks = None
                if time.time() - start_time < self.ADVANCED_CONFIG['verification_timeout'] * 0.7:
                    landmark_data = self.extract_detailed_landmarks(best_image_array)
                    if landmark_data:
                        current_landmarks = landmark_data['points_vector']
                
                best_match = None
                best_confidence = 0
                all_results = []
                
                employees_with_faces = Employee.objects.filter(
                    is_active=True,
                    has_face_registered=True
                )
                
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
                            current_landmarks
                        )
                        
                        all_results.append({
                            'employee': employee,
                            'confidence': confidence,
                            'match': is_match,
                            'details': details
                        })
                        
                        if is_match and confidence > best_confidence:
                            best_confidence = confidence
                            best_match = employee
                            
                    except Exception as e:
                        logger.error(f"Error comparando con {employee.name}: {e}")
                        continue
                
                return {
                    'success': True,
                    'data': {
                        'best_match': best_match,
                        'best_confidence': best_confidence,
                        'all_results': all_results,
                        'quality_info': quality_info
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
                return None, "Timeout: La verificación avanzada excedió el tiempo límite."
            except Exception as e:
                logger.error(f"Error en executor: {e}")
                return None, f"Error en verificación: {str(e)}"