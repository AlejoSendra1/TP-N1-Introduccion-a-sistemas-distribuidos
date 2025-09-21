"""
Reliable Data Transfer (RDT) Protocol Implementation
Stop & Wait protocol with error detection and recovery
"""

import json
import hashlib
import struct
import time
import socket
from enum import Enum
from typing import Dict, Any, Tuple, Optional

# protocol constants
PACKET_SIZE = 1024
TIMEOUT = 2.0
MAX_RETRIES = 5

class PacketType(Enum):
    """Enumeration for packet types - using small integers for minimal overhead"""
    DATA = 1
    ACK = 2
    REQUEST = 3  # for download requests
    
    def __str__(self):
        """String representation for logging/debugging"""
        names = {1: "DATA", 2: "ACK", 3: "REQUEST"}
        return names.get(self.value, f"UNKNOWN({self.value})")

class Protocol(Enum):
    """Enumeration for RDT protocols"""
    STOP_WAIT = "stop_wait"
    SELECTIVE_REPEAT = "selective_repeat"

# global flag for graceful shutdown
_shutdown_requested = False

def request_shutdown():
    """Request graceful shutdown of RDT operations"""
    global _shutdown_requested
    _shutdown_requested = True

def is_shutdown_requested():
    """Check if graceful shutdown has been requested"""
    return _shutdown_requested

class RDTPacket:
    """Represents an RDT packet with all necessary fields"""
    
    def __init__(self, seq_num: int, packet_type: PacketType, data: bytes = b'', 
                 filename: str = '', is_last: bool = False, ack_num: int = -1):
        self.seq_num = seq_num
        self.ack_num = ack_num
        self.type = packet_type
        self.data = data
        self.filename = filename
        self.is_last = is_last
        self.checksum = 0
        self.calculate_checksum()
    
    def calculate_checksum(self):
        """Calculate checksum for the packet"""
        # packet dict without checksum
        packet_data = {
            'seq_num': self.seq_num,
            'ack_num': self.ack_num,
            'type': self.type.value,
            'filename': self.filename,
            'is_last': self.is_last,
            'data_length': len(self.data)
        }
        
        # convert packet data to bytes and add data
        packet_bytes = json.dumps(packet_data, sort_keys=True).encode()
        packet_bytes += self.data
        
        # calculate simple checksum
        self.checksum = sum(packet_bytes) % 65536
    
    def verify_checksum(self) -> bool:
        """Verify packet integrity using checksum"""
        original_checksum = self.checksum
        self.calculate_checksum()
        is_valid = original_checksum == self.checksum
        self.checksum = original_checksum  # restore original
        return is_valid
    
    def to_bytes(self) -> bytes:
        """Serialize packet to bytes for transmission"""
        packet_dict = {
            'seq_num': self.seq_num,
            'ack_num': self.ack_num,
            'type': self.type.value,
            'checksum': self.checksum,
            'filename': self.filename,
            'is_last': self.is_last,
            'data_length': len(self.data)
        }
        
        # convert header to JSON and encode
        header = json.dumps(packet_dict).encode()
        header_length = struct.pack('!I', len(header))
        
        # combine header length + header + data
        return header_length + header + self.data
    
    @classmethod
    def from_bytes(cls, data: bytes) -> 'RDTPacket':
        """Deserialize packet from bytes"""
        # extract header length
        header_length = struct.unpack('!I', data[:4])[0]
        
        # extract header
        header_bytes = data[4:4+header_length]
        header = json.loads(header_bytes.decode())
        
        # extract packet data
        packet_data = data[4+header_length:4+header_length+header['data_length']]
        
        # create packet
        packet = cls(
            seq_num=header['seq_num'],
            packet_type=PacketType(header['type']),
            data=packet_data,
            filename=header['filename'],
            is_last=header['is_last'],
            ack_num=header['ack_num']
        )
        packet.checksum = header['checksum']
        
        return packet


class RDTSender:
    """RDT sender implementation with Stop & Wait protocol"""
    
    def __init__(self, socket: socket.socket, dest_addr: Tuple[str, int], logger):
        self.socket = socket
        self.dest_addr = dest_addr
        self.logger = logger
        self.seq_num = 0
        self.socket.settimeout(TIMEOUT)
    
    def send_file(self, filepath: str, filename: str) -> bool:
        """Send a file using Stop & Wait protocol"""
        try:
            with open(filepath, 'rb') as file:
                self.logger.info(f"Starting file transfer: {filename}")
                
                # send first packet to establish connection
                first_chunk = file.read(PACKET_SIZE)
                if not first_chunk:
                    self.logger.warning("File is empty")
                    return True
                
                is_last_first = len(first_chunk) < PACKET_SIZE
                first_packet = RDTPacket(
                    seq_num=self.seq_num,
                    packet_type=PacketType.DATA,
                    data=first_chunk,
                    filename=filename,
                    is_last=is_last_first
                )
                
                # send first packet
                if not self._send_packet_reliable(first_packet):
                    return False
                
                if is_last_first:
                    self.logger.info("File transfer completed successfully")
                    return True
                
                # alternate sequence number for next packet
                self.seq_num = 1 - self.seq_num
                
                # continue with rest of file
                while True:
                    # check for shutdown request
                    if is_shutdown_requested():
                        self.logger.info("Upload cancelled due to shutdown request")
                        return False
                    
                    chunk = file.read(PACKET_SIZE)
                    if not chunk:
                        break
                    
                    is_last = len(chunk) < PACKET_SIZE
                    packet = RDTPacket(
                        seq_num=self.seq_num,
                        packet_type=PacketType.DATA,
                        data=chunk,
                        is_last=is_last
                    )
                    
                    if self._send_packet_reliable(packet):
                        self.logger.debug(f"Packet {self.seq_num} sent successfully")
                        self.seq_num = 1 - self.seq_num
                        
                        if is_last:
                            break
                    else:
                        self.logger.error(f"Failed to send packet {self.seq_num}")
                        return False
                
                self.logger.info("File transfer completed successfully")
                return True
                
        except FileNotFoundError:
            self.logger.error(f"File not found: {filepath}")
            return False
        except Exception as e:
            self.logger.error(f"Error during file transfer: {e}")
            return False
    
    
    def _send_packet_reliable(self, packet: RDTPacket) -> bool:
        """Send packet with retransmission on timeout"""
        for attempt in range(MAX_RETRIES):
            # check for shutdown request
            if is_shutdown_requested():
                self.logger.info("Packet transmission cancelled due to shutdown request")
                return False
            
            try:
                # send packet
                self.socket.sendto(packet.to_bytes(), self.dest_addr)
                self.logger.debug(f"Sent packet {packet.seq_num}, attempt {attempt + 1}")
                
                # wait for ACK
                while True:
                    # check for shutdown request during ACK wait
                    if is_shutdown_requested():
                        self.logger.info("ACK wait cancelled due to shutdown request")
                        return False
                    
                    try:
                        ack_data, addr = self.socket.recvfrom(4096)
                        ack_packet = RDTPacket.from_bytes(ack_data)
                        
                        # verify ACK
                        if (ack_packet.type == PacketType.ACK and 
                            ack_packet.ack_num == packet.seq_num and
                            ack_packet.verify_checksum()):
                            self.logger.debug(f"Received valid ACK for packet {packet.seq_num}")
                            return True
                        else:
                            self.logger.debug(f"Received invalid ACK: expected {packet.seq_num}, got {ack_packet.ack_num}")
                            # continue waiting for correct ACK
                            
                    except socket.timeout:
                        self.logger.debug(f"Timeout waiting for ACK {packet.seq_num}")
                        break  # retry sending
                        
            except Exception as e:
                if not is_shutdown_requested():
                    self.logger.error(f"Error sending packet: {e}")
                return False
        
        self.logger.error(f"Failed to send packet {packet.seq_num} after {MAX_RETRIES} attempts")
        return False


class RDTReceiver:
    """RDT receiver implementation with Stop & Wait protocol"""
    
    def __init__(self, socket: socket.socket, logger):
        self.socket = socket
        self.logger = logger
        self.expected_seq = 0
    
    def receive_file_with_first_packet(self, storage_dir: str, first_packet: 'RDTPacket', first_addr) -> Optional[str]:
        """Receive a file using Stop & Wait protocol, starting with an already received packet"""
        filename = None
        file_data = b''
        
        try:
            # process the first packet that was already received
            packet = first_packet
            addr = first_addr
            
            # verify checksum
            if not packet.verify_checksum():
                self.logger.debug(f"Corrupted first packet received, aborting")
                return None
            
            # process first packet (should be seq 0)
            if packet.seq_num == self.expected_seq:
                if packet.filename:  # first packet contains filename
                    filename = packet.filename
                    self.logger.info(f"Receiving file: {filename}")
                
                file_data += packet.data
                self.logger.debug(f"Received packet {packet.seq_num}")
                
                # send ACK
                ack = RDTPacket(
                    seq_num=0,  # not used in ACK
                    packet_type=PacketType.ACK,
                    ack_num=packet.seq_num
                )
                self.socket.sendto(ack.to_bytes(), addr)
                self.logger.debug(f"Sent ACK for packet {packet.seq_num}")
                
                # update expected sequence number
                self.expected_seq = 1 - self.expected_seq
                
                # check if this was the only packet
                if packet.is_last:
                    # save file
                    if filename:
                        import os
                        filepath = os.path.join(storage_dir, filename)
                        with open(filepath, 'wb') as f:
                            f.write(file_data)
                        self.logger.info(f"File saved: {filepath}")
                        return filepath
                    return None
            
            # continue receiving remaining packets
            return self._continue_receiving(storage_dir, filename, file_data)
            
        except Exception as e:
            self.logger.error(f"Error receiving file: {e}")
            return None
    
    def _continue_receiving(self, storage_dir: str, filename: str, file_data: bytes) -> Optional[str]:
        """Continue receiving packets after the first one"""
        try:
            while True:
                # receive packet
                packet_data, addr = self.socket.recvfrom(4096)
                packet = RDTPacket.from_bytes(packet_data)
                
                # verify checksum
                if not packet.verify_checksum():
                    self.logger.debug(f"Corrupted packet received, ignoring")
                    continue
                
                # check sequence number if it is correct
                if packet.seq_num == self.expected_seq:
                    # correct packet
                    file_data += packet.data
                    self.logger.debug(f"Received packet {packet.seq_num}")
                    
                    # send ACK
                    ack = RDTPacket(
                        seq_num=0,  # not used in ACK
                        packet_type=PacketType.ACK,
                        ack_num=packet.seq_num
                    )
                    self.socket.sendto(ack.to_bytes(), addr)
                    self.logger.debug(f"Sent ACK for packet {packet.seq_num}")
                    
                    # update expected sequence number
                    self.expected_seq = 1 - self.expected_seq
                    
                    # check if last packet
                    if packet.is_last:
                        break
                        
                else:
                    # duplicate or out-of-order packet
                    self.logger.debug(f"Unexpected packet {packet.seq_num}, expected {self.expected_seq}")
                    
                    # send ACK for previous packet (duplicate ACK)
                    prev_seq = 1 - self.expected_seq
                    ack = RDTPacket(
                        seq_num=0,
                        packet_type=PacketType.ACK,
                        ack_num=prev_seq
                    )
                    self.socket.sendto(ack.to_bytes(), addr)
                    self.logger.debug(f"Sent duplicate ACK for packet {prev_seq}")
            
            # save file
            if filename:
                import os
                filepath = os.path.join(storage_dir, filename)
                with open(filepath, 'wb') as f:
                    f.write(file_data)
                self.logger.info(f"File saved: {filepath}")
                return filepath
            
        except Exception as e:
            self.logger.error(f"Error continuing file reception: {e}")
            return None

    def receive_file(self, storage_dir: str) -> Optional[str]:
        """Receive a file using Stop & Wait protocol"""
        filename = None
        file_data = b''
        
        try:
            while True:
                # receive packet
                packet_data, addr = self.socket.recvfrom(4096)
                packet = RDTPacket.from_bytes(packet_data)
                
                # verify checksum
                if not packet.verify_checksum():
                    self.logger.debug(f"Corrupted packet received, ignoring")
                    continue
                
                # check sequence number if it is correct
                if packet.seq_num == self.expected_seq:
                    # correct packet
                    if packet.filename:  # first packet contains filename
                        filename = packet.filename
                        self.logger.info(f"Receiving file: {filename}")
                    
                    file_data += packet.data
                    self.logger.debug(f"Received packet {packet.seq_num}")
                    
                    # send ACK
                    ack = RDTPacket(
                        seq_num=0,  # not used in ACK
                        packet_type=PacketType.ACK,
                        ack_num=packet.seq_num
                    )
                    self.socket.sendto(ack.to_bytes(), addr)
                    self.logger.debug(f"Sent ACK for packet {packet.seq_num}")
                    
                    # update expected sequence number
                    self.expected_seq = 1 - self.expected_seq
                    
                    # check if last packet
                    if packet.is_last:
                        break
                        
                else:
                    # duplicate or out-of-order packet
                    self.logger.debug(f"Unexpected packet {packet.seq_num}, expected {self.expected_seq}")
                    
                    # send ACK for previous packet (duplicate ACK)
                    prev_seq = 1 - self.expected_seq
                    ack = RDTPacket(
                        seq_num=0,
                        packet_type=PacketType.ACK,
                        ack_num=prev_seq
                    )
                    self.socket.sendto(ack.to_bytes(), addr)
                    self.logger.debug(f"Sent duplicate ACK for packet {prev_seq}")
            
            # save file
            if filename:
                import os
                filepath = os.path.join(storage_dir, filename)
                with open(filepath, 'wb') as f:
                    f.write(file_data)
                self.logger.info(f"File saved: {filepath}")
                return filepath
            
        except Exception as e:
            self.logger.error(f"Error receiving file: {e}")
            return None
