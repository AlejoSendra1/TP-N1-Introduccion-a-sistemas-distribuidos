from typing import Tuple
import os
import queue
import sys
import argparse
import logging
import signal
from socket import timeout, socket, AF_INET, SOCK_DGRAM
import threading
from lib import create_receiver, request_shutdown, Protocol
from lib.base import RDTPacket, PacketType, DATA_BUFFER_SIZE, HANDSHAKE_TIMEOUT, MAX_RETRIES

def setup_logging(verbose, quiet):
    # logging format
    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    
    # logging level based on verbosity flags
    if verbose:
        level = logging.DEBUG
    elif quiet:
        level = logging.WARNING
    else:
        level = logging.INFO
    
    # logging configuration

    # create logs directory if it does not exist
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    logging.basicConfig(
        level=level,
        format=log_format,
        handlers=[logging.FileHandler('logs/download.log')]
    )
    
    return logging.getLogger(__name__)

def setup_argparse():
    parser = argparse.ArgumentParser(description='Download file from server')
    
    # verbosity group (mutually exclusive)
    verbosity_group = parser.add_mutually_exclusive_group()
    verbosity_group.add_argument('-v', '--verbose', action='store_true',
                               help='increase output verbosity')
    verbosity_group.add_argument('-q', '--quiet', action='store_true',
                               help='decrease output verbosity')
    
    # server configuration
    parser.add_argument('-H', '--host', type=str, default='127.0.0.1',
                       help='server IP address')
    parser.add_argument('-p', '--port', type=int, default=49153,
                       help='server port')
    
    # file configuration
    parser.add_argument('-d', '--dst', type=str, required=True,
                       help='destination file path')
    parser.add_argument('-n', '--name', type=str, required=True,
                       help='file name to download')
    
    # protocol configuration
    parser.add_argument('-r', '--protocol', type=str, 
                       choices=['stop_wait', 'selective_repeat'],
                       default='stop_wait', 
                       help='error recovery protocol')
    
    return parser.parse_args()

def signal_handler(signum, frame, logger, socket_obj):
    """Handle interrupt signals gracefully"""
    logger.info(f"Received signal {signum}, stopping download...")
    request_shutdown()  # Signal RDT protocol to stop
    if socket_obj:
        socket_obj.close()
    sys.exit(0)

def perform_download_handshake(socket_obj, server_addr, filename, protocol, logger):
    """
    Perform handshake to request file download
    
    Returns:
        str: session_id if successful, None if failed
    """
    # Create download request packet (INIT with file_size=0 indicates download)
    init_packet = RDTPacket(
        packet_type=PacketType.INIT,
        filename=filename,
        file_size=0,  # 0 indicates download request
        protocol=protocol
    )
    
    # Set timeout for handshake
    original_timeout = socket_obj.gettimeout()
    socket_obj.settimeout(HANDSHAKE_TIMEOUT)
    
    for attempt in range(MAX_RETRIES):
        try:
            # Send download request (INIT)
            socket_obj.sendto(init_packet.to_bytes(), server_addr)
            logger.debug(f"Sent download request for '{filename}' (attempt {attempt + 1})")
            
            # Wait for server response
            response_data, addr = socket_obj.recvfrom(DATA_BUFFER_SIZE)
            
            if addr != server_addr:
                logger.warning(f"Unexpected address: {addr} - expected: {server_addr} in session {init_packet.session_id}")
                continue
                
            response_packet = RDTPacket.from_bytes(response_data)
            
            if response_packet.packet_type == PacketType.ACCEPT:
                if response_packet.session_id and response_packet.verify_checksum():
                    session_id = response_packet.session_id
                    logger.info(f"Download request accepted, session ID: {session_id}")
                    socket_obj.settimeout(original_timeout)
                    return session_id
                else:
                    logger.error("Invalid ACCEPT packet received")
                    
            elif response_packet.packet_type == PacketType.ERROR:
                error_msg = response_packet.data.decode() if response_packet.data else "Unknown error"
                logger.error(f"Server rejected download request: {error_msg}")
                socket_obj.settimeout(original_timeout)
                return None
                
            else:
                logger.debug(f"Unexpected response type: {response_packet.packet_type}")
                
        except timeout:
            logger.debug(f"Timeout waiting for download response, retrying...")
        except Exception as e:
            logger.error(f"Error during download handshake: {e}")
            break
    
    logger.error("Failed to establish download session")
    socket_obj.settimeout(original_timeout)
    return None

def receive_downloaded_file(receiver, logger, data_queue: queue.Queue) -> Tuple[bool, bytes]:
    """
    Receive file data from server after successful handshake
    
    Args:
        data_queue: Queue to store received data chunks

    Returns:
        Tuple[bool, bytes]: (success, file_data)
    """
    try:
        logger.debug("Starting download...")
        # let receiver handle everything (first packet + rest)
        success, file_data = receiver.receive_file_after_handshake(data_queue)

        return success, file_data
    except Exception as e:
        logger.error(f"Error receiving downloaded file: {e}")
        return False, b''

# TODO: esta fn creo que ya la podemos borrar, la dejo mientras por las dudas
def handle_fin(sock,serv_addr,session_id,logger): # copiado de la sesion
    
    logger.debug("Waiting for FIN from server...")
    try:
        # wait for FIN packet with timeout
        sock.settimeout(5.0)
        data, addr = sock.recvfrom(DATA_BUFFER_SIZE)
        fin_packet = RDTPacket.from_bytes(data)
        
        if (fin_packet.packet_type == PacketType.FIN and 
            fin_packet.session_id == session_id and
            addr == serv_addr):
            
            # send FIN ACK
            fin_ack = RDTPacket(
                packet_type=PacketType.ACK,
                session_id=session_id
            )
            sock.sendto(fin_ack.to_bytes(), addr)
            logger.info(f"Session {session_id} closed with FIN/FIN-ACK")
            
        else:
            logger.warning(f"Invalid FIN packet from {addr}, expected: {PacketType.FIN},{session_id}  received: {fin_packet.packet_type},{fin_packet.session_id},{addr}")
            
    except timeout:
        logger.warning("No FIN received, session may be incomplete")
    except Exception as e:
        logger.error(f"Error handling FIN: {e}")
    

def write_to_file(data_queue: queue.Queue, dst_path: str, logger):
    """Thread function to write bytes from queue to file"""
    # Use the dst_path directly instead of reconstructing it
    filepath = dst_path

    try:
        # Create dst directory if it doesn't exist
        dst_dir = os.path.dirname(filepath)
        if dst_dir and not os.path.exists(dst_dir):
            os.makedirs(dst_dir)
            logger.debug(f"Created dst directory: {dst_dir}")

        logger.debug(f"Writing to file: {filepath}")
        with open(filepath, 'wb') as f:
            while True:
                byte_chunk = data_queue.get()
                if byte_chunk is None:  # Sentinel value to stop the thread
                    break
                f.write(byte_chunk)  # Now byte_chunk is already bytes, not individual bytes
                data_queue.task_done()
        logger.debug(f"File writing thread finished for {dst_path}")
    except Exception as e:
        logger.error(f"Error writing to file {dst_path}: {e}")

def main():
    # parse command line arguments
    args = setup_argparse()
    
    # setup logging
    logger = setup_logging(args.verbose, args.quiet)
    
    # set dst path
    if not args.dst:
        args.dst = args.filename
        logger.debug(f"Using default dst filename: {args.dst}")
    
    # check if dst file already exists
    if os.path.exists(args.dst):
        response = input(f"File '{args.dst}' already exists. Overwrite? (y/N): ")
        if response.lower() != 'y':
            logger.info("Download cancelled")
            sys.exit(0)
    
    # setup socket
    clientSocket = socket(AF_INET, SOCK_DGRAM)
    logger.debug("Socket created")
    
    # setup signal handlers
    signal.signal(signal.SIGINT, lambda s, f: signal_handler(s, f, logger, clientSocket))
    signal.signal(signal.SIGTERM, lambda s, f: signal_handler(s, f, logger, clientSocket))
    
    logger.info(f"Requesting file '{args.name}' from {args.host}:{args.port}")
    logger.debug(f"Using protocol: {args.protocol}")
    logger.info("Press Ctrl+C to cancel download")
    
    try:
        protocol = Protocol.from_string(args.protocol)
        server_addr = (args.host, args.port)
        receiver = create_receiver(protocol, clientSocket, logger)
        receiver.perform_handshake(args.name, server_addr)
        logger.debug(f'Receiver created with protocol {protocol}')

        # Step 1: Perform download handshake
        session_id = perform_download_handshake(clientSocket, server_addr, args.name, protocol, logger)

        if not receiver.perform_handshake(args.name, server_addr):
            logger.error("Failed to initiate download")
            sys.exit(1)
        
        data_queue = queue.Queue()  # Queue to hold received data chunks
        # Step 2: Receive file data
        thread_writer = threading.Thread(target=write_to_file, args=(data_queue, args.dst, logger))
        thread_writer.start()
        success, file_data = receive_downloaded_file(clientSocket, server_addr, session_id, protocol, logger, data_queue)

        if not success:
            logger.error("Failed to download file")
            sys.exit(1)

        # handle_fin(clientSocket,server_addr,session_id,logger)

        # Step 3: Wait for thread writer to finish and check for success
        try:
            # Wait for the writer thread to finish
            thread_writer.join()
            logger.debug(f"Thread writer joined, checking for file: {args.dst}")
            
            if not success:
                logger.error("Failed to download file")
                sys.exit(1)

            # Check if the file was written successfully
            if os.path.exists(args.dst):
                file_size = os.path.getsize(args.dst)
                logger.info(f"File saved successfully: {args.dst} ({file_size} bytes)")
            else:
                logger.error(f"Thread writer did not create the expected file: {args.dst}")
                logger.debug(f"Current working directory: {os.getcwd()}")
                logger.debug(f"Files in current directory: {os.listdir('.')}")
                sys.exit(1)

        except Exception as e:
            logger.error(f"Failed to save file: {e}")
            sys.exit(1)
            
    except KeyboardInterrupt:
        logger.info("Download cancelled by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Download error: {e}")
        sys.exit(1)
    finally:
        clientSocket.close()
        logger.debug("Socket closed")

if __name__ == '__main__':
    main()
