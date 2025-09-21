import sys
import socket
import threading
import argparse
import os
import logging
import signal
from lib.rdt_protocol import RDTReceiver, RDTPacket, PacketType

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
    logging.basicConfig(
        level=level,
        format=log_format,
        handlers=[logging.StreamHandler()]
    )
    
    return logging.getLogger(__name__)

def setup_argparse():
    parser = argparse.ArgumentParser(description='File Transfer Server')
    
    # verbosity group (mutually exclusive)
    verbosity_group = parser.add_mutually_exclusive_group()
    verbosity_group.add_argument('-v', '--verbose', action='store_true',
                               help='increase output verbosity')
    verbosity_group.add_argument('-q', '--quiet', action='store_true',
                               help='decrease output verbosity')
    
    # server configuration
    parser.add_argument('-H', '--host', type=str, default='localhost',
                       help='service IP address')
    parser.add_argument('-p', '--port', type=int, default=49153,
                       help='service port')
    parser.add_argument('-s', '--storage', type=str, default='storage',
                       help='storage dir path')
    
    return parser.parse_args()

def handle_client(data, addr, sock, storage_dir, logger):
    """Handle incoming client connection"""
    try:
        # try to parse as RDT packet
        packet = RDTPacket.from_bytes(data)
        logger.debug(f"Received RDT packet from {addr}: type={packet.type}, seq={packet.seq_num}")
        
        if packet.type == PacketType.DATA:
            # this is an upload, handle it directly
            logger.info(f"Starting file upload from {addr}")
            
            # handle upload using the same socket (simplified)
            receiver = RDTReceiver(sock, logger)
            # we need to process this first packet manually since we already received it
            filepath = receiver.receive_file_with_first_packet(storage_dir, packet, addr)
            if filepath:
                logger.info(f"File upload completed: {filepath}")
            else:
                logger.error("File upload failed")
            
        elif packet.type == PacketType.REQUEST:
            # this is a download request
            logger.info(f"Download request from {addr}: {packet.filename}")
            # TODO: implement download logic
            logger.warning("Download not implemented yet")
            
        else:
            logger.debug(f"Unknown packet type: {packet.type}")
            
    except Exception as e:
        # fallback to old protocol for compatibility
        logger.debug(f"Non-RDT packet from {addr}: {data.decode()[:50]}...")
        response = f"Server received: {data.decode()}"
        sock.sendto(response.encode(), addr)

def main():
    # parse command line arguments
    args = setup_argparse()
    
    # setup logging
    logger = setup_logging(args.verbose, args.quiet)
    
    # setup graceful shutdown handler
    killer = GracefulKiller(logger)
    
    # create storage directory if it doesn't exist
    if not os.path.exists(args.storage):
        os.makedirs(args.storage)
        logger.debug(f"Created storage directory: {args.storage}")
    
    # setup socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # allow reuse of address
    
    try:
        sock.bind((args.host, args.port))
        sock.settimeout(1.0)  # timeout to check for shutdown signal
        
        logger.info(f"UDP server listening on {args.host}:{args.port}")
        logger.info(f"Using storage directory: {args.storage}")
        logger.info("Press Ctrl+C to stop the server")

        while not killer.kill_now:
            try:
                data, addr = sock.recvfrom(4096)  # increased buffer size for RDT packets
                logger.debug(f"Packet received from {addr}")
                
                # start a new thread for each message
                client_thread = threading.Thread(
                    target=handle_client,
                    args=(data, addr, sock, args.storage, logger),
                    daemon=True
                )
                client_thread.start()
                
            except socket.timeout:
                # timeout is expected, just check if we should shutdown
                continue
            except Exception as e:
                if not killer.kill_now:
                    logger.error(f"Error receiving data: {e}")
    
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Server error: {e}")
    finally:
        logger.info("Shutting down server...")
        sock.close()
        logger.info("Server stopped")

if __name__ == '__main__':
    main()


