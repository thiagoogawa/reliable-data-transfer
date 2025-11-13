# testes/test_fase2_sr.py
# Testes básicos para Selective Repeat (SR)

import time
from utils.simulator import UnreliableChannel
from fase2.sr import SRSender, SRReceiver

def test_sr_basic():
    print("\n=== Teste SR básico - canal perfeito ===")
    recv = SRReceiver(12001, window_size=5)
    sender = SRSender(12000, ('localhost', 12001), window_size=5)
    data = b'A' * 5000  # 5 KB
    sender.send_stream(data)
    time.sleep(0.5)
    received = recv.get_data()
    assert received == data
    print("✓ Dados recebidos corretamente (canal perfeito)")
    sender.close()
    recv.stop()

def test_sr_lossy():
    print("\n=== Teste SR - canal com perdas 10% e atraso ===")
    channel = UnreliableChannel(loss_rate=0.1, corrupt_rate=0.0, delay_range=(0.01, 0.05))
    recv = SRReceiver(12003, window_size=8, channel=channel)
    sender = SRSender(12002, ('localhost', 12003), window_size=8, channel=channel, timeout=0.2)
    data = b'B' * 50000  # 50 KB
    start = time.time()
    sender.send_stream(data)
    time.sleep(1)
    received = recv.get_data()
    assert received == data
    duration = time.time() - start
    print(f"✓ Dados recebidos corretamente (tempo {duration:.2f}s)")
    sender.close()
    recv.stop()

if __name__ == "__main__":
    test_sr_basic()
    test_sr_lossy()
    print("\nTodos os testes da Fase 2 (SR) passaram com sucesso!")
