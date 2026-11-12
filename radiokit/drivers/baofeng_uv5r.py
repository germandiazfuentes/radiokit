"""Baofeng UV-5R (familia clasica).

Comparte handshake con el UV-S Plus/UV-S9X3 (50 BB FF 20 12 07 25) y, en direcciones de radio, el mismo
mapa de memoria que la familia WP970I (canales 0x0000, ajustes 0x0E20, nombres 0x1000, aux 0x1EC0+).
Diferencias: solo existen 0x0000-0x1800 y 0x1EC0-0x2000, 2 niveles de potencia, firmware BFB/BFS/N5R...
Referencia: CHIRP uv5r.py (GPLv3).
"""
from __future__ import annotations

import re

from ..core.model import Band
from . import register
from .baofeng_wp970i import MAGIC_UVS9X3, WP970I_SETTINGS, WP970IFamily

MAGIC_UV5R_ORIG = bytes.fromhex("50BBFF0125984D")   # firmwares anteriores a BFB291

# Prefijos de firmware de UV-5R (CHIRP BASETYPE_UV5R). "HN5RV" es UV-S Plus/UV-82X3 -> otro driver.
UV5R_FIRMWARES = ("BFS", "BFB", "N5R-2", "N5R2", "N5RV", "BTS", "D5R2", "B5R2")


@register
class BaofengUV5R(WP970IFamily):
    ID = "baofeng.uv-5r"
    MODEL = "UV-5R"
    ALIASES = ("UV-5R+", "UV-5RE", "UV-5RA")
    PROTOCOL_PARAMS = {"magics": (MAGIC_UVS9X3, MAGIC_UV5R_ORIG)}
    PRIORITY = 5
    NAME_LEN = 7
    POWER = ("High", "Low")            # bits lowpower: 0 = High (4-5 W), 1 = Low (1 W)
    BANDS = (Band(136_000_000, 174_000_000), Band(400_000_000, 520_000_000))
    READ_RANGES = ((0x0000, 0x1800), (0x1EC0, 0x2000))
    WRITABLE = tuple(w for w in WP970IFamily.WRITABLE if w[0] < 0x1800)   # sin mensaje de encendido
    SETTINGS = tuple(s for s in WP970I_SETTINGS if not s.key.startswith("poweron"))
    REGIONS = (
        (0x0000, 0x0800, "Canales (128 x 16 B)", "user"),
        (0x0B00, 0x0BF0, "Codigos PTT-ID", "user"),
        (0x0C80, 0x0CB3, "DTMF / ANI", "user"),
        (0x0E20, 0x0E4E, "Ajustes de menu", "settings"),
        (0x0E76, 0x0E78, "Canal activo A/B", "settings"),
        (0x0F08, 0x0F48, "VFO A/B", "settings"),
        (0x0F4E, 0x0F50, "Emisora FM", "settings"),
        (0x1000, 0x1800, "Nombres de canal", "user"),
        (0x1EC0, 0x1EE0, "Auxiliar / mensaje tecla 6", "service"),
        (0x1EE0, 0x1EEE, "Mensaje de encendido", "settings"),
        (0x1EF0, 0x1EFE, "Firmware", "service"),
        (0x1F00, 0x1F60, "Calibracion", "service"),
        (0x1F60, 0x1FA0, "Umbrales de squelch", "service"),
        (0x1FA0, 0x1FC0, "Calibracion sin documentar", "service"),
        (0x1FC0, 0x1FCA, "Limites de banda TX", "service"),
    )
    NOTES = ("Mapa de CHIRP; pendiente de verificar con una radio real. Firmwares anteriores a BFB291 "
             "quedan en solo lectura.")

    @classmethod
    def matches(cls, info):
        fw = info.get("firmware", "")
        return not fw.startswith("HN5RV") and fw.startswith(UV5R_FIRMWARES)

    @classmethod
    def _bfb_version(cls, fw: str) -> int | None:
        m = re.search(r"BFB(\d{3})", fw)
        return int(m.group(1)) if m else None

    @classmethod
    def write_block_reason(cls, image):
        r = super().write_block_reason(image)
        if r:
            return r
        fw = image.meta.get("firmware") or cls.info_from_image(image).get("firmware", "")
        v = cls._bfb_version(fw)
        if v is not None and v < 291:
            return "Firmware original %s (anterior a BFB291): otro mapa de memoria, solo lectura." % fw
        if not image.meta.get("hardware_verified") and not cls.HARDWARE_VERIFIED:
            return ("UV-5R aun sin verificar con hardware: haz primero una lectura y comprueba los canales "
                    "con la pantalla. Despues se habilitara la escritura.")
        return None

    HARDWARE_VERIFIED = False

    @classmethod
    def chirp_export(cls, image):
        ident = bytes.fromhex(image.meta.get("ident", "AA 00 00 00 00 00 00 DD").replace(" ", ""))[:8]
        body = ident + bytes(image.data[0:0x1800]) + bytes(image.data[0x1EC0:0x2000])
        return body, {"rclass": "BaofengUV5R", "vendor": "Baofeng", "model": "UV-5R", "variant": "",
                      "chirp_version": "radiokit"}
