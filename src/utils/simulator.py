# projeto_redes/fase1 - Implementação RDT (rdt2.0, rdt2.1, rdt3.0)
# Organização do documento: cada arquivo começa com um cabeçalho com o nome do arquivo
# Salve cada seção em arquivos separados conforme os cabeçalhos (ex: utils/simulator.py)

# =====================
# utils/simulator.py
# =====================
"""Simulador de canal não confiável.
Use para enviar pacotes entre sockets locais simulando perda, corrupção e atraso.
"""
import random
import threading
import time

class UnreliableChannel:
    def __init__(self, loss_rate=0.0, corrupt_rate=0.0, delay_range=(0.0, 0.0)):
        self.loss_rate = loss_rate
        self.corrupt_rate = corrupt_rate
        self.delay_range = delay_range

    def send(self, packet: bytes, dest_socket, dest_addr):
        # Simular perda
        if random.random() < self.loss_rate:
            print('[SIM] Pacote perdido')
            return

        # Simular corrupção
        if random.random() < self.corrupt_rate:
            packet = self._corrupt_packet(packet)
            print('[SIM] Pacote corrompido')

        # Simular atraso
        delay = random.uniform(*self.delay_range)
        threading.Timer(delay, lambda: dest_socket.sendto(packet, dest_addr)).start()

    def _corrupt_packet(self, packet: bytes) -> bytes:
        if not packet:
            return packet
        packet_list = bytearray(packet)
        num_corruptions = random.randint(1, max(1, min(5, len(packet_list)//4)))
        for _ in range(num_corruptions):
            idx = random.randint(0, len(packet_list) - 1)
            packet_list[idx] ^= 0xFF
        return bytes(packet_list)

