"""
Base classes and utilities for Reliable Data Transfer (RDT) Protocol
Contains abstract classes, packet definitions, enums, and utility functions
"""

import queue
import struct
import time
import socket
from socket import timeout
from abc import ABC, abstractmethod
from enum import Enum
from typing import Tuple, Optional, List

# protocol constants
PACKET_SIZE = 4096  # 4KB packets for better throughput
TIMEOUT = 0.2  # 200ms timeout for better reliability
MAX_RETRIES = 20
WINDOW_SIZE = 20  # smaller window for better reliability with packet loss

# stop & wait specific optimizations
SW_PACKET_SIZE = 4096  # 8KB packets for stop & wait (fewer packets = faster)
SW_TIMEOUT = 0.05  # 50ms timeout for stop & wait (very aggressive)

# timeout constants for critical operations
HANDSHAKE_TIMEOUT = 1 # 1s timeout for INIT/ACCEPT handshake
FIN_TIMEOUT = 1  # 1s timeout for FIN/FIN-ACK handshake
DUPLICATED_FIN_TIMEOUT = 5 # 5s timeout for duplicated FIN
FIRST_DATA_PACKET_TIMEOUT = 5.0  # 5s timeout for first DATA packet

# packet structure constants
HEADER_SIZE = 23  # fixed header size in bytes

# buffer sizes
ACK_BUFFER_SIZE = 1024  # buffer size for ACK packets
DATA_BUFFER_SIZE = HEADER_SIZE + PACKET_SIZE  # buffer size for DATA packets (Selective Repeat)
SW_DATA_BUFFER_SIZE = HEADER_SIZE + SW_PACKET_SIZE  # buffer size for DATA packets (Stop & Wait)
INIT_PACKET_SIZE = 1024  # buffer size for INIT packets

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
    FIN_ACK = 8   # Acknowledge FIN
    ERROR = 6     # Error message
    
    # Legacy (for download - to be implemented)
    REQUEST = 7   # Download request
    
    def __str__(self):
        """Human-readable string representation for logging"""
        return self.name


class Protocol(Enum):
    """Supported RDT protocols"""
    STOP_WAIT = 1
    SELECTIVE_REPEAT = 2
    
    def __str__(self):
        """String representation for logging"""
        if self == Protocol.STOP_WAIT:
            return "stop_wait"
        elif self == Protocol.SELECTIVE_REPEAT:
            return "selective_repeat"
        else:
            return "unknown"
    
    @classmethod
    def from_string(cls, protocol_str: str) -> 'Protocol':
        """Convert string representation to Protocol enum"""
        if protocol_str == "stop_wait":
            return cls.STOP_WAIT
        elif protocol_str == "selective_repeat":
            return cls.SELECTIVE_REPEAT
        else:
            raise ValueError(f"Unknown protocol: {protocol_str}")


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
                 data: bytes = b'', filename: str = None, 
                 ack_num: int = 0, protocol: Optional[Protocol] = None, 
                 session_id: str = '', file_size: int = 0):
        self.seq_num = seq_num
        self.packet_type = packet_type
        self.data = data
        self.filename = filename
        self.ack_num = ack_num
        self.protocol = protocol  # protocol for INIT packet
        self.session_id = session_id  # session identifier
        self.file_size = file_size  # file size for INIT packet
        self.checksum = 0
        self.calculate_checksum()
    
    def calculate_checksum(self):
        """Calculate simple checksum (sum of all bytes)"""
        checksum = 0
        
        # packet data
        if self.data:
            checksum += sum(self.data)
        
        checksum += self.seq_num + self.packet_type.value + self.ack_num
        checksum += self.file_size
        
        # filename if exists
        if self.filename:
            checksum += sum(self.filename.encode('utf-8'))
        
        if self.protocol:
            checksum += self.protocol.value
        
        if self.session_id:
            checksum += sum(self.session_id.encode('utf-8'))
        
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
        # prepare payload according to packet type
        if self.packet_type == PacketType.INIT:
            # INIT: payload = filename as bytes
            payload = self.filename.encode('utf-8') if self.filename else b''
        else:
            # DATA/ACK/FIN/etc: payload = data
            payload = self.data
        
        # prepare session_id as single byte (0-255)
        # for INIT packets, the session_id is 0 (assigned by the server)
        if self.packet_type == PacketType.INIT:
            session_id_byte = 0  # empty for INIT
        else:
            # convert session_id string to integer (0-255)
            try:
                session_id_byte = int(self.session_id) if self.session_id else 0
            except (ValueError, TypeError) as e:
                session_id_byte = 0
        
        # fixed binary header: 23 bytes
        header_bytes = struct.pack(
            '!IIIIIBBB',
            self.seq_num,             # I (4 bytes)
            self.checksum,            # I (4 bytes)
            self.ack_num,             # I (4 bytes)
            len(payload),             # I (4 bytes) - payload length
            self.file_size,           # I (4 bytes)
            self.packet_type.value,   # B (1 byte)
            self.protocol.value if self.protocol else 0,  # B (1 byte)
            session_id_byte           # B (1 byte) - session ID (0-255)
        )
        
        return header_bytes + payload
    
    @classmethod
    def from_bytes(cls, data: bytes) -> 'RDTPacket':
        """Deserialize bytes to RDTPacket"""
        # Fixed header defined as constant
        
        
        if len(data) < HEADER_SIZE:
            raise ValueError(f"Invalid packet: too short (expected {HEADER_SIZE}, got {len(data)})")
        
        # extract fixed header
        header_bytes = data[:HEADER_SIZE]
        header = struct.unpack('!IIIIIBBB', header_bytes)
        
        # parse fields from header
        seq_num = header[0]
        checksum = header[1]
        ack_num = header[2]
        payload_length = header[3]
        file_size = header[4]
        packet_type = PacketType(header[5])
        protocol_value = header[6]
        session_id_byte = header[7]
        
        # convert session_id from byte to string
        session_id = str(session_id_byte) if session_id_byte != 0 else ''
        protocol = Protocol(protocol_value) if protocol_value != 0 else None
        

        # extract payload
        if len(data) < HEADER_SIZE + payload_length:
            raise ValueError("Invalid packet: payload incomplete")
        
        payload = data[HEADER_SIZE:HEADER_SIZE + payload_length]
        
        # intepret payload according to packet type
        if packet_type == PacketType.INIT:
            # INIT: payload = filename
            filename = payload.decode('utf-8') if payload else ''
            packet_data = b''
        else:
            # DATA/ACK/FIN/etc: payload = data
            filename = ''
            packet_data = payload
        
        packet = cls(
            seq_num=seq_num,
            packet_type=packet_type,
            data=packet_data,
            filename=filename,
            ack_num=ack_num,
            protocol=protocol,
            session_id=session_id,
            file_size=file_size
        )
        
        # Set checksum (no recalculate)
        packet.checksum = checksum
        
        return packet


def wait_for_init_packet(sock: socket.socket, timeout: Optional[float] = None) -> Optional[Tuple[RDTPacket, Tuple[str, int]]]:
    """
    Wait for and receive an INIT packet from any client
    
    Args:
        sock: Socket to listen on
        timeout: Optional timeout in seconds
        
    Returns:
        Tuple[RDTPacket, client_addr] or None if timeout/error/no INIT packet
    """
    sock.settimeout(None) # timeout ccleanup
    
    try:
        data, addr = sock.recvfrom(INIT_PACKET_SIZE)  # INIT packets are small; TODO: maybe use a smaller buffer size for INIT packets (because file name cannot be that large)
        packet = RDTPacket.from_bytes(data) 
        
        if packet.packet_type == PacketType.INIT:
            return packet, addr
        else:
            return None  # Not an INIT packet
            
    except Exception as e:
        return None


class AbstractSender(ABC):
    """Abstract base class for RDT senders"""
    
    def __init__(self, socket: socket.socket, dest_addr: Tuple[str, int], logger):
        self.socket = socket
        self.dest_addr = dest_addr
        self.logger = logger
        self.filename = None  # stored for handshake
    
    def send_file(self, filepath: str, filename: str) -> bool:
        """Template method for sending a file"""
        try:
            # validate file (basic, maybe should be more strict or throw an exception to handle)
            if not self._validate_file(filepath):
                return False
            
            # store filename for handshake
            self.filename = filename
            
            # prepare for transfer (only DATA packets)
            packets = self._prepare_packets(filepath)
            if not packets:
                self.logger.warning(f"File {filepath} is empty")
                return True
            
            self.logger.info(f"Starting file transfer: {filename} ({len(packets)} packets)")
            
            # send packets using specific protocol
            result = self._send_packets(packets)
            
            if result:
                self.logger.info("File transfer completed successfully")
            else:
                self.logger.error("File transfer failed")
            
            return result
            
        except FileNotFoundError as e:
            self.logger.error(f"File not found: {filepath}")
            return False
        except Exception as e:
            self.logger.error(f"Error during file transfer: {e}")
            return False
    
    def _validate_file(self, filepath: str) -> bool:
        """Validate that file exists and is readable"""
        import os
        return os.path.exists(filepath) and os.path.isfile(filepath)
    
    def _prepare_packets(self, filepath: str) -> List[RDTPacket]:
        """Prepare DATA packets from file data (no INIT packet)"""
        packets = []
        
        with open(filepath, 'rb') as file:
            chunk_index = 0
            
            while True:
                chunk = file.read(PACKET_SIZE)
                if not chunk:
                    break
                
                packet = RDTPacket(
                    seq_num=chunk_index,
                    packet_type=PacketType.DATA,
                    data=chunk
                )
                packets.append(packet)
                chunk_index += 1
        
        return packets
    
    def close_connection(self):
        self.socket.close()
        self.socket = None

    def perform_handshake(self, filename: str, file_size: int) -> bool:
        """Perform handshake with server"""
        # # Create INIT packet
        # init_packet = RDTPacket(
        #     packet_type=PacketType.INIT,
        #     filename=filename,
        #     file_size=file_size,
        #     protocol=Protocol.STOP_WAIT
        # )
        
        # # longer timeout for handshake
        # original_timeout = self.socket.gettimeout()
        # self.socket.settimeout(HANDSHAKE_TIMEOUT)
        
        # for attempt in range(MAX_RETRIES):
        #     if is_shutdown_requested():
        #         self.socket.settimeout(original_timeout)
        #         return False
                
        #     try:
        #         # Send INIT
        #         self.socket.sendto(init_packet.to_bytes(), self.dest_addr)
        #         self.logger.debug(f"Sent INIT packet (attempt {attempt + 1})")
                
        #         # Wait for ACCEPT
        #         accept_data, addr = self.socket.recvfrom(ACK_BUFFER_SIZE)
        #         accept_packet = RDTPacket.from_bytes(accept_data)
                
        #         if (accept_packet.packet_type == PacketType.ACCEPT and 
        #             accept_packet.session_id and 
        #             accept_packet.verify_checksum()):
                    
        #             self.session_id = accept_packet.session_id
        #             self.logger.info(f"Handshake successful, session ID: {self.session_id}")
        #             self.socket.settimeout(original_timeout)
        #             return True
                    
        #     except timeout:
        #         self.logger.debug(f"Timeout waiting for ACCEPT, retrying...")
        #     except Exception as e:
        #         self.logger.error(f"Error during handshake: {e}")
        #         self.socket.settimeout(original_timeout)
        #         return False
                
        # self.logger.error("Failed to establish session")
        # self.socket.settimeout(original_timeout)
        # return False
        pass

    @abstractmethod
    def _send_packets(self, packets: List[RDTPacket]) -> bool:
        """Send packets using specific protocol - must be implemented by subclasses"""
        pass

class AbstractReceiver(ABC):
    """Abstract base class for RDT receivers"""
    
    def __init__(self, socket: socket.socket, logger):
        self.socket = socket
        self.logger = logger

    def receive_file(self, client_addr: Tuple[str, int], session_id: str, bytes_received: queue.Queue) -> Tuple[bool, bytes]:
        """
        Receive complete file from client
        Handles first packet reception, validation, and delegates to subclass
        
        Args:
            client_addr: Expected client address
            session_id: Expected session ID
            
        Returns:
            Tuple[bool, bytes]: (success, file_data)
        """
        try:
            # wait for first DATA packet
            self.socket.settimeout(FIRST_DATA_PACKET_TIMEOUT)
            data, addr = self.socket.recvfrom(SW_DATA_BUFFER_SIZE) # use largest buffer size to support both protocols
            
            #self.logger.error(f"Packet from unexpected address: {addr}")

            # validate source (only check host, not port - OS may assign different port when client is reconnecting)
            if addr[0] != client_addr[0]:
                self.logger.error(f"Packet from unexpected host: {addr[0]} (expected {client_addr[0]})")
                return False, b''
                
            first_packet = RDTPacket.from_bytes(data)
            
            # validate session
            if first_packet.session_id != session_id:
                self.logger.error(f"Invalid session ID: {first_packet.session_id} - expected: {session_id}")
                return False, b''
            
            # delegate to subclass implementation
            return self.receive_file_with_first_packet(first_packet, addr, bytes_received) # TODO: do not separate first packet reception from the rest of the file !!!!
            
        except timeout as e:
            self.logger.error("Timeout waiting for first DATA packet")
            return False, b''
        except Exception as e:
            self.logger.error(f"Error receiving first packet in session {session_id}: {e}")
            return False, b''
    
    @abstractmethod
    def receive_file_with_first_packet(self, first_packet: RDTPacket, addr: Tuple[str, int], bytes_received: queue.Queue) -> Tuple[bool, bytes]:
        """Receive file starting with first packet - must be implemented by subclasses"""
        pass

    def _handle_fin(self, fin_packet: RDTPacket, addr: Tuple[str, int]) -> bool:
        self.logger.debug("esperando fin")
        fin_ack = RDTPacket(
            packet_type=PacketType.FIN_ACK,
            session_id= fin_packet.session_id if hasattr(fin_packet, 'session_id') and fin_packet.session_id else ''
        )
        self.socket.sendto(fin_ack.to_bytes(), addr)
        for i in range(MAX_RETRIES):
            try:
                # wait for duplicated FIN packet with timeout
                self.socket.settimeout(DUPLICATED_FIN_TIMEOUT)
                data, rcv_addr = self.socket.recvfrom(DATA_BUFFER_SIZE)
                packet = RDTPacket.from_bytes(data)
                if (packet.packet_type == PacketType.FIN and
                        fin_packet.session_id == packet.session_id and
                        addr == rcv_addr):

                    # send FIN ACK
                    self.socket.sendto(fin_ack.to_bytes(), addr)
                    self.logger.info(f"Session {fin_packet.session_id} resending FIN ACK")

                else:
                    self.logger.warning(
                        f"Invalid FIN packet from {addr}, expected: {PacketType.FIN},{fin_packet.session_id},{addr}  received: {packet.packet_type},{packet.session_id},{rcv_addr}")

            except timeout:
                self.logger.debug("No duplicated FIN received before timeout, finishing session")
                return True
            except Exception as e:
                self.logger.error(f"Error handling FIN: {e}")
                return False
        self.logger.warning(f"Fin retries limit reached, forcibly ending the session")
        return False
