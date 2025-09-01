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
  Platform
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import AsyncStorage from '@react-native-async-storage/async-storage';
import NetInfo from '@react-native-community/netinfo';
import * as Location from 'expo-location';
import { Camera, CameraView } from 'expo-camera';
import * as ImageManipulator from 'expo-image-manipulator';

// CAMBIA POR TU IP LOCAL
const API_BASE_URL = 'http://192.168.96.36:8000/api';

interface Employee {
  id: string;
  name: string;
  employee_id: string;
  department: string;
  position: string;
  has_face_registered?: boolean;
  face_registration_date?: string;
}

interface AttendanceRecord {
  id: string;
  employee_name: string;
  attendance_type: string;
  timestamp: string;
  formatted_timestamp: string;
  location_lat: number;
  location_lng: number;
  address: string;
  is_offline_sync: boolean;
  face_confidence?: number;
}

interface OfflineRecord {
  local_id: string;
  employee_name?: string;
  employee_id?: string;
  type: string;
  timestamp: string;
  latitude?: number;
  longitude?: number;
  address: string;
  notes: string;
  photo?: string;
}

type CameraModeType = 'register' | 'verify' | 'new-employee' | null;

export default function App() {
  // Estados principales
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [selectedEmployee, setSelectedEmployee] = useState<Employee | null>(null);
  const [attendanceHistory, setAttendanceHistory] = useState<AttendanceRecord[]>([]);
  const [offlineRecords, setOfflineRecords] = useState<OfflineRecord[]>([]);
  const [isOnline, setIsOnline] = useState(true);
  const [isSyncing, setIsSyncing] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [currentLocation, setCurrentLocation] = useState<string>('Obteniendo ubicación...');
  const [coordinates, setCoordinates] = useState<{lat: number, lng: number} | null>(null);
  
  // Estados para cámara y reconocimiento facial
  const [hasCameraPermission, setHasCameraPermission] = useState<boolean | null>(null);
  const [showCamera, setShowCamera] = useState(false);
  const [facing, setFacing] = useState<'front' | 'back'>('front');
  const [isProcessingPhoto, setIsProcessingPhoto] = useState(false);
  const [cameraMode, setCameraMode] = useState<CameraModeType>(null);
  const [pendingAttendanceType, setPendingAttendanceType] = useState<'entrada' | 'salida'>('entrada');
  const cameraRef = useRef<CameraView>(null);
  
  // Estados para modales
  const [showEmployeeModal, setShowEmployeeModal] = useState(false);
  const [showNewEmployeeModal, setShowNewEmployeeModal] = useState(false);
  const [newEmployeeName, setNewEmployeeName] = useState('');
  const [newEmployeeDepartment, setNewEmployeeDepartment] = useState('');
  const [newEmployeePhoto, setNewEmployeePhoto] = useState<string | null>(null);
  const [useFacialRecognition, setUseFacialRecognition] = useState(true);

  useEffect(() => {
    initializeApp();
  }, []);

  const initializeApp = async () => {
    await loadStoredData();
    await setupLocation();
    await setupCamera();
    setupNetworkListener();
    await loadEmployees();
  };

  const setupCamera = async () => {
    const { status } = await Camera.requestCameraPermissionsAsync();
    setHasCameraPermission(status === 'granted');
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

      try {
        const addresses = await Location.reverseGeocodeAsync({
          latitude,
          longitude,
        });

        if (addresses.length > 0) {
          const address = addresses[0];
          const fullAddress = `${address.street || ''} ${address.streetNumber || ''}, ${address.city || ''}, ${address.region || ''}`.trim();
          setCurrentLocation(fullAddress || `${latitude.toFixed(6)}, ${longitude.toFixed(6)}`);
        } else {
          setCurrentLocation(`${latitude.toFixed(6)}, ${longitude.toFixed(6)}`);
        }
      } catch (error) {
        setCurrentLocation(`${latitude.toFixed(6)}, ${longitude.toFixed(6)}`);
      }
    } catch (error) {
      console.error('Error obteniendo ubicación:', error);
      setCurrentLocation('Error obteniendo ubicación');
    }
  };

  const setupNetworkListener = () => {
    NetInfo.addEventListener(state => {
      const wasOffline = !isOnline;
      const nowOnline = state.isConnected && state.isInternetReachable;
      
      setIsOnline(nowOnline || false);
      
      if (wasOffline && nowOnline) {
        setTimeout(async () => {
          if (offlineRecords.length > 0) {
            syncOfflineRecords();
          }
          await loadEmployees();
        }, 2000);
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
      
      const storedUseFacial = await AsyncStorage.getItem('useFacialRecognition');
      if (storedUseFacial !== null) setUseFacialRecognition(JSON.parse(storedUseFacial));
    } catch (error) {
      console.error('Error loading data:', error);
    }
  };

  const saveToStorage = async (key: string, data: any) => {
    try {
      await AsyncStorage.setItem(key, JSON.stringify(data));
    } catch (error) {
      console.error('Error saving data:', error);
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

  const takePicture = async () => {
    if (!cameraRef.current) return;
    
    try {
      setIsProcessingPhoto(true);
      
      // Capturar foto usando el nuevo método
      const photo = await cameraRef.current.takePictureAsync({
        quality: 0.7,
        base64: true,
        skipProcessing: false
      });
      
      if (!photo || !photo.base64) {
        throw new Error('No se pudo obtener la imagen');
      }
      
      // Procesar imagen
      const manipulated = await ImageManipulator.manipulateAsync(
        photo.uri,
        [
          { resize: { width: 600 } },
          ...(facing === 'front' ? [{ flip: ImageManipulator.FlipType.Horizontal }] : [])
        ],
        { 
          compress: 0.7,
          format: ImageManipulator.SaveFormat.JPEG,
          base64: true
        }
      );
      
      if (!manipulated.base64) {
        throw new Error('No se pudo procesar la imagen');
      }
      
      const photoData = `data:image/jpeg;base64,${manipulated.base64}`;
      
      // Cerrar cámara
      setShowCamera(false);
      
      // Procesar según el modo
      if (cameraMode === 'register') {
        await registerEmployeeFace(photoData);
      } else if (cameraMode === 'verify') {
        await verifyAndMarkAttendance(photoData, pendingAttendanceType);
      } else if (cameraMode === 'new-employee') {
        setNewEmployeePhoto(photoData);
        setShowNewEmployeeModal(true);
      }
      
    } catch (error) {
      console.error('Error capturando foto:', error);
      Alert.alert('Error', 'No se pudo capturar la foto. Intenta nuevamente.');
    } finally {
      setIsProcessingPhoto(false);
      setCameraMode(null);
    }
  };

  const registerEmployeeFace = async (photoData: string) => {
    if (!selectedEmployee) {
      Alert.alert('Error', 'Primero selecciona un empleado');
      return;
    }
    
    setIsProcessingPhoto(true);
    
    try {
      console.log('Registrando rostro para:', selectedEmployee.name);
      
      const response = await fetch(`${API_BASE_URL}/register-face/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          employee_id: selectedEmployee.id,
          photo: photoData
        })
      });
      
      const data = await response.json();
      
      if (data.success) {
        // Actualizar empleado localmente
        setEmployees(prev => prev.map(emp => 
          emp.id === selectedEmployee.id 
            ? { ...emp, has_face_registered: true }
            : emp
        ));
        
        setSelectedEmployee({
          ...selectedEmployee,
          has_face_registered: true
        });
        
        Alert.alert(
          '✅ Registro Exitoso',
          `Rostro registrado correctamente para ${selectedEmployee.name}\n\nAhora puedes usar reconocimiento facial para marcar asistencia.`,
          [{ text: 'Excelente!' }]
        );
      } else {
        Alert.alert(
          'Error en Registro',
          data.message || 'No se pudo registrar el rostro',
          data.tips ? [
            { text: 'Reintentar', onPress: () => openCamera('register') },
            { text: 'Cancelar', style: 'cancel' }
          ] : [{ text: 'OK' }]
        );
      }
    } catch (error) {
      console.error('Error registrando rostro:', error);
      Alert.alert('Error', 'Error conectando con el servidor');
    } finally {
      setIsProcessingPhoto(false);
    }
  };

  const verifyAndMarkAttendance = async (photoData: string, type: 'entrada' | 'salida') => {
    const now = new Date();
    const timestamp = now.toISOString();
    
    // Si está offline, guardar con foto
    if (!isOnline) {
      const offlineRecord: OfflineRecord = {
        local_id: `offline_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
        type: type,
        timestamp: timestamp,
        latitude: coordinates?.lat,
        longitude: coordinates?.lng,
        address: currentLocation,
        notes: 'Verificación facial offline',
        photo: photoData
      };
      
      const updatedOfflineRecords = [...offlineRecords, offlineRecord];
      setOfflineRecords(updatedOfflineRecords);
      await saveToStorage('offlineRecords', updatedOfflineRecords);
      
      Alert.alert(
        '📴 Registro Offline',
        `${type.toUpperCase()} guardada con foto\n\nSe verificará automáticamente cuando vuelva la conexión.`,
        [{ text: 'OK' }]
      );
      return;
    }
    
    setIsProcessingPhoto(true);
    
    try {
      console.log('Verificando rostro para:', type);
      
      const response = await fetch(`${API_BASE_URL}/verify-face/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          photo: photoData,
          type: type,
          latitude: coordinates?.lat,
          longitude: coordinates?.lng,
          address: currentLocation
        })
      });
      
      const data = await response.json();
      
      if (data.success) {
        // Crear registro local
        const newRecord: AttendanceRecord = {
          id: data.record.id,
          employee_name: data.employee.name,
          attendance_type: type,
          timestamp: now.toLocaleString('es-CL'),
          formatted_timestamp: data.record.formatted_timestamp,
          location_lat: coordinates?.lat || 0,
          location_lng: coordinates?.lng || 0,
          address: currentLocation,
          is_offline_sync: false,
          face_confidence: parseFloat(data.confidence?.replace('%', '') || '0') / 100
        };
        
        const updatedHistory = [newRecord, ...attendanceHistory].slice(0, 50);
        setAttendanceHistory(updatedHistory);
        await saveToStorage('attendanceHistory', updatedHistory);
        
        Alert.alert(
          '✅ Asistencia Registrada',
          `${type.toUpperCase()} marcada exitosamente\n\n👤 ${data.employee.name}\n🏢 ${data.employee.department}\n🎯 Confianza: ${data.confidence}\n📍 ${currentLocation}`,
          [{ text: 'Perfecto!' }]
        );
      } else {
        Alert.alert(
          '❌ No Reconocido',
          `${data.message}\n\nConfianza obtenida: ${data.best_confidence || 'N/A'}\nMínimo requerido: ${data.required_confidence || '35%'}`,
          data.suggestions ? [
            { text: 'Reintentar', onPress: () => {
              setPendingAttendanceType(type);
              openCamera('verify');
            }},
            { text: 'Usar Modo Manual', onPress: () => setUseFacialRecognition(false) },
            { text: 'Cancelar', style: 'cancel' }
          ] : [{ text: 'OK' }]
        );
      }
    } catch (error) {
      console.error('Error verificando rostro:', error);
      Alert.alert('Error', 'Error conectando con el servidor');
    } finally {
      setIsProcessingPhoto(false);
    }
  };

  const openCamera = (mode: 'register' | 'verify' | 'new-employee') => {
    if (!hasCameraPermission) {
      Alert.alert('Sin permisos', 'Se requieren permisos de cámara para esta función');
      return;
    }
    
    setCameraMode(mode);
    setShowCamera(true);
  };

  const markAttendanceManual = async (type: 'entrada' | 'salida') => {
    if (!selectedEmployee) {
      Alert.alert('Error', 'Primero selecciona un empleado');
      return;
    }
    
    const now = new Date();
    const timestamp = now.toISOString();
    
    if (!isOnline) {
      // Guardar offline sin foto
      const offlineRecord: OfflineRecord = {
        local_id: `offline_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
        employee_name: selectedEmployee.name,
        employee_id: selectedEmployee.employee_id,
        type: type,
        timestamp: timestamp,
        latitude: coordinates?.lat,
        longitude: coordinates?.lng,
        address: currentLocation,
        notes: 'Registro manual offline'
      };
      
      const updatedOfflineRecords = [...offlineRecords, offlineRecord];
      setOfflineRecords(updatedOfflineRecords);
      await saveToStorage('offlineRecords', updatedOfflineRecords);
      
      Alert.alert(
        '📴 Registro Offline',
        `${type.toUpperCase()} guardada localmente\n\n${selectedEmployee.name}\n\nSe sincronizará cuando vuelva la conexión.`,
        [{ text: 'OK' }]
      );
      return;
    }
    
    // Enviar online
    try {
      const response = await fetch(`${API_BASE_URL}/mark-attendance/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          employee_name: selectedEmployee.name,
          employee_id: selectedEmployee.employee_id,
          type: type,
          timestamp: timestamp,
          latitude: coordinates?.lat,
          longitude: coordinates?.lng,
          address: currentLocation
        })
      });
      
      const data = await response.json();
      
      if (data.success) {
        const newRecord: AttendanceRecord = {
          id: data.record.id,
          employee_name: data.record.employee_name,
          attendance_type: data.record.attendance_type,
          timestamp: now.toLocaleString('es-CL'),
          formatted_timestamp: data.record.formatted_timestamp,
          location_lat: coordinates?.lat || 0,
          location_lng: coordinates?.lng || 0,
          address: currentLocation,
          is_offline_sync: false,
          face_confidence: 0
        };
        
        const updatedHistory = [newRecord, ...attendanceHistory].slice(0, 50);
        setAttendanceHistory(updatedHistory);
        await saveToStorage('attendanceHistory', updatedHistory);
        
        Alert.alert(
          '✅ Registro Exitoso',
          `${type.toUpperCase()} registrada\n\n${selectedEmployee.name}\n${currentLocation}`,
          [{ text: 'OK' }]
        );
      } else {
        Alert.alert('Error', data.message);
      }
    } catch (error) {
      console.error('Error enviando registro:', error);
      Alert.alert('Error', 'Error conectando con el servidor');
    }
  };

  const createEmployee = async () => {
    if (!newEmployeeName.trim()) {
      Alert.alert('Error', 'El nombre es requerido');
      return;
    }
    
    setIsLoading(true);
    
    try {
      const employeeData: any = {
        name: newEmployeeName.trim(),
        department: newEmployeeDepartment.trim() || 'General',
      };
      
      // Incluir foto si se tomó una
      if (newEmployeePhoto) {
        employeeData.photo = newEmployeePhoto;
      }
      
      const response = await fetch(`${API_BASE_URL}/create-employee/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(employeeData)
      });
      
      const data = await response.json();
      
      if (data.success) {
        const newEmployee: Employee = {
          id: data.employee.id,
          name: data.employee.name,
          employee_id: data.employee.employee_id,
          department: data.employee.department,
          position: data.employee.position,
          has_face_registered: data.face_registered || false
        };
        
        setEmployees(prev => [...prev, newEmployee]);
        
        Alert.alert(
          '✅ Empleado Creado',
          `${data.employee.name} creado exitosamente\n\nID: ${data.employee.employee_id}${data.face_registered ? '\n✅ Con rostro registrado' : '\n⚠️ Sin rostro registrado'}`,
          [
            { 
              text: 'Seleccionar', 
              onPress: () => {
                setSelectedEmployee(newEmployee);
                saveToStorage('selectedEmployee', newEmployee);
              }
            },
            { text: 'OK', style: 'cancel' }
          ]
        );
        
        // Limpiar formulario
        setNewEmployeeName('');
        setNewEmployeeDepartment('');
        setNewEmployeePhoto(null);
        setShowNewEmployeeModal(false);
      } else {
        Alert.alert('Error', data.message);
      }
    } catch (error) {
      console.error('Error creando empleado:', error);
      Alert.alert('Error', 'Error creando empleado');
    } finally {
      setIsLoading(false);
    }
  };

  const selectEmployee = async (employee: Employee) => {
    setSelectedEmployee(employee);
    await saveToStorage('selectedEmployee', employee);
    setShowEmployeeModal(false);
    
    if (!employee.has_face_registered && useFacialRecognition) {
      Alert.alert(
        '📸 Registro Facial Pendiente',
        `${employee.name} no tiene rostro registrado.\n\n¿Deseas registrarlo ahora para usar reconocimiento facial?`,
        [
          { text: 'Registrar Ahora', onPress: () => openCamera('register') },
          { text: 'Más Tarde', style: 'cancel' }
        ]
      );
    } else {
      Alert.alert('✅ Empleado Seleccionado', `${employee.name} seleccionado correctamente`);
    }
  };

  const syncOfflineRecords = async () => {
    if (offlineRecords.length === 0 || !isOnline) return;
    
    setIsSyncing(true);
    
    try {
      console.log(`Sincronizando ${offlineRecords.length} registros offline...`);
      
      const response = await fetch(`${API_BASE_URL}/sync-offline/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          offline_records: offlineRecords
        })
      });
      
      const data = await response.json();
      
      if (data.success) {
        // Limpiar registros sincronizados
        setOfflineRecords([]);
        await saveToStorage('offlineRecords', []);
        
        Alert.alert(
          '✅ Sincronización Completa',
          `Se sincronizaron ${data.synced_count} de ${offlineRecords.length} registros.\n\n${data.error_count > 0 ? `${data.error_count} registros con errores.` : 'Todos los registros se sincronizaron correctamente.'}`,
          [{ text: 'OK' }]
        );
        
        // Recargar historial
        await loadEmployees();
      }
    } catch (error) {
      console.error('Error sincronizando:', error);
      Alert.alert('Error', 'Error durante la sincronización');
    } finally {
      setIsSyncing(false);
    }
  };

  const toggleFacialRecognition = async () => {
    const newValue = !useFacialRecognition;
    setUseFacialRecognition(newValue);
    await saveToStorage('useFacialRecognition', newValue);
    
    Alert.alert(
      newValue ? '👤 Reconocimiento Facial' : '📝 Modo Manual',
      newValue 
        ? 'Ahora usarás tu rostro para marcar asistencia.\n\nMás rápido y seguro.'
        : 'Marcarás asistencia seleccionando tu nombre.\n\nÚtil cuando hay problemas con la cámara.'
    );
  };

  const refreshLocation = async () => {
    setCurrentLocation('Actualizando...');
    await setupLocation();
  };

  const testConnection = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/health/`);
      const data = await response.json();
      
      Alert.alert(
        '✅ Conexión OK',
        `Servidor funcionando correctamente\n\nEstado: ${data.status}\nModo: ${data.mode}\nEmpleados: ${data.employees_count}\nRegistros hoy: ${data.attendance_today}`,
        [{ text: 'OK' }]
      );
    } catch (error) {
      Alert.alert(
        '❌ Error de Conexión',
        'No se pudo conectar con el servidor.\n\nVerifica que el servidor Django esté corriendo.',
        [{ text: 'OK' }]
      );
    }
  };

  return (
    <View style={styles.container}>
      <StatusBar style="auto" />
      
      {/* Header */}
      <View style={[styles.header, !isOnline && styles.headerOffline]}>
        <Text style={styles.title}>Sistema de Asistencia</Text>
        <Text style={styles.subtitle}>
          {useFacialRecognition ? '👤 Reconocimiento Facial' : '📝 Modo Manual'} • 
          {isOnline ? ' 🟢 Online' : ' 🔴 Offline'}
          {offlineRecords.length > 0 && ` • ${offlineRecords.length} pendientes`}
        </Text>
      </View>
      
      {/* Toggle Modo */}
      <TouchableOpacity 
        style={styles.toggleButton}
        onPress={toggleFacialRecognition}
      >
        <Text style={styles.toggleText}>
          {useFacialRecognition ? '🔄 Cambiar a Modo Manual' : '🔄 Activar Reconocimiento Facial'}
        </Text>
      </TouchableOpacity>
      
      {/* Empleado seleccionado (solo modo manual) */}
      {!useFacialRecognition && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Empleado Actual</Text>
          {selectedEmployee ? (
            <View style={styles.selectedEmployee}>
              <Text style={styles.employeeName}>{selectedEmployee.name}</Text>
              <Text style={styles.employeeDetails}>
                {selectedEmployee.employee_id} • {selectedEmployee.department}
              </Text>
              {selectedEmployee.has_face_registered && (
                <Text style={styles.faceStatus}>✅ Rostro registrado</Text>
              )}
              <View style={styles.employeeActions}>
                <TouchableOpacity 
                  style={[styles.smallButton, { marginRight: 10 }]}
                  onPress={() => setShowEmployeeModal(true)}
                >
                  <Text style={styles.smallButtonText}>Cambiar</Text>
                </TouchableOpacity>
                {!selectedEmployee.has_face_registered && (
                  <TouchableOpacity 
                    style={[styles.smallButton, styles.registerFaceButton]}
                    onPress={() => openCamera('register')}
                  >
                    <Text style={styles.smallButtonText}>📸 Registrar Rostro</Text>
                  </TouchableOpacity>
                )}
              </View>
            </View>
          ) : (
            <TouchableOpacity 
              style={styles.button}
              onPress={() => setShowEmployeeModal(true)}
            >
              <Text style={styles.buttonText}>Seleccionar Empleado</Text>
            </TouchableOpacity>
          )}
        </View>
      )}
      
      {/* Ubicación */}
      <View style={styles.section}>
        <View style={styles.locationHeader}>
          <Text style={styles.sectionTitle}>📍 Ubicación Actual</Text>
          <TouchableOpacity onPress={refreshLocation}>
            <Text style={styles.refreshButton}>🔄</Text>
          </TouchableOpacity>
        </View>
        <Text style={styles.locationText}>{currentLocation}</Text>
      </View>
      
      {/* Botones principales */}
      <View style={styles.buttonSection}>
        <View style={styles.buttonRow}>
          <TouchableOpacity 
            style={[styles.button, styles.entradaButton]}
            onPress={() => {
              if (useFacialRecognition) {
                setPendingAttendanceType('entrada');
                openCamera('verify');
              } else {
                markAttendanceManual('entrada');
              }
            }}
            disabled={isSyncing || (!useFacialRecognition && !selectedEmployee)}
          >
            <Text style={styles.buttonText}>
              {useFacialRecognition ? '📸 ENTRADA' : 'ENTRADA'}
            </Text>
          </TouchableOpacity>
          
          <TouchableOpacity 
            style={[styles.button, styles.salidaButton]}
            onPress={() => {
              if (useFacialRecognition) {
                setPendingAttendanceType('salida');
                openCamera('verify');
              } else {
                markAttendanceManual('salida');
              }
            }}
            disabled={isSyncing || (!useFacialRecognition && !selectedEmployee)}
          >
            <Text style={styles.buttonText}>
              {useFacialRecognition ? '📸 SALIDA' : 'SALIDA'}
            </Text>
          </TouchableOpacity>
        </View>
        
        {/* Botones secundarios */}
        <View style={styles.secondaryButtons}>
          {offlineRecords.length > 0 && isOnline && !isSyncing && (
            <TouchableOpacity 
              style={[styles.button, styles.syncButton]}
              onPress={syncOfflineRecords}
            >
              <Text style={styles.buttonText}>
                🔄 SINCRONIZAR ({offlineRecords.length})
              </Text>
            </TouchableOpacity>
          )}
          
          <TouchableOpacity 
            style={[styles.smallButton, styles.testButton]}
            onPress={testConnection}
          >
            <Text style={styles.smallButtonText}>🔍 Test Conexión</Text>
          </TouchableOpacity>
        </View>
      </View>
      
      {/* Historial */}
      <View style={styles.historySection}>
        <Text style={styles.historyTitle}>📋 Historial de Asistencia</Text>
        <ScrollView style={styles.historyScroll}>
          {/* Registros offline pendientes */}
          {offlineRecords.map((record) => (
            <View key={record.local_id} style={[styles.historyItem, styles.offlineItem]}>
              <View style={styles.historyContent}>
                <Text style={styles.offlineBadge}>⏳ PENDIENTE</Text>
                <Text style={styles.historyName}>
                  {record.employee_name || 'Por verificar'}
                </Text>
                <Text style={[styles.historyType, 
                  record.type === 'entrada' ? styles.entradaText : styles.salidaText
                ]}>
                  {record.type.toUpperCase()}
                </Text>
                <Text style={styles.historyTime}>
                  {new Date(record.timestamp).toLocaleString('es-CL')}
                </Text>
                {record.photo && <Text style={styles.photoIndicator}>📸 Con foto</Text>}
              </View>
            </View>
          ))}
          
          {/* Registros sincronizados */}
          {attendanceHistory.map((record) => (
            <View key={record.id} style={styles.historyItem}>
              <View style={styles.historyContent}>
                <Text style={styles.historyName}>{record.employee_name}</Text>
                <View style={styles.historyRow}>
                  <Text style={[
                    styles.historyType,
                    record.attendance_type === 'entrada' ? styles.entradaText : styles.salidaText
                  ]}>
                    {record.attendance_type.toUpperCase()}
                  </Text>
                  {record.face_confidence && record.face_confidence > 0 && (
                    <Text style={styles.faceConfidence}>
                      👤 {(record.face_confidence * 100).toFixed(0)}%
                    </Text>
                  )}
                </View>
                <Text style={styles.historyTime}>{record.timestamp}</Text>
                <Text style={styles.locationInfo}>{record.address}</Text>
              </View>
            </View>
          ))}
          
          {attendanceHistory.length === 0 && offlineRecords.length === 0 && (
            <View style={styles.emptyState}>
              <Text style={styles.emptyStateIcon}>📋</Text>
              <Text style={styles.emptyStateText}>
                No hay registros aún
              </Text>
              <Text style={styles.emptyStateSubtext}>
                {useFacialRecognition 
                  ? 'Usa los botones de ENTRADA o SALIDA\npara tomar una foto y marcar asistencia'
                  : 'Selecciona un empleado y usa\nENTRADA o SALIDA para marcar asistencia'}
              </Text>
            </View>
          )}
        </ScrollView>
      </View>
      
      {/* Modal Cámara */}
      <Modal
        animationType="slide"
        transparent={false}
        visible={showCamera}
        onRequestClose={() => setShowCamera(false)}
      >
        <View style={styles.cameraContainer}>
          {hasCameraPermission ? (
            <>
              <CameraView
                ref={cameraRef}
                style={styles.camera}
                facing={facing}
              >
                <View style={styles.cameraOverlay}>
                  {/* Guía visual para centrar rostro */}
                  <View style={styles.faceGuide}>
                    <View style={styles.faceGuideCorner} />
                    <View style={[styles.faceGuideCorner, styles.topRight]} />
                    <View style={[styles.faceGuideCorner, styles.bottomLeft]} />
                    <View style={[styles.faceGuideCorner, styles.bottomRight]} />
                  </View>
                  
                  <Text style={styles.cameraInstructions}>
                    {cameraMode === 'register' 
                      ? '📸 Centra tu rostro en el recuadro\nMira directamente a la cámara'
                      : cameraMode === 'new-employee'
                      ? '📸 Foto para nuevo empleado\nCentra el rostro en el recuadro'
                      : '🔍 Verificando identidad\nMira a la cámara'}
                  </Text>
                </View>
              </CameraView>
              
              <View style={styles.cameraControls}>
                <TouchableOpacity
                  style={styles.flipButton}
                  onPress={() => setFacing(facing === 'back' ? 'front' : 'back')}
                >
                  <Text style={styles.flipText}>🔄</Text>
                </TouchableOpacity>
                
                <TouchableOpacity
                  style={[styles.captureButton, isProcessingPhoto && styles.captureButtonDisabled]}
                  onPress={takePicture}
                  disabled={isProcessingPhoto}
                >
                  {isProcessingPhoto ? (
                    <ActivityIndicator size="large" color="white" />
                  ) : (
                    <View style={styles.captureButtonInner} />
                  )}
                </TouchableOpacity>
                
                <TouchableOpacity
                  style={styles.cancelButton}
                  onPress={() => {
                    setShowCamera(false);
                    setCameraMode(null);
                  }}
                >
                  <Text style={styles.cancelText}>✖</Text>
                </TouchableOpacity>
              </View>
            </>
          ) : (
            <View style={styles.noCameraPermission}>
              <Text style={styles.noCameraIcon}>📷</Text>
              <Text style={styles.noCameraText}>
                No hay permisos de cámara
              </Text>
              <Text style={styles.noCameraSubtext}>
                Ve a configuración y activa los permisos de cámara
              </Text>
              <TouchableOpacity
                style={styles.button}
                onPress={() => setShowCamera(false)}
              >
                <Text style={styles.buttonText}>Cerrar</Text>
              </TouchableOpacity>
            </View>
          )}
        </View>
      </Modal>
      
      {/* Modal Seleccionar Empleado */}
      <Modal
        animationType="slide"
        transparent={true}
        visible={showEmployeeModal}
        onRequestClose={() => setShowEmployeeModal(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>Seleccionar Empleado</Text>
            
            <ScrollView style={styles.employeeList}>
              {employees.length > 0 ? (
                employees.map((employee) => (
                  <TouchableOpacity
                    key={employee.id}
                    style={[
                      styles.employeeItem,
                      selectedEmployee?.id === employee.id && styles.selectedEmployeeItem
                    ]}
                    onPress={() => selectEmployee(employee)}
                  >
                    <View style={styles.employeeItemContent}>
                      <View>
                        <Text style={styles.employeeItemName}>{employee.name}</Text>
                        <Text style={styles.employeeItemDetails}>
                          {employee.employee_id} • {employee.department}
                        </Text>
                      </View>
                      {employee.has_face_registered && (
                        <Text style={styles.faceRegisteredIcon}>👤✓</Text>
                      )}
                    </View>
                  </TouchableOpacity>
                ))
              ) : (
                <Text style={styles.noEmployees}>
                  No hay empleados registrados
                </Text>
              )}
            </ScrollView>
            
            <View style={styles.modalButtons}>
              <TouchableOpacity
                style={[styles.modalButton, styles.createButton]}
                onPress={() => {
                  setShowEmployeeModal(false);
                  setShowNewEmployeeModal(true);
                }}
              >
                <Text style={styles.modalButtonText}>➕ Nuevo Empleado</Text>
              </TouchableOpacity>
              
              <TouchableOpacity
                style={[styles.modalButton, styles.cancelModalButton]}
                onPress={() => setShowEmployeeModal(false)}
              >
                <Text style={styles.modalButtonText}>Cancelar</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
      
      {/* Modal Nuevo Empleado */}
      <Modal
        animationType="slide"
        transparent={true}
        visible={showNewEmployeeModal}
        onRequestClose={() => setShowNewEmployeeModal(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>Crear Nuevo Empleado</Text>
            
            <TextInput
              style={styles.input}
              placeholder="Nombre completo *"
              placeholderTextColor="#999"
              value={newEmployeeName}
              onChangeText={setNewEmployeeName}
            />
            
            <TextInput
              style={styles.input}
              placeholder="Departamento (opcional)"
              placeholderTextColor="#999"
              value={newEmployeeDepartment}
              onChangeText={setNewEmployeeDepartment}
            />
            
            {newEmployeePhoto ? (
              <View style={styles.photoPreview}>
                <Image source={{ uri: newEmployeePhoto }} style={styles.previewImage} />
                <TouchableOpacity
                  style={styles.removePhotoButton}
                  onPress={() => setNewEmployeePhoto(null)}
                >
                  <Text style={styles.removePhotoText}>❌ Quitar foto</Text>
                </TouchableOpacity>
              </View>
            ) : (
              <TouchableOpacity
                style={styles.addPhotoButton}
                onPress={() => {
                  setShowNewEmployeeModal(false);
                  openCamera('new-employee');
                }}
              >
                <Text style={styles.addPhotoText}>📸 Agregar foto (recomendado)</Text>
              </TouchableOpacity>
            )}
            
            <Text style={styles.photoHint}>
              La foto permite usar reconocimiento facial
            </Text>
            
            <View style={styles.modalButtons}>
              <TouchableOpacity
                style={[styles.modalButton, styles.createButton]}
                onPress={createEmployee}
                disabled={isLoading}
              >
                {isLoading ? (
                  <ActivityIndicator color="white" />
                ) : (
                  <Text style={styles.modalButtonText}>Crear Empleado</Text>
                )}
              </TouchableOpacity>
              
              <TouchableOpacity
                style={[styles.modalButton, styles.cancelModalButton]}
                onPress={() => {
                  setShowNewEmployeeModal(false);
                  setNewEmployeeName('');
                  setNewEmployeeDepartment('');
                  setNewEmployeePhoto(null);
                }}
              >
                <Text style={styles.modalButtonText}>Cancelar</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { 
    flex: 1, 
    backgroundColor: '#f0f2f5' 
  },
  
  // Header
  header: { 
    backgroundColor: '#1a73e8', 
    padding: 20, 
    paddingTop: 50, 
    alignItems: 'center',
    elevation: 4,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.2,
    shadowRadius: 4,
  },
  headerOffline: { 
    backgroundColor: '#ea4335' 
  },
  title: { 
    fontSize: 22, 
    fontWeight: 'bold', 
    color: 'white',
    textAlign: 'center'
  },
  subtitle: { 
    fontSize: 14, 
    color: 'rgba(255,255,255,0.9)', 
    marginTop: 5,
    textAlign: 'center'
  },
  
  // Toggle button
  toggleButton: {
    backgroundColor: 'white',
    margin: 15,
    padding: 14,
    borderRadius: 10,
    alignItems: 'center',
    elevation: 2,
    borderWidth: 1,
    borderColor: '#e0e0e0'
  },
  toggleText: {
    color: '#1a73e8',
    fontSize: 15,
    fontWeight: '600'
  },
  
  // Sections
  section: { 
    backgroundColor: 'white', 
    marginHorizontal: 15,
    marginBottom: 10,
    padding: 15, 
    borderRadius: 12, 
    elevation: 2,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 3,
  },
  sectionTitle: {
    fontSize: 15,
    fontWeight: '600',
    color: '#202124',
    marginBottom: 10
  },
  selectedEmployee: {
    alignItems: 'center'
  },
  employeeName: { 
    fontSize: 19, 
    fontWeight: 'bold', 
    color: '#202124',
    marginBottom: 5,
    textAlign: 'center'
  },
  employeeDetails: {
    fontSize: 14,
    color: '#5f6368',
    marginBottom: 5,
    textAlign: 'center'
  },
  faceStatus: {
    fontSize: 13,
    color: '#34a853',
    marginBottom: 10,
    fontWeight: '500'
  },
  employeeActions: {
    flexDirection: 'row',
    justifyContent: 'center',
    marginTop: 10
  },
  
  // Location
  locationHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center'
  },
  locationText: { 
    fontSize: 14, 
    color: '#5f6368', 
    textAlign: 'center',
    lineHeight: 20
  },
  refreshButton: {
    fontSize: 20,
    padding: 5
  },
  
  // Buttons
  buttonSection: { 
    paddingHorizontal: 15, 
    marginBottom: 10
  },
  buttonRow: { 
    flexDirection: 'row', 
    gap: 10,
    marginBottom: 10
  },
  button: { 
    padding: 16, 
    borderRadius: 10, 
    alignItems: 'center',
    elevation: 3,
    backgroundColor: '#1a73e8',
  },
  entradaButton: { 
    backgroundColor: '#34a853', 
    flex: 1 
  },
  salidaButton: { 
    backgroundColor: '#ea4335', 
    flex: 1 
  },
  syncButton: { 
    backgroundColor: '#fbbc04',
    marginBottom: 10
  },
  testButton: {
    backgroundColor: '#5f6368',
  },
  buttonText: { 
    color: 'white', 
    fontSize: 16, 
    fontWeight: 'bold' 
  },
  smallButton: {
    backgroundColor: '#1a73e8',
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 8,
    elevation: 2
  },
  registerFaceButton: {
    backgroundColor: '#34a853'
  },
  smallButtonText: {
    color: 'white',
    fontSize: 13,
    fontWeight: '600'
  },
  secondaryButtons: {
    gap: 10
  },
  
  // History
  historySection: { 
    flex: 1, 
    marginHorizontal: 15, 
    marginBottom: 15,
    backgroundColor: 'white', 
    borderRadius: 12, 
    padding: 15,
    elevation: 2
  },
  historyTitle: { 
    fontSize: 16, 
    fontWeight: '600', 
    color: '#202124', 
    marginBottom: 12 
  },
  historyScroll: { 
    flex: 1 
  },
  historyItem: { 
    padding: 12, 
    borderBottomWidth: 1, 
    borderBottomColor: '#f0f2f5',
    marginBottom: 5,
    borderRadius: 8
  },
  offlineItem: { 
    backgroundColor: '#fef7e0', 
    borderLeftWidth: 4, 
    borderLeftColor: '#fbbc04',
  },
  historyContent: { 
    flex: 1 
  },
  historyName: { 
    fontSize: 15, 
    fontWeight: '600', 
    color: '#202124',
    marginBottom: 3
  },
  historyRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    marginBottom: 3
  },
  historyType: { 
    fontSize: 13, 
    fontWeight: 'bold',
  },
  entradaText: {
    color: '#34a853'
  },
  salidaText: {
    color: '#ea4335'
  },
  faceConfidence: {
    fontSize: 12,
    color: '#1a73e8',
    fontWeight: '600'
  },
  historyTime: { 
    fontSize: 12, 
    color: '#5f6368',
    marginBottom: 2
  },
  locationInfo: {
    fontSize: 11,
    color: '#80868b',
  },
  offlineBadge: { 
    backgroundColor: '#fbbc04', 
    color: 'white', 
    paddingHorizontal: 8,
    paddingVertical: 3, 
    borderRadius: 12, 
    fontSize: 11, 
    fontWeight: 'bold', 
    alignSelf: 'flex-start', 
    marginBottom: 6 
  },
  photoIndicator: {
    fontSize: 11,
    color: '#1a73e8',
    marginTop: 3,
    fontWeight: '500'
  },
  
  // Empty state
  emptyState: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 50
  },
  emptyStateIcon: {
    fontSize: 48,
    marginBottom: 15
  },
  emptyStateText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#202124',
    marginBottom: 8
  },
  emptyStateSubtext: {
    fontSize: 14,
    color: '#5f6368',
    textAlign: 'center',
    lineHeight: 20
  },
  
  // Camera
  cameraContainer: {
    flex: 1,
    backgroundColor: 'black'
  },
  camera: {
    flex: 1
  },
  cameraOverlay: {
    flex: 1,
    backgroundColor: 'transparent',
    justifyContent: 'center',
    alignItems: 'center'
  },
  faceGuide: {
    width: 280,
    height: 280,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 30
  },
  faceGuideCorner: {
    position: 'absolute',
    width: 60,
    height: 60,
    borderColor: 'white',
    borderTopWidth: 3,
    borderLeftWidth: 3,
    top: 0,
    left: 0
  },
  topRight: {
    borderLeftWidth: 0,
    borderRightWidth: 3,
    left: undefined,
    right: 0
  },
  bottomLeft: {
    borderTopWidth: 0,
    borderBottomWidth: 3,
    top: undefined,
    bottom: 0
  },
  bottomRight: {
    borderTopWidth: 0,
    borderLeftWidth: 0,
    borderBottomWidth: 3,
    borderRightWidth: 3,
    top: undefined,
    left: undefined,
    bottom: 0,
    right: 0
  },
  cameraInstructions: {
    color: 'white',
    fontSize: 16,
    textAlign: 'center',
    backgroundColor: 'rgba(0,0,0,0.6)',
    paddingHorizontal: 20,
    paddingVertical: 12,
    borderRadius: 20,
    lineHeight: 22
  },
  cameraControls: {
    position: 'absolute',
    bottom: 40,
    left: 0,
    right: 0,
    flexDirection: 'row',
    justifyContent: 'space-around',
    alignItems: 'center',
    paddingHorizontal: 40
  },
  captureButton: {
    width: 75,
    height: 75,
    borderRadius: 37.5,
    backgroundColor: 'white',
    justifyContent: 'center',
    alignItems: 'center',
    elevation: 5
  },
  captureButtonDisabled: {
    opacity: 0.5
  },
  captureButtonInner: {
    width: 65,
    height: 65,
    borderRadius: 32.5,
    backgroundColor: '#ea4335'
  },
  flipButton: {
    width: 50,
    height: 50,
    borderRadius: 25,
    backgroundColor: 'rgba(255,255,255,0.3)',
    justifyContent: 'center',
    alignItems: 'center'
  },
  flipText: {
    fontSize: 24
  },
  cancelButton: {
    width: 50,
    height: 50,
    borderRadius: 25,
    backgroundColor: 'rgba(255,255,255,0.3)',
    justifyContent: 'center',
    alignItems: 'center'
  },
  cancelText: {
    color: 'white',
    fontSize: 24,
    fontWeight: 'bold'
  },
  noCameraPermission: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 30
  },
  noCameraIcon: {
    fontSize: 64,
    marginBottom: 20
  },
  noCameraText: {
    color: 'white',
    fontSize: 20,
    marginBottom: 10,
    textAlign: 'center',
    fontWeight: '600'
  },
  noCameraSubtext: {
    color: 'rgba(255,255,255,0.8)',
    fontSize: 15,
    textAlign: 'center',
    marginBottom: 30,
    lineHeight: 22
  },
  
  // Modals
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20
  },
  modalContent: {
    backgroundColor: 'white',
    borderRadius: 16,
    padding: 20,
    width: '100%',
    maxHeight: '80%',
    elevation: 5
  },
  modalTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#202124',
    textAlign: 'center',
    marginBottom: 20
  },
  employeeList: {
    maxHeight: 300,
    marginBottom: 15
  },
  employeeItem: {
    padding: 15,
    borderBottomWidth: 1,
    borderBottomColor: '#f0f2f5',
    borderRadius: 10,
    marginBottom: 5
  },
  selectedEmployeeItem: {
    backgroundColor: '#e8f5e8',
    borderLeftWidth: 4,
    borderLeftColor: '#34a853'
  },
  employeeItemContent: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center'
  },
  employeeItemName: {
    fontSize: 16,
    fontWeight: '600',
    color: '#202124',
    marginBottom: 3
  },
  employeeItemDetails: {
    fontSize: 13,
    color: '#5f6368'
  },
  faceRegisteredIcon: {
    fontSize: 22,
    color: '#34a853'
  },
  noEmployees: {
    textAlign: 'center',
    color: '#5f6368',
    fontSize: 15,
    paddingVertical: 30
  },
  modalButtons: {
    flexDirection: 'row',
    gap: 10,
    marginTop: 10
  },
  modalButton: {
    flex: 1,
    padding: 14,
    borderRadius: 10,
    alignItems: 'center',
    elevation: 2
  },
  createButton: {
    backgroundColor: '#34a853'
  },
  cancelModalButton: {
    backgroundColor: '#5f6368'
  },
  modalButtonText: {
    color: 'white',
    fontWeight: '600',
    fontSize: 15
  },
  input: {
    borderWidth: 1,
    borderColor: '#dadce0',
    borderRadius: 10,
    padding: 12,
    marginBottom: 12,
    fontSize: 15,
    color: '#202124'
  },
  photoPreview: {
    alignItems: 'center',
    marginBottom: 15
  },
  previewImage: {
    width: 120,
    height: 120,
    borderRadius: 60,
    marginBottom: 10,
    borderWidth: 3,
    borderColor: '#34a853'
  },
  removePhotoButton: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    backgroundColor: '#ea4335',
    borderRadius: 8
  },
  removePhotoText: {
    color: 'white',
    fontSize: 13,
    fontWeight: '600'
  },
  addPhotoButton: {
    padding: 14,
    backgroundColor: '#1a73e8',
    borderRadius: 10,
    alignItems: 'center',
    marginBottom: 8
  },
  addPhotoText: {
    color: 'white',
    fontSize: 15,
    fontWeight: '600'
  },
  photoHint: {
    fontSize: 12,
    color: '#5f6368',
    textAlign: 'center',
    marginBottom: 15,
    fontStyle: 'italic'
  }
});