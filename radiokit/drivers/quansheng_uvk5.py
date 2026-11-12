"""Quansheng UV-K5 (y UV-K5(8), UV-K6, UV-5R Plus de Quansheng, Retevis RA79, MaxTalker TK-6).

EEPROM de 0x2000 bytes: 200 canales (1-200) de 16 B en 0x0000, atributos en 0x0D60, nombres de 16 B
en 0x0F50, ajustes en 0x0E70, calibracion en 0x1E00-0x2000 (protegida). Mapa de CHIRP uvk5.py (GPLv3).

Hay muchos firmwares: el original (2.01.x, 3.00, 4.00, 5.00, 7.0x, 1.02.x) y alternativos (egzumer,
F4HWN, 1o11, OSFW...). Con firmwares alternativos el mapa de canales suele coincidir pero los ajustes
cambian: radiokit los lee pero no escribe en ellos.

Menu oculto (encender con PTT + tecla lateral 1): F-LOCK, Tx 200/350/500, 350 En, Scra En.
"""
from __future__ import annotations

from ..core.model import CTCSS_TONES, DCS_CODES, Band, Capabilities, Channel, format_tone, parse_tone
from ..core.settings import Setting as S
from ..protocols.quansheng_k5 import QuanshengK5Protocol
from . import register
from .base import RadioDriver

STOCK_FIRMWARES = ("k5_2.01.", "app_2.01.", "2.01.", "3.00.", "4.00.", "k5_4.00.", "5.00.", "7.00.",
                   "7.01.", "1.02.")
BANDS_HZ = ((50_000_000, 76_000_000), (108_000_000, 136_999_900), (137_000_000, 173_999_900),
            (174_000_000, 349_999_900), (350_000_000, 399_999_900), (400_000_000, 469_999_900),
            (470_000_000, 600_000_000))
POWER = ("Low", "Mid", "High")          # bits txpower 0/1/2
G_B, G_D, G_S, G_H = "Basicos", "Pantalla y avisos", "Doble escucha y escaneo", "Menu oculto (servicio)"

K5_SETTINGS = (
    S("squelch", "Squelch", G_B, 0x0E71, "int", max=9, menu="SQL"),
    S("max_talk_time", "Tiempo max. de transmision (min)", G_B, 0x0E72, "int", max=10, menu="TOT"),
    S("key_lock", "Teclado bloqueado", G_B, 0x0E74, "bool"),
    S("vox_switch", "VOX activado", G_B, 0x0E75, "bool", menu="VOX"),
    S("vox_level", "Nivel VOX (0-9 = nivel 1-10)", G_B, 0x0E76, "int", max=9),
    S("mic_gain", "Ganancia de micro", G_B, 0x0E77, "int", max=4, menu="Mic"),
    S("battery_save", "Ahorro de bateria", G_B, 0x0E7B, "list", ("OFF", "1:1", "1:2", "1:3", "1:4"),
      menu="BatSav"),
    S("tail_note", "Eliminar cola de squelch", G_B, 0x0E7E, "bool", menu="STE"),
    S("beep", "Pitido de teclas", G_B, 0x0E90, "bool", menu="Beep"),
    S("auto_keypad_lock", "Bloqueo automatico", G_B, 0x0E96, "bool", menu="KeyLck"),
    S("roger", "Pitido fin de transmision", G_B, 0x0EA9, "list", ("OFF", "ROGER", "MDC"), menu="Roger"),
    S("channel_display", "Mostrar canal como", G_D, 0x0E79, "list", ("Frequency", "Channel No", "Channel Name"),
      menu="ChDisp"),
    S("backlight", "Retroiluminacion", G_D, 0x0E7D, "int", max=5, menu="ABR"),
    S("power_on_disp", "Al encender mostrar", G_D, 0x0E97, "list", ("Full Screen", "Welcome Info", "Voltage"),
      menu="POnMsg"),
    S("logo1", "Mensaje de encendido 1", G_D, 0x0EB0, "text", width=12),
    S("logo2", "Mensaje de encendido 2", G_D, 0x0EC0, "text", width=12),
    S("dual_watch", "Doble escucha", G_S, 0x0E7C, "list", ("Off", "Band A", "Band B"), menu="TDR"),
    S("crossband", "Banda cruzada", G_S, 0x0E7A, "list", ("Off", "Band A", "Band B"), menu="XB"),
    S("scan_resume", "Reanudar escaneo", G_S, 0x0E95, "list", ("TO", "CO", "SE"), menu="ScnRev"),
    S("flock", "F-LOCK (bandas de TX)", G_H, 0x0F40, "list", ("Off", "FCC", "CE", "GB", "430", "438"),
      advanced=True, help="Restriccion regional de transmision. Transmitir fuera de bandas autorizadas es ilegal."),
    S("tx350", "TX 350-400 MHz", G_H, 0x0F41, "bool", advanced=True),
    S("killed", "Radio desactivada por DTMF (kill)", G_H, 0x0F42, "bool", advanced=True,
      help="Si esta activo, la radio fue bloqueada remotamente por codigo DTMF"),
    S("tx200", "TX 174-350 MHz", G_H, 0x0F43, "bool", advanced=True),
    S("tx500", "TX 470-600 MHz", G_H, 0x0F44, "bool", advanced=True),
    S("en350", "Recepcion 350-400 MHz", G_H, 0x0F45, "bool", advanced=True),
    S("enscramble", "Cifrado por inversion (Scra En)", G_H, 0x0F46, "bool", advanced=True),
)


@register
class QuanshengUVK5(RadioDriver):
    ID = "quansheng.uv-k5"
    VENDOR = "Quansheng"
    MODEL = "UV-K5"
    ALIASES = ("UV-K5(8)", "UV-K6", "UV-5R Plus (Quansheng)", "Retevis RA79", "MaxTalker TK-6")
    PROTOCOL = QuanshengK5Protocol
    PROTOCOL_PARAMS = {}
    PRIORITY = 4
    MEM_SIZE = 0x2000
    WRITE_BLOCK = 0x80
    HARDWARE_VERIFIED = False
    WRITABLE = ((0x0000, 0x1D00, "Canales, atributos, nombres y ajustes"),)
    REGIONS = (
        (0x0000, 0x0C80, "Canales 1-200 (16 B)", "user"),
        (0x0C80, 0x0D60, "VFO por banda (14)", "settings"),
        (0x0D60, 0x0E28, "Atributos de canal (lista de escaneo, banda, libre)", "user"),
        (0x0E40, 0x0E68, "Emisoras FM (20)", "settings"),
        (0x0E70, 0x0ED0, "Ajustes de menu y mensajes", "settings"),
        (0x0ED0, 0x0F18, "DTMF", "settings"),
        (0x0F18, 0x0F20, "Listas de escaneo", "settings"),
        (0x0F40, 0x0F47, "Menu oculto: F-LOCK, TX 200/350/500, scrambler", "settings"),
        (0x0F50, 0x1BD0, "Nombres de canal (16 B)", "user"),
        (0x1C00, 0x1D00, "Contactos DTMF", "user"),
        (0x1D00, 0x1E00, "Sin uso conocido", "unknown"),
        (0x1E00, 0x2000, "Calibracion (squelch, potencia por banda, bateria)", "service"),
    )
    SETTINGS = K5_SETTINGS
    NOTES = ("Firmware original: lectura completa; escritura tras verificar con una radio real. "
             "Firmwares alternativos (egzumer, F4HWN...): solo lectura. Conectar el cable con la radio ya encendida.")

    @classmethod
    def matches(cls, info):
        return bool(info.get("firmware"))

    @classmethod
    def is_stock(cls, fw: str) -> bool:
        return fw.startswith(STOCK_FIRMWARES)

    @classmethod
    def write_block_reason(cls, image):
        fw = image.meta.get("firmware", "")
        if not cls.is_stock(fw):
            return ("Firmware '%s' no es el original de Quansheng: el mapa de ajustes puede ser distinto. "
                    "Solo lectura." % fw)
        if not cls.HARDWARE_VERIFIED:
            return "UV-K5 aun sin verificar con hardware: primero una lectura y comprobar canales con la pantalla."
        return None

    @classmethod
    def capabilities(cls):
        return Capabilities(channels=(1, 200), name_length=10,
                            name_chars="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 !@#$%^&*()+-=[]:\";'<>?,./_",
                            power_levels=POWER, bandwidths=("Narrow", "Wide"),
                            bands=tuple(Band(lo, hi) for lo, hi in BANDS_HZ),
                            ctcss=CTCSS_TONES, dcs=DCS_CODES)

    @classmethod
    def info_from_image(cls, image):
        fw = image.meta.get("firmware", "?")
        return {"firmware": fw, "firmware_original": cls.is_stock(fw)}

    # ---- canales ------------------------------------------------------------
    @staticmethod
    def _tone_get(flag, code):
        if flag == 1 and code < len(CTCSS_TONES):
            return format_tone(("ctcss", CTCSS_TONES[code]))
        if flag in (2, 3) and code < len(DCS_CODES):
            return format_tone(("dcs", DCS_CODES[code], "I" if flag == 3 else "N"))
        return None

    @staticmethod
    def _tone_put(t):
        p = parse_tone(t)
        if p is None:
            return 0, 0
        if p[0] == "ctcss":
            return 1, CTCSS_TONES.index(p[1])
        return (3 if p[2] == "I" else 2), DCS_CODES.index(p[1])

    @staticmethod
    def _band(hz):
        for i, (lo, hi) in enumerate(BANDS_HZ):
            if lo <= hz <= hi:
                return i
        return 7

    @classmethod
    def decode_channel(cls, mem, n):
        o, attr = (n - 1) * 16, mem[0x0D60 + n - 1]
        r = mem[o:o + 16]
        freq = int.from_bytes(r[0:4], "little")
        if freq in (0, 0xFFFFFFFF) or attr & 0x08:
            return Channel(number=n, empty=True)
        off = int.from_bytes(r[4:8], "little")
        shift = r[11] & 0x03
        rx = freq * 10
        if off == 0 or shift == 0:
            tx = rx
        elif shift == 2 and off == freq:          # "TX deshabilitado" segun CHIRP
            tx = None
        elif shift == 2:
            tx = rx - off * 10
        else:
            tx = rx + off * 10
        raw = bytes(mem[0x0F50 + (n - 1) * 16:0x0F50 + n * 16])
        name = raw.split(b"\x00")[0].split(b"\xff")[0].decode("latin-1").rstrip()
        extra = {"am": True} if r[11] & 0x10 else {}
        return Channel(
            number=n, empty=False, name=name, rx_freq=rx, tx_freq=tx,
            rx_tone=cls._tone_get(r[10] & 0x0F, r[8]), tx_tone=cls._tone_get(r[10] >> 4, r[9]),
            power=POWER[min((r[12] >> 2) & 3, 2)], bandwidth="Narrow" if r[12] & 0x02 else "Wide",
            bcl=bool(r[12] & 0x10), pttid=("Off", "BOT", "EOT", "Both")[(r[13] >> 1) & 3],
            scan=bool(attr & 0xC0), extra=extra)

    @classmethod
    def encode_channel(cls, mem, ch):
        errs = cls.validate_channel(ch)
        if errs:
            raise ValueError("Canal %d: %s" % (ch.number, "; ".join(errs)))
        o, ai, na = (ch.number - 1) * 16, 0x0D60 + ch.number - 1, 0x0F50 + (ch.number - 1) * 16
        old = cls.decode_channel(mem, ch.number)
        if ch.empty:
            if not old.empty:
                mem[o:o + 16] = b"\xff" * 16
                mem[na:na + 16] = b"\x00" * 16
                mem[ai] = (mem[ai] & 0x30) | 0x08 | 0x07   # libre, banda 7, sin listas de escaneo
            return
        if old.empty:
            mem[o:o + 16] = bytes(16)
            mem[na:na + 16] = b"\x00" * 16
        r = mem[o:o + 16]
        if old.empty or (ch.rx_freq, ch.tx_freq) != (old.rx_freq, old.tx_freq):
            f = ch.rx_freq // 10
            r[0:4] = f.to_bytes(4, "little")
            if ch.tx_freq is None:
                off, shift = f, 2
            elif ch.tx_freq == ch.rx_freq:
                off, shift = 0, 0
            else:
                off, shift = abs(ch.tx_freq - ch.rx_freq) // 10, (1 if ch.tx_freq > ch.rx_freq else 2)
            r[4:8] = off.to_bytes(4, "little")
            r[11] = (r[11] & 0xFC) | shift
        if old.empty or (ch.tx_tone, ch.rx_tone) != (old.tx_tone, old.rx_tone):
            tf, tc = cls._tone_put(ch.tx_tone)
            rf, rc = cls._tone_put(ch.rx_tone)
            r[8], r[9], r[10] = rc, tc, (tf << 4) | rf
        r[12] = (r[12] & ~(0x10 | 0x0C | 0x02) & 0xFF) | (0x10 if ch.bcl else 0) | \
            (POWER.index(ch.power) << 2) | (0x02 if ch.bandwidth == "Narrow" else 0)
        r[13] = (r[13] & ~0x06 & 0xFF) | (("Off", "BOT", "EOT", "Both").index(ch.pttid) << 1)
        mem[o:o + 16] = r
        a = mem[ai] & ~0x08 & 0xFF
        if old.empty or ch.rx_freq != old.rx_freq:
            a = (a & 0xF8) | cls._band(ch.rx_freq)
        if ch.scan and not a & 0xC0:
            a |= 0x80                                  # lista de escaneo 1
        elif not ch.scan:
            a &= ~0xC0 & 0xFF
        mem[ai] = a
        if old.empty or ch.name.upper() != old.name.upper():
            mem[na:na + 16] = ch.name.upper().encode("latin-1")[:10].ljust(16, b"\x00")
