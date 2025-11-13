# projeto_redes/fase2/sr.py
# Implementação do Selective Repeat (SR) - remetente e receptor
# Janela de envio e recepção de tamanho N

import socket
import threading
import struct
import time
from utils.simulator import UnreliableChannel

# Tipos
TYPE_DATA = 0
TYPE_ACK = 1

MSS = 1000  # payload máximo por segmento

def checksum(data: bytes) -> int:
    import zlib
    return zlib.crc32(data) & 0xffffffff

def pack_data(seqnum: int, payload: bytes) -> bytes:
    header = struct.pack('!BI', TYPE_DATA, seqnum)
    chksum = checksum(header + payload)
    return header + struct.pack('!I', chksum) + payload

def unpack_data(packet: bytes):
    if len(packet) < 9:
        return None
    t, seqnum = struct.unpack('!BI', packet[:5])
    chksum = struct.unpack('!I', packet[5:9])[0]
    data = packet[9:]
    return t, seqnum, chksum, data

def pack_ack(seqnum: int) -> bytes:
    header = struct.pack('!BI', TYPE_ACK, seqnum)
    chksum = checksum(header)
    return header + struct.pack('!I', chksum)

def unpack_ack(packet: bytes):
    if len(packet) < 9:
        return None
    t, seqnum = struct.unpack('!BI', packet[:5])
    chksum = struct.unpack('!I', packet[5:9])[0]
    return t, seqnum, chksum


# ==========================
# Remetente (Sender)
# ==========================
class SRSender:
    def __init__(self, local_port:int, dest_addr, window_size:int=5, channel:UnreliableChannel=None, timeout=0.5):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('localhost', local_port))
        self.dest_addr = dest_addr
        self.channel = channel
        self.window = window_size
        self.base = 0
        self.nextseq = 0
        self.lock = threading.Lock()
        self.timers = {}
        self.packets = {}
        self.acked = set()
        self.timeout = timeout
        self.running = True
        self.recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self.recv_thread.start()

    def _start_timer(self, seqnum):
        def timeout_handler():
            with self.lock:
                if seqnum in self.acked:
                    return
                pkt = self.packets.get(seqnum)
                if not pkt:
                    return
                print(f"[SR] Timeout seq={seqnum}, retransmitindo")
                if self.channel:
                    self.channel.send(pkt, self.sock, self.dest_addr)
                else:
                    self.sock.sendto(pkt, self.dest_addr)
                self._start_timer(seqnum)
        t = threading.Timer(self.timeout, timeout_handler)
        t.daemon = True
        t.start()
        old = self.timers.get(seqnum)
        if old:
            try: old.cancel()
            except Exception: pass
        self.timers[seqnum] = t

    def _cancel_timer(self, seqnum):
        t = self.timers.get(seqnum)
        if t:
            try: t.cancel()
            except Exception: pass
            del self.timers[seqnum]

    def _recv_loop(self):
        while self.running:
            try:
                pkt, _ = self.sock.recvfrom(65536)
            except Exception:
                continue
            out = unpack_ack(pkt)
            if out is None:
                continue
            t, seqnum, chksum = out
            if t != TYPE_ACK:
                continue
            header = struct.pack('!BI', t, seqnum)
            if checksum(header) != chksum:
                continue
            with self.lock:
                if seqnum in self.acked:
                    continue
                self.acked.add(seqnum)
                self._cancel_timer(seqnum)
                while self.base in self.acked:
                    try: del self.packets[self.base]
                    except KeyError: pass
                    self.base += 1

    def send_stream(self, data: bytes):
        """Divide o fluxo de bytes em segmentos e envia com Selective Repeat"""
        segments = [data[i:i+MSS] for i in range(0, len(data), MSS)]
        total_segments = len(segments)
        send_index = 0
        while True:
            with self.lock:
                while self.nextseq < self.base + self.window and send_index < total_segments:
                    payload = segments[send_index]
                    seqnum = self.nextseq
                    pkt = pack_data(seqnum, payload)
                    self.packets[seqnum] = pkt
                    if self.channel:
                        self.channel.send(pkt, self.sock, self.dest_addr)
                    else:
                        self.sock.sendto(pkt, self.dest_addr)
                    self._start_timer(seqnum)
                    self.nextseq += 1
                    send_index += 1
            with self.lock:
                if len(self.acked) >= total_segments:
                    break
            time.sleep(0.01)
        with self.lock:
            for s in list(self.timers.keys()):
                self._cancel_timer(s)

    def close(self):
        self.running = False
        try: self.sock.close()
        except Exception: pass


# ==========================
# Receptor (Receiver)
# ==========================
class SRReceiver:
    def __init__(self, local_port:int, window_size:int=5, channel:UnreliableChannel=None):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('localhost', local_port))
        self.channel = channel
        self.window = window_size
        self.base = 0
        self.buffer = {}
        self.delivered = []
        self.lock = threading.Lock()
        self.running = True
        self.thread = threading.Thread(target=self._recv_loop, daemon=True)
        self.thread.start()

    def _in_window(self, seqnum):
        return self.base <= seqnum < self.base + self.window

    def _recv_loop(self):
        while self.running:
            try:
                pkt, addr = self.sock.recvfrom(65536)
            except Exception:
                continue
            out = unpack_data(pkt)
            if out is None:
                continue
            t, seqnum, chksum, data = out
            if t != TYPE_DATA:
                continue
            header = struct.pack('!BI', t, seqnum)
            if checksum(header + data) != chksum:
                continue
            with self.lock:
                if self._in_window(seqnum):
                    if seqnum not in self.buffer:
                        self.buffer[seqnum] = data
                    ack = pack_ack(seqnum)
                    if self.channel:
                        self.channel.send(ack, self.sock, addr)
                    else:
                        self.sock.sendto(ack, addr)
                    while self.base in self.buffer:
                        self.delivered.append(self.buffer[self.base])
                        del self.buffer[self.base]
                        self.base += 1
                elif seqnum < self.base:
                    ack = pack_ack(seqnum)
                    if self.channel:
                        self.channel.send(ack, self.sock, addr)
                    else:
                        self.sock.sendto(ack, addr)

    def get_data(self) -> bytes:
        with self.lock:
            return b''.join(self.delivered)

    def stop(self):
        self.running = False
        try: self.sock.close()
        except Exception: pass
