Para implementar un manejo de errores robusto en el upload (subida de archivos), deberías considerar los siguientes puntos clave:

1. Validación de archivo fuente:
   - Ya lo tienes: si el archivo no existe, aborta y muestra error.

2. Manejo de errores de red y protocolo:
   - Si el servidor rechaza la transferencia (por ejemplo, responde con un paquete ERROR), deberías detectar ese paquete y mostrar el mensaje de error al usuario.
   - Si ocurre un timeout o se pierden demasiados paquetes, abortar la transferencia y mostrar un mensaje claro.

3. Retransmisión y reintentos:
   - Ya implementado en el protocolo, pero podrías exponer al usuario si se superan los reintentos máximos.

4. Señales de interrupción:
   - Ya manejas SIGINT/SIGTERM, pero podrías mostrar mensajes más claros o limpiar recursos adicionales si es necesario.

5. Respuestas del servidor:
   - Si el servidor responde con un paquete de tipo ERROR (PacketType.ERROR), deberías capturarlo en el cliente y mostrar el motivo.

6. Logging detallado:
   - Asegúrate de que todos los errores relevantes se registren con suficiente detalle para depuración.

7. Código sugerido (en el cliente upload.py):
   - En el método send_file y en la lógica de recepción de ACKs, verifica si recibes un paquete de tipo ERROR y actúa en consecuencia.

¿Quieres un ejemplo concreto de cómo detectar y manejar un paquete de error en el cliente?

----------------------------

Estructura del Informe - Transferencia de Archivos UDP vs TCP
1. INTRODUCCIÓN
Elementos obligatorios:

Contexto del problema (transferencia de archivos en redes)
Objetivos del trabajo práctico
Justificación de la comparación UDP vs TCP
Alcance y limitaciones del estudio
Estructura del informe
2. MARCO TEÓRICO
Elementos obligatorios:

Protocolo TCP:
Características (confiable, orientado a conexión)
Control de flujo y congestión
Overhead del protocolo
Protocolo UDP:
Características (no confiable, sin conexión)
Ventajas de performance
Necesidad de implementar confiabilidad
Transferencia de archivos:
Requisitos típicos
Métricas de rendimiento
Comparación teórica entre ambos protocolos
3. DISEÑO E IMPLEMENTACIÓN
Elementos obligatorios:

3.1 Arquitectura del Sistema
Diagrama de arquitectura general
Diagrama de flujo de comunicación
Identificación de componentes (cliente, servidor)
3.2 Implementación TCP
Diagrama de secuencia
Manejo de conexiones
Estructura de mensajes
Gestión de errores
3.3 Implementación UDP
Diagrama de secuencia
Protocolo de confiabilidad implementado:
Numeración de paquetes
Acknowledgments (ACKs)
Timeouts y retransmisiones
Control de flujo
Estructura de paquetes
Gestión de errores
3.4 Aspectos Comunes
Manejo de concurrencia
Interfaz de usuario
Configuración y parámetros
4. METODOLOGÍA DE EVALUACIÓN
Elementos obligatorios:

Métricas definidas:
Tiempo de transferencia
Throughput (MB/s o Mbps)
Uso de CPU
Uso de memoria
Número de retransmisiones (UDP)
Escenarios de prueba:
Tamaños de archivo (pequeños, medianos, grandes)
Condiciones de red (LAN, simulación de pérdidas)
Número de clientes concurrentes
Herramientas de medición
Configuración del entorno de pruebas
5. RESULTADOS EXPERIMENTALES
Elementos obligatorios:

5.1 Configuración de Pruebas
Hardware utilizado
Software y versiones
Parámetros de configuración
Condiciones de red
5.2 Resultados por Escenario
Para cada escenario:

Tablas de datos con métricas obtenidas
Gráficos comparativos:
Tiempo vs tamaño de archivo
Throughput vs tamaño de archivo
CPU/Memoria vs tiempo
Retransmisiones (UDP) vs condiciones de red
5.3 Análisis Estadístico
Medias, medianas, desviaciones estándar
Intervalos de confianza
Pruebas de significancia (si corresponde)
6. ANÁLISIS Y DISCUSIÓN
Elementos obligatorios:

Comparación de rendimiento:
¿Cuándo TCP es superior?
¿Cuándo UDP es superior?
Trade-offs identificados
Análisis de overhead:
Protocolo vs datos útiles
Impacto de retransmisiones
Comportamiento bajo diferentes condiciones:
Archivos pequeños vs grandes
Red estable vs con pérdidas
Un cliente vs múltiples clientes
Limitaciones de la implementación
Factores que afectan el rendimiento
7. CONCLUSIONES
Elementos obligatorios:

Resumen de hallazgos principales
Respuesta a los objetivos planteados
Recomendaciones de uso:
Cuándo usar TCP
Cuándo usar UDP
Lecciones aprendidas
Trabajo futuro
8. REFERENCIAS
Papers académicos sobre protocolos de red
RFCs relevantes (TCP, UDP)
Documentación técnica utilizada
ANEXOS
Elementos obligatorios:

Anexo A: Código fuente (snippets importantes)
Anexo B: Datos completos de experimentos
Anexo C: Manual de usuario (cómo ejecutar)
Anexo D: Configuraciones utilizadas
Consejos Adicionales:
Para cada sección con resultados:
Incluir siempre tablas de datos numéricos
Complementar con gráficos claros
Interpretar cada resultado mostrado
Relacionar con la teoría
Para gráficos:
Ejes claramente etiquetados con unidades
Leyendas descriptivas
Barras de error cuando corresponda
Colores/patrones distinguibles
Para código:
Comentarios explicativos
Solo mostrar partes relevantes
Explicar algoritmos implementados
---------------------------------------

melina-r: Podés leer este enunciado y analizar los puntos claves?

GitHub Copilot: He leído el enunciado del trabajo práctico sobre transferencia de archivos usando UDP y TCP. Te analizo los puntos clave:

## **Objetivo Principal**
Implementar un sistema de transferencia de archivos que funcione tanto con UDP como TCP, comparando el rendimiento de ambos protocolos.

## **Puntos Clave del Desarrollo**

### **1. Arquitectura del Sistema**
- **Cliente**: Solicita archivos al servidor
- **Servidor**: Responde a las solicitudes y envía archivos
- Debe funcionar con ambos protocolos (UDP/TCP)

### **2. Funcionalidades Requeridas**

**Para el Cliente:**
- Conectarse al servidor especificando protocolo (UDP/TCP)
- Solicitar archivos por nombre
- Recibir y guardar archivos localmente
- Manejar errores (archivo no encontrado, etc.)

**Para el Servidor:**
- Escuchar en ambos protocolos simultáneamente
- Procesar solicitudes de archivos
- Enviar archivos existentes
- Manejar múltiples clientes concurrentemente

### **3. Consideraciones Técnicas Importantes**

**Para UDP:**
- Implementar control de flujo manual
- Manejar pérdida de paquetes
- Implementar timeouts y retransmisiones
- Asegurar orden de paquetes
- Tamaño máximo de paquete (típicamente 1472 bytes para evitar fragmentación)

**Para TCP:**
- Aprovechar las garantías del protocolo (orden, entrega, control de flujo)
- Implementación más directa

### **4. Aspectos de Rendimiento a Evaluar**
- Tiempo de transferencia
- Throughput (velocidad de transferencia)
- Uso de CPU y memoria
- Comportamiento ante pérdida de paquetes (UDP)
- Overhead de protocolo

### **5. Manejo de Errores**
- Archivos no encontrados
- Errores de red
- Timeouts
- Corrupción de datos

### **6. Entregables**
- Código fuente comentado
- Informe comparativo de rendimiento
- Documentación de uso
- Análisis de resultados

## **Desafíos Principales**

1. **UDP**: Implementar confiabilidad sobre un protocolo no confiable
2. **Concurrencia**: Manejar múltiples clientes simultáneamente
3. **Medición**: Obtener métricas precisas de rendimiento
4. **Comparación justa**: Asegurar condiciones similares para ambos protocolos

¿Te gustaría que profundice en algún aspecto específico o que te ayude con el diseño de la arquitectura?

melina-r: Podés ayudarme a planificar el informe? Cosas que si o sí tengo que tener en cada sección

GitHub Copilot: ## **Estructura del Informe - Transferencia de Archivos UDP vs TCP**

### **1. INTRODUCCIÓN**
**Elementos obligatorios:**
- Contexto del problema (transferencia de archivos en redes)
- Objetivos del trabajo práctico
- Justificación de la comparación UDP vs TCP
- Alcance y limitaciones del estudio
- Estructura del informe

### **2. MARCO TEÓRICO**
**Elementos obligatorios:**
- **Protocolo TCP:**
  - Características (confiable, orientado a conexión)
  - Control de flujo y congestión
  - Overhead del protocolo
- **Protocolo UDP:**
  - Características (no confiable, sin conexión)
  - Ventajas de performance
  - Necesidad de implementar confiabilidad
- **Transferencia de archivos:**
  - Requisitos típicos
  - Métricas de rendimiento
- **Comparación teórica** entre ambos protocolos

### **3. DISEÑO E IMPLEMENTACIÓN**
**Elementos obligatorios:**

#### **3.1 Arquitectura del Sistema**
- Diagrama de arquitectura general
- Diagrama de flujo de comunicación
- Identificación de componentes (cliente, servidor)

#### **3.2 Implementación TCP**
- Diagrama de secuencia
- Manejo de conexiones
- Estructura de mensajes
- Gestión de errores

#### **3.3 Implementación UDP**
- Diagrama de secuencia
- **Protocolo de confiabilidad implementado:**
  - Numeración de paquetes
  - Acknowledgments (ACKs)
  - Timeouts y retransmisiones
  - Control de flujo
- Estructura de paquetes
- Gestión de errores

#### **3.4 Aspectos Comunes**
- Manejo de concurrencia
- Interfaz de usuario
- Configuración y parámetros

### **4. METODOLOGÍA DE EVALUACIÓN**
**Elementos obligatorios:**
- **Métricas definidas:**
  - Tiempo de transferencia
  - Throughput (MB/s o Mbps)
  - Uso de CPU
  - Uso de memoria
  - Número de retransmisiones (UDP)
- **Escenarios de prueba:**
  - Tamaños de archivo (pequeños, medianos, grandes)
  - Condiciones de red (LAN, simulación de pérdidas)
  - Número de clientes concurrentes
- **Herramientas de medición**
- **Configuración del entorno de pruebas**

### **5. RESULTADOS EXPERIMENTALES**
**Elementos obligatorios:**

#### **5.1 Configuración de Pruebas**
- Hardware utilizado
- Software y versiones
- Parámetros de configuración
- Condiciones de red

#### **5.2 Resultados por Escenario**
Para cada escenario:
- **Tablas de datos** con métricas obtenidas
- **Gráficos comparativos:**
  - Tiempo vs tamaño de archivo
  - Throughput vs tamaño de archivo
  - CPU/Memoria vs tiempo
  - Retransmisiones (UDP) vs condiciones de red

#### **5.3 Análisis Estadístico**
- Medias, medianas, desviaciones estándar
- Intervalos de confianza
- Pruebas de significancia (si corresponde)

### **6. ANÁLISIS Y DISCUSIÓN**
**Elementos obligatorios:**
- **Comparación de rendimiento:**
  - ¿Cuándo TCP es superior?
  - ¿Cuándo UDP es superior?
  - Trade-offs identificados
- **Análisis de overhead:**
  - Protocolo vs datos útiles
  - Impacto de retransmisiones
- **Comportamiento bajo diferentes condiciones:**
  - Archivos pequeños vs grandes
  - Red estable vs con pérdidas
  - Un cliente vs múltiples clientes
- **Limitaciones de la implementación**
- **Factores que afectan el rendimiento**

### **7. CONCLUSIONES**
**Elementos obligatorios:**
- Resumen de hallazgos principales
- Respuesta a los objetivos planteados
- Recomendaciones de uso:
  - Cuándo usar TCP
  - Cuándo usar UDP
- Lecciones aprendidas
- Trabajo futuro

### **8. REFERENCIAS**
- Papers académicos sobre protocolos de red
- RFCs relevantes (TCP, UDP)
- Documentación técnica utilizada

### **ANEXOS**
**Elementos obligatorios:**
- **Anexo A: Código fuente** (snippets importantes)
- **Anexo B: Datos completos** de experimentos
- **Anexo C: Manual de usuario** (cómo ejecutar)
- **Anexo D: Configuraciones** utilizadas

## **Consejos Adicionales:**

### **Para cada sección con resultados:**
- Incluir siempre **tablas de datos numéricos**
- Complementar con **gráficos claros**
- **Interpretar** cada resultado mostrado
- **Relacionar** con la teoría

### **Para gráficos:**
- Ejes claramente etiquetados con unidades
- Leyendas descriptivas
- Barras de error cuando corresponda
- Colores/patrones distinguibles

### **Para código:**
- Comentarios explicativos
- Solo mostrar partes relevantes
- Explicar algoritmos implementados

¿Te gustaría que desarrolle alguna sección específica o que te ayude con la metodología de evaluación?

melina-r: como puedo evaluar estas cosas:
4. Aspectos de Rendimiento a Evaluar
Tiempo de transferencia
Throughput (velocidad de transferencia)
Uso de CPU y memoria
Comportamiento ante pérdida de paquetes (UDP)
Overhead de protocolo


GitHub Copilot: ## **Cómo Evaluar Aspectos de Rendimiento**

### **1. TIEMPO DE TRANSFERENCIA**

#### **Implementación:**
````python
import time

# En el cliente
start_time = time.perf_counter()
# ... transferencia del archivo ...
end_time = time.perf_counter()
transfer_time = end_time - start_time
````

#### **Métricas a capturar:**
- **Tiempo total** (desde solicitud hasta archivo completo)
- **Tiempo de establecimiento de conexión** (solo TCP)
- **Tiempo de transferencia pura** (sin handshakes)

#### **Metodología:**
- Ejecutar **múltiples runs** (mínimo 10) por escenario
- Calcular **media, mediana, desviación estándar**
- Descartar outliers (primeras ejecuciones para "calentar" el sistema)

### **2. THROUGHPUT (VELOCIDAD DE TRANSFERENCIA)**

#### **Cálculo:**
````python
file_size_bytes = os.path.getsize(filename)
throughput_mbps = (file_size_bytes * 8) / (transfer_time * 1_000_000)
throughput_mbs = file_size_bytes / (transfer_time * 1_000_000)
````

#### **Métricas importantes:**
- **Throughput efectivo**: Solo datos útiles / tiempo total
- **Throughput de red**: Incluye overhead del protocolo
- **Throughput sostenido**: Promedio durante toda la transferencia

#### **Escenarios de prueba:**
- Archivos de diferentes tamaños: 1KB, 10KB, 100KB, 1MB, 10MB, 100MB
- Múltiples transferencias simultáneas

### **3. USO DE CPU Y MEMORIA**

#### **Herramientas recomendadas:**

**En Linux:**
````python
import psutil
import threading
import time

class ResourceMonitor:
    def __init__(self, pid):
        self.process = psutil.Process(pid)
        self.cpu_samples = []
        self.memory_samples = []
        self.monitoring = False
        
    def start_monitoring(self):
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor)
        self.monitor_thread.start()
        
    def _monitor(self):
        while self.monitoring:
            self.cpu_samples.append(self.process.cpu_percent())
            self.memory_samples.append(self.process.memory_info().rss / 1024 / 1024)  # MB
            time.sleep(0.1)  # Muestrear cada 100ms
            
    def stop_monitoring(self):
        self.monitoring = False
        self.monitor_thread.join()
        
    def get_stats(self):
        return {
            'avg_cpu': sum(self.cpu_samples) / len(self.cpu_samples),
            'max_cpu': max(self.cpu_samples),
            'avg_memory': sum(self.memory_samples) / len(self.memory_samples),
            'max_memory': max(self.memory_samples)
        }
````

**Usando herramientas del sistema:**
````bash
# Durante la transferencia, en terminal separada:
top -p <PID_PROCESO> -d 1
# o
htop -p <PID_PROCESO>
# o para logging automático:
pidstat -u -r -p <PID> 1 > resource_usage.log
````

### **4. COMPORTAMIENTO ANTE PÉRDIDA DE PAQUETES (UDP)**

#### **Simulación de pérdida de paquetes:**

**Opción 1: Usando tc (Traffic Control) en Linux:**
````bash
# Agregar pérdida de paquetes del 1%
sudo tc qdisc add dev lo root netem loss 1%

# Agregar delay y pérdida
sudo tc qdisc add dev lo root netem delay 10ms loss 5%

# Limpiar reglas
sudo tc qdisc del dev lo root
````

**Opción 2: Implementación en código:**
````python
import random

def simulate_packet_loss(packet, loss_rate=0.05):
    """Simula pérdida de paquetes con probabilidad loss_rate"""
    if random.random() < loss_rate:
        return None  # Paquete "perdido"
    return packet
````

#### **Métricas a medir:**
- **Número de retransmisiones**
- **Tiempo adicional por retransmisiones**
- **Throughput efectivo vs teórico**
- **Tasa de pérdida vs impacto en rendimiento**

````python
class UDPStats:
    def __init__(self):
        self.packets_sent = 0
        self.packets_retransmitted = 0
        self.timeouts = 0
        
    def retransmission_rate(self):
        return self.packets_retransmitted / self.packets_sent if self.packets_sent > 0 else 0
````

### **5. OVERHEAD DE PROTOCOLO**

#### **Medición del overhead:**
````python
def calculate_protocol_overhead(file_size, total_bytes_transmitted):
    """
    file_size: tamaño del archivo original
    total_bytes_transmitted: total de bytes enviados por la red
    """
    overhead_bytes = total_bytes_transmitted - file_size
    overhead_percentage = (overhead_bytes / file_size) * 100
    return overhead_bytes, overhead_percentage
````

#### **Para TCP:**
- **Headers TCP/IP**: ~40 bytes por paquete
- **Handshake inicial**: 3 paquetes
- **Cierre de conexión**: 4 paquetes

#### **Para UDP:**
- **Headers UDP/IP**: ~28 bytes por paquete
- **ACKs implementados**: Contar bytes de acknowledgments
- **Retransmisiones**: Bytes adicionales por paquetes perdidos

````python
class ProtocolAnalyzer:
    def __init__(self):
        self.total_data_bytes = 0
        self.total_network_bytes = 0
        self.control_bytes = 0  # ACKs, headers custom, etc.
        
    def add_packet(self, data_size, header_size, is_retransmission=False):
        self.total_data_bytes += data_size if not is_retransmission else 0
        self.total_network_bytes += data_size + header_size
        if is_retransmission:
            self.control_bytes += data_size + header_size
            
    def get_overhead_stats(self):
        return {
            'data_efficiency': self.total_data_bytes / self.total_network_bytes,
            'protocol_overhead': (self.total_network_bytes - self.total_data_bytes) / self.total_data_bytes,
            'retransmission_overhead': self.control_bytes / self.total_data_bytes
        }
````

## **METODOLOGÍA DE EVALUACIÓN COMPLETA**

### **Script de automatización:**
````python
import json
import statistics

class PerformanceEvaluator:
    def __init__(self, protocol, file_path, iterations=10):
        self.protocol = protocol
        self.file_path = file_path
        self.iterations = iterations
        self.results = []
        
    def run_evaluation(self):
        for i in range(self.iterations):
            print(f"Iteration {i+1}/{self.iterations}")
            
            # Iniciar monitoreo de recursos
            monitor = ResourceMonitor(os.getpid())
            monitor.start_monitoring()
            
            # Ejecutar transferencia
            start_time = time.perf_counter()
            success, stats = self.transfer_file()
            end_time = time.perf_counter()
            
            # Detener monitoreo
            monitor.stop_monitoring()
            
            if success:
                result = {
                    'iteration': i,
                    'transfer_time': end_time - start_time,
                    'throughput': self.calculate_throughput(end_time - start_time),
                    'resource_usage': monitor.get_stats(),
                    'protocol_stats': stats
                }
                self.results.append(result)
                
    def generate_report(self):
        if not self.results:
            return None
            
        transfer_times = [r['transfer_time'] for r in self.results]
        throughputs = [r['throughput'] for r in self.results]
        
        return {
            'protocol': self.protocol,
            'file_size': os.path.getsize(self.file_path),
            'iterations': len(self.results),
            'transfer_time': {
                'mean': statistics.mean(transfer_times),
                'median': statistics.median(transfer_times),
                'std_dev': statistics.stdev(transfer_times) if len(transfer_times) > 1 else 0,
                'min': min(transfer_times),
                'max': max(transfer_times)
            },
            'throughput': {
                'mean': statistics.mean(throughputs),
                'median': statistics.median(throughputs),
                'std_dev': statistics.stdev(throughputs) if len(throughputs) > 1 else 0
            },
            'resource_usage': self.aggregate_resource_usage(),
            'raw_data': self.results
        }
````

### **Escenarios de prueba recomendados:**
1. **Archivos pequeños** (1KB - 100KB): Evaluar overhead
2. **Archivos medianos** (1MB - 10MB): Rendimiento típico
3. **Archivos grandes** (50MB - 500MB): Sostenibilidad
4. **Múltiples clientes**: Escalabilidad
5. **Condiciones de red adversas**: Robustez

¿Te gustaría que desarrolle algún aspecto específico o que te ayude con la implementación de alguna de estas métricas?