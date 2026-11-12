"""Contrato que cumple cada driver y cada protocolo.

ANADIR UNA RADIO NUEVA
  * Mismo protocolo que una existente  -> subclase del driver/RadioDriver con su MEM_SIZE,
    WRITABLE, SETTINGS, capacidades y (de)codificacion de canal. Registrar con @register.
  * Protocolo nuevo -> subclase de Protocol en radiokit/protocols/ (identify, read_memory,
    write_block) y un driver que lo use. Ver docs/ANADIR_RADIO.md.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

from ..core.image import MemoryImage
from ..core.model import Capabilities, Channel
from ..core.settings import Setting
from ..core.transport import Transport

Progress = Callable[[int, int, str], None]   # (hecho, total, mensaje)


def _noprogress(done, total, msg):
    pass


class ProtocolError(Exception):
    pass


class Protocol(ABC):
    """Familia de protocolo de clonado. Una instancia = una sesion con la radio en modo programacion."""
    BAUDRATE = 9600
    WRITE_BLOCK = 0x10

    def __init__(self, transport: Transport, **params):
        self.t = transport
        self.params = params

    @classmethod
    def probe_variants(cls, params: dict) -> list[tuple[tuple, dict]]:
        """Handshakes distintos que hay que probar para estos parametros: [(clave, params_de_sesion)].
        Drivers con la misma clave comparten el handshake y se distinguen luego con matches()."""
        return [((cls.__name__, tuple(sorted((k, repr(v)) for k, v in params.items()))), params)]

    @abstractmethod
    def identify(self) -> dict | None:
        """Pone la radio en modo programacion. Devuelve info (ident, firmware...) o None si no responde.
        SOLO LECTURA: nunca debe modificar la radio."""

    @abstractmethod
    def read_memory(self, size: int, progress: Progress = _noprogress,
                    ranges: tuple[tuple[int, int], ...] | None = None) -> bytearray:
        """Devuelve `size` bytes; lo no incluido en `ranges` queda a 0xFF."""

    @abstractmethod
    def write_block(self, addr: int, data: bytes): ...

    def close(self):
        """Salir del modo programacion si el protocolo lo requiere."""


class RadioDriver(ABC):
    ID = ""                 # identificador estable "fabricante.modelo"
    VENDOR = ""
    MODEL = ""
    ALIASES: tuple[str, ...] = ()
    PROTOCOL: type[Protocol]
    PROTOCOL_PARAMS: dict = {}
    PRIORITY = 0            # mayor = se prefiere si varios drivers encajan con la misma respuesta
    MEM_SIZE = 0
    READ_RANGES: tuple[tuple[int, int], ...] | None = None   # None = toda la memoria
    WRITE_BLOCK = 0x10
    EXPERIMENTAL = False    # sin verificar con hardware: la escritura queda bloqueada
    # Zonas que la aplicacion puede escribir: (inicio, fin, descripcion). Todo lo demas esta protegido.
    WRITABLE: tuple[tuple[int, int, str], ...] = ()
    # Mapa documental de memoria: (inicio, fin, nombre, tipo) tipo: user|settings|service|unknown
    REGIONS: tuple[tuple[int, int, str, str], ...] = ()
    SETTINGS: tuple[Setting, ...] = ()
    NOTES = ""

    # ---- deteccion -------------------------------------------------------
    @classmethod
    def matches(cls, info: dict) -> bool:
        """¿La respuesta de identify() corresponde a este modelo?"""
        return True

    # ---- capacidades / canales ------------------------------------------
    @classmethod
    @abstractmethod
    def capabilities(cls) -> Capabilities: ...

    @classmethod
    @abstractmethod
    def decode_channel(cls, mem: bytearray, number: int) -> Channel: ...

    @classmethod
    @abstractmethod
    def encode_channel(cls, mem: bytearray, ch: Channel):
        """Escribe el canal en mem modificando SOLO los campos que cambian (preserva bits desconocidos)."""

    @classmethod
    def channels(cls, image: MemoryImage) -> list[Channel]:
        lo, hi = cls.capabilities().channels
        return [cls.decode_channel(image.data, n) for n in range(lo, hi + 1)]

    @classmethod
    def validate_channel(cls, ch: Channel) -> list[str]:
        from ..core.model import parse_tone
        caps, errs = cls.capabilities(), []
        lo, hi = caps.channels
        if not lo <= ch.number <= hi:
            errs.append("Canal %d fuera de rango %d-%d" % (ch.number, lo, hi))
        if ch.empty:
            return errs
        if len(ch.name) > caps.name_length:
            errs.append("Nombre de mas de %d caracteres" % caps.name_length)
        bad = [c for c in ch.name.upper() if c not in caps.name_chars]
        if bad:
            errs.append("Caracteres no validos en el nombre: %s" % "".join(bad))
        def band(f):
            return next((b for b in caps.bands if b.low <= f <= b.high), None)
        if not band(ch.rx_freq):
            errs.append("RX %.5f MHz fuera de las bandas de la radio" % (ch.rx_freq / 1e6))
        if ch.tx_freq is not None:
            b = band(ch.tx_freq)
            if not b or not b.tx:
                errs.append("TX %.5f MHz fuera de las bandas de transmision" % (ch.tx_freq / 1e6))
        for t in (ch.tx_tone, ch.rx_tone):
            try:
                pt = parse_tone(t)
            except ValueError as e:
                errs.append(str(e))
                continue
            if pt and pt[0] == "ctcss" and pt[1] not in caps.ctcss:
                errs.append("Subtono %.1f Hz no soportado" % pt[1])
            if pt and pt[0] == "dcs" and pt[1] not in caps.dcs:
                errs.append("Codigo DCS %03d no soportado" % pt[1])
        if ch.power not in caps.power_levels:
            errs.append("Potencia '%s' no valida (%s)" % (ch.power, ", ".join(caps.power_levels)))
        if ch.bandwidth not in caps.bandwidths:
            errs.append("Ancho '%s' no valido" % ch.bandwidth)
        if ch.pttid not in caps.pttid:
            errs.append("PTT-ID '%s' no valido" % ch.pttid)
        return errs

    # ---- ajustes ----------------------------------------------------------
    @classmethod
    def setting(cls, key: str) -> Setting:
        for s in cls.SETTINGS:
            if s.key == key:
                return s
        raise KeyError(key)

    @classmethod
    def info_from_image(cls, image: MemoryImage) -> dict:
        """Datos informativos extraidos de la imagen (firmware, limites...)."""
        return {}

    # ---- seguridad -----------------------------------------------------------
    @classmethod
    def is_writable(cls, addr: int, length: int) -> bool:
        return any(s <= addr and addr + length <= e for s, e, _ in cls.WRITABLE)

    @classmethod
    def write_block_reason(cls, image: MemoryImage) -> str | None:
        """Motivo por el que NO se debe escribir esta imagen en una radio (o None si se puede)."""
        if cls.EXPERIMENTAL:
            return ("Driver experimental de %s: solo lectura hasta verificarlo con una radio real."
                    % cls.MODEL)
        if not cls.WRITABLE:
            return "Este modelo aun no admite escritura (solo copia de seguridad)."
        return None

    # ---- exportacion ---------------------------------------------------------
    @classmethod
    def chirp_export(cls, image: MemoryImage) -> tuple[bytes, dict] | None:
        """(cuerpo_de_imagen, metadatos) para generar un .img abrible en CHIRP, o None."""
        return None

    @classmethod
    def describe(cls) -> dict:
        return {"id": cls.ID, "vendor": cls.VENDOR, "model": cls.MODEL, "aliases": list(cls.ALIASES),
                "protocol": cls.PROTOCOL.__name__, "mem_size": cls.MEM_SIZE, "notes": cls.NOTES,
                "experimental": cls.EXPERIMENTAL, "digital": cls.capabilities().digital,
                "writable": [("0x%04X" % s, "0x%04X" % e, d) for s, e, d in cls.WRITABLE],
                "regions": [("0x%04X" % s, "0x%04X" % e, n, k) for s, e, n, k in cls.REGIONS]}
