"""Plan de canales y ajustes para el Radtel RT-4D (firmware original 3.13).

- Canales 1-19: uso (PMR446 1-16, CASA, 7-7, SOS-Montana).
- Canales 20+: SOLO ESCUCHA (maritimos, repetidores analogicos y DMR de Cataluna/Andorra).
  El RT-4D no admite canales sin TX (los trata como invalidos y no recibe), asi que llevan TX = RX
  con potencia baja, TOT 5 s y (DMR) TX Politely = CC match como proteccion ante un PTT accidental.
- Ajustes: valores de fabrica (copia de reserva de la primera lectura), salvo nombre/bienvenida
  "RT-4D", DTMF Control Off y TX Priority Edit.

Uso:  python tools/rt4d_plan.py COM6 [--dry-run]
Fuentes: EA4T (listados VHF/UHF), EA3HUJ (repetidores DMR, 08/2026), docs/CANALES_ESPANA.md.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from radiokit.core.model import Channel  # noqa: E402
from radiokit.core.service import RadioService  # noqa: E402
from radiokit.drivers.radtel_rt4d import RadtelRT4D as R  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FACTORY_DUMP = ROOT / "backups" / "radiokit" / "radtel.rt-4d" / "20261113_093910_read.bin"

PMR = [(i + 1, 446_006_250 + 12_500 * i) for i in range(16)]
USO = [("CASA", 446_043_750, "100.0"), ("PMR 7-7", 446_081_250, "85.4")]
MARITIMOS = [("MAR16", 156_800_000), ("MAR10 BCN", 156_500_000), ("MAR13 TGN", 156_650_000),
             ("MAR74", 156_725_000), ("MAR67", 156_375_000), ("COST60 BCN", 160_625_000),
             ("COST23 BEGUR", 161_750_000), ("MAR09", 156_450_000)]
# Repetidores analogicos (salida = lo que se escucha). Fuente: EA4T.
REP_VHF = [("ED3YAB", 145_700_000), ("ED3YAF", 145_775_000), ("ED3YAG", 145_750_000), ("ED3YAH", 145_675_000),
           ("ED3YAJ", 145_600_000), ("ED3YAK", 145_650_000), ("ED3YAL", 145_725_000), ("ED3YAP", 145_700_000),
           ("ED3YAQ", 145_737_500), ("ED3YAU", 145_675_000), ("ED3YAW", 145_775_000), ("ED3YAY", 145_650_000),
           ("ED3YAZ", 145_675_000), ("ED3YBA", 145_625_000), ("ED3YBB", 145_750_000)]
REP_UHF = [("ED3YAB", 439_425_000), ("ED3YAC", 438_800_000), ("ED3YAD", 438_975_000), ("ED3YAE", 438_675_000),
           ("ED3YAH", 439_275_000), ("ED3YAI", 439_375_000), ("ED3YAM", 438_775_000), ("ED3YAN", 439_125_000),
           ("ED3YAO", 438_875_000), ("ED3YAP", 438_900_000), ("ED3YAS", 438_950_000), ("ED3YAT", 438_925_000),
           ("ED3YAV", 438_750_000), ("ED3YBC", 438_700_000), ("ED3YBH", 438_725_000)]
# Repetidores DMR (salida, codigo de color). Fuente: EA3HUJ 04/08/2026.
REP_DMR = [("ED3ZAK TIBIDABO", 438_412_500, 1), ("ED3YAN MONTJUIC", 438_462_500, 1),
           ("ED3YAD SABADELL", 438_975_000, 1), ("ED3ZAQ CASTELLAR", 438_525_000, 1),
           ("EA3RCH FARELL", 438_387_500, 1), ("ED3YAC CASTELLAR", 438_800_000, 1),
           ("ED3ZAG STLLORENC", 438_312_500, 1), ("ED3ZAN FIGUERES", 145_587_500, 1),
           ("ED3YAP ROCACORBA", 438_512_500, 1), ("ED3YAZ EL FAR", 438_287_500, 1),
           ("ED3YAM ELS MUNTS", 438_200_000, 1), ("ED3YAY LLEIDA", 438_412_500, 1),
           ("ED3ZAR ALMOSTER", 438_450_000, 1), ("ED3ZAS ESPARREG", 438_500_000, 1),
           ("ED3YBK ESPARREG", 145_575_000, 1), ("ED3ZAS2 ESPARREG", 439_175_000, 1),
           ("EA3RKE ESPARREG", 438_275_000, 1), ("ED3YAQ OSONA", 438_250_000, 1),
           ("ED3YAU VALL ARAN", 438_225_000, 1), ("ED3ZAT TORTOSA", 438_262_500, 1),
           ("ED3YBD MOLINS", 439_350_000, 1), ("EA3URC BAIX LLOB", 438_200_000, 1),
           ("ED3YBC PALAMOS", 439_025_000, 1), ("ED3ZAU TARRAGONA", 438_512_500, 1),
           ("EA3RCI BERGA", 438_212_500, 1), ("EA3RCP CERDANYA", 438_425_000, 1),
           ("EA3RCW PENEDES", 438_300_000, 1), ("EA3RCM ARENYS", 438_437_500, 1),
           ("EA3FL MATARO", 438_225_000, 1), ("EA3RCD TALARN", 439_400_000, 1),
           ("ED3ZAH ANOIA", 439_000_000, 7), ("ED3YAB ANOIA", 439_412_500, 1),
           ("ED3ZAG GARRAF", 438_237_500, 1), ("EA3HKB VILANOVA", 438_337_500, 7),
           ("EA3DKP ROSES", 439_000_000, 1), ("ED3YAM TOSA ALP", 438_775_000, 1),
           ("C30D ANDORRA", 438_400_000, 1)]


def build_channels():
    chans = []
    for n, f in PMR:
        chans.append(Channel(number=n, empty=False, name="PMR %02d" % n, rx_freq=f, tx_freq=f, power="Low",
                             bandwidth="Narrow", extra={"modo": "FM"}))
    n = 17
    for name, f, tone in USO:
        chans.append(Channel(number=n, empty=False, name=name, rx_freq=f, tx_freq=f, tx_tone=tone, rx_tone=tone,
                             power="Low", bandwidth="Narrow", extra={"modo": "FM"}))
        n += 1
    chans.append(Channel(number=n, empty=False, name="SOSMONT", rx_freq=146_175_000, tx_freq=146_175_000,
                         tx_tone="123.0", power="High", bandwidth="Narrow", extra={"modo": "FM"}))
    n += 1

    def rx_only(name, f, wide=True):
        return Channel(number=0, empty=False, name=("RX " + name)[:16], rx_freq=f, tx_freq=f, power="Low",
                       bandwidth="Wide" if wide else "Narrow", scan=False, extra={"modo": "FM", "tot": "5 s"})
    for name, f in MARITIMOS:
        c = rx_only(name, f)
        c.number = n
        chans.append(c)
        n += 1
    for name, f in REP_VHF + REP_UHF:
        c = rx_only(name, f, wide=False)
        c.number = n
        chans.append(c)
        n += 1
    for name, f, cc in REP_DMR:
        chans.append(Channel(number=n, empty=False, name=("RX " + name)[:16], rx_freq=f, tx_freq=f, power="Low",
                             bandwidth="Narrow", scan=False,
                             extra={"modo": "DMR", "tot": "5 s", "timeslot": 1, "color_code": cc,
                                    "dual_slot": False, "tx_politely": "CC match", "cifrado": "Off",
                                    "contacto": 1}))
        n += 1
    return chans


def apply(mem, factory):
    chans = build_channels()
    used = {c.number for c in chans}
    for n in range(1, 1025):                          # borrar todo lo demas (canales de prueba de fabrica)
        if n not in used and not R.decode_channel(mem, n).empty:
            R.encode_channel(mem, Channel(number=n, empty=True))
    for c in chans:
        R.encode_channel(mem, c)
    # Zonas para navegar en "Zone mode"
    by_prefix = lambda pred: [c.number for c in chans if pred(c)]  # noqa: E731
    zones = [("USO", by_prefix(lambda c: c.number <= 19)),
             ("MARITIMO", by_prefix(lambda c: c.name.startswith("RX MAR") or c.name.startswith("RX COST"))),
             ("REP ANALOG", by_prefix(lambda c: c.name.startswith("RX ") and c.extra.get("modo") == "FM"
                                      and not c.name.startswith(("RX MAR", "RX COST")))),
             ("REP DMR", by_prefix(lambda c: c.extra.get("modo") == "DMR"))]
    for z, (name, members) in enumerate(zones, 1):
        R.encode_zone(mem, z, name, members)
    for z in range(len(zones) + 1, 257):              # resto de zonas: vacias (la 5-256 ya lo estan)
        if R.decode_zone(mem, z)["channels"]:
            R.encode_zone(mem, z, "Zone-%03d" % z, [])
    keep = {"radio_name", "welcome", "dtmf_control", "tx_priority", "active_ch_a", "area_a_show", "area_b_show"}
    for s in R.SETTINGS:
        if s.key not in keep:
            s.write(mem, s.read(factory))
    R.setting("radio_name").write(mem, "RT-4D")
    R.setting("welcome").write(mem, "RT-4D")
    R.setting("dtmf_control").write(mem, False)
    R.setting("tx_priority").write(mem, "Edit")
    if R.decode_channel(mem, R.setting("active_ch_a").read(mem) + 1).empty:
        R.setting("active_ch_a").write(mem, 0)        # linea A en un canal vacio -> canal 1 (PMR 01)
    R.setting("area_a_show").write(mem, "Show Alias")  # mostrar el nombre del canal en ambas lineas
    R.setting("area_b_show").write(mem, "Show Alias")
    return chans


def main():
    port, dry = sys.argv[1], "--dry-run" in sys.argv
    fdump = FACTORY_DUMP.read_bytes()
    factory = bytearray(fdump)
    factory[0x2000:0x3000] = fdump[0x3000:0x4000]      # copia de reserva = configuracion original
    svc = RadioService(ROOT / "backups" / "radiokit")
    _, base, _ = svc.read(port, driver_id=R.ID, ranges=R.WRITE_CHECK_RANGES)
    tgt = base.copy()
    chans = apply(tgt.data, factory)
    plan = svc.plan(base, tgt)
    print("Canales del plan: %d | bloques: %s | ajustes cambiados: %d"
          % (len(chans), ", ".join("0x%04X" % b for b in plan.blocks), len(plan.settings)))
    res = svc.write(port, base, tgt, dry_run=dry)
    print("Ensayo correcto" if dry else "VERIFICADO: %s" % res.verified)


if __name__ == "__main__":
    main()
