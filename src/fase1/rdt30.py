# =====================
# fase1/rdt30.py
# =====================
"""Implementação rdt3.0 (rdt2.1 + timer para perdas).
Remetente usa timeout para retransmitir; receptor igual ao rdt2.1.
"""
from fase1.rdt21 import RDT21Receiver, RDT21Sender
import socket
import threading
import time
from utils import simulator
from utils import packet as pkt

class RDT30Sender:
    def __init__(self, local_port, dest_addr, channel: simulator.UnreliableChannel=None):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('localhost', local_port))
        self.dest_addr = dest_addr
        self.channel = channel
        self.seq = 0

    def send(self, data: bytes, timeout=2.0):
        retransmissions = 0
        packet = pkt.pack_rdt21(pkt.TYPE_DATA, self.seq, data)
        while True:
            if self.channel:
                self.channel.send(packet, self.sock, self.dest_addr)
            else:
                self.sock.sendto(packet, self.dest_addr)

            start = time.time()
            self.sock.settimeout(timeout)
            try:
                resp, _ = self.sock.recvfrom(4096)
            except socket.timeout:
                retransmissions += 1
                print('[SENDER30] Timeout, retransmitindo')
                continue
            # process ack
            out = pkt.unpack_rdt21(resp)
            if out is None:
                retransmissions += 1
                continue
            t, seqnum, chksum, payload = out
            if t == pkt.TYPE_ACK and seqnum == self.seq:
                # sucesso
                self.seq ^= 1
                return retransmissions
            else:
                retransmissions += 1
                print('[SENDER30] ACK incorreto, retransmitindo')

# receptor pode ser o mesmo do rdt21
class RDT30Receiver(RDT21Receiver):
    pass