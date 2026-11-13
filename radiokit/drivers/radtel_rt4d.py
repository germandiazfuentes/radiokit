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
    #   0x02 modo (0 = DMR, 1 = analogico, >=2 = vacio)
    #   0x03 DMR: intervalo (0 = TS1) | analogico: ancho (0 = Wide, 1 = Narrow; verificado por diferencia)
    #   0x04 codigo de color (DMR) | 0x04-05 subtono RX (analogico)
    #   0x05 DMR: modo doble intervalo (1 = Dual Slot on; verificado por diferencia)
    #   0x13 bit 7 = excluido del escaneo (verificado); TX se guarda absoluta (offset ya aplicado)
    # Firmware verificado: "RT-4D Test V3.13 2025-01-08" (no publicado en la web de Radtel).
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
        tot_list = ("Off", "5 s", "10 s", "15 s", "30 s")      # posicion en la lista del menu (verificado)
        extra = {"modo": "DMR" if digital else "FM",
                 "tot": tot_list[r[0x14]] if r[0x14] < len(tot_list) else "posicion %d" % r[0x14]}
        if digital:
            contact = u16(0x18)
            politely = ("Impolite", "Carrier Match", "CC match")
            extra.update(timeslot=r[3] + 1, color_code=r[4], dual_slot=bool(r[5]),
                         tx_politely=politely[r[0x11]] if r[0x11] < 3 else r[0x11],
                         cifrado=("Key%d" % u16(0x1A)) if u16(0x1A) not in (0, 0xFFFF) else "Off",
                         contacto=None if contact == 0xFFFF else contact + 1)
        return Channel(
            number=n, empty=False, name=name, rx_freq=rx * 10,
            tx_freq=None if tx in (0, 0xFFFFFFFF) else tx * 10,
            rx_tone=None if digital else cls._tone(u16(0x04)),
            tx_tone=None if digital else cls._tone(u16(0x0E)),
            power="High" if r[0x10] == 1 else "Low",
            bandwidth="Narrow" if digital else ("Narrow" if r[3] == 1 else "Wide"),   # DMR siempre 12.5 kHz
            scan=not (r[0x13] & 0x80), extra=extra)                                  # 0x13 bit 7 = Remove

    KNOWN_FIELDS = {0x02: "modo", 0x03: "intervalo DMR / ancho analogico", 0x04: "CC / subtono RX",
                    0x05: "Dual Slot (DMR) / subtono RX",
                    0x06: "RX", 0x07: "RX", 0x08: "RX", 0x09: "RX", 0x0A: "TX", 0x0B: "TX", 0x0C: "TX",
                    0x0D: "TX", 0x0E: "subtono TX", 0x0F: "subtono TX", 0x10: "potencia",
                    0x11: "TX Politely (0 Impolite, 1 Carrier, 2 CC match)",
                    0x13: "escaneo (bit 7 = Remove) + otros bits", 0x18: "contacto",
                    0x14: "TOT (posicion en la lista: Off, 5s, 10s, 15s, 30s...)",
                    0x1A: "cifrado (n. de clave, 0 = off)", 0x1B: "cifrado",
                    0x19: "contacto"}

    @classmethod
    def explain_offset(cls, a: int) -> str:
        """Texto que explica a que corresponde una direccion de la flash (para analizar diferencias)."""
        if cls.CH_BASE <= a < cls.CH_BASE + 1024 * cls.CH_SIZE:
            n, off = divmod(a - cls.CH_BASE, cls.CH_SIZE)
            if off >= 0x20:
                return "canal %d, nombre[%d]" % (n + 1, off - 0x20)
            return "canal %d, byte 0x%02X (%s)" % (n + 1, off, cls.KNOWN_FIELDS.get(off, "DESCONOCIDO"))
        for s, e, name in ((0x0000, 0x2000, "calibracion"), (0x2000, 0x3000, "ajustes (banco 0)"),
                           (0x3000, 0x4000, "ajustes (banco 1)"), (0x1C000, 0x3C000, "zonas"),
                           (0x5C000, 0x6C000, "contactos"), (0x7C000, 0x7F000, "grupos RX"),
                           (0x82000, 0x85000, "claves de cifrado"), (0xD6000, 0xD7000, "radio FM")):
            if s <= a < e:
                return "%s +0x%04X" % (name, a - s)
        return ""

    @classmethod
    def validate_channel(cls, ch):
        return ["RT-4D: la edicion de canales aun no esta disponible (solo lectura)"]

    @classmethod
    def encode_channel(cls, mem, ch):
        raise NotImplementedError("RT-4D: edicion aun no disponible")
