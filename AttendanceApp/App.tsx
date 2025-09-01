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
  Image,
  SafeAreaView,
  RefreshControl
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import AsyncStorage from '@react-native-async-storage/async-storage';
import NetInfo from '@react-native-community/netinfo';
import * as Location from 'expo-location';
import { CameraView, useCameraPermissions } from 'expo-camera';
import * as ImageManipulator from 'expo-image-manipulator';

// CAMBIA POR TU IP LOCAL
const API_BASE_URL = 'http://192.168.96.36:8000/api';

// Configuración de seguridad
const PHOTOS_REQUIRED = 5; // Requiere 5 fotos para registro

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
  const [currentLocation, setCurrentLocation] = useState<string>('Obteniendo ubicación...');
  const [coordinates, setCoordinates] = useState<{lat: number, lng: number} | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  
  const [permission, requestPermission] = useCameraPermissions();
  const [showCamera, setShowCamera] = useState(false);
  const [facing, setFacing] = useState<'front' | 'back'>('front');
  const [cameraMode, setCameraMode] = useState<'register' | 'verify' | null>(null);
  const [pendingType, setPendingType] = useState<'entrada' | 'salida'>('entrada');
  const cameraRef = useRef<CameraView>(null);
  
  // Estados para registro con múltiples fotos
  const [registrationPhotos, setRegistrationPhotos] = useState<string[]>([]);
  const [currentPhotoIndex, setCurrentPhotoIndex] = useState(0);
  const [showRegistrationGuide, setShowRegistrationGuide] = useState(false);
  
  const [showEmployeeModal, setShowEmployeeModal] = useState(false);
  const [showNewEmployeeModal, setShowNewEmployeeModal] = useState(false);
  const [newEmployeeName, setNewEmployeeName] = useState('');
  const [newEmployeePhotos, setNewEmployeePhotos] = useState<string[]>([]);

  // Guías para las 5 fotos
  const photoGuides = [
    'Foto 1: Mira de frente a la cámara',
    'Foto 2: Gira ligeramente a la izquierda',
    'Foto 3: Gira ligeramente a la derecha',
    'Foto 4: Inclina un poco hacia arriba',
    'Foto 5: Inclina un poco hacia abajo'
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
        setCurrentLocation('Sin permisos de ubicación');
        return;
      }

      const location = await Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.High,
      });

      const { latitude, longitude } = location.coords;
      setCoordinates({ lat: latitude, lng: longitude });
      setCurrentLocation(`${latitude.toFixed(4)}, ${longitude.toFixed(4)}`);
      
      try {
        const addresses = await Location.reverseGeocodeAsync({ latitude, longitude });
        if (addresses.length > 0) {
          const addr = addresses[0];
          setCurrentLocation(`${addr.street || ''} ${addr.city || ''} ${addr.region || ''}`.trim() || `${latitude.toFixed(4)}, ${longitude.toFixed(4)}`);
        }
      } catch (e) {
        // Mantener coordenadas
      }
    } catch (error) {
      setCurrentLocation('Error obteniendo ubicación');
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
      console.error('Error loading data:', error);
    }
  };

  const saveToStorage = async (key: string, data: any) => {
    try {
      await AsyncStorage.setItem(key, JSON.stringify(data));
    } catch (error) {
      console.error('Error saving:', error);
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
      console.error('Error loading employees:', error);
    }
  };

  const onRefresh = async () => {
    setRefreshing(true);
    await setupLocation();
    await loadEmployees();
    setRefreshing(false);
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
      
      const manipulated = await ImageManipulator.manipulateAsync(
        photo.uri,
        [{ resize: { width: 800 } }],
        { compress: 0.8, format: ImageManipulator.SaveFormat.JPEG, base64: true }
      );
      
      const photoData = `data:image/jpeg;base64,${manipulated.base64}`;
      
      if (cameraMode === 'register') {
        // Agregar foto a la colección de registro
        const newPhotos = [...registrationPhotos, photoData];
        setRegistrationPhotos(newPhotos);
        
        if (newPhotos.length < PHOTOS_REQUIRED) {
          // Necesitamos más fotos
          setCurrentPhotoIndex(newPhotos.length);
          Alert.alert(
            `Foto ${newPhotos.length}/${PHOTOS_REQUIRED}`,
            `Bien! Ahora ${photoGuides[newPhotos.length]}`,
            [{ text: 'OK' }]
          );
        } else {
          // Tenemos todas las fotos, enviar registro
          setShowCamera(false);
          await registerFaceWithMultiplePhotos(newPhotos);
        }
      } else if (cameraMode === 'verify') {
        // Verificación normal con una sola foto
        setShowCamera(false);
        await verifyFace(photoData, pendingType);
      }
      
    } catch (error) {
      Alert.alert('Error', 'No se pudo capturar la foto');
    } finally {
      setIsLoading(false);
    }
  };

  const registerFaceWithMultiplePhotos = async (photos: string[]) => {
    if (!selectedEmployee) {
      Alert.alert('Error', 'Selecciona un empleado primero');
      return;
    }
    
    if (photos.length < PHOTOS_REQUIRED) {
      Alert.alert('Error', `Se requieren ${PHOTOS_REQUIRED} fotos, solo hay ${photos.length}`);
      return;
    }
    
    setIsLoading(true);
    
    try {
      const response = await fetch(`${API_BASE_URL}/register-face/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          employee_id: selectedEmployee.id,
          photos: photos  // Enviamos las 5 fotos
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
        
        Alert.alert(
          '✅ Registro Completo',
          `Rostro registrado con ${data.photos_registered} fotos\nNivel de seguridad: ${data.security_level}`,
          [{ text: 'Excelente!' }]
        );
        
        // Limpiar fotos de registro
        setRegistrationPhotos([]);
        setCurrentPhotoIndex(0);
      } else {
        Alert.alert('Error', data.message || 'No se pudo registrar');
        
        // Si hay errores específicos con las fotos
        if (data.errors && data.errors.length > 0) {
          Alert.alert('Problemas con las fotos', data.errors.join('\n'));
        }
      }
    } catch (error) {
      Alert.alert('Error', 'Error registrando rostro');
    } finally {
      setIsLoading(false);
      setCameraMode(null);
    }
  };

  const verifyFace = async (photoData: string, type: 'entrada' | 'salida') => {
    const timestamp = new Date().toISOString();
    
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
      Alert.alert('📴', `${type} guardada offline`);
      return;
    }
    
    setIsLoading(true);
    
    try {
      const response = await fetch(`${API_BASE_URL}/verify-face/`, {
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
          face_confidence: parseFloat(data.confidence?.replace('%', '') || '0') / 100
        };
        
        const updated = [newRecord, ...attendanceHistory].slice(0, 20);
        setAttendanceHistory(updated);
        await saveToStorage('attendanceHistory', updated);
        
        Alert.alert(
          '✅ Verificación Exitosa',
          `${type.toUpperCase()} - ${data.employee.name}\nConfianza: ${data.confidence}\nSeguridad: ${data.security_check}`,
          [{ text: 'OK' }]
        );
      } else {
        Alert.alert(
          '❌ Verificación Fallida',
          `${data.message}\n\nMás cercano: ${data.closest_match || 'N/A'}\nConfianza: ${data.closest_confidence || 'N/A'}\nRequerido: ${data.required_confidence || 'N/A'}`,
          [{ text: 'OK' }]
        );
        
        if (data.suggestions) {
          Alert.alert('Sugerencias', data.suggestions.join('\n'));
        }
      }
    } catch (error) {
      Alert.alert('Error', 'Error de conexión');
    } finally {
      setIsLoading(false);
    }
  };

  const markManual = async (type: 'entrada' | 'salida') => {
    if (!selectedEmployee) {
      Alert.alert('Error', 'Selecciona un empleado');
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
      Alert.alert('📴', `${type} guardada offline`);
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
        
        Alert.alert('✅', `${type.toUpperCase()} - ${selectedEmployee.name}`);
      } else {
        Alert.alert('Error', data.message);
      }
    } catch (error) {
      Alert.alert('Error', 'Error de conexión');
    } finally {
      setIsLoading(false);
    }
  };

  const startRegistration = () => {
    if (!selectedEmployee) {
      Alert.alert('Error', 'Primero selecciona un empleado');
      return;
    }
    
    Alert.alert(
      '📸 Registro de Rostro',
      `Necesitamos tomar ${PHOTOS_REQUIRED} fotos desde diferentes ángulos para mayor seguridad.\n\n¿Listo para comenzar?`,
      [
        { text: 'Cancelar', style: 'cancel' },
        { 
          text: 'Comenzar',
          onPress: () => {
            setRegistrationPhotos([]);
            setCurrentPhotoIndex(0);
            setCameraMode('register');
            setShowCamera(true);
            setShowRegistrationGuide(true);
          }
        }
      ]
    );
  };

  const createEmployee = async () => {
    if (!newEmployeeName.trim()) {
      Alert.alert('Error', 'Ingresa un nombre');
      return;
    }
    
    setIsLoading(true);
    
    try {
      const response = await fetch(`${API_BASE_URL}/create-employee/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: newEmployeeName.trim(),
          department: 'General',
          photos: newEmployeePhotos  // Si hay fotos las enviamos
        })
      });
      
      const data = await response.json();
      
      if (data.success) {
        await loadEmployees();
        setNewEmployeeName('');
        setNewEmployeePhotos([]);
        setShowNewEmployeeModal(false);
        
        if (!data.face_registered && data.photos_required) {
          Alert.alert(
            '✅ Empleado Creado',
            `${data.employee.name} fue creado.\n\nNecesita registrar ${data.photos_required} fotos para usar reconocimiento facial.`,
            [{ text: 'OK' }]
          );
        } else {
          Alert.alert('✅', 'Empleado creado exitosamente');
        }
      } else {
        Alert.alert('Error', data.message);
      }
    } catch (error) {
      Alert.alert('Error', 'Error creando empleado');
    } finally {
      setIsLoading(false);
    }
  };

  const deleteEmployee = async (employee: Employee) => {
    Alert.alert(
      'Eliminar',
      `¿Eliminar a ${employee.name}?`,
      [
        { text: 'No', style: 'cancel' },
        {
          text: 'Sí',
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
                Alert.alert('✅', 'Eliminado');
              }
            } catch (error) {
              Alert.alert('Error', 'No se pudo eliminar');
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
        Alert.alert('✅', `${data.synced_count} sincronizados`);
      }
    } catch (error) {
      console.error('Error sync:', error);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar style="auto" />
      
      <View style={styles.header}>
        <Text style={styles.title}>Asistencia Segura</Text>
        <Text style={[styles.status, !isOnline && styles.offline]}>
          {isOnline ? '● Online' : '● Offline'}
        </Text>
      </View>

      <ScrollView 
        style={styles.content}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
        }
      >
        {/* Empleado */}
        <TouchableOpacity 
          style={styles.card}
          onPress={() => setShowEmployeeModal(true)}
        >
          <Text style={styles.label}>Empleado:</Text>
          <Text style={styles.value}>
            {selectedEmployee ? selectedEmployee.name : 'Seleccionar →'}
          </Text>
          {selectedEmployee?.has_face_registered && (
            <Text style={styles.faceRegistered}>✅ Rostro registrado</Text>
          )}
        </TouchableOpacity>

        {/* Ubicación */}
        <View style={styles.card}>
          <Text style={styles.label}>Ubicación:</Text>
          <Text style={styles.value}>{currentLocation}</Text>
        </View>

        {/* Botones Manual */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Manual (sin verificación)</Text>
          <View style={styles.buttonRow}>
            <TouchableOpacity 
              style={[styles.button, styles.entrada]}
              onPress={() => markManual('entrada')}
              disabled={!selectedEmployee || isLoading}
            >
              <Text style={styles.buttonText}>ENTRADA</Text>
            </TouchableOpacity>
            
            <TouchableOpacity 
              style={[styles.button, styles.salida]}
              onPress={() => markManual('salida')}
              disabled={!selectedEmployee || isLoading}
            >
              <Text style={styles.buttonText}>SALIDA</Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* Botones Facial */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Con Verificación Facial (SEGURO)</Text>
          <View style={styles.buttonRow}>
            <TouchableOpacity 
              style={[styles.button, styles.entrada]}
              onPress={() => {
                setPendingType('entrada');
                setCameraMode('verify');
                setShowCamera(true);
              }}
              disabled={isLoading}
            >
              <Text style={styles.buttonText}>📸 ENTRADA</Text>
            </TouchableOpacity>
            
            <TouchableOpacity 
              style={[styles.button, styles.salida]}
              onPress={() => {
                setPendingType('salida');
                setCameraMode('verify');
                setShowCamera(true);
              }}
              disabled={isLoading}
            >
              <Text style={styles.buttonText}>📸 SALIDA</Text>
            </TouchableOpacity>
          </View>

          {selectedEmployee && !selectedEmployee.has_face_registered && (
            <TouchableOpacity 
              style={styles.registerButton}
              onPress={startRegistration}
            >
              <Text style={styles.registerText}>
                📸 Registrar mi rostro ({PHOTOS_REQUIRED} fotos)
              </Text>
            </TouchableOpacity>
          )}
        </View>

        {/* Sync */}
        {offlineRecords.length > 0 && isOnline && (
          <TouchableOpacity style={styles.syncButton} onPress={syncOfflineRecords}>
            <Text style={styles.syncText}>Sincronizar {offlineRecords.length} registros</Text>
          </TouchableOpacity>
        )}

        {/* Historial */}
        <View style={styles.history}>
          <Text style={styles.historyTitle}>Últimos registros</Text>
          {attendanceHistory.slice(0, 10).map((record, index) => (
            <View key={record.id || index} style={styles.historyItem}>
              <Text style={styles.historyText}>
                {record.employee_name} - {record.attendance_type.toUpperCase()}
              </Text>
              <Text style={styles.historyTime}>
                {record.timestamp}
                {record.face_confidence && record.face_confidence > 0 && 
                  ` • 🔒 ${(record.face_confidence * 100).toFixed(0)}%`
                }
              </Text>
            </View>
          ))}
          {attendanceHistory.length === 0 && (
            <Text style={styles.emptyText}>No hay registros</Text>
          )}
        </View>
      </ScrollView>

      {/* Loading */}
      {isLoading && (
        <View style={styles.loading}>
          <ActivityIndicator size="large" color="#000" />
        </View>
      )}

      {/* Modal Cámara */}
      <Modal visible={showCamera} animationType="slide">
        <View style={styles.cameraContainer}>
          <CameraView
            ref={cameraRef}
            style={styles.camera}
            facing={facing}
          >
            <View style={styles.cameraOverlay}>
              <TouchableOpacity 
                style={styles.closeCamera} 
                onPress={() => {
                  setShowCamera(false);
                  setRegistrationPhotos([]);
                  setCurrentPhotoIndex(0);
                  setCameraMode(null);
                }}
              >
                <Text style={styles.closeCameraText}>✕</Text>
              </TouchableOpacity>
              
              {cameraMode === 'register' && (
                <View style={styles.registrationInfo}>
                  <Text style={styles.photoCounter}>
                    Foto {registrationPhotos.length + 1} de {PHOTOS_REQUIRED}
                  </Text>
                  <Text style={styles.photoGuide}>
                    {photoGuides[registrationPhotos.length]}
                  </Text>
                </View>
              )}
              
              <View style={styles.cameraGuide} />
              
              <View style={styles.cameraControls}>
                <TouchableOpacity onPress={() => setFacing(facing === 'back' ? 'front' : 'back')}>
                  <Text style={styles.flipText}>🔄</Text>
                </TouchableOpacity>
                
                <TouchableOpacity 
                  style={styles.captureButton} 
                  onPress={takePicture}
                  disabled={isLoading}
                >
                  <View style={styles.captureInner} />
                </TouchableOpacity>
                
                <View style={{ width: 40 }} />
              </View>
            </View>
          </CameraView>
        </View>
      </Modal>

      {/* Modal Empleados */}
      <Modal visible={showEmployeeModal} transparent animationType="fade">
        <View style={styles.modalOverlay}>
          <View style={styles.modal}>
            <Text style={styles.modalTitle}>Empleados</Text>
            
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
                      {emp.name} {emp.has_face_registered && '✅'}
                    </Text>
                    <Text style={styles.employeeId}>{emp.employee_id}</Text>
                  </TouchableOpacity>
                  
                  <TouchableOpacity onPress={() => deleteEmployee(emp)}>
                    <Text style={styles.deleteText}>🗑</Text>
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
                <Text>Nuevo</Text>
              </TouchableOpacity>
              
              <TouchableOpacity 
                style={styles.modalButton}
                onPress={() => setShowEmployeeModal(false)}
              >
                <Text>Cerrar</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      {/* Modal Nuevo Empleado */}
      <Modal visible={showNewEmployeeModal} transparent animationType="fade">
        <View style={styles.modalOverlay}>
          <View style={styles.modal}>
            <Text style={styles.modalTitle}>Nuevo Empleado</Text>
            
            <TextInput
              style={styles.input}
              placeholder="Nombre completo"
              value={newEmployeeName}
              onChangeText={setNewEmployeeName}
              autoFocus
            />
            
            <Text style={styles.photoHint}>
              El registro facial se hará después de crear el empleado
            </Text>
            
            <View style={styles.modalButtons}>
              <TouchableOpacity style={styles.modalButton} onPress={createEmployee}>
                <Text>Crear</Text>
              </TouchableOpacity>
              
              <TouchableOpacity 
                style={styles.modalButton}
                onPress={() => {
                  setShowNewEmployeeModal(false);
                  setNewEmployeeName('');
                  setNewEmployeePhotos([]);
                }}
              >
                <Text>Cancelar</Text>
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
    backgroundColor: '#fff',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 20,
    borderBottomWidth: 1,
    borderBottomColor: '#eee',
  },
  title: {
    fontSize: 24,
    fontWeight: '600',
  },
  status: {
    fontSize: 12,
    color: 'green',
  },
  offline: {
    color: 'red',
  },
  content: {
    flex: 1,
  },
  card: {
    padding: 15,
    margin: 15,
    marginBottom: 0,
    backgroundColor: '#f5f5f5',
    borderRadius: 8,
  },
  label: {
    fontSize: 12,
    color: '#666',
    marginBottom: 5,
  },
  value: {
    fontSize: 16,
  },
  faceRegistered: {
    fontSize: 12,
    color: 'green',
    marginTop: 5,
  },
  section: {
    padding: 15,
  },
  sectionTitle: {
    fontSize: 14,
    color: '#666',
    marginBottom: 10,
  },
  buttonRow: {
    flexDirection: 'row',
    gap: 10,
  },
  button: {
    flex: 1,
    padding: 20,
    borderRadius: 8,
    alignItems: 'center',
  },
  entrada: {
    backgroundColor: '#000',
  },
  salida: {
    backgroundColor: '#666',
  },
  buttonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  registerButton: {
    marginTop: 10,
    padding: 12,
    backgroundColor: '#f5f5f5',
    borderRadius: 8,
    alignItems: 'center',
  },
  registerText: {
    fontSize: 14,
  },
  syncButton: {
    margin: 15,
    padding: 15,
    backgroundColor: '#f5f5f5',
    borderRadius: 8,
    alignItems: 'center',
  },
  syncText: {
    fontSize: 14,
  },
  history: {
    padding: 15,
  },
  historyTitle: {
    fontSize: 14,
    color: '#666',
    marginBottom: 10,
  },
  historyItem: {
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#f5f5f5',
  },
  historyText: {
    fontSize: 14,
  },
  historyTime: {
    fontSize: 12,
    color: '#999',
    marginTop: 2,
  },
  emptyText: {
    color: '#999',
    fontSize: 14,
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
  
  // Camera
  cameraContainer: {
    flex: 1,
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
    zIndex: 1,
  },
  closeCameraText: {
    color: '#fff',
    fontSize: 40,
  },
  registrationInfo: {
    position: 'absolute',
    top: 100,
    left: 0,
    right: 0,
    alignItems: 'center',
    zIndex: 1,
  },
  photoCounter: {
    fontSize: 24,
    color: '#fff',
    fontWeight: 'bold',
    backgroundColor: 'rgba(0,0,0,0.5)',
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 20,
  },
  photoGuide: {
    fontSize: 18,
    color: '#fff',
    marginTop: 10,
    backgroundColor: 'rgba(0,0,0,0.7)',
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 15,
    textAlign: 'center',
  },
  cameraGuide: {
    position: 'absolute',
    top: '50%',
    left: '50%',
    width: 200,
    height: 200,
    marginLeft: -100,
    marginTop: -100,
    borderWidth: 2,
    borderColor: '#fff',
    borderRadius: 100,
  },
  cameraControls: {
    position: 'absolute',
    bottom: 50,
    left: 0,
    right: 0,
    flexDirection: 'row',
    justifyContent: 'space-around',
    alignItems: 'center',
  },
  flipText: {
    fontSize: 40,
  },
  captureButton: {
    width: 70,
    height: 70,
    borderRadius: 35,
    backgroundColor: '#fff',
    padding: 5,
  },
  captureInner: {
    flex: 1,
    borderRadius: 30,
    backgroundColor: '#000',
  },
  
  // Modals
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  modal: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 20,
    width: '90%',
    maxHeight: '70%',
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: '600',
    marginBottom: 15,
  },
  employeeList: {
    maxHeight: 300,
  },
  employeeItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#f5f5f5',
  },
  employeeInfo: {
    flex: 1,
  },
  employeeName: {
    fontSize: 16,
  },
  employeeId: {
    fontSize: 12,
    color: '#999',
    marginTop: 2,
  },
  deleteText: {
    fontSize: 20,
    padding: 10,
  },
  input: {
    borderWidth: 1,
    borderColor: '#ddd',
    borderRadius: 8,
    padding: 12,
    fontSize: 16,
    marginBottom: 15,
  },
  photoHint: {
    fontSize: 12,
    color: '#666',
    textAlign: 'center',
    marginBottom: 15,
  },
  modalButtons: {
    flexDirection: 'row',
    gap: 10,
    marginTop: 15,
  },
  modalButton: {
    flex: 1,
    padding: 12,
    backgroundColor: '#f5f5f5',
    borderRadius: 8,
    alignItems: 'center',
  },
});