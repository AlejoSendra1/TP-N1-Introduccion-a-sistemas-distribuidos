import os
import sys
import argparse
import logging
import signal
from socket import socket, AF_INET, SOCK_DGRAM
from lib import create_sender, request_shutdown, Protocol
from lib.base import ACK_BUFFER_SIZE, HANDSHAKE_TIMEOUT, MAX_RETRIES, PacketType, RDTPacket

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
        handlers=[logging.FileHandler('logs/upload.log')]
    )
    
    return logging.getLogger(__name__)

def setup_argparse():
    parser = argparse.ArgumentParser(description='Upload file to server')
    
    # verbosity group (mutually exclusive)
    verbosity_group = parser.add_mutually_exclusive_group()
    verbosity_group.add_argument('-v', '--verbose', action='store_true',
                               help='increase output verbosity')
    verbosity_group.add_argument('-q', '--quiet', action='store_true',
                               help='decrease output verbosity')
    
    # server configuration
    parser.add_argument('-H', '--host', type=str, default='localhost',
                       help='server IP address')
    parser.add_argument('-p', '--port', type=int, default=49153,
                       help='server port')
    
    # file configuration
    parser.add_argument('-s', '--src', type=str, required=True,
                       help='source file path')
    parser.add_argument('-n', '--name', type=str,
                       help='file name (defaults to source file name)')
    
    # protocol configuration
    parser.add_argument('-r', '--protocol', type=str, 
                       choices=['stop_wait', 'selective_repeat'],
                       default='stop_wait', 
                       help='error recovery protocol')
    
    return parser.parse_args()

def signal_handler(signum, frame, logger, socket_obj):
    """Handle interrupt signals gracefully"""
    logger.info(f"Received signal {signum}, stopping upload...")
    request_shutdown()  # Signal RDT protocol to stop
    if socket_obj:
        socket_obj.close()
    sys.exit(0)

def main():
    # parse command line arguments
    args = setup_argparse()
    
    # setup logging
    logger = setup_logging(args.verbose, args.quiet)
    
    # validate source file exists
    if not os.path.exists(args.src):
        logger.error(f"Source file '{args.src}' does not exist")
        sys.exit(1)
    
    # if no name provided, use source filename
    if not args.name:
        args.name = os.path.basename(args.src)
        logger.debug(f"Using source filename: {args.name}")
    
    # setup socket
    clientSocket = socket(AF_INET, SOCK_DGRAM)
    logger.debug(f"Socket created")
    
    # setup signal handlers
    signal.signal(signal.SIGINT, lambda s, f: signal_handler(s, f, logger, clientSocket))
    signal.signal(signal.SIGTERM, lambda s, f: signal_handler(s, f, logger, clientSocket))
    
    logger.info(f"Uploading file '{args.src}' to {args.host}:{args.port}")
    logger.debug(f"Using protocol: {args.protocol}")
    logger.info("Press Ctrl+C to cancel upload")
    
    try:
        # create appropriate sender using factory method
        protocol = Protocol.from_string(args.protocol)
        sender = create_sender(protocol, clientSocket, (args.host, args.port), logger)
        
        # perform handshake first
        if not sender.perform_handshake(args.name, os.path.getsize(args.src)):
            return False

        # send file using selected RDT protocol
        if sender.send_file(args.src, args.name):
            logger.info("File uploaded successfully")
        else:
            logger.error("File upload failed")
            sys.exit(1)
            
    except KeyboardInterrupt as e:
        logger.info("Upload cancelled by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Upload error: {e}")
        sys.exit(1)
    finally:
        clientSocket.close()
        logger.debug("Socket closed")

if __name__ == '__main__':
    main()