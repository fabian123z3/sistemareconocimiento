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
import { PermissionsAndroid } from 'react-native/Libraries/PermissionsAndroid/PermissionsAndroid';

const API_BASE_URL = 'http://192.168.96.36:8000/api';
const VIDEO_REGISTRATION_DURATION = 15;
const VERIFICATION_TIMEOUT = 5;

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
  
  // Camera States
  const [permission, requestPermission] = useCameraPermissions();
  const [showCamera, setShowCamera] = useState(false);
  const [facing, setFacing] = useState<'front' | 'back'>('front');
  const [cameraMode, setCameraMode] = useState<'register' | 'verify' | 'newEmployee' | null>(null);
  const [pendingType, setPendingType] = useState<'entrada' | 'salida'>('entrada');
  const [flashMode, setFlashMode] = useState<'auto' | 'on' | 'off'>('auto');
  const [enableTorch, setEnableTorch] = useState(false);
  const cameraRef = useRef<CameraView>(null);

  // Video Recording States
  const [isRecording, setIsRecording] = useState(false);
  const [recordTimer, setRecordTimer] = useState(VIDEO_REGISTRATION_DURATION);
  const recordIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const [recordingGuide, setRecordingGuide] = useState('');
  
  // Registration States
  const [showEmployeeModal, setShowEmployeeModal] = useState(false);
  const [showNewEmployeeModal, setShowNewEmployeeModal] = useState(false);
  const [newEmployeeName, setNewEmployeeName] = useState('');
  const [creatingEmployee, setCreatingEmployee] = useState(false);

  // Verification States
  const [verificationInProgress, setVerificationInProgress] = useState(false);
  const [timeoutCounter, setTimeoutCounter] = useState(0);

  const videoInstructions = [
    { time: 1, text: 'Gira lentamente la cabeza a la izquierda' },
    { time: 5, text: 'Gira lentamente a la derecha' },
    { time: 9, text: 'Mira al frente y parpadea un par de veces' },
    { time: 13, text: 'Sonríe y luego mantén una expresión neutral' },
    { time: 15, text: '¡Listo! Deteniendo grabación...' },
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

  useEffect(() => {
    if (isRecording) {
      setRecordTimer(VIDEO_REGISTRATION_DURATION);
      setRecordingGuide(videoInstructions[0].text);
      let nextInstructionTime = videoInstructions[0].time;
      let instructionIndex = 0;

      recordIntervalRef.current = setInterval(() => {
        setRecordTimer(prev => {
          const newTime = prev - 1;
          if (newTime >= 0) {
            if (VIDEO_REGISTRATION_DURATION - newTime === nextInstructionTime) {
                instructionIndex++;
                if (instructionIndex < videoInstructions.length) {
                  setRecordingGuide(videoInstructions[instructionIndex].text);
                  nextInstructionTime = videoInstructions[instructionIndex].time;
                }
            }
          }
          if (newTime <= 0) {
            stopRecording();
            return 0;
          }
          return newTime;
        });
      }, 1000);
    } else {
      if (recordIntervalRef.current) {
        clearInterval(recordIntervalRef.current);
        recordIntervalRef.current = null;
      }
    }
    return () => {
      if (recordIntervalRef.current) {
        clearInterval(recordIntervalRef.current);
      }
    };
  }, [isRecording]);

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

  const takePicture = async () => {
    if (!cameraRef.current) return;
    
    let originalBrightness: number | null = null;
    
    try {
      setIsLoading(true);

      const shouldUseScreenFlash = facing === 'front' && (
        flashMode === 'on' || 
        (flashMode === 'auto' && (new Date().getHours() < 8 || new Date().getHours() > 18))
      );

      if (shouldUseScreenFlash) {
          const { status } = await Brightness.requestPermissionsAsync();
          if (status === 'granted') {
              originalBrightness = await Brightness.getBrightnessAsync();
              await Brightness.setBrightnessAsync(1);
              await new Promise(resolve => setTimeout(resolve, 200));
          }
      }

      const photo = await cameraRef.current.takePictureAsync({
        quality: 0.95,
        base64: true,
      });
      
      if (originalBrightness !== null) {
        await Brightness.setBrightnessAsync(originalBrightness);
        originalBrightness = null;
      }

      if (!photo?.base64) {
        throw new Error('No se pudo capturar la foto');
      }
      
      const manipulated = await ImageManipulator.manipulateAsync(
        photo.uri,
        [{ resize: { width: 1200 } }],
        { compress: 0.95, format: ImageManipulator.SaveFormat.JPEG, base64: true }
      );
      
      const photoData = `data:image/jpeg;base64,${manipulated.base64}`;

      setIsLoading(false); 
      setShowCamera(false);
      await verifyFaceWithTimeout(photoData, pendingType);
      
    } catch (error) {
      console.error('Error capturando foto:', error);
      Alert.alert('❌ Error', 'No se pudo capturar la foto. Intenta nuevamente.');
    } finally {
      setIsLoading(false);
      if (originalBrightness !== null) {
        await Brightness.setBrightnessAsync(originalBrightness);
      }
    }
  };

  // Función para solicitar permisos de audio en Android
  const requestAudioPermission = async () => {
    if (Platform.OS === 'android') {
      try {
        const granted = await PermissionsAndroid.request(
          PermissionsAndroid.PERMISSIONS.RECORD_AUDIO,
          {
            title: 'Permiso de Audio',
            message: 'Esta aplicación necesita acceso al micrófono para grabar videos de registro facial',
            buttonNeutral: 'Preguntar después',
            buttonNegative: 'Cancelar',
            buttonPositive: 'OK',
          }
        );
        
        return granted === PermissionsAndroid.RESULTS.GRANTED;
      } catch (err) {
        console.warn(err);
        return false;
      }
    }
    return true; // En iOS se maneja automáticamente por el plugin
  };

  const startVideoRecording = async () => {
    if (!cameraRef.current) return;
    
    // Solicitar permisos de audio antes de grabar
    const hasAudioPermission = await requestAudioPermission();
    if (!hasAudioPermission) {
      Alert.alert(
        'Permiso Requerido',
        'Se necesita acceso al micrófono para grabar video. Ve a Configuración → Aplicaciones → Esta App → Permisos → Micrófono',
        [{ text: 'OK' }]
      );
      setShowCamera(false);
      setCameraMode(null);
      return;
    }
    
    setIsRecording(true);

    try {
      const video = await cameraRef.current.recordAsync({
        maxDuration: VIDEO_REGISTRATION_DURATION,
      });

      if (!video) {
        throw new Error('No se pudo grabar el video');
      }

      console.log('Video recorded:', video.uri);

      if (cameraMode === 'register') {
        await registerFaceWithVideo(video.uri, selectedEmployee);
      } else if (cameraMode === 'newEmployee') {
        await createEmployeeWithVideoDirectly(video.uri, newEmployeeName.trim());
      }
    } catch (error) {
      console.error('Error recording video:', error);
      Alert.alert('❌ Error', 'No se pudo grabar el video. Intenta nuevamente.');
    } finally {
      setIsRecording(false);
      setShowCamera(false);
    }
  };

  const stopRecording = () => {
    if (cameraRef.current && isRecording) {
      cameraRef.current.stopRecording();
      setIsRecording(false);
    }
  };

  const registerFaceWithVideo = async (videoUri: string, employee: Employee | null) => {
    if (!employee) {
      Alert.alert('❌ Error', 'Empleado no seleccionado');
      return;
    }
    setIsLoading(true);
    const formData = new FormData();
    formData.append('employee_id', employee.id);
    formData.append('video', {
      uri: videoUri,
      name: `registration_video_${employee.id}.mp4`,
      type: 'video/mp4',
    } as any);

    try {
      const response = await fetch(`${API_BASE_URL}/register-face-video/`, {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();
      if (data.success) {
        setEmployees(prev => prev.map(emp => 
          emp.id === employee.id 
            ? { ...emp, has_face_registered: true }
            : emp
        ));
        setSelectedEmployee({ ...employee, has_face_registered: true });
        Alert.alert('✅ ¡Registrado!', `Rostro de ${employee.name} registrado con éxito por video`);
      } else {
        Alert.alert('❌ Error', data.message || 'Error registrando rostro por video');
      }
    } catch (error) {
      Alert.alert('❌ Error', 'Error de conexión registrando rostro por video');
    } finally {
      setIsLoading(false);
      setCameraMode(null);
    }
  };

  const createEmployeeWithVideoDirectly = async (videoUri: string, employeeName: string) => {
    setCreatingEmployee(true);
    const formData = new FormData();
    formData.append('name', employeeName);
    formData.append('department', 'General');
    formData.append('video', {
      uri: videoUri,
      name: `new_employee_video.mp4`,
      type: 'video/mp4',
    } as any);

    try {
      const response = await fetch(`${API_BASE_URL}/create-employee-with-video/`, {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();
      if (data.success) {
        await loadEmployees();
        setNewEmployeeName('');
        setShowNewEmployeeModal(false);
        Alert.alert('✅ ¡Creado!', `Empleado ${data.employee.name} creado con reconocimiento facial avanzado por video`);
      } else {
        Alert.alert('❌ Error', data.message || 'Error creando empleado con video');
      }
    } catch (error) {
      Alert.alert('❌ Error', 'Error de conexión creando empleado');
    } finally {
      setCreatingEmployee(false);
      setCameraMode(null);
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
      }, 5000);
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
      '📸 Registro Facial por Video',
      `¿Grabar un video de ${VIDEO_REGISTRATION_DURATION} segundos para registrar el rostro de ${selectedEmployee.name}?\n\nDurante la grabación, sigue las instrucciones en pantalla para un reconocimiento más preciso.`,
      [
        { text: '❌ Cancelar', style: 'cancel' },
        { 
          text: '🎥 Comenzar',
          onPress: () => {
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
    
    Alert.alert(
      '👤 Nuevo Empleado',
      `¿Crear empleado "${newEmployeeName}" con un video de ${VIDEO_REGISTRATION_DURATION} segundos?`,
      [
        { text: '❌ Cancelar', style: 'cancel' },
        { 
          text: '🎥 Crear',
          onPress: () => {
            setCameraMode('newEmployee');
            setShowCamera(true);
          }
        }
      ]
    );
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
            {selectedEmployee ? selectedEmployee.name : 'Seleccionar empleado'}
          </Text>
          {selectedEmployee?.has_face_registered && (
            <Text style={styles.registered}>✅ Reconocimiento facial avanzado activo</Text>
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
          <Text style={styles.sectionTitle}>🔍 Reconocimiento Facial Inteligente</Text>
          <Text style={styles.sectionSubtitle}>
            Detecta rostros con cualquier expresión, lentes, barba o cambios físicos
          </Text>
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
                  `⏱️ ${timeoutCounter}s` : '🔍 SALIDA'}
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
                🎥 Registrar rostro de {selectedEmployee.name} por video
              </Text>
              <Text style={styles.registerSubText}>
                (Sigue las instrucciones en pantalla)
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
              🔄 Sincronizar {offlineRecords.length} registros offline
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
                {record.timestamp}
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
                  setIsRecording(false);
                  setCameraMode(null);
                }}
              >
                <Text style={styles.closeCameraText}>✕</Text>
              </TouchableOpacity>
              
              {renderFlashButton()}

              {(cameraMode === 'verify' || cameraMode === 'register' || cameraMode === 'newEmployee') && (
                <>
                  <View style={styles.faceGuideFrame} />
                  <View style={styles.faceGuideFrameCorners}>
                    <View style={styles.cornerTopLeft} />
                    <View style={styles.cornerTopRight} />
                    <View style={styles.cornerBottomLeft} />
                    <View style={styles.cornerBottomRight} />
                  </View>
                </>
              )}
              
              {(cameraMode === 'register' || cameraMode === 'newEmployee') && (
                <View style={styles.cameraInfo}>
                  <Text style={styles.photoCounter}>
                    {isRecording ? `Grabando... ${recordTimer}s` : `Video de registro`}
                  </Text>
                  <Text style={styles.photoGuide}>
                    {isRecording 
                      ? recordingGuide 
                      : `Graba un video de ${VIDEO_REGISTRATION_DURATION} segundos para registrar tu rostro`}
                  </Text>
                </View>
              )}

              {cameraMode === 'verify' && (
                <View style={styles.cameraInfo}>
                  <Text style={styles.verifyTitle}>
                    🔍 Reconocimiento Inteligente
                  </Text>
                  <Text style={styles.verifySubtitle}>
                    Posiciona tu rostro en el óvalo
                  </Text>
                </View>
              )}
              
              <View style={styles.cameraControls}>
                <TouchableOpacity 
                  style={styles.flipButton}
                  onPress={() => setFacing(facing === 'back' ? 'front' : 'back')}
                >
                  <Text style={styles.controlText}>🔄</Text>
                </TouchableOpacity>
                
                {isRecording ? (
                  <TouchableOpacity
                    style={[styles.captureButton, styles.stopButton]}
                    onPress={stopRecording}
                  >
                    <Text style={styles.captureText}>■</Text>
                  </TouchableOpacity>
                ) : (
                  <TouchableOpacity 
                    style={styles.captureButton} 
                    onPress={cameraMode === 'verify' ? takePicture : startVideoRecording}
                    disabled={isLoading}
                  >
                    <Text style={styles.captureText}>
                      {isLoading ? '⏳' : (cameraMode === 'verify' ? '📸' : '◉')}
                    </Text>
                  </TouchableOpacity>
                )}
                
                <View style={styles.placeholder} />
              </View>
            </View>
          </CameraView>
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
                      {emp.has_face_registered && ' 🔍'}
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
                  {creatingEmployee ? '⏳ Creando...' : '◉ Crear por Video'}
                </Text>
              </TouchableOpacity>
              
              <TouchableOpacity 
                style={[styles.modalButton, styles.modalButtonSecondary]}
                onPress={() => {
                  setShowNewEmployeeModal(false);
                  setNewEmployeeName('');
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
    marginBottom: 8,
    fontWeight: '600',
  },
  sectionSubtitle: {
    fontSize: 12,
    color: '#7f8c8d',
    marginBottom: 15,
    fontStyle: 'italic',
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
  registerSubText: {
    color: '#7f8c8d',
    fontSize: 11,
    marginTop: 3,
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
    zIndex: 99,
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
  flashButton: {
    position: 'absolute',
    top: 50,
    left: 20,
    backgroundColor: 'rgba(0,0,0,0.7)',
    paddingHorizontal: 15,
    paddingVertical: 10,
    borderRadius: 20,
  },
  flashButtonActive: {
    backgroundColor: 'rgba(255,215,0,0.8)',
  },
  flashText: {
    color: '#fff',
    fontSize: 12,
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
    fontSize: 14,
    color: '#fff',
    backgroundColor: 'rgba(0,0,0,0.7)',
    paddingHorizontal: 15,
    paddingVertical: 8,
    borderRadius: 15,
    marginTop: 10,
    textAlign: 'center',
  },
  verifyTitle: {
    fontSize: 20,
    color: '#fff',
    backgroundColor: 'rgba(0,0,0,0.7)',
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 20,
    fontWeight: 'bold',
  },
  verifySubtitle: {
    fontSize: 12,
    color: '#fff',
    backgroundColor: 'rgba(0,0,0,0.7)',
    paddingHorizontal: 15,
    paddingVertical: 8,
    borderRadius: 15,
    marginTop: 10,
    textAlign: 'center',
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
  stopButton: {
    backgroundColor: '#e74c3c',
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
  faceGuideFrame: {
    position: 'absolute',
    top: '20%',
    left: '15%',
    right: '15%',
    height: '60%',
    borderColor: 'rgba(255,255,255,0.3)',
    borderWidth: 3,
    borderRadius: 150,
  },
  faceGuideFrameCorners: {
    position: 'absolute',
    top: '20%',
    left: '15%',
    right: '15%',
    height: '60%',
  },
  cornerTopLeft: {
    position: 'absolute',
    width: 25,
    height: 25,
    borderColor: '#fff',
    borderLeftWidth: 3,
    borderTopWidth: 3,
    borderTopLeftRadius: 10,
  },
  cornerTopRight: {
    position: 'absolute',
    width: 25,
    height: 25,
    borderColor: '#fff',
    borderRightWidth: 3,
    borderTopWidth: 3,
    borderTopRightRadius: 10,
    right: 0,
  },
  cornerBottomLeft: {
    position: 'absolute',
    width: 25,
    height: 25,
    borderColor: '#fff',
    borderLeftWidth: 3,
    borderBottomWidth: 3,
    borderBottomLeftRadius: 10,
    bottom: 0,
  },
  cornerBottomRight: {
    position: 'absolute',
    width: 25,
    height: 25,
    borderColor: '#fff',
    borderRightWidth: 3,
    borderBottomWidth: 3,
    borderBottomRightRadius: 10,
    right: 0,
    bottom: 0,
  },
});