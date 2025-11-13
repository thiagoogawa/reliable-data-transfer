"""Implementação rdt2.0 (stop-and-wait, ACK/NAK, checksum) usando UDP local.
Para facilitar testes usamos sockets UDP em localhost com um UnreliableChannel opcional.
"""
import socket
import threading
import time
from utils import simulator
from utils import packet as pkt

class RDT20Sender:
    def __init__(self, local_port, dest_addr, channel: simulator.UnreliableChannel=None):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('localhost', local_port))
        self.dest_addr = dest_addr
        self.channel = channel
        self.lock = threading.Lock()

    def send(self, data: bytes, timeout=2.0):
        packet = pkt.pack_rdt20(data)
        retransmissions = 0
        while True:
            # enviar
            if self.channel:
                self.channel.send(packet, self.sock, self.dest_addr)
            else:
                self.sock.sendto(packet, self.dest_addr)

            # aguardar ack/nak
            self.sock.settimeout(timeout)
            try:
                resp, _ = self.sock.recvfrom(4096)
            except socket.timeout:
                retransmissions += 1
                print('[SENDER] Timeout, retransmitindo')
                continue

            # interpretar
            if len(resp) >= 1:
                t = resp[0]
                if t == pkt.TYPE_ACK:
                    # sucesso
                    return retransmissions
                elif t == pkt.TYPE_NAK:
                    retransmissions += 1
                    print('[SENDER] Recebeu NAK, retransmitindo')
                    continue
            # Se resposta inválida, retransmitir
            retransmissions += 1
            print('[SENDER] Resposta inválida, retransmitindo')

class RDT20Receiver:
    def __init__(self, local_port, channel: simulator.UnreliableChannel=None):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('localhost', local_port))
        self.channel = channel
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
            out = pkt.unpack_rdt20(pkt_data)
            if out is None:
                continue
            t, chksum, data = out
            if t != pkt.TYPE_DATA:
                continue
            calc = pkt.checksum(data)
            if calc != chksum:
                # enviar NAK
                nak = pkt.pack_ack_rdt20(pkt.TYPE_NAK)
                if self.channel:
                    self.channel.send(nak, self.sock, addr)
                else:
                    self.sock.sendto(nak, addr)
                print('[RECV] Pacote corrompido - NAK enviado')
                continue
            # correto
            self.app_buffer.append(data)
            ack = pkt.pack_ack_rdt20(pkt.TYPE_ACK)
            if self.channel:
                self.channel.send(ack, self.sock, addr)
            else:
                self.sock.sendto(ack, addr)

    def get_all_messages(self):
        # retorna lista de bytes
        buf = self.app_buffer[:]
        self.app_buffer = []
        return buf

    def stop(self):
        self.running = False
        try:
            self.sock.close()
        except Exception:
            pass
