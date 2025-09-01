import React, { useState, useEffect } from 'react';
import { 
  View, 
  Text, 
  StyleSheet, 
  Alert, 
  TouchableOpacity, 
  ScrollView,
  Modal,
  TextInput,
  ActivityIndicator 
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import AsyncStorage from '@react-native-async-storage/async-storage';
import NetInfo from '@react-native-community/netinfo';
import * as Location from 'expo-location';

// CAMBIA POR TU IP LOCAL
const API_BASE_URL = 'http://192.168.96.36:8000/api';

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
  attendance_type: string;
  timestamp: string;
  formatted_timestamp: string;
  location_lat: number;
  location_lng: number;
  address: string;
  is_offline_sync: boolean;
}

interface OfflineRecord {
  local_id: string;
  employee_name: string;
  type: string;
  timestamp: string;
  latitude?: number;
  longitude?: number;
  address: string;
  notes: string;
}

interface PendingEmployee {
  name: string;
  department: string;
  local_id: string;
  created_offline: boolean;
}

export default function App() {
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [selectedEmployee, setSelectedEmployee] = useState<Employee | null>(null);
  const [attendanceHistory, setAttendanceHistory] = useState<AttendanceRecord[]>([]);
  const [offlineRecords, setOfflineRecords] = useState<OfflineRecord[]>([]);
  const [isOnline, setIsOnline] = useState(true);
  const [isSyncing, setIsSyncing] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [currentLocation, setCurrentLocation] = useState<string>('Obteniendo ubicacion...');
  const [coordinates, setCoordinates] = useState<{lat: number, lng: number} | null>(null);
  
  // Estados para modal de empleado
  const [showEmployeeModal, setShowEmployeeModal] = useState(false);
  const [showNewEmployeeModal, setShowNewEmployeeModal] = useState(false);
  const [newEmployeeName, setNewEmployeeName] = useState('');
  const [newEmployeeDepartment, setNewEmployeeDepartment] = useState('');

  useEffect(() => {
    initializeApp();
  }, []);

  const initializeApp = async () => {
    await loadStoredData();
    await setupLocation();
    setupNetworkListener();
    await loadEmployees();
  };

  const setupLocation = async () => {
    try {
      console.log('Solicitando permisos de ubicacion...');
      
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') {
        setCurrentLocation('Sin permisos de ubicacion');
        return;
      }

      console.log('Permisos concedidos, obteniendo ubicacion...');
      
      const location = await Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.High,
      });

      const { latitude, longitude } = location.coords;
      setCoordinates({ lat: latitude, lng: longitude });

      console.log(`Ubicacion obtenida: ${latitude}, ${longitude}`);

      // Obtener direccion legible
      try {
        const addresses = await Location.reverseGeocodeAsync({
          latitude,
          longitude,
        });

        if (addresses.length > 0) {
          const address = addresses[0];
          const fullAddress = `${address.street || ''} ${address.streetNumber || ''}, ${address.city || ''}, ${address.region || ''}`.trim();
          setCurrentLocation(fullAddress || `${latitude.toFixed(6)}, ${longitude.toFixed(6)}`);
          console.log('Direccion obtenida:', fullAddress);
        } else {
          setCurrentLocation(`${latitude.toFixed(6)}, ${longitude.toFixed(6)}`);
        }
      } catch (error) {
        console.log('Error obteniendo direccion, usando coordenadas');
        setCurrentLocation(`${latitude.toFixed(6)}, ${longitude.toFixed(6)}`);
      }

    } catch (error) {
      console.error('Error obteniendo ubicacion:', error);
      setCurrentLocation('Error obteniendo ubicacion');
    }
  };

  const setupNetworkListener = () => {
    NetInfo.addEventListener(state => {
      const wasOffline = !isOnline;
      const nowOnline = state.isConnected && state.isInternetReachable;
      
      setIsOnline(nowOnline || false);
      
      // Auto-sincronizar cuando vuelve la conexion
      if (wasOffline && nowOnline) {
        setTimeout(async () => {
          // Sincronizar empleados offline primero
          await syncOfflineEmployees();
          // Luego sincronizar registros de asistencia
          if (offlineRecords.length > 0) {
            syncOfflineRecords();
          }
          // Recargar empleados del servidor
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

  const createEmployee = async () => {
    if (!newEmployeeName.trim()) {
      Alert.alert('Error', 'El nombre es requerido');
      return;
    }

    setIsLoading(true);
    
    try {
      if (isOnline) {
        // Crear empleado online directamente en el servidor
        console.log(`Creando empleado online: ${newEmployeeName.trim()}`);
        
        const response = await fetch(`${API_BASE_URL}/create-employee/`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            name: newEmployeeName.trim(),
            department: newEmployeeDepartment.trim() || 'General',
          })
        });

        const data = await response.json();
        
        if (data.success) {
          console.log(`Empleado creado en servidor: ${data.employee.name} (${data.employee.employee_id})`);
          
          // Agregar el empleado a la lista local
          const newEmployee: Employee = {
            id: data.employee.id,
            name: data.employee.name,
            employee_id: data.employee.employee_id,
            department: data.employee.department,
            position: data.employee.position
          };
          
          setEmployees(prev => [...prev, newEmployee]);
          
          Alert.alert(
            'Empleado Creado', 
            `${data.employee.name} creado correctamente\nID: ${data.employee.employee_id}\n\nYa puede marcar asistencia inmediatamente.`,
            [
              {
                text: 'Seleccionar Ahora',
                onPress: () => selectEmployee(newEmployee)
              },
              {
                text: 'OK',
                style: 'cancel'
              }
            ]
          );
          
          setNewEmployeeName('');
          setNewEmployeeDepartment('');
          setShowNewEmployeeModal(false);
        } else {
          Alert.alert('Error', data.message);
        }
      } else {
        // Crear empleado offline (se sincronizara cuando haya conexion)
        console.log(`Creando empleado offline: ${newEmployeeName.trim()}`);
        
        const offlineEmployeeId = `OFFLINE_${Date.now()}_${Math.random().toString(36).substr(2, 6).toUpperCase()}`;
        
        const offlineEmployee: Employee = {
          id: offlineEmployeeId,
          name: newEmployeeName.trim(),
          employee_id: offlineEmployeeId,
          department: newEmployeeDepartment.trim() || 'General',
          position: 'Empleado'
        };
        
        // Agregar a lista local
        setEmployees(prev => [...prev, offlineEmployee]);
        
        // Guardar para sincronizacion posterior
        const pendingEmployees = await AsyncStorage.getItem('pendingEmployees');
        const currentPending = pendingEmployees ? JSON.parse(pendingEmployees) : [];
        currentPending.push({
          name: newEmployeeName.trim(),
          department: newEmployeeDepartment.trim() || 'General',
          local_id: offlineEmployeeId,
          created_offline: true
        });
        await AsyncStorage.setItem('pendingEmployees', JSON.stringify(currentPending));
        
        Alert.alert(
          'Empleado Creado Offline',
          `${offlineEmployee.name} creado localmente\n\nSe sincronizara automaticamente cuando vuelva la conexion.`,
          [
            {
              text: 'Seleccionar Ahora',
              onPress: () => selectEmployee(offlineEmployee)
            },
            {
              text: 'OK',
              style: 'cancel'
            }
          ]
        );
        
        setNewEmployeeName('');
        setNewEmployeeDepartment('');
        setShowNewEmployeeModal(false);
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
    Alert.alert('Empleado Seleccionado', `${employee.name} seleccionado para marcar asistencia`);
  };

  const markAttendance = async (type: 'entrada' | 'salida') => {
    if (!selectedEmployee) {
      Alert.alert('Error', 'Primero selecciona un empleado');
      return;
    }

    console.log(`Marcando ${type} para ${selectedEmployee.name}`);
    console.log(`Ubicacion: ${currentLocation}`);
    if (coordinates) {
      console.log(`Coordenadas: ${coordinates.lat}, ${coordinates.lng}`);
    }

    const now = new Date();
    const timestamp = now.toISOString();

    if (!isOnline) {
      // Guardar offline
      console.log('Guardando registro offline');
      
      const offlineRecord: OfflineRecord = {
        local_id: `offline_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
        employee_name: selectedEmployee.name,
        type: type,
        timestamp: timestamp,
        latitude: coordinates?.lat,
        longitude: coordinates?.lng,
        address: currentLocation,
        notes: 'Registro offline'
      };

      const updatedOfflineRecords = [...offlineRecords, offlineRecord];
      setOfflineRecords(updatedOfflineRecords);
      await saveToStorage('offlineRecords', updatedOfflineRecords);

      Alert.alert(
        'Registro Offline',
        `${type.toUpperCase()} guardada localmente\n\n${selectedEmployee.name}\n${currentLocation}\n${now.toLocaleString('es-CL')}\n\nSe sincronizara automaticamente cuando vuelva la conexion.`,
        [{ text: 'OK' }]
      );
      return;
    }

    // Enviar online
    try {
      console.log('Enviando registro online');
      
      const response = await fetch(`${API_BASE_URL}/mark-attendance/`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          employee_name: selectedEmployee.name,
          type: type,
          timestamp: timestamp,
          latitude: coordinates?.lat,
          longitude: coordinates?.lng,
          address: currentLocation
        })
      });

      console.log('Respuesta del servidor:', response.status);
      const data = await response.json();

      if (data.success) {
        console.log('Registro enviado exitosamente');
        
        const newRecord: AttendanceRecord = {
          id: data.record.id,
          employee_name: data.record.employee_name,
          attendance_type: data.record.attendance_type,
          timestamp: now.toLocaleString('es-CL'),
          formatted_timestamp: data.record.formatted_timestamp,
          location_lat: coordinates?.lat || 0,
          location_lng: coordinates?.lng || 0,
          address: currentLocation,
          is_offline_sync: false
        };

        const updatedHistory = [newRecord, ...attendanceHistory].slice(0, 50);
        setAttendanceHistory(updatedHistory);
        await saveToStorage('attendanceHistory', updatedHistory);

        Alert.alert(
          'Registro Exitoso',
          `${type.toUpperCase()} registrada correctamente\n\n${selectedEmployee.name}\n${currentLocation}\n${now.toLocaleString('es-CL')}`,
          [{ text: 'Perfecto!' }]
        );
      } else {
        throw new Error(data.message || 'Error en el servidor');
      }
    } catch (error) {
      console.error('Error enviando registro:', error);
      Alert.alert('Error', 'Error conectando con el servidor');
    }
  };

  const syncOfflineRecords = async () => {
    if (offlineRecords.length === 0 || !isOnline) return;

    console.log(`Sincronizando ${offlineRecords.length} registros offline`);
    setIsSyncing(true);
    
    try {
      // PASO 1: Sincronizar empleados offline primero
      await syncOfflineEmployees();
      
      // PASO 2: Sincronizar registros de asistencia uno por uno
      const successfulRecords: string[] = [];
      const failedRecords: OfflineRecord[] = [];
      
      for (const record of offlineRecords) {
        try {
          console.log(`Sincronizando: ${record.employee_name} - ${record.type}`);
          
          const response = await fetch(`${API_BASE_URL}/mark-attendance/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              employee_name: record.employee_name,
              type: record.type,
              timestamp: record.timestamp,
              latitude: record.latitude,
              longitude: record.longitude,
              address: record.address,
              notes: record.notes + ' (sincronizado offline)',
              is_offline_sync: true,
              offline_timestamp: record.timestamp
            })
          });

          const data = await response.json();
          
          if (data.success) {
            console.log(`Sincronizado: ${record.employee_name} - ${data.record.attendance_type}`);
            successfulRecords.push(record.local_id);
            
            // Agregar al historial local
            const syncedRecord: AttendanceRecord = {
              id: data.record.id,
              employee_name: data.record.employee_name,
              attendance_type: data.record.attendance_type,
              timestamp: new Date(record.timestamp).toLocaleString('es-CL'),
              formatted_timestamp: data.record.formatted_timestamp,
              location_lat: record.latitude || 0,
              location_lng: record.longitude || 0,
              address: record.address,
              is_offline_sync: true
            };
            
            setAttendanceHistory(prev => [syncedRecord, ...prev].slice(0, 50));
          } else {
            console.log(`Error sincronizando ${record.local_id}: ${data.message}`);
            failedRecords.push(record);
          }
        } catch (error) {
          console.error(`Error de red sincronizando ${record.local_id}:`, error);
          failedRecords.push(record);
        }
      }

      // Solo eliminar los registros que se sincronizaron exitosamente
      const remainingRecords = offlineRecords.filter(record => 
        !successfulRecords.includes(record.local_id)
      );
      
      setOfflineRecords(remainingRecords);
      await saveToStorage('offlineRecords', remainingRecords);
      
      // Guardar historial actualizado
      const currentHistory = await AsyncStorage.getItem('attendanceHistory');
      const updatedHistory = currentHistory ? JSON.parse(currentHistory) : [];
      await saveToStorage('attendanceHistory', updatedHistory);

      if (successfulRecords.length > 0) {
        Alert.alert(
          'Sincronizacion Completa',
          `Se sincronizaron ${successfulRecords.length} registros offline.${failedRecords.length > 0 ? `\n\n${failedRecords.length} registros no pudieron sincronizarse y se mantendran para intentar despues.` : ''}`,
          [{ text: 'Excelente!' }]
        );
      } else if (failedRecords.length > 0) {
        Alert.alert(
          'Sincronizacion Parcial',
          `No se pudieron sincronizar ${failedRecords.length} registros. Se mantendran para intentar despues.`,
          [{ text: 'OK' }]
        );
      }
      
      console.log(`Sincronizacion: ${successfulRecords.length} exitosos, ${failedRecords.length} fallidos`);
      
    } catch (error) {
      console.error('Error sincronizando:', error);
      Alert.alert('Error', 'Error durante la sincronizacion');
    } finally {
      setIsSyncing(false);
    }
  };

  const syncOfflineEmployees = async () => {
    try {
      const pendingEmployees = await AsyncStorage.getItem('pendingEmployees');
      if (!pendingEmployees) return;
      
      const employeesToSync = JSON.parse(pendingEmployees);
      console.log(`Sincronizando ${employeesToSync.length} empleados offline`);
      
      const syncedEmployeeIds: string[] = [];
      
      for (const empData of employeesToSync) {
        try {
          const response = await fetch(`${API_BASE_URL}/create-employee/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              name: empData.name,
              department: empData.department || 'General'
            })
          });

          const data = await response.json();
          
          if (data.success) {
            console.log(`Empleado sincronizado: ${data.employee.name} (${data.employee.employee_id})`);
            
            // Actualizar empleado en lista local con datos del servidor
            setEmployees(prev => prev.map(emp => 
              emp.id === empData.local_id ? {
                id: data.employee.id,
                name: data.employee.name,
                employee_id: data.employee.employee_id,
                department: data.employee.department,
                position: data.employee.position
              } : emp
            ));
            
            syncedEmployeeIds.push(empData.local_id);
          }
        } catch (error) {
          console.error(`Error sincronizando empleado ${empData.name}:`, error);
        }
      }
      
      // Limpiar empleados sincronizados exitosamente
      const remainingEmployees = employeesToSync.filter((emp: PendingEmployee) => 
        !syncedEmployeeIds.includes(emp.local_id)
      );
      
      await AsyncStorage.setItem('pendingEmployees', JSON.stringify(remainingEmployees));
      
      if (syncedEmployeeIds.length > 0) {
        console.log(`Sincronizados ${syncedEmployeeIds.length} empleados al servidor`);
      }
      
    } catch (error) {
      console.error('Error sincronizando empleados offline:', error);
    }
  };

  const testConnection = async () => {
    Alert.alert('Probando...', 'Verificando servidor');
    
    try {
      const response = await fetch(`${API_BASE_URL}/health/`);
      const data = await response.json();
      
      Alert.alert(
        'Conexion OK', 
        `Servidor funcionando correctamente\n\nIP: ${API_BASE_URL}\nEstado: ${data.status}`
      );
    } catch (error) {
      Alert.alert('Error de conexion', 'Verifica que el servidor Django este corriendo');
    }
  };

  const clearAllOfflineData = async () => {
    try {
      await AsyncStorage.removeItem('offlineRecords');
      await AsyncStorage.removeItem('pendingEmployees');
      await AsyncStorage.removeItem('attendanceHistory');
      setOfflineRecords([]);
      setAttendanceHistory([]);
      Alert.alert('Limpieza Completa', 'Todos los datos offline fueron eliminados. Ahora puedes empezar limpio.');
      console.log('Datos offline limpiados');
    } catch (error) {
      console.error('Error limpiando datos offline:', error);
    }
  };

  const refreshLocation = async () => {
    setCurrentLocation('Actualizando ubicacion...');
    await setupLocation();
  };

  return (
    <View style={styles.container}>
      <StatusBar style="auto" />
      
      {/* Header */}
      <View style={[styles.header, !isOnline && styles.headerOffline]}>
        <Text style={styles.title}>Sistema de Asistencia GPS</Text>
        <Text style={styles.subtitle}>
          {isOnline ? 'Conectado' : 'Modo Offline'}
          {offlineRecords.length > 0 && ` • ${offlineRecords.length} pendientes`}
          {isSyncing && ' • Sincronizando...'}
        </Text>
      </View>

      {/* Empleado seleccionado */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Empleado Actual</Text>
        {selectedEmployee ? (
          <View style={styles.selectedEmployee}>
            <Text style={styles.employeeName}>{selectedEmployee.name}</Text>
            <Text style={styles.employeeDetails}>
              ID: {selectedEmployee.employee_id} • {selectedEmployee.department}
            </Text>
            <TouchableOpacity 
              style={styles.button}
              onPress={() => setShowEmployeeModal(true)}
            >
              <Text style={styles.buttonText}>Cambiar Empleado</Text>
            </TouchableOpacity>
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

      {/* Ubicacion */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Ubicacion Actual</Text>
        <Text style={styles.locationText}>{currentLocation}</Text>
        {coordinates && (
          <Text style={styles.coordinatesText}>
            {coordinates.lat.toFixed(6)}, {coordinates.lng.toFixed(6)}
          </Text>
        )}
        <TouchableOpacity style={styles.smallButton} onPress={refreshLocation}>
          <Text style={styles.smallButtonText}>Actualizar ubicacion</Text>
        </TouchableOpacity>
      </View>

      {/* Botones principales */}
      <View style={styles.buttonSection}>
        <View style={styles.buttonRow}>
          <TouchableOpacity 
            style={[styles.button, styles.entradaButton]}
            onPress={() => markAttendance('entrada')}
            disabled={isSyncing || !selectedEmployee}
          >
            <Text style={styles.buttonText}>ENTRADA</Text>
          </TouchableOpacity>
          
          <TouchableOpacity 
            style={[styles.button, styles.salidaButton]}
            onPress={() => markAttendance('salida')}
            disabled={isSyncing || !selectedEmployee}
          >
            <Text style={styles.buttonText}>SALIDA</Text>
          </TouchableOpacity>
        </View>
        
        <TouchableOpacity 
          style={[styles.button, styles.testButton]}
          onPress={testConnection}
        >
          <Text style={styles.buttonText}>PROBAR CONEXION</Text>
        </TouchableOpacity>

        {/* Botones de sincronizacion y limpieza */}
        {offlineRecords.length > 0 && isOnline && !isSyncing && (
          <TouchableOpacity 
            style={[styles.button, styles.syncButton]}
            onPress={syncOfflineRecords}
          >
            <Text style={styles.buttonText}>SINCRONIZAR ({offlineRecords.length})</Text>
          </TouchableOpacity>
        )}

        <TouchableOpacity 
          style={[styles.button, styles.clearButton]}
          onPress={clearAllOfflineData}
        >
          <Text style={styles.buttonText}>LIMPIAR DATOS OFFLINE</Text>
        </TouchableOpacity>

        {isSyncing && (
          <View style={[styles.button, styles.syncingButton]}>
            <Text style={styles.buttonText}>SINCRONIZANDO...</Text>
          </View>
        )}
      </View>

      {/* Historial */}
      <View style={styles.historySection}>
        <Text style={styles.historyTitle}>Historial de Asistencia</Text>
        <ScrollView style={styles.historyScroll}>
          {/* Registros offline pendientes */}
          {offlineRecords.map((record) => (
            <View key={record.local_id} style={[styles.historyItem, styles.offlineItem]}>
              <View style={styles.historyContent}>
                <Text style={styles.offlineBadge}>PENDIENTE SYNC</Text>
                <Text style={styles.historyName}>{record.employee_name}</Text>
                <Text style={styles.historyType}>{record.type.toUpperCase()}</Text>
                <Text style={styles.historyTime}>
                  {new Date(record.timestamp).toLocaleString('es-CL')}
                </Text>
                <Text style={styles.locationInfo}>{record.address}</Text>
              </View>
            </View>
          ))}
          
          {/* Registros sincronizados */}
          {attendanceHistory.map((record) => (
            <View key={record.id} style={styles.historyItem}>
              <View style={styles.historyContent}>
                <Text style={styles.historyName}>{record.employee_name}</Text>
                <Text style={styles.historyType}>{record.attendance_type.toUpperCase()}</Text>
                <Text style={styles.historyTime}>{record.timestamp}</Text>
                <Text style={styles.locationInfo}>{record.address}</Text>
                <Text style={styles.syncBadge}>
                  {record.is_offline_sync ? 'Sincronizado' : 'En Linea'}
                </Text>
              </View>
            </View>
          ))}
          
          {attendanceHistory.length === 0 && offlineRecords.length === 0 && (
            <Text style={styles.noRecords}>
              No hay registros aun{'\n\n'}
              Selecciona un empleado y usa los botones ENTRADA o SALIDA para comenzar
            </Text>
          )}
        </ScrollView>
      </View>

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
              {employees.map((employee) => (
                <TouchableOpacity
                  key={employee.id}
                  style={[
                    styles.employeeItem,
                    selectedEmployee?.id === employee.id && styles.selectedEmployeeItem
                  ]}
                  onPress={() => selectEmployee(employee)}
                >
                  <Text style={styles.employeeItemName}>{employee.name}</Text>
                  <Text style={styles.employeeItemDetails}>
                    {employee.employee_id} • {employee.department}
                  </Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
            
            <View style={styles.modalButtons}>
              <TouchableOpacity
                style={[styles.modalButton, styles.createButton]}
                onPress={() => {
                  setShowEmployeeModal(false);
                  setShowNewEmployeeModal(true);
                }}
              >
                <Text style={styles.modalButtonText}>Nuevo Empleado</Text>
              </TouchableOpacity>
              
              <TouchableOpacity
                style={[styles.modalButton, styles.cancelButton]}
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
              value={newEmployeeName}
              onChangeText={setNewEmployeeName}
            />
            
            <TextInput
              style={styles.input}
              placeholder="Departamento (opcional)"
              value={newEmployeeDepartment}
              onChangeText={setNewEmployeeDepartment}
            />
            
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
                style={[styles.modalButton, styles.cancelButton]}
                onPress={() => {
                  setShowNewEmployeeModal(false);
                  setNewEmployeeName('');
                  setNewEmployeeDepartment('');
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
    backgroundColor: '#f5f5f5' 
  },
  
  header: { 
    backgroundColor: '#2c3e50', 
    padding: 20, 
    paddingTop: 50, 
    alignItems: 'center',
  },
  headerOffline: { 
    backgroundColor: '#e67e22' 
  },
  title: { 
    fontSize: 18, 
    fontWeight: 'bold', 
    color: 'white',
    textAlign: 'center'
  },
  subtitle: { 
    fontSize: 12, 
    color: 'white', 
    marginTop: 5,
    textAlign: 'center'
  },
  
  section: { 
    backgroundColor: 'white', 
    margin: 15, 
    padding: 15, 
    borderRadius: 8, 
    elevation: 2
  },
  sectionTitle: {
    fontSize: 14,
    fontWeight: 'bold',
    color: '#2c3e50',
    marginBottom: 10
  },
  selectedEmployee: {
    alignItems: 'center'
  },
  employeeName: { 
    fontSize: 16, 
    fontWeight: 'bold', 
    color: '#2c3e50',
    marginBottom: 5
  },
  employeeDetails: {
    fontSize: 12,
    color: '#7f8c8d',
    marginBottom: 10
  },
  locationText: { 
    fontSize: 12, 
    color: '#7f8c8d', 
    textAlign: 'center',
    marginBottom: 5
  },
  coordinatesText: {
    fontSize: 10,
    color: '#95a5a6',
    textAlign: 'center',
    marginBottom: 10
  },
  
  buttonSection: { 
    paddingHorizontal: 15, 
    gap: 10 
  },
  buttonRow: { 
    flexDirection: 'row', 
    gap: 10 
  },
  button: { 
    padding: 12, 
    borderRadius: 8, 
    alignItems: 'center',
    elevation: 2,
    backgroundColor: '#3498db',
  },
  entradaButton: { 
    backgroundColor: '#27ae60', 
    flex: 1 
  },
  salidaButton: { 
    backgroundColor: '#e74c3c', 
    flex: 1 
  },
  testButton: { 
    backgroundColor: '#17a2b8' 
  },
  syncButton: { 
    backgroundColor: '#f39c12' 
  },
  clearButton: { 
    backgroundColor: '#e67e22' 
  },
  syncingButton: { 
    backgroundColor: '#95a5a6' 
  },
  buttonText: { 
    color: 'white', 
    fontSize: 14, 
    fontWeight: 'bold' 
  },
  smallButton: {
    backgroundColor: '#3498db',
    padding: 8,
    borderRadius: 6,
    alignSelf: 'center'
  },
  smallButtonText: {
    color: 'white',
    fontSize: 10,
    fontWeight: 'bold'
  },
  
  historySection: { 
    flex: 1, 
    margin: 15, 
    backgroundColor: 'white', 
    borderRadius: 8, 
    padding: 10,
    elevation: 2
  },
  historyTitle: { 
    fontSize: 14, 
    fontWeight: 'bold', 
    color: '#2c3e50', 
    marginBottom: 10 
  },
  historyScroll: { 
    flex: 1 
  },
  historyItem: { 
    padding: 10, 
    borderBottomWidth: 1, 
    borderBottomColor: '#ecf0f1'
  },
  offlineItem: { 
    backgroundColor: '#fff3cd', 
    borderLeftWidth: 3, 
    borderLeftColor: '#f39c12',
    borderRadius: 4,
    marginBottom: 8 
  },
  historyContent: { 
    flex: 1 
  },
  historyName: { 
    fontSize: 14, 
    fontWeight: 'bold', 
    color: '#2c3e50',
    marginBottom: 2
  },
  historyType: { 
    fontSize: 12, 
    fontWeight: 'bold',
    color: '#34495e',
    marginBottom: 2
  },
  historyTime: { 
    fontSize: 10, 
    color: '#7f8c8d',
    marginBottom: 3
  },
  locationInfo: {
    fontSize: 9,
    color: '#27ae60',
    marginBottom: 3
  },
  offlineBadge: { 
    backgroundColor: '#f39c12', 
    color: 'white', 
    padding: 3, 
    borderRadius: 3, 
    fontSize: 8, 
    fontWeight: 'bold', 
    alignSelf: 'flex-start', 
    marginBottom: 5 
  },
  syncBadge: {
    backgroundColor: '#27ae60',
    color: 'white',
    padding: 2,
    borderRadius: 2,
    fontSize: 8,
    fontWeight: 'bold',
    alignSelf: 'flex-start'
  },
  noRecords: { 
    textAlign: 'center', 
    color: '#7f8c8d', 
    fontStyle: 'italic', 
    marginTop: 30,
    lineHeight: 16,
    fontSize: 12
  },

  // Estilos del modal
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20
  },
  modalContent: {
    backgroundColor: 'white',
    borderRadius: 8,
    padding: 20,
    width: '100%',
    maxHeight: '80%'
  },
  modalTitle: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#2c3e50',
    textAlign: 'center',
    marginBottom: 15
  },
  employeeList: {
    maxHeight: 300,
    marginBottom: 15
  },
  employeeItem: {
    padding: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#ecf0f1',
    borderRadius: 6,
    marginBottom: 3
  },
  selectedEmployeeItem: {
    backgroundColor: '#e8f5e8',
    borderLeftWidth: 3,
    borderLeftColor: '#27ae60'
  },
  employeeItemName: {
    fontSize: 14,
    fontWeight: 'bold',
    color: '#2c3e50',
    marginBottom: 2
  },
  employeeItemDetails: {
    fontSize: 10,
    color: '#7f8c8d'
  },
  modalButtons: {
    flexDirection: 'row',
    gap: 10
  },
  modalButton: {
    flex: 1,
    padding: 12,
    borderRadius: 6,
    alignItems: 'center'
  },
  createButton: {
    backgroundColor: '#27ae60'
  },
  cancelButton: {
    backgroundColor: '#e74c3c'
  },
  modalButtonText: {
    color: 'white',
    fontWeight: 'bold',
    fontSize: 12
  },
  input: {
    borderWidth: 1,
    borderColor: '#ddd',
    borderRadius: 6,
    padding: 12,
    marginBottom: 10,
    fontSize: 14
  },
});