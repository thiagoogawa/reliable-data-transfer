# =====================
# fase1/rdt21.py
# =====================
"""Implementação rdt2.1 (stop-and-wait com seqnum alternante)
"""
import socket
import threading
import time
from utils import simulator
from utils import packet as pkt

class RDT21Sender:
    def __init__(self, local_port, dest_addr, channel: simulator.UnreliableChannel=None):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('localhost', local_port))
        self.dest_addr = dest_addr
        self.channel = channel
        self.seq = 0

    def send(self, data: bytes, timeout=2.0):
        retransmissions = 0
        while True:
            packet = pkt.pack_rdt21(pkt.TYPE_DATA, self.seq, data)
            if self.channel:
                self.channel.send(packet, self.sock, self.dest_addr)
            else:
                self.sock.sendto(packet, self.dest_addr)

            self.sock.settimeout(timeout)
            try:
                resp, _ = self.sock.recvfrom(4096)
            except socket.timeout:
                retransmissions += 1
                print('[SENDER21] Timeout, retransmitindo')
                continue

            out = pkt.unpack_rdt21(resp)
            if out is None:
                retransmissions += 1
                print('[SENDER21] Ack corrupto, retransmitindo')
                continue
            t, seqnum, chksum, payload = out
            # ack packet: TYPE_ACK with seqnum
            # recompute checksum of header
            header = struct.pack('!BB', t, seqnum)
            calc = pkt.checksum(header)
            # OBS: acknowledgments aqui não carregam dados; checksum only on header
            if t == pkt.TYPE_ACK and seqnum == self.seq:
                # sucesso
                self.seq ^= 1
                return retransmissions
            else:
                retransmissions += 1
                print('[SENDER21] ACK incorreto ou duplicado, retransmitindo')

class RDT21Receiver:
    def __init__(self, local_port, channel: simulator.UnreliableChannel=None):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('localhost', local_port))
        self.channel = channel
        self.expected = 0
        self.app_buffer = []
        self.running = True
        self.thread = threading.Thread(target=self._recv_loop, daemon=True)
        self.thread.start()

    def _recv_loop(self):
        while self.running:
            try:
                pkt_data, addr = self.sock.recvfrom(65536)
            except Exception:
                continue
            out = pkt.unpack_rdt21(pkt_data)
            if out is None:
                continue
            t, seqnum, chksum, data = out
            if t != pkt.TYPE_DATA:
                continue
            # verificar checksum
            calc = pkt.checksum(struct.pack('!B', t) + struct.pack('!B', seqnum) + data)
            if calc != chksum:
                # enviar ACK do último (como NAK não usado)
                # Aqui usamos NAK (compatível com rdt2.1) para simplificar
                nak = pkt.pack_rdt21(pkt.TYPE_NAK, seqnum)
                if self.channel:
                    self.channel.send(nak, self.sock, addr)
                else:
                    self.sock.sendto(nak, addr)
                print('[RECV21] Pacote corrompido - NAK enviado')
                continue
            # Se for o esperado
            if seqnum == self.expected:
                self.app_buffer.append(data)
                ack = pkt.pack_rdt21(pkt.TYPE_ACK, seqnum)
                if self.channel:
                    self.channel.send(ack, self.sock, addr)
                else:
                    self.sock.sendto(ack, addr)
                self.expected ^= 1
            else:
                # duplicado: reenviar ack do último entregue (expected^1)
                last = self.expected ^ 1
                ack = pkt.pack_rdt21(pkt.TYPE_ACK, last)
                if self.channel:
                    self.channel.send(ack, self.sock, addr)
                else:
                    self.sock.sendto(ack, addr)
                print('[RECV21] Pacote duplicado - ACK reenviado')

    def get_all_messages(self):
        buf = self.app_buffer[:]
        self.app_buffer = []
        return buf

    def stop(self):
        self.running = False
        try:
            self.sock.close()
        except Exception:
            pass
