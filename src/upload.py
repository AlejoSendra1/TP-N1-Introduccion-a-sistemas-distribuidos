import sys
import os
import argparse
import logging
from socket import *

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
    parser.add_argument('-r', '--protocol', type=str, choices=['stop_wait', 'selective_repeat'],
                       default='stop_wait', help='error recovery protocol')
    
    return parser.parse_args()

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
    
    logger.info(f"Uploading file '{args.src}' to {args.host}:{args.port}")
    logger.debug(f"Using protocol: {args.protocol}")
    
    # TODO: implement actual file upload logic here
    # for now, just sending a test message
    message = f"UPLOAD {args.name}"
    clientSocket.sendto(message.encode(), (args.host, args.port))
    logger.debug(f"Upload request sent")
    
    modifiedMessage, serverAddress = clientSocket.recvfrom(2048)
    logger.info(f"Server response: {modifiedMessage.decode()}")
    
    clientSocket.close()
    logger.debug("Socket closed")

main()