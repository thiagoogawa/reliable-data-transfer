# src/utils/simulator.py
"""Simulador de canal não confiável.
Este simulador corrompe/perde/aplica atraso apenas em pacotes de DADOS,
ignorando ACKs/NAKs (pacotes curtos ou com tipo != TYPE_DATA).
"""
import struct
import random
import threading

# manter compatibilidade com utils.packet.TYPE_DATA sem import circular aqui:
# vamos declarar o valor esperado (mesmo do packet.py)
# NOTE: se mudar TYPE_DATA no packet.py, atualize aqui também.
TYPE_DATA = 0

class UnreliableChannel:
    def __init__(self, loss_rate=0.0, corrupt_rate=0.0, delay_range=(0.0, 0.0)):
        self.loss_rate = loss_rate
        self.corrupt_rate = corrupt_rate
        self.delay_range = delay_range

    def send(self, packet: bytes, dest_socket, dest_addr):
        # Se o pacote não parece ser um segmento de DADOS (ex.: ACK/NAK de 1 byte),
        # não aplicamos corrupção — só aplicamos perda/atraso.
        try:
            is_data = len(packet) > 0 and packet[0] == TYPE_DATA
        except Exception:
            is_data = False

        # Simular perda (aplica a todos)
        if random.random() < self.loss_rate:
            print('[SIM] Pacote perdido')
            return

        # Simular corrupção: **apenas** para pacotes de dados
        pkt_to_send = packet
        if is_data and (random.random() < self.corrupt_rate):
            pkt_to_send = self._corrupt_packet(packet)
            print('[SIM] Pacote corrompido')

        # Simular atraso (aplica a todos)
        delay = random.uniform(*self.delay_range)
        threading.Timer(delay, lambda: dest_socket.sendto(pkt_to_send, dest_addr)).start()

    def _corrupt_packet(self, packet: bytes) -> bytes:
        if not packet:
            return packet
        packet_list = bytearray(packet)
        # corrompe alguns bytes aleatórios
        num_corruptions = random.randint(1, max(1, min(5, len(packet_list)//4)))
        for _ in range(num_corruptions):
            idx = random.randint(0, len(packet_list) - 1)
            packet_list[idx] ^= 0xFF
        return bytes(packet_list)
