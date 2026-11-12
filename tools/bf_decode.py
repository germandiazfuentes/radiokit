"""Decodificador (stdlib) de volcados de memoria Baofeng UV-S9X3 / UV-S Plus tri.

Mapa de memoria tomado del driver CHIRP baofeng_wp970i.py (licencia GPLv3).
Uso: python bf_decode.py backup.bin [--json salida.json]
"""
import json
import sys

DTCS = sorted((23, 25, 26, 31, 32, 36, 43, 47, 51, 53, 54, 65, 71, 72, 73, 74,
               114, 115, 116, 122, 125, 131, 132, 134, 143, 145, 152, 155, 156,
               162, 165, 172, 174, 205, 212, 223, 225, 226, 243, 244, 245, 246,
               251, 252, 255, 261, 263, 265, 266, 271, 274, 306, 311, 315, 325,
               331, 332, 343, 346, 351, 356, 364, 365, 371, 411, 412, 413, 423,
               431, 432, 445, 446, 452, 454, 455, 462, 464, 465, 466, 503, 506,
               516, 523, 526, 532, 546, 565, 606, 612, 624, 627, 631, 632, 654,
               662, 664, 703, 712, 723, 731, 732, 734, 743, 754, 645))

# Codigo de subtono CTCSS -> numero de canal "PMR" estandar (38 tonos)
CTCSS38 = [67.0, 71.9, 74.4, 77.0, 79.7, 82.5, 85.4, 88.5, 91.5, 94.8, 97.4,
           100.0, 103.5, 107.2, 110.9, 114.8, 118.8, 123.0, 127.3, 131.8,
           136.5, 141.3, 146.2, 151.4, 156.7, 162.2, 167.9, 173.8, 179.9,
           186.2, 192.8, 203.5, 210.7, 218.1, 225.7, 233.6, 241.8, 250.3]

PMR446 = {round(446.00625 + 0.0125 * i, 5): i + 1 for i in range(16)}

S = {  # listas de opciones (driver CHIRP)
    "step": ["2.5", "5.0", "6.25", "10.0", "12.5", "20.0", "25.0", "50.0"],
    "save": ["Off", "1:1", "1:2", "1:3", "1:4"],
    "timeout": ["%d s" % x for x in range(15, 615, 15)],
    "voice": ["Off", "English", "Chinese"],
    "dtmfst": ["Off", "DT-ST", "ANI-ST", "DT+ANI"],
    "screv": ["TO", "CO", "SE"],
    "pttid": ["Off", "BOT", "EOT", "Both"],
    "mdf": ["Channel", "Name", "Frequency"],
    "color": ["Off", "Blue", "Orange", "Purple"],
    "almod": ["Site", "Tone", "Code"],
    "ab": ["A", "B"],
    "offab": ["Off", "A", "B"],
    "ponmsg": ["Full", "Message"],
    "workmode": ["Frequency", "Channel"],
    "rpste": ["Off"] + [str(x) for x in range(1, 11)],
    "stedelay": ["Off"] + ["%d ms" % x for x in range(100, 1100, 100)],
}


def lbcd(b):
    return int("".join("%02x" % x for x in reversed(b)))


def pick(lst, i):
    return lst[i] if 0 <= i < len(lst) else "?(%d)" % i


def tone(v):
    if v in (0, 0xFFFF):
        return None
    if v >= 0x0258:
        return "%.1f Hz" % (v / 10.0)
    if v > 0x69:
        return "D%03dI" % DTCS[v - 0x6A]
    return "D%03dN" % DTCS[v - 1]


def chan(m, n):
    raw = m[n * 16:n * 16 + 16]
    if raw[0] == 0xFF:
        return None
    rx = lbcd(raw[0:4]) * 10
    txinh = raw[4:8] in (b"\xff" * 4, b"\x00" * 4)
    tx = None if txinh else lbcd(raw[4:8]) * 10
    rxt = int.from_bytes(raw[8:10], "little")
    txt = int.from_bytes(raw[10:12], "little")
    b12, b13, b14, b15 = raw[12:16]
    name = m[0x1000 + n * 16:0x1000 + n * 16 + 7].replace(b"\xff", b" ")
    name = name.decode("ascii", "replace").rstrip(" \x00")
    rxmhz = rx / 1e6
    d = {
        # la radio numera los canales 0-127
        "ch": n, "name": name, "rx_mhz": rxmhz,
        "tx_mhz": tx / 1e6 if tx else None,
        "duplex": "off(TX inh.)" if txinh else (
            "" if tx == rx else ("+" if tx > rx else "-")
            if abs(tx - rx) < 70e6 else "split"),
        "tx_tone": tone(txt), "rx_tone": tone(rxt),
        "power": "High" if (b14 & 3) == 0 else "Low" if (b14 & 3) == 2 else "?%d" % (b14 & 3),
        "bandwidth": "Wide" if (b15 >> 6) & 1 else "Narrow",
        "scan": bool((b15 >> 2) & 1),
        "bcl": bool((b15 >> 3) & 1),
        "pttid": pick(S["pttid"], b15 & 3),
        "scode": (b12 & 0x0F) + 1,
        "raw": raw.hex(" "),
    }
    k = round(rxmhz, 5)
    if k in PMR446:
        d["pmr446"] = PMR446[k]
        t = d["tx_tone"]
        if t and t.endswith("Hz"):
            hz = float(t.split()[0])
            if hz in CTCSS38:
                d["pmr_subtone_idx"] = CTCSS38.index(hz) + 1
    return d


def settings(m):
    s = m[0x0E20:0x0E50]
    g = lambda o: s[o - 0x20]  # noqa: E731
    return {
        "squelch": g(0x20), "step_khz": pick(S["step"], g(0x21)),
        "save": pick(S["save"], g(0x23)), "vox": "Off" if g(0x24) == 0 else g(0x24),
        "backlight(abr)": g(0x26), "dual_watch(tdr)": bool(g(0x27)),
        "beep": bool(g(0x28)), "tot": pick(S["timeout"], g(0x29)),
        "voice": pick(S["voice"], g(0x2E)), "dtmf_sidetone": pick(S["dtmfst"], g(0x30)),
        "scan_resume": pick(S["screv"], g(0x32) & 3), "pttid": pick(S["pttid"], g(0x33)),
        "pttid_delay(pttlt)": g(0x34), "display_a": pick(S["mdf"], g(0x35)),
        "display_b": pick(S["mdf"], g(0x36)), "bcl": bool(g(0x37)),
        "auto_lock": bool(g(0x38)), "wt_led": pick(S["color"], g(0x3D)),
        "rx_led": pick(S["color"], g(0x3E)), "tx_led": pick(S["color"], g(0x3F)),
        "alarm_mode": pick(S["almod"], g(0x40)), "band": g(0x41),
        "tx_under_tdr": pick(S["offab"], g(0x42)), "squelch_tail(ste)": bool(g(0x43)),
        "rpt_ste": pick(S["rpste"], g(0x44)), "rpt_ste_delay": pick(S["stedelay"], g(0x45)),
        "power_on_msg": pick(S["ponmsg"], g(0x46)), "roger": bool(g(0x47)),
        "tdr_channel_prio": g(0x49),
        "flags_e4a": "{:08b}".format(g(0x4A)), "flags_e4b": "{:08b}".format(g(0x4B)),
        "workmode(vfo/mr)": pick(S["workmode"], g(0x4C)), "keylock": bool(g(0x4D)),
        "mr_channel_a": m[0x0E76] & 0x7F, "mr_channel_b": m[0x0E77] & 0x7F,
    }


def text(m, a, n=7):
    return m[a:a + n].replace(b"\xff", b"").decode("ascii", "replace").strip("\x00 ")


def limits(m):
    out = {}
    for i, k in enumerate(("vhf", "uhf", "vhf2")):
        b = m[0x1FC0 + 5 * i:0x1FC5 + 5 * i]
        bb = lambda x: int("%02x%02x" % (x[0], x[1]))  # noqa: E731
        out[k] = {"enable": b[0], "low_mhz": bb(b[1:3]), "high_mhz": bb(b[3:5])}
    return out


def main():
    path = sys.argv[1]
    m = open(path, "rb").read()[:0x2000]
    chans = [c for c in (chan(m, i) for i in range(128)) if c]
    info = {
        "firmware": text(m, 0x1EF0, 14), "poweron_msg": [text(m, 0x1EE0), text(m, 0x1EE7)],
        "sixpoweron_msg": [text(m, 0x1ED0), text(m, 0x1ED7)],
        "limits": limits(m), "settings": settings(m), "channels": chans,
    }
    if "--json" in sys.argv:
        out = sys.argv[sys.argv.index("--json") + 1]
        with open(out, "w", encoding="utf-8") as f:
            json.dump(info, f, indent=2, ensure_ascii=False)
    print("Firmware:", info["firmware"], "| Msg encendido:", info["poweron_msg"])
    print("Limites banda:", info["limits"])
    print("\nAjustes:")
    for k, v in info["settings"].items():
        print("  %-22s %s" % (k, v))
    print("\n%-3s %-7s %-10s %-10s %-11s %-10s %-10s %-5s %-6s %-4s %s" % (
        "CH", "Nombre", "RX MHz", "TX MHz", "Duplex", "Tono TX", "Tono RX",
        "Pot", "Ancho", "Scan", "PMR"))
    for c in chans:
        pmr = ("PMR%d" % c["pmr446"] + ("/sub%d" % c["pmr_subtone_idx"]
               if "pmr_subtone_idx" in c else "")) if "pmr446" in c else ""
        print("%-3d %-7s %-10.5f %-10s %-11s %-10s %-10s %-5s %-6s %-4s %s" % (
            c["ch"], c["name"], c["rx_mhz"],
            "%.5f" % c["tx_mhz"] if c["tx_mhz"] else "-", c["duplex"],
            c["tx_tone"] or "-", c["rx_tone"] or "-", c["power"],
            c["bandwidth"], "si" if c["scan"] else "no", pmr))
    print("\nTotal canales programados: %d / 128 (numeracion 0-127, como en la pantalla)" % len(chans))


if __name__ == "__main__":
    main()
