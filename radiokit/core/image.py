"""Imagen de memoria de una radio + persistencia (.bin propio y .img compatible con CHIRP)."""
from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

CHIRP_MAGIC = b"\x00\xffchirp\xeeimg\x00\x01"


@dataclass
class MemoryImage:
    data: bytearray
    driver_id: str                       # p.ej. "baofeng.uvs9x3"
    meta: dict = field(default_factory=dict)   # firmware, ident, puerto, fecha...

    def copy(self) -> "MemoryImage":
        return MemoryImage(bytearray(self.data), self.driver_id, dict(self.meta))

    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest().upper()

    def diff_blocks(self, other: "MemoryImage", block: int) -> list[int]:
        """Direcciones de los bloques de `block` bytes que difieren."""
        a, b = self.data, other.data
        return [i for i in range(0, min(len(a), len(b)), block) if a[i:i + block] != b[i:i + block]]

    def diff_bytes(self, other: "MemoryImage") -> list[int]:
        return [i for i, (x, y) in enumerate(zip(self.data, other.data)) if x != y]

    # ---- persistencia -------------------------------------------------
    def save(self, path: str | Path, chirp_body: bytes | None = None, chirp_meta: dict | None = None):
        """Guarda <path>.bin (memoria pura), <path>.json (metadatos) y, si se da, <path>.img (CHIRP)."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.with_suffix(".bin").write_bytes(bytes(self.data))
        meta = dict(self.meta, driver_id=self.driver_id, sha256=self.sha256())
        p.with_suffix(".json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        if chirp_body is not None and chirp_meta is not None:
            raw = chirp_body + CHIRP_MAGIC + base64.b64encode(json.dumps(chirp_meta).encode())
            p.with_suffix(".img").write_bytes(raw)
        return p.with_suffix(".bin")

    @classmethod
    def load(cls, path: str | Path, driver_id: str | None = None, size: int | None = None) -> "MemoryImage":
        p = Path(path)
        raw = p.read_bytes()
        meta = {}
        if CHIRP_MAGIC in raw:                         # .img de CHIRP
            idx = raw.index(CHIRP_MAGIC)
            try:
                meta = json.loads(base64.b64decode(raw[idx + len(CHIRP_MAGIC):]).decode())
            except ValueError:
                meta = {}
            raw = raw[:idx]
        side = p.with_suffix(".json")
        if side.exists():
            meta.update(json.loads(side.read_text(encoding="utf-8")))
        did = driver_id or meta.get("driver_id")
        if not did:
            raise ValueError("No se sabe a que radio pertenece %s; indica el driver" % p.name)
        if size:
            raw = raw[:size]
        meta["source_file"] = str(p)
        return cls(bytearray(raw), did, meta)
