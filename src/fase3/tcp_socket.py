# src/fase3/tcp_socket.py
"""
TCP-like sobre UDP — versão com retransmissão robusta de handshake (SYN/SYN-ACK)
e proteção contra timeouts em canais com perda.
"""

import socket
import threading
import struct
import time
import random
import zlib

from utils.simulator import UnreliableChannel

FLAG_FIN = 0x01
FLAG_SYN = 0x02
FLAG_ACK = 0x10

HDR_FMT = '!I I B B H I'
HDR_LEN = 16
MAX_SEG_DATA = 1000

def checksum(data: bytes) -> int:
    return zlib.crc32(data) & 0xffffffff

def pack_segment(seqnum:int, acknum:int, flags:int, window:int, data:bytes=b'') -> bytes:
    hdr_no_ck = struct.pack('!I I B B H', seqnum, acknum, flags, HDR_LEN, window)
    ck = checksum(hdr_no_ck + data)
    hdr = struct.pack(HDR_FMT, seqnum, acknum, flags, HDR_LEN, window, ck)
    return hdr + data

def unpack_segment(seg: bytes):
    if len(seg) < HDR_LEN:
        return None
    seqnum, acknum, flags, hdrlen, window, ck = struct.unpack(HDR_FMT, seg[:HDR_LEN])
    data = seg[HDR_LEN:]
    hdr_no_ck = struct.pack('!I I B B H', seqnum, acknum, flags, hdrlen, window)
    calc = checksum(hdr_no_ck + data)
    return {'seq': seqnum, 'ack': acknum, 'flags': flags, 'window': window, 'ck': ck, 'calc': calc, 'data': data}

class SimpleTCPSocket:
    def __init__(self, local_port:int, channel:UnreliableChannel=None):
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp.bind(('localhost', local_port))
        self.channel = channel

        self.remote = None
        self.state = 'CLOSED'

        # seq/ack (byte-based)
        self.seq = random.randint(0, 2**31-1)
        self.ack = 0

        # send/recv buffers and locks
        self.send_lock = threading.Lock()
        self.send_buffer = {}   # seq -> (segment_bytes, send_time)
        self.recv_buffer = {}   # seq -> data
        self.app_recv = bytearray()
        self.recv_window = 4096

        # RTT estimation
        self.estimated_rtt = 0.5
        self.dev_rtt = 0.25
        self.timeout_interval = self._calc_timeout()

        # control
        self.running = True
        self._connect_event = threading.Event()
        self._close_event = threading.Event()

        # threads
        self._recv_t = threading.Thread(target=self._recv_loop, daemon=True)
        self._retx_t = threading.Thread(target=self._retx_loop, daemon=True)
        self._recv_t.start()
        self._retx_t.start()

    # ----------------------
    # helpers
    # ----------------------
    def _calc_timeout(self):
        return max(0.1, self.estimated_rtt + 4*self.dev_rtt)

    def _update_rtt(self, sample):
        self.estimated_rtt = 0.875*self.estimated_rtt + 0.125*sample
        self.dev_rtt = 0.75*self.dev_rtt + 0.25*abs(sample - self.estimated_rtt)
        self.timeout_interval = self._calc_timeout()

    def _send_raw(self, seg, addr):
        if self.channel:
            self.channel.send(seg, self.udp, addr)
        else:
            try:
                self.udp.sendto(seg, addr)
            except OSError:
                # socket may be closed; ignore
                pass

    # ----------------------
    # receive loop
    # ----------------------
    def _recv_loop(self):
        while self.running:
            try:
                seg_bytes, addr = self.udp.recvfrom(65536)
            except Exception:
                continue
            parsed = unpack_segment(seg_bytes)
            if parsed is None:
                continue
            if parsed['ck'] != parsed['calc']:
                continue  # corrupted
            seqnum = parsed['seq']
            acknum = parsed['ack']
            flags = parsed['flags']
            data = parsed['data']
            window = parsed['window']

            # update remote address
            self.remote = addr

            # --- HANDSHAKE server side: receive SYN ---
            if flags == FLAG_SYN and self.state == 'LISTEN':
                # set ack to client's seq+1
                self.ack = seqnum + 1
                # build SYN-ACK
                synack = pack_segment(self.seq, self.ack, FLAG_SYN | FLAG_ACK, self.recv_window)
                # send SYN-ACK and store in send_buffer so retransmitter handles it
                with self.send_lock:
                    self.send_buffer[self.seq] = (synack, time.time())
                    if self.remote:
                        self._send_raw(synack, addr)
                # consume seq for our SYN-ACK
                self.seq += 1
                self.state = 'SYN_RCVD'
                continue

            # --- HANDSHAKE client side: received SYN-ACK ---
            if flags == (FLAG_SYN | FLAG_ACK) and self.state == 'SYN_SENT':
                # record ack and send final ACK
                self.ack = seqnum + 1
                ackseg = pack_segment(self.seq, self.ack, FLAG_ACK, self.recv_window)
                # send ACK (final) — don't store it in send_buffer (no data)
                self._send_raw(ackseg, addr)
                # mark established
                self.state = 'ESTABLISHED'
                # since the client may have stored its SYN in send_buffer, ACK handler will remove it
                self._connect_event.set()
                continue

            # --- HANDSHAKE server: final ACK from client ---
            if flags == FLAG_ACK and self.state == 'SYN_RCVD':
                # this ACK likely acknowledges server's SYN-ACK; send_buffer removals happen in ACK handling
                self.state = 'ESTABLISHED'
                continue

            # --- ACK handling: remove acked segments from send_buffer ---
            if flags & FLAG_ACK:
                with self.send_lock:
                    to_delete = []
                    for s_seq, (segb, sent_time) in list(self.send_buffer.items()):
                        parsed_sent = unpack_segment(segb)
                        if parsed_sent is None:
                            continue
                        sent_seq = parsed_sent['seq']
                        sent_len = len(parsed_sent['data'])
                        sent_last = sent_seq + sent_len
                        # acknum is next expected byte: if acknum > sent_last -> this segment fully acked
                        if acknum > sent_last:
                            sample = time.time() - sent_time
                            self._update_rtt(sample)
                            to_delete.append(s_seq)
                    for s in to_delete:
                        try:
                            del self.send_buffer[s]
                        except KeyError:
                            pass
                # update advertised window
                self.recv_window = window

            # --- FIN handling ---
            if flags & FLAG_FIN:
                # ack FIN
                self.ack = seqnum + 1
                ackseg = pack_segment(self.seq, self.ack, FLAG_ACK, self.recv_window)
                self._send_raw(ackseg, addr)

                # transitions
                if self.state == 'FIN_WAIT_2':
                    self.state = 'CLOSED'
                    self._close_event.set()
                    continue
                if self.state == 'ESTABLISHED':
                    self.state = 'CLOSE_WAIT'
                    continue
                if self.state == 'FIN_WAIT_1':
                    # if our FIN was already acked and we get FIN, finish
                    if len(self.send_buffer) == 0:
                        self.state = 'CLOSED'
                        self._close_event.set()
                    else:
                        self.state = 'CLOSING'
                    continue

            # --- DATA handling ---
            if data:
                if seqnum == self.ack:
                    self.app_recv.extend(data)
                    self.ack = seqnum + len(data)
                    # deliver buffered
                    while self.ack in self.recv_buffer:
                        frag = self.recv_buffer.pop(self.ack)
                        self.app_recv.extend(frag)
                        self.ack += len(frag)
                elif seqnum > self.ack:
                    if seqnum not in self.recv_buffer:
                        self.recv_buffer[seqnum] = data
                # always send cumulative ACK
                ackseg = pack_segment(self.seq, self.ack, FLAG_ACK, self.recv_window)
                self._send_raw(ackseg, addr)

    # ------------------------------
    # retransmission loop
    # ------------------------------
    def _retx_loop(self):
        while self.running:
            time.sleep(0.05)
            now = time.time()
            with self.send_lock:
                for s_seq, (segbytes, ts) in list(self.send_buffer.items()):
                    if now - ts > self.timeout_interval:
                        # retransmit and update timestamp
                        self.send_buffer[s_seq] = (segbytes, now)
                        if self.remote:
                            self._send_raw(segbytes, self.remote)

    # ------------------------------
    # public API
    # ------------------------------
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

    def connect(self, dest, timeout=5.0):
        """
        Send SYN repeatedly until SYN-ACK received or timeout.
        We store the SYN in send_buffer so retransmissions are handled by _retx_loop too.
        """
        self.remote = dest
        syn = pack_segment(self.seq, 0, FLAG_SYN, self.recv_window)
        with self.send_lock:
            self.send_buffer[self.seq] = (syn, time.time())
            self._send_raw(syn, dest)
        # consume seq for our SYN
        self.seq += 1
        self.state = 'SYN_SENT'

        start = time.time()
        # retransmit loop (in addition to _retx_loop): proactively re-send SYN if still in send_buffer
        while True:
            if self._connect_event.wait(timeout=0.1):
                break
            if time.time() - start > timeout:
                break
            # if still in send_buffer (not acked), re-send (also _retx_loop will handle)
            with self.send_lock:
                for s_seq, (segb, ts) in list(self.send_buffer.items()):
                    parsed = unpack_segment(segb)
                    if parsed and parsed['flags'] == FLAG_SYN:
                        # resend SYN proactively
                        self._send_raw(segb, dest)

        if not self._connect_event.is_set():
            # give a chance that ACK handler will clear buffer; then timeout
            raise TimeoutError('connect timeout')

    def send(self, data: bytes):
        offset = 0
        total_len = len(data)
        while offset < total_len:
            chunk = data[offset: offset + MAX_SEG_DATA]
            seg = pack_segment(self.seq, self.ack, FLAG_ACK, self.recv_window, chunk)
            with self.send_lock:
                self.send_buffer[self.seq] = (seg, time.time())
                if self.remote:
                    self._send_raw(seg, self.remote)
            self.seq += len(chunk)
            offset += len(chunk)
            # avoid unbounded queue growth: simple backoff
            safety_start = time.time()
            while True:
                with self.send_lock:
                    pending = len(self.send_buffer)
                if pending < 500:
                    break
                if time.time() - safety_start > 2.0:
                    break
                time.sleep(0.01)

        # wait for buffer to drain with reasonable timeout
        start = time.time()
        max_wait = max(5.0, total_len / 1024.0)
        while True:
            with self.send_lock:
                if len(self.send_buffer) == 0:
                    break
            if time.time() - start > max_wait:
                break
            time.sleep(0.01)

    def recv(self, bufsize=4096):
        if len(self.app_recv) == 0:
            return b''
        out = bytes(self.app_recv[:bufsize])
        self.app_recv = self.app_recv[bufsize:]
        return out

    def close(self, timeout=5.0):
        start = time.time()

        if self.state == 'CLOSED':
            self._cleanup()
            return

        # try draining send_buffer briefly
        drain_deadline = time.time() + min(1.0, timeout/2.0)
        while True:
            with self.send_lock:
                pending = len(self.send_buffer)
            if pending == 0:
                break
            if time.time() > drain_deadline:
                break
            time.sleep(0.01)

        # active close: send FIN and wait for FIN/ACK sequence
        if self.state in ('ESTABLISHED', 'SYN_RCVD'):
            fin = pack_segment(self.seq, self.ack, FLAG_FIN | FLAG_ACK, self.recv_window)
            with self.send_lock:
                self.send_buffer[self.seq] = (fin, time.time())
                if self.remote:
                    self._send_raw(fin, self.remote)
            self.seq += 1
            self.state = 'FIN_WAIT_1'

            # wait for close event or timeout
            while True:
                if self._close_event.wait(timeout=0.1):
                    break
                if time.time() - start > timeout:
                    break
            self._cleanup()
            return

        # passive close: if peer closed first, send our FIN and wait for ack
        if self.state == 'CLOSE_WAIT':
            fin = pack_segment(self.seq, self.ack, FLAG_FIN | FLAG_ACK, self.recv_window)
            with self.send_lock:
                self.send_buffer[self.seq] = (fin, time.time())
                if self.remote:
                    self._send_raw(fin, self.remote)
            self.seq += 1
            self.state = 'LAST_ACK'
            while True:
                if self._close_event.wait(timeout=0.1):
                    break
                if time.time() - start > timeout:
                    break
            self._cleanup()
            return

        # other states: wait a bit then cleanup
        wait_deadline = time.time() + timeout
        while time.time() < wait_deadline:
            if self._close_event.wait(timeout=0.1):
                break
        self._cleanup()

    def _cleanup(self):
        # stop threads and close socket
        self.running = False
        self._close_event.set()
        # small pause to let retx timers finish attempts
        time.sleep(0.01)
        try:
            self.udp.close()
        except:
            pass

    def __del__(self):
        try:
            self._cleanup()
        except:
            pass
