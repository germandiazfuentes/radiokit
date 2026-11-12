"""Familia Baofeng WP970I (mapa de 0x2000 bytes): UV-S Plus (tri), UV-S9X3, BF-A58S, UV-9R...

Mapa de memoria tomado de CHIRP baofeng_wp970i.py (GPLv3) y verificado con volcados reales
de dos UV-S Plus (firmware HN5RV011). Ver docs/INVESTIGACION_Y_DISENO.md.
"""
from __future__ import annotations

from ..core.image import MemoryImage
from ..core.model import Band, Capabilities, Channel, DCS_CODES, format_tone, parse_tone
from ..core.settings import Setting as S
from ..protocols.baofeng_clone import BaofengCloneProtocol
from . import register
from .base import RadioDriver

MAGIC_WP970I = bytes.fromhex("50BBFF20140413")
MAGIC_UVS9X3 = bytes.fromhex("50BBFF20120725")

OFF1TO9 = ("Off",) + tuple("123456789")
OFF1TO10 = OFF1TO9 + ("10",)
COLORS = ("Off", "Blue", "Orange", "Purple")
G_BASIC, G_DISPLAY, G_SCAN, G_DTMF, G_ADV, G_SERVICE = (
    "Basicos", "Pantalla y avisos", "Doble escucha y escaneo", "PTT-ID / DTMF", "Avanzados", "Servicio")

WP970I_SETTINGS = (
    S("squelch", "Squelch", G_BASIC, 0x0E20, "list", OFF1TO9, menu="SQL"),
    S("save", "Ahorro de bateria", G_BASIC, 0x0E23, "list", ("Off", "1:1", "1:2", "1:3", "1:4"), menu="SAVE"),
    S("vox", "VOX", G_BASIC, 0x0E24, "list", OFF1TO10, menu="VOX", help="Transmision por voz. Off = desactivado"),
    S("timeout", "Tiempo max. de transmision", G_BASIC, 0x0E29, "list",
      tuple("%d s" % x for x in range(15, 615, 15)), menu="TOT"),
    S("beep", "Pitido de teclas", G_BASIC, 0x0E28, "bool", menu="BEEP"),
    S("voice", "Voz", G_BASIC, 0x0E2E, "list", ("Off", "English", "Chinese"), menu="VOICE"),
    S("roger", "Pitido fin de transmision (Roger)", G_BASIC, 0x0E47, "bool", menu="ROGER"),
    S("ste", "Eliminar cola de squelch", G_BASIC, 0x0E43, "bool", menu="STE"),
    S("autolk", "Bloqueo automatico de teclado", G_BASIC, 0x0E38, "bool", menu="AUTOLK"),
    S("keylock", "Teclado bloqueado", G_BASIC, 0x0E4D, "bool"),
    S("abr", "Retroiluminacion", G_DISPLAY, 0x0E26, "list", OFF1TO10, menu="ABR"),
    S("mdfa", "Pantalla linea A", G_DISPLAY, 0x0E35, "list", ("Channel", "Name", "Frequency"), menu="MDF-A"),
    S("mdfb", "Pantalla linea B", G_DISPLAY, 0x0E36, "list", ("Channel", "Name", "Frequency"), menu="MDF-B"),
    S("wtled", "Color en espera", G_DISPLAY, 0x0E3D, "list", COLORS, menu="WT-LED"),
    S("rxled", "Color en recepcion", G_DISPLAY, 0x0E3E, "list", COLORS, menu="RX-LED"),
    S("txled", "Color en transmision", G_DISPLAY, 0x0E3F, "list", COLORS, menu="TX-LED"),
    S("ponmsg", "Al encender mostrar", G_DISPLAY, 0x0E46, "list", ("Full", "Message"), menu="PONMSG"),
    S("poweron1", "Mensaje de encendido 1", G_DISPLAY, 0x1EE0, "text", width=7),
    S("poweron2", "Mensaje de encendido 2", G_DISPLAY, 0x1EE7, "text", width=7),
    S("displayab", "Linea activa", G_DISPLAY, 0x0E4A, "list", ("A", "B"), bit=7, width=1),
    S("tdr", "Doble escucha", G_SCAN, 0x0E27, "bool", menu="TDR"),
    S("tdrab", "Prioridad TX en doble escucha", G_SCAN, 0x0E42, "list", ("Off", "A", "B"), menu="TDR-AB"),
    S("screv", "Reanudar escaneo", G_SCAN, 0x0E32, "list", ("TO", "CO", "SE"), bit=0, width=2, menu="SC-REV"),
    S("workmode", "Modo de trabajo", G_SCAN, 0x0E4C, "list", ("Frequency", "Channel"), menu="VFO/MR"),
    S("mrcha", "Canal activo A", G_SCAN, 0x0E76, "int", bit=0, width=7, max=127),
    S("mrchb", "Canal activo B", G_SCAN, 0x0E77, "int", bit=0, width=7, max=127),
    S("fm_preset", "Emisora FM (MHz)", G_SCAN, 0x0F4E, "freq_fm"),
    S("dtmfst", "Tono local DTMF", G_DTMF, 0x0E30, "list", ("Off", "DT-ST", "ANI-ST", "DT+ANI"), menu="DTMFST"),
    S("pttid", "Cuando enviar PTT-ID", G_DTMF, 0x0E33, "list", ("Off", "BOT", "EOT", "Both"), menu="PTT-ID"),
    S("pttlt", "Retardo PTT-ID", G_DTMF, 0x0E34, "int", max=50, menu="PTT-LT"),
    S("almod", "Modo alarma", G_ADV, 0x0E40, "list", ("Site", "Tone", "Code"), menu="AL-MOD"),
    S("rpste", "STE repetidor", G_ADV, 0x0E44, "list", ("Off",) + tuple(str(x) for x in range(1, 11)), menu="RP-STE"),
    S("rptrl", "Retardo STE repetidor", G_ADV, 0x0E45, "list",
      ("Off",) + tuple("%d ms" % x for x in range(100, 1100, 100)), menu="RPT-RL"),
    S("fmradio", "Radio FM habilitada", G_ADV, 0x0E4A, "bool", bit=4, width=1, advanced=True),
    S("alarm", "Sonido de alarma", G_ADV, 0x0E4A, "bool", bit=3, width=1, advanced=True),
    S("reset", "Menu RESET disponible", G_ADV, 0x0E4A, "bool", bit=1, width=1, advanced=True,
      help="Oculto: si se desactiva, el usuario no puede resetear la radio desde el menu"),
    S("menu", "Menus disponibles", G_ADV, 0x0E4A, "bool", bit=0, width=1, advanced=True,
      help="Oculto: si se desactiva, el menu de la radio queda bloqueado"),
    S("vfomrlock", "Bloquear cambio VFO/MR", G_ADV, 0x0E4B, "bool", bit=0, width=1, advanced=True,
      help="Oculto: impide pasar a modo frecuencia (VFO) desde el teclado"),
    S("singleptt", "PTT unico", G_ADV, 0x0E4B, "bool", bit=1, width=1, advanced=True),
)


class WP970IFamily(RadioDriver):
    """Base para todos los modelos con el mapa WP970I. No se registra por si misma."""
    VENDOR = "Baofeng"
    PROTOCOL = BaofengCloneProtocol
    PROTOCOL_PARAMS = {"magics": (MAGIC_WP970I,)}
    MEM_SIZE = 0x2000
    WRITE_BLOCK = 0x10
    NAME_LEN = 6
    POWER = ("High", "Mid", "Low")            # valor de bits 'lowpower' = indice
    BANDS = (Band(136_000_000, 174_000_000), Band(400_000_000, 520_000_000))
    WRITABLE = (
        (0x0000, 0x0800, "Canales"),
        (0x0B00, 0x0BF0, "Codigos PTT-ID"),
        (0x0CA0, 0x0CC0, "ANI"),
        (0x0E20, 0x0E50, "Ajustes de menu"),
        (0x0E70, 0x0E80, "Canal activo A/B"),
        (0x0F40, 0x0F50, "Emisora FM"),
        (0x1000, 0x1800, "Nombres de canal"),
        (0x1EE0, 0x1EF0, "Mensaje de encendido"),
    )
    REGIONS = (
        (0x0000, 0x0800, "Canales (128 x 16 B)", "user"),
        (0x0B00, 0x0BF0, "Codigos PTT-ID", "user"),
        (0x0CAA, 0x0CB3, "ANI", "user"),
        (0x0E20, 0x0E4E, "Ajustes de menu", "settings"),
        (0x0E50, 0x0E58, "Desconocido (distinto en cada unidad)", "unknown"),
        (0x0E76, 0x0E78, "Canal activo A/B", "settings"),
        (0x0F00, 0x0F40, "VFO A/B", "settings"),
        (0x0F4E, 0x0F50, "Emisora FM", "settings"),
        (0x1000, 0x1800, "Nombres de canal", "user"),
        (0x1E00, 0x1E80, "Valores de fabrica de VFO", "service"),
        (0x1E80, 0x1EC0, "Calibracion potencia TX (VHF)", "service"),
        (0x1ED0, 0x1EDE, "Mensaje tecla 6 + encendido", "service"),
        (0x1EE0, 0x1EEE, "Mensaje de encendido", "settings"),
        (0x1EF0, 0x1EFE, "Firmware (identifica el modelo)", "service"),
        (0x1F00, 0x1F60, "Calibracion potencia TX (UHF/VHF2)", "service"),
        (0x1F60, 0x1FA0, "Umbrales de squelch / VOX", "service"),
        (0x1FA0, 0x1FC0, "Calibracion sin documentar", "service"),
        (0x1FC0, 0x1FCF, "Limites de banda TX", "service"),
    )
    SETTINGS = WP970I_SETTINGS

    @classmethod
    def capabilities(cls):
        return Capabilities(
            channels=(0, 127), name_length=cls.NAME_LEN,
            name_chars="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 !@#$%^&*()+-=[]:\";'<>?,./",
            power_levels=cls.POWER, bandwidths=("Narrow", "Wide"), bands=cls.BANDS,
            dcs=tuple(sorted(DCS_CODES + (645,))))

    # ---- codificacion ---------------------------------------------------
    @staticmethod
    def _lbcd_get(b: bytes) -> int:
        return int("".join("%02x" % x for x in reversed(b)))

    @staticmethod
    def _lbcd_put(v: int) -> bytes:
        s = "%08d" % v
        return bytes(int(s[i:i + 2], 16) for i in range(6, -1, -2))

    @classmethod
    def _tone_get(cls, v: int):
        if v in (0, 0xFFFF):
            return None
        if v >= 0x0258:
            return format_tone(("ctcss", v / 10.0))
        dcs = cls.capabilities().dcs
        if v > 0x69:
            return format_tone(("dcs", dcs[v - 0x6A], "I"))
        return format_tone(("dcs", dcs[v - 1], "N"))

    @classmethod
    def _tone_put(cls, t) -> int:
        p = parse_tone(t)
        if p is None:
            return 0
        if p[0] == "ctcss":
            return round(p[1] * 10)
        idx = cls.capabilities().dcs.index(p[1])
        return idx + (0x6A if p[2] == "I" else 1)

    @classmethod
    def _power_get(cls, bits: int) -> str:
        return cls.POWER[bits] if bits < len(cls.POWER) else cls.POWER[0]

    @classmethod
    def _power_put(cls, p: str) -> int:
        return cls.POWER.index(p)

    @classmethod
    def decode_channel(cls, mem, n):
        r = mem[n * 16:n * 16 + 16]
        if r[0] == 0xFF:
            return Channel(number=n, empty=True)
        txinh = bytes(r[4:8]) in (b"\xff" * 4, b"\x00" * 4)
        nm = bytes(mem[0x1000 + n * 16:0x1000 + n * 16 + 7])
        name = nm.replace(b"\xff", b" ").decode("ascii", "replace").rstrip(" \x00")
        return Channel(
            number=n, empty=False, name=name,
            rx_freq=cls._lbcd_get(r[0:4]) * 10,
            tx_freq=None if txinh else cls._lbcd_get(r[4:8]) * 10,
            rx_tone=cls._tone_get(int.from_bytes(r[8:10], "little")),
            tx_tone=cls._tone_get(int.from_bytes(r[10:12], "little")),
            power=cls._power_get(r[14] & 0x03),
            bandwidth="Wide" if r[15] & 0x40 else "Narrow",
            scan=bool(r[15] & 0x04), bcl=bool(r[15] & 0x08),
            pttid=("Off", "BOT", "EOT", "Both")[r[15] & 0x03],
            scode=r[12] & 0x0F)

    @classmethod
    def encode_channel(cls, mem, ch):
        errs = cls.validate_channel(ch)
        if errs:
            raise ValueError("Canal %d: %s" % (ch.number, "; ".join(errs)))
        o, no = ch.number * 16, 0x1000 + ch.number * 16
        old = cls.decode_channel(mem, ch.number)
        if ch.empty:
            if not old.empty:                           # borrar solo si tenia contenido
                mem[o:o + 16] = b"\xff" * 16
                mem[no:no + 16] = b"\xff" * 16
            return
        if old.empty:                                   # canal nuevo: plantilla a ceros como CHIRP
            mem[o:o + 16] = bytes(16)
        r = mem[o:o + 16]
        if old.empty or ch.rx_freq != old.rx_freq:
            r[0:4] = cls._lbcd_put(ch.rx_freq // 10)
        if old.empty or ch.tx_freq != old.tx_freq:
            r[4:8] = b"\xff" * 4 if ch.tx_freq is None else cls._lbcd_put(ch.tx_freq // 10)
        if old.empty or ch.rx_tone != old.rx_tone:
            r[8:10] = cls._tone_put(ch.rx_tone).to_bytes(2, "little")
        if old.empty or ch.tx_tone != old.tx_tone:
            r[10:12] = cls._tone_put(ch.tx_tone).to_bytes(2, "little")
        r[12] = (r[12] & 0xF0) | (ch.scode & 0x0F)
        r[14] = (r[14] & 0xFC) | cls._power_put(ch.power)
        b15 = r[15] & ~(0x40 | 0x08 | 0x04 | 0x03) & 0xFF
        b15 |= (0x40 if ch.bandwidth == "Wide" else 0) | (0x08 if ch.bcl else 0) | (0x04 if ch.scan else 0)
        b15 |= ("Off", "BOT", "EOT", "Both").index(ch.pttid)
        r[15] = b15
        mem[o:o + 16] = r
        if old.empty or ch.name.upper() != old.name:
            if old.empty:
                mem[no:no + 16] = b"\xff" * 16
            mem[no:no + 7] = ch.name.upper().encode("ascii")[:7].ljust(7, b"\xff")

    @classmethod
    def info_from_image(cls, image: MemoryImage):
        m = image.data

        def txt(a, n=14):
            return bytes(m[a:a + n]).replace(b"\xff", b"").decode("ascii", "replace").strip("\x00 ")

        def bbcd(b):
            return int("%02x%02x" % (b[0], b[1]))
        limits = {}
        for i, k in enumerate(("VHF", "UHF", "VHF2")):
            b = m[0x1FC0 + 5 * i:0x1FC5 + 5 * i]
            try:
                limits[k] = {"habilitada": bool(b[0]), "MHz": [bbcd(b[1:3]), bbcd(b[3:5])]}
            except ValueError:
                pass
        return {"firmware": txt(0x1EF0), "mensaje_tecla6": txt(0x1ED0), "limites_tx": limits}

    @classmethod
    def chirp_export(cls, image):
        ident = bytes.fromhex(image.meta.get("ident", "AA 00 00 00 00 00 00 DD").replace(" ", ""))
        return bytes(image.data) + ident, {"rclass": cls.CHIRP_CLASS, "vendor": "Baofeng", "model": cls.CHIRP_MODEL,
                       "variant": "", "chirp_version": "radiokit"}

    CHIRP_CLASS, CHIRP_MODEL = "WP970I", "WP970I"


class WP970ITriBand(WP970IFamily):
    NAME_LEN = 7
    POWER = ("High", "Low")                   # tribanda: bits 0 = High, 2 = Low
    BANDS = (Band(136_000_000, 174_000_000), Band(200_000_000, 260_000_000),
             Band(400_000_000, 520_000_000))

    @classmethod
    def _power_get(cls, bits):
        return "Low" if bits == 2 else "High"

    @classmethod
    def _power_put(cls, p):
        return 2 if p == "Low" else 0


@register
class BaofengUVSPlusTri(WP970ITriBand):
    ID = "baofeng.uv-s-plus-tri"
    MODEL = "UV-S Plus (tri)"
    ALIASES = ("UV-S9X3", "UV-S9 Plus tri")
    PROTOCOL_PARAMS = {"magics": (MAGIC_UVS9X3,)}
    PRIORITY = 10
    CHIRP_CLASS, CHIRP_MODEL = "UVS9X3", "UV-S9X3"
    NOTES = ("Verificado con firmware HN5RV011. Canales numerados 0-127 como en pantalla. "
             "Sin control remoto en tiempo real: solo clonado de memoria.")

    @classmethod
    def matches(cls, info):
        # El UV-5R responde al mismo handshake: se distingue por el firmware (0x1EF0)
        return info.get("firmware", "").startswith("HN5RV")


@register
class BaofengBFA58S(WP970ITriBand):
    ID = "baofeng.bf-a58s"
    MODEL = "BF-A58S"
    ALIASES = ("UV-82III",)
    PROTOCOL_PARAMS = {"magics": (MAGIC_WP970I,)}
    EXPERIMENTAL = True
    CHIRP_CLASS, CHIRP_MODEL = "BFA58S", "BF-A58S"
    NOTES = "Sin verificar con hardware real (mapa identico a CHIRP)."
