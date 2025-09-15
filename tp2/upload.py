import sys
from socket import *



def main():
    
    args = sys.argv
    serverIp = args[1]
    serverPort = int(args[2])
    
    clientSocket = socket(AF_INET, SOCK_DGRAM)
    print(f'mensaje a enviar a {serverIp}:{serverPort}')
    message = input("Input something: ")
    for a in message:
        clientSocket.sendto(a.encode(),(serverIp, serverPort))
    modifiedMessage, serverAddress = clientSocket.recvfrom(2048)
    print(modifiedMessage.decode())
    clientSocket.close()

main()