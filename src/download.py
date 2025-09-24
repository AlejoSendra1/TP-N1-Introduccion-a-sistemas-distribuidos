import os
import argparse
import logging
from socket import socket, AF_INET, SOCK_DGRAM
from lib import Protocol

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
    parser = argparse.ArgumentParser(description='Download file from server')
    
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
    parser.add_argument('-d', '--dst', type=str, required=True,
                       help='destination file path')
    parser.add_argument('-n', '--name', type=str, required=True,
                       help='file name to download')
    
    # protocol configuration
    parser.add_argument('-r', '--protocol', type=str, 
                       choices=[p.value for p in Protocol],
                       default=Protocol.STOP_WAIT.value, 
                       help='error recovery protocol')
    
    return parser.parse_args()

def main():
    args = setup_argparse()
    
    # setup logging
    logger = setup_logging(args.verbose, args.quiet)
    
    # ensure destination directory exists
    dst_dir = os.path.dirname(args.dst)
    if dst_dir and not os.path.exists(dst_dir):
        logger.info(f"Creating destination directory: {dst_dir}")
        os.makedirs(dst_dir)
    
    # setup socket
    clientSocket = socket(AF_INET, SOCK_DGRAM)
    logger.debug("Socket created")
    
    logger.info(f"Downloading file '{args.name}' from {args.host}:{args.port}")
    logger.debug(f"Saving to: {args.dst}")
    logger.debug(f"Using protocol: {args.protocol}")
    
    # TODO: DOWNLOAD IMPLEMENTATION
    # this is a placeholder with actual download logic using the library:
    # 
    # 1) create sender using factory:
    #    from lib import create_sender, Protocol
    #    sender = create_sender(Protocol(args.protocol), clientSocket, (args.host, args.port), logger)
    # 
    # 2) perform handshake (INIT with file_size=0 for download):
    #    success = sender._perform_handshake(args.name, 0)  # filename, file_size=0
    # 
    # 3) receive file data:
    #    if success:
    #        file_data = sender.receive_downloaded_file()  # TODO: implement this method
    #        
    #        # 4) Save file:
    #        with open(args.dst, 'wb') as f:
    #            f.write(file_data)
    #        logger.info(f"File downloaded successfully: {args.dst}")
    #    else:
    #        logger.error("Download failed")
    # 
    # 5) close socket and handle FIN/FIN-ACK automatically
    
    # PLACEHOLDER CODE (remove when implementing):
    message = f"DOWNLOAD {args.name}"
    clientSocket.sendto(message.encode(), (args.host, args.port))
    logger.debug("Download request sent")
    
    modifiedMessage, serverAddress = clientSocket.recvfrom(2048)
    logger.info(f"Server response: {modifiedMessage.decode()}")
    
    clientSocket.close()
    logger.debug("Socket closed")

main()