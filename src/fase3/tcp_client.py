# src/fase3/tcp_client.py
from fase3.tcp_socket import SimpleTCPSocket
import time

def client_example():
    client = SimpleTCPSocket(local_port=9000)
    client.connect(('localhost', 8000))
    print("Connected to server.")
    data = b'x' * 10240
    client.send(data)
    print("Client sent 10KB")
    time.sleep(0.5)
    client.close()
    print("Client closed")

if __name__ == '__main__':
    client_example()
