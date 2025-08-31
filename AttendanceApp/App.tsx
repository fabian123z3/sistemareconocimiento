import React, { useState, useEffect, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Alert,
  TouchableOpacity,
  Modal,
  ScrollView,
  Dimensions,
  ActivityIndicator
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { CameraView, useCameraPermissions } from 'expo-camera';
import * as Location from 'expo-location';
import AsyncStorage from '@react-native-async-storage/async-storage';
import axios from 'axios';

const { width, height } = Dimensions.get('window');

// Configuración del servidor Django
const API_BASE_URL = 'http://10.0.2.2:8000/api'; // Para emulador Android
// const API_BASE_URL = 'http://localhost:8000/api'; // Para iOS simulator
// const API_BASE_URL = 'http://YOUR_IP:8000/api'; // Para dispositivo físico

interface Employee {
  id: string;
  name: string;
  employee_id: string;
  department: string;
  position: string;
}

interface AttendanceRecord {
  id: string;
  employee_name: string;
  employee_id: string;
  attendance_type: string;
  timestamp: string;
  confidence_percentage: string;
}

export default function App() {
  // Estados principales
  const [currentUser, setCurrentUser] = useState<Employee | null>(null);
  const [attendanceHistory, setAttendanceHistory] = useState<AttendanceRecord[]>([]);
  const [loading, setLoading] = useState(false);

  // Estados de cámara
  const [permission, requestPermission] = useCameraPermissions();
  const [showCamera, setShowCamera] = useState(false);
  const [showRegistration, setShowRegistration] = useState(false);
  const [attendanceType, setAttendanceType] = useState<'entrada' | 'salida'>('entrada');

  // Estados de registro
  const [registrationData, setRegistrationData] = useState({
    name: '',
    employee_id: '',
    department: '',
    position: ''
  });
  const [showRegistrationForm, setShowRegistrationForm] = useState(false);

  const cameraRef = useRef<CameraView>(null);

  useEffect(() => {
    loadStoredData();
  }, []);

  const loadStoredData = async () => {
    try {
      const storedUser = await AsyncStorage.getItem('currentUser');
      const storedHistory = await AsyncStorage.getItem('attendanceHistory');
      
      if (storedUser) {
        setCurrentUser(JSON.parse(storedUser));
      }
      
      if (storedHistory) {
        setAttendanceHistory(JSON.parse(storedHistory));
      }
    } catch (error) {
      console.error('Error loading stored data:', error);
    }
  };

  const saveToStorage = async (key: string, data: any) => {
    try {
      await AsyncStorage.setItem(key, JSON.stringify(data));
    } catch (error) {
      console.error('Error saving to storage:', error);
    }
  };

  const takePictureAndProcess = async (isRegistration: boolean = false) => {
    if (!cameraRef.current) return;

    try {
      setLoading(true);

      // Tomar foto
      const photo = await cameraRef.current.takePictureAsync({
        quality: 0.8,
        base64: true,
      });

      if (!photo || !photo.base64) {
        Alert.alert('Error', 'No se pudo capturar la imagen');
        return;
      }

      // Obtener ubicación
      let location = null;
      try {
        const { status } = await Location.requestForegroundPermissionsAsync();
        if (status === 'granted') {
          const locationData = await Location.getCurrentPositionAsync({
            accuracy: Location.Accuracy.High,
          });
          location = {
            latitude: locationData.coords.latitude,
            longitude: locationData.coords.longitude,
          };
        }
      } catch (locationError) {
        console.warn('Error getting location:', locationError);
      }

      const base64Image = `data:image/jpeg;base64,${photo.base64}`;

      if (isRegistration) {
        await registerEmployee(base64Image);
      } else {
        await verifyAttendance(base64Image, location);
      }

    } catch (error) {
      console.error('Error processing image:', error);
      Alert.alert('Error', 'Error procesando la imagen');
    } finally {
      setLoading(false);
    }
  };

  const registerEmployee = async (base64Image: string) => {
    try {
      const response = await axios.post(`${API_BASE_URL}/register-employee/`, {
        name: registrationData.name,
        employee_id: registrationData.employee_id,
        email: `${registrationData.employee_id}@company.com`,
        department: registrationData.department,
        position: registrationData.position,
        image: base64Image,
      });

      if (response.data.success) {
        Alert.alert(
          'Registro Exitoso',
          `${registrationData.name} ha sido registrado correctamente`,
          [{ text: 'OK', onPress: () => {
            setShowRegistration(false);
            setShowRegistrationForm(false);
            setRegistrationData({ name: '', employee_id: '', department: '', position: '' });
          }}]
        );
      } else {
        Alert.alert('Error de Registro', response.data.message);
      }
    } catch (error) {
      console.error('Registration error:', error);
      Alert.alert('Error', 'Error conectando con el servidor');
    }
  };

  const verifyAttendance = async (base64Image: string, location: any) => {
    try {
      const requestData: any = {
        image: base64Image,
        type: attendanceType,
      };

      if (location) {
        requestData.latitude = location.latitude;
        requestData.longitude = location.longitude;
      }

      const response = await axios.post(`${API_BASE_URL}/verify-attendance/`, requestData);

      if (response.data.success) {
        const { employee, attendance } = response.data;
        
        // Actualizar usuario actual
        setCurrentUser(employee);
        saveToStorage('currentUser', employee);

        // Agregar al historial
        const newRecord: AttendanceRecord = {
          id: attendance.id,
          employee_name: employee.name,
          employee_id: employee.employee_id,
          attendance_type: attendance.type,
          timestamp: new Date(attendance.timestamp).toLocaleString('es-CL'),
          confidence_percentage: attendance.confidence,
        };

        const updatedHistory = [newRecord, ...attendanceHistory].slice(0, 50);
        setAttendanceHistory(updatedHistory);
        saveToStorage('attendanceHistory', updatedHistory);

        Alert.alert(
          'Asistencia Registrada',
          `${employee.name}\n${attendance.type.toUpperCase()}\nConfianza: ${attendance.confidence}\n${newRecord.timestamp}`,
          [{ text: 'OK', onPress: () => setShowCamera(false) }]
        );
      } else {
        Alert.alert('Acceso Denegado', response.data.message);
      }
    } catch (error) {
      console.error('Verification error:', error);
      Alert.alert('Error', 'Error conectando con el servidor');
    }
  };

  const startCamera = async (type: 'entrada' | 'salida') => {
    if (!permission?.granted) {
      const result = await requestPermission();
      if (!result.granted) {
        Alert.alert('Permiso requerido', 'Se necesita acceso a la cámara');
        return;
      }
    }

    setAttendanceType(type);
    setShowCamera(true);
  };

  const startRegistration = async () => {
    if (!permission?.granted) {
      const result = await requestPermission();
      if (!result.granted) {
        Alert.alert('Permiso requerido', 'Se necesita acceso a la cámara');
        return;
      }
    }

    setShowRegistrationForm(true);
  };

  const proceedWithRegistration = () => {
    if (!registrationData.name || !registrationData.employee_id) {
      Alert.alert('Error', 'Nombre e ID de empleado son requeridos');
      return;
    }
    setShowRegistrationForm(false);
    setShowRegistration(true);
  };

  return (
    <View style={styles.container}>
      <StatusBar style="auto" />
      
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.title}>Sistema de Asistencia</Text>
        <Text style={styles.subtitle}>Reconocimiento Facial con IA</Text>
      </View>

      {/* Estado del usuario */}
      <View style={styles.userSection}>
        {currentUser ? (
          <View style={styles.userInfo}>
            <Text style={styles.userName}>{currentUser.name}</Text>
            <Text style={styles.userDetails}>
              ID: {currentUser.employee_id} | {currentUser.department}
            </Text>
            <Text style={styles.userPosition}>{currentUser.position}</Text>
          </View>
        ) : (
          <Text style={styles.noUserText}>No hay usuario activo</Text>
        )}
      </View>

      {/* Botones principales */}
      <View style={styles.buttonSection}>
        <TouchableOpacity
          style={[styles.button, styles.entradaButton]}
          onPress={() => startCamera('entrada')}
        >
          <Text style={styles.buttonText}>📷 ENTRADA</Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.button, styles.salidaButton]}
          onPress={() => startCamera('salida')}
        >
          <Text style={styles.buttonText}>📷 SALIDA</Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.button, styles.registerButton]}
          onPress={startRegistration}
        >
          <Text style={styles.buttonText}>👤 REGISTRAR EMPLEADO</Text>
        </TouchableOpacity>
      </View>

      {/* Historial */}
      <View style={styles.historySection}>
        <Text style={styles.historyTitle}>Historial Reciente</Text>
        <ScrollView style={styles.historyList}>
          {attendanceHistory.slice(0, 5).map((record) => (
            <View key={record.id} style={styles.historyItem}>
              <Text style={styles.historyName}>{record.employee_name}</Text>
              <Text style={styles.historyDetails}>
                {record.attendance_type.toUpperCase()} | {record.confidence_percentage}
              </Text>
              <Text style={styles.historyTime}>{record.timestamp}</Text>
            </View>
          ))}
          {attendanceHistory.length === 0 && (
            <Text style={styles.noHistoryText}>No hay registros aún</Text>
          )}
        </ScrollView>
      </View>

      {/* Modal de formulario de registro */}
      <Modal visible={showRegistrationForm} animationType="slide" transparent>
        <View style={styles.modalOverlay}>
          <View style={styles.formContainer}>
            <Text style={styles.formTitle}>Nuevo Empleado</Text>
            
            <Text style={styles.inputLabel}>Nombre completo:</Text>
            <TouchableOpacity style={styles.input}>
              <Text style={styles.inputText}>
                {registrationData.name || 'Ingrese nombre'}
              </Text>
            </TouchableOpacity>
            
            <Text style={styles.inputLabel}>ID Empleado:</Text>
            <TouchableOpacity style={styles.input}>
              <Text style={styles.inputText}>
                {registrationData.employee_id || 'Ingrese ID'}
              </Text>
            </TouchableOpacity>
            
            <Text style={styles.inputLabel}>Departamento:</Text>
            <TouchableOpacity style={styles.input}>
              <Text style={styles.inputText}>
                {registrationData.department || 'Departamento'}
              </Text>
            </TouchableOpacity>
            
            <Text style={styles.inputLabel}>Cargo:</Text>
            <TouchableOpacity style={styles.input}>
              <Text style={styles.inputText}>
                {registrationData.position || 'Cargo'}
              </Text>
            </TouchableOpacity>

            <View style={styles.formButtons}>
              <TouchableOpacity
                style={[styles.button, styles.cancelButton]}
                onPress={() => setShowRegistrationForm(false)}
              >
                <Text style={styles.buttonText}>Cancelar</Text>
              </TouchableOpacity>
              
              <TouchableOpacity
                style={[styles.button, styles.confirmButton]}
                onPress={proceedWithRegistration}
              >
                <Text style={styles.buttonText}>Continuar</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      {/* Modal de cámara */}
      <Modal visible={showCamera || showRegistration} animationType="slide">
        <View style={styles.cameraContainer}>
          <View style={styles.cameraHeader}>
            <Text style={styles.cameraTitle}>
              {showRegistration ? 'Registro Facial' : `Verificación - ${attendanceType.toUpperCase()}`}
            </Text>
            <TouchableOpacity
              onPress={() => {
                setShowCamera(false);
                setShowRegistration(false);
              }}
              style={styles.closeButton}
            >
              <Text style={styles.closeButtonText}>✕</Text>
            </TouchableOpacity>
          </View>

          <CameraView
            ref={cameraRef}
            style={styles.camera}
            facing="front"
          />

          <View style={styles.cameraOverlay}>
            <View style={styles.faceFrame} />
            <Text style={styles.instructionText}>
              {showRegistration
                ? 'Posiciona tu rostro en el marco para registrarte'
                : 'Posiciona tu rostro en el marco para verificar asistencia'
              }
            </Text>
            
            <TouchableOpacity
              style={styles.captureButton}
              onPress={() => takePictureAndProcess(showRegistration)}
              disabled={loading}
            >
              {loading ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <Text style={styles.captureButtonText}>
                  {showRegistration ? '📸 REGISTRAR' : '📸 VERIFICAR'}
                </Text>
              )}
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f5f5',
  },
  header: {
    backgroundColor: '#2c3e50',
    padding: 20,
    paddingTop: 50,
    alignItems: 'center',
  },
  title: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#fff',
  },
  subtitle: {
    fontSize: 14,
    color: '#ecf0f1',
    marginTop: 5,
  },
  userSection: {
    backgroundColor: '#fff',
    margin: 20,
    padding: 20,
    borderRadius: 10,
    elevation: 3,
  },
  userInfo: {
    alignItems: 'center',
  },
  userName: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#2c3e50',
  },
  userDetails: {
    fontSize: 14,
    color: '#7f8c8d',
    marginTop: 5,
  },
  userPosition: {
    fontSize: 16,
    color: '#34495e',
    marginTop: 5,
  },
  noUserText: {
    textAlign: 'center',
    color: '#7f8c8d',
    fontStyle: 'italic',
  },
  buttonSection: {
    padding: 20,
    gap: 15,
  },
  button: {
    padding: 15,
    borderRadius: 10,
    alignItems: 'center',
    elevation: 2,
  },
  entradaButton: {
    backgroundColor: '#27ae60',
  },
  salidaButton: {
    backgroundColor: '#e74c3c',
  },
  registerButton: {
    backgroundColor: '#3498db',
  },
  cancelButton: {
    backgroundColor: '#95a5a6',
  },
  confirmButton: {
    backgroundColor: '#27ae60',
  },
  buttonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: 'bold',
  },
  historySection: {
    flex: 1,
    margin: 20,
    backgroundColor: '#fff',
    borderRadius: 10,
    padding: 15,
    elevation: 3,
  },
  historyTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#2c3e50',
    marginBottom: 15,
  },
  historyList: {
    flex: 1,
  },
  historyItem: {
    padding: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#ecf0f1',
  },
  historyName: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#2c3e50',
  },
  historyDetails: {
    fontSize: 12,
    color: '#7f8c8d',
    marginTop: 2,
  },
  historyTime: {
    fontSize: 12,
    color: '#95a5a6',
    marginTop: 2,
  },
  noHistoryText: {
    textAlign: 'center',
    color: '#7f8c8d',
    fontStyle: 'italic',
    marginTop: 20,
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    padding: 20,
  },
  formContainer: {
    backgroundColor: '#fff',
    borderRadius: 15,
    padding: 25,
  },
  formTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    textAlign: 'center',
    marginBottom: 20,
    color: '#2c3e50',
  },
  inputLabel: {
    fontSize: 14,
    color: '#2c3e50',
    marginBottom: 5,
    fontWeight: '500',
  },
  input: {
    borderWidth: 1,
    borderColor: '#ddd',
    borderRadius: 8,
    padding: 15,
    marginBottom: 15,
    backgroundColor: '#f9f9f9',
  },
  inputText: {
    fontSize: 16,
    color: '#2c3e50',
  },
  formButtons: {
    flexDirection: 'row',
    gap: 15,
    marginTop: 20,
  },
  cameraContainer: {
    flex: 1,
    backgroundColor: '#000',
  },
  cameraHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 20,
    paddingTop: 50,
    backgroundColor: 'rgba(0,0,0,0.8)',
  },
  cameraTitle: {
    color: '#fff',
    fontSize: 18,
    fontWeight: 'bold',
    flex: 1,
  },
  closeButton: {
    padding: 10,
    backgroundColor: 'rgba(255,255,255,0.2)',
    borderRadius: 20,
  },
  closeButtonText: {
    color: '#fff',
    fontSize: 18,
    fontWeight: 'bold',
  },
  camera: {
    flex: 1,
  },
  cameraOverlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    justifyContent: 'center',
    alignItems: 'center',
  },
  faceFrame: {
    width: 250,
    height: 300,
    borderWidth: 3,
    borderColor: '#27ae60',
    borderRadius: 125,
    backgroundColor: 'transparent',
  },
  instructionText: {
    color: '#fff',
    fontSize: 16,
    textAlign: 'center',
    marginTop: 20,
    backgroundColor: 'rgba(0,0,0,0.7)',
    padding: 15,
    borderRadius: 10,
    marginHorizontal: 20,
  },
  captureButton: {
    backgroundColor: '#27ae60',
    paddingHorizontal: 30,
    paddingVertical: 15,
    borderRadius: 25,
    marginTop: 30,
    minWidth: 150,
    alignItems: 'center',
  },
  captureButtonText: {
    color: '#fff',
    fontSize: 18,
    fontWeight: 'bold',
  },
});