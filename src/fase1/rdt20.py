# src/fase1/rdt20.py

import socket
import threading
from utils.packet import (
    pack_rdt20,
    unpack_rdt20,
    pack_ack_rdt20,
    TYPE_ACK,
    TYPE_NAK,
    TYPE_DATA,
    checksum,
)


class RDT20Sender:
    """Sender rdt2.0 (stop-and-wait). Retorna número de retransmissões."""

    def __init__(self, local_port, dest_addr, channel=None, timeout=1.0):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("localhost", local_port))
        self.dest_addr = dest_addr
        self.channel = channel
        self.timeout = timeout

    def send(self, msg):
        """
        msg: str ou bytes
        retorna: número de retransmissões realizadas
        """
        # converter str → bytes
        if isinstance(msg, bytes):
            data = msg
        else:
            data = msg.encode()

        pkt = pack_rdt20(data)
        retrans = 0

        while True:
            # --- ENVIO ---
            if self.channel:
                self.channel.send(pkt, self.sock, self.dest_addr)
            else:
                self.sock.sendto(pkt, self.dest_addr)

            # --- AGUARDAR ACK/NAK ---
            self.sock.settimeout(self.timeout)
            try:
                resp, _ = self.sock.recvfrom(1024)
            except socket.timeout:
                retrans += 1
                continue

            # ACK/NAK deve ter exatamente 1 byte
            if len(resp) != 1:
                retrans += 1
                continue

            resp_type = resp[0]

            if resp_type == TYPE_ACK:
                return retrans  # SUCESSO
            else:
                # NAK ou lixo
                retrans += 1
                continue

    def close(self):
        try: self.sock.close()
        except: pass



class RDT20Receiver:
    """Receiver rdt2.0: roda em thread, envia ACK/NAK e bufferiza mensagens."""

    def __init__(self, local_port, channel=None):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("localhost", local_port))
        self.channel = channel
        self.buffer = []
        self.running = True
        self.lock = threading.Lock()
        self.last_payload = None
        self.last_checksum = None

        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _send(self, pkt, addr):
        """Envia pacote ACK/NAK com ou sem canal."""
        if self.channel:
            self.channel.send(pkt, self.sock, addr)
        else:
            try:
                self.sock.sendto(pkt, addr)
            except:
                pass

    def _loop(self):
        while self.running:
            try:
                pkt_bytes, addr = self.sock.recvfrom(65536)
            except:
                continue

            unpacked = unpack_rdt20(pkt_bytes)

            # Pacote sem formato válido → NAK
            if unpacked is None:
                self._send(pack_ack_rdt20(TYPE_NAK), addr)
                continue

            t, chksum, data = unpacked

            # --- DETECÇÃO DE CORRUPÇÃO MAIS FORTE ---
            # tipo corrompido → NAK
            if t != TYPE_DATA:
                self._send(pack_ack_rdt20(TYPE_NAK), addr)
                continue

            # checksum errado → NAK
            if checksum(data) != chksum:
                self._send(pack_ack_rdt20(TYPE_NAK), addr)
                continue

            # --- PACOTE OK ---
            with self.lock:
                if chksum == self.last_checksum and data == self.last_payload:
                    # ACK anterior pode ter sido corrompido; reenvia ACK sem duplicar entrega.
                    self._send(pack_ack_rdt20(TYPE_ACK), addr)
                    continue

                self.buffer.append(data)
                self.last_checksum = chksum
                self.last_payload = data

            self._send(pack_ack_rdt20(TYPE_ACK), addr)

    def get_all_messages(self):
        """Retorna lista de bytes entregues e limpa buffer."""
        with self.lock:
            msgs = self.buffer[:]
            self.buffer = []
        return msgs

    def stop(self):
        self.running = False
        try: self.sock.close()
        except: pass
