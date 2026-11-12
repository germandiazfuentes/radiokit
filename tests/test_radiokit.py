"""Pruebas de radiokit con un emulador y volcados reales. Ejecutar:  python -m unittest -v tests.test_radiokit"""
import glob
import os
import tempfile
import unittest
from unittest import mock

from radiokit import drivers
from radiokit.core.image import MemoryImage
from radiokit.core.model import Channel
from radiokit.core.service import ProtectedRegionError, RadioChangedError, RadioService
from radiokit.drivers.baofeng_wp970i import MAGIC_UVS9X3, BaofengUVSPlusTri
from radiokit.testing.fake_baofeng import FakeBaofengRadio

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Volcado real de una UV-S Plus (tri) con el plan de canales PMR/montana/maritimo (sin canales privados)
DUMP = os.path.join(ROOT, "tests", "data", "uv-s-plus-reference.bin")
D = BaofengUVSPlusTri


def real_dumps():
    """Volcado de referencia + copias locales en backups/ (si existen; no se publican)."""
    local = [p for p in glob.glob(os.path.join(ROOT, "backups", "**", "*.bin"), recursive=True)
             if os.path.getsize(p) == 0x2000 and "radiokit" not in p and "demo" not in p]
    return [DUMP] + local


@unittest.skipUnless(os.path.exists(DUMP), "falta el volcado real de referencia")
class TestDriver(unittest.TestCase):
    def setUp(self):
        self.img = MemoryImage(bytearray(open(DUMP, "rb").read()), D.ID)

    def test_decode_known_channels(self):
        ch = {c.number: c for c in D.channels(self.img)}
        self.assertEqual((ch[20].name, ch[20].rx_freq, ch[20].tx_tone, ch[20].rx_tone),
                         ("SOSMONT", 146_175_000, "123.0", None))
        self.assertEqual(ch[77].name, "PMR 7-7")
        self.assertEqual(ch[77].rx_tone, "85.4")
        self.assertEqual((ch[1].name, ch[1].bandwidth), ("PMR 01", "Narrow"))
        self.assertTrue(ch[2].scan)
        self.assertEqual((ch[22].name, ch[22].tx_freq, ch[22].scan), ("MAR16", None, False))
        self.assertEqual(ch[112].tx_tone, "123.0")
        self.assertTrue(ch[44].empty)
        self.assertEqual(sum(not c.empty for c in ch.values()), 30)

    def test_roundtrip_all_real_dumps(self):
        """Decodificar y volver a codificar cada canal no cambia ni un byte."""
        for p in real_dumps():
            mem = bytearray(open(p, "rb").read())
            orig = bytes(mem)
            for c in D.channels(MemoryImage(mem, D.ID)):
                D.encode_channel(mem, c)
            self.assertEqual(bytes(mem), orig, p)

    def test_edit_channel(self):
        mem = self.img.data
        c = D.decode_channel(mem, 77)
        c.name, c.bandwidth, c.tx_tone = "PRUEBA", "Wide", "D023N"
        D.encode_channel(mem, c)
        c2 = D.decode_channel(mem, 77)
        self.assertEqual((c2.name, c2.bandwidth, c2.tx_tone, c2.rx_tone), ("PRUEBA", "Wide", "D023N", "85.4"))
        c2.tx_tone = "D754I"
        D.encode_channel(mem, c2)
        self.assertEqual(D.decode_channel(mem, 77).tx_tone, "D754I")

    def test_new_and_delete_channel(self):
        mem = self.img.data
        D.encode_channel(mem, Channel(number=60, empty=False, name="MAR16", rx_freq=156_800_000,
                                      tx_freq=None, bandwidth="Wide", scan=False))
        c = D.decode_channel(mem, 60)
        self.assertEqual((c.name, c.tx_freq, c.duplex, c.bandwidth), ("MAR16", None, "off", "Wide"))
        D.encode_channel(mem, Channel(number=60, empty=True))
        self.assertTrue(D.decode_channel(mem, 60).empty)
        self.assertEqual(bytes(mem[60 * 16:61 * 16]), b"\xff" * 16)

    def test_validation(self):
        bad = Channel(number=5, empty=False, name="DEMASIADOLARGO", rx_freq=300_000_000, tx_tone="99.9")
        errs = D.validate_channel(bad)
        self.assertTrue(any("Nombre" in e for e in errs))
        self.assertTrue(any("fuera de las bandas" in e for e in errs))
        self.assertTrue(any("Subtono" in e for e in errs))
        with self.assertRaises(ValueError):
            D.encode_channel(self.img.data, bad)

    def test_settings(self):
        mem = self.img.data
        self.assertEqual(D.setting("mdfa").read(mem), "Name")
        self.assertEqual(D.setting("squelch").read(mem), "5")
        self.assertEqual(D.setting("fm_preset").read(mem), 102.0)
        self.assertEqual(D.setting("mrchb").read(mem), 20)
        self.assertTrue(D.setting("menu").read(mem))
        D.setting("mdfa").write(mem, "Frequency")
        self.assertEqual(mem[0x0E35], 2)
        before = mem[0x0E4A]
        D.setting("fmradio").write(mem, False)
        self.assertEqual(mem[0x0E4A], before & ~0x10)
        with self.assertRaises(ValueError):
            D.setting("mdfa").write(mem, "Nada")


@unittest.skipUnless(os.path.exists(DUMP), "falta el volcado real de referencia")
class TestServiceWithEmulator(unittest.TestCase):
    def setUp(self):
        self.mem = open(DUMP, "rb").read()
        self.fake = FakeBaofengRadio(self.mem, MAGIC_UVS9X3)
        self.tmp = tempfile.TemporaryDirectory()
        self.svc = RadioService(self.tmp.name, transport_factory=lambda port: self.fake, log=lambda m: None)
        p = mock.patch("radiokit.core.service.time.sleep")
        p.start()
        self.addCleanup(p.stop)
        q = mock.patch("radiokit.protocols.baofeng_clone.time.sleep")
        q.start()
        self.addCleanup(q.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def test_detect_and_read(self):
        drv, img, path = self.svc.read("FAKE")
        self.assertIs(drv, D)
        self.assertEqual(bytes(img.data), self.mem)
        self.assertEqual(img.meta["firmware"], "HN5RV011")
        self.assertTrue(os.path.exists(path))
        self.assertTrue(os.path.exists(path.replace(".bin", ".img")))
        self.assertEqual(self.fake.writes, [])          # leer nunca escribe

    def test_write_only_changed_blocks_and_verify(self):
        _, base, _ = self.svc.read("FAKE")
        tgt = base.copy()
        c = D.decode_channel(tgt.data, 77)
        c.name = "PRUEBA"
        D.encode_channel(tgt.data, c)
        D.setting("mdfa").write(tgt.data, "Frequency")
        plan = self.svc.plan(base, tgt)
        self.assertEqual(plan.blocks, [0x0E30, 0x14D0])
        self.assertEqual(plan.channels, [77])
        self.assertEqual(plan.settings, ["mdfa"])
        res = self.svc.write("FAKE", base, tgt)
        self.assertTrue(res.verified)
        self.assertEqual(sorted(self.fake.writes), [0x0E30, 0x14D0])
        self.assertEqual(bytes(self.fake.mem), bytes(tgt.data))

    def test_dry_run_writes_nothing(self):
        _, base, _ = self.svc.read("FAKE")
        tgt = base.copy()
        D.setting("squelch").write(tgt.data, "3")
        res = self.svc.write("FAKE", base, tgt, dry_run=True)
        self.assertTrue(res.dry_run)
        self.assertEqual(self.fake.writes, [])

    def test_refuses_protected_regions(self):
        _, base, _ = self.svc.read("FAKE")
        tgt = base.copy()
        tgt.data[0x1E90] ^= 0xFF                         # calibracion de potencia
        with self.assertRaises(ProtectedRegionError):
            self.svc.write("FAKE", base, tgt)
        self.assertEqual(self.fake.writes, [])

    def test_aborts_if_radio_changed(self):
        _, base, _ = self.svc.read("FAKE")
        tgt = base.copy()
        D.setting("squelch").write(tgt.data, "3")
        self.fake.mem[0x0E20] = 9                       # alguien toca la radio entre lectura y escritura
        with self.assertRaises(RadioChangedError):
            self.svc.write("FAKE", base, tgt)
        self.assertEqual(self.fake.writes, [])

    def test_radio_state_change_elsewhere_is_tolerated(self):
        _, base, _ = self.svc.read("FAKE")
        tgt = base.copy()
        D.setting("squelch").write(tgt.data, "3")
        self.fake.mem[0x0E77] = 22                      # cambio de canal en otro bloque: se respeta
        res = self.svc.write("FAKE", base, tgt)
        self.assertTrue(res.verified)
        self.assertEqual(self.fake.mem[0x0E77], 22)


class TestRegistry(unittest.TestCase):
    def test_drivers_well_formed(self):
        ids = set()
        for d in drivers.all_drivers():
            self.assertNotIn(d.ID, ids)
            ids.add(d.ID)
            self.assertTrue(d.MEM_SIZE > 0)
            if not d.WRITABLE:
                self.assertIsNotNone(d.write_block_reason(MemoryImage(bytearray(16), d.ID)))
            for s, e, _ in d.WRITABLE:
                for rs, re_, name, kind in d.REGIONS:
                    if kind == "service":
                        self.assertTrue(e <= rs or s >= re_, "%s escribe en zona de servicio %s" % (d.ID, name))


class _NoSleep(unittest.TestCase):
    def setUp(self):
        for target in ("radiokit.core.service.time.sleep", "radiokit.protocols.baofeng_clone.time.sleep",
                       "radiokit.drivers.time.sleep"):
            p = mock.patch(target)
            p.start()
            self.addCleanup(p.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def service(self, fake):
        return RadioService(self.tmp.name, transport_factory=lambda port: fake, log=lambda m: None)


@unittest.skipUnless(os.path.exists(DUMP), "falta el volcado real de referencia")
class TestUV5R(_NoSleep):
    def make_uv5r(self, fw=b"BFB297"):
        mem = bytearray(open(DUMP, "rb").read())
        mem[0x1800:0x1EC0] = b"\xff" * (0x1EC0 - 0x1800)
        mem[0x1EF0:0x1EFE] = fw.ljust(14, b"\xff")
        return FakeBaofengRadio(bytes(mem), MAGIC_UVS9X3)

    def test_detected_as_uv5r_by_firmware(self):
        from radiokit.drivers.baofeng_uv5r import BaofengUV5R
        fake = self.make_uv5r()
        drv, img, path = self.service(fake).read("FAKE")
        self.assertIs(drv, BaofengUV5R)
        self.assertEqual(img.meta["firmware"], "BFB297")
        ch = {c.number: c for c in drv.channels(img)}
        self.assertEqual(ch[20].rx_freq, 146_175_000)
        img_bytes = open(path.replace(".bin", ".img"), "rb").read()
        self.assertTrue(img_bytes.startswith(bytes.fromhex("AA307604000520DD")))   # formato CHIRP UV-5R

    def test_uv5r_write_blocked_until_verified(self):
        fake = self.make_uv5r()
        svc = self.service(fake)
        _, base, _ = svc.read("FAKE")
        tgt = base.copy()
        tgt.data[0x0E20] = 3
        with self.assertRaises(ProtectedRegionError):
            svc.write("FAKE", base, tgt)
        self.assertEqual(fake.writes, [])

    def test_unknown_firmware_is_rejected(self):
        with self.assertRaises(LookupError):
            self.service(self.make_uv5r(b"ZZZ999")).read("FAKE")


class TestUV13Pro(_NoSleep):
    def logical_image(self):
        from radiokit.drivers.baofeng_uv13pro import BaofengUV13Pro as U
        mem = bytearray(b"\xff" * U.MEM_SIZE)
        chans = [Channel(number=1, empty=False, name="PMR 01", rx_freq=446_006_250, tx_freq=446_006_250),
                 Channel(number=252, empty=False, name="LIMITE1", rx_freq=145_500_000, tx_freq=145_500_000,
                         tx_tone="88.5", rx_tone="88.5", power="Low", bandwidth="Wide"),
                 Channel(number=253, empty=False, name="REPETIDOR", rx_freq=145_650_000, tx_freq=145_050_000,
                         tx_tone="D023N", rx_tone="D754I"),
                 Channel(number=999, empty=False, name="ULTIMO", rx_freq=433_500_000, tx_freq=None, scan=False)]
        for c in chans:
            U.encode_channel(mem, c)
        return U, mem, chans

    def test_encode_decode(self):
        U, mem, chans = self.logical_image()
        for c in chans:
            d = U.decode_channel(mem, c.number)
            self.assertEqual((d.name, d.rx_freq, d.tx_freq, d.tx_tone, d.rx_tone, d.power, d.bandwidth, d.scan),
                             (c.name, c.rx_freq, c.tx_freq, c.tx_tone, c.rx_tone, c.power, c.bandwidth, c.scan))
        self.assertEqual(U._ch_addr(253), 0x1000)
        self.assertEqual(U._name_addr(373), 0x5000)

    def test_read_through_page_map(self):
        from radiokit.testing.fake_uv17 import FakeUV17Radio
        U, mem, chans = self.logical_image()
        fake = FakeUV17Radio(bytes(mem))
        drv, img, _ = self.service(fake).read("FAKE")
        self.assertIs(drv, U)
        self.assertEqual(bytes(img.data), bytes(mem))
        self.assertEqual(drv.decode_channel(img.data, 253).name, "REPETIDOR")
        tgt = img.copy()
        tgt.data[0x7041] = 2
        with self.assertRaises(ProtectedRegionError):          # experimental: solo lectura
            self.service(fake).write("FAKE", img, tgt)
        self.assertEqual(fake.writes, [])


class TestRT4D(_NoSleep):
    def test_full_flash_backup(self):
        from radiokit.drivers.radtel_rt4d import RadtelRT4D
        from radiokit.testing.fake_rt4d import FakeRT4D
        flash = bytes((i * 7 + (i >> 10)) & 0xFF for i in range(RadtelRT4D.MEM_SIZE))
        fake = FakeRT4D(flash)
        drv, img, path = self.service(fake).read("FAKE")
        self.assertIs(drv, RadtelRT4D)
        self.assertEqual(bytes(img.data), flash)
        self.assertTrue(fake.closed_cmd)
        self.assertEqual(drv.channels(img), [])
        self.assertIsNotNone(drv.write_block_reason(img))


if __name__ == "__main__":
    unittest.main()
