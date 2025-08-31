import face_recognition
import cv2
import numpy as np
import json
import base64
from PIL import Image
import io
from django.conf import settings
import os

class FaceRecognitionService:
    def __init__(self):
        self.tolerance = 0.6  # Ajustar según precisión deseada
    
    def encode_face_from_base64(self, base64_image):
        """
        Genera encoding facial desde imagen en base64
        """
        try:
            # Decodificar imagen base64
            image_data = base64.b64decode(base64_image.split(',')[1] if ',' in base64_image else base64_image)
            image = Image.open(io.BytesIO(image_data))
            
            # Convertir a RGB si es necesario
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Convertir PIL a numpy array
            image_array = np.array(image)
            
            # Detectar rostros
            face_locations = face_recognition.face_locations(image_array)
            
            if not face_locations:
                return None, "No se detectó ningún rostro en la imagen"
            
            if len(face_locations) > 1:
                return None, "Se detectaron múltiples rostros. Usar imagen con un solo rostro"
            
            # Generar encoding
            face_encodings = face_recognition.face_encodings(image_array, face_locations)
            
            if not face_encodings:
                return None, "No se pudo generar encoding facial"
            
            # Convertir encoding a lista para JSON
            encoding_list = face_encodings[0].tolist()
            
            return encoding_list, "Encoding facial generado exitosamente"
            
        except Exception as e:
            return None, f"Error procesando imagen: {str(e)}"
    
    def compare_faces(self, known_encoding, unknown_encoding, tolerance=None):
        """
        Compara dos encodings faciales
        """
        if tolerance is None:
            tolerance = self.tolerance
        
        try:
            # Convertir listas a numpy arrays
            known_encoding = np.array(known_encoding)
            unknown_encoding = np.array(unknown_encoding)
            
            # Comparar rostros
            matches = face_recognition.compare_faces([known_encoding], unknown_encoding, tolerance=tolerance)
            face_distances = face_recognition.face_distance([known_encoding], unknown_encoding)
            
            is_match = matches[0]
            confidence = 1 - face_distances[0]  # Convertir distancia a confianza
            
            return is_match, float(confidence)
            
        except Exception as e:
            return False, 0.0
    
    def find_best_match(self, known_encodings, unknown_encoding):
        """
        Encuentra la mejor coincidencia entre múltiples encodings conocidos
        """
        best_match = None
        best_confidence = 0.0
        
        for employee_id, encoding_data in known_encodings.items():
            try:
                encoding = json.loads(encoding_data)
                is_match, confidence = self.compare_faces(encoding, unknown_encoding)
                
                if is_match and confidence > best_confidence:
                    best_match = employee_id
                    best_confidence = confidence
                    
            except Exception as e:
                continue
        
        return best_match, best_confidence
    
    def validate_image_quality(self, base64_image):
        """
        Valida la calidad de la imagen para reconocimiento facial
        """
        try:
            # Decodificar imagen
            image_data = base64.b64decode(base64_image.split(',')[1] if ',' in base64_image else base64_image)
            image = Image.open(io.BytesIO(image_data))
            
            # Verificar dimensiones mínimas
            if image.width < 200 or image.height < 200:
                return False, "Imagen muy pequeña. Mínimo 200x200 píxeles"
            
            # Convertir a array para análisis
            image_array = np.array(image.convert('RGB'))
            
            # Verificar brillo promedio
            gray = cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)
            avg_brightness = np.mean(gray)
            
            if avg_brightness < 50:
                return False, "Imagen muy oscura. Mejorar iluminación"
            
            if avg_brightness > 200:
                return False, "Imagen muy brillante. Reducir iluminación"
            
            # Verificar nitidez usando varianza del Laplaciano
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            
            if laplacian_var < 100:
                return False, "Imagen borrosa. Enfocar mejor"
            
            return True, "Calidad de imagen aceptable"
            
        except Exception as e:
            return False, f"Error validando imagen: {str(e)}"
    
    def preprocess_image(self, base64_image):
        """
        Preprocesa la imagen para mejorar el reconocimiento
        """
        try:
            # Decodificar imagen
            image_data = base64.b64decode(base64_image.split(',')[1] if ',' in base64_image else base64_image)
            image = Image.open(io.BytesIO(image_data))
            image_array = np.array(image.convert('RGB'))
            
            # Redimensionar si es muy grande
            height, width = image_array.shape[:2]
            if width > 800:
                ratio = 800 / width
                new_width = 800
                new_height = int(height * ratio)
                image_array = cv2.resize(image_array, (new_width, new_height))
            
            # Mejorar contraste
            lab = cv2.cvtColor(image_array, cv2.COLOR_RGB2LAB)
            l, a, b = cv2.split(lab)
            l = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8)).apply(l)
            enhanced = cv2.merge([l, a, b])
            enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2RGB)
            
            # Convertir de vuelta a base64
            pil_img = Image.fromarray(enhanced)
            buffer = io.BytesIO()
            pil_img.save(buffer, format='JPEG', quality=85)
            enhanced_b64 = base64.b64encode(buffer.getvalue()).decode()
            
            return f"data:image/jpeg;base64,{enhanced_b64}"
            
        except Exception as e:
            return base64_image  # Retornar imagen original si falla el procesamiento