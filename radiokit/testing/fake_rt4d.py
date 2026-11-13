"""Emulador minimo del acceso SPI del Radtel RT-4D (lectura de bloques de 1 KB)."""
from __future__ import annotations

from ..core.transport import Transport


class FakeRT4D(Transport):
    def __init__(self, flash: bytes):
        self.flash = bytearray(flash)
        self.out = bytearray()
        self.baud = 115200
        self.closed_cmd = False
        self.writes = []

    def open(self):
        self.out.clear()

    def close(self):
        pass

    def set_baudrate(self, baud):
        self.baud = baud

    def flush_input(self):
        self.out.clear()

    def read(self, n, timeout=1.5):
        d = bytes(self.out[:n])
        del self.out[:n]
        return d

    def write(self, c: bytes):
        if self.baud != 115200:
            return
        if len(c) == 4 and c[0] == 0x52 and sum(c[:3]) & 0xFF == c[3]:
            kb = (c[1] << 8) | c[2]
            body = bytes([0x52, c[1], c[2]]) + bytes(self.flash[kb * 1024:(kb + 1) * 1024])
            self.out += body + bytes([sum(body) & 0xFF])
        elif len(c) == 5 and c[:4] == bytes([0x34, 0, 0, 0x10]):
            self.out += b"\x06"
        elif c == bytes([0x34, 0x52, 0x05, 0xEE, 0x79]):
            self.closed_cmd = True
        elif len(c) == 1028 and c[0] in self.REGIONS and sum(c[:-1]) & 0xFF == c[-1]:
            addr = self.REGIONS[c[0]] + ((c[1] << 8) | c[2]) * 1024
            self.flash[addr:addr + 1024] = c[3:1027]
            self.writes.append(addr)
            self.out += b"\x06"

    REGIONS = {0x90: 0x2000, 0x91: 0x4000, 0x92: 0x1C000, 0x93: 0x5C000, 0x94: 0x7C000, 0x95: 0x82000,
               0x99: 0xD6000}
    writes: list
