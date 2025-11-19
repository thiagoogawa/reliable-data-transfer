# 📦 Reliable Data Transfer --- Implementação Completa (Fase 1, 2 e 3)

Este projeto implementa, em Python, os protocolos de **Transferência
Confiável de Dados (RDT)** apresentados no curso e no PDF base: - RDT
2.0 - RDT 2.1 - RDT 3.0 - Selective Repeat (SR) - TCP Simplificado sobre
UDP

Todos os módulos utilizam sockets UDP reais, combinados com um **canal
não confiável** (`UnreliableChannel`) que adiciona perda, corrupção e
atraso artificial.


https://github.com/user-attachments/assets/67c8a296-16a0-45fb-85b9-a2a54dbc8d00



------------------------------------------------------------------------

## 🧩 Estrutura do Projeto

    reliable-data-transfer/
    │
    ├── src/
    │   ├── fase1/
    │   │   ├── rdt20.py
    │   │   ├── rdt21.py
    │   │   ├── rdt30.py
    │   │
    │   ├── fase2/
    │   │   └── sr.py
    │   │
    │   ├── fase3/
    │   │   └── tcp_socket.py
    │   │
    │   ├── utils/
    │   │   ├── packet.py
    │   │   └── simulator.py
    │   │
    │   └── testes/
    │       ├── test_fase1.py
    │       ├── test_fase2_sr.py
    │       └── test_fase3.py
    │
    └── README.md

------------------------------------------------------------------------

# 📘 1. FASE 1 --- RDT

### ✔ RDT 2.0

-   Canal pode corromper pacotes
-   Checksum
-   ACK/NAK
-   Retransmissão via NAK

### ✔ RDT 2.1

-   Canal corrompe DATA e ACK
-   Seqnum alternado (0/1)
-   Detecta duplicatas

### ✔ RDT 3.0

-   Canal pode perder pacotes
-   Timeout + retransmissão
-   Funciona com perda + atraso

### 🧪 Testes Fase 1

    python3 -m testes.test_fase1

------------------------------------------------------------------------

# 📘 2. FASE 2 --- Selective Repeat (SR)

### ✔ Implementa:

-   Janela deslizante
-   ACK seletivo
-   Retransmissão individual por timeout
-   Bufferização fora de ordem
-   Reordenação

### 🧪 Testes Fase 2

    python3 -m testes.test_fase2_sr

------------------------------------------------------------------------

# 📘 3. FASE 3 --- TCP Simplificado sobre UDP

### 🔗 Handshake (3-way)

-   SYN
-   SYN+ACK
-   ACK
-   Retransmissão de SYN/SYN-ACK

### 📤 Envio

-   Segmentação (1000 bytes)
-   ACK cumulativo
-   Timeout adaptativo (RTT)
-   Retransmissão periódica

### 📥 Recepção

-   Buffer de reorder
-   ACK imediato

### 🔚 Fechamento

-   FIN
-   ACK do FIN
-   LAST_ACK
-   FIN_WAIT
-   Timeout seguro

### 🧪 Testes Fase 3

    python3 -m testes.test_fase3

------------------------------------------------------------------------

# ▶ Executar todos os testes

    cd src
    python3 -m testes.test_fase1
    python3 -m testes.test_fase2_sr
    python3 -m testes.test_fase3

------------------------------------------------------------------------

# 🧾 Requisitos Atendidos

  Requisito             OK
  --------------------- ----
  RDT 2.0               ✔
  RDT 2.1               ✔
  RDT 3.0               ✔
  Canal não confiável   ✔
  Selective Repeat      ✔
  Janela deslizante     ✔
  ACK seletivo          ✔
  RTT dinâmico          ✔
  Timeout adaptativo    ✔
  TCP Simplificado      ✔
  Handshake 3-way       ✔
  FIN/ACK               ✔
  Reordenação           ✔
  Retransmissão         ✔
  Testes completos      ✔

------------------------------------------------------------------------

# 📄 Licença

Projeto acadêmico --- uso livre para fins educativos.

# 🚀 Autor

Thiago Ogawa
