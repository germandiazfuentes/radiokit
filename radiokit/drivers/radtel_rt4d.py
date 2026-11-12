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

    @classmethod
    def capabilities(cls):
        return Capabilities(channels=(1, 0), name_length=16, name_chars="", power_levels=("High", "Low"),
                            bandwidths=("Narrow", "Wide"),
                            bands=(Band(136_000_000, 174_000_000), Band(400_000_000, 480_000_000)),
                            digital=True)

    @classmethod
    def decode_channel(cls, mem, number):
        raise NotImplementedError("Codeplug del RT-4D aun no decodificado")

    @classmethod
    def encode_channel(cls, mem, ch):
        raise NotImplementedError("Codeplug del RT-4D aun no decodificado")
