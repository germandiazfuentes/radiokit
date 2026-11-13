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
        flash = bytearray((i * 7 + (i >> 10)) & 0xFF for i in range(RadtelRT4D.MEM_SIZE))
        flash[0x4000:0x10000] = b"\xff" * 0xC000
        # Canal 1 DMR (140.125, TS1, CC0, alta) y canal 9 FM 145.555 con CTCSS 88.5 / DCS 023 invertido
        r1 = bytearray(48)
        r1[0:2] = b"\x01\x01"                                # modo DMR en 0x02 (=0), TS1, CC0
        r1[0x06:0x0A] = r1[0x0A:0x0E] = bytes.fromhex("54d0d500")
        r1[0x0E:0x10], r1[0x10] = bytes.fromhex("9e12"), 1
        r1[0x20:0x30] = b"\xff" * 16
        flash[0x4000:0x4000 + 48] = r1
        r9 = bytearray(bytes.fromhex("000101007513" "6c19de00" "6c19de00" "1330" "01000010") + bytes(12))
        r9[0x20:0x30] = b"PRUEBA".ljust(16, b"\xff")
        flash[0x4000 + 8 * 48:0x4000 + 9 * 48] = r9
        fake = FakeRT4D(bytes(flash))
        drv, img, path = self.service(fake).read("FAKE")
        self.assertIs(drv, RadtelRT4D)
        self.assertEqual(bytes(img.data), bytes(flash))
        self.assertTrue(fake.closed_cmd)
        chans = [c for c in drv.channels(img) if not c.empty]
        self.assertEqual([c.number for c in chans], [1, 9])
        c1, c9 = chans
        self.assertEqual((c1.rx_freq, c1.extra["modo"], c1.extra["timeslot"], c1.extra["color_code"], c1.power),
                         (140_125_000, "DMR", 1, 0, "High"))
        self.assertEqual((c9.name, c9.rx_freq, c9.extra["modo"], c9.rx_tone, c9.tx_tone),
                         ("PRUEBA", 145_555_000, "FM", "88.5", "D023I"))
        self.assertIsNone(drv.write_block_reason(img))

    def test_settings_write_flow(self):
        from radiokit.drivers.radtel_rt4d import RadtelRT4D as R
        from radiokit.testing.fake_rt4d import FakeRT4D
        flash = bytearray(b"\xff" * R.MEM_SIZE)
        flash[0x2000:0x3000] = bytes(0x1000)
        flash[0x204C:0x205C] = b"PRUEBA".ljust(16, b"\xff")
        flash[0x2208] = 1                                      # DTMF Control On
        fake = FakeRT4D(bytes(flash))
        svc = self.service(fake)
        _, base, _ = svc.read("FAKE", ranges=R.WRITE_CHECK_RANGES)
        tgt = base.copy()
        R.setting("dtmf_control").write(tgt.data, False)
        R.setting("radio_name").write(tgt.data, "RT-4D")
        plan = svc.plan(base, tgt)
        self.assertEqual(plan.blocks, [0x2000])                 # un sector de 4 KB
        self.assertEqual(sorted(plan.settings), ["dtmf_control", "radio_name"])
        res = svc.write("FAKE", base, tgt)
        self.assertTrue(res.verified)
        self.assertEqual(fake.writes, [0x2000, 0x2400, 0x2800, 0x2C00])   # 4 paquetes de 1 KB
        self.assertEqual(bytes(fake.flash[0x204C:0x2052]), b"RT-4D\xff")
        self.assertEqual(fake.flash[0x2208], 0)
        tgt2 = base.copy()
        tgt2.data[0x4000] ^= 1                                  # canales: aun no escribibles
        with self.assertRaises(ProtectedRegionError):
            svc.plan(base, tgt2)


class TestUVK5(_NoSleep):
    def eeprom(self):
        from radiokit.drivers.quansheng_uvk5 import QuanshengUVK5 as K
        mem = bytearray(b"\xff" * 0x2000)
        mem[0x0D60:0x0D60 + 200] = b"\x0f" * 200            # todos libres
        mem[0x0F50:0x0F50 + 200 * 16] = b"\x00" * (200 * 16)
        mem[0x1E00:0x2000] = bytes(range(256)) * 2           # "calibracion"
        mem[0x0F40:0x0F47] = bytes([0, 0, 0, 0, 0, 0, 0])
        chans = [Channel(number=1, empty=False, name="PMR 7-7", rx_freq=446_081_250, tx_freq=446_081_250,
                         tx_tone="85.4", rx_tone="85.4", power="Low", bandwidth="Narrow"),
                 Channel(number=2, empty=False, name="RPT", rx_freq=145_650_000, tx_freq=145_050_000,
                         tx_tone="D023N", rx_tone="D754I", power="High", bandwidth="Wide"),
                 Channel(number=200, empty=False, name="MAR16", rx_freq=156_800_000, tx_freq=None, scan=False)]
        for c in chans:
            K.encode_channel(mem, c)
        return K, mem, chans

    def test_crc_reference_vector(self):
        from radiokit.protocols.quansheng_k5 import crc16_xmodem
        self.assertEqual(crc16_xmodem(b"123456789"), 0x31C3)

    def test_encode_decode(self):
        K, mem, chans = self.eeprom()
        for c in chans:
            d = K.decode_channel(mem, c.number)
            self.assertEqual((d.name, d.rx_freq, d.tx_freq, d.tx_tone, d.rx_tone, d.power, d.bandwidth, d.scan),
                             (c.name, c.rx_freq, c.tx_freq, c.tx_tone, c.rx_tone, c.power, c.bandwidth, c.scan))
        self.assertTrue(K.decode_channel(mem, 3).empty)
        K.encode_channel(mem, Channel(number=2, empty=True))
        self.assertTrue(K.decode_channel(mem, 2).empty)

    def test_read_and_write_blocked_by_firmware(self):
        from radiokit.testing.fake_k5 import FakeUVK5
        K, mem, _ = self.eeprom()
        for fw, expect in (("k5_2.01.26", "sin verificar"), ("EGZUMER v0.22", "no es el original")):
            fake = FakeUVK5(bytes(mem), fw)
            drv, img, _ = self.service(fake).read("FAKE")
            self.assertIs(drv, K)
            self.assertEqual(bytes(img.data), bytes(mem))
            self.assertEqual(img.meta["firmware"], fw)
            self.assertIn(expect, K.write_block_reason(img))

    def test_write_flow_when_verified(self):
        from radiokit.testing.fake_k5 import FakeUVK5
        K, mem, _ = self.eeprom()
        fake = FakeUVK5(bytes(mem))
        svc = self.service(fake)
        _, base, _ = svc.read("FAKE")
        tgt = base.copy()
        c = K.decode_channel(tgt.data, 1)
        c.name = "MONTANA"
        K.encode_channel(tgt.data, c)
        with mock.patch.object(K, "HARDWARE_VERIFIED", True):
            plan = svc.plan(base, tgt)
            self.assertEqual(plan.blocks, [0x0F00])
            res = svc.write("FAKE", base, tgt)
        self.assertTrue(res.verified)
        self.assertEqual(fake.writes, [0x0F00])
        self.assertEqual(fake.resets, 1)                     # reinicio tras escribir
        self.assertEqual(bytes(fake.mem[0x1E00:]), bytes(mem[0x1E00:]))   # calibracion intacta
        tgt2 = base.copy()
        tgt2.data[0x1E10] ^= 0xFF
        with self.assertRaises(ProtectedRegionError):
            svc.plan(base, tgt2)


if __name__ == "__main__":
    unittest.main()
