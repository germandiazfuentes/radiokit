"""Protocolo de clonado Baofeng "clasico" (UV-5R, UV-82, BF-F8HP, WP970I, UV-S9X3, UV-S Plus...).

  PC -> magic (7 B, byte a byte)   radio -> 06
  PC -> 02                         radio -> ident (8 B AA..DD; 12 B en algunos UV-6)
  PC -> 06                         radio -> 06          (modo programacion)
  Lectura:   PC -> 'S' AH AL LEN    radio -> [06] 'X' AH AL LEN datos   PC -> 06
  Escritura: PC -> 'X' AH AL LEN datos                                   radio -> 06
Referencia: CHIRP chirp/drivers/baofeng_common.py y uv5r.py (GPLv3); reimplementado aqui.
"""
from __future__ import annotations

import struct
import time

from ..drivers.base import Progress, Protocol, ProtocolError, _noprogress


class BaofengCloneProtocol(Protocol):
    BAUDRATE = 9600
    TIMEOUT = 1.5

    @classmethod
    def probe_variants(cls, params):
        out = []
        for m in params["magics"]:
            p = dict(params, magic=m)
            p.pop("magics")
            out.append(((cls.__name__, m), p))
        return out

    def __init__(self, transport, magic: bytes, read_block: int = 0x40, write_block: int = 0x10,
                 magic_delay: float = 0.01, fw_block: int = 0x1EC0):
        super().__init__(transport, magic=magic)
        self.magic, self.rblock, self.wblock = magic, read_block, write_block
        self.magic_delay, self.fw_block = magic_delay, fw_block
        self.WRITE_BLOCK = write_block
        self._first_read = True
        self.dropped_byte = False

    def _recv(self, n):
        return self.t.read(n, self.TIMEOUT)

    def identify(self):
        t = self.t
        t.flush_input()
        for b in self.magic:                    # como CHIRP: byte a byte con pausa
            t.write(bytes([b]))
            time.sleep(self.magic_delay)
        if self._recv(1) != b"\x06":
            return None
        t.write(b"\x02")
        ident = b""
        for _ in range(12):                     # 8 B normalmente, 12 B en algunos UV-6
            c = self._recv(1)
            ident += c
            if c in (b"", b"\xdd"):
                break
        if len(ident) not in (8, 12) or ident[:1] != b"\xaa" or ident[-1:] != b"\xdd":
            return None
        t.write(b"\x06")
        if self._recv(1) != b"\x06":
            return None
        # Firmware: leer antes un bloque fuera de la zona auxiliar (firmwares nuevos devuelven basura si no)
        self.read_block(0x1E80, 0x40)
        fwb = self.read_block(self.fw_block, 0x40)
        b5 = self.read_block(0x1FC0, 0x40)
        self.dropped_byte = b5[15] == 0xFF
        firmware = fwb[48:62].replace(b"\xff", b"").decode("ascii", "replace").strip("\x00 ")
        return {"ident": ident.hex(" ").upper(), "firmware": firmware,
                "dropped_byte": self.dropped_byte, "magic": self.magic.hex(" ").upper()}

    def read_block(self, addr: int, size: int) -> bytes:
        self.t.write(struct.pack(">BHB", ord("S"), addr, size))
        if not self._first_read:
            ack = self._recv(1)
            if ack != b"\x06":
                raise ProtocolError("La radio rechaza leer 0x%04X (ack=%r)" % (addr, ack))
        self._first_read = False
        hdr = self._recv(4)
        if len(hdr) != 4:
            raise ProtocolError("Sin respuesta al leer 0x%04X" % addr)
        cmd, a, n = struct.unpack(">BHB", hdr)
        if cmd != ord("X") or a != addr or n != size:
            raise ProtocolError("Respuesta invalida en 0x%04X: %s" % (addr, hdr.hex(" ")))
        data = self._recv(size)
        if len(data) != size:
            raise ProtocolError("Bloque incompleto en 0x%04X (%d/%d)" % (addr, len(data), size))
        self.t.write(b"\x06")
        time.sleep(0.05)
        return data

    def read_memory(self, size, progress: Progress = _noprogress, ranges=None):
        out = bytearray(b"\xff" * size)
        ranges = ranges or ((0, size),)
        total = sum(e - s for s, e in ranges)
        done = 0
        for s, e in ranges:
            addr = s
            while addr < e:
                # Radios con "dropped byte": el ultimo tramo hay que leerlo en bloques de 0x10
                bs = 0x10 if (self.dropped_byte and addr >= 0x1FC0) else min(self.rblock, e - addr)
                out[addr:addr + bs] = self.read_block(addr, bs)
                addr += bs
                done += bs
                progress(done, total, "Leyendo 0x%04X" % addr)
        return out

    def write_block(self, addr, data):
        if len(data) != self.wblock:
            raise ProtocolError("Bloque de escritura de tamano %d (esperado %d)" % (len(data), self.wblock))
        self.t.write(struct.pack(">BHB", ord("X"), addr, len(data)) + bytes(data))
        time.sleep(0.05)
        ack = self._recv(1)
        if ack != b"\x06":
            raise ProtocolError("La radio no confirma la escritura de 0x%04X (ack=%r)" % (addr, ack))
