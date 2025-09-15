# TP N° 1: Introducción a Sistemas Distribuidos
Este repositorio contiene la implementación del Trabajo Práctico N° 1 de la materia Introducción a Sistemas Distribuidos. El proyecto consiste en un servidor de archivos y un cliente para la carga de los mismos, implementados en Python. La topología de red propuesta para las pruebas puede ser simulada utilizando Mininet.

## Modo de Uso

### Servidor
    
El servidor se encarga de escuchar conexiones y gestionar la recepción y distribución de archivos.

Modo de ejecucion:

```
python3 server.py <interfaz_de_escucha> <puerto>
```

Donde: 
< interfazde escucha>: La interfaz de red en la que el servidor escuchará las conexiones. 0.0.0.0 para escuchar en todas las interfaces disponibles.

< puerto >: El número de puerto en el que el servidor estará escuchando.

Ejemplo:

```
python3 server.py 0.0.0.0 13000
``` 

<br>


### Cliente
El cliente se encarga de conectar al servidor y enviar msj (por ahora).

Modo de ejecucion:

```
python3 upload.py <ip_del_servidor> <puerto_del_servidor>
```

< ip del servidor >: La dirección IP del servidor.

< puerto del servidor >: El número de puerto en el que antiende el servidor.

Ejemplo:

```
python3 upload.py 10.0.0.1 13000
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

para liberar recursos ocupados en caso de cierre incorrecto de la app:
```
mn -c 
```