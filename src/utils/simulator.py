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
        """
        loss_rate: probabilidade de perda (0 a 1)
        corrupt_rate: probabilidade de corrupção (0 a 1)
        delay_range: (min_delay, max_delay) em segundos
        """
        self.loss_rate = loss_rate
        self.corrupt_rate = corrupt_rate
        self.delay_range = delay_range

    def send(self, packet: bytes, dest_socket, dest_addr):
        """Simula enviar um pacote com perda, corrupção e atraso."""
        # Simular perda
        if random.random() < self.loss_rate:
            print('[SIM] Pacote perdido')
            return

        # Simular corrupção
        pkt_to_send = packet
        if random.random() < self.corrupt_rate:
            pkt_to_send = self._corrupt_packet(packet)
            print('[SIM] Pacote corrompido')

        # Simular atraso
        delay = random.uniform(*self.delay_range)

        def delayed_send():
            try:
                dest_socket.sendto(pkt_to_send, dest_addr)
            except OSError:
                # O socket pode ter sido fechado antes do timer disparar
                # Evitamos os erros: OSError: [Errno 9] Bad file descriptor
                return

        threading.Timer(delay, delayed_send).start()

    def _corrupt_packet(self, packet: bytes) -> bytes:
        """Corrompe alguns bytes do pacote."""
        if not packet:
            return packet

        packet_list = bytearray(packet)

        # Corrupção leve: altera de 1 até N bytes
        num_corruptions = random.randint(1, max(1, min(5, len(packet_list)//4)))

        for _ in range(num_corruptions):
            idx = random.randint(0, len(packet_list) - 1)
            packet_list[idx] ^= 0xFF  # inverte bits

        return bytes(packet_list)
