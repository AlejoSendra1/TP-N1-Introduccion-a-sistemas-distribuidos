import socket
import argparse
import os
import logging
import signal
import random
from typing import Tuple, Optional
from lib import RDTPacket, PacketType, Protocol, create_receiver, wait_for_init_packet

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
    High-level file server interface
    Handles incoming connections and transfer requests
    """
    
    def __init__(self, sock: socket.socket, logger):
        self.sock = sock
        self.logger = logger
        
    def wait_for_transfer(self, timeout: Optional[float] = None) -> Optional[TransferRequest]:
        """
        Wait for an incoming transfer request
        
        Returns:
            TransferRequest object or None if timeout/error
        """
        result = wait_for_init_packet(self.sock, timeout)
        if result:
            packet, addr = result
            return TransferRequest(self.sock, self.logger, packet, addr)
        return None


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
        
        # create file server
        file_server = FileServer(sock, logger)
        
        while not killer.kill_now:
            # wait for transfer request
            request = file_server.wait_for_transfer(timeout=1.0)
            
            # TODO: CONCURRENT SERVER IMPLEMENTATION
            # handle concurrent requests
            
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
                elif isinstance(request, TransferRequest):
                    logger.info(f"Transfer request from {request.source_address}: {request.filename}")

                    # handle upload request (current logic)
                
                    # CURRENT LOGIC (UPLOAD ONLY):
                    # simple policy: accept all transfers
                    result = request.accept()
                    
                    if result:
                        success, file_data = result
                        if success:
                            # save the file
                            filepath = os.path.join(args.storage, request.filename)
                            with open(filepath, 'wb') as f:
                                f.write(file_data)
                            logger.info(f"File saved: {filepath}")
                        else:
                            logger.error("Transfer failed")
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