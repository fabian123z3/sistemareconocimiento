import React, { useState, useEffect } from 'react';
import { View, Text, StyleSheet, Alert, TouchableOpacity, ScrollView } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import AsyncStorage from '@react-native-async-storage/async-storage';
import NetInfo from '@react-native-community/netinfo';
import * as Location from 'expo-location';

const API_BASE_URL = 'http://192.168.96.36:8000/api';

interface AttendanceRecord {
  id: string;
  employee_name: string;
  attendance_type: string;
  timestamp: string;
  latitude: number;
  longitude: number;
  address: string;
}

interface OfflineRecord {
  local_id: string;
  type: string;
  timestamp: string;
  latitude: number;
  longitude: number;
  address: string;
  employee_name: string;
}

export default function App() {
  const [attendanceHistory, setAttendanceHistory] = useState<AttendanceRecord[]>([]);
  const [offlineRecords, setOfflineRecords] = useState<OfflineRecord[]>([]);
  const [isOnline, setIsOnline] = useState(true);
  const [isSyncing, setIsSyncing] = useState(false);
  const [currentLocation, setCurrentLocation] = useState<string>('Obteniendo ubicación...');
  const [coordinates, setCoordinates] = useState<{lat: number, lng: number} | null>(null);
  const [employeeName] = useState('Usuario Demo'); // Nombre fijo para pruebas

  useEffect(() => {
    initializeApp();
  }, []);

  const initializeApp = async () => {
    await loadStoredData();
    await setupLocation();
    setupNetworkListener();
  };

  const setupLocation = async () => {
    try {
      console.log('🌍 Solicitando permisos de ubicación...');
      
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') {
        Alert.alert('Permisos', 'Se necesitan permisos de ubicación para registrar asistencia');
        setCurrentLocation('Sin permisos de ubicación');
        return;
      }

      console.log('✅ Permisos concedidos, obteniendo ubicación...');
      
      const location = await Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.High,
      });

      const { latitude, longitude } = location.coords;
      setCoordinates({ lat: latitude, lng: longitude });

      console.log(`📍 Ubicación obtenida: ${latitude}, ${longitude}`);

      // Obtener dirección legible
      try {
        const addresses = await Location.reverseGeocodeAsync({
          latitude,
          longitude,
        });

        if (addresses.length > 0) {
          const address = addresses[0];
          const fullAddress = `${address.street || ''} ${address.streetNumber || ''}, ${address.city || ''}, ${address.region || ''}`.trim();
          setCurrentLocation(fullAddress || `${latitude.toFixed(6)}, ${longitude.toFixed(6)}`);
          console.log('🏠 Dirección obtenida:', fullAddress);
        } else {
          setCurrentLocation(`${latitude.toFixed(6)}, ${longitude.toFixed(6)}`);
        }
      } catch (error) {
        console.log('❌ Error obteniendo dirección, usando coordenadas');
        setCurrentLocation(`${latitude.toFixed(6)}, ${longitude.toFixed(6)}`);
      }

    } catch (error) {
      console.error('❌ Error obteniendo ubicación:', error);
      Alert.alert('Error', 'No se pudo obtener la ubicación');
      setCurrentLocation('Error obteniendo ubicación');
    }
  };

  const setupNetworkListener = () => {
    NetInfo.addEventListener(state => {
      const wasOffline = !isOnline;
      const nowOnline = state.isConnected && state.isInternetReachable;
      
      setIsOnline(nowOnline || false);
      
      // Auto-sincronizar cuando vuelve la conexión
      if (wasOffline && nowOnline && offlineRecords.length > 0) {
        setTimeout(() => {
          syncOfflineRecords();
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

  const markAttendance = async (type: 'entrada' | 'salida') => {
    if (!coordinates) {
      Alert.alert('Error', 'No se ha obtenido la ubicación. Espera un momento e intenta de nuevo.');
      return;
    }

    console.log(`📝 Marcando ${type} para ${employeeName}`);
    console.log(`📍 Ubicación: ${currentLocation}`);
    console.log(`🗺️ Coordenadas: ${coordinates.lat}, ${coordinates.lng}`);

    const now = new Date();
    const timestamp = now.toISOString();

    if (!isOnline) {
      // Guardar offline
      console.log('📱 Guardando registro offline');
      
      const offlineRecord: OfflineRecord = {
        local_id: `offline_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
        type: type,
        timestamp: timestamp,
        latitude: coordinates.lat,
        longitude: coordinates.lng,
        address: currentLocation,
        employee_name: employeeName
      };

      const updatedOfflineRecords = [...offlineRecords, offlineRecord];
      setOfflineRecords(updatedOfflineRecords);
      await saveToStorage('offlineRecords', updatedOfflineRecords);

      Alert.alert(
        '📱 Registro Offline',
        `${type.toUpperCase()} guardada localmente\n\n` +
        `👤 ${employeeName}\n` +
        `📍 ${currentLocation}\n` +
        `🕒 ${now.toLocaleString('es-CL')}\n\n` +
        `Se sincronizará automáticamente cuando vuelva la conexión.`,
        [{ text: 'OK' }]
      );
      return;
    }

    // Enviar online
    try {
      console.log('🌐 Enviando registro online');
      
      const response = await fetch(`${API_BASE_URL}/mark-attendance/`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          employee_name: employeeName,
          type: type,
          timestamp: timestamp,
          latitude: coordinates.lat,
          longitude: coordinates.lng,
          address: currentLocation
        })
      });

      console.log('📡 Respuesta del servidor:', response.status);
      const data = await response.json();

      if (data.success) {
        console.log('✅ Registro enviado exitosamente');
        
        const newRecord: AttendanceRecord = {
          id: data.record.id,
          employee_name: employeeName,
          attendance_type: type,
          timestamp: now.toLocaleString('es-CL'),
          latitude: coordinates.lat,
          longitude: coordinates.lng,
          address: currentLocation,
        };

        const updatedHistory = [newRecord, ...attendanceHistory].slice(0, 50);
        setAttendanceHistory(updatedHistory);
        await saveToStorage('attendanceHistory', updatedHistory);

        Alert.alert(
          '✅ Registro Exitoso',
          `${type.toUpperCase()} registrada correctamente\n\n` +
          `👤 ${employeeName}\n` +
          `📍 ${currentLocation}\n` +
          `🕒 ${now.toLocaleString('es-CL')}`,
          [{ text: 'Perfecto!' }]
        );
      } else {
        throw new Error(data.message || 'Error en el servidor');
      }
    } catch (error) {
      console.error('❌ Error enviando registro:', error);
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
          console.log(`🔄 Sincronizando: ${record.type} - ${record.employee_name}`);
          
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
              is_offline_sync: true,
              offline_timestamp: record.timestamp
            })
          });

          const data = await response.json();
          
          if (data.success) {
            successCount++;
            console.log(`✅ Sincronizado: ${record.employee_name}`);
            
            const syncedRecord: AttendanceRecord = {
              id: data.record.id,
              employee_name: record.employee_name,
              attendance_type: record.type,
              timestamp: new Date(record.timestamp).toLocaleString('es-CL'),
              latitude: record.latitude,
              longitude: record.longitude,
              address: record.address,
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

      // Actualizar historial
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
          `Se sincronizaron ${successCount} registros offline.${remainingRecords.length > 0 ? `\n\n${remainingRecords.length} registros no pudieron sincronizarse.` : ''}`,
          [{ text: 'Excelente!' }]
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

  const testConnection = async () => {
    Alert.alert('🔍 Probando...', 'Verificando servidor');
    
    try {
      const response = await fetch(`${API_BASE_URL}/health/`);
      const data = await response.json();
      
      Alert.alert(
        '✅ Conexión OK', 
        `Servidor funcionando correctamente\n\nIP: 192.168.96.36:8000\nEstado: ${data.status}`
      );
    } catch (error) {
      Alert.alert('❌ Error de conexión', 'Verifica que el servidor Django esté corriendo en 192.168.96.36:8000');
    }
  };

  const refreshLocation = async () => {
    setCurrentLocation('Actualizando ubicación...');
    await setupLocation();
  };

  return (
    <View style={styles.container}>
      <StatusBar style="auto" />
      
      {/* Header */}
      <View style={[styles.header, !isOnline && styles.headerOffline]}>
        <Text style={styles.title}>📍 Sistema de Asistencia con GPS</Text>
        <Text style={styles.subtitle}>
          {isOnline ? '🌐 Conectado' : '📱 Modo Offline'}
          {offlineRecords.length > 0 && ` • ${offlineRecords.length} pendientes`}
          {isSyncing && ' • Sincronizando...'}
        </Text>
      </View>

      {/* Usuario y ubicación */}
      <View style={styles.userSection}>
        <Text style={styles.userName}>👤 {employeeName}</Text>
        <Text style={styles.locationTitle}>📍 Ubicación actual:</Text>
        <Text style={styles.locationText}>{currentLocation}</Text>
        {coordinates && (
          <Text style={styles.coordinatesText}>
            🗺️ {coordinates.lat.toFixed(6)}, {coordinates.lng.toFixed(6)}
          </Text>
        )}
        <TouchableOpacity style={styles.refreshButton} onPress={refreshLocation}>
          <Text style={styles.refreshButtonText}>🔄 Actualizar ubicación</Text>
        </TouchableOpacity>
      </View>

      {/* Botones principales */}
      <View style={styles.buttonSection}>
        <View style={styles.buttonRow}>
          <TouchableOpacity 
            style={[styles.button, styles.entradaButton]}
            onPress={() => markAttendance('entrada')}
            disabled={isSyncing || !coordinates}
          >
            <Text style={styles.buttonText}>📍 ENTRADA</Text>
            <Text style={styles.buttonSubtext}>Con ubicación GPS</Text>
          </TouchableOpacity>
          
          <TouchableOpacity 
            style={[styles.button, styles.salidaButton]}
            onPress={() => markAttendance('salida')}
            disabled={isSyncing || !coordinates}
          >
            <Text style={styles.buttonText}>📍 SALIDA</Text>
            <Text style={styles.buttonSubtext}>Con ubicación GPS</Text>
          </TouchableOpacity>
        </View>
        
        <TouchableOpacity 
          style={[styles.button, styles.testButton]}
          onPress={testConnection}
        >
          <Text style={styles.buttonText}>🔍 PROBAR CONEXIÓN</Text>
        </TouchableOpacity>

        {/* Botón de sincronización manual */}
        {offlineRecords.length > 0 && isOnline && !isSyncing && (
          <TouchableOpacity 
            style={[styles.button, styles.syncButton]}
            onPress={syncOfflineRecords}
          >
            <Text style={styles.buttonText}>🔄 SINCRONIZAR ({offlineRecords.length})</Text>
            <Text style={styles.buttonSubtext}>Enviar registros offline</Text>
          </TouchableOpacity>
        )}

        {isSyncing && (
          <View style={[styles.button, styles.syncingButton]}>
            <Text style={styles.buttonText}>⏳ SINCRONIZANDO...</Text>
            <Text style={styles.buttonSubtext}>Enviando al servidor...</Text>
          </View>
        )}
      </View>

      {/* Historial */}
      <View style={styles.historySection}>
        <Text style={styles.historyTitle}>📋 Registros de Asistencia</Text>
        <ScrollView style={styles.historyScroll}>
          {/* Registros offline pendientes */}
          {offlineRecords.map((record) => (
            <View key={record.local_id} style={[styles.historyItem, styles.offlineItem]}>
              <View style={styles.historyContent}>
                <Text style={styles.offlineBadge}>📱 PENDIENTE SYNC</Text>
                <Text style={styles.historyName}>{record.employee_name}</Text>
                <Text style={styles.historyType}>{record.type.toUpperCase()}</Text>
                <Text style={styles.historyTime}>
                  {new Date(record.timestamp).toLocaleString('es-CL')}
                </Text>
                <Text style={styles.locationInfo}>📍 {record.address}</Text>
                <Text style={styles.coordinatesInfo}>
                  🗺️ {record.latitude.toFixed(6)}, {record.longitude.toFixed(6)}
                </Text>
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
                <Text style={styles.locationInfo}>📍 {record.address}</Text>
                <Text style={styles.coordinatesInfo}>
                  🗺️ {record.latitude.toFixed(6)}, {record.longitude.toFixed(6)}
                </Text>
                <Text style={styles.syncBadge}>✅ Sincronizado</Text>
              </View>
            </View>
          ))}
          
          {attendanceHistory.length === 0 && offlineRecords.length === 0 && (
            <Text style={styles.noRecords}>
              No hay registros aún{'\n\n'}
              Usa los botones ENTRADA o SALIDA para comenzar a registrar tu asistencia con ubicación GPS
            </Text>
          )}
        </ScrollView>
      </View>
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
  
  userSection: { 
    backgroundColor: 'white', 
    margin: 20, 
    padding: 20, 
    borderRadius: 10, 
    alignItems: 'center',
    elevation: 2
  },
  userName: { 
    fontSize: 18, 
    fontWeight: 'bold', 
    color: '#2c3e50',
    marginBottom: 15
  },
  locationTitle: {
    fontSize: 14,
    fontWeight: 'bold',
    color: '#34495e',
    marginBottom: 5
  },
  locationText: { 
    fontSize: 14, 
    color: '#7f8c8d', 
    textAlign: 'center',
    marginBottom: 5
  },
  coordinatesText: {
    fontSize: 12,
    color: '#95a5a6',
    textAlign: 'center',
    marginBottom: 15
  },
  refreshButton: {
    backgroundColor: '#3498db',
    padding: 10,
    borderRadius: 8,
  },
  refreshButtonText: {
    color: 'white',
    fontSize: 12,
    fontWeight: 'bold'
  },
  
  buttonSection: { 
    paddingHorizontal: 20, 
    gap: 15 
  },
  buttonRow: { 
    flexDirection: 'row', 
    gap: 15 
  },
  button: { 
    padding: 15, 
    borderRadius: 10, 
    alignItems: 'center',
    elevation: 2
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
  syncingButton: { 
    backgroundColor: '#95a5a6' 
  },
  buttonText: { 
    color: 'white', 
    fontSize: 16, 
    fontWeight: 'bold' 
  },
  buttonSubtext: { 
    color: 'white', 
    fontSize: 10, 
    marginTop: 2, 
    opacity: 0.9 
  },
  
  historySection: { 
    flex: 1, 
    margin: 20, 
    backgroundColor: 'white', 
    borderRadius: 10, 
    padding: 15,
    elevation: 2
  },
  historyTitle: { 
    fontSize: 18, 
    fontWeight: 'bold', 
    color: '#2c3e50', 
    marginBottom: 15 
  },
  historyScroll: { 
    flex: 1 
  },
  historyItem: { 
    padding: 15, 
    borderBottomWidth: 1, 
    borderBottomColor: '#ecf0f1'
  },
  offlineItem: { 
    backgroundColor: '#fff3cd', 
    borderLeftWidth: 4, 
    borderLeftColor: '#f39c12',
    borderRadius: 5,
    marginBottom: 10 
  },
  historyContent: { 
    flex: 1 
  },
  historyName: { 
    fontSize: 16, 
    fontWeight: 'bold', 
    color: '#2c3e50',
    marginBottom: 3
  },
  historyType: { 
    fontSize: 14, 
    fontWeight: 'bold',
    color: '#34495e',
    marginBottom: 3
  },
  historyTime: { 
    fontSize: 12, 
    color: '#7f8c8d',
    marginBottom: 5
  },
  locationInfo: {
    fontSize: 11,
    color: '#27ae60',
    marginBottom: 2
  },
  coordinatesInfo: {
    fontSize: 10,
    color: '#95a5a6',
    marginBottom: 5
  },
  offlineBadge: { 
    backgroundColor: '#f39c12', 
    color: 'white', 
    padding: 4, 
    borderRadius: 4, 
    fontSize: 10, 
    fontWeight: 'bold', 
    alignSelf: 'flex-start', 
    marginBottom: 8 
  },
  syncBadge: {
    backgroundColor: '#27ae60',
    color: 'white',
    padding: 3,
    borderRadius: 3,
    fontSize: 9,
    fontWeight: 'bold',
    alignSelf: 'flex-start'
  },
  noRecords: { 
    textAlign: 'center', 
    color: '#7f8c8d', 
    fontStyle: 'italic', 
    marginTop: 50,
    lineHeight: 20
  },
});