# src/fase3/tcp_socket.py
# (mesmo conteúdo que você já tem, com as correções de SYN/SYN-ACK)
import socket, threading, struct, time, random, zlib
from utils.simulator import UnreliableChannel

FLAG_FIN = 0x01
FLAG_SYN = 0x02
FLAG_ACK = 0x10
HDR_FMT = '!I I B B H I'
MAX_SEG_DATA = 1000

def checksum(data: bytes) -> int:
    return zlib.crc32(data) & 0xffffffff

def pack_segment(seqnum:int, acknum:int, flags:int, window:int, data:bytes=b'') -> bytes:
    hdr_without_ck = struct.pack('!I I B B H', seqnum, acknum, flags, 20, window)
    ck = checksum(hdr_without_ck + data)
    hdr = struct.pack(HDR_FMT, seqnum, acknum, flags, 20, window, ck)
    return hdr + data

def unpack_segment(segment: bytes):
    if len(segment) < 16:
        return None
    seqnum, acknum, flags, hdrlen, window, ck = struct.unpack(HDR_FMT, segment[:16])
    data = segment[16:]
    hdr_without_ck = struct.pack('!I I B B H', seqnum, acknum, flags, hdrlen, window)
    calc = checksum(hdr_without_ck + data)
    return {'seq': seqnum, 'ack': acknum, 'flags': flags, 'window': window, 'ck': ck, 'calc': calc, 'data': data}

class SimpleTCPSocket:
    def __init__(self, local_port:int, channel:UnreliableChannel=None):
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp.bind(('localhost', local_port))
        self.peer = None
        self.state = 'CLOSED'
        self.seq = random.randint(0, 65535)
        self.ack = 0
        self.send_buffer = {}
        self.send_lock = threading.Lock()
        self.recv_buffer = {}
        self.recv_lock = threading.Lock()
        self.app_recv = bytearray()
        self.recv_window = 4096
        self.estimated_rtt = 1.0
        self.dev_rtt = 0.5
        self.timeout_interval = self._calc_timeout()
        self.channel = channel
        self.running = True
        self.recv_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self.retx_thread = threading.Thread(target=self._retransmit_loop, daemon=True)
        self.recv_thread.start()
        self.retx_thread.start()
        self._connect_event = threading.Event()
        self.remote_addr = None

    def _calc_timeout(self):
        return max(0.1, self.estimated_rtt + 4 * self.dev_rtt)

    def _update_rtt(self, sample):
        self.estimated_rtt = 0.875 * self.estimated_rtt + 0.125 * sample
        self.dev_rtt = 0.75 * self.dev_rtt + 0.25 * abs(sample - self.estimated_rtt)
        self.timeout_interval = self._calc_timeout()

    def _send_raw(self, segment: bytes, addr):
        if self.channel:
            self.channel.send(segment, self.udp, addr)
        else:
            self.udp.sendto(segment, addr)

    def _receive_loop(self):
        while self.running:
            try:
                seg, addr = self.udp.recvfrom(65536)
            except Exception:
                continue
            parsed = unpack_segment(seg)
            if parsed is None:
                continue
            if parsed['ck'] != parsed['calc']:
                continue
            flags = parsed['flags']
            seqnum = parsed['seq']
            acknum = parsed['ack']
            data = parsed['data']
            window = parsed['window']
            self.remote_addr = addr

            # --- SYN (server side receives SYN) ---
            if flags & FLAG_SYN:
                if self.state == 'LISTEN':
                    self.ack = seqnum + 1
                    seg_out = pack_segment(self.seq, self.ack, FLAG_SYN | FLAG_ACK, self.recv_window, b'')
                    self._send_raw(seg_out, addr)
                    # consume one seq for SYN-ACK we just sent
                    self.seq += 1
                    self.state = 'SYN_RCVD'
                continue

            # --- SYN-ACK received (client side) ---
            if (flags & FLAG_SYN) and (flags & FLAG_ACK):
                if self.state == 'SYN_SENT':
                    self.ack = seqnum + 1
                    seg_out = pack_segment(self.seq, self.ack, FLAG_ACK, self.recv_window, b'')
                    self._send_raw(seg_out, addr)
                    self.state = 'ESTABLISHED'
                    self._connect_event.set()
                continue

            # --- ACK handling (cumulative) ---
            if flags & FLAG_ACK:
                with self.send_lock:
                    to_remove = []
                    for s_seq, (segbytes, send_time, cnt) in list(self.send_buffer.items()):
                        parsed_sent = unpack_segment(segbytes)
                        if parsed_sent is None:
                            continue
                        sent_seq = parsed_sent['seq']
                        sent_len = len(parsed_sent['data'])
                        sent_last_byte = sent_seq + sent_len
                        if acknum > sent_last_byte:
                            sample = time.time() - send_time
                            self._update_rtt(sample)
                            to_remove.append(s_seq)
                    for s in to_remove:
                        try: del self.send_buffer[s]
                        except KeyError: pass
                self.recv_window = window

            # --- FIN handling ---
            if flags & FLAG_FIN:
                self.ack = seqnum + 1
                ack_seg = pack_segment(self.seq, self.ack, FLAG_ACK, self.recv_window, b'')
                self._send_raw(ack_seg, addr)
                if self.state == 'ESTABLISHED':
                    self.state = 'CLOSE_WAIT'
                continue

            # --- DATA handling ---
            if len(data) > 0:
                with self.recv_lock:
                    if seqnum == self.ack:
                        self.app_recv.extend(data)
                        self.ack = seqnum + len(data)
                        while self.ack in self.recv_buffer:
                            frag = self.recv_buffer.pop(self.ack)
                            self.app_recv.extend(frag)
                            self.ack += len(frag)
                    elif seqnum > self.ack:
                        if seqnum < self.ack + self.recv_window:
                            if seqnum not in self.recv_buffer:
                                self.recv_buffer[seqnum] = data
                    else:
                        pass
                ack_seg = pack_segment(self.seq, self.ack, FLAG_ACK, self.recv_window, b'')
                self._send_raw(ack_seg, addr)

    def _retransmit_loop(self):
        while self.running:
            now = time.time()
            with self.send_lock:
                for s_seq, (segbytes, send_time, cnt) in list(self.send_buffer.items()):
                    if now - send_time > self.timeout_interval:
                        try:
                            self.send_buffer[s_seq] = (segbytes, now, cnt + 1)
                            if self.remote_addr:
                                self._send_raw(segbytes, self.remote_addr)
                        except Exception:
                            continue
            time.sleep(0.05)

    def listen(self):
        self.state = 'LISTEN'

    def accept(self, timeout=None):
        start = time.time()
        while True:
            if self.state == 'ESTABLISHED':
                return self
            if timeout and (time.time() - start) > timeout:
                raise TimeoutError('accept timeout')
            time.sleep(0.01)

    def connect(self, dest):
        self.remote_addr = dest
        syn_segment = pack_segment(self.seq, 0, FLAG_SYN, self.recv_window, b'')
        self._send_raw(syn_segment, dest)
        # consume one seq for SYN we sent
        self.seq += 1
        self.state = 'SYN_SENT'
        success = self._connect_event.wait(timeout=5.0)
        if not success:
            raise TimeoutError('connect timeout')
        return

    def send(self, data: bytes):
        offset = 0
        while offset < len(data):
            while self.recv_window <= 0:
                time.sleep(0.01)
            chunk = data[offset: offset + MAX_SEG_DATA]
            seg = pack_segment(self.seq, self.ack, FLAG_ACK, self.recv_window, chunk)
            with self.send_lock:
                self.send_buffer[self.seq] = (seg, time.time(), 0)
                if self.remote_addr:
                    self._send_raw(seg, self.remote_addr)
            self.seq += len(chunk)
            offset += len(chunk)
        while True:
            with self.send_lock:
                if len(self.send_buffer) == 0:
                    break
            time.sleep(0.01)

    def recv(self, bufsize=4096):
        with self.recv_lock:
            if len(self.app_recv) == 0:
                return b''
            out = bytes(self.app_recv[:bufsize])
            self.app_recv = self.app_recv[bufsize:]
            return out

    def close(self):
        if self.state != 'ESTABLISHED':
            self.running = False
            try: self.udp.close()
            except: pass
            return
        fin_seg = pack_segment(self.seq, self.ack, FLAG_FIN | FLAG_ACK, self.recv_window, b'')
        with self.send_lock:
            self.send_buffer[self.seq] = (fin_seg, time.time(), 0)
            if self.remote_addr:
                self._send_raw(fin_seg, self.remote_addr)
        self.seq += 1
        time.sleep(1.0)
        self.running = False
        try: self.udp.close()
        except: pass
