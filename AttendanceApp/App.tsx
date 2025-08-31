import React, { useState, useEffect } from 'react';
import { View, Text, StyleSheet, Alert, TouchableOpacity, Modal, ScrollView, TextInput, Image } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import * as ImagePicker from 'expo-image-picker';
import AsyncStorage from '@react-native-async-storage/async-storage';
import NetInfo from '@react-native-community/netinfo';

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

interface OfflineRecord {
  local_id: string;
  type: string;
  image: string;
  timestamp: string;
  latitude?: number;
  longitude?: number;
  notes?: string;
}

export default function App() {
  const [currentUser, setCurrentUser] = useState<Employee | null>(null);
  const [attendanceHistory, setAttendanceHistory] = useState<AttendanceRecord[]>([]);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [offlineRecords, setOfflineRecords] = useState<OfflineRecord[]>([]);
  
  const [isOnline, setIsOnline] = useState(true);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  
  const [employeeName, setEmployeeName] = useState('');
  const [showRegistrationForm, setShowRegistrationForm] = useState(false);
  const [showEmployeeList, setShowEmployeeList] = useState(false);
  
  const [capturedPhoto, setCapturedPhoto] = useState<string | null>(null);
  const [showPhotoPreview, setShowPhotoPreview] = useState(false);
  const [currentAction, setCurrentAction] = useState<'register' | 'entrada' | 'salida' | null>(null);

  useEffect(() => {
    loadStoredData();
    loadEmployees();
    setupNetworkListener();
  }, []);

  const setupNetworkListener = () => {
    const unsubscribe = NetInfo.addEventListener(state => {
      const wasOffline = !isOnline;
      const nowOnline = state.isConnected && state.isInternetReachable;
      
      setIsOnline(nowOnline || false);
      
      // Si volvimos a estar online, sincronizar automáticamente
      if (wasOffline && nowOnline && offlineRecords.length > 0) {
        setTimeout(() => {
          syncOfflineRecords();
        }, 1000); // Esperar 1 segundo para estabilizar la conexión
      }
    });

    return unsubscribe;
  };

  const loadStoredData = async () => {
    try {
      const storedUser = await AsyncStorage.getItem('currentUser');
      const storedHistory = await AsyncStorage.getItem('attendanceHistory');
      const storedOffline = await AsyncStorage.getItem('offlineRecords');
      
      if (storedUser) setCurrentUser(JSON.parse(storedUser));
      if (storedHistory) setAttendanceHistory(JSON.parse(storedHistory));
      if (storedOffline) setOfflineRecords(JSON.parse(storedOffline));
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

  const takePhoto = async (action: 'register' | 'entrada' | 'salida') => {
    try {
      console.log(`📸 Iniciando captura de foto para: ${action}`);
      
      // Solicitar permisos
      const { status } = await ImagePicker.requestCameraPermissionsAsync();
      if (status !== 'granted') {
        Alert.alert('Error', 'Se necesita permiso para usar la cámara');
        return;
      }

      setCurrentAction(action);
      
      // Tomar foto con alta calidad para 85% de confianza
      const result = await ImagePicker.launchCameraAsync({
        mediaTypes: ImagePicker.MediaTypeOptions.Images,
        allowsEditing: true,
        aspect: [3, 4],
        quality: 0.9, // Alta calidad para mejor reconocimiento
        base64: true,
      });

      console.log('📸 Resultado de la cámara:', result);

      if (!result.canceled && result.assets[0]) {
        const photo = result.assets[0];
        console.log('📸 Foto capturada exitosamente');
        setCapturedPhoto(photo.uri);
        setShowPhotoPreview(true);
      } else {
        console.log('📸 Captura cancelada por el usuario');
        setCurrentAction(null);
      }
    } catch (error) {
      console.error('❌ Error tomando foto:', error);
      Alert.alert('Error', 'Error tomando la foto: ' + error);
      setCurrentAction(null);
    }
  };

  const processPhoto = async () => {
    if (!capturedPhoto || !currentAction) {
      Alert.alert('Error', 'No hay foto o acción seleccionada');
      return;
    }

    console.log(`⚡ Procesando foto para: ${currentAction}`);
    setIsProcessing(true);
    setShowPhotoPreview(false);

    try {
      // Convertir a base64
      let base64Image = '';
      
      if (capturedPhoto.includes('data:image')) {
        base64Image = capturedPhoto;
      } else {
        const response = await fetch(capturedPhoto);
        const blob = await response.blob();
        
        base64Image = await new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result as string);
          reader.onerror = reject;
          reader.readAsDataURL(blob);
        });
      }

      console.log('📸 Base64 preparado, tamaño:', base64Image.length);

      if (currentAction === 'register') {
        await processRegistration(base64Image);
      } else {
        await processVerification(base64Image, currentAction);
      }
    } catch (error) {
      console.error('❌ Error procesando foto:', error);
      Alert.alert('Error', 'Error procesando la foto: ' + error);
    } finally {
      setIsProcessing(false);
      setCapturedPhoto(null);
      setCurrentAction(null);
    }
  };

  const processRegistration = async (base64Image: string) => {
    if (!employeeName.trim()) {
      Alert.alert('Error', 'Falta el nombre del empleado');
      return;
    }

    if (!isOnline) {
      Alert.alert('Sin conexión', 'El registro requiere conexión a internet');
      return;
    }

    try {
      console.log('👤 Enviando registro:', employeeName);
      
      const response = await fetch(`${API_BASE_URL}/register-photo/`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          name: employeeName.trim(),
          image: base64Image
        })
      });

      console.log('👤 Respuesta del servidor:', response.status);
      const data = await response.json();
      console.log('👤 Datos recibidos:', data);

      if (data.success) {
        await loadEmployees();
        
        Alert.alert(
          '✅ Registro Exitoso', 
          `${employeeName} registrado con ID ${data.employee.employee_id}\n\nReconocimiento configurado para 85% de similitud`,
          [{ text: 'OK', onPress: () => {
            setShowRegistrationForm(false);
            setEmployeeName('');
          }}]
        );
      } else {
        Alert.alert('❌ Error en Registro', data.message || 'Error en el registro');
      }
    } catch (error) {
      console.error('❌ Error de conexión:', error);
      Alert.alert('❌ Error', 'Error conectando con el servidor');
    }
  };

  const processVerification = async (base64Image: string, type: string) => {
    console.log(`🔍 Verificando asistencia: ${type}, Online: ${isOnline}`);
    
    if (!isOnline) {
      // MODO OFFLINE - Guardar para sincronizar después
      console.log('📱 Guardando registro offline');
      
      const offlineRecord: OfflineRecord = {
        local_id: `offline_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
        type: type,
        image: base64Image,
        timestamp: new Date().toISOString(),
        notes: 'Registrado offline'
      };

      const updatedOfflineRecords = [...offlineRecords, offlineRecord];
      setOfflineRecords(updatedOfflineRecords);
      await saveToStorage('offlineRecords', updatedOfflineRecords);

      Alert.alert(
        '📱 Registro Offline',
        `${type.toUpperCase()} guardada localmente.\n\nSe sincronizará automáticamente cuando vuelva la conexión.\n\nRequiere 85% de similitud para confirmar identidad.`,
        [{ text: 'OK' }]
      );
      return;
    }

    try {
      console.log('🌐 Enviando verificación online');
      
      const response = await fetch(`${API_BASE_URL}/verify-photo/`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          image: base64Image,
          type: type
        })
      });

      console.log('🔍 Respuesta verificación:', response.status);
      const data = await response.json();
      console.log('🔍 Datos verificación:', data);

      if (data.success) {
        const { employee, attendance } = data;
        
        console.log(`✅ Empleado reconocido: ${employee.name} con ${attendance.confidence}`);
        
        setCurrentUser(employee);
        await saveToStorage('currentUser', employee);

        const newRecord: AttendanceRecord = {
          id: attendance.id,
          employee_name: employee.name,
          attendance_type: attendance.type,
          timestamp: new Date(attendance.timestamp).toLocaleString('es-CL'),
          confidence_percentage: attendance.confidence,
        };

        const updatedHistory = [newRecord, ...attendanceHistory].slice(0, 50);
        setAttendanceHistory(updatedHistory);
        await saveToStorage('attendanceHistory', updatedHistory);

        Alert.alert(
          '✅ Reconocido',
          `¡${employee.name}!\n\n${attendance.type.toUpperCase()} registrada exitosamente\nSimilitud: ${attendance.confidence} (≥85% requerido)`,
          [{ text: 'OK' }]
        );
      } else {
        console.log('❌ No reconocido:', data.message);
        Alert.alert(
          '❌ No Reconocido', 
          data.message || 'No se alcanzó el 85% de similitud requerido.\n\n¿Estás registrado en el sistema?'
        );
      }
    } catch (error) {
      console.error('❌ Error de conexión en verificación:', error);
      Alert.alert('❌ Error', 'Error conectando con el servidor');
    }
  };

  const syncOfflineRecords = async () => {
    if (offlineRecords.length === 0 || !isOnline) return;

    console.log(`🔄 Sincronizando ${offlineRecords.length} registros offline`);
    setIsSyncing(true);
    
    try {
      let successCount = 0;
      const remainingRecords: OfflineRecord[] = [];
      const syncedRecords: AttendanceRecord[] = [];

      for (const record of offlineRecords) {
        try {
          console.log(`🔄 Sincronizando registro: ${record.local_id}`);
          
          const response = await fetch(`${API_BASE_URL}/verify-photo/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              image: record.image,
              type: record.type,
              latitude: record.latitude,
              longitude: record.longitude,
              notes: record.notes,
              is_offline_sync: true,
              offline_timestamp: record.timestamp
            })
          });

          const data = await response.json();
          
          if (data.success) {
            successCount++;
            console.log(`✅ Sincronizado: ${data.employee.name} - ${data.attendance.confidence}`);
            
            const syncedRecord: AttendanceRecord = {
              id: data.attendance.id,
              employee_name: data.employee.name,
              attendance_type: data.attendance.type,
              timestamp: new Date(record.timestamp).toLocaleString('es-CL'),
              confidence_percentage: data.attendance.confidence,
            };

            syncedRecords.push(syncedRecord);
          } else {
            console.log(`❌ Error sincronizando ${record.local_id}: ${data.message}`);
            remainingRecords.push(record);
          }
        } catch (error) {
          console.error(`❌ Error de red sincronizando ${record.local_id}:`, error);
          remainingRecords.push(record);
        }
      }

      // Actualizar historial con registros sincronizados
      if (syncedRecords.length > 0) {
        const updatedHistory = [...syncedRecords, ...attendanceHistory].slice(0, 50);
        setAttendanceHistory(updatedHistory);
        await saveToStorage('attendanceHistory', updatedHistory);
      }

      // Actualizar registros offline pendientes
      setOfflineRecords(remainingRecords);
      await saveToStorage('offlineRecords', remainingRecords);

      if (successCount > 0) {
        Alert.alert(
          '🔄 Sincronización Completa',
          `Se sincronizaron ${successCount} registros offline.\n\nTodos los registros alcanzaron el 85% de similitud requerido.${remainingRecords.length > 0 ? `\n\n${remainingRecords.length} registros no pudieron sincronizarse (similitud <85%)` : ''}`,
          [{ text: 'OK' }]
        );
      } else if (remainingRecords.length > 0) {
        Alert.alert(
          '⚠️ Sincronización Incompleta',
          `${remainingRecords.length} registros no alcanzaron el 85% de similitud requerido.\n\nPodrían ser fotos de personas no registradas o de baja calidad.`,
          [{ text: 'OK' }]
        );
      }
      
      console.log(`✅ Sincronización: ${successCount} exitosos, ${remainingRecords.length} pendientes`);
      
    } catch (error) {
      console.error('❌ Error sincronizando:', error);
      Alert.alert('❌ Error', 'Error durante la sincronización');
    } finally {
      setIsSyncing(false);
    }
  };

  const deleteEmployee = async (employee: Employee) => {
    if (!isOnline) {
      Alert.alert('Sin conexión', 'Esta acción requiere conexión a internet');
      return;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/delete-employee/${employee.id}/`, {
        method: 'DELETE',
      });

      const data = await response.json();
      if (data.success) {
        await loadEmployees();
        if (currentUser?.id === employee.id) {
          setCurrentUser(null);
          await AsyncStorage.removeItem('currentUser');
        }
        Alert.alert('✅ Eliminado', data.message);
      } else {
        Alert.alert('❌ Error', data.message);
      }
    } catch (error) {
      Alert.alert('❌ Error', 'Error conectando con servidor');
    }
  };

  const deleteAttendanceRecord = async (recordId: string) => {
    if (!isOnline) {
      Alert.alert('Sin conexión', 'Esta acción requiere conexión a internet');
      return;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/delete-attendance/${recordId}/`, {
        method: 'DELETE',
      });

      if (response.ok) {
        const updatedHistory = attendanceHistory.filter(record => record.id !== recordId);
        setAttendanceHistory(updatedHistory);
        await saveToStorage('attendanceHistory', updatedHistory);
        Alert.alert('✅ Eliminado', 'Registro eliminado correctamente');
      }
    } catch (error) {
      Alert.alert('❌ Error', 'Error eliminando registro');
    }
  };

  const clearOfflineRecords = async () => {
    Alert.alert(
      '🗑️ Limpiar Registros Offline',
      '¿Estás seguro de eliminar todos los registros offline pendientes?\n\nEsto no se puede deshacer.',
      [
        { text: 'Cancelar', style: 'cancel' },
        { 
          text: 'Eliminar', 
          style: 'destructive', 
          onPress: async () => {
            setOfflineRecords([]);
            await saveToStorage('offlineRecords', []);
            Alert.alert('✅ Limpiado', 'Registros offline eliminados');
          }
        }
      ]
    );
  };

  return (
    <View style={styles.container}>
      <StatusBar style="auto" />
      
      {/* Header con estado de conexión */}
      <View style={[styles.header, !isOnline && styles.headerOffline]}>
        <Text style={styles.title}>📸 Sistema de Asistencia</Text>
        <Text style={styles.subtitle}>
          {isOnline ? '🌐 Conectado' : '📱 Modo Offline'} • Precisión: 85%
          {offlineRecords.length > 0 && ` • ${offlineRecords.length} pendientes`}
          {isSyncing && ' • Sincronizando...'}
        </Text>
      </View>

      {/* Usuario actual */}
      <View style={styles.userSection}>
        {currentUser ? (
          <>
            <Text style={styles.userName}>👤 {currentUser.name}</Text>
            <Text style={styles.userDetails}>ID: {currentUser.employee_id}</Text>
          </>
        ) : (
          <Text style={styles.noUser}>Sin usuario actual</Text>
        )}
      </View>

      {/* Botones principales */}
      <View style={styles.buttonSection}>
        <View style={styles.buttonRow}>
          <TouchableOpacity 
            style={[styles.button, styles.entradaButton]}
            onPress={() => takePhoto('entrada')}
            disabled={isProcessing || isSyncing}
          >
            <Text style={styles.buttonText}>📸 ENTRADA</Text>
            <Text style={styles.buttonSubtext}>Requiere 85% similitud</Text>
            {isProcessing && currentAction === 'entrada' && (
              <Text style={styles.processingText}>Procesando...</Text>
            )}
          </TouchableOpacity>
          
          <TouchableOpacity 
            style={[styles.button, styles.salidaButton]}
            onPress={() => takePhoto('salida')}
            disabled={isProcessing || isSyncing}
          >
            <Text style={styles.buttonText}>📸 SALIDA</Text>
            <Text style={styles.buttonSubtext}>Requiere 85% similitud</Text>
            {isProcessing && currentAction === 'salida' && (
              <Text style={styles.processingText}>Procesando...</Text>
            )}
          </TouchableOpacity>
        </View>
        
        <TouchableOpacity 
          style={[styles.button, styles.registerButton, !isOnline && styles.buttonDisabled]} 
          onPress={() => setShowRegistrationForm(true)}
          disabled={isProcessing || !isOnline || isSyncing}
        >
          <Text style={styles.buttonText}>👤 REGISTRAR EMPLEADO</Text>
          <Text style={styles.buttonSubtext}>
            {!isOnline ? 'Requiere conexión' : 'Sistema de reconocimiento facial'}
          </Text>
        </TouchableOpacity>
        
        <TouchableOpacity 
          style={[styles.button, styles.listButton]} 
          onPress={() => setShowEmployeeList(true)}
          disabled={isSyncing}
        >
          <Text style={styles.buttonText}>📋 EMPLEADOS ({employees.length})</Text>
        </TouchableOpacity>

        {offlineRecords.length > 0 && (
          <View style={styles.offlineSection}>
            {isOnline && !isSyncing && (
              <TouchableOpacity 
                style={[styles.button, styles.syncButton]} 
                onPress={syncOfflineRecords}
              >
                <Text style={styles.buttonText}>🔄 SINCRONIZAR ({offlineRecords.length})</Text>
                <Text style={styles.buttonSubtext}>Verificar con 85% similitud</Text>
              </TouchableOpacity>
            )}
            
            {isSyncing && (
              <View style={[styles.button, styles.syncingButton]}>
                <Text style={styles.buttonText}>⏳ SINCRONIZANDO...</Text>
                <Text style={styles.buttonSubtext}>Verificando identidades...</Text>
              </View>
            )}
            
            <TouchableOpacity 
              style={[styles.button, styles.clearButton]} 
              onPress={clearOfflineRecords}
              disabled={isSyncing}
            >
              <Text style={styles.buttonText}>🗑️ LIMPIAR OFFLINE</Text>
            </TouchableOpacity>
          </View>
        )}
      </View>

      {/* Historial */}
      <View style={styles.historySection}>
        <Text style={styles.historyTitle}>📋 Registros Recientes</Text>
        <ScrollView style={styles.historyScroll}>
          {/* Registros offline pendientes */}
          {offlineRecords.map((record) => (
            <View key={record.local_id} style={[styles.historyItem, styles.offlineItem]}>
              <View style={styles.historyContent}>
                <Text style={styles.offlineBadge}>📱 PENDIENTE SYNC</Text>
                <Text style={styles.historyType}>{record.type.toUpperCase()}</Text>
                <Text style={styles.historyTime}>
                  {new Date(record.timestamp).toLocaleString('es-CL')}
                </Text>
                <Text style={styles.offlineNote}>Requiere verificación de 85% similitud</Text>
              </View>
            </View>
          ))}
          
          {/* Registros sincronizados */}
          {attendanceHistory.slice(0, 10).map((record) => (
            <View key={record.id} style={styles.historyItem}>
              <View style={styles.historyContent}>
                <Text style={styles.historyName}>{record.employee_name}</Text>
                <Text style={styles.historyType}>
                  {record.attendance_type.toUpperCase()} • {record.confidence_percentage}
                </Text>
                <Text style={styles.historyTime}>{record.timestamp}</Text>
                {record.confidence_percentage.includes('Sync offline') && (
                  <Text style={styles.syncBadge}>🔄 Sincronizado</Text>
                )}
              </View>
              {isOnline && !isSyncing && (
                <TouchableOpacity 
                  style={styles.deleteButton}
                  onPress={() => deleteAttendanceRecord(record.id)}
                >
                  <Text style={styles.deleteText}>🗑️</Text>
                </TouchableOpacity>
              )}
            </View>
          ))}
          
          {attendanceHistory.length === 0 && offlineRecords.length === 0 && (
            <Text style={styles.noRecords}>No hay registros aún</Text>
          )}
        </ScrollView>
      </View>

      {/* Modal preview de foto */}
      <Modal visible={showPhotoPreview} transparent animationType="slide">
        <View style={styles.modalOverlay}>
          <View style={styles.photoPreviewContainer}>
            <Text style={styles.modalTitle}>📸 Confirmar Foto</Text>
            
            {capturedPhoto && (
              <Image source={{ uri: capturedPhoto }} style={styles.photoPreview} />
            )}
            
            <Text style={styles.actionText}>
              {currentAction === 'register' ? 
                `Registrar: ${employeeName}` : 
                `Marcar ${currentAction?.toUpperCase()}`
              }
            </Text>
            
            <Text style={styles.confidenceInfo}>
              {currentAction === 'register' ? 
                'Se configurará reconocimiento facial' : 
                'Requiere 85% de similitud para verificar'
              }
            </Text>
            
            {!isOnline && currentAction !== 'register' && (
              <Text style={styles.offlineWarning}>
                📱 Modo Offline - Se sincronizará automáticamente cuando vuelva la conexión
              </Text>
            )}
            
            <View style={styles.photoButtons}>
              <TouchableOpacity 
                style={[styles.button, styles.cancelButton]} 
                onPress={() => {
                  setShowPhotoPreview(false);
                  setCapturedPhoto(null);
                  setCurrentAction(null);
                }}
                disabled={isProcessing}
              >
                <Text style={styles.buttonText}>❌ Cancelar</Text>
              </TouchableOpacity>
              
              <TouchableOpacity 
                style={[styles.button, styles.confirmButton]} 
                onPress={processPhoto}
                disabled={isProcessing}
              >
                <Text style={styles.buttonText}>
                  {isProcessing ? '⏳ Procesando...' : '✅ Confirmar'}
                </Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      {/* Modal de registro */}
      <Modal visible={showRegistrationForm} transparent animationType="slide">
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>👤 Registrar Empleado</Text>
            <Text style={styles.modalDescription}>
              Ingresa el nombre completo del empleado
            </Text>
            <Text style={styles.confidenceInfo}>
              Se configurará reconocimiento facial con 85% de precisión
            </Text>
            
            <TextInput
              style={styles.textInput}
              value={employeeName}
              onChangeText={setEmployeeName}
              placeholder="Nombre completo del empleado"
              autoCapitalize="words"
            />
            
            <View style={styles.modalButtons}>
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
                onPress={() => {
                  if (employeeName.trim().length >= 2) {
                    setShowRegistrationForm(false);
                    takePhoto('register');
                  } else {
                    Alert.alert('Error', 'Ingrese un nombre válido (mínimo 2 caracteres)');
                  }
                }}
              >
                <Text style={styles.buttonText}>📸 Tomar Foto</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      {/* Lista de empleados */}
      <Modal visible={showEmployeeList} animationType="slide">
        <View style={styles.container}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>📋 Empleados Registrados</Text>
            <TouchableOpacity 
              style={styles.closeButton}
              onPress={() => setShowEmployeeList(false)}
            >
              <Text style={styles.closeButtonText}>✕</Text>
            </TouchableOpacity>
          </View>
          
          <ScrollView style={styles.employeeList}>
            {employees.map((employee) => (
              <View key={employee.id} style={styles.employeeItem}>
                <View style={styles.employeeInfo}>
                  <Text style={styles.employeeName}>{employee.name}</Text>
                  <Text style={styles.employeeId}>ID: {employee.employee_id}</Text>
                  <Text style={styles.employeeNote}>Reconocimiento facial configurado</Text>
                </View>
                {isOnline && !isSyncing && (
                  <TouchableOpacity 
                    style={styles.deleteButton}
                    onPress={() => {
                      Alert.alert(
                        'Eliminar Empleado',
                        `¿Estás seguro de eliminar a ${employee.name}?\n\nEsto eliminará su reconocimiento facial.`,
                        [
                          { text: 'Cancelar', style: 'cancel' },
                          { text: 'Eliminar', style: 'destructive', onPress: () => deleteEmployee(employee) }
                        ]
                      );
                    }}
                  >
                    <Text style={styles.deleteText}>🗑️</Text>
                  </TouchableOpacity>
                )}
              </View>
            ))}
            
            {employees.length === 0 && (
              <View style={styles.noDataContainer}>
                <Text style={styles.noDataText}>
                  No hay empleados registrados{'\n\n'}
                  {!isOnline ? 'Requiere conexión para cargar empleados' : 'Usa "REGISTRAR EMPLEADO" para configurar reconocimiento facial'}
                </Text>
              </View>
            )}
          </ScrollView>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f5f5f5' },
  header: { backgroundColor: '#2c3e50', padding: 20, paddingTop: 50, alignItems: 'center' },
  headerOffline: { backgroundColor: '#e67e22' },
  title: { fontSize: 20, fontWeight: 'bold', color: 'white' },
  subtitle: { fontSize: 12, color: 'white', marginTop: 5, textAlign: 'center' },
  
  userSection: { backgroundColor: 'white', margin: 20, padding: 20, borderRadius: 10, alignItems: 'center', elevation: 2 },
  userName: { fontSize: 18, fontWeight: 'bold', color: '#2c3e50' },
  userDetails: { fontSize: 14, color: '#7f8c8d', marginTop: 5 },
  noUser: { fontSize: 16, color: '#95a5a6', fontStyle: 'italic' },
  
  buttonSection: { paddingHorizontal: 20, gap: 15 },
  buttonRow: { flexDirection: 'row', gap: 15 },
  button: { padding: 15, borderRadius: 10, alignItems: 'center', elevation: 2 },
  entradaButton: { backgroundColor: '#27ae60', flex: 1 },
  salidaButton: { backgroundColor: '#e74c3c', flex: 1 },
  registerButton: { backgroundColor: '#3498db' },
  listButton: { backgroundColor: '#9b59b6' },
  syncButton: { backgroundColor: '#f39c12' },
  syncingButton: { backgroundColor: '#95a5a6' },
  clearButton: { backgroundColor: '#e74c3c', marginTop: 10 },
  cancelButton: { backgroundColor: '#95a5a6', flex: 1 },
  confirmButton: { backgroundColor: '#27ae60', flex: 1 },
  buttonDisabled: { backgroundColor: '#bdc3c7' },
  buttonText: { color: 'white', fontSize: 16, fontWeight: 'bold' },
  buttonSubtext: { color: 'white', fontSize: 10, marginTop: 2, opacity: 0.9 },
  processingText: { color: 'white', fontSize: 12, marginTop: 5 },
  offlineText: { color: 'white', fontSize: 12, marginTop: 5, fontStyle: 'italic' },
  
  offlineSection: { marginTop: 10 },
  
  historySection: { flex: 1, margin: 20, backgroundColor: 'white', borderRadius: 10, padding: 15, elevation: 2 },
  historyTitle: { fontSize: 18, fontWeight: 'bold', color: '#2c3e50', marginBottom: 15 },
  historyScroll: { flex: 1 },
  historyItem: { padding: 12, borderBottomWidth: 1, borderBottomColor: '#ecf0f1', flexDirection: 'row', alignItems: 'center' },
  offlineItem: { backgroundColor: '#fff3cd', borderLeftWidth: 4, borderLeftColor: '#f39c12' },
  historyContent: { flex: 1 },
  historyName: { fontSize: 16, fontWeight: 'bold', color: '#2c3e50' },
  historyType: { fontSize: 14, color: '#7f8c8d', marginTop: 2 },
  historyTime: { fontSize: 12, color: '#95a5a6', marginTop: 2 },
  offlineBadge: { backgroundColor: '#f39c12', color: 'white', padding: 4, borderRadius: 4, fontSize: 10, fontWeight: 'bold', alignSelf: 'flex-start', marginBottom: 5 },
  offlineNote: { fontSize: 10, color: '#f39c12', fontStyle: 'italic', marginTop: 2 },
  syncBadge: { backgroundColor: '#3498db', color: 'white', padding: 2, borderRadius: 3, fontSize: 9, fontWeight: 'bold', alignSelf: 'flex-start', marginTop: 3 },
  deleteButton: { padding: 8 },
  deleteText: { fontSize: 18 },
  noRecords: { textAlign: 'center', color: '#7f8c8d', fontStyle: 'italic', marginTop: 50 },
  
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'center', padding: 20 },
  modalContent: { backgroundColor: 'white', padding: 25, borderRadius: 15, elevation: 5 },
  modalHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 20, paddingTop: 50, backgroundColor: '#2c3e50' },
  modalTitle: { fontSize: 20, fontWeight: 'bold', color: '#2c3e50', textAlign: 'center' },
  modalDescription: { fontSize: 14, color: '#7f8c8d', textAlign: 'center', marginVertical: 15 },
  confidenceInfo: { fontSize: 12, color: '#3498db', textAlign: 'center', marginVertical: 10, fontStyle: 'italic' },
  
  textInput: { borderWidth: 1, borderColor: '#ddd', padding: 15, borderRadius: 8, fontSize: 16, marginBottom: 20 },
  modalButtons: { flexDirection: 'row', gap: 15 },
  
  photoPreviewContainer: { backgroundColor: 'white', padding: 25, borderRadius: 15, alignItems: 'center', elevation: 5 },
  photoPreview: { width: 250, height: 300, marginVertical: 20, borderRadius: 10, backgroundColor: '#f5f5f5' },
  actionText: { fontSize: 16, fontWeight: 'bold', color: '#2c3e50', textAlign: 'center', marginBottom: 10 },
  photoButtons: { flexDirection: 'row', gap: 15, marginTop: 20 },
  offlineWarning: { color: '#f39c12', textAlign: 'center', marginVertical: 15, fontWeight: 'bold', fontSize: 14 },
  
  employeeList: { flex: 1, padding: 20 },
  employeeItem: { flexDirection: 'row', padding: 15, backgroundColor: '#f8f9fa', borderRadius: 10, marginBottom: 10, alignItems: 'center', elevation: 1 },
  employeeInfo: { flex: 1 },
  employeeName: { fontSize: 16, fontWeight: 'bold', color: '#2c3e50' },
  employeeId: { fontSize: 14, color: '#7f8c8d', marginTop: 2 },
  employeeNote: { fontSize: 11, color: '#3498db', marginTop: 2, fontStyle: 'italic' },
  
  closeButton: { backgroundColor: 'rgba(255,255,255,0.2)', padding: 12, borderRadius: 25 },
  closeButtonText: { color: 'white', fontSize: 18, fontWeight: 'bold' },
  
  noDataContainer: { flex: 1, justifyContent: 'center', alignItems: 'center', marginTop: 100 },
  noDataText: { textAlign: 'center', color: '#7f8c8d', fontSize: 16, fontStyle: 'italic', lineHeight: 24 },
});