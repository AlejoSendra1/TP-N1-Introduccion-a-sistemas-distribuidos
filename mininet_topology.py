from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import OVSController
from mininet.cli import CLI
from mininet.link import TCLink

class MyTopo(Topo):
    def build(self):
        switch = self.addSwitch('s1')
        
        h1 = self.addHost('h1')
        h2 = self.addHost('h2')
        h3 = self.addHost('h3')
        
        self.addLink(h1, switch, bw=10, max_queue_size=1000, loss=10, use_htb=True)
        self.addLink(h2, switch, bw=10, max_queue_size=1000, use_htb=True)
        self.addLink(h3, switch)

if __name__ == '__main__':
    topo = MyTopo()
    net = Mininet(topo=topo, controller=OVSController, link=TCLink)
    net.start()    

    # Abre la CLI de Mininet
    CLI(net)
    net.stop()

"""
self.addLink( node1, node2, bw=10, delay='5ms', max_queue_size=1000, loss=10, use_htb=True): 
adds a bidirectional link with bandwidth, delay and loss characteristics, with a maximum queue
size of 1000 packets using the Hierarchical Token Bucket rate limiter and netem delay/loss emulator. 
The parameter bw is expressed as a number in Mbit; delay is expressed as a string with units in place
 (e.g. '5ms', '100us', '1s'); loss is expressed as a percentage (between 0 and 100); 
 and max_queue_size is expressed in packets.
"""