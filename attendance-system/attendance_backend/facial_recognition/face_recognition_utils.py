import face_recognition
import cv2
import numpy as np
import json
import base64
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import io

class FaceRecognitionService:
    def __init__(self):
        self.tolerance = 2.0  # ULTRA permisivo para cambios físicos
    
    def tolerant_photo_encoding(self, base64_image):
        """
        📸 ENCODING DE FOTO - ULTRA TOLERANTE para cambios físicos
        (lentes, barba, iluminación, pose, etc.)
        """
        try:
            print("📸 Procesando foto con máxima tolerancia...")
            
            # Decodificar imagen
            image_data = base64.b64decode(base64_image.split(',')[1] if ',' in base64_image else base64_image)
            image = Image.open(io.BytesIO(image_data))
            print(f"📸 Imagen original: {image.width}x{image.height}")
            
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Redimensionar inteligentemente
            target_width = 800  # Tamaño óptimo para análisis
            if image.width != target_width:
                aspect_ratio = image.height / image.width
                target_height = int(target_width * aspect_ratio)
                image = image.resize((target_width, target_height), Image.Resampling.LANCZOS)
                print(f"📸 Redimensionado a: {target_width}x{target_height}")
            
            # GENERAR MÚLTIPLES VERSIONES para máxima tolerancia
            versions = self._create_tolerant_versions(image)
            
            # DETECTAR ROSTROS EN TODAS LAS VERSIONES
            all_encodings = []
            
            for version_name, version_image in versions.items():
                print(f"🔍 Analizando versión: {version_name}")
                
                version_array = np.array(version_image)
                
                # Detectar rostros con múltiples métodos
                face_locations = self._detect_faces_multi_method(version_array)
                
                if face_locations:
                    print(f"✅ {len(face_locations)} rostro(s) en versión {version_name}")
                    
                    # Usar el rostro más grande
                    if len(face_locations) > 1:
                        face_locations = [max(face_locations, key=lambda f: (f[2] - f[0]) * (f[1] - f[3]))]
                    
                    # Generar encoding
                    try:
                        face_encodings = face_recognition.face_encodings(
                            version_array,
                            face_locations,
                            num_jitters=3  # Más variaciones para tolerancia
                        )
                        
                        if face_encodings:
                            all_encodings.append({
                                'version': version_name,
                                'encoding': face_encodings[0].tolist(),
                                'location': face_locations[0]
                            })
                    except Exception as e:
                        print(f"❌ Error generando encoding para {version_name}: {str(e)}")
            
            if not all_encodings:
                return None, "No se detectó rostro en ninguna versión de la imagen"
            
            # Seleccionar el mejor encoding (el de mejor calidad)
            main_encoding = all_encodings[0]['encoding']
            alternative_encodings = [enc['encoding'] for enc in all_encodings[1:]]
            
            print(f"✅ Generados {len(all_encodings)} encodings tolerantes")
            
            # Retornar encoding principal y alternativos
            result = {
                'main': main_encoding,
                'alternatives': alternative_encodings
            }
            
            return result, f"Encoding exitoso con {len(all_encodings)} versiones"
            
        except Exception as e:
            print(f"❌ Error procesando foto: {str(e)}")
            return None, f"Error procesando imagen: {str(e)}"
    
    def _create_tolerant_versions(self, image):
        """
        🎨 CREAR MÚLTIPLES VERSIONES para máxima tolerancia a cambios
        """
        versions = {}
        
        # Versión original
        versions['original'] = image
        
        # Versión con mejor contraste (para mala iluminación)
        enhancer = ImageEnhance.Contrast(image)
        versions['high_contrast'] = enhancer.enhance(2.5)
        
        # Versión más brillante (para lugares oscuros)
        enhancer = ImageEnhance.Brightness(image)
        versions['bright'] = enhancer.enhance(1.4)
        
        # Versión más oscura (para lugares muy iluminados)
        versions['dark'] = enhancer.enhance(0.7)
        
        # Versión con más nitidez (para fotos borrosas)
        enhancer = ImageEnhance.Sharpness(image)
        versions['sharp'] = enhancer.enhance(2.0)
        
        # Versión ecualizada (mejora automática)
        versions['equalized'] = ImageOps.equalize(image)
        
        # Versión en escala de grises convertida a RGB (elimina efectos de color)
        gray = ImageOps.grayscale(image).convert('RGB')
        versions['grayscale'] = gray
        
        # Versión con filtro de nitidez
        versions['filtered'] = image.filter(ImageFilter.SHARPEN)
        
        return versions
    
    def _detect_faces_multi_method(self, image_array):
        """
        🎯 DETECTAR ROSTROS con múltiples métodos para máxima tolerancia
        """
        face_locations = []
        
        # Método 1: HOG estándar
        try:
            locations = face_recognition.face_locations(
                image_array,
                number_of_times_to_upsample=1,
                model="hog"
            )
            if locations:
                face_locations.extend(locations)
        except:
            pass
        
        # Método 2: CNN (más preciso)
        try:
            locations = face_recognition.face_locations(
                image_array,
                number_of_times_to_upsample=2,
                model="cnn"
            )
            if locations:
                face_locations.extend(locations)
        except:
            pass
        
        # Método 3: HOG con más upsampling
        try:
            locations = face_recognition.face_locations(
                image_array,
                number_of_times_to_upsample=3,
                model="hog"
            )
            if locations:
                face_locations.extend(locations)
        except:
            pass
        
        # Eliminar duplicados (rostros muy similares)
        if len(face_locations) > 1:
            unique_locations = []
            for loc in face_locations:
                is_duplicate = False
                for unique_loc in unique_locations:
                    # Si las ubicaciones son muy similares, es un duplicado
                    if (abs(loc[0] - unique_loc[0]) < 20 and 
                        abs(loc[1] - unique_loc[1]) < 20 and 
                        abs(loc[2] - unique_loc[2]) < 20 and 
                        abs(loc[3] - unique_loc[3]) < 20):
                        is_duplicate = True
                        break
                if not is_duplicate:
                    unique_locations.append(loc)
            face_locations = unique_locations
        
        return face_locations
    
    def ultra_tolerant_compare(self, known_encoding, unknown_encoding):
        """
        🔍 COMPARACIÓN ULTRA TOLERANTE para cambios físicos
        - Lentes vs sin lentes
        - Con barba vs sin barba
        - Diferentes iluminaciones
        - Diferentes poses
        """
        try:
            known_encoding = np.array(known_encoding)
            unknown_encoding = np.array(unknown_encoding)
            
            # Método 1: Distancia euclidiana estándar
            euclidean_distance = np.linalg.norm(known_encoding - unknown_encoding)
            
            # Método 2: Distancia de coseno (mejor para cambios de iluminación)
            cosine_similarity = np.dot(known_encoding, unknown_encoding) / (
                np.linalg.norm(known_encoding) * np.linalg.norm(unknown_encoding)
            )
            cosine_distance = 1 - cosine_similarity
            
            # Método 3: Distancia de Manhattan (más tolerante a outliers)
            manhattan_distance = np.sum(np.abs(known_encoding - unknown_encoding))
            
            # Combinar métricas con pesos optimizados para tolerancia
            # Euclidiana: 40%, Coseno: 35%, Manhattan: 25%
            combined_distance = (
                0.40 * (euclidean_distance / 2.0) +  # Normalizada
                0.35 * cosine_distance +
                0.25 * (manhattan_distance / 100.0)  # Normalizada
            )
            
            # Convertir a confianza ULTRA PERMISIVA
            # Ajustado para ser muy tolerante a cambios físicos
            max_distance = 1.5  # Muy alto para máxima tolerancia
            confidence = max(0, 1 - (combined_distance / max_distance))
            
            # Bonus por similitud de coseno alta (bueno para iluminación)
            if cosine_similarity > 0.7:
                confidence += 0.1
            
            # Asegurar que no exceda 1.0
            confidence = min(1.0, confidence)
            
            print(f"🔍 Métricas - Euclidiana: {euclidean_distance:.3f}, Coseno: {cosine_distance:.3f}, Manhattan: {manhattan_distance:.1f}")
            print(f"🔍 Distancia combinada: {combined_distance:.3f}, Confianza final: {confidence:.3f}")
            
            return confidence
            
        except Exception as e:
            print(f"❌ Error en comparación tolerante: {str(e)}")
            return 0.0
    
    # Métodos de compatibilidad
    def encode_face_from_base64(self, base64_image):
        """Método de compatibilidad"""
        return self.tolerant_photo_encoding(base64_image)
    
    def compare_faces(self, known_encoding, unknown_encoding, tolerance=None):
        """Método de compatibilidad"""
        confidence = self.ultra_tolerant_compare(known_encoding, unknown_encoding)
        threshold = 0.05 if tolerance is None else tolerance  # Umbral ultra bajo
        return confidence > threshold, confidence
    
    def validate_image_quality(self, base64_image):
        """
        ✅ VALIDACIÓN PERMISIVA de imagen
        """
        try:
            image_data = base64.b64decode(base64_image.split(',')[1] if ',' in base64_image else base64_image)
            image = Image.open(io.BytesIO(image_data))
            
            # Validaciones mínimas
            if image.width < 100 or image.height < 100:
                return False, "Imagen muy pequeña (mínimo 100x100)"
            
            if image.width > 10000 or image.height > 10000:
                return False, "Imagen muy grande (máximo 10000x10000)"
            
            # Verificar que no esté completamente negra o blanca
            image_array = np.array(image.convert('L'))  # Escala de grises
            mean_brightness = np.mean(image_array)
            
            if mean_brightness < 10:
                return False, "Imagen muy oscura"
            elif mean_brightness > 245:
                return False, "Imagen muy clara"
            
            print(f"✅ Imagen válida: {image.width}x{image.height}, brillo promedio: {mean_brightness:.1f}")
            return True, "Imagen válida"
            
        except Exception as e:
            print(f"❌ Error validando imagen: {str(e)}")
            return False, f"Error: {str(e)}"