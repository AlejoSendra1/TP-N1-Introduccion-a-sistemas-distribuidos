"""
Stop & Wait RDT Protocol Implementation
Simple reliable data transfer with alternating sequence numbers
"""

import socket
from typing import List, Tuple
from .base import (
    AbstractSender, AbstractReceiver, RDTPacket, PacketType, Protocol,
    MAX_RETRIES, ACK_BUFFER_SIZE, DATA_BUFFER_SIZE, 
    SW_PACKET_SIZE, SW_TIMEOUT, HANDSHAKE_TIMEOUT, FIN_TIMEOUT, is_shutdown_requested
)


class RDTSender(AbstractSender):
    """RDT sender implementation with Stop & Wait protocol"""
    
    def __init__(self, socket: socket.socket, dest_addr: Tuple[str, int], logger):
        super().__init__(socket, dest_addr, logger)
        self.seq_num = 0
        self.session_id = None
        self.socket.settimeout(SW_TIMEOUT)
    
    def _prepare_packets(self, filepath: str, filename: str) -> List[RDTPacket]:
        """Prepare packets from file using SW_PACKET_SIZE for Stop & Wait"""
        packets = []
        
        with open(filepath, 'rb') as file:
            chunk_index = 0
            
            while True:
                chunk = file.read(SW_PACKET_SIZE)
                if not chunk:
                    break
                
                # check if this is the last chunk by trying to read one more byte
                next_byte = file.read(1)
                is_last = len(next_byte) == 0
                
                # if not last, put the byte back
                if not is_last:
                    file.seek(file.tell() - 1)
                
                packet = RDTPacket(
                    seq_num=chunk_index,
                    packet_type=PacketType.DATA,
                    data=chunk,
                    filename=filename if chunk_index == 0 else '',
                    is_last=is_last
                )
                packets.append(packet)
                chunk_index += 1
                
                if is_last:
                    break
        
        return packets
    
    def _send_packets(self, packets: List[RDTPacket]) -> bool:
        """Send packets using Stop & Wait protocol"""
        # perform handshake first
        if not self._perform_handshake(packets[0].filename, len(packets) * SW_PACKET_SIZE):
            return False
            
        for i, packet in enumerate(packets):
            # check for shutdown request
            if is_shutdown_requested():
                self.logger.info("Upload cancelled due to shutdown request")
                return False
            
            # update sequence number (alternating 0, 1)
            packet.seq_num = self.seq_num
            packet.session_id = self.session_id  # add session ID to all packets
            packet.calculate_checksum()  # recalculate after changes
            
            if self._send_packet_reliable(packet):
                self.logger.debug(f"Packet {self.seq_num} sent successfully")
                self.seq_num = 1 - self.seq_num  # alternate between 0 and 1
                
                # if this was the last packet, we're done with data transfer
                if packet.is_last:
                    self.logger.info("Last packet sent and acknowledged")
                    break
            else:
                self.logger.error(f"Failed to send packet {self.seq_num}")
                return False
        
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
                self.socket.settimeout(original_timeout)
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
                    
            except socket.timeout:
                self.logger.debug(f"Timeout waiting for FIN ACK, retrying...")
            except Exception as e:
                self.logger.error(f"Error sending FIN: {e}")
                self.socket.settimeout(original_timeout)
                return False
        
        self.logger.error("Failed to close session with FIN")
        self.socket.settimeout(original_timeout)
        return False
    
    def _send_packet_reliable(self, packet: RDTPacket) -> bool:
        """Send packet with retransmission on timeout"""
        for attempt in range(MAX_RETRIES):
            # check for shutdown during retries
            if is_shutdown_requested():
                self.logger.info("Upload cancelled during retransmission")
                return False
            
            try:
                # send packet
                self.socket.sendto(packet.to_bytes(), self.dest_addr)
                self.logger.debug(f"Sent packet {packet.seq_num} (attempt {attempt + 1})")
                
                # wait for ACK
                ack_data, addr = self.socket.recvfrom(ACK_BUFFER_SIZE)
                ack_packet = RDTPacket.from_bytes(ack_data)
                
                # verify ACK
                if (ack_packet.packet_type == PacketType.ACK and 
                    ack_packet.ack_num == packet.seq_num and 
                    ack_packet.verify_checksum()):
                    self.logger.debug(f"Received ACK for packet {packet.seq_num}")
                    return True
                else:
                    self.logger.debug(f"Invalid ACK for packet {packet.seq_num}, retrying...")
                    
            except socket.timeout:
                self.logger.debug(f"Timeout for packet {packet.seq_num}, retrying...")
            except Exception as e:
                self.logger.error(f"Error sending packet {packet.seq_num}: {e}")
                return False
        
        self.logger.error(f"Failed to send packet {packet.seq_num} after {MAX_RETRIES} attempts")
        return False
    
    def _perform_handshake(self, filename: str, file_size: int) -> bool:
        """Perform handshake with server"""
        # Create INIT packet
        init_packet = RDTPacket(
            packet_type=PacketType.INIT,
            filename=filename,
            file_size=file_size,
            protocol=Protocol.STOP_WAIT
        )
        
        # longer timeout for handshake
        original_timeout = self.socket.gettimeout()
        self.socket.settimeout(HANDSHAKE_TIMEOUT)
        
        for attempt in range(MAX_RETRIES):
            if is_shutdown_requested():
                self.socket.settimeout(original_timeout)
                return False
                
            try:
                # Send INIT
                self.socket.sendto(init_packet.to_bytes(), self.dest_addr)
                self.logger.debug(f"Sent INIT packet (attempt {attempt + 1})")
                
                # Wait for ACCEPT
                accept_data, addr = self.socket.recvfrom(ACK_BUFFER_SIZE)
                accept_packet = RDTPacket.from_bytes(accept_data)
                
                if (accept_packet.packet_type == PacketType.ACCEPT and 
                    accept_packet.session_id and 
                    accept_packet.verify_checksum()):
                    
                    self.session_id = accept_packet.session_id
                    self.logger.info(f"Handshake successful, session ID: {self.session_id}")
                    self.socket.settimeout(original_timeout)
                    return True
                    
            except socket.timeout:
                self.logger.debug(f"Timeout waiting for ACCEPT, retrying...")
            except Exception as e:
                self.logger.error(f"Error during handshake: {e}")
                self.socket.settimeout(original_timeout)
                return False
                
        self.logger.error("Failed to establish session")
        self.socket.settimeout(original_timeout)
        return False


class RDTReceiver(AbstractReceiver):
    """RDT receiver implementation with Stop & Wait protocol"""
    
    def __init__(self, socket: socket.socket, logger):
        super().__init__(socket, logger)
        self.expected_seq = 0
    
    def receive_file_with_first_packet(self, first_packet: RDTPacket, addr: Tuple[str, int]) -> Tuple[bool, bytes]:
        """Receive file starting with first packet"""
        if not first_packet.verify_checksum():
            self.logger.error("First packet has invalid checksum")
            return False, b''
        
        if first_packet.seq_num != self.expected_seq:
            self.logger.warning(f"Unexpected sequence number {first_packet.seq_num}, expected {self.expected_seq}")
            # send ACK for the expected sequence number (previous packet)
            ack = RDTPacket(seq_num=0, packet_type=PacketType.ACK, ack_num=1-self.expected_seq)
            self.socket.sendto(ack.to_bytes(), addr)
            return False, b''
        
        file_data = first_packet.data
        filename = first_packet.filename
        
        # send ACK for first packet (include session_id if present)
        ack = RDTPacket(seq_num=0, packet_type=PacketType.ACK, ack_num=first_packet.seq_num,
                       session_id=first_packet.session_id if hasattr(first_packet, 'session_id') and first_packet.session_id else '')
        
        self.socket.sendto(ack.to_bytes(), addr)
        self.logger.debug(f"Sent ACK for packet {first_packet.seq_num}")
        
        if first_packet.is_last:
            self.logger.info(f"File {filename} received completely in one packet")
            return True, file_data
        
        # continue receiving remaining packets
        self.expected_seq = 1 - self.expected_seq
        success, remaining_data = self._continue_receiving(addr)
        
        if success:
            return True, file_data + remaining_data
        else:
            return False, b''
    
    def _continue_receiving(self, addr: Tuple[str, int]) -> Tuple[bool, bytes]:
        """Continue receiving remaining packets"""
        file_data = b''
        
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
                
                if not packet.verify_checksum():
                    self.logger.error(f"Packet {packet.seq_num} has invalid checksum")
                    continue
                
                if packet.seq_num == self.expected_seq:
                    # correct packet received
                    file_data += packet.data
                    
                    # send ACK (include session_id if present)
                    ack = RDTPacket(seq_num=0, packet_type=PacketType.ACK, ack_num=packet.seq_num,
                                   session_id=packet.session_id if hasattr(packet, 'session_id') and packet.session_id else '')
                    
                    self.socket.sendto(ack.to_bytes(), addr)
                    self.logger.debug(f"Sent ACK for packet {packet.seq_num}")
                    
                    if packet.is_last:
                        self.logger.info("File received completely")
                        return True, file_data
                    
                    # prepare for next packet
                    self.expected_seq = 1 - self.expected_seq
                    
                else:
                    # duplicate or out-of-order packet
                    self.logger.debug(f"Duplicate packet {packet.seq_num}, expected {self.expected_seq}")
                    # send ACK for the received packet (duplicate ACK with session_id if present)
                    ack = RDTPacket(seq_num=0, packet_type=PacketType.ACK, ack_num=packet.seq_num,
                                   session_id=packet.session_id if hasattr(packet, 'session_id') and packet.session_id else '')
                    
                    self.socket.sendto(ack.to_bytes(), addr)
                    
            except socket.timeout:
                self.logger.debug("Timeout waiting for packet")
                continue
            except Exception as e:
                self.logger.error(f"Error receiving packet: {e}")
                return False, b''
