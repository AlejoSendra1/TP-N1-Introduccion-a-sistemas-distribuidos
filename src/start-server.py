import socket
import argparse
import os
import logging
import signal
import random
import threading
import time
from typing import Tuple, Optional, Dict
from lib import RDTPacket, PacketType, Protocol, create_receiver, wait_for_init_packet
from lib.factory import create_sender

class SessionInfo:
    """Information about an active concurrent session"""
    def __init__(self, session_id: str, dedicated_port: int, thread: threading.Thread, 
                 dedicated_socket: socket.socket, client_addr: Tuple[str, int]):
        self.session_id = session_id
        self.dedicated_port = dedicated_port
        self.thread = thread
        self.dedicated_socket = dedicated_socket
        self.client_addr = client_addr
        self.created_at = time.time()
        self.connected = False  # True when dedicated thread starts for dedicated client port

class Session:
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
        # generate session ID as single byte (1-255, 0 reserved for INIT)
        self.session_id = str(random.randint(1, 255)) # TODO: use a better session ID generation method, to avoid collisions
        
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
            # let receiver handle everything (first packet + rest)
            success, file_data = receiver.receive_file(self.client_addr, self.session_id)
            
            if success:
                # send FIN ACK
                self._handle_fin()
            
            return success, file_data
            
        except Exception as e:
            self.logger.error(f"Error receiving file: {e}")
            return False, b''
    
    def _handle_fin(self):
        """Handle FIN packet and send FIN ACK"""
        try:
            # send FIN ACK
            # FIN packet received and validated by concrete receiver
            # here we only have to send FIN ACK
            fin_ack = RDTPacket(
                packet_type=PacketType.ACK,
                session_id=self.session_id
            )
            self.sock.sendto(fin_ack.to_bytes(), self.client_addr) # TODO: create send FIN ACK method in concrete receiver
            self.logger.info(f"Session {self.session_id} closed with FIN/FIN-ACK")
            
            # clean up session after successful FIN ACK
            self.session_id = None
            self.client_addr = None
            self.protocol = None
            self.filename = None
            self.file_size = None
                
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
        sender.session_id = self.session_id
        if sender.send_file(source, self.filename):
            self.logger.info("File uploaded successfully")

        else:
            self.logger.error("File upload failed")



class ConcurrentTransferRequest:
    """
    Represents an incoming transfer request with concurrent handling
    Creates dedicated port and thread for each transfer
    """
    
    def __init__(self, file_server: 'FileServer', init_packet: RDTPacket, client_addr: Tuple[str, int]):
        self.file_server = file_server
        self.init_packet = init_packet
        self.client_addr = client_addr
        self.logger = file_server.logger
        self._session_id = None
        self._dedicated_port = None
        
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
        Accept the transfer with dedicated port and thread
        
        Returns:
            Tuple[bool, bytes] or None if handshake fails
        """
        try:
            # create dedicated socket and port
            dedicated_sock, dedicated_port = self.file_server._create_dedicated_socket()
            self._dedicated_port = dedicated_port
            
            # generate session ID
            session_id = str(random.randint(1, 255))
            self._session_id = session_id
            
            # send ACCEPT with dedicated port in payload
            accept_packet = RDTPacket(
                packet_type=PacketType.ACCEPT,
                session_id=session_id,
                data=str(dedicated_port).encode('utf-8')  # port in payload
            )
            
            self.file_server.sock.sendto(accept_packet.to_bytes(), self.client_addr)
            self.logger.info(f"Sent ACCEPT to {self.client_addr} with dedicated port {dedicated_port}")
            
            # create thread to handle transfer on dedicated port
            transfer_thread = threading.Thread(
                target=self._handle_dedicated_transfer,
                args=(dedicated_sock, session_id),
                daemon=True
            )
            
            # create session info
            session_info = SessionInfo(
                session_id=session_id,
                dedicated_port=dedicated_port,
                thread=transfer_thread,
                dedicated_socket=dedicated_sock,
                client_addr=self.client_addr
            )
            
            #add to active sessions
            self.file_server.add_session(session_id, session_info)
            
            # start transfer thread
            transfer_thread.start()
            
            return True, b''  # ssuccess, but no data yet (handled by thread, actual transfer happens in background)
            
        except Exception as e:
            self.logger.error(f"Failed to accept transfer: {e}")
            return None
    
    def _handle_dedicated_transfer(self, dedicated_sock: socket.socket, session_id: str):
        """Handle the actual transfer on dedicated port (runs in separate thread)"""
        try:
            self.logger.info(f"Thread started for session {session_id} on port {self._dedicated_port}")
            
            # mark session as connected when dedicated thread starts
            # if client does not connect to dedicated port, the session will be cleaned up after a timeout
            with self.file_server.sessions_lock:
                if session_id in self.file_server.active_sessions:
                    self.file_server.active_sessions[session_id].connected = True
            
            # ccreate receiver for this dedicated transfer
            receiver = create_receiver(self.protocol, dedicated_sock, self.logger)
            
            # the client will send DATA packets directly to this dedicated port
            success, file_data = receiver.receive_file(self.client_addr, session_id)
            
            if success:
                # send FIN ACK to complete the transfer
                fin_ack = RDTPacket(
                    packet_type=PacketType.FIN_ACK,
                    session_id=session_id
                )
                dedicated_sock.sendto(fin_ack.to_bytes(), self.client_addr)
                self.logger.debug(f"Sent FIN ACK for session {session_id}")
                
                self._save_file(file_data)
                self.logger.info(f"File transfer completed for session {session_id}")
            else:
                self.logger.error(f"File transfer failed for session {session_id}")
                
        except Exception as e:
            self.logger.error(f"Error in dedicated transfer thread {session_id}: {e}")
        finally:
            # Cleanup session
            self.file_server.remove_session(session_id)
            dedicated_sock.close()
            self.logger.info(f"Session {session_id} cleaned up")
    
    def _save_file(self, file_data: bytes):
        """Save received file to storage"""
        try:
            # get storage directory from file server
            storage_dir = getattr(self.file_server, 'storage_dir', 'storage')
            
            os.makedirs(storage_dir, exist_ok=True)
            safe_filename = os.path.basename(self.filename.strip())
            filepath = os.path.join(storage_dir, safe_filename)
            
            with open(filepath, 'wb') as f:
                f.write(file_data)
            self.logger.info(f"File saved: {filepath}")
            
        except Exception as e:
            self.logger.error(f"Failed to save file: {e}")
    
    def get_session_id(self) -> Optional[str]:
        """Get the session ID after acceptance"""
        return self._session_id
        
    def reject(self, reason: str = "Transfer rejected"):
        """Reject the transfer request"""
        error_packet = RDTPacket(
            packet_type=PacketType.ERROR,
            data=reason.encode('utf-8')
        )
        try:
            self.file_server.sock.sendto(error_packet.to_bytes(), self.client_addr)
        except Exception as e:
            self.logger.error(f"Failed to send rejection: {e}")


class TransferRequest:
    """
    Legacy TransferRequest class for backward compatibility
    Represents an incoming transfer request
    Provides simple interface for server to accept/reject
    """
    
    def __init__(self, sock: socket.socket, logger, init_packet: RDTPacket, client_addr: Tuple[str, int]):
        self.sock = sock
        self.logger = logger
        self.init_packet = init_packet
        self.client_addr = client_addr
        self.session = Session(sock, logger)
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
        if self.session.accept_transfer(self.init_packet, self.client_addr):
            self._session_id = self.session.session_id  # cache for future use
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


class FileServer:
    """
    High-level concurrent file server interface
    Handles incoming connections and transfer requests with dedicated ports
    """
    
    def __init__(self, sock: socket.socket, logger, max_concurrent: int = 10):
        self.sock = sock
        self.logger = logger
        self.max_concurrent = max_concurrent
        
        # for concurrent session management
        self.active_sessions: Dict[str, SessionInfo] = {}
        self.sessions_lock = threading.Lock()
        
        # server host for binding dedicated sockets
        self.host = sock.getsockname()[0]
        
        # start cleanup thread
        self.cleanup_thread = threading.Thread(target=self._cleanup_sessions, daemon=True)
        self.cleanup_thread.start()
        
        self.logger.info(f"Concurrent server initialized (max {max_concurrent} sessions)")
        
    def wait_for_transfer(self, timeout: Optional[float] = None) -> Optional['ConcurrentTransferRequest']:
        """
        Wait for an incoming transfer request and assign dedicated port
        
        Returns:
            ConcurrentTransferRequest object or None if timeout/error/server full
        """
        self.logger.debug(f"Waiting for transfer request (timeout={timeout})")
        result = wait_for_init_packet(self.sock, timeout)
        if result:
            packet, addr = result
            
            if packet.file_size == 0:
                self.logger.info('devolviendo download req en wait for transfer') ##sacar
                return DownloadRequest(self.sock, self.logger, packet, addr)
            
            self.logger.debug(f"Received INIT packet from {addr}: {packet.filename}")
            
            # check if server is at capacity
            with self.sessions_lock:
                if len(self.active_sessions) >= self.max_concurrent:
                    self.logger.warning(f"Server at capacity ({self.max_concurrent} sessions), rejecting client {addr}")
                    self._send_error(addr, "Server at capacity, try again later")
                    return None
            
            return ConcurrentTransferRequest(self, packet, addr)
        else:
            self.logger.debug("No INIT packet received (timeout or error)")
        return None
    
    def _send_error(self, addr: Tuple[str, int], message: str):
        """Send error packet to client"""
        error_packet = RDTPacket(
            packet_type=PacketType.ERROR,
            data=message.encode('utf-8')
        )
        try:
            self.sock.sendto(error_packet.to_bytes(), addr)
        except Exception as e:
            self.logger.error(f"Failed to send error to {addr}: {e}")
    
    def _create_dedicated_socket(self) -> Tuple[socket.socket, int]:
        """Create a dedicated socket with dynamic port assignment"""
        dedicated_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        dedicated_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # because our server assigns dynamic ports, we need to allow reuse of the same port (to avoid Address already in use errors)
        
        # bind to dynamic port (0 = OS assigns available port)
        dedicated_sock.bind((self.host, 0))
        dedicated_port = dedicated_sock.getsockname()[1]
        
        self.logger.debug(f"Created dedicated socket on port {dedicated_port}")
        return dedicated_sock, dedicated_port
    
    def _cleanup_sessions(self):
        """Background thread to cleanup expired sessions"""
        SESSION_TIMEOUT = 30  # 30 seconds timeout for abandoned sessions
        
        while True:
            try:
                time.sleep(5)  # check every 5 seconds
                current_time = time.time()
                
                with self.sessions_lock:
                    expired_sessions = []
                    for session_id, session_info in self.active_sessions.items():
                        # clean up sessions that have not connected or finished threads
                        if (not session_info.connected and 
                            current_time - session_info.created_at > SESSION_TIMEOUT) or \
                           (not session_info.thread.is_alive()):
                            expired_sessions.append(session_id)
                    
                    for session_id in expired_sessions:
                        self._remove_session(session_id)
                        
            except Exception as e:
                self.logger.error(f"Error in cleanup thread: {e}")
    
    def _remove_session(self, session_id: str):
        """Remove session and cleanup resources (must be called with sessions_lock held)"""
        if session_id in self.active_sessions:
            session_info = self.active_sessions[session_id]
            
            # close dedicated socket
            try:
                session_info.dedicated_socket.close()
            except Exception as e:
                self.logger.debug(f"Error closing socket for session {session_id}: {e}")
            
            # remove from active sessions
            del self.active_sessions[session_id]
            self.logger.debug(f"Cleaned up session {session_id} (port {session_info.dedicated_port})")
    
    def add_session(self, session_id: str, session_info: SessionInfo):
        """Add new session to active sessions"""
        with self.sessions_lock:
            self.active_sessions[session_id] = session_info
            self.logger.info(f"Added session {session_id} on port {session_info.dedicated_port}")
    
    def remove_session(self, session_id: str):
        """Remove session (public method)"""
        with self.sessions_lock:
            self._remove_session(session_id)


class GracefulKiller:
    """Handles graceful shutdown on SIGINT and SIGTERM"""
    def __init__(self, logger):
        self.kill_now = False
        self.logger = logger
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)
    
    def _handle_signal(self, signum, frame):
        self.logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.kill_now = True

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
        self.session = Session(sock, logger)
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

def setup_logging(verbose, quiet):
    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    
    if verbose:
        level = logging.DEBUG
    elif quiet:
        level = logging.WARNING
    else:
        level = logging.INFO
    
    logging.basicConfig(
        level=level,
        format=log_format,
        handlers=[logging.StreamHandler()]
    )
    
    return logging.getLogger(__name__)

def setup_argparse():
    parser = argparse.ArgumentParser(description='RDT File Transfer Server')
    
    verbosity_group = parser.add_mutually_exclusive_group()
    verbosity_group.add_argument('-v', '--verbose', action='store_true',
                               help='increase output verbosity')
    verbosity_group.add_argument('-q', '--quiet', action='store_true',
                               help='decrease output verbosity')
    
    parser.add_argument('-H', '--host', type=str, default='localhost',
                       help='service IP address')
    parser.add_argument('-p', '--port', type=int, default=49153,
                       help='service port')
    parser.add_argument('-s', '--storage', type=str, default='storage',
                       help='storage dir path')
    
    return parser.parse_args()


def main():
    # arguments parsing
    args = setup_argparse()
    
    # setup logging
    logger = setup_logging(args.verbose, args.quiet)
    
    # setup graceful shutdown
    killer = GracefulKiller(logger)
    
    # create storage directory
    if not os.path.exists(args.storage):
        os.makedirs(args.storage)
        logger.debug(f"Created storage directory: {args.storage}")
    
    # create UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        sock.bind((args.host, args.port))
        logger.info(f"Server listening on {args.host}:{args.port}")
        logger.info(f"Storage directory: {args.storage}")
        logger.info("Press Ctrl+C to stop")
        
        # create concurrent file server
        file_server = FileServer(sock, logger, max_concurrent=10)
        
        # store storage directory for use in ConcurrentTransferRequest
        file_server.storage_dir = args.storage
        
        while not killer.kill_now:
            # wait for transfer request
            request = file_server.wait_for_transfer()
            
            if request:
                
                # INPROGRESS: DOWNLOAD IMPLEMENTATION
                # handle different request types:
                if isinstance(request, DownloadRequest):
                    logger.info(f"Download request from {request.source_address}: {request.filename}")
                    # handle download request

                    filepath = os.path.join(args.storage, request.filename)
                    if os.path.exists(filepath):
                        success = request.accept(filepath)  # send file to client
                        if success:
                            logger.info(f"Connection setuped succesfully")
                        else:
                            logger.error("Connection error")

                        
                    else:
                        logger.error(f"File not found: {filepath}")
                        request.reject("File not found")
                elif isinstance(request, ConcurrentTransferRequest):
                    logger.info(f"Transfer request from {request.source_address}: {request.filename}")
                
                    # starts a background thread and returns immediately
                    result = request.accept()
                    
                    if result:
                        success, _ = result
                        if success:
                            logger.info(f"Transfer accepted and started in background thread")
                        else:
                            logger.error("Transfer failed to start")
                    else:
                        logger.error("Handshake failed")
    
    except KeyboardInterrupt as e:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Server error: {e}")
    finally:
        sock.close()
        logger.info("Server stopped")


if __name__ == '__main__':
    main()