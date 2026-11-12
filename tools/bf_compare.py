"""Compara dos volcados Baofeng UV-S9X3 (.bin) y valida compatibilidad entre radios.

Uso: python bf_compare.py radioA.bin radioB.bin
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bf_decode import chan, settings, text  # noqa: E402

# Campos que impiden escucharse si difieren
CRIT = ("rx_mhz", "tx_mhz", "tx_tone", "rx_tone")
WARN = ("bandwidth", "duplex")
INFO = ("name", "power", "scan", "bcl", "pttid", "scode")


def load(p):
    m = open(p, "rb").read()[:0x2000]
    return m, {c["ch"]: c for c in (chan(m, i) for i in range(128)) if c}


def fmt(c):
    if not c:
        return "(vacio)"
    return "%s %.5f TX:%s tonoTX:%s tonoRX:%s %s %s" % (
        c["name"] or "-", c["rx_mhz"],
        "%.5f" % c["tx_mhz"] if c["tx_mhz"] else "-",
        c["tx_tone"] or "-", c["rx_tone"] or "-", c["bandwidth"], c["power"])


def main():
    pa, pb = sys.argv[1], sys.argv[2]
    ma, ca = load(pa)
    mb, cb = load(pb)
    print("A:", os.path.basename(pa), "| firmware", text(ma, 0x1EF0, 14))
    print("B:", os.path.basename(pb), "| firmware", text(mb, 0x1EF0, 14))
    if ma == mb:
        print("\n== Las memorias son IDENTICAS byte a byte. ==")
        return

    crit = warn = info = 0
    print("\n--- Canales ---")
    for n in sorted(set(ca) | set(cb)):
        a, b = ca.get(n), cb.get(n)
        if a is None or b is None:
            crit += 1
            print("[CRITICO] CH%-3d solo en %s" % (n, "A" if a else "B"))
            print("      A:", fmt(a))
            print("      B:", fmt(b))
            continue
        diffs = [(k, "CRITICO") for k in CRIT if a[k] != b[k]] + \
                [(k, "AVISO") for k in WARN if a[k] != b[k]] + \
                [(k, "info") for k in INFO if a[k] != b[k]]
        if not diffs:
            continue
        lvl = diffs[0][1]
        crit += lvl == "CRITICO"
        warn += lvl == "AVISO"
        info += lvl == "info"
        print("[%s] CH%-3d difiere en: %s" % (lvl, n, ", ".join(k for k, _ in diffs)))
        print("      A:", fmt(a))
        print("      B:", fmt(b))

    print("\n--- Ajustes generales ---")
    sa, sb = settings(ma), settings(mb)
    for k in sa:
        if sa[k] != sb[k]:
            print("  %-22s A=%s  B=%s" % (k, sa[k], sb[k]))

    other = [a for a in range(0, 0x2000, 16) if ma[a:a + 16] != mb[a:a + 16]]
    cal = [a for a in other if 0x1E80 <= a < 0x1FC0]
    if cal:
        print("\n(Calibracion de fabrica distinta en %d bloques 0x1E80-0x1FBF: normal entre unidades)" % len(cal))

    print("\nResumen: %d criticos, %d avisos, %d menores" % (crit, warn, info))


if __name__ == "__main__":
    main()
