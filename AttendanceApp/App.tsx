import React, { useState, useEffect, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Alert,
  TouchableOpacity,
  Modal,
  ScrollView,
  TextInput,
  ActivityIndicator
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { CameraView, useCameraPermissions } from 'expo-camera';
import AsyncStorage from '@react-native-async-storage/async-storage';

const API_BASE_URL = 'http://192.168.18.124:8000/api';

interface Employee {
  id: string;
  name: string;
  employee_id: string;
}

interface AttendanceRecord {
  id: string;
  employee_name: string;
  attendance_type: string;
  timestamp: string;
  confidence_percentage: string;
}

export default function App() {
  const [currentUser, setCurrentUser] = useState<Employee | null>(null);
  const [attendanceHistory, setAttendanceHistory] = useState<AttendanceRecord[]>([]);
  const [employees, setEmployees] = useState<Employee[]>([]);
  
  const [permission, requestPermission] = useCameraPermissions();
  const [showCamera, setShowCamera] = useState(false);
  const [cameraMode, setCameraMode] = useState<'register' | 'entrada' | 'salida'>('entrada');
  
  const [isProcessing, setIsProcessing] = useState(false);
  const [processingStatus, setProcessingStatus] = useState('');
  const [attemptCount, setAttemptCount] = useState(0);
  
  const [employeeName, setEmployeeName] = useState('');
  const [showRegistrationForm, setShowRegistrationForm] = useState(false);
  const [showEmployeeList, setShowEmployeeList] = useState(false);

  const cameraRef = useRef<CameraView>(null);
  const processTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    loadStoredData();
    loadEmployees();
  }, []);

  useEffect(() => {
    if (showCamera) {
      startUltraFastProcessing();
    } else {
      stopProcessing();
    }
    return () => stopProcessing();
  }, [showCamera]);

  const loadStoredData = async () => {
    try {
      const storedUser = await AsyncStorage.getItem('currentUser');
      const storedHistory = await AsyncStorage.getItem('attendanceHistory');
      
      if (storedUser) setCurrentUser(JSON.parse(storedUser));
      if (storedHistory) setAttendanceHistory(JSON.parse(storedHistory));
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

  const startUltraFastProcessing = () => {
    console.log('⚡ Iniciando procesamiento ultra rápido para cámara mala');
    setIsProcessing(true);
    setAttemptCount(0);
    setProcessingStatus('Preparando cámara mala...');
    
    // Dar tiempo mínimo para estabilizar
    setTimeout(() => {
      setProcessingStatus('⚡ Procesando con cámara básica...');
      processFrame();
    }, 1500);
  };

  const stopProcessing = () => {
    if (processTimeoutRef.current) {
      clearTimeout(processTimeoutRef.current);
      processTimeoutRef.current = null;
    }
    setIsProcessing(false);
    setAttemptCount(0);
  };

  const processFrame = async () => {
    if (!cameraRef.current || !isProcessing) return;

    try {
      setAttemptCount(prev => prev + 1);
      setProcessingStatus(`⚡ Intento ${attemptCount + 1} - Cámara mala`);

      // Captura súper optimizada para cámaras malas
      const photo = await cameraRef.current.takePictureAsync({
        quality: 0.05, // SÚPER baja para cámaras malas
        base64: true,
        skipProcessing: true,
      });

      if (photo?.base64) {
        const base64Image = `data:image/jpeg;base64,${photo.base64}`;
        
        if (cameraMode === 'register') {
          await processUltraFastRegistration(base64Image);
        } else {
          await processUltraFastVerification(base64Image);
        }
      }
    } catch (error) {
      console.warn('Error processing frame:', error);
      setProcessingStatus('❌ Error, reintentando...');
      
      // Reintentar después de error
      processTimeoutRef.current = setTimeout(processFrame, 2000);
    }
  };

  const processUltraFastRegistration = async (base64Image: string) => {
    try {
      const response = await fetch(`${API_BASE_URL}/ultra-fast-register/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: employeeName.trim(),
          image: base64Image,
          ultra_fast: true,
          attempt: attemptCount
        })
      });

      const data = await response.json();

      if (data.success) {
        stopProcessing();
        setProcessingStatus('✅ ¡Registrado exitosamente!');
        
        // Actualizar lista de empleados
        await loadEmployees();
        
        Alert.alert(
          'Registro Completado',
          `${employeeName} registrado con éxito`,
          [{ text: 'OK', onPress: () => {
            setShowCamera(false);
            setShowRegistrationForm(false);
            setEmployeeName('');
          }}]
        );
      } else if (data.processing) {
        setProcessingStatus(`⚡ ${data.message}`);
        // Continuar procesando
        processTimeoutRef.current = setTimeout(processFrame, 1000);
      } else {
        setProcessingStatus('❌ Error registrando');
        processTimeoutRef.current = setTimeout(processFrame, 2000);
      }
    } catch (error) {
      setProcessingStatus('❌ Error conexión');
      processTimeoutRef.current = setTimeout(processFrame, 2000);
    }
  };

  const processUltraFastVerification = async (base64Image: string) => {
    try {
      const response = await fetch(`${API_BASE_URL}/ultra-fast-verify/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          image: base64Image,
          type: cameraMode,
          ultra_fast: true,
          attempt: attemptCount
        })
      });

      const data = await response.json();

      if (data.success) {
        stopProcessing();
        const { employee, attendance } = data;
        
        setProcessingStatus(`✅ ¡${employee.name}!`);
        setCurrentUser(employee);
        saveToStorage('currentUser', employee);

        const newRecord: AttendanceRecord = {
          id: attendance.id,
          employee_name: employee.name,
          attendance_type: attendance.type,
          timestamp: new Date(attendance.timestamp).toLocaleString('es-CL'),
          confidence_percentage: attendance.confidence,
        };

        const updatedHistory = [newRecord, ...attendanceHistory].slice(0, 20);
        setAttendanceHistory(updatedHistory);
        saveToStorage('attendanceHistory', updatedHistory);

        Alert.alert(
          'Reconocido',
          `¡Hola ${employee.name}!\n${attendance.type.toUpperCase()} registrada`,
          [{ text: 'OK', onPress: () => setShowCamera(false) }]
        );
      } else if (data.processing) {
        setProcessingStatus(`⚡ ${data.message}`);
        processTimeoutRef.current = setTimeout(processFrame, 1000);
      } else {
        setProcessingStatus('❌ No reconocido');
        processTimeoutRef.current = setTimeout(processFrame, 2000);
      }
    } catch (error) {
      setProcessingStatus('❌ Error conexión');
      processTimeoutRef.current = setTimeout(processFrame, 2000);
    }
  };

  const startCamera = async (mode: 'entrada' | 'salida') => {
    if (!permission?.granted) {
      const result = await requestPermission();
      if (!result.granted) {
        Alert.alert('Permiso requerido', 'Se necesita acceso a la cámara');
        return;
      }
    }
    setCameraMode(mode);
    setShowCamera(true);
  };

  const startRegistration = () => {
    setShowRegistrationForm(true);
  };

  const proceedWithRegistration = () => {
    if (!employeeName.trim() || employeeName.length < 2) {
      Alert.alert('Error', 'Ingrese un nombre válido');
      return;
    }
    setShowRegistrationForm(false);
    setCameraMode('register');
    setShowCamera(true);
  };

  const deleteEmployee = async (employee: Employee) => {
    try {
      const response = await fetch(`${API_BASE_URL}/delete-employee/${employee.id}/`, {
        method: 'DELETE',
      });

      const data = await response.json();
      if (data.success) {
        await loadEmployees();
        Alert.alert('Eliminado', `${employee.name} eliminado del sistema`);
      } else {
        Alert.alert('Error', data.message || 'Error eliminando empleado');
      }
    } catch (error) {
      Alert.alert('Error', 'Error conectando con servidor');
    }
  };

  const confirmDeleteEmployee = (employee: Employee) => {
    Alert.alert(
      'Eliminar Empleado',
      `¿Eliminar a ${employee.name} del sistema?`,
      [
        { text: 'Cancelar', style: 'cancel' },
        { text: 'Eliminar', style: 'destructive', onPress: () => deleteEmployee(employee) }
      ]
    );
  };

  const deleteAttendanceRecord = async (recordId: string) => {
    try {
      const response = await fetch(`${API_BASE_URL}/delete-attendance/${recordId}/`, {
        method: 'DELETE',
      });

      if (response.ok) {
        const updatedHistory = attendanceHistory.filter(record => record.id !== recordId);
        setAttendanceHistory(updatedHistory);
        saveToStorage('attendanceHistory', updatedHistory);
        Alert.alert('Eliminado', 'Registro eliminado');
      }
    } catch (error) {
      Alert.alert('Error', 'Error eliminando registro');
    }
  };

  return (
    <View style={styles.container}>
      <StatusBar style="auto" />
      
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.title}>⚡ Sistema Ultra Rápido</Text>
        <Text style={styles.subtitle}>Optimizado para Cámaras Malas</Text>
      </View>

      {/* Usuario actual */}
      <View style={styles.userSection}>
        {currentUser ? (
          <Text style={styles.userName}>👤 {currentUser.name}</Text>
        ) : (
          <Text style={styles.noUserText}>⚡ Sistema listo</Text>
        )}
      </View>

      {/* Botones principales */}
      <View style={styles.buttonSection}>
        <View style={styles.buttonRow}>
          <TouchableOpacity
            style={[styles.button, styles.entradaButton]}
            onPress={() => startCamera('entrada')}
          >
            <Text style={styles.buttonText}>⚡ ENTRADA</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.button, styles.salidaButton]}
            onPress={() => startCamera('salida')}
          >
            <Text style={styles.buttonText}>⚡ SALIDA</Text>
          </TouchableOpacity>
        </View>

        <TouchableOpacity
          style={[styles.button, styles.registerButton]}
          onPress={startRegistration}
        >
          <Text style={styles.buttonText}>👤 REGISTRAR EMPLEADO</Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.button, styles.employeeListButton]}
          onPress={() => setShowEmployeeList(true)}
        >
          <Text style={styles.buttonText}>📋 EMPLEADOS ({employees.length})</Text>
        </TouchableOpacity>
      </View>

      {/* Historial */}
      <View style={styles.historySection}>
        <Text style={styles.historyTitle}>📋 Últimos Registros</Text>
        <ScrollView style={styles.historyList}>
          {attendanceHistory.slice(0, 5).map((record) => (
            <View key={record.id} style={styles.historyItem}>
              <View style={styles.historyContent}>
                <Text style={styles.historyName}>{record.employee_name}</Text>
                <Text style={styles.historyDetails}>
                  {record.attendance_type.toUpperCase()} | {record.confidence_percentage}
                </Text>
                <Text style={styles.historyTime}>{record.timestamp}</Text>
              </View>
              <TouchableOpacity
                style={styles.deleteButton}
                onPress={() => deleteAttendanceRecord(record.id)}
              >
                <Text style={styles.deleteButtonText}>🗑</Text>
              </TouchableOpacity>
            </View>
          ))}
        </ScrollView>
      </View>

      {/* Modal de registro */}
      <Modal visible={showRegistrationForm} animationType="slide" transparent>
        <View style={styles.modalOverlay}>
          <View style={styles.formContainer}>
            <Text style={styles.formTitle}>👤 Registro Rápido</Text>
            
            <TextInput
              style={styles.textInput}
              value={employeeName}
              onChangeText={setEmployeeName}
              placeholder="Nombre del empleado"
              autoFocus
            />

            <View style={styles.formButtons}>
              <TouchableOpacity
                style={[styles.button, styles.cancelButton]}
                onPress={() => {
                  setShowRegistrationForm(false);
                  setEmployeeName('');
                }}
              >
                <Text style={styles.buttonText}>Cancelar</Text>
              </TouchableOpacity>
              
              <TouchableOpacity
                style={[styles.button, styles.confirmButton]}
                onPress={proceedWithRegistration}
              >
                <Text style={styles.buttonText}>⚡ Registrar</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      {/* Lista de empleados */}
      <Modal visible={showEmployeeList} animationType="slide">
        <View style={styles.employeeListContainer}>
          <View style={styles.employeeListHeader}>
            <Text style={styles.employeeListTitle}>📋 Empleados Registrados</Text>
            <TouchableOpacity
              onPress={() => setShowEmployeeList(false)}
              style={styles.closeButton}
            >
              <Text style={styles.closeButtonText}>✕</Text>
            </TouchableOpacity>
          </View>

          <ScrollView style={styles.employeeList}>
            {employees.map((employee) => (
              <View key={employee.id} style={styles.employeeItem}>
                <View style={styles.employeeInfo}>
                  <Text style={styles.employeeName}>{employee.name}</Text>
                  <Text style={styles.employeeId}>{employee.employee_id}</Text>
                </View>
                <TouchableOpacity
                  style={styles.deleteEmployeeButton}
                  onPress={() => confirmDeleteEmployee(employee)}
                >
                  <Text style={styles.deleteButtonText}>🗑</Text>
                </TouchableOpacity>
              </View>
            ))}
            {employees.length === 0 && (
              <Text style={styles.noEmployeesText}>No hay empleados registrados</Text>
            )}
          </ScrollView>
        </View>
      </Modal>

      {/* Cámara ultra rápida */}
      <Modal visible={showCamera} animationType="slide">
        <View style={styles.cameraContainer}>
          <View style={styles.cameraHeader}>
            <Text style={styles.cameraTitle}>
              {cameraMode === 'register' ? 
                `⚡ Registrando: ${employeeName}` : 
                `⚡ ${cameraMode.toUpperCase()}`
              }
            </Text>
            <TouchableOpacity
              onPress={() => setShowCamera(false)}
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
            <View style={styles.ultraFastFrame} />
            
            <View style={styles.statusContainer}>
              <Text style={styles.statusText}>{processingStatus}</Text>
              {attemptCount > 0 && (
                <Text style={styles.attemptText}>Intento: {attemptCount}</Text>
              )}
              {isProcessing && (
                <ActivityIndicator color="#e74c3c" size="small" style={styles.spinner} />
              )}
            </View>
            
            <Text style={styles.instructionText}>
              ⚡ Sistema ultra rápido para cámaras básicas{'\n'}
              Mantente frente a la cámara
            </Text>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f5f5f5' },
  header: { backgroundColor: '#2c3e50', padding: 20, paddingTop: 50, alignItems: 'center' },
  title: { fontSize: 24, fontWeight: 'bold', color: '#fff' },
  subtitle: { fontSize: 14, color: '#ecf0f1', marginTop: 5 },
  userSection: { backgroundColor: '#fff', margin: 20, padding: 20, borderRadius: 10, elevation: 3 },
  userName: { fontSize: 20, fontWeight: 'bold', color: '#2c3e50', textAlign: 'center' },
  noUserText: { textAlign: 'center', color: '#7f8c8d', fontStyle: 'italic', fontSize: 16 },
  buttonSection: { padding: 20, gap: 15 },
  buttonRow: { flexDirection: 'row', gap: 15 },
  button: { padding: 15, borderRadius: 10, alignItems: 'center', elevation: 2 },
  entradaButton: { backgroundColor: '#27ae60', flex: 1 },
  salidaButton: { backgroundColor: '#e74c3c', flex: 1 },
  registerButton: { backgroundColor: '#3498db' },
  employeeListButton: { backgroundColor: '#9b59b6' },
  cancelButton: { backgroundColor: '#95a5a6', flex: 1 },
  confirmButton: { backgroundColor: '#27ae60', flex: 1 },
  buttonText: { color: '#fff', fontSize: 16, fontWeight: 'bold' },
  historySection: { flex: 1, margin: 20, backgroundColor: '#fff', borderRadius: 10, padding: 15, elevation: 3 },
  historyTitle: { fontSize: 18, fontWeight: 'bold', color: '#2c3e50', marginBottom: 15 },
  historyList: { flex: 1 },
  historyItem: { flexDirection: 'row', padding: 10, borderBottomWidth: 1, borderBottomColor: '#ecf0f1', alignItems: 'center' },
  historyContent: { flex: 1 },
  historyName: { fontSize: 16, fontWeight: 'bold', color: '#2c3e50' },
  historyDetails: { fontSize: 12, color: '#7f8c8d', marginTop: 2 },
  historyTime: { fontSize: 12, color: '#95a5a6', marginTop: 2 },
  deleteButton: { padding: 8, backgroundColor: '#e74c3c', borderRadius: 15, marginLeft: 10 },
  deleteButtonText: { color: '#fff', fontSize: 14 },
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'center', padding: 20 },
  formContainer: { backgroundColor: '#fff', borderRadius: 15, padding: 25 },
  formTitle: { fontSize: 20, fontWeight: 'bold', textAlign: 'center', marginBottom: 20, color: '#2c3e50' },
  textInput: { borderWidth: 1, borderColor: '#ddd', borderRadius: 8, padding: 15, marginBottom: 15, fontSize: 16 },
  formButtons: { flexDirection: 'row', gap: 15, marginTop: 20 },
  employeeListContainer: { flex: 1, backgroundColor: '#fff' },
  employeeListHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 20, paddingTop: 50, backgroundColor: '#2c3e50' },
  employeeListTitle: { color: '#fff', fontSize: 18, fontWeight: 'bold', flex: 1 },
  closeButton: { padding: 10, backgroundColor: 'rgba(255,255,255,0.2)', borderRadius: 20 },
  closeButtonText: { color: '#fff', fontSize: 18, fontWeight: 'bold' },
  employeeList: { flex: 1, padding: 20 },
  employeeItem: { flexDirection: 'row', padding: 15, backgroundColor: '#f8f9fa', borderRadius: 10, marginBottom: 10, alignItems: 'center' },
  employeeInfo: { flex: 1 },
  employeeName: { fontSize: 16, fontWeight: 'bold', color: '#2c3e50' },
  employeeId: { fontSize: 12, color: '#7f8c8d', marginTop: 2 },
  deleteEmployeeButton: { padding: 10, backgroundColor: '#e74c3c', borderRadius: 15 },
  noEmployeesText: { textAlign: 'center', color: '#7f8c8d', fontStyle: 'italic', marginTop: 50 },
  cameraContainer: { flex: 1, backgroundColor: '#000' },
  cameraHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 20, paddingTop: 50, backgroundColor: 'rgba(0,0,0,0.8)' },
  cameraTitle: { color: '#fff', fontSize: 18, fontWeight: 'bold', flex: 1 },
  camera: { flex: 1 },
  cameraOverlay: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, justifyContent: 'center', alignItems: 'center' },
  ultraFastFrame: { width: 250, height: 300, borderWidth: 3, borderColor: '#e74c3c', borderRadius: 125, backgroundColor: 'transparent' },
  statusContainer: { backgroundColor: 'rgba(0,0,0,0.9)', paddingHorizontal: 20, paddingVertical: 15, borderRadius: 25, marginTop: 30, alignItems: 'center', minWidth: 250 },
  statusText: { color: '#fff', fontSize: 16, fontWeight: 'bold', textAlign: 'center' },
  attemptText: { color: '#e74c3c', fontSize: 12, marginTop: 5 },
  spinner: { marginTop: 10 },
  instructionText: { color: '#fff', fontSize: 14, textAlign: 'center', marginTop: 20, backgroundColor: 'rgba(0,0,0,0.7)', padding: 15, borderRadius: 10, marginHorizontal: 20 },
});