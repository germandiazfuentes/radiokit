"""Ajustes declarativos: cada ajuste de menu se describe con datos (offset, tipo, opciones).

Para anadir los ajustes de un modelo nuevo basta con escribir su lista de Setting.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Setting:
    key: str                    # identificador estable, p.ej. "squelch"
    label: str                  # texto para la interfaz
    group: str                  # "Basicos", "Pantalla", ...
    offset: int                 # direccion del byte (o primer byte)
    kind: str                   # "list" | "int" | "bool" | "text" | "freq_fm"
    options: tuple = ()         # para "list": textos por valor 0..N-1
    bit: int | None = None      # para campos de bits: bit menos significativo
    width: int = 8              # numero de bits (o longitud de texto para "text")
    min: int = 0
    max: int = 255
    menu: str = ""              # nombre en el menu de la radio (p.ej. "SQL")
    help: str = ""
    advanced: bool = False      # ocultar por defecto (ajustes "de servicio")
    pad: int = 0x20             # relleno de los textos (0x20 espacio, 0xFF en algunas radios)
    meta: dict = field(default_factory=dict)

    def _mask(self):
        return (1 << self.width) - 1

    def read(self, mem: bytearray):
        if self.kind == "text":
            raw = bytes(mem[self.offset:self.offset + self.width])
            return raw.replace(b"\xff", b"").replace(b"\x00", b"").decode("ascii", "replace").rstrip()
        if self.kind == "freq_fm":                      # u16 big-endian en decimas de MHz
            v = int.from_bytes(mem[self.offset:self.offset + 2], "big")
            return v / 10.0 if 650 <= v <= 1080 else None
        raw = mem[self.offset]
        if self.bit is not None:
            raw = (raw >> self.bit) & self._mask()
        if self.kind == "bool":
            return bool(raw)
        if self.kind == "list":
            return self.options[raw] if raw < len(self.options) else "?(%d)" % raw
        return raw

    def write(self, mem: bytearray, value):
        if self.kind == "text":
            b = str(value).encode("ascii", "strict")[:self.width]
            mem[self.offset:self.offset + self.width] = b.ljust(self.width, bytes([self.pad]))
            return
        if self.kind == "freq_fm":
            v = round(float(value) * 10)
            if not 650 <= v <= 1080:
                raise ValueError("Frecuencia FM fuera de 65.0-108.0 MHz")
            mem[self.offset:self.offset + 2] = v.to_bytes(2, "big")
            return
        if self.kind == "bool":
            raw = 1 if value in (True, 1, "1", "true", "True", "on") else 0
        elif self.kind == "list":
            if value not in self.options:
                raise ValueError("%s: valor %r no valido (%s)" % (self.label, value, ", ".join(map(str, self.options))))
            raw = self.options.index(value)
        else:
            raw = int(value)
            if not self.min <= raw <= self.max:
                raise ValueError("%s: %d fuera de rango %d-%d" % (self.label, raw, self.min, self.max))
        if self.bit is None:
            mem[self.offset] = raw
        else:
            m = self._mask() << self.bit
            mem[self.offset] = (mem[self.offset] & ~m & 0xFF) | ((raw << self.bit) & m)

    def describe(self, mem: bytearray) -> dict:
        return {"key": self.key, "label": self.label, "group": self.group, "kind": self.kind,
                "options": list(self.options), "min": self.min, "max": self.max, "menu": self.menu,
                "help": self.help, "advanced": self.advanced, "width": self.width,
                "value": self.read(mem)}
