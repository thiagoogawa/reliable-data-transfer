"""Funções utilitárias para empacotar e desempacotar pacotes simples.
Formato usado nas fases 1 e 2 (simplificado):
Tipo (1 byte), SeqNum (1 byte, opcional), Checksum (4 bytes, crc32), Dados...
"""
import struct
import zlib

# Types
TYPE_DATA = 0
TYPE_ACK = 1
TYPE_NAK = 2

def checksum(data: bytes) -> int:
    # usa crc32 truncado a 32 bits
    return zlib.crc32(data) & 0xffffffff

def pack_rdt20(data: bytes) -> bytes:
    # Tipo (1), Checksum (4), Dados
    chksum = checksum(data)
    return struct.pack('!BI', TYPE_DATA, chksum) + data

def unpack_rdt20(packet: bytes):
    try:
        if len(packet) < 5:
            return None
        t, chksum = struct.unpack('!BI', packet[:5])
        data = packet[5:]
        return t, chksum, data
    except Exception:
        return None

def pack_ack_rdt20(ack_type=TYPE_ACK) -> bytes:
    # ACK/NAK tem apenas Tipo (1)
    return struct.pack('!B', ack_type)

# rdt2.1: inclui SeqNum (1 byte) entre Tipo e Checksum
def pack_rdt21(type_byte: int, seqnum: int, data: bytes=b'') -> bytes:
    chksum = checksum(struct.pack('!B', type_byte) + struct.pack('!B', seqnum) + data)
    return struct.pack('!BBI', type_byte, seqnum, chksum) + data

def unpack_rdt21(packet: bytes):
    if len(packet) < 6:
        return None
    type_byte, seqnum, chksum = struct.unpack('!BBI', packet[:6])
    data = packet[6:]
    return type_byte, seqnum, chksum, data

# rdt3.0 usa rdt2.1 com timers (mesmo formato)