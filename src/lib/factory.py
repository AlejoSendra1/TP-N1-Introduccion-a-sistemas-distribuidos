"""
Factory methods for creating RDT protocol implementations
Provides a clean interface for instantiating senders and receivers

TODO: DOWNLOAD IMPLEMENTATION
The factory is already prepared for download functionality:
- create_sender() can be used by server to send files to clients
- create_receiver() can be used by clients to receive files from server
- No changes needed to factory methods
"""

import socket
from typing import Tuple
from .base import AbstractSender, AbstractReceiver, Protocol
from .stop_wait import RDTSender, RDTReceiver
from .selective_repeat import SelectiveRepeatSender, SelectiveRepeatReceiver


def create_sender(protocol: Protocol, socket: socket.socket, dest_addr: Tuple[str, int], logger) -> AbstractSender:
    """
    Factory method to create appropriate sender based on protocol
    
    Args:
        protocol: The RDT protocol to use (STOP_WAIT or SELECTIVE_REPEAT)
        socket: UDP socket for communication
        dest_addr: Destination address (host, port)
        logger: Logger instance
        
    Returns:
        AbstractSender: Concrete sender implementation
        
    Raises:
        ValueError: If protocol is not supported
    """
    if protocol == Protocol.STOP_WAIT:
        return RDTSender(socket, dest_addr, logger)
    elif protocol == Protocol.SELECTIVE_REPEAT:
        return SelectiveRepeatSender(socket, dest_addr, logger)


def create_receiver(protocol: Protocol, socket: socket.socket, logger) -> AbstractReceiver:
    """
    Factory method to create appropriate receiver based on protocol
    
    Args:
        protocol: The RDT protocol to use (STOP_WAIT or SELECTIVE_REPEAT)
        socket: UDP socket for communication
        logger: Logger instance
        
    Returns:
        AbstractReceiver: Concrete receiver implementation
        
    Raises:
        ValueError: If protocol is not supported
    """
    if protocol == Protocol.STOP_WAIT:
        return RDTReceiver(socket, logger) # TODO: rename to StopWaitReceiver
    elif protocol == Protocol.SELECTIVE_REPEAT:
        return SelectiveRepeatReceiver(socket, logger)
    else:
        raise ValueError(f"Unknown protocol: {protocol}")


# Convenience functions for common use cases
def create_stop_wait_sender(socket: socket.socket, dest_addr: Tuple[str, int], logger) -> RDTSender:
    """Create a Stop & Wait sender"""
    return RDTSender(socket, dest_addr, logger)


def create_stop_wait_receiver(socket: socket.socket, logger) -> RDTReceiver:
    """Create a Stop & Wait receiver"""
    return RDTReceiver(socket, logger)


def create_selective_repeat_sender(socket: socket.socket, dest_addr: Tuple[str, int], logger) -> SelectiveRepeatSender:
    """Create a Selective Repeat sender"""
    return SelectiveRepeatSender(socket, dest_addr, logger)


def create_selective_repeat_receiver(socket: socket.socket, logger) -> SelectiveRepeatReceiver:
    """Create a Selective Repeat receiver"""
    return SelectiveRepeatReceiver(socket, logger)

