# src/testes/test_fase3.py
import threading
import time
from utils.simulator import UnreliableChannel
from fase3.tcp_socket import SimpleTCPSocket

def test_handshake_and_transfer():
    print("\n=== Test: handshake + 10KB transfer ===")
    server = SimpleTCPSocket(local_port=8000)
    server.listen()

    def server_thread():
        conn = server.accept(timeout=5)
        # read 10KB
        buf = b''
        while len(buf) < 10240:
            chunk = conn.recv(4096)
            if not chunk:
                time.sleep(0.01)
                continue
            buf += chunk
        print("Server got:", len(buf))
        conn.close()

    t = threading.Thread(target=server_thread, daemon=True)
    t.start()

    client = SimpleTCPSocket(local_port=9000)
    client.connect(('localhost', 8000))
    data = b'A' * 10240
    client.send(data)
    time.sleep(0.5)
    client.close()
    time.sleep(0.5)
    print("Test finished")

def test_with_loss():
    print("\n=== Test: transfer with simulated loss (20%) ===")
    channel = UnreliableChannel(loss_rate=0.2, corrupt_rate=0.0, delay_range=(0.01, 0.05))
    server = SimpleTCPSocket(local_port=8010, channel=channel)
    server.listen()

    def server_thread():
        conn = server.accept(timeout=5)
        buf = b''
        while len(buf) < 1024*50:
            chunk = conn.recv(4096)
            if not chunk:
                time.sleep(0.01)
                continue
            buf += chunk
        print("Server got:", len(buf))
        conn.close()

    t = threading.Thread(target=server_thread, daemon=True)
    t.start()

    client = SimpleTCPSocket(local_port=9020, channel=channel)
    client.connect(('localhost', 8010))
    data = b'B' * (1024*50)
    client.send(data)
    time.sleep(1.0)
    client.close()
    time.sleep(0.5)
    print("Loss test finished")

if __name__ == '__main__':
    test_handshake_and_transfer()
    test_with_loss()
