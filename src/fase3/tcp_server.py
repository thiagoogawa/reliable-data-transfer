# src/fase3/tcp_server.py
from fase3.tcp_socket import SimpleTCPSocket
import time

def server_example():
    server = SimpleTCPSocket(local_port=8000)
    server.listen()
    print("Server listening on 8000 (blocking accept)...")
    conn = server.accept(timeout=10)
    print("Connection accepted.")
    # read 10KB
    total = b''
    while len(total) < 10240:
        chunk = conn.recv(4096)
        if not chunk:
            time.sleep(0.01)
            continue
        total += chunk
    print(f"Server received {len(total)} bytes")
    conn.close()

if __name__ == '__main__':
    server_example()
