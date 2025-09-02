import face_recognition
import cv2
import numpy as np
import json
import base64
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import io

class ImprovedFaceRecognitionService:
    def __init__(self):
        # Configuración más tolerante para cambios físicos
        self.base_confidence = 0.60  # Reducido para ser más permisivo
        self.glasses_tolerance = 0.50  # Tolerancia especial para lentes
        self.lighting_tolerance = 0.55  # Tolerancia para poca luz
    
    def enhance_low_light_image(self, image):
        """Mejorar imágenes con poca iluminación"""
        # Convertir a array numpy
        img_array = np.array(image)
        
        # Mejoras para poca luz
        enhanced_versions = []
        
        # 1. Ecualización de histograma
        img_yuv = cv2.cvtColor(img_array, cv2.COLOR_RGB2YUV)
        img_yuv[:,:,0] = cv2.equalizeHist(img_yuv[:,:,0])
        equalized = cv2.cvtColor(img_yuv, cv2.COLOR_YUV2RGB)
        enhanced_versions.append(Image.fromarray(equalized))
        
        # 2. Corrección Gamma para oscuridad
        gamma = 1.5
        inv_gamma = 1.0 / gamma
        table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in np.arange(0, 256)]).astype("uint8")
        gamma_corrected = cv2.LUT(img_array, table)
        enhanced_versions.append(Image.fromarray(gamma_corrected))
        
        # 3. CLAHE (Contrast Limited Adaptive Histogram Equalization)
        lab = cv2.cvtColor(img_array, cv2.COLOR_RGB2LAB)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
        lab[:,:,0] = clahe.apply(lab[:,:,0])
        clahe_enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
        enhanced_versions.append(Image.fromarray(clahe_enhanced))
        
        # 4. Brillo y contraste automático
        enhanced = ImageEnhance.Brightness(image).enhance(1.4)
        enhanced = ImageEnhance.Contrast(enhanced).enhance(1.3)
        enhanced_versions.append(enhanced)
        
        return enhanced_versions
    
    def detect_brightness_level(self, image_array):
        """Detectar el nivel de brillo de la imagen"""
        gray = cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)
        return np.mean(gray)
    
    def create_glasses_variations(self, image):
        """Crear variaciones para personas con/sin lentes"""
        variations = [image]  # Original
        
        try:
            # Aumentar contraste en área de ojos
            enhanced = ImageEnhance.Contrast(image).enhance(1.5)
            variations.append(enhanced)
            
            # Reducir reflejos (simular quitar lentes)
            img_array = np.array(image)
            hsv = cv2.cvtColor(img_array, cv2.COLOR_RGB2HSV)
            
            # Reducir saturación en áreas brillantes (reflejos de lentes)
            bright_mask = hsv[:,:,2] > 200
            hsv[bright_mask, 1] = hsv[bright_mask, 1] * 0.7
            
            no_glare = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)
            variations.append(Image.fromarray(no_glare))
            
            # Suavizar para simular sin lentes
            blurred = image.filter(ImageFilter.GaussianBlur(0.5))
            variations.append(blurred)
            
        except Exception as e:
            print(f"Error creando variaciones de lentes: {e}")
        
        return variations
    
    def robust_face_detection(self, image_array):
        """Detección de rostros más robusta"""
        face_locations = []
        
        # Método 1: HOG estándar
        try:
            locations = face_recognition.face_locations(image_array, model="hog")
            if locations:
                face_locations.extend(locations)
        except:
            pass
        
        # Método 2: CNN si no encuentra con HOG
        if not face_locations:
            try:
                locations = face_recognition.face_locations(image_array, model="cnn")
                if locations:
                    face_locations.extend(locations)
            except:
                pass
        
        # Método 3: Con imagen mejorada si no encuentra rostro
        if not face_locations:
            try:
                enhanced = cv2.equalizeHist(cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY))
                enhanced_rgb = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2RGB)
                locations = face_recognition.face_locations(enhanced_rgb, model="hog")
                if locations:
                    face_locations.extend(locations)
            except:
                pass
        
        # Remover duplicados
        unique_faces = []
        for face in face_locations:
            is_duplicate = False
            for existing in unique_faces:
                # Si las caras están muy cerca, es duplicado
                if all(abs(face[i] - existing[i]) < 30 for i in range(4)):
                    is_duplicate = True
                    break
            if not is_duplicate:
                unique_faces.append(face)
        
        return unique_faces
    
    def process_photo_with_auto_enhance(self, base64_image):
        """Procesar foto con mejoras automáticas"""
        try:
            # Decodificar imagen
            if ',' in base64_image:
                image_data = base64.b64decode(base64_image.split(',')[1])
            else:
                image_data = base64.b64decode(base64_image)
            
            image = Image.open(io.BytesIO(image_data))
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Redimensionar si es muy grande
            if image.width > 1024:
                ratio = 1024 / image.width
                new_height = int(image.height * ratio)
                image = image.resize((1024, new_height), Image.Resampling.LANCZOS)
            
            image_array = np.array(image)
            brightness = self.detect_brightness_level(image_array)
            
            print(f"🔍 Brillo detectado: {brightness:.1f}")
            
            # Generar versiones mejoradas según condiciones
            all_versions = []
            
            # Siempre incluir original
            all_versions.append(('original', image))
            
            # Si hay poca luz (< 80), aplicar mejoras
            if brightness < 80:
                print("💡 Aplicando mejoras para poca luz...")
                enhanced_versions = self.enhance_low_light_image(image)
                for i, enhanced in enumerate(enhanced_versions):
                    all_versions.append((f'low_light_{i}', enhanced))
            
            # Crear variaciones para lentes
            glasses_variations = self.create_glasses_variations(image)
            for i, variation in enumerate(glasses_variations):
                all_versions.append((f'glasses_var_{i}', variation))
            
            # Procesar cada versión
            all_encodings = []
            successful_versions = []
            
            for version_name, version_image in all_versions:
                try:
                    version_array = np.array(version_image)
                    face_locations = self.robust_face_detection(version_array)
                    
                    if face_locations:
                        # Usar la cara más grande
                        best_face = max(face_locations, key=lambda f: (f[2]-f[0])*(f[1]-f[3]))
                        
                        # Generar encoding con menos jitters para ser más rápido
                        encodings = face_recognition.face_encodings(
                            version_array,
                            [best_face],
                            num_jitters=3,  # Reducido para velocidad
                            model="large"
                        )
                        
                        if encodings:
                            all_encodings.append({
                                'encoding': encodings[0].tolist(),
                                'version': version_name,
                                'face_location': best_face,
                                'brightness': self.detect_brightness_level(version_array)
                            })
                            successful_versions.append(version_name)
                            print(f"✅ Encoding exitoso para versión: {version_name}")
                    
                except Exception as e:
                    print(f"❌ Error procesando {version_name}: {e}")
                    continue
            
            if not all_encodings:
                return None, "No se pudo detectar rostro en ninguna versión"
            
            # Seleccionar los mejores encodings
            main_encoding = all_encodings[0]['encoding']  # Usar el primero como principal
            alternative_encodings = [enc['encoding'] for enc in all_encodings[1:]]
            
            result = {
                'main': main_encoding,
                'alternatives': alternative_encodings,
                'versions_processed': len(all_versions),
                'successful_versions': successful_versions,
                'brightness_level': brightness,
                'enhanced_for_low_light': brightness < 80
            }
            
            print(f"✅ Procesamiento exitoso: {len(all_encodings)} encodings generados")
            return result, f"Procesado con {len(successful_versions)} versiones exitosas"
            
        except Exception as e:
            return None, f"Error procesando imagen: {str(e)}"
    
    def flexible_face_comparison(self, stored_encodings_data, current_encoding):
        """Comparación más flexible para cambios físicos"""
        try:
            # Obtener encodings almacenados
            main_stored = np.array(stored_encodings_data.get('main', []))
            alternatives_stored = stored_encodings_data.get('alternatives', [])
            
            if len(main_stored) == 0:
                return False, 0.0, "Sin encodings almacenados"
            
            all_stored = [main_stored] + [np.array(alt) for alt in alternatives_stored if len(alt) > 0]
            current_enc = np.array(current_encoding)
            
            all_confidences = []
            
            # Comparar con todos los encodings almacenados
            for stored_enc in all_stored:
                try:
                    # Distancia euclidiana (método principal de face_recognition)
                    distance = face_recognition.face_distance([stored_enc], current_enc)[0]
                    euclidean_confidence = max(0, 1 - distance)
                    
                    # Similitud coseno (mejor para variaciones de iluminación)
                    cosine_sim = np.dot(stored_enc, current_enc) / (
                        np.linalg.norm(stored_enc) * np.linalg.norm(current_enc)
                    )
                    cosine_confidence = (cosine_sim + 1) / 2  # Normalizar a 0-1
                    
                    # Correlación de Pearson
                    correlation = np.corrcoef(stored_enc, current_enc)[0, 1]
                    correlation = max(-1, min(1, correlation))  # Clamp
                    correlation_confidence = (correlation + 1) / 2
                    
                    # Promedio ponderado (euclidiana tiene más peso)
                    combined_confidence = (
                        euclidean_confidence * 0.6 +
                        cosine_confidence * 0.25 +
                        correlation_confidence * 0.15
                    )
                    
                    all_confidences.append({
                        'euclidean': euclidean_confidence,
                        'cosine': cosine_confidence,
                        'correlation': correlation_confidence,
                        'combined': combined_confidence,
                        'distance': distance
                    })
                    
                except Exception as e:
                    print(f"Error comparando encoding: {e}")
                    continue
            
            if not all_confidences:
                return False, 0.0, "Error en todas las comparaciones"
            
            # Obtener la mejor coincidencia
            best_match = max(all_confidences, key=lambda x: x['combined'])
            final_confidence = best_match['combined']
            
            # Determinar umbral dinámico
            distance = best_match['distance']
            
            # Umbrales más permisivos
            if distance <= 0.4:  # Muy similar
                threshold = 0.60
            elif distance <= 0.5:  # Similar con cambios menores
                threshold = 0.50
            elif distance <= 0.6:  # Cambios moderados (lentes, iluminación)
                threshold = 0.45
            else:  # Cambios mayores
                threshold = 0.40
            
            is_match = final_confidence >= threshold
            
            # Información detallada para debug
            match_info = f"Dist: {distance:.3f}, Conf: {final_confidence:.1%}, Umbral: {threshold:.1%}"
            
            print(f"🔍 Comparación: {match_info} -> {'✅ MATCH' if is_match else '❌ NO MATCH'}")
            
            return is_match, final_confidence, match_info
            
        except Exception as e:
            print(f"❌ Error en comparación: {str(e)}")
            return False, 0.0, f"Error: {str(e)}"
    
    def encode_face_from_base64(self, base64_image):
        """Método principal para encoding (compatible)"""
        return self.process_photo_with_auto_enhance(base64_image)
    
    def compare_faces(self, stored_data, current_encoding, tolerance=None):
        """Método principal para comparación (compatible)"""
        if isinstance(stored_data, dict):
            # Nuevo formato con múltiples encodings
            return self.flexible_face_comparison(stored_data, current_encoding)
        else:
            # Formato legacy - convertir
            legacy_data = {
                'main': stored_data if isinstance(stored_data, list) else stored_data.tolist(),
                'alternatives': []
            }
            return self.flexible_face_comparison(legacy_data, current_encoding)
    
    def validate_image_quality(self, base64_image):
        """Validación más permisiva"""
        try:
            if ',' in base64_image:
                image_data = base64.b64decode(base64_image.split(',')[1])
            else:
                image_data = base64.b64decode(base64_image)
            
            image = Image.open(io.BytesIO(image_data))
            
            # Validaciones básicas
            if image.width < 150 or image.height < 150:
                return False, "Imagen muy pequeña (mínimo 150x150)"
            
            if image.width > 10000 or image.height > 10000:
                return False, "Imagen muy grande"
            
            # Verificar que no esté completamente negra o blanca
            image_array = np.array(image.convert('L'))
            mean_brightness = np.mean(image_array)
            
            if mean_brightness < 10:
                return False, "Imagen muy oscura - usa el flash o mejora la iluminación"
            elif mean_brightness > 245:
                return False, "Imagen muy clara (sobreexpuesta)"
            
            print(f"✅ Imagen válida: {image.width}x{image.height}, brillo: {mean_brightness:.1f}")
            return True, "Imagen válida"
            
        except Exception as e:
            return False, f"Error validando imagen: {str(e)}"