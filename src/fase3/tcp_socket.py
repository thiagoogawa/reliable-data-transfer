# src/fase3/tcp_socket.py
# SimpleTCP over UDP - simplified TCP-like socket
import socket
import threading
import struct
import time
import random
import zlib
from utils.simulator import UnreliableChannel

# Flags (use subset)
FLAG_FIN = 0x01
FLAG_SYN = 0x02
FLAG_ACK = 0x10

# Segment header:
# SeqNum (4), AckNum (4), Flags (1), HeaderLen (1), Window (2), Checksum (4)
HDR_FMT = '!I I B B H I'  # total header = 4+4+1+1+2+4 = 16 bytes

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
    # validate checksum
    hdr_without_ck = struct.pack('!I I B B H', seqnum, acknum, flags, hdrlen, window)
    calc = checksum(hdr_without_ck + data)
    return {'seq': seqnum, 'ack': acknum, 'flags': flags, 'window': window, 'ck': ck, 'calc': calc, 'data': data}

class SimpleTCPSocket:
    def __init__(self, local_port:int, channel:UnreliableChannel=None):
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp.bind(('localhost', local_port))
        self.peer = None
        self.state = 'CLOSED'
        # byte-based seq numbers
        self.seq = random.randint(0, 65535)  # ISN
        self.ack = 0
        # send/recv buffers
        self.send_buffer = {}  # seqnum -> (segment_bytes, send_time, retrans_count)
        self.send_lock = threading.Lock()
        self.recv_buffer = {}  # seqnum -> data
        self.recv_lock = threading.Lock()
        self.app_recv = bytearray()
        # flow control
        self.recv_window = 4096
        # RTT estimation
        self.estimated_rtt = 1.0
        self.dev_rtt = 0.5
        self.timeout_interval = self._calc_timeout()
        # channel simulator (optional)
        self.channel = channel
        # background threads
        self.running = True
        self.recv_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self.retx_thread = threading.Thread(target=self._retransmit_loop, daemon=True)
        self.recv_thread.start()
        self.retx_thread.start()
        # events
        self._connect_event = threading.Event()
        self._accept_event = threading.Event()
        self._close_event = threading.Event()
        # connection info
        self.remote_addr = None

    def _calc_timeout(self):
        return max(0.1, self.estimated_rtt + 4 * self.dev_rtt)

    def _update_rtt(self, sample):
        # Exponential weighted moving average
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
            # verify checksum
            if parsed['ck'] != parsed['calc']:
                # corrupted segment -> ignore
                continue
            flags = parsed['flags']
            seqnum = parsed['seq']
            acknum = parsed['ack']
            data = parsed['data']
            window = parsed['window']
            # update peer/window
            self.remote_addr = addr
            # handle SYN (server side accept)
            if flags & FLAG_SYN:
                # received SYN: respond with SYN-ACK if listening
                if self.state == 'LISTEN':
                    # choose ISN for server (reuse self.seq)
                    self.ack = seqnum + 1
                    # send SYN-ACK
                    seg_out = pack_segment(self.seq, self.ack, FLAG_SYN | FLAG_ACK, self.recv_window, b'')
                    self._send_raw(seg_out, addr)
                    self.state = 'SYN_RCVD'
                # else: ignore
                continue
            # handle SYN-ACK at client
            if (flags & FLAG_SYN) and (flags & FLAG_ACK):
                if self.state == 'SYN_SENT':
                    # accept and send final ACK
                    # ack should be seq from server +1 (server used its ISN)
                    self.ack = seqnum + 1
                    # update RTT sample if possible (we could measure SYN->SYN-ACK time; omitted)
                    # send ACK
                    self.seq = self.seq + 1  # client had sent SYN occupying one seq
                    seg_out = pack_segment(self.seq, self.ack, FLAG_ACK, self.recv_window, b'')
                    self._send_raw(seg_out, addr)
                    self.state = 'ESTABLISHED'
                    self._connect_event.set()
                continue
            # handle ACK
            if flags & FLAG_ACK:
                # process ack number: cumulative ack (acknum is next byte expected)
                with self.send_lock:
                    # find send_buffer entries with last byte < acknum
                    to_remove = []
                    for s_seq, (segbytes, send_time, cnt) in list(self.send_buffer.items()):
                        # segbytes starts at s_seq and includes header len (16) + data
                        # We stored segments created with seq being byte-offset. To check, get data len:
                        parsed_sent = unpack_segment(segbytes)
                        if parsed_sent is None:
                            continue
                        sent_seq = parsed_sent['seq']
                        sent_len = len(parsed_sent['data'])
                        sent_last_byte = sent_seq + sent_len
                        # acknum is next expected byte, so if acknum > sent_last_byte => acked
                        if acknum > sent_last_byte:
                            # update RTT
                            sample = time.time() - send_time
                            self._update_rtt(sample)
                            to_remove.append(s_seq)
                    for s in to_remove:
                        # remove and cancel—no explicit timer per segment; tracked by retransmit loop
                        try:
                            del self.send_buffer[s]
                        except KeyError:
                            pass
                # update remote's advertised window
                self.recv_window = window
            # handle FIN (closing)
            if flags & FLAG_FIN:
                # respond with ACK, then FIN from this side when application finishes
                # ack the FIN (fin occupies 1 byte)
                self.ack = seqnum + 1
                ack_seg = pack_segment(self.seq, self.ack, FLAG_ACK, self.recv_window, b'')
                self._send_raw(ack_seg, addr)
                # set state to CLOSE_WAIT if established
                if self.state == 'ESTABLISHED':
                    self.state = 'CLOSE_WAIT'
                # if received FIN while in FIN_WAIT_1/2 handling may differ; keep simple
                continue
            # handle data segments
            if len(data) > 0:
                # if seq matches expected ack (self.ack) -> deliver and advance
                with self.recv_lock:
                    if seqnum == self.ack:
                        # deliver in-order
                        self.app_recv.extend(data)
                        self.ack = seqnum + len(data)
                        # also check buffered out-of-order fragments
                        while self.ack in self.recv_buffer:
                            frag = self.recv_buffer.pop(self.ack)
                            self.app_recv.extend(frag)
                            self.ack += len(frag)
                    elif seqnum > self.ack:
                        # out-of-order: buffer if within window (simple window check)
                        if seqnum < self.ack + self.recv_window:
                            if seqnum not in self.recv_buffer:
                                self.recv_buffer[seqnum] = data
                    else:
                        # seqnum < ack -> duplicate; ignore
                        pass
                # send cumulative ACK (next byte expected)
                ack_seg = pack_segment(self.seq, self.ack, FLAG_ACK, self.recv_window, b'')
                self._send_raw(ack_seg, addr)

    def _retransmit_loop(self):
        # periodically check send_buffer for segments older than timeout_interval and retransmit
        while self.running:
            now = time.time()
            with self.send_lock:
                for s_seq, (segbytes, send_time, cnt) in list(self.send_buffer.items()):
                    if now - send_time > self.timeout_interval:
                        # retransmit
                        try:
                            parsed = unpack_segment(segbytes)
                            if parsed is None:
                                continue
                            # update send_time and increment count
                            self.send_buffer[s_seq] = (segbytes, now, cnt + 1)
                            if self.remote_addr:
                                self._send_raw(segbytes, self.remote_addr)
                        except Exception:
                            continue
            time.sleep(0.05)

    # --- public API similar to socket ---
    def listen(self):
        self.state = 'LISTEN'

    def accept(self, timeout=None):
        # block until SYN and handshake completed
        # when SYN arrives, _receive_loop will send SYN-ACK and set state to SYN_RCVD; then when final ACK arrives, state->ESTABLISHED
        start = time.time()
        while True:
            if self.state == 'ESTABLISHED':
                return self  # for simplicity return self as connection object
            if timeout and (time.time() - start) > timeout:
                raise TimeoutError('accept timeout')
            time.sleep(0.01)

    def connect(self, dest):
        # three-way handshake
        self.remote_addr = dest
        # send SYN
        syn_segment = pack_segment(self.seq, 0, FLAG_SYN, self.recv_window, b'')
        # SYN consumes one sequence number (like TCP uses one for SYN)
        self._send_raw(syn_segment, dest)
        self.seq += 1
        self.state = 'SYN_SENT'
        # wait for established (SYN-ACK handling in recv loop will set ESTABLISHED and event)
        success = self._connect_event.wait(timeout=5.0)
        if not success:
            raise TimeoutError('connect timeout')
        return

    def send(self, data: bytes):
        # chunk data into MAX_SEG_DATA sized segments, use byte-based seq
        offset = 0
        while offset < len(data):
            # respect remote window (simple: block if remote window small)
            while self.recv_window <= 0:
                time.sleep(0.01)
            chunk = data[offset: offset + MAX_SEG_DATA]
            seg = pack_segment(self.seq, self.ack, FLAG_ACK, self.recv_window, chunk)
            with self.send_lock:
                # store with send time
                self.send_buffer[self.seq] = (seg, time.time(), 0)
                if self.remote_addr:
                    self._send_raw(seg, self.remote_addr)
            self.seq += len(chunk)
            offset += len(chunk)
        # optionally block until all sent data acked
        while True:
            with self.send_lock:
                if len(self.send_buffer) == 0:
                    break
            time.sleep(0.01)

    def recv(self, bufsize=4096):
        # return up to bufsize bytes from app_recv
        with self.recv_lock:
            if len(self.app_recv) == 0:
                return b''
            out = bytes(self.app_recv[:bufsize])
            self.app_recv = self.app_recv[bufsize:]
            return out

    def close(self):
        # active close: send FIN, wait for ACK and peer's FIN/ACK sequence (simplified)
        if self.state != 'ESTABLISHED':
            # just close
            self.running = False
            try: self.udp.close()
            except: pass
            return
        fin_seg = pack_segment(self.seq, self.ack, FLAG_FIN | FLAG_ACK, self.recv_window, b'')
        # FIN occupies one seq number
        with self.send_lock:
            self.send_buffer[self.seq] = (fin_seg, time.time(), 0)
            if self.remote_addr:
                self._send_raw(fin_seg, self.remote_addr)
        self.seq += 1
        # wait briefly for ACK and remote FIN
        # simple approach: wait a bit then stop
        time.sleep(1.0)
        self.running = False
        try: self.udp.close()
        except: pass
