"""Emulador de radio Baofeng (protocolo de clonado clasico) para pruebas y modo demo.

Se comporta como el puerto serie: lo que el PC "escribe" se procesa y la respuesta queda
disponible para read(). La memoria se inicializa con un volcado real.
"""
from __future__ import annotations

import struct

from ..core.transport import Transport


class FakeBaofengRadio(Transport):
    def __init__(self, memory: bytes, magic: bytes, ident: bytes = bytes.fromhex("AA307604000520DD")):
        self.mem = bytearray(memory)
        self.magic, self.ident = magic, ident
        self.out = bytearray()       # radio -> PC
        self.inbuf = bytearray()     # PC -> radio pendiente de procesar
        self.state = "idle"          # idle | wait02 | wait06 | prog
        self.first_read = True
        self.writes: list[int] = []  # direcciones escritas (para las pruebas)
        self.reads = 0
        self.is_open = False

    # --- Transport ---
    def open(self):
        self.is_open = True
        self.state, self.first_read = "idle", True
        self.inbuf.clear()
        self.out.clear()

    def close(self):
        self.is_open = False

    def set_baudrate(self, baud):
        pass

    def flush_input(self):
        self.out.clear()

    def read(self, n, timeout=1.5):
        d = bytes(self.out[:n])
        del self.out[:n]
        return d

    def write(self, data):
        self.inbuf += data
        self._process()

    # --- maquina de estados de la radio ---
    def _process(self):
        while self.inbuf:
            if self.state == "idle":
                if len(self.inbuf) < len(self.magic):
                    return
                if bytes(self.inbuf[:len(self.magic)]) == self.magic:
                    del self.inbuf[:len(self.magic)]
                    self.out += b"\x06"
                    self.state = "wait02"
                else:
                    self.inbuf.clear()       # magic desconocido: la radio lo ignora
                    return
            elif self.state == "wait02":
                if self.inbuf.pop(0) == 0x02:
                    self.out += self.ident
                    self.state = "wait06"
            elif self.state == "wait06":
                if self.inbuf.pop(0) == 0x06:
                    self.out += b"\x06"
                    self.state = "prog"
            elif self.state == "prog":
                c = self.inbuf[0]
                if c == 0x06:                   # ack del PC tras un bloque leido
                    self.inbuf.pop(0)
                elif c == ord("S"):
                    if len(self.inbuf) < 4:
                        return
                    _, a, n = struct.unpack(">BHB", self.inbuf[:4])
                    del self.inbuf[:4]
                    if not self.first_read:
                        self.out += b"\x06"
                    self.first_read = False
                    self.out += struct.pack(">BHB", ord("X"), a, n) + self.mem[a:a + n]
                    self.reads += 1
                elif c == ord("X"):
                    if len(self.inbuf) < 4:
                        return
                    _, a, n = struct.unpack(">BHB", self.inbuf[:4])
                    if len(self.inbuf) < 4 + n:
                        return
                    self.mem[a:a + n] = self.inbuf[4:4 + n]
                    del self.inbuf[:4 + n]
                    self.writes.append(a)
                    self.out += b"\x06"
                else:
                    self.inbuf.pop(0)
