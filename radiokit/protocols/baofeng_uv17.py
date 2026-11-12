"""Protocolo Baofeng familia UV-17 (UV-17, UV-13 Pro, ...). 57600 baudios.

  PC -> "PSEARCH"                  radio -> 06 "UV15999"...   (huella)
  PC -> "PASSSTA", "SYSINFO", 56 00 00 0A 0D, 06, 56 00 10 0A 0D, 06, 56 00 20 0A 0D, 06
  PC -> 56 00 00 00 0A             radio -> 11 B; bytes 7..10 = tamano de memoria (LE)
  PC -> 06, FF FF FF FF 0C "UV15999", 02, 06
  Mapa de paginas: para cada 0x1000: PC -> 'R' addr(3 B LE) 01  radio -> 6 B (byte 5 = n. de pagina BCD), PC -> 06
  Lectura:   PC -> 'R' addr(3 B LE) LEN    radio -> 5 B cabecera + LEN datos, PC -> 06 (radio responde 1 B)
  Escritura: PC -> 'W' addr(3 B LE) LEN datos   radio -> 06
La flash reparte las paginas logicas (16,17,18,19,24,25,26,4,6) en posiciones fisicas variables
(nivelacion de desgaste); la imagen se guarda en orden logico: pagina i -> 0x1000*i.
Referencia: CHIRP baofeng_uv17.py / baofeng_uv17Pro.py (GPLv3); reimplementado aqui.
"""
from __future__ import annotations

import struct

from ..drivers.base import Progress, Protocol, ProtocolError, _noprogress

UV17_MAGICS = ((b"PASSSTA", 3), (b"SYSINFO", 1), (b"\x56\x00\x00\x0A\x0D", 13), (b"\x06", 1),
               (b"\x56\x00\x10\x0A\x0D", 13), (b"\x06", 1), (b"\x56\x00\x20\x0A\x0D", 13), (b"\x06", 1))
UV17_MAGICS2 = ((b"\x06", 1), (b"\xFF\xFF\xFF\xFF\x0C\x55\x56\x31\x35\x39\x39\x39", 1), (b"\x02", 8),
                (b"\x06", 1))


class BaofengUV17Protocol(Protocol):
    BAUDRATE = 57600
    TIMEOUT = 1.5
    PAGE = 0x1000

    def __init__(self, transport, ident: bytes = b"PSEARCH", fingerprint: bytes = b"\x06UV15999",
                 block_order: tuple[int, ...] = (16, 17, 18, 19, 24, 25, 26, 4, 6), block: int = 0x40):
        super().__init__(transport, ident=ident, fingerprint=fingerprint, block_order=block_order, block=block)
        self.ident, self.fingerprint, self.block_order, self.block = ident, fingerprint, block_order, block
        self.WRITE_BLOCK = block
        self.page_map: list[int] = []
        self.responses: dict[str, str] = {}

    def _x(self, data: bytes, n: int) -> bytes:
        self.t.write(data)
        return self.t.read(n, self.TIMEOUT)

    def _frame(self, cmd: bytes, addr: int, length: int, data: bytes = b"") -> bytes:
        return cmd + struct.pack("<I", addr)[:3] + bytes([length]) + data

    def identify(self):
        self.t.flush_input()
        ack = self._x(self.ident, len(self.fingerprint))
        if not ack.startswith(self.fingerprint):
            return None
        for magic, n in UV17_MAGICS:
            r = self._x(magic, n)
            self.responses[magic.hex()] = r.hex(" ")
        r = self._x(b"\x56\x00\x00\x00\x0A", 11)
        if len(r) != 11:
            raise ProtocolError("Respuesta de tamano de memoria invalida: %s" % r.hex(" "))
        mem_size = struct.unpack("<I", r[7:11])[0]
        for magic, n in UV17_MAGICS2:
            self._x(magic, n)
        # Mapa de paginas fisicas (solo lectura)
        self.page_map = []
        for addr in range(0x1FFF, mem_size + 0x1000, 0x1000):
            r = self._x(self._frame(b"R", addr, 1), 6)
            if len(r) != 6:
                raise ProtocolError("Sin respuesta al leer el mapa en 0x%05X" % addr)
            b = r[5]
            self.page_map.append((b >> 4 & 0xF) * 10 + (b & 0xF))
            self._x(b"\x06", 1)
        missing = [p for p in self.block_order if p not in self.page_map]
        return {"ident": self.ident.decode(), "fingerprint": ack.hex(" "), "mem_size": mem_size,
                "page_map": self.page_map, "missing_pages": missing,
                "firmware": "memoria 0x%X" % mem_size, "sysinfo": self.responses}

    def _phys(self, logical_addr: int) -> int:
        page = self.block_order[logical_addr // self.PAGE]
        if page not in self.page_map:
            raise ProtocolError("Pagina %d no encontrada en el mapa de la radio (%s). "
                                "Puede ser la variante V2: no se continua." % (page, self.page_map))
        return (self.page_map.index(page) + 1) * self.PAGE + logical_addr % self.PAGE

    def read_memory(self, size, progress: Progress = _noprogress, ranges=None):
        out = bytearray(b"\xff" * size)
        ranges = ranges or ((0, size),)
        total = sum(e - s for s, e in ranges)
        done = 0
        for s, e in ranges:
            for la in range(s, e, self.block):
                r = self._x(self._frame(b"R", self._phys(la), self.block), self.block + 5)
                if len(r) != self.block + 5:
                    raise ProtocolError("Bloque incompleto en 0x%05X (%d B)" % (la, len(r)))
                out[la:la + self.block] = r[5:]
                self._x(b"\x06", 1)
                done += self.block
                progress(done, total, "Leyendo 0x%05X" % la)
        return out

    def write_block(self, addr, data):
        if len(data) != self.block:
            raise ProtocolError("Bloque de %d B (esperado %d)" % (len(data), self.block))
        r = self._x(self._frame(b"W", self._phys(addr), self.block, bytes(data)), 1)
        if r != b"\x06":
            raise ProtocolError("La radio no confirma la escritura de 0x%05X (%r)" % (addr, r))
