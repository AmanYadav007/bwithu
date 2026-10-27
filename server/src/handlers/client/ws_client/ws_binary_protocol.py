"""
WebSocket binary protocol
Packing and unpacking of binary data
"""
import struct
from typing import Optional, List, Tuple
from dataclasses import dataclass
from loguru import logger


# ============================================================================
# Binary packet header
# ============================================================================

@dataclass
class BinaryPacketHeader:
    """
    Binary packet header (36 bytes)
    
    Header (36 bytes):
      - Magic: "JBIN" (4 bytes)
      - Request Id: "xxx" (8 bytes, first 8 characters of request_id)
      - Packet Type: 0 (4 bytes, 0=audio, 1=video)
      - Packet Index: 0 (4 bytes, index of this packet)
      - Total Packets: 2 (4 bytes, total packets)
      - Data Size: 20000 (4 bytes, data size of this packet)
      - Reserved: 0 (8 bytes, reserved)
    """
    magic: bytes  # 4 bytes: b"JBIN"
    request_id: str  # 8 bytes: first 8 characters of request_id
    packet_type: int  # 4 bytes: 0=audio, 1=video
    packet_index: int  # 4 bytes: index of this packet
    total_packets: int  # 4 bytes: total packets
    data_size: int  # 4 bytes: data size of this packet
    reserved: int  # 8 bytes: reserved
    
    HEADER_SIZE = 36
    MAGIC = b"JBIN"
    
    @classmethod
    def parse(cls, data: bytes) -> Optional['BinaryPacketHeader']:
        """
        Parse a binary packet header
        
        Args:
            data: at least 36 bytes
            
        Returns:
            The parsed header, or None if parsing fails
        """
        if len(data) < cls.HEADER_SIZE:
            return None
        
        try:
            # Unpack: 4s(magic) + 8s(request_id) + 4I(four uint32) + Q(uint64)
            unpacked = struct.unpack("<4s8s4IQ", data[:cls.HEADER_SIZE])
            
            magic = unpacked[0]
            if magic != cls.MAGIC:
                logger.warning(f"Invalid magic: {magic}, expected {cls.MAGIC}")
                return None
            
            request_id = unpacked[1].decode('utf-8', errors='ignore').rstrip('\x00')
            packet_type = unpacked[2]
            packet_index = unpacked[3]
            total_packets = unpacked[4]
            data_size = unpacked[5]
            reserved = unpacked[6]
            
            return cls(
                magic=magic,
                request_id=request_id,
                packet_type=packet_type,
                packet_index=packet_index,
                total_packets=total_packets,
                data_size=data_size,
                reserved=reserved
            )
        except Exception as e:
            logger.error(f"Failed to parse binary packet header: {e}")
            return None
    
    def pack(self) -> bytes:
        """
        Pack the header into bytes
        
        Returns:
            36 bytes
        """
        # Make request_id exactly 8 bytes
        request_id_bytes = self.request_id[:8].encode('utf-8')
        request_id_bytes = request_id_bytes.ljust(8, b'\x00')
        
        return struct.pack(
            "<4s8s4IQ",
            self.magic,
            request_id_bytes,
            self.packet_type,
            self.packet_index,
            self.total_packets,
            self.data_size,
            self.reserved
        )


# ============================================================================
# Binary packet assembler (for receiving segmented data)
# ============================================================================

@dataclass
class StreamAssemblyState:
    """Assembly state of one human audio/video binary stream"""
    request_id: str
    expected_segments: int
    expected_size: int
    metadata: Optional[object] = None
    received_segments: int = 0
    received_size: int = 0
    chunks: List[bytes] = None
    
    def __post_init__(self):
        if self.chunks is None:
            self.chunks = []
    
    def append(self, chunk: bytes) -> Optional[bytes]:
        """Append a segment; returns the complete data once all segments are in"""
        self.chunks.append(chunk)
        self.received_segments += 1
        self.received_size += len(chunk)
        
        if self.received_segments >= self.expected_segments or self.received_size >= self.expected_size:
            data = b"".join(self.chunks)
            if self.expected_size and self.expected_size != len(data):
                logger.warning(
                    f"Binary data size mismatch for request_id={self.request_id}: "
                    f"expected={self.expected_size}, actual={len(data)}"
                )
            return data
        return None


class BinaryStreamAssembler:
    """
    Binary stream assembler
    Assembles header-less binary segments in registration order (basic audio/video upload)
    """
    
    def __init__(self):
        from collections import deque
        self._queue = deque()  # type: ignore[var-annotated]
    
    def register(self, request_id: str, expected_segments: int, expected_size: int,
                 metadata: Optional[object] = None) -> StreamAssemblyState:
        state = StreamAssemblyState(
            request_id=request_id,
            expected_segments=expected_segments,
            expected_size=expected_size,
            metadata=metadata or {}
        )
        self._queue.append(state)
        return state
    
    def append(self, chunk: bytes) -> Optional[Tuple[StreamAssemblyState, bytes]]:
        if not self._queue:
            logger.warning("Received unexpected binary chunk with no pending registrations")
            return None
        
        state = self._queue[0]
        data = state.append(chunk)
        if data is not None:
            self._queue.popleft()
            return state, data
        return None
    
    def clear(self):
        self._queue.clear()


# ============================================================================
# Binary packet splitter (for sending large data)
# ============================================================================

class BinaryPacketSplitter:
    """
    Binary packet splitter
    Splits large data into fixed-size segments
    """
    
    # Motion data output segment size: 16 KB
    MOTION_DATA_SEGMENT_SIZE = 16 * 1024
    
    @staticmethod
    def split(request_id: str, packet_type: int, data: bytes, 
              segment_size: int = MOTION_DATA_SEGMENT_SIZE) -> List[bytes]:
        """
        Split data into segments
        
        Args:
            request_id: request ID
            packet_type: data type (0=audio, 1=video)
            data: the data to split
            segment_size: size of each segment (excluding the header)
            
        Returns:
            List of segments, each with header and data
        """
        if len(data) == 0:
            # Empty data: return one empty packet
            # header = BinaryPacketHeader(
            #     magic=BinaryPacketHeader.MAGIC,
            #     request_id=request_id,
            #     packet_type=packet_type,
            #     packet_index=0,
            #     total_packets=1,
            #     data_size=0,
            #     reserved=0
            # )
            return [b""]
        
        # Total number of segments
        total_packets = (len(data) + segment_size - 1) // segment_size
        
        packets = []
        for i in range(total_packets):
            start = i * segment_size
            end = min(start + segment_size, len(data))
            segment_data = data[start:end]
            
            # header = BinaryPacketHeader(
            #     magic=BinaryPacketHeader.MAGIC,
            #     request_id=request_id,
            #     packet_type=packet_type,
            #     packet_index=i,
            #     total_packets=total_packets,
            #     data_size=len(segment_data),
            #     reserved=0
            # )
            
            packet = segment_data
            packets.append(packet)
        
        return packets

