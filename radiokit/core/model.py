"""Modelo neutro (independiente del modelo de radio) de canales y capacidades."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

CTCSS_TONES = (67.0, 69.3, 71.9, 74.4, 77.0, 79.7, 82.5, 85.4, 88.5, 91.5, 94.8, 97.4, 100.0, 103.5,
               107.2, 110.9, 114.8, 118.8, 123.0, 127.3, 131.8, 136.5, 141.3, 146.2, 151.4, 156.7,
               159.8, 162.2, 165.5, 167.9, 171.3, 173.8, 177.3, 179.9, 183.5, 186.2, 189.9, 192.8,
               196.6, 199.5, 203.5, 206.5, 210.7, 218.1, 225.7, 229.1, 233.6, 241.8, 250.3, 254.1)

# Tabla PMR446 habitual de 38 subtonos (walkies comerciales: "subtono N")
PMR_SUBTONES = (67.0, 71.9, 74.4, 77.0, 79.7, 82.5, 85.4, 88.5, 91.5, 94.8, 97.4, 100.0, 103.5,
                107.2, 110.9, 114.8, 118.8, 123.0, 127.3, 131.8, 136.5, 141.3, 146.2, 151.4, 156.7,
                162.2, 167.9, 173.8, 179.9, 186.2, 192.8, 203.5, 210.7, 218.1, 225.7, 233.6, 241.8,
                250.3)

DCS_CODES = (23, 25, 26, 31, 32, 36, 43, 47, 51, 53, 54, 65, 71, 72, 73, 74, 114, 115, 116, 122,
             125, 131, 132, 134, 143, 145, 152, 155, 156, 162, 165, 172, 174, 205, 212, 223, 225,
             226, 243, 244, 245, 246, 251, 252, 255, 261, 263, 265, 266, 271, 274, 306, 311, 315,
             325, 331, 332, 343, 346, 351, 356, 364, 365, 371, 411, 412, 413, 423, 431, 432, 445,
             446, 452, 454, 455, 462, 464, 465, 466, 503, 506, 516, 523, 526, 532, 546, 565, 606,
             612, 624, 627, 631, 632, 654, 662, 664, 703, 712, 723, 731, 732, 734, 743, 754)

PMR446 = {round(446_006_250 + 12_500 * i): i + 1 for i in range(16)}


def parse_tone(t: str | None):
    """'88.5' -> ('ctcss', 88.5) ; 'D023N' -> ('dcs', 23, 'N') ; None/'' -> None."""
    if t in (None, "", "-", "off", "Off"):
        return None
    t = str(t).strip().upper().replace("HZ", "").strip()
    if t.startswith("D"):
        code, pol = int(t[1:4]), (t[4:5] or "N")
        if pol not in "NI":
            raise ValueError("Polaridad DCS invalida: %s" % t)
        return ("dcs", code, pol)
    return ("ctcss", round(float(t), 1))


def format_tone(kind_val) -> str | None:
    if kind_val is None:
        return None
    if kind_val[0] == "dcs":
        return "D%03d%s" % (kind_val[1], kind_val[2])
    return "%.1f" % kind_val[1]


@dataclass
class Channel:
    number: int
    empty: bool = True
    name: str = ""
    rx_freq: int = 0               # Hz
    tx_freq: int | None = None     # Hz; None = transmision inhibida (solo escucha)
    tx_tone: str | None = None     # "88.5" | "D023N" | None
    rx_tone: str | None = None
    power: str = "High"
    bandwidth: str = "Narrow"      # "Narrow" (12.5 kHz) | "Wide" (25 kHz)
    scan: bool = True
    bcl: bool = False              # bloqueo de canal ocupado
    pttid: str = "Off"
    scode: int = 0
    extra: dict = field(default_factory=dict)   # campos propios del modelo

    @property
    def duplex(self) -> str:
        if self.tx_freq is None:
            return "off"
        if self.tx_freq == self.rx_freq:
            return ""
        return "+" if self.tx_freq > self.rx_freq else "-"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["duplex"] = self.duplex
        d["pmr446"] = PMR446.get(self.rx_freq) if not self.empty else None
        tt = parse_tone(self.tx_tone)
        d["pmr_subtone"] = (PMR_SUBTONES.index(tt[1]) + 1
                            if tt and tt[0] == "ctcss" and tt[1] in PMR_SUBTONES else None)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Channel":
        keys = cls.__dataclass_fields__.keys()
        return cls(**{k: v for k, v in d.items() if k in keys})


@dataclass
class Band:
    low: int     # Hz
    high: int    # Hz
    tx: bool = True


@dataclass
class Capabilities:
    channels: tuple[int, int]               # (primero, ultimo) como se ven en la radio
    name_length: int
    name_chars: str
    power_levels: tuple[str, ...]
    bandwidths: tuple[str, ...]
    bands: tuple[Band, ...]
    ctcss: tuple[float, ...] = CTCSS_TONES
    dcs: tuple[int, ...] = DCS_CODES
    pttid: tuple[str, ...] = ("Off", "BOT", "EOT", "Both")
    digital: bool = False                   # radios DMR: contactos, grupos, zonas (futuro)

    def to_dict(self) -> dict:
        return asdict(self)
