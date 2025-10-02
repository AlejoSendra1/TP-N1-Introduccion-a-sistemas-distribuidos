import time
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import OVSController
from mininet.cli import CLI
from mininet.link import TCLink

class MyTopo(Topo):
    def build(self, loss=10):
        switch = self.addSwitch('s1')
        
        h1 = self.addHost('h1')
        h2 = self.addHost('h2')
        h3 = self.addHost('h3')
        h4 = self.addHost('h4')
        
        self.addLink(h1, switch, bw=10, max_queue_size=1000, loss=loss, use_htb=True)
        self.addLink(h2, switch, bw=10, max_queue_size=1000, use_htb=True)
        self.addLink(h3, switch)
        self.addLink(h4, switch)

def run_upload(host, file, protocol='stop_wait'):
    """Función para ejecutar la subida de un archivo"""
    host.cmd(f'python3 upload.py -H 10.0.0.1 -s ../data/{file} -r {protocol}')

def run_upload_concurrent(host , file, protocol='stop_wait'):
    """Función para ejecutar la subida de un archivo de forma concurrente"""
    return host.popen(f'cd src && python3 upload.py -H 10.0.0.1 -s ../data/{file} -r {protocol}')

def run_download(host, filename, destination, protocol='stop_wait'):
    """Función para ejecutar la descarga de un archivo"""
    host.cmd(f'python3 download.py -H 10.0.0.1 -n {filename} -d {destination} -r {protocol}')

def run_download_concurrent(host, filename, destination, protocol='stop_wait'):
    """Función para ejecutar la descarga de un archivo de forma concurrente"""
    return host.popen(f'cd src && python3 download.py -H 10.0.0.1 -n {filename} -d {destination} -r {protocol}')

def setup_and_test(net: Mininet):
    """Configurar y ejecutar las pruebas con upload/download concurrentes"""
    h1 = net.get('h1')  # servidor
    h2 = net.get('h2')  # cliente uploads
    h3 = net.get('h3')  # cliente downloads
    h4 = net.get('h4')  # libre para futuros tests

    server_ip = h1.IP()
    port = 5000
    protocol = "stop_wait"
    files_to_transfer = ["1kb", "10kb", "100kb", "1mb", "6mb", "10mb"]

    print("=== Iniciando servidor en h1 ===")
    h1.popen(
        ["python3", "start-server.py",
         "-H", server_ip],
        cwd="src"
    )
    time.sleep(5)  # dar tiempo al server para inicializar

    print("=== Uploads concurrentes ===")
    uploads = [
        h2.popen(
            ["python3", "upload.py",
             "-H", server_ip,
             "-s", f"../data/{size}.jpeg",
             "-r", protocol],
            cwd="src"
        )
        for size in files_to_transfer
    ]

    for i, proc in enumerate(uploads, 1):
        proc.wait()
        print(f"Upload {i} terminado.")

    print("=== Downloads concurrentes ===")
    downloads = [
        h3.popen(
            ["python3", "download.py",
             "-H", server_ip,
             "-d", f"r_{size}.jpeg",
             "-n", f"d_{size}.jpeg",
             "-r", protocol],
            cwd="src"
        )
        for size in files_to_transfer
    ]

    for i, proc in enumerate(downloads, 1):
        proc.wait()
        print(f"Download {i} terminado.")

    print("=== Uploads + Downloads concurrentes ===")
    mixed = []
    for size in files_to_transfer:
        mixed.append(
            h2.popen(
                ["python3", "upload.py",
                 "-H", server_ip,
                 "-s", f"../data/{size}.jpeg",
                 "-r", protocol],
                cwd="src"
            )
        )
        mixed.append(
            h3.popen(
                ["python3", "download.py",
                 "-H", server_ip,
                 "-d", f"rm_{size}.jpeg",
                 "-n", f"d_{size}.jpeg",
                 "-r", protocol],
                cwd="src"
            )
        )

    for i, proc in enumerate(mixed, 1):
        proc.wait()
        print(f"Tarea mixta {i} terminada.")

    print("=== Todas las transferencias finalizadas ===")

def setup_and_test_blocking(net: Mininet):
    """Configurar y ejecutar las pruebas de manera BLOQUEANTE (secuencial)"""
    h1 = net.get('h1')  # servidor
    h2 = net.get('h2')  # cliente uploads
    h3 = net.get('h3')  # cliente downloads
    h4 = net.get('h4')  # libre para futuros tests

    server_ip = h1.IP()
    port = 5000
    protocol = "stop_wait"
    files_to_transfer = ["1kb", "10kb", "100kb", "1mb", "6mb", "10mb"]

    print("=== Iniciando servidor en h1 (bloqueante) ===")
    h1.cmd(
        f"cd src && python3 start-server.py -H {server_ip} &"
    )
    time.sleep(5)  # esperar al server

    h2.cmd("cd src")
    h3.cmd("cd src")

    print("=== Uploads secuenciales ===")
    for size in files_to_transfer:
        print(f"Subiendo {size}.jpeg desde h2...")
        output = h2.cmd(
            f"python3 upload.py -H {server_ip}"
            f" -s ../data/{size}.jpeg -r {protocol}"
        )
        print(output.strip())

    print("=== Downloads secuenciales ===")
    for size in files_to_transfer:
        print(f"Descargando {size}.jpeg en h3...")
        output = h3.cmd(
            f"python3 download.py -H {server_ip}"
            f" -d r_{size}.jpeg -n d_{size}.jpeg -r {protocol}"
        )
        print(output.strip())

    print("=== Uploads + Downloads intercalados (bloqueantes) ===")
    for size in files_to_transfer:
        print(f"Subiendo {size}.jpeg desde h2...")
        out_up = h2.cmd(
            f"python3 upload.py -H {server_ip} "
            f"-s ../data/{size}.jpeg -r {protocol}"
        )
        print(out_up.strip())

        print(f"Descargando {size}.jpeg en h3...")
        out_down = h3.cmd(
            f"python3 download.py -H {server_ip} "
            f"-d rm_{size}.jpeg -n d_{size}.jpeg -r {protocol}"
        )
        print(out_down.strip())

    print("=== Todas las transferencias bloqueantes finalizadas ===")

def simple_test(net):
    """Prueba simple para debugging"""
    h1 = net.get('h1')
    h2 = net.get('h2')
    h3 = net.get('h3')
    
    print("=== Prueba simple ===")
    h1.cmd('cd src/ && python3 start-server.py -H 10.0.0.1 -v &')
    time.sleep(5)
    
    # Un solo upload
    print("Upload 1...")
    result1 = h2.cmd('python3 upload.py -H 10.0.0.1 -s ../data/1kb.jpeg -n test1.jpeg -v')
    print(f"Resultado: {result1}")
    
    time.sleep(3)
    
    # Segundo upload
    print("Upload 2...")
    result2 = h2.cmd('python3 upload.py -H 10.0.0.1 -s ../data/10kb.jpeg -n test2.jpeg -v')
    print(f"Resultado: {result2}")
    
    # Verificar archivos
    files = h1.cmd('ls src/storage/')
    print(f"Archivos: {files}")

if __name__ == '__main__':
    topo = MyTopo(loss=15)
    net = Mininet(topo=topo, controller=OVSController, link=TCLink)
    net.start()    

    try:
        # Ejecutar las pruebas
        setup_and_test(net)
        # Entrar en CLI para debugging manual
        CLI(net)
        
    except KeyboardInterrupt:
        print("Interrumpido por usuario")
    finally:
        print("Deteniendo red...")
        net.stop()