"""Prueba de escritura del RT-4D: reescribe la zona de ajustes (0x2000-0x2FFF, 4 KB) con
EXACTAMENTE los mismos bytes que acaba de leer en la misma sesion. No cambia nada si la radio
se comporta como se espera. Uso: python tools/rt4d_write_test.py COM6
"""
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from radiokit.core.transport import SerialTransport  # noqa: E402
from radiokit.protocols.radtel_spi import RadtelSPIProtocol  # noqa: E402

BASE, SIZE = 0x2000, 0x1000

port = sys.argv[1]
t = SerialTransport(port, 115200)
t.open()
p = RadtelSPIProtocol(t)
try:
    info = p.identify()
    if not info:
        sys.exit("El RT-4D no responde (o esta en modo bootloader). No se escribe nada.")
    cur = p.read_memory(BASE + SIZE, ranges=((BASE, BASE + SIZE),))[BASE:BASE + SIZE]
    again = p.read_memory(BASE + SIZE, ranges=((BASE, BASE + SIZE),))[BASE:BASE + SIZE]
    if cur != again:
        sys.exit("Dos lecturas seguidas de los ajustes no coinciden: lectura inestable, no se escribe.")
    print("Ajustes leidos 2 veces, identicos. SHA256 %s" % hashlib.sha256(cur).hexdigest()[:16])
    for kb in range(SIZE // 1024):
        p.write_block(BASE + kb * 1024, cur[kb * 1024:(kb + 1) * 1024])
        print("  KB %d escrito, la radio confirma (06)" % kb)
    after = p.read_memory(BASE + SIZE, ranges=((BASE, BASE + SIZE),))[BASE:BASE + SIZE]
    print("Relectura en la misma sesion: %s" % ("IDENTICA" if after == cur else "DISTINTA"))
finally:
    p.close()
    t.close()
