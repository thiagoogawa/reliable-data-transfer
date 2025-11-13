# =====================
# testes/test_fase1.py
# =====================
"""Script de testes para Fase 1.
Executa os testes obrigatórios do enunciado.
"""
import time
import threading
from utils.simulator import UnreliableChannel
from fase1.rdt20 import RDT20Sender, RDT20Receiver
from fase1.rdt21 import RDT21Sender, RDT21Receiver
from fase1.rdt30 import RDT30Sender, RDT30Receiver


def test_rdt20_perfeito():
    print('\n=== Teste rdt2.0 - canal perfeito ===')
    recv = RDT20Receiver(10001)
    sender = RDT20Sender(10000, ('localhost', 10001))
    msgs = [f'msg {i}'.encode() for i in range(10)]
    total_retx = 0
    for m in msgs:
        r = sender.send(m)
        total_retx += r
    time.sleep(0.5)
    rec = recv.get_all_messages()
    assert len(rec) == 10
    print('Mensagens recebidas:', len(rec), 'Retransmissões:', total_retx)
    recv.stop()


def test_rdt20_corrompido():
    print('\n=== Teste rdt2.0 - 30% de corrupção ===')
    channel = UnreliableChannel(loss_rate=0.0, corrupt_rate=0.3, delay_range=(0.01, 0.05))
    recv = RDT20Receiver(10003, channel)
    sender = RDT20Sender(10002, ('localhost', 10003), channel)
    msgs = [f'msg {i}'.encode() for i in range(10)]
    total_retx = 0
    for m in msgs:
        r = sender.send(m)
        total_retx += r
    time.sleep(1)
    rec = recv.get_all_messages()
    assert len(rec) == 10
    print('Mensagens recebidas:', len(rec), 'Retransmissões:', total_retx)
    recv.stop()


def test_rdt21():
    print('\n=== Teste rdt2.1 - corrupcao DATA 20% e ACKs 20% ===')
    # Simulamos corrupção tanto na transmissão quanto nas respostas
    channel = UnreliableChannel(loss_rate=0.0, corrupt_rate=0.2, delay_range=(0.01, 0.05))
    recv = RDT21Receiver(10005, channel)
    sender = RDT21Sender(10004, ('localhost', 10005), channel)
    msgs = [f'msg {i}'.encode() for i in range(10)]
    total_retx = 0
    for m in msgs:
        r = sender.send(m)
        total_retx += r
    time.sleep(1)
    rec = recv.get_all_messages()
    assert len(rec) == 10
    print('Mensagens recebidas:', len(rec), 'Retransmissões:', total_retx)
    recv.stop()


def test_rdt30():
    print('\n=== Teste rdt3.0 - perda 15% DATA e 15% ACKs, atraso 50-500ms ===')
    channel = UnreliableChannel(loss_rate=0.15, corrupt_rate=0.0, delay_range=(0.05, 0.5))
    # Para simular perda de ACKs também, usamos channel tanto para envio quanto para respostas
    recv = RDT30Receiver(10007, channel)
    sender = RDT30Sender(10006, ('localhost', 10007), channel)
    msgs = [f'msg {i}'.encode() for i in range(10)]
    total_retx = 0
    for m in msgs:
        r = sender.send(m, timeout=2.0)
        total_retx += r
    time.sleep(2)
    rec = recv.get_all_messages()
    assert len(rec) == 10
    print('Mensagens recebidas:', len(rec), 'Retransmissões:', total_retx)
    recv.stop()

if __name__ == '__main__':
    test_rdt20_perfeito()
    test_rdt20_corrompido()
    test_rdt21()
    test_rdt30()
    print('\nTodos os testes da Fase 1 completados com sucesso (asserts passaram)')