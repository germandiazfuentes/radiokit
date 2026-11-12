"""Aplica el plan de canales (docs/CANALES_ESPANA.md §5) a un volcado UV-S9X3.

Uso: python bf_plan.py base.bin objetivo.bin
Solo modifica canales (0x0000-0x07FF) y nombres (0x1000-0x17FF).
"""
import sys

NARROW_SCAN, NARROW_NOSCAN, WIDE_NOSCAN = 0x04, 0x00, 0x40
TXINH = None

# canal: (nombre, rx MHz, tx MHz | TXINH, tono TX Hz | None, byte15)
PLAN = {
    20: ("SOSMONT", 146.175, 146.175, 123.0, NARROW_SCAN),
    21: ("PMR 7-7", 446.08125, 446.08125, 85.4, NARROW_SCAN),   # TSQL (rx tono abajo)
    22: ("MAR16", 156.800, TXINH, None, WIDE_NOSCAN),
    23: ("MAR10", 156.500, TXINH, None, WIDE_NOSCAN),
    24: ("MAR13", 156.650, TXINH, None, WIDE_NOSCAN),
    25: ("MAR74", 156.725, TXINH, None, WIDE_NOSCAN),
    26: ("MAR67", 156.375, TXINH, None, WIDE_NOSCAN),
    27: ("COST60", 160.625, TXINH, None, WIDE_NOSCAN),
    28: ("COST23", 161.750, TXINH, None, WIDE_NOSCAN),
    29: ("MAR09", 156.450, TXINH, None, WIDE_NOSCAN),
}
RX_TONE = {21: 85.4}          # canales con tono tambien en RX (TSQL)
NARROW_ONLY = list(range(1, 17)) + [44, 77]   # PMR existentes -> Narrow
ADD_TX_TONE = {112: 123.0}    # EMERGEN 146.175 -> subtono 123 Hz


def lbcd(mhz):
    s = "%08d" % round(mhz * 1e5)
    return bytes(int(s[i:i + 2], 16) for i in range(6, -1, -2))


def tone(hz):
    return (0 if hz is None else round(hz * 10)).to_bytes(2, "little")


def main():
    base, out = sys.argv[1], sys.argv[2]
    m = bytearray(open(base, "rb").read()[:0x2000])
    assert len(m) == 0x2000

    for ch, (name, rx, tx, ttone, b15) in PLAN.items():
        rec = lbcd(rx) + (b"\xff" * 4 if tx is TXINH else lbcd(tx))
        rec += tone(RX_TONE.get(ch)) + tone(ttone) + bytes([0, 0, 0, b15])
        m[ch * 16:ch * 16 + 16] = rec
        n = name.encode("ascii").ljust(7, b"\xff")
        m[0x1000 + ch * 16:0x1000 + ch * 16 + 7] = n

    for ch in NARROW_ONLY:
        assert m[ch * 16] != 0xFF, "canal %d vacio" % ch
        m[ch * 16 + 15] &= ~0x40 & 0xFF

    for ch, hz in ADD_TX_TONE.items():
        assert m[ch * 16] != 0xFF
        m[ch * 16 + 10:ch * 16 + 12] = tone(hz)

    orig = open(base, "rb").read()[:0x2000]
    changed = [a for a in range(0, 0x2000, 16) if m[a:a + 16] != orig[a:a + 16]]
    bad = [a for a in changed if not (a < 0x0800 or 0x1000 <= a < 0x1800)]
    assert not bad, "cambio fuera de zona permitida: %s" % bad
    open(out, "wb").write(m)
    print("Bloques modificados: %d -> %s" % (len(changed), " ".join("%04X" % a for a in changed)))


if __name__ == "__main__":
    main()
