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
    scale: int = 1              # "int"/"u16": valor mostrado = crudo * scale + base
    base: int = 0
    meta: dict = field(default_factory=dict)

    def _mask(self):
        return (1 << self.width) - 1

    def read(self, mem: bytearray):
        if self.kind == "text":
            raw = bytes(mem[self.offset:self.offset + self.width])
            return raw.replace(b"\xff", b"").replace(b"\x00", b"").decode("ascii", "replace").rstrip()
        if self.kind == "bcd_le":                       # numero en BCD, byte menos significativo primero
            raw = bytes(mem[self.offset:self.offset + self.width])
            try:
                return int("".join("%02x" % b for b in reversed(raw)))
            except ValueError:
                return None
        if self.kind == "freq_fm":                      # u16 big-endian en decimas de MHz
            v = int.from_bytes(mem[self.offset:self.offset + 2], "big")
            return v / 10.0 if 650 <= v <= 1080 else None
        if self.kind == "u16":
            return int.from_bytes(mem[self.offset:self.offset + 2], "little") * self.scale + self.base
        raw = mem[self.offset]
        if self.kind == "int" and self.bit is None and (self.scale != 1 or self.base):
            return raw * self.scale + self.base
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
        if self.kind == "bcd_le":
            v = int(value)
            if not self.min <= v <= self.max:
                raise ValueError("%s: %d fuera de rango" % (self.label, v))
            s = "%0*d" % (self.width * 2, v)
            mem[self.offset:self.offset + self.width] = bytes(int(s[i:i + 2], 16) for i in range(len(s) - 2, -1, -2))
            return
        if self.kind == "freq_fm":
            v = round(float(value) * 10)
            if not 650 <= v <= 1080:
                raise ValueError("Frecuencia FM fuera de 65.0-108.0 MHz")
            mem[self.offset:self.offset + 2] = v.to_bytes(2, "big")
            return
        if self.kind in ("int", "u16") and (self.scale != 1 or self.base):
            v = int(value)
            if (v - self.base) % self.scale:
                raise ValueError("%s: %d no es multiplo de %d" % (self.label, v, self.scale))
            value = (v - self.base) // self.scale
        if self.kind == "u16":
            v = int(value)
            if not self.min <= v <= self.max:
                raise ValueError("%s: %d fuera de rango %d-%d" % (self.label, v, self.min, self.max))
            mem[self.offset:self.offset + 2] = v.to_bytes(2, "little")
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
                "options": list(self.options), "min": self.min * self.scale + self.base,
                "max": self.max * self.scale + self.base, "step": self.scale, "menu": self.menu,
                "help": self.help, "advanced": self.advanced, "width": self.width,
                "value": self.read(mem)}
