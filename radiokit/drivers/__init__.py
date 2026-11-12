"""Registro de drivers y autodeteccion."""
from __future__ import annotations

import importlib
import pkgutil
import time

from .base import RadioDriver

_DRIVERS: dict[str, type[RadioDriver]] = {}


def register(cls: type[RadioDriver]) -> type[RadioDriver]:
    if not cls.ID:
        raise ValueError("Driver sin ID: %s" % cls.__name__)
    if cls.ID in _DRIVERS and _DRIVERS[cls.ID] is not cls:
        raise ValueError("ID de driver duplicado: %s" % cls.ID)
    _DRIVERS[cls.ID] = cls
    return cls


def _load_all():
    """Importa todos los modulos de radiokit.drivers para que se registren solos."""
    for m in pkgutil.iter_modules(__path__):
        if m.name != "base":
            importlib.import_module("%s.%s" % (__name__, m.name))


def all_drivers() -> list[type[RadioDriver]]:
    _load_all()
    return sorted(_DRIVERS.values(), key=lambda d: (d.VENDOR, d.MODEL))


def get_driver(driver_id: str) -> type[RadioDriver]:
    _load_all()
    try:
        return _DRIVERS[driver_id]
    except KeyError:
        raise KeyError("Driver desconocido: %s" % driver_id) from None


def detect(transport, log=print, only: type[RadioDriver] | None = None):
    """Prueba los handshakes (solo lectura) de cada familia hasta que uno responda.

    `only` limita la prueba a un modelo concreto (y sus hermanos de handshake).
    Devuelve (driver, protocolo_en_modo_programacion, info) o lanza LookupError.
    """
    variants: dict[tuple, dict] = {}      # clave -> {"proto", "params", "drivers"}
    for d in sorted(all_drivers(), key=lambda d: -d.PRIORITY):
        for key, params in d.PROTOCOL.probe_variants(d.PROTOCOL_PARAMS):
            v = variants.setdefault(key, {"proto": d.PROTOCOL, "params": params, "drivers": []})
            v["drivers"].append(d)
    if only:
        keys = {k for k, _ in only.PROTOCOL.probe_variants(only.PROTOCOL_PARAMS)}
        variants = {k: v for k, v in variants.items() if k in keys}
    first = True
    for v in variants.values():
        if not first:
            time.sleep(1.5)       # dar tiempo a la radio a salir de un handshake fallido
        first = False
        P = v["proto"]
        transport.set_baudrate(P.BAUDRATE)
        transport.flush_input()
        proto = P(transport, **v["params"])
        log("Probando %s (%s)..." % (P.__name__, ", ".join(d.MODEL for d in v["drivers"])))
        info = proto.identify()
        if not info:
            continue
        cands = [d for d in v["drivers"] if d.matches(info)]
        if cands:
            log("Detectado: %s %s (firmware %s)" % (cands[0].VENDOR, cands[0].MODEL, info.get("firmware", "?")))
            return cands[0], proto, info
        # La radio ya esta en modo programacion: no se puede seguir probando otros handshakes.
        raise LookupError("La radio responde al protocolo %s pero ningun driver reconoce su "
                          "firmware/identificacion: %r. Apagala y enciendela antes de reintentar."
                          % (P.__name__, info))
    raise LookupError("Ninguna radio conocida ha respondido. Comprueba que esta encendida, "
                      "con el cable bien encajado y el volumen a medio recorrido.")
