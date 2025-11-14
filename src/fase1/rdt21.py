# src/fase1/rdt21.py

import socket
import threading
import struct
from utils.packet import (
    pack_rdt21,
    unpack_rdt21,
    TYPE_DATA,
    TYPE_ACK,
    TYPE_NAK,
    checksum,
)


class RDT21Sender:
    """
    rdt 2.1 Sender (stop-and-wait com seqnum e ACK/NAK robustos).
    """

    def __init__(self, local_port, dest_addr, channel=None, timeout=1.0):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("localhost", local_port))
        self.dest_addr = dest_addr
        self.channel = channel
        self.timeout = timeout
        self.seqnum = 0  # alterna entre 0 e 1

    def send(self, msg):
        """
        Envia msg (bytes ou str), retorna nº de retransmissões.
        """
        if isinstance(msg, bytes):
            data = msg
        else:
            data = msg.encode()

        pkt = pack_rdt21(TYPE_DATA, self.seqnum, data)
        retrans = 0

        while True:
            # SEND
            if self.channel:
                self.channel.send(pkt, self.sock, self.dest_addr)
            else:
                self.sock.sendto(pkt, self.dest_addr)

            # WAIT
            self.sock.settimeout(self.timeout)
            try:
                resp_bytes, _ = self.sock.recvfrom(2048)
            except socket.timeout:
                retrans += 1
                continue

            # unpack
            resp = unpack_rdt21(resp_bytes)
            if resp is None:
                retrans += 1
                continue

            t, rseq, chksum, payload = resp

            # validate checksum
            calc = checksum(struct.pack('!BB', t, rseq) + payload)
            if calc != chksum:
                retrans += 1
                continue

            # ACK correto?
            if t == TYPE_ACK and rseq == self.seqnum:
                self.seqnum ^= 1
                return retrans

            # NAK → retransmitir
            if t == TYPE_NAK and rseq == self.seqnum:
                retrans += 1
                continue

            # qualquer outra coisa → retransmitir
            retrans += 1

    def close(self):
        try:
            self.sock.close()
        except:
            pass



class RDT21Receiver:
    """
    rdt 2.1 Receiver
    """

    def __init__(self, local_port, channel=None):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("localhost", local_port))
        self.channel = channel
        self.expected = 0
        self.buffer = []
        self.running = True

        self.thread = threading.Thread(target=self._recv_loop, daemon=True)
        self.thread.start()

    def _send(self, pkt, addr):
        if self.channel:
            self.channel.send(pkt, self.sock, addr)
        else:
            try:
                self.sock.sendto(pkt, addr)
            except:
                pass

    def _recv_loop(self):
        while self.running:
            try:
                pkt_bytes, addr = self.sock.recvfrom(65536)
            except:
                continue

            unpacked = unpack_rdt21(pkt_bytes)
            if unpacked is None:
                # pacote ilegível → NAK com seqnum esperado
                nak = pack_rdt21(TYPE_NAK, self.expected, b'')
                self._send(nak, addr)
                continue

            t, seqnum, chksum, data = unpacked

            # validar checksum
            calc = checksum(struct.pack('!BB', t, seqnum) + data)
            if calc != chksum:
                nak = pack_rdt21(TYPE_NAK, self.expected, b'')
                self._send(nak, addr)
                continue

            if t != TYPE_DATA:
                # Se chegou ACK/NAK errado no receptor → ignora
                continue

            # Se seqnum correto
            if seqnum == self.expected:
                self.buffer.append(data)
                ack = pack_rdt21(TYPE_ACK, self.expected, b'')
                self._send(ack, addr)
                self.expected ^= 1
            else:
                # seqnum duplicado → reenvia ACK anterior
                oldack = pack_rdt21(TYPE_ACK, seqnum, b'')
                self._send(oldack, addr)

    def get_all_messages(self):
        msgs = self.buffer[:]
        self.buffer = []
        return msgs

    def stop(self):
        self.running = False
        try:
            self.sock.close()
        except:
            pass
