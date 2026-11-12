"""Baofeng UV-13 Pro (V1/V2) - familia UV-17. 999 canales, nombres de 11 caracteres.

Imagen logica de 0x9000 bytes (9 paginas de 4 KB en el orden 16,17,18,19,24,25,26,4,6).
Mapa tomado de CHIRP baofeng_uv17.py (GPLv3). EXPERIMENTAL: CHIRP tiene errores abiertos con la V2
("memoria corrupta"), por eso la escritura queda bloqueada hasta verificar con la radio real.
"""
from __future__ import annotations

from ..core.model import Band, Capabilities, Channel, format_tone, parse_tone
from ..core.settings import Setting as S
from ..protocols.baofeng_uv17 import BaofengUV17Protocol
from . import register
from .base import RadioDriver

G_B, G_D = "Basicos", "Pantalla y avisos"
UV17_SETTINGS = (
    S("squelch", "Squelch", G_B, 0x7041, "list", ("Off",) + tuple("123456789"), menu="SQL"),
    S("tot", "Tiempo max. de transmision", G_B, 0x7040, "list",
      ("Off",) + tuple("%d s" % x for x in range(15, 615, 15)), menu="TOT"),
    S("voice", "Idioma de voz", G_B, 0x7043, "list", ("Chinese", "English"), bit=1, width=1),
    S("voicesw", "Voz activada", G_B, 0x7043, "bool", bit=0, width=1),
    S("autolock", "Bloqueo automatico", G_B, 0x7045, "bool", bit=6, width=1),
    S("beep", "Pitido de teclas", G_B, 0x7045, "bool", bit=7, width=1),
    S("tail", "Eliminar cola de squelch", G_B, 0x7045, "bool", bit=4, width=1),
    S("scanmode", "Modo de escaneo", G_B, 0x7045, "list", ("Time", "Carrier", "Search"), bit=2, width=2),
    S("dtmfst", "Tono local DTMF", G_B, 0x7045, "list", ("Off", "DT-ST", "ANI-ST", "DT+ANI"), bit=0, width=2),
    S("dualstandby", "Doble escucha", G_B, 0x7046, "bool", bit=6, width=1),
    S("roger", "Pitido Roger", G_B, 0x7046, "bool", bit=5, width=1),
    S("fmenable", "Radio FM habilitada", G_B, 0x7046, "bool", bit=1, width=1),
    S("backlight", "Retroiluminacion", G_D, 0x7044, "list",
      ("Always On",) + tuple("%d s" % x for x in range(1, 11))),
    S("powerondistype", "Al encender mostrar", G_D, 0x7000, "list", ("Full", "Message", "Voltage")),
    S("boottext1", "Mensaje de encendido 1", G_D, 0x7010, "text", width=10),
    S("boottext2", "Mensaje de encendido 2", G_D, 0x7020, "text", width=10),
    S("chadistype", "Pantalla linea A", G_D, 0x7050, "list", ("Name", "Frequency"), bit=0, width=1),
    S("chbdistype", "Pantalla linea B", G_D, 0x7050, "list", ("Name", "Frequency"), bit=1, width=1),
)


@register
class BaofengUV13Pro(RadioDriver):
    ID = "baofeng.uv-13pro"
    VENDOR = "Baofeng"
    MODEL = "UV-13 Pro"
    ALIASES = ("UV-13 Pro V2", "UV-17 (familia)")
    PROTOCOL = BaofengUV17Protocol
    PROTOCOL_PARAMS = {}
    PRIORITY = 3
    MEM_SIZE = 0x9000
    WRITE_BLOCK = 0x40
    EXPERIMENTAL = True
    MEM_SIZES = (0x31FFF,)        # respuesta de tamano de memoria conocida (V1); la V2 se anadira al verificarla
    WRITABLE = ((0x0000, 0x7000, "Canales y nombres"), (0x7000, 0x7060, "Ajustes"))
    REGIONS = (
        (0x0010, 0x0030, "VFO A/B", "settings"),
        (0x0030, 0x4000, "Canales (999 x 16 B, en 4 tramos)", "user"),
        (0x4000, 0x7000, "Nombres (11 caracteres)", "user"),
        (0x7000, 0x7060, "Ajustes", "settings"),
        (0x8000, 0x8060, "PTT-ID / ANI", "user"),
    )
    SETTINGS = UV17_SETTINGS
    NOTES = ("Experimental (solo lectura). CHIRP reporta 'memoria corrupta' con algunas V2: se verificara "
             "con una radio real antes de habilitar la escritura.")

    @classmethod
    def matches(cls, info):
        return info.get("mem_size") in cls.MEM_SIZES

    @classmethod
    def capabilities(cls):
        return Capabilities(channels=(1, 999), name_length=11,
                            name_chars="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 !@#$%^&*()+-=[]:\";'<>?,./",
                            power_levels=("High", "Low"), bandwidths=("Narrow", "Wide"),
                            bands=(Band(136_000_000, 174_000_000), Band(400_000_000, 520_000_000)))

    # ---- direcciones ----------------------------------------------------------
    @staticmethod
    def _ch_addr(n: int) -> int:
        i = n - 1
        if i >= 762:
            return 0x3000 + 16 * (i - 762)
        if i >= 507:
            return 0x2000 + 16 * (i - 507)
        if i >= 252:
            return 0x1000 + 16 * (i - 252)
        return 0x0030 + 16 * i

    @staticmethod
    def _name_addr(n: int) -> int:
        i = n - 1
        if i >= 744:
            return 0x6000 + 11 * (i - 744)
        if i >= 372:
            return 0x5000 + 11 * (i - 372)
        return 0x4000 + 11 * i

    # ---- codificacion -----------------------------------------------------------
    @staticmethod
    def _lbcd_get(b):
        return int("".join("%02x" % x for x in reversed(b)))

    @staticmethod
    def _lbcd_put(v):
        s = "%08d" % v
        return bytes(int(s[i:i + 2], 16) for i in range(6, -1, -2))

    @staticmethod
    def _bcd(v: int) -> int:
        return (v & 0xF) + (v >> 4 & 0xF) * 10 + (v >> 8 & 0xF) * 100 + (v >> 12 & 0xF) * 1000

    @staticmethod
    def _tobcd(n: int) -> int:
        s = "%04d" % n
        return (int(s[0]) << 12) | (int(s[1]) << 8) | (int(s[2]) << 4) | int(s[3])

    @classmethod
    def _tone_get(cls, v):
        if v in (0, 0xFFFF):
            return None
        if v & 0x8000:
            return format_tone(("dcs", cls._bcd(v & 0x0FFF), "I" if (v & 0xC000) == 0xC000 else "N"))
        return format_tone(("ctcss", cls._bcd(v) / 10.0))

    @classmethod
    def _tone_put(cls, t):
        p = parse_tone(t)
        if p is None:
            return 0
        if p[0] == "ctcss":
            return cls._tobcd(round(p[1] * 10))
        return 0x8000 | cls._tobcd(p[1]) | (0x4000 if p[2] == "I" else 0)

    @classmethod
    def decode_channel(cls, mem, n):
        o = cls._ch_addr(n)
        r = mem[o:o + 16]
        if r[0] == 0xFF:
            return Channel(number=n, empty=True)
        txinh = bytes(r[4:8]) in (b"\xff" * 4, b"\x00" * 4)
        na = cls._name_addr(n)
        name = bytes(mem[na:na + 11]).replace(b"\xff", b"\x00").split(b"\x00")[0]
        return Channel(
            number=n, empty=False, name=name.decode("ascii", "replace").rstrip(),
            rx_freq=cls._lbcd_get(r[0:4]) * 10,
            tx_freq=None if txinh else cls._lbcd_get(r[4:8]) * 10,
            rx_tone=cls._tone_get(int.from_bytes(r[9:11], "little")),
            tx_tone=cls._tone_get(int.from_bytes(r[11:13], "little")),
            power="High" if r[13] & 0x02 else "Low",
            bandwidth="Wide" if r[13] & 0x04 else "Narrow",
            bcl=bool(r[13] & 0x40), pttid=("Off", "BOT", "EOT", "Both")[(r[13] >> 4) & 3],
            scan=bool(r[14] & 0x01), scode=(r[14] >> 4) & 0x0F)

    @classmethod
    def encode_channel(cls, mem, ch):
        errs = cls.validate_channel(ch)
        if errs:
            raise ValueError("Canal %d: %s" % (ch.number, "; ".join(errs)))
        o, na = cls._ch_addr(ch.number), cls._name_addr(ch.number)
        old = cls.decode_channel(mem, ch.number)
        if ch.empty:
            if not old.empty:
                mem[o:o + 16] = b"\xff" * 16
            return
        if old.empty:
            mem[o:o + 16] = bytes(16)
        r = mem[o:o + 16]
        if old.empty or ch.rx_freq != old.rx_freq:
            r[0:4] = cls._lbcd_put(ch.rx_freq // 10)
        if old.empty or ch.tx_freq != old.tx_freq:
            r[4:8] = b"\xff" * 4 if ch.tx_freq is None else cls._lbcd_put(ch.tx_freq // 10)
        if old.empty or ch.rx_tone != old.rx_tone:
            r[9:11] = cls._tone_put(ch.rx_tone).to_bytes(2, "little")
        if old.empty or ch.tx_tone != old.tx_tone:
            r[11:13] = cls._tone_put(ch.tx_tone).to_bytes(2, "little")
        b13 = r[13] & ~(0x40 | 0x30 | 0x04 | 0x02) & 0xFF
        b13 |= (0x40 if ch.bcl else 0) | (("Off", "BOT", "EOT", "Both").index(ch.pttid) << 4)
        b13 |= (0x04 if ch.bandwidth == "Wide" else 0) | (0x02 if ch.power == "High" else 0)
        r[13] = b13
        r[14] = (r[14] & 0x0E) | ((ch.scode & 0x0F) << 4) | (0x01 if ch.scan else 0)
        mem[o:o + 16] = r
        if old.empty or ch.name.upper() != old.name:
            mem[na:na + 11] = ch.name.upper().encode("ascii")[:11].ljust(11, b"\x00")
