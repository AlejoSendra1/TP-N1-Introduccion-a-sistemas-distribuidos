import sys
import socket
import threading

def handle_client(data, addr, sock):
    print(f"[NEW THREAD] Received from {addr}: {data.decode()}")
    response = f"Server received: {data.decode()}"
    sock.sendto(response.encode(), addr)

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    args = sys.argv
    serverIp = args[1]
    serverPort = int(args[2])

    sock.bind((serverIp, serverPort))
    print(f"UDP server listening on {serverIp}:{serverPort}...")

    while True:
        data, addr = sock.recvfrom(1024)  
        print(f"[MAIN THREAD] Packet from {addr}")
        
        # Start a new thread for each message
        client_thread = threading.Thread(
            target=handle_client,
            args=(data, addr, sock),
            daemon=True
        )
        client_thread.start()

main()


