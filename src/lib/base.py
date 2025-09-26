"""
Base classes and utilities for Reliable Data Transfer (RDT) Protocol
Contains abstract classes, packet definitions, enums, and utility functions
"""

import json
import struct
import time
import socket
from abc import ABC, abstractmethod
from enum import Enum
from typing import Tuple, Optional, List

# protocol constants
PACKET_SIZE = 4096  # 4KB packets for better throughput
TIMEOUT = 0.2  # 200ms timeout for better reliability
MAX_RETRIES = 20
WINDOW_SIZE = 20  # smaller window for better reliability with packet loss

# stop & wait specific optimizations
SW_PACKET_SIZE = 8192  # 8KB packets for stop & wait (fewer packets = faster)
SW_TIMEOUT = 0.05  # 50ms timeout for stop & wait (very aggressive)

# timeout constants for critical operations
HANDSHAKE_TIMEOUT = 0.5  # 500ms timeout for INIT/ACCEPT handshake
FIN_TIMEOUT = 0.5  # 500ms timeout for FIN/FIN-ACK handshake

# buffer sizes
ACK_BUFFER_SIZE = 1024  # buffer size for ACK packets
DATA_BUFFER_SIZE = 16384  # buffer size for DATA packets (2x SW_PACKET_SIZE for safety)

# global shutdown flag for graceful termination
_shutdown_requested = False

def request_shutdown():
    """Request graceful shutdown of all RDT operations"""
    global _shutdown_requested
    _shutdown_requested = True

def is_shutdown_requested() -> bool:
    """Check if shutdown has been requested"""
    return _shutdown_requested


class PacketType(Enum):
    """Packet types for RDT protocol"""
    # Data transfer
    DATA = 1
    ACK = 2
    
    # Handshake
    INIT = 3      # Initialize transfer
    ACCEPT = 4    # Accept transfer
    
    # Control
    FIN = 5       # Finish transfer
    ERROR = 6     # Error message
    
    # Legacy (for download - to be implemented)
    REQUEST = 7   # Download request
    
    def __str__(self):
        """Human-readable string representation for logging"""
        return self.name


class Protocol(Enum):
    """Supported RDT protocols"""
    STOP_WAIT = "stop_wait"
    SELECTIVE_REPEAT = "selective_repeat"


class PacketTimer:
    """Timer for individual packets in Selective Repeat protocol"""
    
    def __init__(self, timeout: float = TIMEOUT):
        self.timeout = timeout
        self.start_time = time.time()
    
    def is_expired(self) -> bool:
        """Check if timer has expired"""
        return time.time() - self.start_time > self.timeout
    
    def reset(self):
        """Reset timer"""
        self.start_time = time.time()


class RDTPacket:
    """RDT packet with error detection and metadata"""
    
    def __init__(self, seq_num: int = 0, packet_type: PacketType = PacketType.DATA, 
                 data: bytes = b'', filename: str = '', is_last: bool = False, 
                 ack_num: int = 0, protocol: Optional[Protocol] = None, 
                 session_id: str = '', file_size: int = 0):
        self.seq_num = seq_num
        self.packet_type = packet_type
        self.data = data
        self.filename = filename
        self.is_last = is_last
        self.ack_num = ack_num
        self.protocol = protocol  # protocol for INIT packet
        self.session_id = session_id  # session identifier
        self.file_size = file_size  # file size for INIT packet
        self.checksum = 0
        self.calculate_checksum()
    
    def calculate_checksum(self):
        """Calculate simple checksum (sum of all bytes)"""
        checksum = sum(self.data)
        checksum += self.seq_num + self.packet_type.value + self.ack_num
        checksum += sum(self.filename.encode())
        checksum += int(self.is_last) + self.file_size
        if self.protocol:
            checksum += sum(self.protocol.value.encode())
        if self.session_id:
            checksum += sum(self.session_id.encode())
        self.checksum = checksum % 65536
    
    def verify_checksum(self) -> bool:
        """Verify packet integrity"""
        old_checksum = self.checksum
        self.calculate_checksum()
        is_valid = old_checksum == self.checksum
        self.checksum = old_checksum
        return is_valid
    
    def to_bytes(self) -> bytes:
        """Serialize packet to bytes for transmission"""
        # create header
        header = {
            'seq_num': self.seq_num,
            'type': self.packet_type.value,
            'checksum': self.checksum,
            'filename': self.filename,
            'is_last': self.is_last,
            'ack_num': self.ack_num,
            'data_length': len(self.data),
            'protocol': self.protocol.value if self.protocol else None,
            'session_id': self.session_id,
            'file_size': self.file_size
        }
        
        header_bytes = json.dumps(header).encode()
        header_length = len(header_bytes)
        
        # pack: header_length (4 bytes) + header + data
        return struct.pack('!I', header_length) + header_bytes + self.data
    
    @classmethod
    def from_bytes(cls, data: bytes) -> 'RDTPacket':
        """Deserialize bytes to RDTPacket"""
        if len(data) < 4:
            raise ValueError("Invalid packet: too short")
        
        # extract header length
        header_length = struct.unpack('!I', data[:4])[0]
        
        if len(data) < 4 + header_length:
            raise ValueError("Invalid packet: header incomplete")
        
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
            ack_num=header['ack_num'],
            protocol=Protocol(header['protocol']) if header.get('protocol') else None,
            session_id=header.get('session_id', ''),
            file_size=header.get('file_size', 0)
        )
        packet.checksum = header['checksum']
        
        return packet


class AbstractSender(ABC):
    """Abstract base class for RDT senders"""
    
    def __init__(self, socket: socket.socket, dest_addr: Tuple[str, int], logger):
        self.socket = socket
        self.dest_addr = dest_addr
        self.logger = logger
    
    def send_file(self, filepath: str, filename: str) -> bool:
        """Template method for sending a file"""
        try:
            # validate file (basic, maybe should be more strict or throw an exception to handle)
            if not self._validate_file(filepath):
                return False
            
            # prepare for transfer
            packets = self._prepare_packets(filepath, filename)
            if not packets:
                self.logger.warning("File is empty")
                return True
            
            self.logger.info(f"Starting file transfer: {filename} ({len(packets)} packets)")
            
            # send packets using specific protocol
            result = self._send_packets(packets)
            
            if result:
                self.logger.info("File transfer completed successfully")
            else:
                self.logger.error("File transfer failed")
            
            return result
            
        # TODO: DOWNLOAD IMPLEMENTATION
        # we should add a method to receive downloaded files from server:
        # def receive_downloaded_file(self) -> bytes:
        #     """Receive file after download request - must be implemented by subclasses"""
        #     # 1. Wait for DATA packets from server
        #     # 2. Send ACKs for received packets
        #     # 3. Handle retransmissions and timeouts
        #     # 4. Return complete file data
        #     pass
            
        except FileNotFoundError:
            self.logger.error(f"File not found: {filepath}")
            return False
        except Exception as e:
            self.logger.error(f"Error during file transfer: {e}")
            return False
    
    def _validate_file(self, filepath: str) -> bool:
        """Validate that file exists and is readable"""
        import os
        return os.path.exists(filepath) and os.path.isfile(filepath)
    
    def _prepare_packets(self, filepath: str, filename: str) -> List[RDTPacket]:
        """Prepare packets from file - common logic"""
        packets = []
        
        with open(filepath, 'rb') as file:
            chunk_index = 0
            
            while True:
                chunk = file.read(PACKET_SIZE)
                if not chunk:
                    break
                
                # check if this is the last chunk by trying to read one more byte
                next_byte = file.read(1)
                is_last = len(next_byte) == 0
                
                # if not last, put the byte back
                if not is_last:
                    file.seek(file.tell() - 1)
                
                packet = RDTPacket(
                    seq_num=chunk_index,
                    packet_type=PacketType.DATA,
                    data=chunk,
                    filename=filename if chunk_index == 0 else '',
                    is_last=is_last
                )
                packets.append(packet)
                chunk_index += 1
                
                if is_last:
                    break
        
        return packets
    
    def close_connection(self):
        self.socket.close()
        self.socket = None
    
    ##############
    def send_file_to_client(self, filepath: str, filename: str) -> bool:
        """Template method for sending a file"""
        try:
            # validate file (basic, maybe should be more strict or throw an exception to handle)
            if not self._validate_file(filepath):
                return False
            
            # prepare for transfer
            packets = self._prepare_packets(filepath, filename)
            if not packets:
                self.logger.warning("File is empty")
                return True
            
            self.logger.info(f"Starting file transfer: {filename} ({len(packets)} packets)")
            
            # send packets using specific protocol
            result = self._send_packets(packets)
            
            if result:
                self.logger.info("File transfer completed successfully")
            else:
                self.logger.error("File transfer failed")
            
            return result
            
        # TODO: DOWNLOAD IMPLEMENTATION
        # we should add a method to receive downloaded files from server:
        # def receive_downloaded_file(self) -> bytes:
        #     """Receive file after download request - must be implemented by subclasses"""
        #     # 1. Wait for DATA packets from server
        #     # 2. Send ACKs for received packets
        #     # 3. Handle retransmissions and timeouts
        #     # 4. Return complete file data
        #     pass
            
        except FileNotFoundError:
            self.logger.error(f"File not found: {filepath}")
            return False
        except Exception as e:
            self.logger.error(f"Error during file transfer: {e}")
            return False
    ###########

    @abstractmethod
    def _send_packets(self, packets: List[RDTPacket]) -> bool:
        """Send packets using specific protocol - must be implemented by subclasses"""
        pass

class AbstractReceiver(ABC):
    """Abstract base class for RDT receivers"""
    
    def __init__(self, socket: socket.socket, logger):
        self.socket = socket
        self.logger = logger
    
    @abstractmethod
    def receive_file_with_first_packet(self, first_packet: RDTPacket, addr: Tuple[str, int]) -> Tuple[bool, bytes]:
        """Receive file starting with first packet - must be implemented by subclasses"""
        pass

