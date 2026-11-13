"""Linea de comandos de radiokit.

  python -m radiokit ports                     puertos serie
  python -m radiokit drivers                   modelos soportados
  python -m radiokit read --port COM6          detectar y leer la radio (guarda copia)
  python -m radiokit show <copia.bin>          canales y ajustes de una copia
  python -m radiokit serve [--port 8446]       interfaz web en http://127.0.0.1:8446
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, drivers
from .core.image import MemoryImage
from .core.service import RadioService
from .core.transport import list_ports

ROOT = Path(__file__).resolve().parent.parent
BACKUPS = ROOT / "backups" / "radiokit"


def _progress(done, total, msg):
    pct = int(100 * done / max(total, 1))
    sys.stdout.write("\r[%-30s] %3d%% %s   " % ("#" * (pct * 30 // 100), pct, msg))
    sys.stdout.flush()
    if done >= total:
        sys.stdout.write("\n")


def cmd_show(path):
    img = MemoryImage.load(path)
    d = drivers.get_driver(img.driver_id)
    print("%s %s | %s" % (d.VENDOR, d.MODEL, d.info_from_image(img)))
    print("\n%-4s %-8s %-11s %-11s %-9s %-9s %-5s %-6s %s" % (
        "CH", "Nombre", "RX MHz", "TX MHz", "Tono TX", "Tono RX", "Pot", "Ancho", "Scan"))
    for c in d.channels(img):
        if c.empty:
            continue
        print("%-4d %-8s %-11.5f %-11s %-9s %-9s %-5s %-6s %s" % (
            c.number, c.name, c.rx_freq / 1e6, "%.5f" % (c.tx_freq / 1e6) if c.tx_freq else "solo RX",
            c.tx_tone or "-", c.rx_tone or "-", c.power, c.bandwidth, "si" if c.scan else "no"))
    print()
    for s in d.SETTINGS:
        print("  %-28s %s" % (s.label, s.read(img.data)))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="radiokit", description="radiokit %s" % __version__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ports")
    sub.add_parser("drivers")
    r = sub.add_parser("read")
    r.add_argument("--port", required=True)
    r.add_argument("--model", help="ID del modelo (ver 'drivers') para no autodetectar, p.ej. radtel.rt-4d")
    s = sub.add_parser("show")
    s.add_argument("path")
    w = sub.add_parser("serve")
    w.add_argument("--port", type=int, default=8446)
    w.add_argument("--no-browser", action="store_true")
    w.add_argument("--demo", metavar="COPIA.bin", help="anade un puerto DEMO con una radio simulada")
    a = ap.parse_args(argv)

    if a.cmd == "ports":
        for p in list_ports():
            print("%-6s %s" % (p["port"], p["device"]))
    elif a.cmd == "drivers":
        for d in drivers.all_drivers():
            print("%-26s %-8s %-18s %s" % (d.ID, d.VENDOR, d.MODEL, ", ".join(d.ALIASES)))
    elif a.cmd == "read":
        svc = RadioService(BACKUPS)
        d, img, path = svc.read(a.port, _progress, driver_id=a.model)
        print("%s %s firmware %s -> %s" % (d.VENDOR, d.MODEL, img.meta.get("firmware"), path))
    elif a.cmd == "show":
        cmd_show(a.path)
    elif a.cmd == "serve":
        from .web.server import serve
        serve(a.port, BACKUPS, open_browser=not a.no_browser, demo_dump=a.demo)


if __name__ == "__main__":
    main()
