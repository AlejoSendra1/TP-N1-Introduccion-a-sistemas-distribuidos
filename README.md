# TP N° 1: Introducción a Sistemas Distribuidos
Este repositorio contiene la implementación del Trabajo Práctico N° 1 de la materia Introducción a Sistemas Distribuidos. El proyecto consiste en un servidor de archivos y un cliente para la carga de los mismos, implementados en Python. La topología de red propuesta para las pruebas puede ser simulada utilizando Mininet.

## Modo de Uso

### Servidor
    
El servidor se encarga de escuchar conexiones y gestionar la recepción y distribución de archivos.

Modo de ejecucion:


```
python3 start-server.py [-h] [-v | -q] [-H HOST] [-p PORT] [-s STORAGE]
```
#### Opciones disponibles:

- `-h`, `--help`: Muestra el mensaje de ayuda.
- `-v`, `--verbose`: Aumenta el nivel de detalle en los mensajes de salida
- `-q`, `--quiet`: Disminuye el nivel de detalle en los mensajes de salida. 
- `-H HOST`, `--host HOST`: Dirección IP en el que el servidor escuchará las conexiones
- `-p PORT`, `--port PORT`: Número de puerto en el que el servidor estará escuchando.
- `-s STORAGE`, `--storage STORAGE`: Ruta al directorio donde se almacenarán los archivos recibidos. Por default es el directorio storage en el que se encuentra parado al momento de ejecutarlo (en caso de no existir se crea).


Ejemplo de ejecucion:

```
python3 start-server.py -H 10.0.0.1 -p 13000
```

<br>


### Cliente
El cliente se encarga de conectar al servidor y enviar o recibir archivos.

### Upload
Modo de ejecucion:

```
python3 upload.py [-h] [-v | -q] [-H HOST] [-p PORT] -s SRC [-n NAME]
[-r {stop_wait,selective_repeat}]
```
#### Opciones disponibles:

- `-h`, `--help`: Muestra el mensaje de ayuda.
- `-v`, `--verbose`: Aumenta el nivel de detalle en los mensajes de salida
- `-q`, `--quiet`: Disminuye el nivel de detalle en los mensajes de salida. 
- `-H HOST`, `--host HOST`: Dirección IP del servidor.  
- `-p PORT`, `--port PORT`: Puerto en el que escucha el servidor.  
- `-s SRC`, `--src SRC`: Ruta al archivo que se desea enviar.  
- `-n NAME`, `--name NAME`: Nombre con el que se guardará el archivo en el servidor (por defecto se usa el nombre original).  
- `-r {stop_wait,selective_repeat}`, `--protocol {stop_wait,selective_repeat}`: Protocolo de recuperación de errores a utilizar (por default se usa stop and wait).  

Ejemplo de ejecucion:

```
python3 upload.py -v -H 10.0.0.1 -p 13000 -s prueba123.jpg
```

### Download
Modo de ejecucion:

```
python3 download.py [-h] [-v | -q] [-H HOST] [-p PORT] -d DST -n NAME
[-r {stop_wait,selective_repeat}]
```
#### Opciones disponibles:

- `-h`, `--help`: Muestra el mensaje de ayuda.
- `-v`, `--verbose`: Aumenta el nivel de detalle en los mensajes de salida
- `-q`, `--quiet`: Disminuye el nivel de detalle en los mensajes de salida. 
- `-H HOST`, `--host HOST`: Dirección IP del servidor.  
- `-p PORT`, `--port PORT`: Puerto en el que escucha el servidor.  
- `-d DST`, `--dst DST`: Ruta local donde se guardará el archivo descargado.  
- `-n NAME`, `--name NAME`: Nombre del archivo que se desea descargar del servidor.  
- `-r {stop_wait,selective_repeat}`, `--protocol {stop_wait,selective_repeat}`: Protocolo de recuperación de errores a utilizar (por default se usa stop and wait).  

Ejemplo de ejecucion:

```
python3 download.py -v -H 10.0.0.1 -p 13000 -n prueba123.jpg -d hola123.jpg
```
<br>

## 🌐 Simulación con Mininet
Se proporciona un script para simular una topología de red simple.

<br>

### Pasos para la Simulación

```
sudo python3 mininet_topology.py
```

Una vez en la consola de Mininet, se puede abrir terminales para cada host con el comando xterm:

```
mininet> xterm <nombre_de_host>
```

Los nombres de los hosts son h1, h2, etc..

Dentro de cada nueva terminal (xterm), se pueden ejecutar los script's de servidor o cliente.


### Comandos Útiles en Mininet

Ver la configuración de red de un host: 
```
mininet> <nombre_de_host> ifconfig
```

Ejemplo:
```
mininet> h1 ifconfig
```

Para salir de la consola de Mininet:
```
mininet> exit
```

Para liberar recursos ocupados en caso de cierre incorrecto de la app:
```
mn -c 
```
