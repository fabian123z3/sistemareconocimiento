import face_recognition
import cv2
import numpy as np
import json
import base64
from PIL import Image, ImageEnhance, ImageFilter
import io

class FaceRecognitionService:
    def __init__(self):
        self.tolerance = 0.9  # Ultra permisivo para cámaras malas
    
    def ultra_fast_encoding(self, base64_image):
        """
        ⚡ ENCODING ULTRA RÁPIDO para cámaras MUY MALAS
        """
        try:
            print("⚡ Procesamiento ultra rápido iniciado...")
            
            # Decodificar rápidamente
            image_data = base64.b64decode(base64_image.split(',')[1] if ',' in base64_image else base64_image)
            image = Image.open(io.BytesIO(image_data))
            
            print(f"⚡ Imagen original: {image.width}x{image.height}")
            
            # Convertir a RGB
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # OPTIMIZACIÓN EXTREMA PARA CÁMARAS MALAS
            # Redimensionar a tamaño fijo pequeño para velocidad
            target_size = 200  # Muy pequeño para velocidad máxima
            image = image.resize((target_size, target_size), Image.Resampling.BILINEAR)
            print(f"⚡ Redimensionado a {target_size}x{target_size}")
            
            # MEJORAS AGRESIVAS para cámaras malas
            # Aumentar contraste dramáticamente
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(2.5)  # Contraste muy alto
            
            # Aumentar brillo si está muy oscuro
            enhancer = ImageEnhance.Brightness(image)
            image = enhancer.enhance(1.3)
            
            # Aplicar filtro de nitidez
            image = image.filter(ImageFilter.SHARPEN)
            
            print("⚡ Mejoras aplicadas para cámara mala")
            
            # Convertir a array
            image_array = np.array(image)
            
            # DETECCIÓN ULTRA RÁPIDA
            print("⚡ Detección ultra rápida...")
            face_locations = face_recognition.face_locations(
                image_array,
                number_of_times_to_upsample=0,  # Sin upsampling
                model="hog"  # Más rápido que CNN
            )
            
            print(f"⚡ Rostros detectados: {len(face_locations)}")
            
            if not face_locations:
                # INTENTO CON MÁS CONTRASTE si no se detecta
                enhancer = ImageEnhance.Contrast(Image.fromarray(image_array))
                enhanced = enhancer.enhance(3.0)  # Contraste extremo
                enhanced_array = np.array(enhanced)
                
                face_locations = face_recognition.face_locations(
                    enhanced_array,
                    number_of_times_to_upsample=0,
                    model="hog"
                )
                
                print(f"⚡ Segundo intento con contraste extremo: {len(face_locations)}")
                
                if not face_locations:
                    return None, "No se detectó rostro"
                
                image_array = enhanced_array
            
            # Usar el rostro más grande
            if len(face_locations) > 1:
                face_locations = [max(face_locations, key=lambda f: (f[2] - f[0]) * (f[1] - f[3]))]
            
            # ENCODING ULTRA RÁPIDO
            print("⚡ Generando encoding ultra rápido...")
            face_encodings = face_recognition.face_encodings(
                image_array,
                face_locations,
                num_jitters=0  # Sin jitters para velocidad máxima
            )
            
            if not face_encodings:
                return None, "Error generando encoding"
            
            encoding_list = face_encodings[0].tolist()
            print(f"⚡ Encoding ultra rápido generado: {len(encoding_list)} características")
            
            return encoding_list, "Encoding ultra rápido exitoso"
            
        except Exception as e:
            print(f"❌ Error ultra rápido: {str(e)}")
            return None, f"Error: {str(e)}"
    
    def ultra_fast_compare(self, known_encoding, unknown_encoding):
        """
        ⚡ COMPARACIÓN ULTRA RÁPIDA para cámaras malas
        """
        try:
            known_encoding = np.array(known_encoding)
            unknown_encoding = np.array(unknown_encoding)
            
            # Usar solo distancia euclidiana para velocidad máxima
            distance = np.linalg.norm(known_encoding - unknown_encoding)
            
            # Convertir distancia a confianza (más permisivo)
            confidence = max(0, 1 - (distance / 1.5))  # Umbral muy permisivo
            
            print(f"⚡ Comparación ultra rápida: Distancia={distance:.3f}, Confianza={confidence:.3f}")
            
            return confidence
            
        except Exception as e:
            print(f"❌ Error comparación ultra rápida: {str(e)}")
            return 0.0
    
    # Métodos de compatibilidad
    def encode_face_from_base64(self, base64_image):
        return self.ultra_fast_encoding(base64_image)
    
    def compare_faces(self, known_encoding, unknown_encoding, tolerance=None):
        confidence = self.ultra_fast_compare(known_encoding, unknown_encoding)
        return confidence > 0.15, confidence
    
    def validate_image_quality(self, base64_image):
        """
        ⚡ VALIDACIÓN ULTRA PERMISIVA
        """
        try:
            image_data = base64.b64decode(base64_image.split(',')[1] if ',' in base64_image else base64_image)
            image = Image.open(io.BytesIO(image_data))
            
            # Solo verificar que no esté completamente vacía
            if image.width < 10 or image.height < 10:
                return False, "Imagen demasiado pequeña"
            
            print(f"⚡ Imagen ultra básica válida: {image.width}x{image.height}")
            return True, "Válida"
            
        except Exception:
            return False, "Imagen corrupta"
    
    def preprocess_image(self, base64_image):
        """
        ⚡ SIN PROCESAMIENTO para velocidad máxima
        """
        return base64_image