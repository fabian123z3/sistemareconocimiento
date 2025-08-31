import face_recognition
import cv2
import numpy as np
import json
import base64
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import io

class FaceRecognitionService:
    def __init__(self):
        self.confidence_threshold = 0.85  # 85% de similitud requerida
    
    def tolerant_photo_encoding(self, base64_image):
        """
        📸 ENCODING DE FOTO - OPTIMIZADO PARA 85% DE CONFIANZA
        """
        try:
            print("📸 Procesando foto para 85% de confianza...")
            
            # Decodificar imagen
            image_data = base64.b64decode(base64_image.split(',')[1] if ',' in base64_image else base64_image)
            image = Image.open(io.BytesIO(image_data))
            print(f"📸 Imagen original: {image.width}x{image.height}")
            
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Redimensionar para análisis óptimo
            target_width = 1024  # Mayor resolución para mejor precisión
            if image.width != target_width:
                aspect_ratio = image.height / image.width
                target_height = int(target_width * aspect_ratio)
                image = image.resize((target_width, target_height), Image.Resampling.LANCZOS)
                print(f"📸 Redimensionado a: {target_width}x{target_height}")
            
            # GENERAR VERSIONES MEJORADAS para mejor análisis
            versions = self._create_enhanced_versions(image)
            
            # DETECTAR ROSTROS EN TODAS LAS VERSIONES
            all_encodings = []
            
            for version_name, version_image in versions.items():
                print(f"🔍 Analizando versión: {version_name}")
                
                version_array = np.array(version_image)
                
                # Detectar rostros con alta precisión
                face_locations = self._detect_faces_high_precision(version_array)
                
                if face_locations:
                    print(f"✅ {len(face_locations)} rostro(s) en versión {version_name}")
                    
                    # Usar el rostro más grande y centrado
                    if len(face_locations) > 1:
                        face_locations = [self._select_best_face(face_locations)]
                    
                    # Generar encoding con alta precisión
                    try:
                        face_encodings = face_recognition.face_encodings(
                            version_array,
                            face_locations,
                            num_jitters=5,  # Más precisión para 85% threshold
                            model="large"  # Modelo más preciso
                        )
                        
                        if face_encodings:
                            all_encodings.append({
                                'version': version_name,
                                'encoding': face_encodings[0].tolist(),
                                'location': face_locations[0],
                                'quality_score': self._calculate_face_quality(version_array, face_locations[0])
                            })
                    except Exception as e:
                        print(f"❌ Error generando encoding para {version_name}: {str(e)}")
            
            if not all_encodings:
                return None, "No se detectó rostro en ninguna versión de la imagen"
            
            # Seleccionar el encoding de mejor calidad
            best_encoding = max(all_encodings, key=lambda x: x['quality_score'])
            alternative_encodings = [enc['encoding'] for enc in all_encodings if enc != best_encoding]
            
            print(f"✅ Generados {len(all_encodings)} encodings, mejor calidad: {best_encoding['quality_score']:.3f}")
            
            # Retornar encoding principal y alternativos
            result = {
                'main': best_encoding['encoding'],
                'alternatives': alternative_encodings,
                'quality_score': best_encoding['quality_score'],
                'version_used': best_encoding['version']
            }
            
            return result, f"Encoding exitoso con {len(all_encodings)} versiones"
            
        except Exception as e:
            print(f"❌ Error procesando foto: {str(e)}")
            return None, f"Error procesando imagen: {str(e)}"
    
    def _create_enhanced_versions(self, image):
        """
        🎨 CREAR VERSIONES MEJORADAS para análisis de alta precisión
        """
        versions = {}
        
        # Versión original
        versions['original'] = image
        
        # Versión con contraste optimizado
        enhancer = ImageEnhance.Contrast(image)
        versions['enhanced_contrast'] = enhancer.enhance(1.8)
        
        # Versión con brillo optimizado
        enhancer = ImageEnhance.Brightness(image)
        versions['enhanced_brightness'] = enhancer.enhance(1.2)
        
        # Versión con nitidez mejorada
        enhancer = ImageEnhance.Sharpness(image)
        versions['enhanced_sharpness'] = enhancer.enhance(1.5)
        
        # Versión ecualizada (mejora automática)
        versions['equalized'] = ImageOps.equalize(image)
        
        # Versión con filtro de mejora
        versions['filtered'] = image.filter(ImageFilter.SHARPEN)
        
        # Versión normalizada (mejor para condiciones variables)
        normalized = ImageOps.autocontrast(image)
        versions['normalized'] = normalized
        
        return versions
    
    def _detect_faces_high_precision(self, image_array):
        """
        🎯 DETECTAR ROSTROS con alta precisión para 85% threshold
        """
        face_locations = []
        
        # Método 1: CNN (más preciso)
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
        
        # Método 2: HOG con upsampling
        try:
            locations = face_recognition.face_locations(
                image_array,
                number_of_times_to_upsample=2,
                model="hog"
            )
            if locations:
                face_locations.extend(locations)
        except:
            pass
        
        # Eliminar duplicados cercanos
        if len(face_locations) > 1:
            unique_locations = []
            for loc in face_locations:
                is_duplicate = False
                for unique_loc in unique_locations:
                    if self._faces_overlap(loc, unique_loc):
                        is_duplicate = True
                        break
                if not is_duplicate:
                    unique_locations.append(loc)
            face_locations = unique_locations
        
        return face_locations
    
    def _faces_overlap(self, face1, face2, threshold=30):
        """Verificar si dos rostros se superponen"""
        return (abs(face1[0] - face2[0]) < threshold and 
                abs(face1[1] - face2[1]) < threshold and 
                abs(face1[2] - face2[2]) < threshold and 
                abs(face1[3] - face2[3]) < threshold)
    
    def _select_best_face(self, face_locations):
        """Seleccionar el mejor rostro basado en tamaño y posición"""
        # Preferir rostros más grandes y centrados
        scored_faces = []
        
        for face in face_locations:
            top, right, bottom, left = face
            
            # Tamaño del rostro
            face_size = (bottom - top) * (right - left)
            
            # Posición central (bonus para rostros centrados)
            center_y = (top + bottom) / 2
            center_x = (left + right) / 2
            
            # Score combinado
            score = face_size * 0.8 + (1000 - abs(center_y - 512)) * 0.1 + (1000 - abs(center_x - 512)) * 0.1
            
            scored_faces.append((face, score))
        
        # Retornar el rostro con mejor score
        return max(scored_faces, key=lambda x: x[1])[0]
    
    def _calculate_face_quality(self, image_array, face_location):
        """Calcular calidad del rostro detectado"""
        top, right, bottom, left = face_location
        
        # Extraer región del rostro
        face_image = image_array[top:bottom, left:right]
        
        if face_image.size == 0:
            return 0.0
        
        # Métricas de calidad
        face_size = (bottom - top) * (right - left)
        contrast = np.std(face_image)
        brightness = np.mean(face_image)
        
        # Score de calidad normalizado
        size_score = min(1.0, face_size / 10000)  # Normalizar tamaño
        contrast_score = min(1.0, contrast / 100)  # Normalizar contraste
        brightness_score = 1.0 - abs(brightness - 128) / 128  # Brillo óptimo ~128
        
        quality = (size_score * 0.4 + contrast_score * 0.3 + brightness_score * 0.3)
        
        return quality
    
    def ultra_tolerant_compare(self, known_encoding, unknown_encoding):
        """
        🔍 COMPARACIÓN OPTIMIZADA PARA 85% DE CONFIANZA
        """
        try:
            known_encoding = np.array(known_encoding)
            unknown_encoding = np.array(unknown_encoding)
            
            # Método 1: Distancia euclidiana (el más estándar)
            euclidean_distance = np.linalg.norm(known_encoding - unknown_encoding)
            
            # Método 2: Distancia de coseno (mejor para variaciones de iluminación)
            cosine_similarity = np.dot(known_encoding, unknown_encoding) / (
                np.linalg.norm(known_encoding) * np.linalg.norm(unknown_encoding)
            )
            cosine_distance = 1 - cosine_similarity
            
            # Método 3: Correlación de Pearson
            correlation = np.corrcoef(known_encoding, unknown_encoding)[0, 1]
            correlation = max(-1, min(1, correlation))  # Clamp entre -1 y 1
            
            # Combinar métricas para 85% threshold
            # Euclidiana normalizada (0.6 = threshold estándar face_recognition)
            euclidean_score = max(0, 1 - (euclidean_distance / 0.6))
            
            # Coseno score
            cosine_score = cosine_similarity
            
            # Correlación score
            correlation_score = (correlation + 1) / 2  # Normalizar a 0-1
            
            # Score combinado ponderado
            # Euclidiana: 50%, Coseno: 30%, Correlación: 20%
            combined_confidence = (
                0.50 * euclidean_score +
                0.30 * cosine_score +
                0.20 * correlation_score
            )
            
            # Asegurar que esté en rango 0-1
            combined_confidence = max(0.0, min(1.0, combined_confidence))
            
            print(f"🔍 Métricas - Euclidiana: {euclidean_distance:.3f} (score: {euclidean_score:.3f})")
            print(f"🔍 Coseno: {cosine_distance:.3f} (score: {cosine_score:.3f})")
            print(f"🔍 Correlación: {correlation:.3f} (score: {correlation_score:.3f})")
            print(f"🔍 Confianza final: {combined_confidence:.3f} ({combined_confidence:.1%})")
            
            return combined_confidence
            
        except Exception as e:
            print(f"❌ Error en comparación: {str(e)}")
            return 0.0
    
    def compare_faces(self, known_encoding, unknown_encoding, tolerance=None):
        """
        🔍 COMPARAR ROSTROS con threshold de 85%
        """
        confidence = self.ultra_tolerant_compare(known_encoding, unknown_encoding)
        
        # Usar threshold de 85% si no se especifica otro
        threshold = self.confidence_threshold if tolerance is None else tolerance
        is_match = confidence >= threshold
        
        return is_match, confidence
    
    def validate_image_quality(self, base64_image):
        """
        ✅ VALIDACIÓN ESTRICTA de imagen para alta precisión
        """
        try:
            image_data = base64.b64decode(base64_image.split(',')[1] if ',' in base64_image else base64_image)
            image = Image.open(io.BytesIO(image_data))
            
            # Validaciones de tamaño
            if image.width < 200 or image.height < 200:
                return False, "Imagen muy pequeña (mínimo 200x200 para 85% de confianza)"
            
            if image.width > 8000 or image.height > 8000:
                return False, "Imagen muy grande (máximo 8000x8000)"
            
            # Verificar calidad de iluminación
            image_array = np.array(image.convert('L'))  # Escala de grises
            mean_brightness = np.mean(image_array)
            brightness_std = np.std(image_array)
            
            if mean_brightness < 20:
                return False, "Imagen muy oscura para reconocimiento preciso"
            elif mean_brightness > 235:
                return False, "Imagen muy clara (sobreexpuesta)"
            
            if brightness_std < 15:
                return False, "Imagen con poco contraste"
            
            # Verificar que no esté borrosa
            laplacian_var = cv2.Laplacian(np.array(image.convert('L')), cv2.CV_64F).var()
            if laplacian_var < 100:
                return False, "Imagen muy borrosa para reconocimiento preciso"
            
            print(f"✅ Imagen válida: {image.width}x{image.height}")
            print(f"   Brillo: {mean_brightness:.1f}, Contraste: {brightness_std:.1f}, Nitidez: {laplacian_var:.1f}")
            return True, "Imagen válida para reconocimiento de alta precisión"
            
        except Exception as e:
            print(f"❌ Error validando imagen: {str(e)}")
            return False, f"Error: {str(e)}"
    
    def encode_face_from_base64(self, base64_image):
        """Método de compatibilidad"""
        return self.tolerant_photo_encoding(base64_image)