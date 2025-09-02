import face_recognition
import cv2
import numpy as np
import json
import base64
from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageDraw
import io
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from scipy.spatial import distance
from .models import Employee

class ImprovedFaceRecognitionService:
    def __init__(self):
        self.base_confidence = 0.60
        self.glasses_tolerance = 0.50
        self.lighting_tolerance = 0.55
        self.VIDEO_FRAME_RATE = 10 
        self.SMART_CONFIG = {
            'min_photos': 8,
            'base_tolerance': 0.30,
            'adaptive_tolerance': True,
            'min_confidence': 0.65,
            'min_matches': 2,
            'use_landmarks': True,
            'use_augmentation': True,
            'max_tolerance': 0.35,
            'verification_timeout': 5,
            'strict_mode': False,
            'require_full_face': False,
            'min_face_size': 60,
            'expression_variance': True,
            'lighting_adaptation': True,
        }

    def enhance_low_light_image(self, image):
        img_array = np.array(image)
        enhanced_versions = []
        
        img_yuv = cv2.cvtColor(img_array, cv2.COLOR_RGB2YUV)
        img_yuv[:,:,0] = cv2.equalizeHist(img_yuv[:,:,0])
        equalized = cv2.cvtColor(img_yuv, cv2.COLOR_YUV2RGB)
        enhanced_versions.append(Image.fromarray(equalized))
        
        gamma = 1.5
        inv_gamma = 1.0 / gamma
        table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in np.arange(0, 256)]).astype("uint8")
        gamma_corrected = cv2.LUT(img_array, table)
        enhanced_versions.append(Image.fromarray(gamma_corrected))
        
        lab = cv2.cvtColor(img_array, cv2.COLOR_RGB2LAB)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
        lab[:,:,0] = clahe.apply(lab[:,:,0])
        clahe_enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
        enhanced_versions.append(Image.fromarray(clahe_enhanced))
        
        enhanced = ImageEnhance.Brightness(image).enhance(1.4)
        enhanced = ImageEnhance.Contrast(enhanced).enhance(1.3)
        enhanced_versions.append(enhanced)
        
        return enhanced_versions
    
    def detect_brightness_level(self, image_array):
        gray = cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)
        return np.mean(gray)
    
    def create_glasses_variations(self, image):
        variations = [image]
        
        try:
            enhanced = ImageEnhance.Contrast(image).enhance(1.5)
            variations.append(enhanced)
            
            img_array = np.array(image)
            hsv = cv2.cvtColor(img_array, cv2.COLOR_RGB2HSV)
            
            bright_mask = hsv[:,:,2] > 200
            hsv[bright_mask, 1] = hsv[bright_mask, 1] * 0.7
            
            no_glare = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)
            variations.append(Image.fromarray(no_glare))
            
            blurred = image.filter(ImageFilter.GaussianBlur(0.5))
            variations.append(blurred)
            
        except Exception as e:
            print(f"Error creando variaciones de lentes: {e}")
        
        return variations

    def robust_face_detection(self, image_array):
        face_locations = []
        
        try:
            locations = face_recognition.face_locations(image_array, model="hog")
            if locations:
                face_locations.extend(locations)
        except:
            pass
        
        if not face_locations:
            try:
                locations = face_recognition.face_locations(image_array, model="cnn")
                if locations:
                    face_locations.extend(locations)
            except:
                pass
        
        if not face_locations:
            try:
                enhanced = cv2.equalizeHist(cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY))
                enhanced_rgb = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2RGB)
                locations = face_recognition.face_locations(enhanced_rgb, model="hog")
                if locations:
                    face_locations.extend(locations)
            except:
                pass
        
        unique_faces = []
        for face in face_locations:
            is_duplicate = False
            for existing in unique_faces:
                if all(abs(face[i] - existing[i]) < 30 for i in range(4)):
                    is_duplicate = True
                    break
            if not is_duplicate:
                unique_faces.append(face)
        
        return unique_faces

    def extract_face_landmarks(self, image_array):
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

    def create_augmented_encodings(self, image_array, face_location):
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
        
        bright = ImageEnhance.Brightness(image).enhance(1.3)
        bright_encoding = face_recognition.face_encodings(
            np.array(bright), [face_location], num_jitters=2
        )
        if bright_encoding:
            augmented_encodings.append(bright_encoding[0])
        
        contrast = ImageEnhance.Contrast(image).enhance(1.5)
        contrast_encoding = face_recognition.face_encodings(
            np.array(contrast), [face_location], num_jitters=2
        )
        if contrast_encoding:
            augmented_encodings.append(contrast_encoding[0])
        
        blurred = image.filter(ImageFilter.GaussianBlur(radius=0.5))
        blur_encoding = face_recognition.face_encodings(
            np.array(blurred), [face_location], num_jitters=2
        )
        if blur_encoding:
            augmented_encodings.append(blur_encoding[0])
        
        return augmented_encodings

    def process_registration_photos(self, photos_base64):
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
                    landmarks = self.extract_face_landmarks(image_array)
                    if landmarks is not None:
                        all_landmarks.append(landmarks.tolist())
                    else:
                        all_landmarks.append(None)
                except:
                    all_landmarks.append(None)
                
                if encodings and self.SMART_CONFIG['use_augmentation']:
                    try:
                        augmented = self.create_augmented_encodings(image_array, face_location)
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

    def intelligent_face_comparison(self, stored_data, current_encoding, current_landmarks, quick_mode=False):
        stored_encodings = stored_data.get('encodings', [])
        stored_landmarks = stored_data.get('landmarks', [])
        stored_augmented = stored_data.get('augmented', [])
        
        if not stored_encodings:
            return False, 0.0, "Sin datos de rostro"
        
        if self.SMART_CONFIG['strict_mode'] and current_landmarks is None:
            return False, 0.0, "No se detectaron puntos faciales"
        
        all_scores = []
        high_quality_scores = []
        
        all_stored_encs = [np.array(e) for e in stored_encodings if e is not None]
        for aug_list in stored_augmented:
            all_stored_encs.extend([np.array(e) for e in aug_list if e is not None])

        for stored_enc_array in all_stored_encs:
            euclidean_dist = face_recognition.face_distance([stored_enc_array], current_encoding)[0]
            
            if self.SMART_CONFIG['strict_mode'] and euclidean_dist > 0.6:
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
        
        if self.SMART_CONFIG['strict_mode']:
            if len(high_quality_scores) < self.SMART_CONFIG['min_matches']:
                return False, 0.0, f"Insuficientes coincidencias ({len(high_quality_scores)}/{self.SMART_CONFIG['min_matches']})"
        
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
                
                if self.SMART_CONFIG['strict_mode']:
                    landmark_match = landmark_score > 0.65
                    if not landmark_match:
                        return False, 0.0, f"Geometría facial no coincide ({landmark_score:.1%})"
        
        if not all_scores:
            return False, 0.0, "No hay coincidencias"
        
        if self.SMART_CONFIG['strict_mode'] and high_quality_scores:
            final_score = np.mean(high_quality_scores)
        else:
            final_score = np.percentile(all_scores, 60)
        
        if final_score < self.SMART_CONFIG['min_confidence']:
            return False, final_score, f"Confianza insuficiente ({final_score:.1%} < {self.SMART_CONFIG['min_confidence']:.0%})"
        
        is_match = final_score >= (1 - self.SMART_CONFIG['base_tolerance']) and final_score >= self.SMART_CONFIG['min_confidence']
        confidence = min(1.0, final_score)
        
        return is_match, confidence, f"Score: {confidence:.1%}"

    def process_video_for_encodings(self, video_path):
        """Procesa un video para encontrar y devolver una lista de encodings faciales únicos."""
        try:
            video_capture = cv2.VideoCapture(video_path)
            if not video_capture.isOpened():
                return None, "No se pudo abrir el archivo de video"
                
            encodings = []
            frame_count = 0
            
            while True:
                ret, frame = video_capture.read()
                if not ret:
                    break
                
                frame_count += 1
                if frame_count % (int(video_capture.get(cv2.CAP_PROP_FPS)) / self.VIDEO_FRAME_RATE) != 0:
                    continue

                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                face_locations = face_recognition.face_locations(rgb_frame)
                frame_encodings = face_recognition.face_encodings(rgb_frame, face_locations)
                
                if frame_encodings:
                    for encoding in frame_encodings:
                        encodings.append(encoding.tolist())
            
            video_capture.release()
            
            if not encodings:
                return None, "No se detectó ningún rostro en el video."

            unique_encodings = [np.array(encodings[0])]
            for new_enc in encodings[1:]:
                is_unique = True
                for unique_enc in unique_encodings:
                    if face_recognition.face_distance([unique_enc], new_enc)[0] < 0.4:
                        is_unique = False
                        break
                if is_unique:
                    unique_encodings.append(np.array(new_enc))
            
            return [enc.tolist() for enc in unique_encodings], "Encodings extraídos exitosamente."

        except Exception as e:
            print(f"Error procesando video: {e}")
            return None, f"Error interno: {e}"

    def get_face_encoding(self, image_data_list):
        encodings = []
        for image_data in image_data_list:
            if ',' in image_data:
                image_data = base64.b64decode(image_data.split(',')[1])
            else:
                image_data = base64.b64decode(image_data)
            
            try:
                image = face_recognition.load_image_file(io.BytesIO(image_data))
                
                face_encodings = face_recognition.face_encodings(image)
                
                if not face_encodings:
                    enhanced_images = self.enhance_low_light_image(Image.fromarray(image))
                    for enhanced_image in enhanced_images:
                        enhanced_image_array = np.array(enhanced_image)
                        face_encodings_enhanced = face_recognition.face_encodings(enhanced_image_array)
                        if face_encodings_enhanced:
                            face_encodings = face_encodings_enhanced
                            break
                
                if face_encodings:
                    encodings.append(face_encodings[0])
            except Exception as e:
                print(f"Error procesando imagen: {e}")
                
        return encodings
    
    def intelligent_verify(self, photo_base64):
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
                
                if not face_locations and (time.time() - start_time < self.SMART_CONFIG['verification_timeout']/2):
                    try:
                        face_locations = face_recognition.face_locations(
                            image_array,
                            model="cnn"
                        )
                    except:
                        pass
                
                if not face_locations:
                    return {'success': False, 'error': 'No se detectó rostro'}
                
                if self.SMART_CONFIG.get('require_full_face', True):
                    face_valid, face_message = self.verify_face_quality(image_array, face_locations[0])
                    if not face_valid:
                        return {'success': False, 'error': f'Rostro inválido: {face_message}'}
                
                current_encoding = face_recognition.face_encodings(
                    image_array,
                    face_locations,
                    num_jitters=2,
                    model="large"
                )[0]
                
                current_landmarks = None
                if time.time() - start_time < self.SMART_CONFIG['verification_timeout'] * 0.8:
                    try:
                        current_landmarks = self.extract_face_landmarks(image_array)
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
                    if time.time() - start_time > self.SMART_CONFIG['verification_timeout'] * 0.9:
                        break
                    
                    try:
                        stored_encodings_json = employee.face_encoding
                        if not stored_encodings_json:
                            continue
                        
                        stored_data = json.loads(stored_encodings_json)
                        
                        if isinstance(stored_data, list):
                            # Formato de video
                            known_encodings_np = [np.array(e) for e in stored_data]
                            distances = face_recognition.face_distance(known_encodings_np, current_encoding)
                            min_distance = np.min(distances)
                            confidence = 1 - min_distance
                            
                            if confidence > best_confidence:
                                best_confidence = confidence
                                best_match = employee
                                all_results.append({'employee': employee, 'confidence': confidence})

                        elif isinstance(stored_data, dict):
                            # Formato de fotos
                            is_match, confidence, details = self.intelligent_face_comparison(
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
                result = future.result(timeout=self.SMART_CONFIG['verification_timeout'])
                return result.get('data'), result.get('error')
            except FutureTimeoutError:
                future.cancel()
                return None, "Timeout: La verificación excedió el tiempo límite."
            except Exception as e:
                return None, f"Error en verificación: {str(e)}"

    def verify_face_quality(self, image_array, face_location):
        """Verificar que el rostro sea de calidad suficiente y esté completo"""
        top, right, bottom, left = face_location
        
        face_width = right - left
        face_height = bottom - top
        
        if face_width < self.SMART_CONFIG['min_face_size'] or face_height < self.SMART_CONFIG['min_face_size']:
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