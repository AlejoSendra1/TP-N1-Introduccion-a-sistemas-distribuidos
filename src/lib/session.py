"""
Session management for RDT protocols
Handles handshake and file transfers
"""
import argparse
import os
import socket
import sys
import uuid
from typing import Tuple, Optional
from .base import RDTPacket, PacketType, Protocol, DATA_BUFFER_SIZE
from .factory import create_receiver, create_sender


class RDTSession:
    """
    Manages a complete RDT file transfer session
    Handles handshake and delegates to appropriate receiver
    """
    
    def __init__(self, sock: socket.socket, logger):
        self.sock = sock
        self.logger = logger
        self.session_id = None
        self.client_addr = None
        self.protocol = None
        self.filename = None
        self.file_size = None
        
    def accept_transfer(self, init_packet: RDTPacket, client_addr: Tuple[str, int]) -> bool:
        """
        Accept an incoming transfer request
        Performs handshake and prepares for transfer
        
        Returns:
            bool: True if handshake successful
        """
        # Validate INIT packet
        if init_packet.packet_type != PacketType.INIT:
            self.logger.error("Invalid packet type for session start")
            return False
            
        # Store session information
        self.client_addr = client_addr
        self.protocol = init_packet.protocol
        self.filename = init_packet.filename
        self.file_size = init_packet.file_size
        self.session_id = str(uuid.uuid4())
        
        self.logger.info(f"Accepting transfer for {self.filename} using {self.protocol.value}")
        
        # Send ACCEPT with session ID
        accept = RDTPacket(
            packet_type=PacketType.ACCEPT,
            session_id=self.session_id
        )
        
        try:
            self.sock.sendto(accept.to_bytes(), client_addr)
            self.logger.debug(f"Sent ACCEPT with session ID: {self.session_id}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to send ACCEPT: {e}")
            return False
    
    def receive_file(self) -> Tuple[bool, bytes]:
        """
        Receive the file after handshake
        
        Returns:
            Tuple[bool, bytes]: (success, file_data)
        """
        if not self.session_id:
            self.logger.error("No active session")
            return False, b''
            
        receiver = create_receiver(self.protocol, self.sock, self.logger)
        
        try:
            # wait for first DATA packet
            self.sock.settimeout(5.0)
            data, addr = self.sock.recvfrom(DATA_BUFFER_SIZE)
            
            # validate source
            if addr != self.client_addr:
                self.logger.error(f"Packet from unexpected address: {addr}")
                return False, b''
                
            first_packet = RDTPacket.from_bytes(data)
            
            # validate session
            if first_packet.session_id != self.session_id:
                self.logger.error(f"Invalid session ID: {first_packet.session_id}")
                return False, b''
                
            # let receiver handle the rest
            success, file_data = receiver.receive_file_with_first_packet(first_packet, self.client_addr)
            
            return success, file_data
            
        except socket.timeout:
            self.logger.error("Timeout waiting for first DATA packet")
            return False, b''
        except Exception as e:
            self.logger.error(f"Error receiving file: {e}")
            return False, b''
    
    def _handle_fin(self):
        """Handle FIN packet and send FIN ACK"""
        self.logger.debug("esperando fin")
        try:
            # wait for FIN packet with timeout
            self.sock.settimeout(5.0)
            data, addr = self.sock.recvfrom(DATA_BUFFER_SIZE)
            fin_packet = RDTPacket.from_+bytes(data)
            
            if (fin_packet.packet_type == PacketType.FIN and 
                fin_packet.session_id == self.session_id and
                addr == self.client_addr):
                
                # send FIN ACK
                fin_ack = RDTPacket(
                    packet_type=PacketType.ACK,
                    session_id=self.session_id
                )
                self.sock.sendto(fin_ack.to_bytes(), addr)
                self.logger.info(f"Session {self.session_id} closed with FIN/FIN-ACK")
                
                # clean up session after successful FIN ACK
                self.session_id = None
                self.client_addr = None
                self.protocol = None
                self.filename = None
                self.file_size = None
            else:
                self.logger.warning(f"Invalid FIN packet from {addr}, expected: {PacketType.FIN},{self.session_id},{self.client_addr}  received: {fin_packet.packet_type},{fin_packet.session_id},{addr}")
                
        except socket.timeout:
            self.logger.warning("No FIN received, session may be incomplete")
        except Exception as e:
            self.logger.error(f"Error handling FIN: {e}")
    
    def reject_transfer(self, client_addr: Tuple[str, int], reason: str = "Transfer rejected"):
        """Send rejection/error response"""
        error = RDTPacket(
            packet_type=PacketType.ERROR,
            data=reason.encode()
        )
        try:
            self.sock.sendto(error.to_bytes(), client_addr)
        except Exception as e:
            self.logger.error(f"Failed to send rejection: {e}")

    def send_file(self,source):
        sender = create_sender(self.protocol , self.sock, self.client_addr, self.logger)

        if sender.send_file(source, self.filename, self.session_id):
            self.logger.info("File uploaded successfully")
        else:
            self.logger.error("File upload failed")
            sys.exit(1)


class RDTServer:
    """
    High-level RDT server interface
    Handles the protocol completely, server just needs to save files
    
    TODO: DOWNLOAD IMPLEMENTATION
    Extend to handle download requests:
    1. Detect transfer type in wait_for_transfer():
       - UPLOAD: init_packet.file_size > 0
       - DOWNLOAD: init_packet.file_size == 0 (BETTER IF PACKET TYPE IS = PacketType.REQUEST)
    2. Return DownloadRequest for download requests
    3. Create DownloadRequest class similar to TransferRequest
    """
    
    def __init__(self, sock: socket.socket, logger):
        self.sock = sock
        self.logger = logger
        
    def wait_for_transfer(self, timeout: Optional[float] = None) -> Optional['TransferRequest']:
        """
        Wait for an incoming transfer request
        
        Returns:
            TransferRequest object or None if timeout/error

        """
        if timeout:
            self.sock.settimeout(timeout)
            
        try:
            data, addr = self.sock.recvfrom(DATA_BUFFER_SIZE)
            packet = RDTPacket.from_bytes(data)
            
            if packet.packet_type == PacketType.INIT:
                # TODO: DOWNLOAD IMPLEMENTATION
                # Detect transfer type based on file_size:
                if packet.file_size == 0:
                    self.logger.info('devolviendo download req en wait for transfer') ##sacar
                    return DownloadRequest(self.sock, self.logger, packet, addr)
                else:
                    self.logger.info('devolviendo transfer req en wait for transfer')##sacar
                    return TransferRequest(self.sock, self.logger, packet, addr)
                
            else:
                self.logger.debug(f"Ignoring non-INIT packet: {packet.packet_type}")
                return None
                
        except socket.timeout:
            return None
        except Exception as e:
            self.logger.error(f"Error waiting for transfer: {e}")
            return None
    
    @staticmethod
    def extract_session_id(packet_data: bytes) -> Optional[str]:
        """
        Extract session ID from raw packet data without full parsing
        Useful for future concurrent server implementations to route packets
        
        Args:
            packet_data: Raw packet bytes
            
        Returns:
            Session ID or None if packet doesn't contain one
        """
        try:
            # Quick extraction without full validation
            # Session ID is at a fixed offset in the packet structure
            packet = RDTPacket.from_bytes(packet_data)
            return packet.session_id
        except Exception:
            return None


class TransferRequest:
    """
    Represents an incoming transfer request
    Provides simple interface for server to accept/reject
    
    """
    
    def __init__(self, sock: socket.socket, logger, init_packet: RDTPacket, client_addr: Tuple[str, int]):
        self.sock = sock
        self.logger = logger
        self.init_packet = init_packet
        self.client_addr = client_addr
        self.session = RDTSession(sock, logger)
        self._session_id = None  # cache session ID after handshake
        
    @property
    def filename(self) -> str:
        return self.init_packet.filename
        
    @property
    def file_size(self) -> int:
        return self.init_packet.file_size
        
    @property
    def protocol(self) -> Protocol:
        return self.init_packet.protocol
        
    @property
    def source_address(self) -> Tuple[str, int]:
        return self.client_addr
        
    def accept(self) -> Optional[Tuple[bool, bytes]]:
        """
        Accept the transfer and receive the file
        
        Returns:
            Tuple[bool, bytes] or None if handshake fails
        """
        self.logger.info("a punto de aceptar el transfer") ###

        if self.session.accept_transfer(self.init_packet, self.client_addr):
            self._session_id = self.session.session_id  # cache for future use
            self.logger.info("se acepto el transfer") ###
            return self.session.receive_file()
        return None
    
    def get_session_id(self) -> Optional[str]:
        """
        Get the session ID after acceptance
        Useful for future concurrent server implementations
        
        Returns:
            Session ID or None if not yet accepted
        """
        return self._session_id
        
    def reject(self, reason: str = "Transfer rejected"):
        """Reject the transfer request"""
        self.session.reject_transfer(self.client_addr, reason)

    @staticmethod
    def extract_session_id(packet_data: bytes) -> Optional[str]:
        """
        Extract session ID from raw packet data without full parsing
        Useful for future concurrent server implementations to route packets
        
        Args:
            packet_data: Raw packet bytes
            
        Returns:
            Session ID or None if packet doesn't contain one
        """
        try:
            # Quick extraction without full validation
            # Session ID is at a fixed offset in the packet structure
            packet = RDTPacket.from_bytes(packet_data)
            return packet.session_id
        except Exception:
            return None


class DownloadRequest:
    """
    Represents an incoming download request
    Provides simple interface for server to accept/reject and send files
    
    Similar to TransferRequest but for download - server acts as sender

        TODO: DOWNLOAD IMPLEMENTATION
    create similar DownloadRequest class:
    class DownloadRequest:
        def __init__(self, sock, logger, init_packet, client_addr):
            # Similar to TransferRequest but for download
        
        def accept(self, filepath: str) -> bool:
            # 1) perform handshake (INIT -> ACCEPT)
            # 2) create sender using factory.create_sender()
            # 3) send file using sender.send_file(filepath, filename)
            # 4) handle FIN/FIN-ACK
            # 5) return success/failure
    """
    
    def __init__(self, sock: socket.socket, logger, init_packet: RDTPacket, client_addr: Tuple[str, int]):
        self.sock = sock
        self.logger = logger
        self.init_packet = init_packet
        self.client_addr = client_addr
        self.session = RDTSession(sock, logger)
        self._session_id = None  # cache session ID after handshake
        
    @property
    def filename(self) -> str:
        """The filename requested by the client"""
        return self.init_packet.filename
        
    @property
    def protocol(self) -> Protocol:
        """The protocol requested by the client"""
        return self.init_packet.protocol
        
    @property
    def source_address(self) -> Tuple[str, int]:
        """The client's address"""
        return self.client_addr
        
    def accept(self, filepath: str) -> bool:
        """
        Do the handshake and set up for receiving incoming bytes
        
        Args:
            filepath: Local path to the file to send
        
        Returns:
            True if file was sent successfully, False otherwise
        """
        if self.session.accept_transfer(self.init_packet, self.client_addr):
            self._session_id = self.session.session_id  # cache for future use
            self.session.send_file(filepath)
            return True
        return False
        
    
    def get_session_id(self) -> Optional[str]:
        """
        Get the session ID after acceptance
        Useful for future concurrent server implementations
        
        Returns:
            Session ID or None if not yet accepted
        """
        return self._session_id
        
    def reject(self, reason: str = "Download request rejected"):
        """
        Reject the download request
        
        Args:
            reason: Reason for rejection to send to client
        """
        try:
            self.session.reject_download_request(self.client_addr, reason)
            self.logger.info(f"Rejected download request from {self.client_addr}: {reason}")
        except Exception as e:
            self.logger.error(f"Error rejecting download request: {e}")
    
    def get_file_info(self, filepath: str) -> Optional[Tuple[str, int]]:
        """
        Get file information for the requested file
        
        Args:
            filepath: Path to the file
            
        Returns:
            Tuple of (filename, file_size) or None if file doesn't exist
        """
        try:
            if not self.file_exists(filepath):
                return None
            
            filename = os.path.basename(filepath)
            file_size = os.path.getsize(filepath)
            return filename, file_size
        except Exception as e:
            self.logger.error(f"Error getting file info for {filepath}: {e}")
            return None

    @staticmethod
    def extract_session_id(packet_data: bytes) -> Optional[str]:
        """
        Extract session ID from raw packet data without full parsing
        Useful for future concurrent server implementations to route packets
        
        Args:
            packet_data: Raw packet bytes
            
        Returns:
            Session ID or None if packet doesn't contain one
        """
        try:
            # Quick extraction without full validation
            # Session ID is at a fixed offset in the packet structure
            packet = RDTPacket.from_bytes(packet_data)
            return packet.session_id
        except Exception:
            return None