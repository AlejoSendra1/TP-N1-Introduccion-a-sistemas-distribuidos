import sys
from socket import *

"""
self.addLink( node1, node2, bw=10, delay='5ms', max_queue_size=1000, loss=10, use_htb=True): 
adds a bidirectional link with bandwidth, delay and loss characteristics, with a maximum queue
size of 1000 packets using the Hierarchical Token Bucket rate limiter and netem delay/loss emulator. 
The parameter bw is expressed as a number in Mbit; delay is expressed as a string with units in place
 (e.g. '5ms', '100us', '1s'); loss is expressed as a percentage (between 0 and 100); 
 and max_queue_size is expressed in packets.
"""

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