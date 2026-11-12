"""Protocolo Quansheng UV-K5 / UV-K6 / UV-5R Plus (Quansheng) y clones. 38400 baudios.

Paquete:  AB CD | LEN | 00 | XOR(payload + CRC16-XMODEM LE) | DC BA
Respuesta: AB CD | LEN | 00 | XOR(cuerpo) | 2 B | DC BA
  Hola:     14 05 04 00 <ts 4 B>                      -> 15 05 ... firmware (ASCII desde el byte 4)
  Leer:     1B 05 08 00 <addr LE 2 B> <len> 00 <ts>    -> 1C 05 ... datos desde el byte 8
  Escribir: 1D 05 <len+8> 00 <addr LE> <len> 01 <ts> datos -> 1E 05 .. .. <addr LE>
  Reiniciar: DD 05 00 00
La radio NO entra en un modo de programacion especial: sigue funcionando mientras se lee.
Referencia: CHIRP uvk5.py (GPLv3); reimplementado aqui.
"""
from __future__ import annotations

import struct

from ..drivers.base import Progress, Protocol, ProtocolError, _noprogress

XOR_TABLE = (22, 108, 20, 230, 46, 145, 13, 64, 33, 53, 213, 64, 19, 3, 233, 128)
TIMESTAMP = b"\x6a\x39\x57\x64"


def xor(data: bytes) -> bytes:
    return bytes(b ^ XOR_TABLE[i % 16] for i, b in enumerate(data))


def crc16_xmodem(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return crc


def make_packet(payload: bytes) -> bytes:
    body = payload + struct.pack("<H", crc16_xmodem(payload))
    return struct.pack(">HBB", 0xABCD, len(payload), 0) + xor(body) + b"\xdc\xba"


class QuanshengK5Protocol(Protocol):
    BAUDRATE = 38400
    TIMEOUT = 0.8
    READ_BLOCK = 0x80
    WRITE_BLOCK = 0x80

    def _send(self, payload: bytes):
        self.t.write(make_packet(payload))

    def _reply(self) -> bytes | None:
        hdr = self.t.read(4, self.TIMEOUT)
        if len(hdr) != 4:
            return None
        if hdr[0] != 0xAB or hdr[1] != 0xCD or hdr[3] != 0:
            raise ProtocolError("Cabecera invalida: %s" % hdr.hex(" "))
        body = self.t.read(hdr[2], self.TIMEOUT)
        foot = self.t.read(4, self.TIMEOUT)
        if len(body) != hdr[2] or len(foot) != 4 or foot[2:] != b"\xdc\xba":
            raise ProtocolError("Respuesta incompleta o pie invalido")
        return xor(body)

    def identify(self):
        self.t.flush_input()
        for _ in range(3):
            self._send(b"\x14\x05\x04\x00" + TIMESTAMP)
            try:
                rep = self._reply()
            except ProtocolError:
                return None
            if rep:
                break
        else:
            return None
        if rep[:2] == b"\x18\x05":
            raise ProtocolError("La radio esta en modo de actualizacion de firmware: reiniciala en modo normal")
        if rep[:2] != b"\x15\x05":
            return None
        fw = bytearray()
        for c in rep[4:29]:
            if c < 0x20 or c > 0x7E:
                break
            fw.append(c)
        return {"ident": rep[:4].hex(" ").upper(), "firmware": fw.decode("ascii")}

    def read_block(self, addr: int, n: int) -> bytes:
        self._send(b"\x1b\x05\x08\x00" + struct.pack("<HBB", addr, n, 0) + TIMESTAMP)
        rep = self._reply()
        if not rep or rep[:2] != b"\x1c\x05" or len(rep) < 8 + n:
            raise ProtocolError("Lectura invalida en 0x%04X" % addr)
        return rep[8:8 + n]

    def read_memory(self, size, progress: Progress = _noprogress, ranges=None):
        out = bytearray(b"\xff" * size)
        ranges = ranges or ((0, size),)
        total = sum(e - s for s, e in ranges)
        done = 0
        for s, e in ranges:
            for a in range(s, e, self.READ_BLOCK):
                n = min(self.READ_BLOCK, e - a)
                out[a:a + n] = self.read_block(a, n)
                done += n
                progress(done, total, "Leyendo 0x%04X" % a)
        return out

    def write_block(self, addr, data):
        n = len(data)
        self._send(b"\x1d\x05" + struct.pack("<BBHBB", n + 8, 0, addr, n, 1) + TIMESTAMP + bytes(data))
        rep = self._reply()
        if not rep or rep[0] != 0x1E or rep[4] != (addr & 0xFF) or rep[5] != (addr >> 8):
            raise ProtocolError("La radio no confirma la escritura de 0x%04X" % addr)

    def finish_write(self):
        self._send(b"\xdd\x05\x00\x00")     # reinicio: la radio recarga la EEPROM
