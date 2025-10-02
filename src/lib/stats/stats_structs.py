import os
import time
import statistics

class Stats:
    def __init__(self, process, protocol):
        self.process = process
        self.protocol = protocol
        self.start_time = None
        self.connection_time = None
        self.end_time = None
        self.final_status = None  # "success" or "failure"
        self.handshake_attempts = 0
        self.file_size = 0
        self.packets = 0

        # For Selective Repeat
        self.window_size = 0  
        self.window_utilization = []

    def start(self):
        self.start_time = time.time()

    def mark_connection_established(self):
        self.connection_time = time.time()

    def finish(self, status="success"):
        self.end_time = time.time()
        self.final_status = status
        self.record_to_csv()

    def record_to_csv(self, filename="stats.csv"):
        pass  # To be implemented in subclasses

class SenderStats(Stats):
    def __init__(self, process, protocol):
        super().__init__(process, protocol)
        self.send_times = {} # seq_num -> send_time
        self.bytes_sent = 0
        self.packets_sent = 0
        self.retransmissions = 0
        self.rtts = [] # time from send to ack for each packet


    def send(self, seq_num, bytes_len):
        now = time.time()
        self.send_times[seq_num] = now
        self.packets_sent += 1
        self.bytes_sent += bytes_len
    
    def ack(self, seq_num):
        now = time.time()
        if seq_num in self.send_times:
            rtt = now - self.send_times.pop(seq_num)
            self.rtts.append(rtt)

    def avg_rtt(self):
        return sum(self.rtts)/len(self.rtts) if self.rtts else 0

    def jitter(self):
        return statistics.stdev(self.rtts) if len(self.rtts) > 1 else 0

    def overhead(self):
        return self.retransmissions / self.packets_sent if self.packets_sent else 0
    
    def record_to_csv(self, filename="sender_stats.csv"):
        if not os.path.exists(filename):
            with open(filename, 'w') as f:
                f.write("process,protocol,status,file_size,total_packets,total_time,connection_time,handshake_attempts,bytes_sent,packets_sent,retransmissions,avg_rtt,jitter,overhead,window_utilization\n")
        with open(filename, 'a') as f:
            total_time = self.end_time - self.start_time if self.start_time and self.end_time else 0
            connection_time = self.connection_time - self.start_time if self.start_time and self.connection_time else 0
            avg_util = sum(self.window_utilization)/len(self.window_utilization) if self.window_utilization else 0
            f.write(f"{self.process},{self.protocol},{self.final_status},{self.file_size},{self.packets},{total_time:.2f},{connection_time:.2f},{self.handshake_attempts},{self.bytes_sent},{self.packets_sent},{self.retransmissions},{self.avg_rtt():.4f},{self.jitter():.4f},{self.overhead():.4f},{avg_util:.4f}\n")



class ReceiverStats(Stats):
    def __init__(self, process, protocol):
        super().__init__(process, protocol)
        self.bytes_received = 0
        self.packets_received = 0
        self.duplicate_packets = 0
        self.file_size = 0

    def recv(self, bytes_len):
        self.bytes_received += bytes_len
        self.packets_received += 1

    def throughput(self):
        duration = self.end_time - self.start_time if self.start_time and self.end_time else 0
        return self.bytes_received / duration if duration > 0 else 0

    def record_to_csv(self, filename="receiver_stats.csv"):
        if not os.path.exists(filename):
            with open(filename, 'w') as f:
                f.write("process,protocol,status,file_size,total_packets,total_time,connection_time,handshake_attempts,bytes_received,packets_received,throughput,window_utilization,duplicate_packets\n")
        with open(filename, 'a') as f:
            total_time = self.end_time - self.start_time if self.start_time and self.end_time else 0
            connection_time = self.connection_time - self.start_time if self.start_time and self.connection_time else 0
            avg_util = sum(self.window_utilization)/len(self.window_utilization) if self.window_utilization else 0
            f.write(f"{self.process},{self.protocol},{self.final_status},{self.file_size},{self.packets},{total_time:.2f},{connection_time:.2f},{self.handshake_attempts},{self.bytes_received},{self.packets_received},{self.throughput():.4f},{avg_util:.4f},{self.duplicate_packets}\n")
