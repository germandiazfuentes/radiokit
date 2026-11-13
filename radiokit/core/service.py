"""Operaciones seguras con radios: detectar, leer (con copia automatica) y escribir.

Reglas de escritura (no se pueden saltar desde la interfaz):
 1. Solo se escriben bloques que difieren entre la imagen base y la objetivo.
 2. Todos esos bloques deben estar en zonas WRITABLE del driver (calibracion/firmware protegidos).
 3. Justo antes de escribir se lee la radio entera y se guarda como copia "prewrite".
 4. Si algun bloque a escribir ha cambiado en la radio desde que se leyo la base, se aborta.
 5. Tras escribir se relee la radio y se verifica cada bloque escrito.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from .. import drivers as registry
from ..drivers.base import RadioDriver, _noprogress
from .image import MemoryImage
from .transport import SerialTransport, Transport

Log = Callable[[str], None]


class ProtectedRegionError(Exception):
    pass


class RadioChangedError(Exception):
    pass


class VerifyError(Exception):
    pass


@dataclass
class WritePlan:
    driver_id: str
    blocks: list[int]
    regions: list[str]
    channels: list[int]
    settings: list[str]

    def to_dict(self):
        return {"driver_id": self.driver_id, "blocks": ["%04X" % b for b in self.blocks],
                "regions": self.regions, "channels": self.channels, "settings": self.settings}


@dataclass
class WriteResult:
    plan: WritePlan
    prewrite_backup: str
    postwrite_backup: str = ""
    verified: bool = False
    other_diffs: list[str] = field(default_factory=list)
    dry_run: bool = False


class RadioService:
    def __init__(self, backup_dir: str | Path, transport_factory=SerialTransport, log: Log = print):
        self.backup_dir = Path(backup_dir)
        self.transport_factory = transport_factory
        self.log = log

    # ------------------------------------------------------------------
    def _backup(self, image: MemoryImage, driver: type[RadioDriver], kind: str) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.backup_dir / driver.ID / ("%s_%s" % (ts, kind))
        exp = driver.chirp_export(image)
        if exp:
            p = image.save(path, chirp_body=exp[0], chirp_meta=exp[1])
        else:
            p = image.save(path)
        self.log("Copia guardada: %s (SHA256 %s)" % (p, image.sha256()[:16]))
        return str(p)

    def _session_read(self, t: Transport, progress, expect: type[RadioDriver] | None = None,
                      keep_open: bool = False, ranges=None):
        driver, proto, info = registry.detect(t, log=self.log, only=expect)
        if expect and driver.ID != expect.ID:
            raise RadioChangedError("Conectada una %s y se esperaba una %s" % (driver.MODEL, expect.MODEL))
        data = proto.read_memory(driver.MEM_SIZE, progress, ranges or driver.READ_RANGES)
        if not keep_open:
            proto.close()
        meta = dict(info, read_at=datetime.now().isoformat(timespec="seconds"),
                    vendor=driver.VENDOR, model=driver.MODEL)
        return driver, proto, MemoryImage(data, driver.ID, meta)

    # ------------------------------------------------------------------
    def read(self, port: str, progress=_noprogress, driver_id: str | None = None, ranges=None
             ) -> tuple[type[RadioDriver], MemoryImage, str]:
        """Detecta la radio (o usa el modelo indicado) y descarga su memoria (solo lectura).
        `ranges` limita la lectura (el resto queda a FF): util para comparar antes/despues.
        Guarda copia automatica."""
        only = registry.get_driver(driver_id) if driver_id else None
        with self.transport_factory(port) as t:
            driver, _, image = self._session_read(t, progress, expect=only, ranges=ranges)
        image.meta["port"] = port
        if ranges:
            image.meta["partial_ranges"] = ["0x%X-0x%X" % r for r in ranges]
        path = self._backup(image, driver, "partial" if ranges else "read")
        return driver, image, path

    def plan(self, base: MemoryImage, target: MemoryImage) -> WritePlan:
        driver = registry.get_driver(base.driver_id)
        if target.driver_id != base.driver_id:
            raise ValueError("Las imagenes son de modelos distintos")
        if len(target.data) != driver.MEM_SIZE or len(base.data) != driver.MEM_SIZE:
            raise ValueError("Tamano de imagen incorrecto")
        bs = driver.WRITE_BLOCK
        blocked = driver.write_block_reason(base)
        if blocked:
            raise ProtectedRegionError(blocked)
        blocks = base.diff_blocks(target, bs)
        bad = [b for b in blocks if not driver.is_writable(b, bs)]
        if bad:
            raise ProtectedRegionError("Cambios en zonas protegidas: " + ", ".join("0x%04X" % b for b in bad))
        regions = sorted({d for b in blocks for s, e, d in driver.WRITABLE if s <= b < e})
        lo, hi = driver.capabilities().channels
        chans = [n for n in range(lo, hi + 1)
                 if driver.decode_channel(base.data, n) != driver.decode_channel(target.data, n)]
        sets = [s.key for s in driver.SETTINGS if s.read(base.data) != s.read(target.data)]
        return WritePlan(driver.ID, blocks, regions, chans, sets)

    def write(self, port: str, base: MemoryImage, target: MemoryImage, progress=_noprogress,
              dry_run: bool = False) -> WriteResult:
        plan = self.plan(base, target)
        driver = registry.get_driver(plan.driver_id)
        bs = driver.WRITE_BLOCK
        if not plan.blocks:
            raise ValueError("No hay cambios que escribir")
        self.log("Plan: %d bloques (%s)" % (len(plan.blocks), ", ".join(plan.regions)))

        check = driver.WRITE_CHECK_RANGES
        with self.transport_factory(port) as t:
            _, proto, current = self._session_read(t, progress, expect=driver, keep_open=True, ranges=check)
            current.meta["port"] = port
            pre = self._backup(current, driver, "prewrite")
            changed = [b for b in plan.blocks if current.data[b:b + bs] != base.data[b:b + bs]]
            if changed:
                raise RadioChangedError(
                    "La radio ha cambiado desde que se leyo en bloques que se iban a escribir (%s). "
                    "Vuelve a leer la radio y repite los cambios. No se ha escrito nada."
                    % ", ".join("0x%04X" % b for b in changed))
            result = WriteResult(plan, pre, dry_run=dry_run)
            if dry_run:
                proto.close()
                self.log("Ensayo: la radio coincide con la base; no se escribe nada.")
                return result
            for i, b in enumerate(plan.blocks):
                proto.write_block(b, bytes(target.data[b:b + bs]))
                progress(i + 1, len(plan.blocks), "Escribiendo 0x%04X" % b)
            proto.finish_write()
            proto.close()
        self.log("Escritura completada. Verificando...")

        after = None
        for attempt in range(3):                       # algunas radios tardan en volver tras escribir
            time.sleep(driver.POST_WRITE_DELAY * (attempt + 1))
            try:
                with self.transport_factory(port) as t:
                    _, _, after = self._session_read(t, progress, expect=driver, ranges=check)
                break
            except LookupError:
                self.log("La radio aun no responde tras escribir; reintentando...")
        if after is None:
            raise VerifyError("Escrito, pero la radio no responde para verificar. Copia previa: %s" % pre)
        after.meta["port"] = port
        result.postwrite_backup = self._backup(after, driver, "postwrite")
        bad = [b for b in plan.blocks if after.data[b:b + bs] != target.data[b:b + bs]]
        if bad:
            raise VerifyError("La verificacion ha fallado en %s. Copia previa: %s"
                              % (", ".join("0x%04X" % b for b in bad), pre))
        result.verified = True
        diffs = after.diff_bytes(target)
        if check:
            diffs = [a for a in diffs if any(s <= a < e for s, e in check)]
        result.other_diffs = ["0x%04X" % a for a in diffs]
        self.log("VERIFICADO: %d bloques escritos correctamente." % len(plan.blocks))
        return result
