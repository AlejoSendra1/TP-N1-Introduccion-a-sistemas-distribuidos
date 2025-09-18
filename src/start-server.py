import sys
import socket
import threading
import argparse
import os
import logging

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

def handle_client(data, addr, sock, logger):
    logger.debug(f"Received from {addr}: {data.decode()}")
    response = f"Server received: {data.decode()}"
    sock.sendto(response.encode(), addr)

def main():
    # parse command line arguments
    args = setup_argparse()
    
    # setup logging
    logger = setup_logging(args.verbose, args.quiet)
    
    # create storage directory if it doesn't exist
    if not os.path.exists(args.storage):
        os.makedirs(args.storage)
        logger.debug(f"Created storage directory: {args.storage}")
    
    # setup socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.host, args.port))
    
    logger.info(f"UDP server listening on {args.host}:{args.port}")
    logger.info(f"Using storage directory: {args.storage}")

    while True:
        data, addr = sock.recvfrom(1024)  
        logger.debug(f"Packet received from {addr}")
        
        # start a new thread for each message
        client_thread = threading.Thread(
            target=handle_client,
            args=(data, addr, sock, logger),
            daemon=True
        )
        client_thread.start()

main()


