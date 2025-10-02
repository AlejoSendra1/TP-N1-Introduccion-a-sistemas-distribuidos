import socket
import argparse
import os
import logging
import signal
import random
import threading
import queue
import time
from abc import ABC, abstractmethod
from typing import Tuple, Optional, Dict
from lib import (
    RDTPacket,
    PacketType,
    Protocol,
    create_receiver,
    wait_for_init_packet,
    SEQ_NUM_MODULO,
)
from lib.base import ACK_BUFFER_SIZE, HANDSHAKE_TIMEOUT, MAX_RETRIES
from lib.factory import create_sender

FREE = 0
READING = 1
WRITING = 2


class AbstractRequest(ABC):
    """
    Abstract base class for all transfer requests
    Defines the polymorphic interface that all request types must implement
    """

    @abstractmethod
    def accept(self) -> bool:
        """
        Accept and handle the request

        Returns:
            bool: True if request was handled successfully, False otherwise
        """
        pass

    @property
    @abstractmethod
    def filename(self) -> str:
        """The filename associated with this request"""
        pass

    @property
    @abstractmethod
    def source_address(self) -> Tuple[str, int]:
        """The client's address"""
        pass


class SessionInfo:
    """Information about an active concurrent session"""

    def __init__(
        self,
        session_id: str,
        dedicated_port: int,
        thread: threading.Thread,
        dedicated_socket: socket.socket,
        client_addr: Tuple[str, int],
    ):
        self.session_id = session_id
        self.dedicated_port = dedicated_port
        self.thread = thread
        self.dedicated_socket = dedicated_socket
        self.client_addr = client_addr
        self.created_at = time.time()
        self.connected = False  # True when dedicated thread
        # starts for dedicated client port


class ConcurrentTransferRequest(AbstractRequest):
    """
    Represents an incoming upload transfer request with concurrent handling
    Creates dedicated port and thread for each transfer
    Inherits from AbstractRequest to provide polymorphic interface
    """

    def __init__(
        self,
        file_server: "FileServer",
        init_packet: RDTPacket,
        client_addr: Tuple[str, int],
    ):
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

    def accept(self) -> bool:
        """
        Accept the transfer with dedicated port and thread
        Handles queue and writer thread creation internally

        Returns:
            bool: True if transfer started successfully, False otherwise
        """
        try:
            # create data queue for thread communication
            data_queue = queue.Queue()

            # construct filepath for saving the file
            storage_dir = self.file_server.storage_dir

            safe_filename = os.path.basename(self.filename.strip())
            filepath = os.path.join(storage_dir, safe_filename)

            if not self.file_server.file_manager.can_start_upload(filepath):
                self.reject("File already exists and is in use")
                return False

            # create writer thread to save data to disk
            writer_thread = threading.Thread(
                target=write_file, args=(data_queue, filepath), daemon=True
            )
            writer_thread.start()
            self.logger.debug(f"Started writer thread for {filepath}")

            # create dedicated socket and port
            dedicated_sock, dedicated_port = (
                self.file_server._create_dedicated_socket()
            )
            self._dedicated_port = dedicated_port

            # generate unique session ID
            session_id = self.file_server._generate_unique_session_id()
            self._session_id = session_id

            # send ACCEPT with dedicated port in payload
            accept_packet = RDTPacket(
                packet_type=PacketType.ACCEPT,
                session_id=session_id,
                data=str(dedicated_port).encode("utf-8"),  # port in payload
            )

            # STEP 3: Wait for final ACK from client
            self.file_server.sock.settimeout(HANDSHAKE_TIMEOUT)
            dedicated_sock.settimeout(HANDSHAKE_TIMEOUT)
            for attempt in range(MAX_RETRIES):
                try:
                    self.file_server.sock.sendto(
                        accept_packet.to_bytes(), self.client_addr
                    )
                    self.logger.info(
                        f"Sent ACCEPT to {self.client_addr} with "
                        f"dedicated port {dedicated_port}, attempt {attempt}"
                    )
                    ack_data, ack_addr = dedicated_sock.recvfrom(
                        ACK_BUFFER_SIZE
                    )

                    if ack_addr != self.client_addr:
                        self.logger.warning(
                            f"Received ACK from unexpected address: {ack_addr}"
                        )
                        continue
                    self.logger.debug("Packet received from client")
                    ack_packet = RDTPacket.from_bytes(ack_data)

                    # accept both ACCEPT_ACK and DATA as
                    # valid handshake completion
                    # (client may send first DATA packet
                    # immediately after ACCEPT_ACK)
                    if (
                        ack_packet.packet_type == PacketType.ACCEPT_ACK
                        and ack_packet.session_id == self._session_id
                        and ack_packet.verify_checksum()
                    ) or ack_packet.packet_type == PacketType.DATA:
                        self.logger.info(
                            f"Received {ack_packet.packet_type} "
                            f"- Handshake complete"
                        )
                        break
                    else:
                        self.logger.debug(
                            "Invalid ACCEPT_ACK packet, waiting..."
                        )

                except socket.timeout:
                    # Resend ACCEPT if no ACCEPT_ACK received
                    self.logger.debug(
                        "Resending ACCEPT (no ACCEPT_ACK received)"
                    )

            # create thread to handle transfer on dedicated port
            transfer_thread = threading.Thread(
                target=self._handle_dedicated_transfer,
                args=(dedicated_sock, session_id, data_queue),
                daemon=True,
            )

            # create session info
            session_info = SessionInfo(
                session_id=session_id,
                dedicated_port=dedicated_port,
                thread=transfer_thread,
                dedicated_socket=dedicated_sock,
                client_addr=self.client_addr,
            )

            # add to active sessions
            self.file_server.add_session(session_id, session_info)

            # start transfer thread
            transfer_thread.start()

            return True

        except Exception as e:
            self.logger.error(f"Failed to accept transfer: {e}")
            return False

    def _handle_dedicated_transfer(
        self,
        dedicated_sock: socket.socket,
        session_id: str,
        data_queue: queue.Queue,
    ):
        """Handle the actual transfer on dedicated port
        (runs in separate thread)"""
        try:
            self.logger.info(
                f"Thread started for session {session_id} "
                f"on port {self._dedicated_port}"
            )

            # mark session as connected when dedicated thread starts
            # if client does not connect to dedicated port, the session
            # will be cleaned up after a timeout
            with self.file_server.sessions_lock:
                if session_id in self.file_server.active_sessions:
                    self.file_server.active_sessions[
                        session_id
                    ].connected = True

            # ccreate receiver for this dedicated transfer
            receiver = create_receiver(
                self.protocol, dedicated_sock, self.logger
            )

            # the client will send DATA packets directly to this dedicated port
            success, file_data = receiver.receive_file(
                self.client_addr, session_id, data_queue
            )

            if success:
                # send FIN ACK to complete the transfer
                fin_ack = RDTPacket(
                    packet_type=PacketType.FIN_ACK, session_id=session_id
                )
                dedicated_sock.sendto(fin_ack.to_bytes(), self.client_addr)
                self.logger.debug(f"Sent FIN ACK for session {session_id}")

                self._save_file(file_data)
                self.logger.info(
                    f"File transfer completed for session {session_id}"
                )
            else:
                self.logger.error(
                    f"File transfer failed for session {session_id}"
                )

        except Exception as e:
            self.logger.error(
                f"Error in dedicated transfer thread {session_id}: {e}"
            )
        finally:
            # Cleanup session
            storage_dir = self.file_server.storage_dir
            safe_filename = os.path.basename(self.filename.strip())
            filepath = os.path.join(storage_dir, safe_filename)
            self.file_server.file_manager.release_upload(filepath)
            self.file_server.remove_session(session_id)
            dedicated_sock.close()
            self.logger.info(f"Session {session_id} cleaned up")

    def _save_file(self, file_data: bytes):
        """Save received file to storage"""
        try:
            # get storage directory from file server
            storage_dir = getattr(self.file_server, "storage_dir", "storage")

            os.makedirs(storage_dir, exist_ok=True)
            safe_filename = os.path.basename(self.filename.strip())
            filepath = os.path.join(storage_dir, safe_filename)

            with open(filepath, "wb") as f:
                f.write(file_data)
            self.logger.info(f"File saved: {filepath}")

        except Exception as e:
            self.logger.error(f"Failed to save file: {e}")

    def reject(self, reason: str = "Transfer rejected"):
        """Reject the transfer request"""
        error_packet = RDTPacket(
            packet_type=PacketType.ERROR, data=reason.encode("utf-8")
        )
        self.logger.debug("Rejecting File transfer")
        try:
            self.file_server.sock.sendto(
                error_packet.to_bytes(), self.client_addr
            )
        except Exception as e:
            self.logger.error(f"Failed to send rejection: {e}")


class ConcurrentDownloadRequest(AbstractRequest):
    def __init__(
        self,
        file_server: "FileServer",
        init_packet: RDTPacket,
        client_addr: Tuple[str, int],
    ):
        self.file_server = file_server
        self.init_packet = init_packet
        self.client_addr = client_addr
        self.logger = file_server.logger
        self._session_id = None
        self._dedicated_port = None

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

    def _handle_dedicated_request(
        self, dedicated_sock: socket.socket, session_id: str
    ):
        storage_dir = self.file_server.storage_dir

        safe_filename = os.path.basename(self.filename.strip())
        filepath = os.path.join(storage_dir, safe_filename)
        try:
            self.logger.info(
                f"Thread started for session {session_id} "
                f"on port {self._dedicated_port}"
            )

            # mark session as connected when dedicated thread starts
            # if client does not connect to dedicated port, the session
            # will be cleaned up after a timeout
            with self.file_server.sessions_lock:
                if session_id in self.file_server.active_sessions:
                    self.file_server.active_sessions[
                        session_id
                    ].connected = True

            # ccreate receiver for this dedicated download
            sender = create_sender(
                self.protocol, dedicated_sock, self.client_addr, self.logger
            )
            sender.session_id = session_id
            self.logger.debug(
                f"Created sender for session {session_id} "
                f"for client with address: {self.client_addr}"
            )

            # the client will send DATA packets directly to this dedicated port
            success = sender.send_file(filepath, self.filename)

            if success:
                self.logger.info(
                    f"File download completed for session {session_id}"
                )
            else:
                self.logger.error(
                    f"File download failed for session {session_id}"
                )

        except Exception as e:
            self.logger.error(
                f"Error in dedicated transfer thread {session_id}: {e}"
            )
        finally:
            # Cleanup session
            self.file_server.remove_session(session_id)
            self.file_server.file_manager.release_download(filepath)
            dedicated_sock.close()
            self.logger.info(f"Session {session_id} cleaned up")

    def accept(self) -> bool:
        """
        Do the handshake and set up for receiving incoming bytes
        Returns:
            True if file was sent successfully, False otherwise
        """
        storage_dir = self.file_server.storage_dir

        safe_filename = os.path.basename(self.filename.strip())
        filepath = os.path.join(storage_dir, safe_filename)
        if not os.path.exists(filepath):
            self.reject("File doesnt exist")
            return False
        elif not self.file_server.file_manager.can_start_download(filepath):
            self.reject("File in use")
            return False

        try:
            # create dedicated socket and port
            dedicated_sock, dedicated_port = (
                self.file_server._create_dedicated_socket()
            )
            self._dedicated_port = dedicated_port

            # generate unique session ID
            session_id = self.file_server._generate_unique_session_id()
            self._session_id = session_id

            # send ACCEPT with dedicated port in payload
            accept_packet = RDTPacket(
                packet_type=PacketType.ACCEPT,
                session_id=session_id,
                data=str(dedicated_port).encode("utf-8"),  # port in payload
            )

            # STEP 3: Wait for final ACK from client
            self.file_server.sock.settimeout(HANDSHAKE_TIMEOUT)
            dedicated_sock.settimeout(HANDSHAKE_TIMEOUT)
            for attempt in range(MAX_RETRIES):
                try:
                    self.file_server.sock.sendto(
                        accept_packet.to_bytes(), self.client_addr
                    )
                    self.logger.info(
                        f"Sent ACCEPT to {self.client_addr} with "
                        f"dedicated port {dedicated_port}, attempt {attempt}"
                    )
                    ack_data, ack_addr = dedicated_sock.recvfrom(
                        ACK_BUFFER_SIZE
                    )

                    if ack_addr != self.client_addr:
                        self.logger.warning(
                            f"Received ACK from unexpected address: {ack_addr}"
                        )
                        continue
                    self.logger.debug("Packet received from client")
                    ack_packet = RDTPacket.from_bytes(ack_data)

                    if (
                        ack_packet.packet_type == PacketType.ACCEPT_ACK
                        and ack_packet.session_id == self._session_id
                        and ack_packet.verify_checksum()
                    ):
                        self.logger.info(
                            f"Received {ack_packet.packet_type} "
                            f"- Handshake complete"
                        )
                        break
                    else:
                        self.logger.debug(
                            "Invalid ACCEPT_ACK packet, waiting..."
                        )

                except socket.timeout:
                    self.logger.debug(
                        "Resending ACCEPT (no ACCEPT_ACK received)"
                    )

            transfer_thread = threading.Thread(
                target=self._handle_dedicated_request,
                args=(dedicated_sock, session_id),
                daemon=True,
            )

            # create session info
            session_info = SessionInfo(
                session_id=session_id,
                dedicated_port=dedicated_port,
                thread=transfer_thread,
                dedicated_socket=dedicated_sock,
                client_addr=self.client_addr,
            )

            # add to active sessions
            self.file_server.add_session(session_id, session_info)

            # start transfer thread
            transfer_thread.start()

            return True  # ssuccess, but no data yet
            # (handled by thread, actual transfer happens in background)
        except Exception:
            return False

    def reject(self, reason: str = "Download request rejected"):
        """
        Reject the download request

        Args:
            reason: Reason for rejection to send to client
        """

        error_packet = RDTPacket(
            packet_type=PacketType.ERROR, data=reason.encode("utf-8")
        )
        self.logger.debug("Rejecting File download")
        try:
            self.file_server.sock.sendto(
                error_packet.to_bytes(), self.client_addr
            )
        except Exception as e:
            self.logger.error(f"Failed to send rejection: {e}")
        pass

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


class FileAccessManager:
    def __init__(self):
        # { filename: (state, readers) }
        # state = FREE, READING o WRITING
        # readers = number of threads currently reading file
        self.files = {}
        self.lock = threading.Lock()

    def can_start_download(self, filename: str) -> bool:
        with self.lock:
            state, readers = self.files.get(filename, (FREE, 0))
            if state == WRITING:
                return False
            self.files[filename] = (READING, readers + 1)
            return True

    def can_start_upload(self, filename: str) -> bool:
        with self.lock:
            state, readers = self.files.get(filename, (FREE, 0))
            if state != FREE:
                return False
            self.files[filename] = (WRITING, 0)
            return True

    def release_download(self, filename: str):
        with self.lock:
            if filename in self.files:
                state, readers = self.files[filename]
                readers -= 1
                if readers <= 0:
                    self.files[filename] = (FREE, 0)
                else:
                    self.files[filename] = (READING, readers)

    def release_upload(self, filename: str):
        with self.lock:
            if filename in self.files:
                self.files[filename] = (FREE, 0)


class FileServer:
    """
    High-level concurrent file server interface
    Handles incoming connections and transfer requests with dedicated ports
    """

    def __init__(self, sock: socket.socket, logger, max_concurrent: int = 10):
        self.sock = sock
        self.logger = logger
        self.max_concurrent = max_concurrent
        self.storage_dir = None

        # for concurrent session management
        self.active_sessions: Dict[str, SessionInfo] = {}
        self.sessions_lock = threading.Lock()

        # file management
        self.file_manager = FileAccessManager()

        # server host for binding dedicated sockets
        self.host = sock.getsockname()[0]

        # start cleanup thread
        self.cleanup_thread = threading.Thread(
            target=self._cleanup_sessions, daemon=True
        )
        self.cleanup_thread.start()

        self.logger.info(
            f"Concurrent server initialized (max {max_concurrent} sessions)"
        )

    def wait_for_transfer(
        self, timeout: Optional[float] = None
    ) -> ConcurrentDownloadRequest | None | ConcurrentTransferRequest:
        """
        Wait for an incoming transfer request and assign dedicated port

        Returns:
            ConcurrentTransferRequest object or
            None if timeout/error/server full
        """
        self.logger.debug(f"Waiting for transfer request (timeout={timeout})")
        result = wait_for_init_packet(self.sock, timeout)
        if result:
            packet, addr = result

            # ccheck request type based on packet type
            if packet.packet_type == PacketType.DOWNLOAD_INIT:
                self.logger.debug(
                    f"Received DOWNLOAD_INIT from {addr} "
                    f"for '{packet.filename}'"
                )
                return ConcurrentDownloadRequest(self, packet, addr)

            elif packet.packet_type == PacketType.UPLOAD_INIT:
                self.logger.debug(
                    f"Received UPLOAD_INIT from {addr}: {packet.filename}"
                )

                # check if server is at capacity
                with self.sessions_lock:
                    if len(self.active_sessions) >= self.max_concurrent:
                        self.logger.warning(
                            f"Server at capacity ({self.max_concurrent} "
                            f"sessions), rejecting client {addr}"
                        )
                        self._send_error(
                            addr, "Server at capacity, try again later"
                        )
                        return None

                return ConcurrentTransferRequest(self, packet, addr)
            else:
                self.logger.warning(
                    f"Received unknown packet type {packet.packet_type} "
                    f"from {addr}"
                )
                return None
        else:
            self.logger.debug("No INIT packet received (timeout or error)")
        return None

    def _send_error(self, addr: Tuple[str, int], message: str):
        """Send error packet to client"""
        error_packet = RDTPacket(
            packet_type=PacketType.ERROR, data=message.encode("utf-8")
        )
        try:
            self.sock.sendto(error_packet.to_bytes(), addr)
        except Exception as e:
            self.logger.error(f"Failed to send error to {addr}: {e}")

    def _generate_unique_session_id(self) -> str:
        """Generate a unique session ID that's not currently in use"""
        with self.sessions_lock:
            # try up to 100 times to generate a unique ID
            for _ in range(100):
                # random session ID (1-255)
                session_id = str(random.randint(1, SEQ_NUM_MODULO - 1))
                if session_id not in self.active_sessions:
                    return session_id

            # fallback: find first available ID
            for i in range(1, SEQ_NUM_MODULO):
                session_id = str(i)
                if session_id not in self.active_sessions:
                    return session_id

            # all IDs exhausted (shouldn't happen with proper cleanup)
            raise RuntimeError("No available session IDs")

    def _create_dedicated_socket(self) -> Tuple[socket.socket, int]:
        """Create a dedicated socket with dynamic port assignment"""
        dedicated_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        dedicated_sock.setsockopt(
            socket.SOL_SOCKET, socket.SO_REUSEADDR, 1
        )  # because our server assigns dynamic ports, we need to allow reuse
        # of the same port (to avoid Address already in use errors)

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
                    for (
                        session_id,
                        session_info,
                    ) in self.active_sessions.items():
                        # clean up sessions that have not
                        # connected or finished threads
                        if (
                            not session_info.connected
                            and current_time - session_info.created_at
                            > SESSION_TIMEOUT
                        ) or (not session_info.thread.is_alive()):
                            expired_sessions.append(session_id)

                    for session_id in expired_sessions:
                        self._remove_session(session_id)

            except Exception as e:
                self.logger.error(f"Error in cleanup thread: {e}")

    def _remove_session(self, session_id: str):
        """Remove session and cleanup resources (must be called
        with sessions_lock held)"""
        if session_id in self.active_sessions:
            session_info = self.active_sessions[session_id]

            # close dedicated socket
            try:
                session_info.dedicated_socket.close()
            except Exception as e:
                self.logger.debug(
                    f"Error closing socket for session {session_id}: {e}"
                )

            # remove from active sessions
            del self.active_sessions[session_id]
            self.logger.debug(
                f"Cleaned up session {session_id} "
                f"(port {session_info.dedicated_port})"
            )

    def add_session(self, session_id: str, session_info: SessionInfo):
        """Add new session to active sessions"""
        with self.sessions_lock:
            self.active_sessions[session_id] = session_info
            self.logger.info(
                f"Added session {session_id} on "
                f"port {session_info.dedicated_port}"
            )

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
        self.logger.info(
            f"Received signal {signum}, initiating graceful shutdown..."
        )
        self.kill_now = True


def setup_logging(verbose, quiet):
    log_format = "%(asctime)s - %(levelname)s - %(message)s"

    if verbose:
        level = logging.DEBUG
    elif quiet:
        level = logging.WARNING
    else:
        level = logging.INFO

    # create logs directory if it does not exist
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    logging.basicConfig(
        level=level,
        format=log_format,
        handlers=[logging.FileHandler("logs/server.log")],
    )

    return logging.getLogger(__name__)


def setup_argparse():
    parser = argparse.ArgumentParser(description="RDT File Transfer Server")

    verbosity_group = parser.add_mutually_exclusive_group()
    verbosity_group.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="increase output verbosity",
    )
    verbosity_group.add_argument(
        "-q", "--quiet", action="store_true", help="decrease output verbosity"
    )

    parser.add_argument(
        "-H",
        "--host",
        type=str,
        default="localhost",
        help="service IP address",
    )
    parser.add_argument(
        "-p", "--port", type=int, default=49153, help="service port"
    )
    parser.add_argument(
        "-s", "--storage", type=str, default="storage", help="storage dir path"
    )

    return parser.parse_args()


def write_file(queue: queue.Queue, filepath: str):
    """Thread function to write received bytes to file"""
    dir, filename = os.path.split(filepath)
    with open(f"{dir}/{filename}", "wb") as f:
        while True:
            data = queue.get()
            if data is None:
                break
            f.write(bytes(data))
            queue.task_done()


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
                # polymorphic handling: all requests use the
                # same .accept() interface
                logger.info(
                    f"Request from {request.source_address}: "
                    f"{request.filename}"
                )

                success = request.accept()

                if success:
                    logger.info("Request handled successfully")
                else:
                    logger.error("Request failed")

    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Server error: {e}")
    finally:
        sock.close()
        logger.info("Server stopped")


if __name__ == "__main__":
    main()
