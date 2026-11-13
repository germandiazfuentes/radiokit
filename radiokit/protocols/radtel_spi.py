"""Protocolo de acceso a la flash SPI del Radtel RT-4D (DMR). 115200 baudios. SOLO LECTURA por ahora.

  Lectura de 1 KB:  PC -> 52 KH KL CS                     (KH:KL = n. de KB, CS = suma & 0xFF)
                    radio -> 3 B cabecera + 1024 B + CS    (cabecera[0] = FF => error / modo bootloader)
  Aviso de inicio:  PC -> 34 00 00 10 CS                   radio -> 06
  Cierre:           PC -> 34 52 05 EE 79
Protocolo documentado a partir del proyecto rt4d-cps (jcalado), usado solo como referencia.
La flash completa son 4 MB (4096 bloques); el formato del codeplug depende del firmware
(Radtel original o DualTachyon REFW), por eso se guarda la flash entera.
"""
from __future__ import annotations

from ..drivers.base import Progress, Protocol, ProtocolError, _noprogress


def _cs(b: bytes) -> int:
    return sum(b) & 0xFF


class RadtelSPIProtocol(Protocol):
    BAUDRATE = 115200
    TIMEOUT = 2.0
    KB = 1024

    def _read_kb(self, kb: int) -> bytes | None:
        cmd = bytearray([0x52, (kb >> 8) & 0xFF, kb & 0xFF, 0])
        cmd[3] = _cs(cmd[:3])
        self.t.write(bytes(cmd))
        r = self.t.read(1028, self.TIMEOUT)
        if len(r) != 1028 or r[0] == 0xFF or _cs(r[:-1]) != r[-1]:
            return None
        return r[3:1027]

    def identify(self):
        self.t.flush_input()
        first = self._read_kb(0)
        if first is None:
            return None                       # no es un RT-4D, o esta en modo bootloader
        cmd = bytearray([0x34, 0x00, 0x00, 0x10, 0])
        cmd[4] = _cs(cmd[:4])
        self.t.write(bytes(cmd))
        ack = self.t.read(1, self.TIMEOUT)
        if ack != b"\x06":
            return None
        printable = bytes(c if 32 <= c < 127 else 0x2E for c in first[:64]).decode()
        return {"ident": first[:16].hex(" ").upper(), "firmware": "?", "kb0_ascii": printable}

    def read_memory(self, size, progress: Progress = _noprogress, ranges=None):
        out = bytearray(b"\xff" * size)
        ranges = ranges or ((0, size),)
        total = sum(e - s for s, e in ranges)
        done = 0
        for s, e in ranges:
            for addr in range(s - s % self.KB, e, self.KB):
                d = None
                for _ in range(3):              # reintentos ante errores de suma de control
                    d = self._read_kb(addr // self.KB)
                    if d is not None:
                        break
                if d is None:
                    raise ProtocolError("No se puede leer la flash en 0x%06X" % addr)
                out[addr:addr + self.KB] = d
                done += self.KB
                progress(done, total, "Leyendo flash 0x%06X" % addr)
        return out

    # Zonas escribibles: (direccion, tamano, identificador de zona del protocolo)
    REGION_IDS = ((0x002000, 0x1000, 0x90), (0x004000, 0xC000, 0x91), (0x01C000, 0x20000, 0x92),
                  (0x05C000, 0x10000, 0x93), (0x07C000, 0x3000, 0x94), (0x082000, 0x3000, 0x95),
                  (0x0D6000, 0x1000, 0x99))
    WRITE_BLOCK = KB

    def write_block(self, addr, data):
        """Escribe 1 KB en la flash. Paquete: zona | KB dentro de la zona (2 B) | 1024 B | suma."""
        if len(data) != self.KB or addr % self.KB:
            raise ProtocolError("Escritura de RT-4D: bloques de 1 KB alineados")
        for base, size, rid in self.REGION_IDS:
            if base <= addr < base + size:
                kb = (addr - base) // self.KB
                break
        else:
            raise ProtocolError("0x%06X no pertenece a ninguna zona escribible" % addr)
        pkt = bytearray([rid, (kb >> 8) & 0xFF, kb & 0xFF]) + bytes(data) + b"\x00"
        pkt[-1] = _cs(pkt[:-1])
        self.t.write(bytes(pkt))
        ack = self.t.read(1, self.TIMEOUT)
        if ack != b"\x06":
            raise ProtocolError("El RT-4D no confirma la escritura en 0x%06X (respuesta %r)" % (addr, ack))

    def close(self):
        try:
            self.t.write(bytes([0x34, 0x52, 0x05, 0xEE, 0x79]))
        except Exception:  # noqa: BLE001
            pass
