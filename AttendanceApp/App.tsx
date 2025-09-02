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
  const [currentLocation, setCurrentLocation] = useState<string>('Obteniendo ubicación...');
  const [coordinates, setCoordinates] = useState<{lat: number, lng: number} | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  
  const [permission, requestPermission] = useCameraPermissions();
  const [showCamera, setShowCamera] = useState(false);
  const [facing, setFacing] = useState<'front' | 'back'>('front');
  const [cameraMode, setCameraMode] = useState<'register' | 'verify' | 'newEmployee' | null>(null);
  const [pendingType, setPendingType] = useState<'entrada' | 'salida'>('entrada');
  const cameraRef = useRef<CameraView>(null);
  
  const [registrationPhotos, setRegistrationPhotos] = useState<string[]>([]);
  const [showEmployeeModal, setShowEmployeeModal] = useState(false);
  const [showNewEmployeeModal, setShowNewEmployeeModal] = useState(false);
  const [newEmployeeName, setNewEmployeeName] = useState('');
  const [newEmployeePhotos, setNewEmployeePhotos] = useState<string[]>([]);
  const [creatingEmployee, setCreatingEmployee] = useState(false);

  const [verificationInProgress, setVerificationInProgress] = useState(false);
  const [timeoutCounter, setTimeoutCounter] = useState(0);

  const photoGuides = [
    'Foto 1: Frente',
    'Foto 2: Izquierda',
    'Foto 3: Derecha', 
    'Foto 4: Arriba',
    'Foto 5: Abajo'
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
        setCurrentLocation('Sin permisos');
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
          setCurrentLocation(`${addr.street || ''} ${addr.city || ''}`.trim() || `${latitude.toFixed(4)}, ${longitude.toFixed(4)}`);
        }
      } catch (e) {
        // Mantener coordenadas
      }
    } catch (error) {
      setCurrentLocation('Error ubicación');
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
        const currentPhotos = [...registrationPhotos, photoData];
        setRegistrationPhotos(currentPhotos);
        
        if (currentPhotos.length < PHOTOS_REQUIRED) {
          Alert.alert(
            `Foto ${currentPhotos.length}/${PHOTOS_REQUIRED}`,
            `${photoGuides[currentPhotos.length]}`,
            [{ text: 'OK' }]
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
            `Foto ${currentPhotos.length}/${PHOTOS_REQUIRED}`,
            `${photoGuides[currentPhotos.length]}`,
            [{ text: 'OK' }]
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
      Alert.alert('Error', 'No se pudo capturar la foto');
      setIsLoading(false);
    }
  };

  const verifyFaceWithTimeout = async (photoData: string, type: 'entrada' | 'salida') => {
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
    Alert.alert('Offline', `${type} guardada offline`);
    return;
  }
  
  setVerificationInProgress(true);
  setTimeoutCounter(0);
  
  const timeoutInterval = setInterval(() => {
    setTimeoutCounter(prev => prev + 1);
  }, 1000);

  // TIMEOUT REAL DE 10 SEGUNDOS
  const timeoutPromise = new Promise((_, reject) => {
    setTimeout(() => {
      reject(new Error('TIMEOUT_EXCEEDED'));
    }, 10000); // 10 segundos exactos
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
    // Race entre fetch y timeout
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
      
      Alert.alert('Verificado', `${type.toUpperCase()} - ${data.employee.name}`);
    } else {
      Alert.alert('No verificado', 'Rostro no reconocido');
    }
  } catch (error: any) {
    clearInterval(timeoutInterval);
    setVerificationInProgress(false);
    
    if (error.message === 'TIMEOUT_EXCEEDED') {
      Alert.alert(
        'Tiempo excedido',
        'La verificación tardó más de 10 segundos. Marcación rechazada.'
      );
    } else {
      Alert.alert('Error', 'Error de conexión');
    }
  }
};
  const registerFaceWithMultiplePhotos = async (photos: string[]) => {
    if (!selectedEmployee) {
      Alert.alert('Error', 'Selecciona un empleado');
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
        
        Alert.alert('Registrado', 'Rostro registrado correctamente');
        setRegistrationPhotos([]);
      } else {
        Alert.alert('Error', data.message);
      }
    } catch (error) {
      Alert.alert('Error', 'Error registrando rostro');
    } finally {
      setIsLoading(false);
      setCameraMode(null);
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
      Alert.alert('Offline', `${type} guardada offline`);
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
        
        Alert.alert('Registrado', `${type.toUpperCase()} - ${selectedEmployee.name}`);
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
      Alert.alert('Error', 'Selecciona un empleado');
      return;
    }
    
    Alert.alert(
      'Registro',
      `Tomar ${PHOTOS_REQUIRED} fotos para registrar rostro?`,
      [
        { text: 'No', style: 'cancel' },
        { 
          text: 'Si',
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
      Alert.alert('Error', 'Ingresa un nombre');
      return;
    }
    
    setNewEmployeePhotos([]);
    
    Alert.alert(
      'Nuevo Empleado',
      `Tomar ${PHOTOS_REQUIRED} fotos para ${newEmployeeName}?`,
      [
        { text: 'No', style: 'cancel' },
        { 
          text: 'Si',
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
        
        Alert.alert('Creado', `Empleado ${data.employee.name} creado`);
      } else {
        Alert.alert('Error', data.message);
      }
    } catch (error) {
      Alert.alert('Error', 'Error creando empleado');
    } finally {
      setIsLoading(false);
      setCreatingEmployee(false);
    }
  };

  const deleteEmployee = async (employee: Employee) => {
    Alert.alert(
      'Eliminar',
      `Eliminar a ${employee.name}?`,
      [
        { text: 'No', style: 'cancel' },
        {
          text: 'Si',
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
                Alert.alert('Eliminado', `${employee.name} eliminado`);
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
        Alert.alert('Sincronizado', `${data.synced_count} registros sincronizados`);
      }
    } catch (error) {
      console.error('Error sync:', error);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar style="auto" />
      
      <View style={styles.header}>
        <Text style={styles.title}>Asistencia</Text>
        <Text style={[styles.status, !isOnline && styles.offline]}>
          {isOnline ? 'Online' : 'Offline'}
          {verificationInProgress && ` - ${timeoutCounter}s`}
        </Text>
      </View>

      <ScrollView 
        style={styles.content}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
        }
      >
        <TouchableOpacity 
          style={styles.card}
          onPress={() => setShowEmployeeModal(true)}
        >
          <Text style={styles.label}>Empleado:</Text>
          <Text style={styles.value}>
            {selectedEmployee ? selectedEmployee.name : 'Seleccionar'}
          </Text>
          {selectedEmployee?.has_face_registered && (
            <Text style={styles.registered}>Rostro registrado</Text>
          )}
        </TouchableOpacity>

        <View style={styles.card}>
          <Text style={styles.label}>Ubicación:</Text>
          <Text style={styles.value}>{currentLocation}</Text>
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Manual</Text>
          <View style={styles.buttonRow}>
            <TouchableOpacity 
              style={[styles.button, styles.entrada]}
              onPress={() => markManual('entrada')}
              disabled={!selectedEmployee || isLoading || verificationInProgress}
            >
              <Text style={styles.buttonText}>ENTRADA</Text>
            </TouchableOpacity>
            
            <TouchableOpacity 
              style={[styles.button, styles.salida]}
              onPress={() => markManual('salida')}
              disabled={!selectedEmployee || isLoading || verificationInProgress}
            >
              <Text style={styles.buttonText}>SALIDA</Text>
            </TouchableOpacity>
          </View>
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Facial</Text>
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
                  `${timeoutCounter}s` : 'ENTRADA'}
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
                  `${timeoutCounter}s` : 'SALIDA'}
              </Text>
            </TouchableOpacity>
          </View>

          {selectedEmployee && !selectedEmployee.has_face_registered && (
            <TouchableOpacity 
              style={styles.registerButton}
              onPress={startRegistration}
              disabled={verificationInProgress}
            >
              <Text style={styles.registerText}>
                Registrar rostro
              </Text>
            </TouchableOpacity>
          )}
        </View>

        {offlineRecords.length > 0 && isOnline && (
          <TouchableOpacity 
            style={styles.syncButton} 
            onPress={syncOfflineRecords}
          >
            <Text style={styles.syncText}>
              Sincronizar {offlineRecords.length} registros
            </Text>
          </TouchableOpacity>
        )}

        <View style={styles.history}>
          <Text style={styles.historyTitle}>Registros</Text>
          {attendanceHistory.slice(0, 10).map((record, index) => (
            <View key={record.id || index} style={styles.historyItem}>
              <Text style={styles.historyText}>
                {record.employee_name} - {record.attendance_type.toUpperCase()}
              </Text>
              <Text style={styles.historyTime}>
                {record.timestamp}
                {record.face_confidence && record.face_confidence > 0 && ' (Facial)'}
              </Text>
            </View>
          ))}
          {attendanceHistory.length === 0 && (
            <Text style={styles.emptyText}>Sin registros</Text>
          )}
        </View>
      </ScrollView>

      {isLoading && (
        <View style={styles.loading}>
          <ActivityIndicator size="large" color="#000" />
        </View>
      )}

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
                  setNewEmployeePhotos([]);
                  setCameraMode(null);
                }}
              >
                <Text style={styles.closeCameraText}>X</Text>
              </TouchableOpacity>
              
              {(cameraMode === 'register' || cameraMode === 'newEmployee') && (
                <View style={styles.info}>
                  <Text style={styles.photoCounter}>
                    {(cameraMode === 'register' ? registrationPhotos.length : newEmployeePhotos.length) + 1}/{PHOTOS_REQUIRED}
                  </Text>
                </View>
              )}

              {cameraMode === 'verify' && (
                <View style={styles.info}>
                  <Text style={styles.verifyTitle}>
                    Verificación Facial
                  </Text>
                </View>
              )}
              
              <View style={styles.cameraControls}>
                <TouchableOpacity onPress={() => setFacing(facing === 'back' ? 'front' : 'back')}>
                  <Text style={styles.flipText}>Flip</Text>
                </TouchableOpacity>
                
                <TouchableOpacity 
                  style={styles.captureButton} 
                  onPress={takePicture}
                  disabled={isLoading}
                >
                  <Text style={styles.captureText}>Tomar</Text>
                </TouchableOpacity>
              </View>
            </View>
          </CameraView>
        </View>
      </Modal>

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
                      {emp.name}
                      {emp.has_face_registered && ' ✓'}
                    </Text>
                    <Text style={styles.employeeId}>{emp.employee_id}</Text>
                  </TouchableOpacity>
                  
                  <TouchableOpacity onPress={() => deleteEmployee(emp)}>
                    <Text style={styles.deleteText}>Eliminar</Text>
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

      <Modal visible={showNewEmployeeModal} transparent animationType="fade">
        <View style={styles.modalOverlay}>
          <View style={styles.modal}>
            <Text style={styles.modalTitle}>Nuevo Empleado</Text>
            
            <TextInput
              style={styles.input}
              placeholder="Nombre"
              value={newEmployeeName}
              onChangeText={setNewEmployeeName}
              editable={!creatingEmployee}
            />
            
            <View style={styles.modalButtons}>
              <TouchableOpacity 
                style={styles.modalButton} 
                onPress={startNewEmployeeFlow}
                disabled={!newEmployeeName.trim() || creatingEmployee}
              >
                <Text>Crear</Text>
              </TouchableOpacity>
              
              <TouchableOpacity 
                style={styles.modalButton}
                onPress={() => {
                  setShowNewEmployeeModal(false);
                  setNewEmployeeName('');
                  setNewEmployeePhotos([]);
                }}
                disabled={creatingEmployee}
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
    fontSize: 20,
    fontWeight: 'bold',
  },
  status: {
    fontSize: 14,
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
 registered: {
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
   backgroundColor: '#007AFF',
 },
 salida: {
   backgroundColor: '#666',
 },
 facial: {
   backgroundColor: '#28a745',
 },
 buttonText: {
   color: '#fff',
   fontSize: 16,
   fontWeight: 'bold',
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
   textAlign: 'center',
 },
 loading: {
   position: 'absolute',
   top: 0,
   left: 0,
   right: 0,
   bottom: 0,
   backgroundColor: 'rgba(255,255,255,0.8)',
   justifyContent: 'center',
   alignItems: 'center',
 },
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
   backgroundColor: 'rgba(0,0,0,0.5)',
   padding: 10,
   borderRadius: 20,
 },
 closeCameraText: {
   color: '#fff',
   fontSize: 20,
 },
 info: {
   position: 'absolute',
   top: 100,
   left: 0,
   right: 0,
   alignItems: 'center',
 },
 photoCounter: {
   fontSize: 20,
   color: '#fff',
   backgroundColor: 'rgba(0,0,0,0.5)',
   padding: 10,
   borderRadius: 10,
 },
 verifyTitle: {
   fontSize: 20,
   color: '#fff',
   backgroundColor: 'rgba(0,0,0,0.5)',
   padding: 10,
   borderRadius: 10,
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
   fontSize: 18,
   color: '#fff',
   backgroundColor: 'rgba(0,0,0,0.5)',
   padding: 10,
   borderRadius: 10,
 },
 captureButton: {
   backgroundColor: '#007AFF',
   padding: 15,
   borderRadius: 10,
 },
 captureText: {
   color: '#fff',
   fontSize: 16,
   fontWeight: 'bold',
 },
 modalOverlay: {
   flex: 1,
   backgroundColor: 'rgba(0,0,0,0.5)',
   justifyContent: 'center',
   alignItems: 'center',
 },
 modal: {
   backgroundColor: '#fff',
   borderRadius: 10,
   padding: 20,
   width: '90%',
   maxHeight: '70%',
 },
 modalTitle: {
   fontSize: 18,
   fontWeight: 'bold',
   marginBottom: 15,
   textAlign: 'center',
 },
 employeeList: {
   maxHeight: 300,
 },
 employeeItem: {
   flexDirection: 'row',
   justifyContent: 'space-between',
   alignItems: 'center',
   paddingVertical: 10,
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
   fontSize: 14,
   color: 'red',
 },
 input: {
   borderWidth: 1,
   borderColor: '#ddd',
   borderRadius: 8,
   padding: 12,
   fontSize: 16,
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