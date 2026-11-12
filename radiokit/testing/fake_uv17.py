"""Emulador del protocolo Baofeng UV-17/UV-13 Pro (cada write() es un comando completo)."""
from __future__ import annotations

import struct

from ..core.transport import Transport


class FakeUV17Radio(Transport):
    def __init__(self, logical: bytes, mem_size: int = 0x31FFF,
                 block_order=(16, 17, 18, 19, 24, 25, 26, 4, 6), extra_pages=(1, 2, 3, 5, 7, 165)):
        # Paginas fisicas en orden "desordenado" (nivelacion de desgaste)
        n_slots = (mem_size + 0x1000 - 0x1FFF + 0xFFF) // 0x1000
        pages = list(block_order[::-1]) + list(extra_pages)
        self.page_map = (pages + [99] * n_slots)[:n_slots]
        self.flash = bytearray(b"\xff" * ((n_slots + 1) * 0x1000))
        for i, p in enumerate(block_order):
            slot = self.page_map.index(p) + 1
            self.flash[slot * 0x1000:(slot + 1) * 0x1000] = logical[i * 0x1000:(i + 1) * 0x1000]
        self.block_order, self.mem_size = block_order, mem_size
        self.out = bytearray()
        self.writes: list[int] = []
        self.authed = False

    def logical(self) -> bytes:
        out = bytearray()
        for p in self.block_order:
            slot = self.page_map.index(p) + 1
            out += self.flash[slot * 0x1000:(slot + 1) * 0x1000]
        return bytes(out)

    def open(self):
        self.out.clear()
        self.authed = False

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
        if getattr(self, "baud", 57600) != 57600:
            return
        if c == b"PSEARCH":
            self.out += b"\x06UV15999"
            self.authed = True
        elif not self.authed:
            return
        elif c == b"PASSSTA":
            self.out += b"\x50\x00\x00"
        elif c == b"SYSINFO":
            self.out += b"\x06"
        elif c == b"\x56\x00\x00\x00\x0A":
            self.out += b"\x56\x00\x00\x00\x0A\x00\x00" + struct.pack("<I", self.mem_size)
        elif c[:1] == b"\x56":
            self.out += bytes(13)
        elif c in (b"\x06",) or c[:4] == b"\xff\xff\xff\xff":
            self.out += b"\x06"
        elif c == b"\x02":
            self.out += bytes(8)
        elif c[:1] in (b"R", b"W") and len(c) >= 5:
            addr = int.from_bytes(c[1:4], "little")
            n = c[4]
            if c[:1] == b"R" and n == 1:
                p = self.page_map[addr // 0x1000 - 1]
                b = 0xFF if p == 165 else ((p // 10) << 4) | (p % 10)   # 165 = pagina borrada (FF)
                self.out += c[:5] + bytes([b])
            elif c[:1] == b"R":
                self.out += c[:5] + self.flash[addr:addr + n]
            else:
                self.flash[addr:addr + n] = c[5:5 + n]
                self.writes.append(addr)
                self.out += b"\x06"
