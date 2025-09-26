import socket
import argparse
import os
import logging
import signal
import sys
from lib import RDTServer
from lib.factory import create_sender
from lib.session import DownloadRequest, TransferRequest
from lib.base import Protocol

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
        
        # create RDT server
        rdt_server = RDTServer(sock, logger)
        
        while not killer.kill_now:
            # wait for transfer request
            request = rdt_server.wait_for_transfer(timeout=1.0)
            
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
    
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Server error: {e}")
    finally:
        sock.close()
        logger.info("Server stopped")


if __name__ == '__main__':
    main()