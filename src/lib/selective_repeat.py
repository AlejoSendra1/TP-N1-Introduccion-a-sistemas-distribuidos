"""
Selective Repeat RDT Protocol Implementation
Reliable data transfer with sliding window and selective retransmission
"""

import socket
from typing import List, Tuple, Dict
from .base import (
    AbstractSender, AbstractReceiver, RDTPacket, PacketType, Protocol, PacketTimer,
    TIMEOUT, MAX_RETRIES, WINDOW_SIZE, PACKET_SIZE, ACK_BUFFER_SIZE, DATA_BUFFER_SIZE, 
    HANDSHAKE_TIMEOUT, FIN_TIMEOUT, is_shutdown_requested
)


class SelectiveRepeatSender(AbstractSender):
    """Selective Repeat sender implementation with sliding window"""
    
    def __init__(self, socket: socket.socket, dest_addr: Tuple[str, int], logger, window_size: int = WINDOW_SIZE):
        super().__init__(socket, dest_addr, logger)
        self.window_size = window_size
        
        # selective repeat state variables (as per theory)
        self.send_base = 0  # oldest unacknowledged packet
        self.nextseqnum = 0  # next available sequence number
        self.send_window: Dict[int, Tuple[RDTPacket, PacketTimer]] = {}  # {seq_num: (packet, timer)}
        self.session_id = None
        
        self.socket.settimeout(0.1)  # non-blocking socket for checking timers
    
    def _send_packets(self, packets: List[RDTPacket]) -> bool:
        """Send packets using selective repeat protocol"""
        total_packets = len(packets)
        
        # perform handshake first (INIT pkg)
        if total_packets > 0:
            file_size = sum(len(p.data) for p in packets if p.data)
            self.logger.debug(f"Calculated file_size: {file_size} from {total_packets} packets")
            
            self.socket.settimeout(TIMEOUT)
            if not self._perform_handshake(self.filename, file_size):
                return False
            self.socket.settimeout(0.1)  # Back to non-blocking
        
        while self.send_base < total_packets or len(self.send_window) > 0:
            # check for shutdown request
            if is_shutdown_requested():
                self.logger.info("Upload cancelled due to shutdown request")
                return False
            
            # send new packets within window
            while (self.nextseqnum < total_packets and 
                   self.nextseqnum < self.send_base + self.window_size):
                
                packet = packets[self.nextseqnum]
                packet.seq_num = self.nextseqnum
                
                # add session ID to all packets
                if self.session_id:
                    packet.session_id = self.session_id
                    
                packet.calculate_checksum()
                
                # send packet
                self.socket.sendto(packet.to_bytes(), self.dest_addr)
                self.logger.debug(f"Sent packet {self.nextseqnum}")
                
                # add to window with timer
                timer = PacketTimer()
                self.send_window[self.nextseqnum] = (packet, timer)
                
                self.nextseqnum += 1
            
            # handle ACKs and timeouts
            if not self._handle_acks_and_timeouts():
                return False
        
        self.logger.info("All packets sent and acknowledged successfully")
        
        # send FIN to close session
        if self._send_fin():
            self.logger.info("Session closed successfully")
            return True
        else:
            self.logger.error("Failed to close session")
            return False
    
    def _send_fin(self) -> bool:
        """Send FIN packet to close session"""
        if not self.session_id:
            self.logger.warning("No session ID for FIN packet")
            return True  # no session to close
            
        fin_packet = RDTPacket(
            packet_type=PacketType.FIN,
            session_id=self.session_id
        )
        
        # longer timeout for FIN handshake
        original_timeout = self.socket.gettimeout()
        self.socket.settimeout(FIN_TIMEOUT)
        
        for attempt in range(MAX_RETRIES):
            if is_shutdown_requested():
                return False
                
            try:
                self.socket.sendto(fin_packet.to_bytes(), self.dest_addr)
                self.logger.debug(f"Sent FIN packet (attempt {attempt + 1})")
                
                # wait for FIN ACK
                ack_data, addr = self.socket.recvfrom(ACK_BUFFER_SIZE)
                ack_packet = RDTPacket.from_bytes(ack_data)
                
                if (ack_packet.packet_type == PacketType.ACK and 
                    ack_packet.session_id == self.session_id):
                    self.logger.debug("Received FIN ACK")
                    self.socket.settimeout(original_timeout)
                    return True
                else:
                    self.logger.debug(f"Invalid FIN ACK, retrying...")
                    
            except socket.timeout as e:
                self.logger.debug(f"Timeout waiting for FIN ACK, retrying...")
            except Exception as e:
                self.logger.error(f"Error sending FIN: {e}")
                self.socket.settimeout(original_timeout)
                return False
        
        self.logger.error("Failed to close session with FIN")
        self.socket.settimeout(original_timeout)
        return False
    
    def _handle_acks_and_timeouts(self):
        """Handle incoming ACKs and expired timers"""
        try:
            # try to receive ACK (non-blocking)
            ack_data, _addr = self.socket.recvfrom(ACK_BUFFER_SIZE)
            ack_packet = RDTPacket.from_bytes(ack_data)
            
            if (ack_packet.packet_type == PacketType.ACK and 
                ack_packet.verify_checksum() and
                ack_packet.ack_num in self.send_window):
                
                # remove acknowledged packet from window
                del self.send_window[ack_packet.ack_num]
                self.logger.debug(f"Received ACK for packet {ack_packet.ack_num}")
                
                # advance send_base if possible
                while self.send_base not in self.send_window and self.send_base < self.nextseqnum:
                    self.send_base += 1
                
                self.logger.debug(f"Send base advanced to {self.send_base}")
                
                # session ID should already be set from handshake
            
        except socket.timeout as e:
            pass  # no ACK received, continue
        except Exception as e:
            self.logger.error(f"Error receiving ACK: {e}")
            return False
        
        # check for expired timers and retransmit
        expired_packets = []
        for seq_num, (packet, timer) in self.send_window.items():
            if timer.is_expired():
                expired_packets.append(seq_num)
        
        for seq_num in expired_packets:
            packet, timer = self.send_window[seq_num]
            
            # retransmit packet
            self.socket.sendto(packet.to_bytes(), self.dest_addr)
            self.logger.debug(f"Retransmitted packet {seq_num}")
            
            # reset timer
            timer.reset()
        
        return True
    
    def _perform_handshake(self, filename: str, file_size: int) -> bool:
        """Perform handshake with server"""
        # create INIT packet
        try:
            init_packet = RDTPacket(
                packet_type=PacketType.INIT,
                filename=filename,
                file_size=file_size,
                protocol=Protocol.SELECTIVE_REPEAT,
                data=b''
            )
        except Exception as e:
            self.logger.error(f"Error creating INIT packet: {e}")
            self.logger.error(f"filename type: {type(filename)}, value: {filename}")
            self.logger.error(f"file_size type: {type(file_size)}, value: {file_size}")
            raise
        
        # longer timeout for handshake
        original_timeout = self.socket.gettimeout()
        self.socket.settimeout(HANDSHAKE_TIMEOUT)
        
        for attempt in range(MAX_RETRIES):
            if is_shutdown_requested():
                self.socket.settimeout(original_timeout)
                return False
                
            try:
                # send INIT
                self.socket.sendto(init_packet.to_bytes(), self.dest_addr)
                self.logger.debug(f"Sent INIT packet (attempt {attempt + 1})")
                
                # wait for ACCEPT
                accept_data, addr = self.socket.recvfrom(ACK_BUFFER_SIZE)
                accept_packet = RDTPacket.from_bytes(accept_data)
                
                if (accept_packet.packet_type == PacketType.ACCEPT and 
                    accept_packet.session_id and 
                    accept_packet.verify_checksum()):
                    
                    self.session_id = accept_packet.session_id
                    self.logger.info(f"Handshake successful, session ID: {self.session_id}")
                    self.socket.settimeout(original_timeout)
                    return True
                    
            except socket.timeout as e:
                self.logger.debug(f"Timeout waiting for ACCEPT, retrying...")
            except Exception as e:
                self.logger.error(f"Error during handshake: {e}")
                self.socket.settimeout(original_timeout)
                return False
                
        self.logger.error("Failed to establish session")
        self.socket.settimeout(original_timeout)
        return False

class SelectiveRepeatReceiver(AbstractReceiver):
    """Selective Repeat receiver implementation with buffering"""
    
    def __init__(self, socket: socket.socket, logger, window_size: int = WINDOW_SIZE):
        super().__init__(socket, logger)
        self.window_size = window_size
        self.rcv_base = 0  # oldest expected packet
        self.rcv_window: Dict[int, RDTPacket] = {}  # {seq_num: packet}
        self.received_data = b''  # Accumulator for all received data
    
    def receive_file_with_first_packet(self, first_packet: RDTPacket, addr: Tuple[str, int]) -> Tuple[bool, bytes]:
        """Receive file starting with first packet"""
        self.logger.info("Starting file reception with Selective Repeat")
        
        # process first packet
        complete = self._process_packet(first_packet, addr)
        if complete:
            # file is complete, but continue receiving until FIN
            self.logger.info("File transfer complete, waiting for FIN")
        
        # continue receiving packets
        while True:
            # check for shutdown request
            if is_shutdown_requested():
                self.logger.info("File reception cancelled due to shutdown request")
                return False, b''
            
            try:
                data, client_addr = self.socket.recvfrom(DATA_BUFFER_SIZE)
                
                if client_addr != addr:
                    self.logger.warning(f"Received packet from unexpected address: {client_addr}")
                    continue
                
                packet = RDTPacket.from_bytes(data)
                
                # check if this is a FIN packet
                if packet.packet_type == PacketType.FIN:
                    self.logger.info("Received FIN packet, file transfer complete")
                    return True, self.received_data
                
                # process regular DATA packet
                complete = self._process_packet(packet, addr)
                
                # don't return here - continue until FIN
                    
            except socket.timeout as e:
                continue
            except Exception as e:
                self.logger.error(f"Error receiving packet: {e}")
                return False, b''
    
    def _process_packet(self, packet: RDTPacket, addr: Tuple[str, int]) -> bool:
        """Process a received packet and return is_complete"""
        seq_num = packet.seq_num
        
        # always send ACK (even for duplicates or out-of-order)
        # Include session_id if packet has it
        ack = RDTPacket(seq_num=0, packet_type=PacketType.ACK, ack_num=seq_num,
                       session_id=packet.session_id if hasattr(packet, 'session_id') and packet.session_id else '')
        
        self.socket.sendto(ack.to_bytes(), addr)
        
        if not packet.verify_checksum():
            self.logger.error(f"Packet {seq_num} has invalid checksum")
            return False
        
        if seq_num >= self.rcv_base and seq_num < self.rcv_base + self.window_size:
            # packet is within receiver window
            if seq_num not in self.rcv_window:
                # new packet, buffer it
                self.rcv_window[seq_num] = packet
                self.logger.debug(f"Buffered packet {seq_num}")
            else:
                self.logger.debug(f"Duplicate packet {seq_num}")
            
            # deliver consecutive packets starting from rcv_base
            filename = ''
            is_complete = False
            
            while self.rcv_base in self.rcv_window:
                delivered_packet = self.rcv_window.pop(self.rcv_base)
                self.received_data += delivered_packet.data
                
                if self.rcv_base == 0:
                    filename = delivered_packet.filename
                
                self.logger.debug(f"Delivered packet {self.rcv_base}")
                
                self.rcv_base += 1
            
            if is_complete:
                # file is complete, but don't return yet - we're waiting for FIN
                return False
        
        elif seq_num < self.rcv_base:
            # packet is before receiver window (duplicate)
            self.logger.debug(f"Sent duplicate ACK for packet {seq_num}")
        
        else:
            # packet is outside receiver window (too far ahead)
            self.logger.debug(f"Packet {seq_num} outside receiver window, ignoring")
        
        return False
