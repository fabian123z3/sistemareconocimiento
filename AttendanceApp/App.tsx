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
  RefreshControl,
  Platform,
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import AsyncStorage from '@react-native-async-storage/async-storage';
import NetInfo from '@react-native-community/netinfo';
import * as Location from 'expo-location';
import { CameraView, useCameraPermissions } from 'expo-camera';
import * as Brightness from 'expo-brightness';
import * as ImageManipulator from 'expo-image-manipulator';
import { BarCodeScanner } from 'expo-barcode-scanner';

const API_BASE_URL = 'http://192.168.96.36:8000/api';
const PHOTOS_FOR_REGISTRATION = 8;
const VERIFICATION_TIMEOUT = 15;

interface Employee {
  id: string;
  name: string;
  employee_id: string;
  rut: string;
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
  
  // Camera States
  const [permission, requestPermission] = useCameraPermissions();
  const [showCamera, setShowCamera] = useState(false);
  const [facing, setFacing] = useState<'front' | 'back'>('front');
  const [cameraMode, setCameraMode] = useState<'register' | 'verify' | 'qr' | null>(null);
  const [pendingType, setPendingType] = useState<'entrada' | 'salida'>('entrada');
  const [flashMode, setFlashMode] = useState<'auto' | 'on' | 'off'>('auto');
  const [enableTorch, setEnableTorch] = useState(false);
  const cameraRef = useRef<CameraView>(null);

  // Photo Registration States
  const [capturedPhotos, setCapturedPhotos] = useState<string[]>([]);
  const [currentPhotoIndex, setCurrentPhotoIndex] = useState(0);
  
  // Registration States
  const [showEmployeeModal, setShowEmployeeModal] = useState(false);
  const [showNewEmployeeModal, setShowNewEmployeeModal] = useState(false);
  const [showFaceRegisterModal, setShowFaceRegisterModal] = useState(false);
  const [newEmployeeName, setNewEmployeeName] = useState('');
  const [newEmployeeRut, setNewEmployeeRut] = useState('');
  const [creatingEmployee, setCreatingEmployee] = useState(false);
  const [pendingEmployee, setPendingEmployee] = useState<Employee | null>(null);

  // Verification States
  const [verificationInProgress, setVerificationInProgress] = useState(false);
  const [timeoutCounter, setTimeoutCounter] = useState(0);
  const [isScanning, setIsScanning] = useState(false);

  // QR Scanner States
  const [showQRScanner, setShowQRScanner] = useState(false);

  const photoInstructions = [
    'Mira al frente con expresión neutral',
    'Sonríe ligeramente',
    'Gira la cabeza ligeramente a la izquierda',
    'Gira la cabeza ligeramente a la derecha',
    'Mira hacia arriba ligeramente',
    'Mira hacia abajo ligeramente',
    'Con lentes (si los usas normalmente)',
    'Sin lentes (si usas lentes, quítatelos)'
  ];

  useEffect(() => {
    initializeApp();
  }, []);

  useEffect(() => {
    if (showCamera && facing === 'back') {
      const shouldUseTorch = flashMode === 'on' || 
                             (flashMode === 'auto' && (new Date().getHours() < 8 || new Date().getHours() > 18));
      setEnableTorch(shouldUseTorch);
    } else {
      setEnableTorch(false);
    }
  }, [flashMode, facing, showCamera]);

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
        // Keep coordinates if geocoding fails
      }
    } catch (error) {
      setCurrentLocation('❌ Error obteniendo ubicación');
    }
  };

  const setupNetworkListener = () => {
    NetInfo.addEventListener(state => {
      const online = state.isConnected && state.isInternetReachable;
      setIsOnline(online || false);
      
      if (online) {
        checkAndSyncOfflineRecords();
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
    await fetchAttendanceRecordsFromServer();
    setRefreshing(false);
  };

  const formatRut = (rut: string): string => {
    const clean = rut.replace(/[^0-9kK]/g, '').toLowerCase();
    
    if (clean.length === 0) return '';
    if (clean.length === 1) return clean;
    
    const body = clean.slice(0, -1);
    const dv = clean.slice(-1);
    
    let formattedBody = '';
    for (let i = 0; i < body.length; i++) {
      if (i > 0 && (body.length - i) % 3 === 0) {
        formattedBody += '.';
      }
      formattedBody += body[i];
    }
    
    return `${formattedBody}-${dv}`;
  };

  const validateRut = (rut: string): boolean => {
  const clean = rut.replace(/[^0-9kK]/g, '').toLowerCase();
  
  if (clean.length < 8 || clean.length > 9) return false;
  
  const body = clean.slice(0, -1);
  const dv = clean.slice(-1);
  
  if (!/^\d+$/.test(body)) return false;
  
  let sum = 0;
  let multiplier = 2;
  
  for (let i = body.length - 1; i >= 0; i--) {
    sum += parseInt(body[i]) * multiplier;
    multiplier = multiplier === 7 ? 2 : multiplier + 1;
  }
  
  const remainder = sum % 11;
  const calculatedDv = remainder === 0 ? '0' : remainder === 1 ? 'k' : (11 - remainder).toString();
  
  return dv === calculatedDv;
};

  const cleanRutForBackend = (rut: string): string => {
    const clean = rut.replace(/[^0-9kK]/g, '').toLowerCase();
    if (clean.length < 2) return clean;
    
    const body = clean.slice(0, -1);
    const dv = clean.slice(-1).toUpperCase();
    
    return `${body}-${dv}`;
  };

  const takePicture = async () => {
    if (!cameraRef.current) return;
    
    let originalBrightness: number | null = null;
    
    try {
      setIsLoading(true);

      const shouldUseScreenFlash = facing === 'front' && (
        flashMode === 'on' || 
        (flashMode === 'auto' && (new Date().getHours() < 8 || new Date().getHours() > 18))
      );
      const shouldUseTorch = facing === 'back' && (
        flashMode === 'on' ||
        (flashMode === 'auto' && (new Date().getHours() < 8 || new Date().getHours() > 18))
      );

      if (shouldUseScreenFlash) {
          const { status } = await Brightness.requestPermissionsAsync();
          if (status === 'granted') {
              originalBrightness = await Brightness.getBrightnessAsync();
              await Brightness.setBrightnessAsync(1);
              await new Promise(resolve => setTimeout(resolve, 400));
          }
      } else if (shouldUseTorch) {
          setEnableTorch(true);
      }

      const photo = await cameraRef.current.takePictureAsync({
        quality: 0.95,
        base64: true,
      });
      
      if (originalBrightness !== null) {
        await Brightness.setBrightnessAsync(originalBrightness);
        originalBrightness = null;
      }
      setEnableTorch(false);

      if (!photo?.base64) {
        throw new Error('No se pudo capturar la foto');
      }
      
      const manipulated = await ImageManipulator.manipulateAsync(
        photo.uri,
        [{ resize: { width: 1200 } }],
        { compress: 0.95, format: ImageManipulator.SaveFormat.JPEG, base64: true }
      );
      
      const photoData = `data:image/jpeg;base64,${manipulated.base64}`;

      if (cameraMode === 'verify') {
        setIsLoading(false); 
        setShowCamera(false);
        await verifyFaceWithTimeout(photoData, pendingType);
      } else if (cameraMode === 'register') {
        const newPhotos = [...capturedPhotos, photoData];
        setCapturedPhotos(newPhotos);
        
        if (newPhotos.length >= PHOTOS_FOR_REGISTRATION) {
          setIsLoading(false);
          setShowCamera(false);
          await registerFaceWithPhotos(newPhotos, pendingEmployee);
        } else {
          setCurrentPhotoIndex(prev => prev + 1);
          setIsLoading(false);
        }
      }
      
    } catch (error) {
      console.error('Error capturando foto:', error);
      Alert.alert('❌ Error', 'No se pudo capturar la foto. Intenta nuevamente.');
    } finally {
      setIsLoading(false);
      if (originalBrightness !== null) {
        await Brightness.setBrightnessAsync(originalBrightness);
      }
      setEnableTorch(false);
    }
  };

  const createEmployeeBasic = async () => {
    if (!newEmployeeName.trim() || !newEmployeeRut.trim()) {
      Alert.alert('❌ Error', 'Ingresa el nombre y RUT del empleado');
      return;
    }

    if (!validateRut(newEmployeeRut)) {
      Alert.alert('❌ Error', 'RUT inválido');
      return;
    }

    setCreatingEmployee(true);

    try {
      const response = await fetch(`${API_BASE_URL}/create-employee-basic/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: newEmployeeName.trim(),
          rut: cleanRutForBackend(newEmployeeRut.trim()),
          department: 'General'
        })
      });

      const data = await response.json();
      
      if (data.success) {
        await loadEmployees();
        setNewEmployeeName('');
        setNewEmployeeRut('');
        setShowNewEmployeeModal(false);
        
        Alert.alert(
          '✅ Empleado Creado', 
          `${data.employee.name} registrado exitosamente.\n\n¿Deseas registrar su rostro ahora?`,
          [
            { text: '⏭️ Después', style: 'cancel' },
            { 
              text: '📸 Registrar Rostro',
              onPress: () => {
                const employee = data.employee;
                setPendingEmployee(employee);
                setShowFaceRegisterModal(true);
              }
            }
          ]
        );
      } else {
        Alert.alert('❌ Error', data.message || 'Error creando empleado');
      }
    } catch (error) {
      Alert.alert('❌ Error', 'Error de conexión creando empleado');
    } finally {
      setCreatingEmployee(false);
    }
  };

  const registerFaceWithPhotos = async (photos: string[], employee: Employee | null) => {
    if (!employee) {
      Alert.alert('❌ Error', 'Empleado no seleccionado');
      return;
    }
    
    setIsLoading(true);
    
    try {
      const response = await fetch(`${API_BASE_URL}/register-face/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          employee_id: employee.id,
          photos: photos
        })
      });

      const data = await response.json();
      if (data.success) {
        setEmployees(prev => prev.map(emp => 
          emp.id === employee.id 
            ? { ...emp, has_face_registered: true }
            : emp
        ));
        
        if (selectedEmployee?.id === employee.id) {
          setSelectedEmployee({ ...employee, has_face_registered: true });
        }
        
        Alert.alert('✅ ¡Registrado!', `Rostro de ${employee.name} registrado con ${data.photos_processed} fotos válidas`);
      } else {
        Alert.alert('❌ Error', data.message || 'Error registrando rostro');
      }
    } catch (error) {
      Alert.alert('❌ Error', 'Error de conexión registrando rostro');
    } finally {
      setIsLoading(false);
      setCameraMode(null);
      setCapturedPhotos([]);
      setCurrentPhotoIndex(0);
      setShowFaceRegisterModal(false);
      setPendingEmployee(null);
    }
  };

  const startFaceRegistration = (employee: Employee) => {
    setPendingEmployee(employee);
    setCameraMode('register');
    setCapturedPhotos([]);
    setCurrentPhotoIndex(0);
    setShowCamera(true);
    setShowFaceRegisterModal(false);
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
      Alert.alert('📱 Offline', `${type.toUpperCase()} guardada para sincronizar`);
      return;
    }
    
    setVerificationInProgress(true);
    setTimeoutCounter(0);
    
    const timeoutInterval = setInterval(() => {
      setTimeoutCounter(prev => prev + 1);
    }, 1000);

    const timeoutPromise = new Promise((_, reject) => {
      setTimeout(() => {
        reject(new Error('TIMEOUT_EXCEEDED'));
      }, VERIFICATION_TIMEOUT * 1000);
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
          timestamp: data.record.timestamp,
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
          'La verificación tardó más de 5 segundos.\n\n💡 Consejos:\n• Mejora la iluminación\n• Acércate más a la cámara\n• Evita sombras en el rostro'
        );
      } else {
        Alert.alert('❌ Error', 'Error de conexión. Intenta nuevamente.');
      }
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
        employee_id: selectedEmployee.employee_id, // CORRECCIÓN: Usamos el employee_id para que el backend lo reconozca
        employee_name: selectedEmployee.name,
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
          employee_id: selectedEmployee.employee_id,
          employee_name: selectedEmployee.name,
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
          timestamp: data.record.timestamp,
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

  const markAttendanceQR = async (type: 'entrada' | 'salida') => {
    setCameraMode('qr');
    setPendingType(type);
    setShowCamera(true);
  };

  const handleQRCodeScanned = async ({ data }: { data: string }) => {
    if (isScanning || !isOnline) {
        return;
    }
    
    setIsScanning(true);
    setIsLoading(true);
    
    try {
      const response = await fetch(`${API_BASE_URL}/verify-qr/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          qr_data: data,
          type: pendingType,
          latitude: coordinates?.lat,
          longitude: coordinates?.lng,
          address: currentLocation
        })
      });
      
      const result = await response.json();
      
      if (result.success) {
        const newRecord: AttendanceRecord = {
          id: result.record.id,
          employee_name: result.employee.name,
          attendance_type: pendingType,
          timestamp: result.record.timestamp,
          location_lat: coordinates?.lat || 0,
          location_lng: coordinates?.lng || 0,
          address: currentLocation,
          is_offline_sync: false,
          face_confidence: 0
        };
        
        const updated = [newRecord, ...attendanceHistory].slice(0, 20);
        setAttendanceHistory(updated);
        await saveToStorage('attendanceHistory', updated);
        
        Alert.alert(
          '✅ ¡Código QR Verificado!', 
          `${pendingType.toUpperCase()} - ${result.employee.name}\n🆔 RUT: ${result.employee.rut}`
        );
      } else {
        Alert.alert('❌ QR No Válido', result.message || 'Código QR no reconocido o RUT no coincide');
      }
    } catch (error) {
      Alert.alert('❌ Error', 'Error verificando código QR');
    } finally {
      setIsLoading(false);
      setShowCamera(false);
      setCameraMode(null);
      setIsScanning(false);
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
    setIsLoading(true);

    try {
      const response = await fetch(`${API_BASE_URL}/sync-offline/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ offline_records: offlineRecords }),
      });

      const data = await response.json();

      if (data.success) {
        // Copia los registros offline antes de borrarlos
        const syncedRecords = [...offlineRecords];

        await saveToStorage('offlineRecords', []);
        setOfflineRecords([]);
        Alert.alert('✅ Sincronizado', `${data.synced_count} registros sincronizados`);
        
        // Mapea los registros sincronizados para que coincidan con la interfaz de `AttendanceRecord`
        const newHistoryItems = syncedRecords.map(record => ({
          id: record.local_id, // Usamos el ID local temporalmente
          employee_name: record.employee_name,
          attendance_type: record.type,
          timestamp: record.timestamp,
          location_lat: record.latitude,
          location_lng: record.longitude,
          address: record.address,
          is_offline_sync: true, 
          face_confidence: record.photo ? 0.75 : 0 // Asigna una confianza si es una foto
        }));

        // Actualiza el historial local de inmediato
        setAttendanceHistory(prev => [...newHistoryItems, ...prev].slice(0, 20));
        
        // Vuelve a cargar los datos del servidor para obtener los IDs correctos y el historial completo
        await loadEmployees();
        await fetchAttendanceRecordsFromServer();

      } else {
        Alert.alert('❌ Sincronización fallida', data.message || `No se pudieron sincronizar todos los registros. Errores: ${data.error_count}`);
      }
    } catch (error) {
      console.error('Error sync:', error);
      Alert.alert('❌ Error de conexión', 'No se pudo conectar al servidor para sincronizar.');
    } finally {
      setIsLoading(false);
    }
  };

  const checkAndSyncOfflineRecords = async () => {
    try {
      const storedOffline = await AsyncStorage.getItem('offlineRecords');
      const recordsToSync = storedOffline ? JSON.parse(storedOffline) : [];

      if (recordsToSync.length > 0) {
        console.log(`🔎 Se encontraron ${recordsToSync.length} registros offline. Intentando sincronizar...`);
        
        const response = await fetch(`${API_BASE_URL}/sync-offline/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ offline_records: recordsToSync }),
        });

        const data = await response.json();

        if (data.success) {
          await saveToStorage('offlineRecords', []);
          setOfflineRecords([]);
          console.log('✅ Sincronización exitosa. Registros locales limpiados.');
          await fetchAttendanceRecordsFromServer();
        } else {
          console.error('❌ Sincronización fallida:', data.message);
        }
      }
    } catch (error) {
      console.error('Error al sincronizar:', error);
    }
  };

  const fetchAttendanceRecordsFromServer = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/attendance-records/?days=7&limit=20`);
      const data = await response.json();

      if (data.success) {
        // Ordenar los registros por fecha de forma descendente
        const sortedRecords = data.records.sort((a: AttendanceRecord, b: AttendanceRecord) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
        setAttendanceHistory(sortedRecords);
        await saveToStorage('attendanceHistory', sortedRecords);
      }
    } catch (error) {
      console.error('Error fetching attendance records:', error);
    }
  };

  const renderFlashButton = () => {
    const flashIcons = {
      'off': '🔦',
      'on': '💡',
      'auto': '⚡'
    };
    
    const flashIsActive = enableTorch;
    const flashStatus = flashMode.toUpperCase();
    
    return (
      <TouchableOpacity
        style={[styles.flashButton, flashIsActive && styles.flashButtonActive]}
        onPress={() => {
          const modes = ['auto', 'on', 'off'] as const;
          const currentIndex = modes.indexOf(flashMode);
          const nextMode = modes[(currentIndex + 1) % modes.length];
          setFlashMode(nextMode);
        }}
      >
        <Text style={styles.flashText}>
          {flashIcons[flashMode]} {flashStatus}
        </Text>
      </TouchableOpacity>
    );
  };

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar style="auto" />
      
      <View style={styles.header}>
        <Text style={styles.title}>📱 Asistencia Pro</Text>
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
        <TouchableOpacity 
          style={styles.card}
          onPress={() => setShowEmployeeModal(true)}
        >
          <Text style={styles.label}>👤 Empleado:</Text>
          <Text style={styles.value}>
            {selectedEmployee ? `${selectedEmployee.name} (${selectedEmployee.rut})` : 'Seleccionar empleado'}
          </Text>
          {selectedEmployee?.has_face_registered && (
            <Text style={styles.registered}>✅ Reconocimiento facial activo</Text>
          )}
          {selectedEmployee && !selectedEmployee.has_face_registered && (
            <TouchableOpacity 
              style={styles.registerFaceButton}
              onPress={() => {
                setPendingEmployee(selectedEmployee);
                setShowFaceRegisterModal(true);
              }}
            >
              <Text style={styles.registerFaceText}>📸 Registrar Rostro</Text>
            </TouchableOpacity>
          )}
        </TouchableOpacity>

        <View style={styles.card}>
          <Text style={styles.label}>📍 Ubicación:</Text>
          <Text style={styles.value}>{currentLocation}</Text>
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>📝 Marcado Manual</Text>
          <View style={styles.buttonRow}>
            <TouchableOpacity 
              style={[styles.button, styles.entrada]}
              onPress={() => markManual('entrada')}
              disabled={!selectedEmployee || isLoading || verificationInProgress}
            >
              <Text style={styles.buttonText}>🟢 ENTRADA</Text>
            </TouchableOpacity>
            
            <TouchableOpacity 
              style={[styles.button, styles.salida]}
              onPress={() => markManual('salida')}
             disabled={!selectedEmployee || isLoading || verificationInProgress}
           >
             <Text style={styles.buttonText}>🔴 SALIDA</Text>
           </TouchableOpacity>
         </View>
       </View>

       <View style={styles.section}>
         <Text style={styles.sectionTitle}>🔍 Reconocimiento Facial</Text>
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
                 `⏱️ ${timeoutCounter}s` : '🔍 ENTRADA'}
             </Text>
           </TouchableOpacity>
           
           <TouchableOpacity 
             style={[styles.button, styles.salida]}
             onPress={() => {
               setPendingType('salida');
               setCameraMode('verify');
               setShowCamera(true);
             }}
             disabled={isLoading || verificationInProgress}
           >
             <Text style={styles.buttonText}>
               {verificationInProgress && pendingType === 'salida' ? 
                 `⏱️ ${timeoutCounter}s` : '🔍 SALIDA'}
             </Text>
           </TouchableOpacity>
         </View>
       </View>

       <View style={styles.section}>
         <Text style={styles.sectionTitle}>🆔 Código QR</Text>
         <View style={styles.buttonRow}>
           <TouchableOpacity 
             style={[styles.button, styles.qr]}
             onPress={() => markAttendanceQR('entrada')}
             disabled={isLoading || verificationInProgress || !isOnline}
           >
             <Text style={styles.buttonText}>📱 QR ENTRADA</Text>
           </TouchableOpacity>
           
           <TouchableOpacity 
             style={[styles.button, styles.qr]}
             onPress={() => markAttendanceQR('salida')}
             disabled={isLoading || verificationInProgress || !isOnline}
           >
             <Text style={styles.buttonText}>📱 QR SALIDA</Text>
           </TouchableOpacity>
         </View>
       </View>

       {offlineRecords.length > 0 && isOnline && (
         <TouchableOpacity 
           style={styles.syncButton} 
           onPress={syncOfflineRecords}
         >
           <Text style={styles.syncText}>
             🔄 Sincronizar {offlineRecords.length} registros
           </Text>
         </TouchableOpacity>
       )}

       <View style={styles.history}>
         <Text style={styles.historyTitle}>📋 Registros Recientes</Text>
         {attendanceHistory.slice(0, 10).map((record, index) => (
           <View key={record.id || index} style={styles.historyItem}>
             <Text style={styles.historyText}>
               {record.employee_name} - {record.attendance_type.toUpperCase()}
             </Text>
             <Text style={styles.historyTime}>
               {new Date(record.timestamp).toLocaleString('es-CL')}
               {record.face_confidence && record.face_confidence > 0 && ` 🔍 ${(record.face_confidence * 100).toFixed(0)}%`}
             </Text>
           </View>
         ))}
         {attendanceHistory.length === 0 && (
           <Text style={styles.emptyText}>Sin registros recientes</Text>
         )}
       </View>
     </ScrollView>

     {isLoading && (
       <View style={styles.loading}>
         <ActivityIndicator size="large" color="#007AFF" />
         <Text style={styles.loadingText}>Procesando...</Text>
       </View>
     )}

     <Modal visible={showCamera} animationType="slide">
       <View style={styles.cameraContainer}>
         {cameraMode === 'qr' ? (
           <BarCodeScanner
             onBarCodeScanned={handleQRCodeScanned}
             style={styles.camera}
           >
             <View style={styles.cameraOverlay}>
               <TouchableOpacity 
                 style={styles.closeCamera} 
                 onPress={() => {
                   setShowCamera(false);
                   setCameraMode(null);
                 }}
               >
                 <Text style={styles.closeCameraText}>✕</Text>
               </TouchableOpacity>
               
               <View style={styles.qrFrame} />
               
               <View style={styles.cameraInfo}>
                 <Text style={styles.qrTitle}>📱 Escanear QR</Text>
               </View>
             </View>
           </BarCodeScanner>
         ) : (
           <CameraView
             ref={cameraRef}
             style={styles.camera}
             facing={facing}
             enableTorch={enableTorch}
           >
             <View style={styles.cameraOverlay}>
               <TouchableOpacity 
                 style={styles.closeCamera} 
                 onPress={() => {
                   setShowCamera(false);
                   setCameraMode(null);
                   setCapturedPhotos([]);
                   setCurrentPhotoIndex(0);
                 }}
               >
                 <Text style={styles.closeCameraText}>✕</Text>
               </TouchableOpacity>
               
               {renderFlashButton()}

               <View style={styles.faceFrame} />
               
               {cameraMode === 'register' && (
                 <View style={styles.cameraInfo}>
                   <Text style={styles.photoCounter}>
                     Foto {currentPhotoIndex + 1} de {PHOTOS_FOR_REGISTRATION}
                   </Text>
                   <Text style={styles.photoGuide}>
                     {photoInstructions[currentPhotoIndex] || 'Posiciona tu rostro'}
                   </Text>
                 </View>
               )}

               {cameraMode === 'verify' && (
                 <View style={styles.cameraInfo}>
                   <Text style={styles.verifyTitle}>🔍 Verificación</Text>
                 </View>
               )}
               
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
                     {isLoading ? '⏳' : '📸'}
                   </Text>
                 </TouchableOpacity>
                 
                 <View style={styles.placeholder} />
               </View>
             </View>
           </CameraView>
         )}
       </View>
     </Modal>

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
                     {emp.has_face_registered && ' 📸'}
                   </Text>
                   <Text style={styles.employeeId}>{emp.employee_id} - {emp.rut}</Text>
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
           />

           <TextInput
             style={styles.input}
             placeholder="RUT (ej: 12345678-9)"
             value={formatRut(newEmployeeRut)}
             onChangeText={(text) => setNewEmployeeRut(text.replace(/[^0-9kK.-]/g, ''))}
             editable={!creatingEmployee}
             maxLength={12}
           />
           
           <View style={styles.modalButtons}>
             <TouchableOpacity 
               style={[styles.modalButton, (!newEmployeeName.trim() || !newEmployeeRut.trim() || !validateRut(newEmployeeRut) || creatingEmployee) && styles.modalButtonDisabled]} 
               onPress={createEmployeeBasic}
               disabled={!newEmployeeName.trim() || !newEmployeeRut.trim() || !validateRut(newEmployeeRut) || creatingEmployee}
             >
               <Text style={styles.buttonText}>
                 {creatingEmployee ? '⏳ Creando...' : '✅ Crear'}
               </Text>
             </TouchableOpacity>
             
             <TouchableOpacity 
               style={[styles.modalButton, styles.modalButtonSecondary]}
               onPress={() => {
                 setShowNewEmployeeModal(false);
                 setNewEmployeeName('');
                 setNewEmployeeRut('');
               }}
               disabled={creatingEmployee}
             >
               <Text style={styles.buttonText}>✕ Cancelar</Text>
             </TouchableOpacity>
           </View>
           
           {newEmployeeRut && !validateRut(newEmployeeRut) && (
             <Text style={styles.errorText}>❌ RUT inválido</Text>
           )}
         </View>
       </View>
     </Modal>

     <Modal visible={showFaceRegisterModal} transparent animationType="fade">
       <View style={styles.modalOverlay}>
         <View style={styles.modal}>
           <Text style={styles.modalTitle}>📸 Registro Facial</Text>
           
           <Text style={styles.modalText}>
             ¿Registrar rostro de {pendingEmployee?.name}?
           </Text>
           <Text style={styles.modalSubText}>
             Se tomarán {PHOTOS_FOR_REGISTRATION} fotos con diferentes expresiones
           </Text>
           
           <View style={styles.modalButtons}>
             <TouchableOpacity 
               style={styles.modalButton}
               onPress={() => startFaceRegistration(pendingEmployee!)}
             >
               <Text style={styles.buttonText}>📸 Comenzar</Text>
             </TouchableOpacity>
             
             <TouchableOpacity 
               style={[styles.modalButton, styles.modalButtonSecondary]}
               onPress={() => {
                 setShowFaceRegisterModal(false);
                 setPendingEmployee(null);
               }}
             >
               <Text style={styles.buttonText}>⏭️ Después</Text>
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
    fontSize: 20,
    fontWeight: 'bold',
    color: '#2c3e50',
  },
  status: {
    fontSize: 12,
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
    borderRadius: 8,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
    elevation: 2,
  },
  label: {
    fontSize: 12,
    color: '#7f8c8d',
    marginBottom: 5,
  },
  value: {
    fontSize: 14,
    color: '#2c3e50',
  },
  registered: {
    fontSize: 10,
    color: '#27ae60',
    marginTop: 5,
  },
  registerFaceButton: {
    marginTop: 10,
    backgroundColor: '#3498db',
    padding: 8,
    borderRadius: 4,
    alignItems: 'center',
  },
  registerFaceText: {
    color: '#fff',
    fontSize: 12,
  },
  section: {
    margin: 15,
  },
  sectionTitle: {
    fontSize: 14,
    color: '#34495e',
    marginBottom: 10,
    fontWeight: '600',
  },
  buttonRow: {
    flexDirection: 'row',
    gap: 10,
  },
  button: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: 6,
    alignItems: 'center',
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
  qr: {
    backgroundColor: '#9b59b6',
  },
  buttonText: {

    color: '#fff',
    fontSize: 12,
    fontWeight: 'bold',
  },
  syncButton: {
    margin: 15,
    backgroundColor: '#f39c12',
    padding: 12,
    borderRadius: 6,
    alignItems: 'center',
  },
  syncText: {
    color: '#fff',
    fontSize: 12,
  },
  history: {
    margin: 15,
    backgroundColor: '#fff',
    padding: 15,
    borderRadius: 8,
  },
  historyTitle: {
    fontSize: 14,
    color: '#34495e',
    marginBottom: 10,
    fontWeight: '600',
  },
  historyItem: {
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#ecf0f1',
  },
  historyText: {
    fontSize: 12,
    color: '#2c3e50',
  },
  historyTime: {
    fontSize: 10,
    color: '#7f8c8d',
    marginTop: 2,
  },
  emptyText: {
    color: '#bdc3c7',
    fontSize: 12,
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
    fontSize: 12,
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
  },
  closeCamera: {
    position: 'absolute',
    top: 50,
    right: 20,
    backgroundColor: 'rgba(0,0,0,0.7)',
    width: 40,
    height: 40,
    borderRadius: 20,
    justifyContent: 'center',
    alignItems: 'center',
  },
  closeCameraText: {
    color: '#fff',
    fontSize: 20,
  },
  flashButton: {
    position: 'absolute',
    top: 50,
    left: 20,
    backgroundColor: 'rgba(0,0,0,0.7)',
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 15,
  },
  flashButtonActive: {
    backgroundColor: 'rgba(255,215,0,0.8)',
  },
  flashText: {
    color: '#fff',
    fontSize: 10,
  },
  cameraInfo: {
    position: 'absolute',
    top: 120,
    left: 0,
    right: 0,
    alignItems: 'center',
  },
  photoCounter: {
    fontSize: 16,
    color: '#fff',
    backgroundColor: 'rgba(0,0,0,0.7)',
    paddingHorizontal: 15,
    paddingVertical: 8,
    borderRadius: 15,
  },
  photoGuide: {
    fontSize: 12,
    color: '#fff',
    backgroundColor: 'rgba(0,0,0,0.7)',
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 10,
    marginTop: 8,
    textAlign: 'center',
  },
  verifyTitle: {
    fontSize: 16,
    color: '#fff',
    backgroundColor: 'rgba(0,0,0,0.7)',
    paddingHorizontal: 15,
    paddingVertical: 8,
    borderRadius: 15,
  },
  qrTitle: {
    fontSize: 16,
    color: '#fff',
    backgroundColor: 'rgba(0,0,0,0.7)',
    paddingHorizontal: 15,
    paddingVertical: 8,
    borderRadius: 15,
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
    width: 50,
    height: 50,
    borderRadius: 25,
    justifyContent: 'center',
    alignItems: 'center',
  },
  captureButton: {
    backgroundColor: '#3498db',
    width: 70,
    height: 70,
    borderRadius: 35,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 3,
    borderColor: '#fff',
  },
  captureText: {
    fontSize: 25,
  },
  controlText: {
    fontSize: 20,
  },
  placeholder: {
    width: 50,
    height: 50,
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
    fontSize: 16,
    fontWeight: 'bold',
    marginBottom: 15,
    textAlign: 'center',
    color: '#2c3e50',
  },
  modalText: {
    fontSize: 14,
    color: '#2c3e50',
    textAlign: 'center',
    marginBottom: 10,
  },
  modalSubText: {
    fontSize: 12,
    color: '#7f8c8d',
    textAlign: 'center',
    marginBottom: 20,
  },
  employeeList: {
    maxHeight: 250,
  },
  employeeItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#ecf0f1',
  },
  employeeInfo: {
    flex: 1,
  },
  employeeName: {
    fontSize: 14,
    fontWeight: '600',
    color: '#2c3e50',
  },
  employeeId: {
    fontSize: 10,
    color: '#7f8c8d',
    marginTop: 2,
  },
  deleteText: {
    fontSize: 16,
    padding: 5,
  },
  input: {
    borderWidth: 1,
    borderColor: '#ddd',
    borderRadius: 6,
    padding: 10,
    fontSize: 14,
    marginBottom: 15,
    backgroundColor: '#f8f9fa',
  },
  modalButtons: {
    flexDirection: 'row',
    gap: 10,
    marginTop: 10,
  },
  modalButton: {
    flex: 1,
    padding: 12,
    backgroundColor: '#3498db',
    borderRadius: 6,
    alignItems: 'center',
  },
  modalButtonSecondary: {
    backgroundColor: '#95a5a6',
  },
  modalButtonDisabled: {
    backgroundColor: '#bdc3c7',
  },
  errorText: {
    color: '#e74c3c',
    fontSize: 10,
    textAlign: 'center',
    marginTop: 5,
  },
  faceFrame: {
    position: 'absolute',
    top: '25%',
    left: '20%',
    right: '20%',
    height: '50%',
    borderColor: '#fff',
    borderWidth: 2,
    borderRadius: 100,
  },
  qrFrame: {
    position: 'absolute',
    top: '30%',
    left: '20%',
    right: '20%',
    height: '40%',
    borderColor: '#fff',
    borderWidth: 2,
    borderRadius: 10,
  },
});