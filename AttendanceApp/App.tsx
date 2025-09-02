import React, { useState, useEffect, useRef } from 'react';
import { 
  View, 
  Text, 
  StyleSheet, 
  Alert, 
  TouchableOpacity, 
  ScrollView,
  Modal,
  TextInput,
  ActivityIndicator,
  SafeAreaView,
  RefreshControl
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import AsyncStorage from '@react-native-async-storage/async-storage';
import NetInfo from '@react-native-community/netinfo';
import * as Location from 'expo-location';
import { CameraView, useCameraPermissions } from 'expo-camera';
import * as ImageManipulator from 'expo-image-manipulator';

const API_BASE_URL = 'http://192.168.96.36:8000/api';
const PHOTOS_REQUIRED = 5;
const VERIFICATION_TIMEOUT = 10;

interface Employee {
  id: string;
  name: string;
  employee_id: string;
  department: string;
  position: string;
  has_face_registered?: boolean;
}

interface AttendanceRecord {
  id: string;
  employee_name: string;
  attendance_type: string;
  timestamp: string;
  location_lat: number;
  location_lng: number;
  address: string;
  is_offline_sync: boolean;
  face_confidence?: number;
}

export default function App() {
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [selectedEmployee, setSelectedEmployee] = useState<Employee | null>(null);
  const [attendanceHistory, setAttendanceHistory] = useState<AttendanceRecord[]>([]);
  const [offlineRecords, setOfflineRecords] = useState<any[]>([]);
  const [isOnline, setIsOnline] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [currentLocation, setCurrentLocation] = useState<string>('📍 Obteniendo ubicación...');
  const [coordinates, setCoordinates] = useState<{lat: number, lng: number} | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  
  // Estados de cámara
  const [permission, requestPermission] = useCameraPermissions();
  const [showCamera, setShowCamera] = useState(false);
  const [facing, setFacing] = useState<'front' | 'back'>('front');
  const [cameraMode, setCameraMode] = useState<'register' | 'verify' | 'newEmployee' | null>(null);
  const [pendingType, setPendingType] = useState<'entrada' | 'salida'>('entrada');
  const cameraRef = useRef<CameraView>(null);
  
  // Estados de registro
  const [registrationPhotos, setRegistrationPhotos] = useState<string[]>([]);
  const [showEmployeeModal, setShowEmployeeModal] = useState(false);
  const [showNewEmployeeModal, setShowNewEmployeeModal] = useState(false);
  const [newEmployeeName, setNewEmployeeName] = useState('');
  const [newEmployeePhotos, setNewEmployeePhotos] = useState<string[]>([]);
  const [creatingEmployee, setCreatingEmployee] = useState(false);

  // Estados de verificación
  const [verificationInProgress, setVerificationInProgress] = useState(false);
  const [timeoutCounter, setTimeoutCounter] = useState(0);

  // Guías para registro
  const photoGuides = [
    '📸 Foto 1: Frente directo',
    '📸 Foto 2: Ligeramente izquierda', 
    '📸 Foto 3: Ligeramente derecha',
    '📸 Foto 4: Mirando hacia arriba',
    '📸 Foto 5: Expresión neutral'
  ];

  useEffect(() => {
    initializeApp();
  }, []);

  const initializeApp = async () => {
    await loadStoredData();
    await setupLocation();
    setupNetworkListener();
    await loadEmployees();
    if (!permission?.granted) {
      await requestPermission();
    }
  };

  const setupLocation = async () => {
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') {
        setCurrentLocation('❌ Sin permisos de ubicación');
        return;
      }

      setCurrentLocation('📍 Obteniendo ubicación...');
      
      const location = await Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.High,
      });

      const { latitude, longitude } = location.coords;
      setCoordinates({ lat: latitude, lng: longitude });
      setCurrentLocation(`📍 ${latitude.toFixed(4)}, ${longitude.toFixed(4)}`);
      
      try {
        const addresses = await Location.reverseGeocodeAsync({ latitude, longitude });
        if (addresses.length > 0) {
          const addr = addresses[0];
          const fullAddress = `${addr.street || ''} ${addr.city || ''}`.trim();
          if (fullAddress) {
            setCurrentLocation(`📍 ${fullAddress}`);
          }
        }
      } catch (e) {
        // Mantener coordenadas si falla geocoding
      }
    } catch (error) {
      setCurrentLocation('❌ Error obteniendo ubicación');
    }
  };

  const setupNetworkListener = () => {
    NetInfo.addEventListener(state => {
      const online = state.isConnected && state.isInternetReachable;
      setIsOnline(online || false);
      
      if (online && offlineRecords.length > 0) {
        syncOfflineRecords();
      }
    });
  };

  const loadStoredData = async () => {
    try {
      const storedHistory = await AsyncStorage.getItem('attendanceHistory');
      if (storedHistory) setAttendanceHistory(JSON.parse(storedHistory));
      
      const storedOffline = await AsyncStorage.getItem('offlineRecords');
      if (storedOffline) setOfflineRecords(JSON.parse(storedOffline));

      const storedEmployee = await AsyncStorage.getItem('selectedEmployee');
      if (storedEmployee) setSelectedEmployee(JSON.parse(storedEmployee));
    } catch (error) {
      console.error('Error cargando datos:', error);
    }
  };

  const saveToStorage = async (key: string, data: any) => {
    try {
      await AsyncStorage.setItem(key, JSON.stringify(data));
    } catch (error) {
      console.error('Error guardando:', error);
    }
  };

  const loadEmployees = async () => {
    if (!isOnline) return;
    
    try {
      const response = await fetch(`${API_BASE_URL}/employees/`);
      const data = await response.json();
      
      if (data.success) {
        setEmployees(data.employees);
      }
    } catch (error) {
      console.error('Error cargando empleados:', error);
    }
  };

  const onRefresh = async () => {
    setRefreshing(true);
    await setupLocation();
    await loadEmployees();
    setRefreshing(false);
  };

  const detectLowLight = async (imageUri: string): Promise<boolean> => {
    // Función simplificada para detectar poca luz
    // En un entorno real, analizarías los píxeles de la imagen
    const currentHour = new Date().getHours();
    return currentHour < 7 || currentHour > 19; // Asume poca luz fuera de 7AM-7PM
  };

  const takePicture = async () => {
    if (!cameraRef.current) return;
    
    try {
      setIsLoading(true);
      
      const photo = await cameraRef.current.takePictureAsync({
        quality: 0.8,
        base64: true,
      });
      
      if (!photo?.base64) {
        throw new Error('No se pudo capturar la foto');
      }
      
      // Manipular imagen para mejor calidad
      const manipulated = await ImageManipulator.manipulateAsync(
        photo.uri,
        [
          { resize: { width: 800 } },
        ],
        { 
          compress: 0.8, 
          format: ImageManipulator.SaveFormat.JPEG, 
          base64: true 
        }
      );
      
      const photoData = `data:image/jpeg;base64,${manipulated.base64}`;
      
      if (cameraMode === 'register') {
        const currentPhotos = [...registrationPhotos, photoData];
        setRegistrationPhotos(currentPhotos);
        
        if (currentPhotos.length < PHOTOS_REQUIRED) {
          Alert.alert(
            `✅ Foto ${currentPhotos.length}/${PHOTOS_REQUIRED}`,
            `${photoGuides[currentPhotos.length]}`,
            [{ text: '📸 Continuar' }]
          );
          setIsLoading(false);
        } else {
          setShowCamera(false);
          setIsLoading(false);
          await registerFaceWithMultiplePhotos(currentPhotos);
        }
      } else if (cameraMode === 'newEmployee') {
        const currentPhotos = [...newEmployeePhotos, photoData];
        setNewEmployeePhotos(currentPhotos);
        
        if (currentPhotos.length < PHOTOS_REQUIRED) {
          Alert.alert(
            `✅ Foto ${currentPhotos.length}/${PHOTOS_REQUIRED}`,
            `${photoGuides[currentPhotos.length]}`,
            [{ text: '📸 Continuar' }]
          );
          setIsLoading(false);
        } else {
          setShowCamera(false);
          setCameraMode(null);
          setIsLoading(false);
          await createEmployeeWithPhotosDirectly(currentPhotos, newEmployeeName.trim());
        }
      } else if (cameraMode === 'verify') {
        setShowCamera(false);
        setIsLoading(false);
        await verifyFaceWithTimeout(photoData, pendingType);
      }
      
    } catch (error) {
      console.error('Error capturando foto:', error);
      Alert.alert('❌ Error', 'No se pudo capturar la foto. Intenta nuevamente.');
      setIsLoading(false);
    }
  };

  const verifyFaceWithTimeout = async (photoData: string, type: 'entrada' | 'salida') => {
    const timestamp = new Date().toISOString();
    
    // Si está offline, guardar localmente
    if (!isOnline) {
      const record = {
        local_id: `offline_${Date.now()}`,
        type,
        timestamp,
        latitude: coordinates?.lat,
        longitude: coordinates?.lng,
        address: currentLocation,
        photo: photoData
      };
      
      const updated = [...offlineRecords, record];
      setOfflineRecords(updated);
      await saveToStorage('offlineRecords', updated);
      Alert.alert('📱 Offline', `${type.toUpperCase()} guardada para sincronizar`);
      return;
    }
    
    setVerificationInProgress(true);
    setTimeoutCounter(0);
    
    // Contador visual
    const timeoutInterval = setInterval(() => {
      setTimeoutCounter(prev => prev + 1);
    }, 1000);

    // Timeout de 10 segundos
    const timeoutPromise = new Promise((_, reject) => {
      setTimeout(() => {
        reject(new Error('TIMEOUT_EXCEEDED'));
      }, 10000);
    });

    const fetchPromise = fetch(`${API_BASE_URL}/verify-face/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        photo: photoData,
        type,
        latitude: coordinates?.lat,
        longitude: coordinates?.lng,
        address: currentLocation
      })
    });

    try {
      const response = await Promise.race([fetchPromise, timeoutPromise]) as Response;
      
      clearInterval(timeoutInterval);
      setVerificationInProgress(false);
      
      const data = await response.json();
      
      if (data.success) {
        const newRecord: AttendanceRecord = {
          id: data.record.id,
          employee_name: data.employee.name,
          attendance_type: type,
          timestamp: new Date().toLocaleString('es-CL'),
          location_lat: coordinates?.lat || 0,
          location_lng: coordinates?.lng || 0,
          address: currentLocation,
          is_offline_sync: false,
          face_confidence: parseFloat(data.verification?.confidence?.replace('%', '') || '0') / 100
        };
        
        const updated = [newRecord, ...attendanceHistory].slice(0, 20);
        setAttendanceHistory(updated);
        await saveToStorage('attendanceHistory', updated);
        
        Alert.alert(
          '✅ ¡Verificado!', 
          `${type.toUpperCase()} - ${data.employee.name}\n🎯 ${data.verification?.confidence}`
        );
      } else {
        Alert.alert(
          '❌ No Reconocido', 
          data.message || 'Rostro no encontrado en el sistema'
        );
      }
    } catch (error: any) {
      clearInterval(timeoutInterval);
      setVerificationInProgress(false);
      
      if (error.message === 'TIMEOUT_EXCEEDED') {
        Alert.alert(
          '⏱️ Tiempo Excedido',
          'La verificación tardó más de 10 segundos.\n\n💡 Consejos:\n• Mejora la iluminación\n• Acércate más a la cámara\n• Evita sombras en el rostro'
        );
      } else {
        Alert.alert('❌ Error', 'Error de conexión. Intenta nuevamente.');
      }
    }
  };

  const registerFaceWithMultiplePhotos = async (photos: string[]) => {
    if (!selectedEmployee) {
      Alert.alert('❌ Error', 'Selecciona un empleado primero');
      return;
    }
    
    setIsLoading(true);
    
    try {
      const response = await fetch(`${API_BASE_URL}/register-face/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          employee_id: selectedEmployee.id,
          photos: photos
        })
      });
      
      const data = await response.json();
      
      if (data.success) {
        setEmployees(prev => prev.map(emp => 
          emp.id === selectedEmployee.id 
            ? { ...emp, has_face_registered: true }
            : emp
        ));
        setSelectedEmployee({ ...selectedEmployee, has_face_registered: true });
        
        Alert.alert('✅ ¡Registrado!', `Rostro de ${selectedEmployee.name} registrado correctamente`);
        setRegistrationPhotos([]);
      } else {
        Alert.alert('❌ Error', data.message || 'Error registrando rostro');
      }
    } catch (error) {
      Alert.alert('❌ Error', 'Error de conexión registrando rostro');
    } finally {
      setIsLoading(false);
      setCameraMode(null);
    }
  };

  const markManual = async (type: 'entrada' | 'salida') => {
    if (!selectedEmployee) {
      Alert.alert('❌ Error', 'Selecciona un empleado primero');
      return;
    }
    
    const timestamp = new Date().toISOString();
    
    if (!isOnline) {
      const record = {
        local_id: `offline_${Date.now()}`,
        employee_name: selectedEmployee.name,
        employee_id: selectedEmployee.employee_id,
        type,
        timestamp,
        latitude: coordinates?.lat,
        longitude: coordinates?.lng,
        address: currentLocation
      };
      
      const updated = [...offlineRecords, record];
      setOfflineRecords(updated);
      await saveToStorage('offlineRecords', updated);
      Alert.alert('📱 Offline', `${type.toUpperCase()} guardada para sincronizar`);
      return;
    }
    
    setIsLoading(true);
    
    try {
      const response = await fetch(`${API_BASE_URL}/mark-attendance/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          employee_name: selectedEmployee.name,
          employee_id: selectedEmployee.employee_id,
          type,
          timestamp,
          latitude: coordinates?.lat,
          longitude: coordinates?.lng,
          address: currentLocation
        })
      });
      
      const data = await response.json();
      
      if (data.success) {
        const newRecord: AttendanceRecord = {
          id: data.record.id,
          employee_name: selectedEmployee.name,
          attendance_type: type,
          timestamp: new Date().toLocaleString('es-CL'),
          location_lat: coordinates?.lat || 0,
          location_lng: coordinates?.lng || 0,
          address: currentLocation,
          is_offline_sync: false,
          face_confidence: 0
        };
        
        const updated = [newRecord, ...attendanceHistory].slice(0, 20);
        setAttendanceHistory(updated);
        await saveToStorage('attendanceHistory', updated);
        
        Alert.alert('✅ Registrado', `${type.toUpperCase()} - ${selectedEmployee.name}`);
      } else {
        Alert.alert('❌ Error', data.message || 'Error registrando asistencia');
      }
    } catch (error) {
      Alert.alert('❌ Error', 'Error de conexión');
    } finally {
      setIsLoading(false);
    }
  };

  const startRegistration = () => {
    if (!selectedEmployee) {
      Alert.alert('❌ Error', 'Selecciona un empleado primero');
      return;
    }
    
    Alert.alert(
      '📸 Registro Facial',
      `¿Tomar ${PHOTOS_REQUIRED} fotos para registrar el rostro de ${selectedEmployee.name}?`,
      [
        { text: '❌ Cancelar', style: 'cancel' },
        { 
          text: '📸 Comenzar',
          onPress: () => {
            setRegistrationPhotos([]);
            setCameraMode('register');
            setShowCamera(true);
          }
        }
      ]
    );
  };

  const startNewEmployeeFlow = () => {
    if (!newEmployeeName.trim()) {
      Alert.alert('❌ Error', 'Ingresa el nombre del empleado');
      return;
    }
    
    setNewEmployeePhotos([]);
    
    Alert.alert(
      '👤 Nuevo Empleado',
      `¿Crear empleado "${newEmployeeName}" con ${PHOTOS_REQUIRED} fotos?`,
      [
        { text: '❌ Cancelar', style: 'cancel' },
        { 
          text: '📸 Crear',
          onPress: () => {
            setNewEmployeePhotos([]);
            setCameraMode('newEmployee');
            setShowCamera(true);
          }
        }
      ]
    );
  };

  const createEmployeeWithPhotosDirectly = async (photos: string[], employeeName: string) => {
    setCreatingEmployee(true);
    setIsLoading(true);
    
    try {
      const response = await fetch(`${API_BASE_URL}/create-employee/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: employeeName,
          department: 'General',
          photos: photos
        })
      });
      
      const data = await response.json();
      
      if (data.success) {
        await loadEmployees();
        setNewEmployeeName('');
        setNewEmployeePhotos([]);
        setShowNewEmployeeModal(false);
        
        Alert.alert('✅ ¡Creado!', `Empleado ${data.employee.name} creado y registrado`);
      } else {
        Alert.alert('❌ Error', data.message || 'Error creando empleado');
      }
    } catch (error) {
      Alert.alert('❌ Error', 'Error de conexión creando empleado');
    } finally {
      setIsLoading(false);
      setCreatingEmployee(false);
    }
  };

  const deleteEmployee = async (employee: Employee) => {
    Alert.alert(
      '🗑️ Eliminar Empleado',
      `¿Estás seguro de eliminar a ${employee.name}?`,
      [
        { text: '❌ Cancelar', style: 'cancel' },
        {
          text: '🗑️ Eliminar',
          style: 'destructive',
          onPress: async () => {
            try {
              const response = await fetch(`${API_BASE_URL}/delete-employee/${employee.id}/`, {
                method: 'DELETE'
              });
              
              const data = await response.json();
              
              if (data.success) {
                setEmployees(prev => prev.filter(e => e.id !== employee.id));
                if (selectedEmployee?.id === employee.id) {
                  setSelectedEmployee(null);
                  await AsyncStorage.removeItem('selectedEmployee');
                }
                Alert.alert('✅ Eliminado', `${employee.name} eliminado del sistema`);
              }
            } catch (error) {
              Alert.alert('❌ Error', 'No se pudo eliminar el empleado');
            }
          }
        }
      ]
    );
  };

  const syncOfflineRecords = async () => {
    if (offlineRecords.length === 0 || !isOnline) return;
    
    try {
      const response = await fetch(`${API_BASE_URL}/sync-offline/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ offline_records: offlineRecords })
      });
      
      const data = await response.json();
      
      if (data.success) {
        setOfflineRecords([]);
        await saveToStorage('offlineRecords', []);
        Alert.alert('✅ Sincronizado', `${data.synced_count} registros sincronizados`);
      }
    } catch (error) {
      console.error('Error sync:', error);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar style="auto" />
      
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.title}>📱 Asistencia</Text>
        <Text style={[styles.status, !isOnline && styles.offline]}>
          {isOnline ? '🟢 Online' : '🔴 Offline'}
          {verificationInProgress && ` ⏱️ ${timeoutCounter}s`}
        </Text>
      </View>

      <ScrollView 
        style={styles.content}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
        }
      >
        {/* Empleado seleccionado */}
        <TouchableOpacity 
          style={styles.card}
          onPress={() => setShowEmployeeModal(true)}
        >
          <Text style={styles.label}>👤 Empleado:</Text>
          <Text style={styles.value}>
            {selectedEmployee ? selectedEmployee.name : 'Seleccionar empleado'}
          </Text>
          {selectedEmployee?.has_face_registered && (
            <Text style={styles.registered}>✅ Rostro registrado</Text>
          )}
        </TouchableOpacity>

        {/* Ubicación */}
        <View style={styles.card}>
          <Text style={styles.label}>📍 Ubicación:</Text>
          <Text style={styles.value}>{currentLocation}</Text>
        </View>

        {/* Botones de marcado manual */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>📝 Marcado Manual</Text>
          <View style={styles.buttonRow}>
            <TouchableOpacity 
              style={[styles.button, styles.entrada]}
              onPress={() => markManual('entrada')}
              disabled={!selectedEmployee || isLoading || verificationInProgress}
            >
              <Text style={styles.buttonText}>
                🟢 ENTRADA
              </Text>
            </TouchableOpacity>
            
            <TouchableOpacity 
              style={[styles.button, styles.salida]}
              onPress={() => markManual('salida')}
              disabled={!selectedEmployee || isLoading || verificationInProgress}
            >
              <Text style={styles.buttonText}>
                🔴 SALIDA
              </Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* Botones de verificación facial */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>📸 Verificación Facial</Text>
          <View style={styles.buttonRow}>
            <TouchableOpacity 
              style={[styles.button, styles.facial]}
              onPress={() => {
                setPendingType('entrada');
                setCameraMode('verify');
                setShowCamera(true);
              }}
              disabled={isLoading || verificationInProgress}
            >
              <Text style={styles.buttonText}>
                {verificationInProgress && pendingType === 'entrada' ? 
                  `⏱️ ${timeoutCounter}s` : '📸 ENTRADA'}
              </Text>
            </TouchableOpacity>
            
            <TouchableOpacity 
              style={[styles.button, styles.facial]}
              onPress={() => {
                setPendingType('salida');
                setCameraMode('verify');
                setShowCamera(true);
              }}
              disabled={isLoading || verificationInProgress}
            >
              <Text style={styles.buttonText}>
                {verificationInProgress && pendingType === 'salida' ? 
                  `⏱️ ${timeoutCounter}s` : '📸 SALIDA'}
              </Text>
            </TouchableOpacity>
          </View>

          {/* Botón de registro de rostro */}
          {selectedEmployee && !selectedEmployee.has_face_registered && (
            <TouchableOpacity 
              style={styles.registerButton}
              onPress={startRegistration}
              disabled={verificationInProgress}
            >
              <Text style={styles.registerText}>
                📸 Registrar rostro de {selectedEmployee.name}
              </Text>
            </TouchableOpacity>
          )}
        </View>

        {/* Sincronización offline */}
        {offlineRecords.length > 0 && isOnline && (
          <TouchableOpacity 
            style={styles.syncButton} 
            onPress={syncOfflineRecords}
          >
            <Text style={styles.syncText}>
              🔄 Sincronizar {offlineRecords.length} registros offline
            </Text>
          </TouchableOpacity>
        )}

        {/* Historial de asistencia */}
        <View style={styles.history}>
          <Text style={styles.historyTitle}>📋 Registros Recientes</Text>
          {attendanceHistory.slice(0, 10).map((record, index) => (
            <View key={record.id || index} style={styles.historyItem}>
              <Text style={styles.historyText}>
                {record.employee_name} - {record.attendance_type.toUpperCase()}
              </Text>
              <Text style={styles.historyTime}>
                {record.timestamp}
                {record.face_confidence && record.face_confidence > 0 && ' 📸'}
              </Text>
            </View>
          ))}
          {attendanceHistory.length === 0 && (
            <Text style={styles.emptyText}>Sin registros recientes</Text>
          )}
        </View>
      </ScrollView>

      {/* Indicador de carga */}
      {isLoading && (
        <View style={styles.loading}>
          <ActivityIndicator size="large" color="#007AFF" />
          <Text style={styles.loadingText}>Procesando...</Text>
        </View>
      )}

      {/* Modal de cámara */}
      <Modal visible={showCamera} animationType="slide">
        <View style={styles.cameraContainer}>
          <CameraView
            ref={cameraRef}
            style={styles.camera}
            facing={facing}
          >
            <View style={styles.cameraOverlay}>
              {/* Botón cerrar */}
              <TouchableOpacity 
                style={styles.closeCamera} 
                onPress={() => {
                  setShowCamera(false);
                  setRegistrationPhotos([]);
                  setNewEmployeePhotos([]);
                  setCameraMode(null);
                }}
              >
                <Text style={styles.closeCameraText}>✕</Text>
              </TouchableOpacity>
              
              {/* Información del modo */}
              {(cameraMode === 'register' || cameraMode === 'newEmployee') && (
                <View style={styles.cameraInfo}>
                  <Text style={styles.photoCounter}>
                    📸 Foto {(cameraMode === 'register' ? registrationPhotos.length : newEmployeePhotos.length) + 1}/{PHOTOS_REQUIRED}
                  </Text>
                  <Text style={styles.photoGuide}>
                    {photoGuides[cameraMode === 'register' ? registrationPhotos.length : newEmployeePhotos.length]}
                  </Text>
                </View>
              )}

              {cameraMode === 'verify' && (
                <View style={styles.cameraInfo}>
                  <Text style={styles.verifyTitle}>
                    🔍 Verificación Facial
                  </Text>
                  <Text style={styles.verifySubtitle}>
                    Centra tu rostro en la cámara
                  </Text>
                </View>
              )}
              
              {/* Controles de cámara */}
              <View style={styles.cameraControls}>
                <TouchableOpacity 
                  style={styles.flipButton}
                  onPress={() => setFacing(facing === 'back' ? 'front' : 'back')}
                >
                  <Text style={styles.controlText}>🔄</Text>
                </TouchableOpacity>
                
                <TouchableOpacity 
                  style={styles.captureButton} 
                  onPress={takePicture}
                  disabled={isLoading}
                >
                  <Text style={styles.captureText}>
                    {isLoading ? '⏳' : 
                    '📸'
                  }
                </Text>
                </TouchableOpacity>
                
                <View style={styles.placeholder} />
              </View>
            </View>
          </CameraView>
        </View>
      </Modal>

      {/* Modal de selección de empleados */}
      <Modal visible={showEmployeeModal} transparent animationType="fade">
        <View style={styles.modalOverlay}>
          <View style={styles.modal}>
            <Text style={styles.modalTitle}>👥 Empleados</Text>
            
            <ScrollView style={styles.employeeList}>
              {employees.map((emp) => (
                <View key={emp.id} style={styles.employeeItem}>
                  <TouchableOpacity
                    style={styles.employeeInfo}
                    onPress={async () => {
                      setSelectedEmployee(emp);
                      await saveToStorage('selectedEmployee', emp);
                      setShowEmployeeModal(false);
                    }}
                  >
                    <Text style={styles.employeeName}>
                      {emp.name}
                      {emp.has_face_registered && ' ✅'}
                    </Text>
                    <Text style={styles.employeeId}>{emp.employee_id}</Text>
                  </TouchableOpacity>
                  
                  <TouchableOpacity onPress={() => deleteEmployee(emp)}>
                    <Text style={styles.deleteText}>🗑️</Text>
                  </TouchableOpacity>
                </View>
              ))}
            </ScrollView>
            
            <View style={styles.modalButtons}>
              <TouchableOpacity 
                style={styles.modalButton}
                onPress={() => {
                  setShowEmployeeModal(false);
                  setShowNewEmployeeModal(true);
                }}
              >
                <Text style={styles.buttonText}>➕ Nuevo</Text>
              </TouchableOpacity>
              
              <TouchableOpacity 
                style={[styles.modalButton, styles.modalButtonSecondary]}
                onPress={() => setShowEmployeeModal(false)}
              >
                <Text style={styles.buttonText}>✕ Cerrar</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      {/* Modal de nuevo empleado */}
      <Modal visible={showNewEmployeeModal} transparent animationType="fade">
        <View style={styles.modalOverlay}>
          <View style={styles.modal}>
            <Text style={styles.modalTitle}>➕ Nuevo Empleado</Text>
            
            <TextInput
              style={styles.input}
              placeholder="Nombre completo"
              value={newEmployeeName}
              onChangeText={setNewEmployeeName}
              editable={!creatingEmployee}
              placeholderTextColor="#999"
            />
            
            <View style={styles.modalButtons}>
              <TouchableOpacity 
                style={[styles.modalButton, (!newEmployeeName.trim() || creatingEmployee) && styles.modalButtonDisabled]} 
                onPress={startNewEmployeeFlow}
                disabled={!newEmployeeName.trim() || creatingEmployee}
              >
                <Text style={styles.buttonText}>
                  {creatingEmployee ? '⏳ Creando...' : '📸 Crear'}
                </Text>
              </TouchableOpacity>
              
              <TouchableOpacity 
                style={[styles.modalButton, styles.modalButtonSecondary]}
                onPress={() => {
                  setShowNewEmployeeModal(false);
                  setNewEmployeeName('');
                  setNewEmployeePhotos([]);
                }}
                disabled={creatingEmployee}
              >
                <Text style={styles.buttonText}>✕ Cancelar</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f6fa',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 20,
    backgroundColor: '#fff',
    borderBottomWidth: 1,
    borderBottomColor: '#e1e8ed',
  },
  title: {
    fontSize: 22,
    fontWeight: 'bold',
    color: '#2c3e50',
  },
  status: {
    fontSize: 14,
    fontWeight: '500',
    color: '#27ae60',
  },
  offline: {
    color: '#e74c3c',
  },
  content: {
    flex: 1,
  },
  card: {
    backgroundColor: '#fff',
    margin: 15,
    padding: 20,
    borderRadius: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
  },
  label: {
    fontSize: 14,
    color: '#7f8c8d',
    marginBottom: 5,
    fontWeight: '500',
  },
  value: {
    fontSize: 16,
    color: '#2c3e50',
    fontWeight: '500',
  },
  registered: {
    fontSize: 12,
    color: '#27ae60',
    marginTop: 5,
    fontWeight: '500',
  },
  section: {
    margin: 15,
  },
  sectionTitle: {
    fontSize: 16,
    color: '#34495e',
    marginBottom: 15,
    fontWeight: '600',
  },
  buttonRow: {
    flexDirection: 'row',
    gap: 12,
  },
  button: {
    flex: 1,
    paddingVertical: 16,
    paddingHorizontal: 20,
    borderRadius: 12,
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
  },
  entrada: {
    backgroundColor: '#27ae60',
  },
  salida: {
    backgroundColor: '#e74c3c',
  },
  facial: {
    backgroundColor: '#3498db',
  },
  buttonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: 'bold',
  },
  registerButton: {
    marginTop: 15,
    backgroundColor: '#f8f9fa',
    padding: 15,
    borderRadius: 12,
    alignItems: 'center',
    borderWidth: 2,
    borderColor: '#3498db',
    borderStyle: 'dashed',
  },
  registerText: {
    color: '#3498db',
    fontSize: 14,
    fontWeight: '600',
  },
  syncButton: {
    margin: 15,
    backgroundColor: '#f39c12',
    padding: 15,
    borderRadius: 12,
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
  },
  syncText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: 'bold',
  },
  history: {
    margin: 15,
    backgroundColor: '#fff',
    padding: 20,
    borderRadius: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
  },
  historyTitle: {
    fontSize: 16,
    color: '#34495e',
    marginBottom: 15,
    fontWeight: '600',
  },
  historyItem: {
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#ecf0f1',
  },
  historyText: {
    fontSize: 14,
    color: '#2c3e50',
    fontWeight: '500',
  },
  historyTime: {
    fontSize: 12,
    color: '#7f8c8d',
    marginTop: 4,
  },
  emptyText: {
    color: '#bdc3c7',
    fontSize: 14,
    textAlign: 'center',
    fontStyle: 'italic',
  },
  loading: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(255,255,255,0.9)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  loadingText: {
    marginTop: 10,
    fontSize: 16,
    color: '#7f8c8d',
  },
  cameraContainer: {
    flex: 1,
    backgroundColor: '#000',
  },
  camera: {
    flex: 1,
  },
  cameraOverlay: {
    flex: 1,
    backgroundColor: 'transparent',
  },
  closeCamera: {
    position: 'absolute',
    top: 50,
    right: 20,
    backgroundColor: 'rgba(0,0,0,0.7)',
    width: 50,
    height: 50,
    borderRadius: 25,
    justifyContent: 'center',
    alignItems: 'center',
  },
  closeCameraText: {
    color: '#fff',
    fontSize: 24,
    fontWeight: 'bold',
  },
  cameraInfo: {
    position: 'absolute',
    top: 120,
    left: 0,
    right: 0,
    alignItems: 'center',
  },
  photoCounter: {
    fontSize: 20,
    color: '#fff',
    backgroundColor: 'rgba(0,0,0,0.7)',
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 20,
    fontWeight: 'bold',
  },
  photoGuide: {
    fontSize: 16,
    color: '#fff',
    backgroundColor: 'rgba(0,0,0,0.7)',
    paddingHorizontal: 15,
    paddingVertical: 8,
    borderRadius: 15,
    marginTop: 10,
  },
  verifyTitle: {
    fontSize: 24,
    color: '#fff',
    backgroundColor: 'rgba(0,0,0,0.7)',
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 20,
    fontWeight: 'bold',
  },
  verifySubtitle: {
    fontSize: 16,
    color: '#fff',
    backgroundColor: 'rgba(0,0,0,0.7)',
    paddingHorizontal: 15,
    paddingVertical: 8,
    borderRadius: 15,
    marginTop: 10,
  },
  cameraControls: {
    position: 'absolute',
    bottom: 50,
    left: 0,
    right: 0,
    flexDirection: 'row',
    justifyContent: 'space-around',
    alignItems: 'center',
    paddingHorizontal: 40,
  },
  flipButton: {
    backgroundColor: 'rgba(0,0,0,0.7)',
    width: 60,
    height: 60,
    borderRadius: 30,
    justifyContent: 'center',
    alignItems: 'center',
  },
  captureButton: {
    backgroundColor: '#3498db',
    width: 80,
    height: 80,
    borderRadius: 40,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 4,
    borderColor: '#fff',
  },
  captureText: {
    fontSize: 30,
  },
  controlText: {
    fontSize: 24,
  },
  placeholder: {
    width: 60,
    height: 60,
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  modal: {
    backgroundColor: '#fff',
    borderRadius: 15,
    padding: 25,
    width: '90%',
    maxHeight: '70%',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.25,
    shadowRadius: 10,
    elevation: 10,
  },
  modalTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    marginBottom: 20,
    textAlign: 'center',
    color: '#2c3e50',
  },
  employeeList: {
    maxHeight: 300,
  },
  employeeItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 15,
    borderBottomWidth: 1,
    borderBottomColor: '#ecf0f1',
  },
  employeeInfo: {
    flex: 1,
  },
  employeeName: {
    fontSize: 16,
    fontWeight: '600',
    color: '#2c3e50',
  },
  employeeId: {
    fontSize: 12,
    color: '#7f8c8d',
    marginTop: 2,
  },
  deleteText: {
    fontSize: 18,
    padding: 10,
  },
  input: {
    borderWidth: 1,
    borderColor: '#ddd',
    borderRadius: 10,
    padding: 15,
    fontSize: 16,
    marginBottom: 20,
    backgroundColor: '#f8f9fa',
  },
  modalButtons: {
    flexDirection: 'row',
    gap: 12,
    marginTop: 15,
  },
  modalButton: {
    flex: 1,
    padding: 15,
    backgroundColor: '#3498db',
    borderRadius: 10,
    alignItems: 'center',
  },
  modalButtonSecondary: {
    backgroundColor: '#95a5a6',
  },
  modalButtonDisabled: {
    backgroundColor: '#bdc3c7',
  },
});
