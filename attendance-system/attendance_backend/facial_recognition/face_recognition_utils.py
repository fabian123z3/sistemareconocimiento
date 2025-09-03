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
            'base_tolerance': 0.28,  # Más estricto para mejor precisión
            'adaptive_tolerance': True,
            'min_confidence': 0.70,  # Mayor confianza requerida
            'min_matches': 3,  # Mínimo matches para validar
            'use_landmarks': True,
            'use_environmental_adaptation': True,
            'max_tolerance': 0.35,
            'verification_timeout': 8,  # Más tiempo para análisis completo
            'strict_mode': True,
            'min_face_size': 80,  # Rostro más grande requerido
            'brightness_adaptation': True,
            'contrast_enhancement': True,
            'blur_detection': True,
            'quality_threshold': 0.6,
        }

    def detect_image_quality(self, image_array):
        """Detecta la calidad de la imagen"""
        try:
            # Convertir a PIL para análisis
            pil_image = Image.fromarray(image_array)
            
            # Detectar desenfoque usando varianza del Laplaciano
            gray = cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            blur_score = min(laplacian_var / 100.0, 1.0)  # Normalizar
            
            # Detectar brillo
            stat = ImageStat.Stat(pil_image)
            brightness = sum(stat.mean) / len(stat.mean) / 255.0
            
            # Detectar contraste
            contrast_score = np.std(np.array(pil_image)) / 255.0
            
            # Puntaje general de calidad
            quality_score = (blur_score * 0.4 + 
                           min(abs(brightness - 0.5) * 2, 1.0) * 0.3 + 
                           contrast_score * 0.3)
            
            return {
                'overall_quality': min(quality_score, 1.0),
                'blur_score': blur_score,
                'brightness': brightness,
                'contrast': contrast_score,
                'is_acceptable': quality_score > self.ADVANCED_CONFIG['quality_threshold']
            }
        except:
            return {
                'overall_quality': 0.5,
                'blur_score': 0.5,
                'brightness': 0.5,
                'contrast': 0.5,
                'is_acceptable': False
            }

    def enhance_image_quality(self, image):
        """Mejora la calidad de la imagen automáticamente"""
        enhanced_versions = []
        
        try:
            # Original
            enhanced_versions.append(image)
            
            # Mejora de contraste adaptativo
            img_array = np.array(image)
            
            # CLAHE (Contrast Limited Adaptive Histogram Equalization)
            lab = cv2.cvtColor(img_array, cv2.COLOR_RGB2LAB)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
            lab[:,:,0] = clahe.apply(lab[:,:,0])
            clahe_enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
            enhanced_versions.append(Image.fromarray(clahe_enhanced))
            
            # Corrección gamma para diferentes condiciones de luz
            for gamma in [0.8, 1.2]:
                inv_gamma = 1.0 / gamma
                table = np.array([((i / 255.0) ** inv_gamma) * 255 
                                for i in np.arange(0, 256)]).astype("uint8")
                gamma_corrected = cv2.LUT(img_array, table)
                enhanced_versions.append(Image.fromarray(gamma_corrected))
            
            # Mejora de nitidez
            sharpening_kernel = np.array([[-1,-1,-1],
                                        [-1, 9,-1],
                                        [-1,-1,-1]])
            sharpened = cv2.filter2D(img_array, -1, sharpening_kernel)
            sharpened = np.clip(sharpened, 0, 255).astype(np.uint8)
            enhanced_versions.append(Image.fromarray(sharpened))
            
            return enhanced_versions
            
        except Exception as e:
            logger.error(f"Error mejorando imagen: {e}")
            return [image]

    def create_environmental_adaptations(self, image_array, face_location):
        """Crea adaptaciones para diferentes condiciones ambientales"""
        adaptations = []
        
        try:
            image = Image.fromarray(image_array)
            top, right, bottom, left = face_location
            
            # Simulación de diferentes condiciones de iluminación
            lighting_conditions = [
                {'brightness': 0.7, 'contrast': 1.3, 'name': 'low_light'},
                {'brightness': 1.3, 'contrast': 0.8, 'name': 'bright_light'},
                {'brightness': 1.0, 'contrast': 1.5, 'name': 'high_contrast'},
                {'brightness': 0.9, 'contrast': 1.1, 'name': 'normal_enhanced'}
            ]
            
            for condition in lighting_conditions:
                try:
                    adapted = ImageEnhance.Brightness(image).enhance(condition['brightness'])
                    adapted = ImageEnhance.Contrast(adapted).enhance(condition['contrast'])
                    
                    # Extraer encoding de la versión adaptada
                    adapted_array = np.array(adapted)
                    encoding = face_recognition.face_encodings(
                        adapted_array, [face_location], num_jitters=3, model="large"
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
        """Extrae landmarks faciales detallados"""
        try:
            face_landmarks_list = face_recognition.face_landmarks(image_array)
            
            if not face_landmarks_list:
                return None
            
            landmarks = face_landmarks_list[0]
            
            # Calcular características geométricas
            features = {}
            
            # Distancias entre características clave
            if 'left_eye' in landmarks and 'right_eye' in landmarks:
                left_eye_center = np.mean(landmarks['left_eye'], axis=0)
                right_eye_center = np.mean(landmarks['right_eye'], axis=0)
                eye_distance = np.linalg.norm(left_eye_center - right_eye_center)
                features['eye_distance'] = float(eye_distance)
            
            # Ancho de la nariz
            if 'nose_bridge' in landmarks:
                nose_width = np.max(landmarks['nose_bridge'], axis=0)[0] - np.min(landmarks['nose_bridge'], axis=0)[0]
                features['nose_width'] = float(nose_width)
            
            # Altura facial
            if 'chin' in landmarks and 'nose_bridge' in landmarks:
                chin_bottom = np.max(landmarks['chin'], axis=0)[1]
                nose_top = np.min(landmarks['nose_bridge'], axis=0)[1]
                face_height = chin_bottom - nose_top
                features['face_height'] = float(face_height)
            
            # Vector de puntos concatenados
            points_vector = []
            for feature in ['chin', 'left_eyebrow', 'right_eyebrow', 'nose_bridge', 
                          'nose_tip', 'left_eye', 'right_eye', 'top_lip', 'bottom_lip']:
                if feature in landmarks:
                    for point in landmarks[feature]:
                        points_vector.extend(point)
            
            return {
                'geometric_features': features,
                'points_vector': np.array(points_vector),
                'raw_landmarks': landmarks
            }
            
        except Exception as e:
            logger.error(f"Error extrayendo landmarks: {e}")
            return None

    def process_advanced_registration(self, photos_base64):
        """Procesa registro avanzado con 8 fotos y múltiples adaptaciones"""
        all_encodings = []
        all_landmarks = []
        all_environmental_adaptations = []
        valid_photos = 0
        failed_reasons = []
        quality_scores = []
        
        print(f"\n📸 Iniciando registro avanzado con {len(photos_base64)} fotos...")
        
        for idx, photo_base64 in enumerate(photos_base64):
            try:
                print(f"   Procesando foto {idx+1}/{len(photos_base64)}...")
                
                if ',' in photo_base64:
                    photo_base64 = photo_base64.split(',')[1]
                
                image_data = base64.b64decode(photo_base64)
                image = Image.open(io.BytesIO(image_data))
                
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                
                # Redimensionar si es muy grande
                if image.width > 1200:
                    ratio = 1200 / image.width
                    new_height = int(image.height * ratio)
                    image = image.resize((1200, new_height), Image.Resampling.LANCZOS)
                
                image_array = np.array(image)
                
                # Evaluar calidad de imagen
                quality_info = self.detect_image_quality(image_array)
                quality_scores.append(quality_info['overall_quality'])
                
                if not quality_info['is_acceptable']:
                    # Intentar mejorar la imagen
                    enhanced_versions = self.enhance_image_quality(image)
                    image_array = np.array(enhanced_versions[1])  # Usar versión mejorada
                    quality_info = self.detect_image_quality(image_array)
                
                # Detección de rostros robusta
                face_locations = face_recognition.face_locations(
                    image_array,
                    number_of_times_to_upsample=2,
                    model="hog"
                )
                
                if not face_locations:
                    face_locations = face_recognition.face_locations(
                        image_array,
                        model="cnn"
                    )
                
                if not face_locations:
                    # Último intento con mejora de contraste
                    enhanced = ImageEnhance.Contrast(image).enhance(1.8)
                    enhanced_array = np.array(enhanced)
                    face_locations = face_recognition.face_locations(
                        enhanced_array,
                        number_of_times_to_upsample=1,
                        model="hog"
                    )
                    if face_locations:
                        image_array = enhanced_array
                
                if not face_locations:
                    failed_reasons.append(f"Foto {idx+1}: No se detectó rostro")
                    all_encodings.append(None)
                    all_landmarks.append(None)
                    all_environmental_adaptations.append([])
                    continue
                
                face_location = face_locations[0]
                
                # Verificar tamaño mínimo del rostro
                top, right, bottom, left = face_location
                face_width = right - left
                face_height = bottom - top
                
                if face_width < self.ADVANCED_CONFIG['min_face_size'] or face_height < self.ADVANCED_CONFIG['min_face_size']:
                    failed_reasons.append(f"Foto {idx+1}: Rostro muy pequeño")
                    all_encodings.append(None)
                    all_landmarks.append(None)
                    all_environmental_adaptations.append([])
                    continue
                
                # Extraer encodings principales
                encodings = face_recognition.face_encodings(
                    image_array,
                    [face_location],
                    num_jitters=15,  # Más jitters para mayor robustez
                    model="large"
                )
                
                if encodings:
                    all_encodings.append(encodings[0].tolist())
                    valid_photos += 1
                    print(f"     ✅ Encoding extraído (calidad: {quality_info['overall_quality']:.2f})")
                else:
                    failed_reasons.append(f"Foto {idx+1}: Fallo en extracción de características")
                    all_encodings.append(None)
                
                # Extraer landmarks detallados
                landmarks = self.extract_detailed_landmarks(image_array)
                all_landmarks.append(landmarks.get('points_vector').tolist() if landmarks else None)
                
                # Crear adaptaciones ambientales
                if encodings and self.ADVANCED_CONFIG['use_environmental_adaptation']:
                    adaptations = self.create_environmental_adaptations(image_array, face_location)
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
        """Comparación facial avanzada con múltiples métodos"""
        try:
            stored_encodings = stored_data.get('encodings', [])
            stored_landmarks = stored_data.get('landmarks', [])
            environmental_adaptations = stored_data.get('environmental_adaptations', [])
            
            if not stored_encodings:
                return False, 0.0, "Sin datos de rostro registrados"
            
            all_scores = []
            detailed_matches = []
            
            # Comparar con encodings principales
            for i, stored_enc in enumerate(stored_encodings):
                if stored_enc is None:
                    continue
                
                stored_enc_array = np.array(stored_enc)
                
                # Distancia euclidiana
                euclidean_dist = face_recognition.face_distance([stored_enc_array], current_encoding)[0]
                euclidean_score = 1 - euclidean_dist
                
                # Similitud coseno
                cosine_sim = 1 - distance.cosine(stored_enc_array, current_encoding)
                
                # Correlación
                correlation = np.corrcoef(stored_enc_array, current_encoding)[0, 1]
                if np.isnan(correlation):
                    correlation = 0
                
                # Puntaje combinado
                combined_score = (
                    euclidean_score * 0.5 +
                    cosine_sim * 0.3 +
                    correlation * 0.2
                )
                
                all_scores.append(combined_score)
                detailed_matches.append({
                    'photo_index': i,
                    'euclidean': euclidean_score,
                    'cosine': cosine_sim,
                    'correlation': correlation,
                    'combined': combined_score
                })
            
            # Comparar con adaptaciones ambientales
            adaptation_scores = []
            for adaptations in environmental_adaptations:
                for adaptation in adaptations:
                    if 'encoding' in adaptation:
                        adapt_enc = np.array(adaptation['encoding'])
                        adapt_dist = face_recognition.face_distance([adapt_enc], current_encoding)[0]
                        adapt_score = 1 - adapt_dist
                        adaptation_scores.append(adapt_score)
                        all_scores.append(adapt_score)
            
            if not all_scores:
                return False, 0.0, "No se pudieron calcular coincidencias"
            
            # Análisis de landmarks si están disponibles
            landmark_bonus = 0
            if current_landmarks is not None and stored_landmarks:
                landmark_similarities = []
                current_lm_array = np.array(current_landmarks)
                
                for stored_lm in stored_landmarks:
                    if stored_lm is not None:
                        stored_lm_array = np.array(stored_lm)
                        min_len = min(len(current_lm_array), len(stored_lm_array))
                        
                        if min_len > 50:  # Suficientes puntos para comparar
                            lm_similarity = 1 - distance.cosine(
                                current_lm_array[:min_len],
                                stored_lm_array[:min_len]
                            )
                            if not np.isnan(lm_similarity):
                                landmark_similarities.append(lm_similarity)
                
                if landmark_similarities:
                    landmark_score = np.mean(landmark_similarities)
                    landmark_bonus = min(landmark_score * 0.1, 0.1)  # Máximo 10% de bonus
            
            # Calcular confianza final
            top_scores = sorted(all_scores, reverse=True)[:5]  # Top 5 matches
            final_confidence = np.mean(top_scores) + landmark_bonus
            final_confidence = min(final_confidence, 1.0)
            
            # Validación estricta
            if self.ADVANCED_CONFIG['strict_mode']:
                high_confidence_matches = [s for s in all_scores if s > 0.65]
                if len(high_confidence_matches) < self.ADVANCED_CONFIG['min_matches']:
                    return False, final_confidence, f"Insuficientes matches de alta confianza ({len(high_confidence_matches)}/{self.ADVANCED_CONFIG['min_matches']})"
            
            is_match = (final_confidence >= self.ADVANCED_CONFIG['min_confidence'] and 
                       final_confidence >= (1 - self.ADVANCED_CONFIG['base_tolerance']))
            
            details = f"Score: {final_confidence:.1%}, Matches: {len(all_scores)}, Adaptations: {len(adaptation_scores)}"
            
            return is_match, final_confidence, details
            
        except Exception as e:
            logger.error(f"Error en comparación avanzada: {e}")
            return False, 0.0, f"Error de comparación: {str(e)}"

    def advanced_verify(self, photo_base64):
        """Verificación avanzada con timeout"""
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
                
                image_array = np.array(image)
                
                # Evaluar y mejorar calidad
                quality_info = self.detect_image_quality(image_array)
                if not quality_info['is_acceptable']:
                    enhanced_versions = self.enhance_image_quality(image)
                    image_array = np.array(enhanced_versions[1])
                
                # Detección robusta de rostros
                face_locations = face_recognition.face_locations(
                    image_array,
                    number_of_times_to_upsample=2,
                    model="hog"
                )
                
                if not face_locations and (time.time() - start_time < self.ADVANCED_CONFIG['verification_timeout']/2):
                    face_locations = face_recognition.face_locations(
                        image_array,
                        model="cnn"
                    )
                
                if not face_locations:
                    return {'success': False, 'error': 'No se detectó rostro en la imagen'}
                
                face_location = face_locations[0]
                
                # Extraer características
                current_encoding = face_recognition.face_encodings(
                    image_array,
                    [face_location],
                    num_jitters=5,
                    model="large"
                )
                
                if not current_encoding:
                    return {'success': False, 'error': 'No se pudieron extraer características faciales'}
                
                current_encoding = current_encoding[0]
                
                # Extraer landmarks si hay tiempo
                current_landmarks = None
                if time.time() - start_time < self.ADVANCED_CONFIG['verification_timeout'] * 0.7:
                    landmark_data = self.extract_detailed_landmarks(image_array)
                    if landmark_data:
                        current_landmarks = landmark_data['points_vector']
                
                best_match = None
                best_confidence = 0
                all_results = []
                
                # Comparar con todos los empleados registrados
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
        
        # Ejecutar con timeout
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