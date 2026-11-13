"""Radtel RT-4D (DMR + analogico). Fase 1: copia de seguridad completa de la flash SPI (4 MB).

La decodificacion del codeplug (canales, contactos, grupos, zonas) depende del firmware instalado:
Radtel original (cambia de formato entre versiones) o DualTachyon REFW. Se anadira cuando se
disponga de una copia real de la radio y se sepa que firmware lleva.
"""
from __future__ import annotations

from ..core.model import Band, Capabilities
from ..core.settings import Setting as S
from ..protocols.radtel_spi import RadtelSPIProtocol
from . import register
from .base import RadioDriver


TIMER = ("Off", "5 s", "10 s", "15 s", "30 s")     # inicio de las listas de tiempos (verificado)
G_R, G_S, G_A = "Radio", "Escaneo", "Pantalla"
# Ajustes del menu "Radio Setting" verificados uno a uno (lectura antes/despues), firmware 3.13.
RT4D_SETTINGS = (
    S("radio_name", "01 Nombre de radio", G_R, 0x204C, "text", width=16, pad=0xFF, menu="Radio Name"),
    S("welcome", "Mensaje de bienvenida (sin verificar)", G_A, 0x202C, "text", width=16, pad=0xFF),
    S("voice", "02 Voz", G_R, 0x205C, "bool", menu="Voice Prompt"),
    S("key_beep", "03 Pitido de teclas", G_R, 0x205D, "bool", menu="Key Beep"),
    S("lock_timer", "04 Bloqueo de teclado", G_R, 0x205F, "list", TIMER, menu="Lock Timer"),
    S("backlight", "05 Retroiluminacion", G_A, 0x2060, "bool", menu="Backlight"),
    S("light_timer", "06 Apagado de luz", G_A, 0x2062, "list", TIMER, menu="Light Timer"),
    S("brightness", "07 Brillo", G_A, 0x2061, "int", max=4, menu="Brightness"),
    S("menu_exit", "08 Salida de menu", G_R, 0x2065, "list", TIMER, menu="Menu Exit"),
    S("state_timer", "09 Mostrar estado", G_A, 0x2011, "list", TIMER, menu="State Timer"),
    S("dual_standby", "10 Doble escucha", G_R, 0x2066, "bool", menu="Dual Standby"),
    S("tx_priority", "11 Prioridad TX", G_R, 0x207E, "list", ("Edit", "Busy"), menu="TX priority"),
    S("freq_step", "12 Paso (kHz)", G_R, 0x2080, "list",
      ("0.25", "1.25", "2.5", "5", "6.25", "10", "12.5", "20", "25", "50", "100", "500", "1000", "5000"),
      menu="Freq Step"),
    S("talk_around", "13 Talk Around", G_R, 0x2067, "list", ("Off", "Talk Around", "Invert Freq"),
      menu="Talk Around"),
    S("save_mode", "14 Ahorro de bateria", G_R, 0x2063, "list", ("Off", "1:1", "1:2", "1:3"), menu="Save Mode"),
    S("scan_mode", "15 Modo de escaneo", G_S, 0x20A3, "list", ("CO", "TO", "SE"), menu="Scan Mode"),
    S("scan_dir", "16 Direccion de escaneo", G_S, 0x20A2, "list", ("Up", "Down"), menu="Scan Direction"),
    S("scan_dwell", "17 Espera de escaneo", G_S, 0x20A5, "int", max=30, menu="Scan Dwell"),
    S("scan_return", "18 Retorno de escaneo", G_S, 0x20A4, "list", ("Original CH", "Current CH"),
      menu="Scan Return"),
    S("alarm_type", "19 Tipo de alarma", G_R, 0x2068, "list", ("Local", "Remote", "Local+Remote"),
      menu="Alarm Type"),
    S("area_a_show", "22 Linea A muestra", G_A, 0x2085, "list", ("Show CH No", "Show Freq", "Show Alias"),
      menu="Area A Show"),
    S("lcd_contrast", "31 Contraste LCD", G_A, 0x20E9, "int", max=63, menu="LCD Contrast"),
    S("active_ch_a", "Canal activo linea A (0 = canal 1)", G_A, 0x208C, "int", max=255, advanced=True),
    # Digital Set (verificado)
    S("dmr_id", "01 ID DMR personal", "Digital", 0x2180, "bcd_le", width=4, max=16776415, menu="Personal ID",
      help="Tu ID DMR (radioid.net). Se guarda en BCD invertido."),
    S("call_tone", "02 Tono de llamada", "Digital", 0x218D, "bool", menu="Call Tone"),
    S("call_end_tone", "03 Tono fin de llamada", "Digital", 0x218E, "bool", menu="Call End Tone"),
    S("group_hold", "04 Group Hold", "Digital", 0x218F, "int", max=255, menu="Group Hold"),
    S("single_hold", "05 Single Hold", "Digital", 0x2191, "int", max=255, menu="Single Hold"),
    S("dmr_sql", "06 Squelch digital", "Digital", 0x2193, "int", max=16, menu="SQ level"),
    S("dmr_mic", "07 Ganancia micro (DMR)", "Digital", 0x2187, "int", max=31, menu="Mic Gain"),
    S("dmr_spk", "08 Ganancia altavoz (DMR)", "Digital", 0x2188, "int", max=31, menu="SPK Gain"),
    # Analog Set (verificado)
    S("ana_sql", "01 Squelch analogico", "Analogico", 0x2102, "int", max=10, menu="SQ level"),
    S("tx_start_tone", "02 Tono al empezar TX", "Analogico", 0x210B, "bool", menu="TX Start Tone"),
    S("tx_end_tone", "03 Tono al acabar TX", "Analogico", 0x210C, "list",
      ("Off", "Roger beep1", "Roger beep2", "Radio name"), menu="TX End Tone"),
    S("single_tone", "04 Tono unico (Hz)", "Analogico", 0x2100, "u16", max=5000, menu="Single Tone"),
    S("ana_mic", "05 Ganancia micro", "Analogico", 0x2105, "int", max=31, menu="Mic Gain"),
    S("ana_spk", "06 Ganancia altavoz", "Analogico", 0x2106, "int", max=63, menu="SPK Gain"),
    S("detect_range", "07 Rango de deteccion", "Analogico", 0x2110, "list", ("18-64 MHz", "64-136 MHz"),
      menu="Detect Range", help="Solo se conocen las dos primeras opciones"),
    S("rpt_delay", "08 Retardo repetidor (ms)", "Analogico", 0x2111, "int", scale=100, max=20,
      menu="Repeater Delay"),
    S("dtmf_delay", "09 Retardo DTMF (ms)", "DTMF", 0x2200, "int", scale=100, max=20, menu="DTMF Delay"),
    S("dtmf_interval", "10 Intervalo DTMF (ms) (deducido)", "DTMF", 0x2201, "int", scale=10, base=30, max=17,
      menu="DTMF Interval"),
    S("dtmf_duration", "11 Duracion DTMF (ms)", "DTMF", 0x2202, "int", scale=10, base=30, max=17,
      menu="DTMF Duration"),
    S("dtmf_mode", "12 Modo DTMF", "DTMF", 0x2203, "list", ("Off", "Tx start", "Tx end", "Both"),
      menu="DTMF Mode"),
    S("dtmf_select", "13 Codigo DTMF (0 = codigo 01)", "DTMF", 0x2204, "int", max=15, menu="DTMF Select"),
    S("dtmf_display", "14 Mostrar DTMF recibido", "DTMF", 0x2205, "bool", menu="DTMF Display"),
    S("dtmf_tx_gain", "15 Ganancia TX DTMF", "DTMF", 0x2206, "int", max=127, menu="DTMF TX Gain"),
    S("dtmf_rx_th", "16 Umbral RX DTMF", "DTMF", 0x2207, "int", max=127, menu="DTMF RX TH"),
    S("dtmf_control", "17 Control remoto DTMF", "DTMF", 0x2208, "bool", menu="DTMF Control",
      help="Permite que otras radios bloqueen/desactiven esta por DTMF"),
)


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
    SETTINGS = RT4D_SETTINGS
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
    # Escritura (probada 2026-11-13 con datos identicos en la zona 0x90 = ajustes 0x2000, 4 KB):
    #   la radio acepta los paquetes (06) y, al cerrar la sesion, sincroniza sus copias de reserva
    #   (ajustes 0x3000, canales 0x10000, zonas 0x3C000) con las principales. Basta escribir las principales.
    #   Tras cerrar, esperar unos segundos antes de volver a leer. Escribir siempre sectores completos de 4 KB.
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
