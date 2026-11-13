"""Radtel RT-4D (DMR + analogico). Fase 1: copia de seguridad completa de la flash SPI (4 MB).

La decodificacion del codeplug (canales, contactos, grupos, zonas) depende del firmware instalado:
Radtel original (cambia de formato entre versiones) o DualTachyon REFW. Se anadira cuando se
disponga de una copia real de la radio y se sepa que firmware lleva.
"""
from __future__ import annotations

from ..core.model import Band, Capabilities
from ..protocols.radtel_spi import RadtelSPIProtocol
from . import register
from .base import RadioDriver


@register
class RadtelRT4D(RadioDriver):
    ID = "radtel.rt-4d"
    VENDOR = "Radtel"
    MODEL = "RT-4D"
    ALIASES = ("iRadio DM-4R",)
    PROTOCOL = RadtelSPIProtocol
    PROTOCOL_PARAMS = {}
    PRIORITY = 1
    MEM_SIZE = 4 * 1024 * 1024
    WRITE_BLOCK = 1024
    WRITABLE = ()                      # solo lectura
    REGIONS = ((0x000000, 0x400000, "Flash SPI completa (codeplug, contactos, calibracion...)", "unknown"),)
    NOTES = ("Solo copia de seguridad de la flash completa (~6 min a 115200). El editor de canales DMR "
             "se anadira tras analizar una copia real y el firmware de la radio.")

    # Canales: 1024 registros de 48 B en 0x4000 (formato del firmware original 3.13, verificado con
    # fotos de la pantalla). Campos confirmados:
    #   0x02 modo (0 = DMR, 1 = analogico, >=2 = vacio)   0x03 intervalo DMR (0 = TS1)
    #   0x04 codigo de color (DMR) | 0x04-05 subtono RX (analogico)
    #   0x06 RX y 0x0A TX: u32 LE en pasos de 10 Hz       0x0E-0F subtono TX (analogico)
    #   0x10 potencia (1 = alta)                           0x18-19 contacto DMR (indice, FFFF = ninguno)
    #   0x20-2F nombre (GBK, FF = vacio)
    # Subtonos u16 LE: nibble alto 1 = CTCSS (decimas de Hz), 2/3 = DCS normal/invertido (codigo octal).
    CH_BASE, CH_SIZE = 0x4000, 48

    @classmethod
    def capabilities(cls):
        return Capabilities(channels=(1, 1024), name_length=16, name_chars="", power_levels=("High", "Low"),
                            bandwidths=("Narrow", "Wide", "?"),
                            bands=(Band(136_000_000, 174_000_000), Band(400_000_000, 480_000_000)),
                            digital=True)

    @staticmethod
    def _tone(v: int):
        kind, val = v >> 12, v & 0x0FFF
        if kind == 1:
            return "%.1f" % (val / 10)
        if kind in (2, 3):
            return "D%03o%s" % (val, "N" if kind == 2 else "I")
        return None

    @classmethod
    def decode_channel(cls, mem, n):
        from ..core.model import Channel
        o = cls.CH_BASE + (n - 1) * cls.CH_SIZE
        r = bytes(mem[o:o + cls.CH_SIZE])
        if r == b"\xff" * cls.CH_SIZE or r[2] >= 2:
            return Channel(number=n, empty=True)
        u16 = lambda a: int.from_bytes(r[a:a + 2], "little")  # noqa: E731
        u32 = lambda a: int.from_bytes(r[a:a + 4], "little")  # noqa: E731
        rx, tx = u32(0x06), u32(0x0A)
        name = r[0x20:0x30].replace(b"\xff", b"").decode("gbk", "replace").strip("\x00 ")
        digital = r[2] == 0
        extra = {"modo": "DMR" if digital else "FM"}
        if digital:
            contact = u16(0x18)
            extra.update(timeslot=r[3] + 1, color_code=r[4], contacto=None if contact == 0xFFFF else contact + 1)
        return Channel(
            number=n, empty=False, name=name, rx_freq=rx * 10,
            tx_freq=None if tx in (0, 0xFFFFFFFF) else tx * 10,
            rx_tone=None if digital else cls._tone(u16(0x04)),
            tx_tone=None if digital else cls._tone(u16(0x0E)),
            power="High" if r[0x10] == 1 else "Low", bandwidth="?", scan=True, extra=extra)

    @classmethod
    def validate_channel(cls, ch):
        return ["RT-4D: la edicion de canales aun no esta disponible (solo lectura)"]

    @classmethod
    def encode_channel(cls, mem, ch):
        raise NotImplementedError("RT-4D: edicion aun no disponible")
