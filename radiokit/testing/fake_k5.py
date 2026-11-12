"""Emulador del protocolo Quansheng UV-K5 (paquetes ofuscados con CRC)."""
from __future__ import annotations

import struct

from ..core.transport import Transport
from ..protocols.quansheng_k5 import crc16_xmodem, xor


class FakeUVK5(Transport):
    def __init__(self, eeprom: bytes, firmware: str = "k5_2.01.26"):
        self.mem = bytearray(eeprom)
        self.firmware = firmware
        self.out = bytearray()
        self.baud = 38400
        self.writes: list[int] = []
        self.resets = 0

    def open(self):
        self.out.clear()

    def close(self):
        pass

    def set_baudrate(self, baud):
        self.baud = baud

    def flush_input(self):
        self.out.clear()

    def read(self, n, timeout=1.0):
        d = bytes(self.out[:n])
        del self.out[:n]
        return d

    def _reply(self, body: bytes):
        self.out += struct.pack(">HBB", 0xABCD, len(body), 0) + xor(body) + b"\x00\x00\xdc\xba"

    def write(self, pkt: bytes):
        if self.baud != 38400 or len(pkt) < 8 or pkt[:2] != b"\xab\xcd" or pkt[-2:] != b"\xdc\xba":
            return
        n = pkt[2]
        plain = xor(pkt[4:-2])
        payload, crc = plain[:n], plain[n:n + 2]
        if struct.pack("<H", crc16_xmodem(payload)) != crc:
            return                                   # CRC incorrecto: la radio lo ignora
        cmd = payload[:2]
        if cmd == b"\x14\x05":
            self._reply(b"\x15\x05\x24\x00" + self.firmware.encode().ljust(16, b"\x00") + bytes(16))
        elif cmd == b"\x1b\x05":
            addr, ln = struct.unpack("<HB", payload[4:7])
            self._reply(b"\x1c\x05" + struct.pack("<BBHBB", ln + 4, 0, addr, ln, 0) + self.mem[addr:addr + ln])
        elif cmd == b"\x1d\x05":
            addr, ln = struct.unpack("<HB", payload[4:7])
            self.mem[addr:addr + ln] = payload[12:12 + ln]
            self.writes.append(addr)
            self._reply(b"\x1e\x05\x02\x00" + struct.pack("<H", addr))
        elif cmd == b"\xdd\x05":
            self.resets += 1
