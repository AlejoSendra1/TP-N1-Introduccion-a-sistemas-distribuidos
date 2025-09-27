"""
RDT Protocol Library
Reliable Data Transfer protocols with modular architecture

This library provides implementations for:
- Stop & Wait protocol (simple, reliable)
- Selective Repeat protocol (advanced, efficient)

Usage:
    from lib import create_sender, create_receiver, Protocol
    
    # Create a sender
    sender = create_sender(Protocol.STOP_WAIT, socket, dest_addr, logger)
    
    # Send a file
    success = sender.send_file("path/to/file.txt", "file.txt")

TODO: DOWNLOAD IMPLEMENTATION
when implementing download, add to exports:
- DownloadRequest (new class in session.py)
- receive_downloaded_file method in AbstractSender
"""

# Main factory functions - primary public API
from .factory import create_sender, create_receiver

# Protocol and utility exports
from .base import (
    Protocol,
    PacketType, 
    RDTPacket,
    request_shutdown,
    is_shutdown_requested,
    wait_for_init_packet,
    PACKET_SIZE,
    TIMEOUT,
    MAX_RETRIES,
    WINDOW_SIZE,
    DATA_BUFFER_SIZE,
    SW_DATA_BUFFER_SIZE
)

# Concrete implementations (for advanced usage)
from .stop_wait import RDTSender, RDTReceiver
from .selective_repeat import SelectiveRepeatSender, SelectiveRepeatReceiver

# Abstract base classes (for extending the library)
from .base import AbstractSender, AbstractReceiver

# Define what gets exported with "from lib import *"
__all__ = [
    # Primary API
    'create_sender',
    'create_receiver',
    'Protocol',
    
    # Utilities
    'request_shutdown',
    'is_shutdown_requested',
    'wait_for_init_packet',
    'PacketType',
    'RDTPacket',
    
    # Constants
    'PACKET_SIZE',
    'TIMEOUT', 
    'MAX_RETRIES',
    'WINDOW_SIZE',
    'DATA_BUFFER_SIZE',
    'SW_DATA_BUFFER_SIZE',
    
    # Concrete implementations
    'RDTSender',
    'RDTReceiver', 
    'SelectiveRepeatSender',
    'SelectiveRepeatReceiver',
    
    # Abstract classes
    'AbstractSender',
    'AbstractReceiver',
]

