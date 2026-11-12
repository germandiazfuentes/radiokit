"""Transporte de bytes hacia la radio.

- SerialTransport: usa pyserial si esta instalado; si no, la API Win32 via ctypes (sin dependencias).
- list_ports(): puertos serie disponibles.
Todos los transportes implementan: open(), close(), write(b), read(n, timeout) -> bytes,
flush_input(), set_baudrate(baud).
"""
from __future__ import annotations

import sys
import time


class TransportError(Exception):
    pass


class Transport:
    """Interfaz comun. read() devuelve lo recibido (puede ser menos de n si vence el timeout)."""

    def open(self): ...
    def close(self): ...
    def write(self, data: bytes): ...
    def read(self, n: int, timeout: float = 1.5) -> bytes: ...
    def flush_input(self): ...
    def set_baudrate(self, baud: int): ...

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()


def list_ports() -> list[dict]:
    """Lista de puertos serie: [{'port': 'COM6', 'device': '\\Device\\...'}]."""
    ports = []
    if sys.platform == "win32":
        import winreg
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DEVICEMAP\SERIALCOMM")
        except OSError:
            return ports
        i = 0
        while True:
            try:
                device, port, _ = winreg.EnumValue(key, i)
            except OSError:
                break
            ports.append({"port": port, "device": device})
            i += 1
        ports.sort(key=lambda p: int("".join(c for c in p["port"] if c.isdigit()) or 0))
        return ports
    try:  # otras plataformas: pyserial
        from serial.tools import list_ports as lp
        return [{"port": p.device, "device": p.description} for p in lp.comports()]
    except ImportError:
        return ports


def SerialTransport(port: str, baudrate: int = 9600) -> Transport:
    try:
        import serial  # noqa: F401
        return _PySerialTransport(port, baudrate)
    except ImportError:
        if sys.platform != "win32":
            raise TransportError("Instala pyserial para usar puertos serie en esta plataforma")
        return _Win32SerialTransport(port, baudrate)


class _PySerialTransport(Transport):
    def __init__(self, port, baudrate):
        self.port, self.baudrate, self._s = port, baudrate, None

    def open(self):
        import serial
        self._s = serial.Serial(self.port, self.baudrate, timeout=0.05)

    def close(self):
        if self._s:
            self._s.close()
            self._s = None

    def set_baudrate(self, baud):
        self.baudrate = baud
        if self._s:
            self._s.baudrate = baud

    def write(self, data):
        self._s.write(data)

    def flush_input(self):
        self._s.reset_input_buffer()

    def read(self, n, timeout=1.5):
        buf = b""
        end = time.monotonic() + timeout
        while len(buf) < n and time.monotonic() < end:
            buf += self._s.read(n - len(buf))
        return buf


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _INVALID = wintypes.HANDLE(-1).value
    _MAXDWORD = 0xFFFFFFFF

    class _DCB(ctypes.Structure):
        _fields_ = [
            ("DCBlength", wintypes.DWORD), ("BaudRate", wintypes.DWORD),
            ("fBinary", wintypes.DWORD, 1), ("fParity", wintypes.DWORD, 1),
            ("fOutxCtsFlow", wintypes.DWORD, 1), ("fOutxDsrFlow", wintypes.DWORD, 1),
            ("fDtrControl", wintypes.DWORD, 2), ("fDsrSensitivity", wintypes.DWORD, 1),
            ("fTXContinueOnXoff", wintypes.DWORD, 1), ("fOutX", wintypes.DWORD, 1),
            ("fInX", wintypes.DWORD, 1), ("fErrorChar", wintypes.DWORD, 1),
            ("fNull", wintypes.DWORD, 1), ("fRtsControl", wintypes.DWORD, 2),
            ("fAbortOnError", wintypes.DWORD, 1), ("fDummy2", wintypes.DWORD, 17),
            ("wReserved", wintypes.WORD), ("XonLim", wintypes.WORD), ("XoffLim", wintypes.WORD),
            ("ByteSize", wintypes.BYTE), ("Parity", wintypes.BYTE), ("StopBits", wintypes.BYTE),
            ("XonChar", ctypes.c_char), ("XoffChar", ctypes.c_char), ("ErrorChar", ctypes.c_char),
            ("EofChar", ctypes.c_char), ("EvtChar", ctypes.c_char), ("wReserved1", wintypes.WORD),
        ]

    class _COMMTIMEOUTS(ctypes.Structure):
        _fields_ = [(n, wintypes.DWORD) for n in (
            "ReadIntervalTimeout", "ReadTotalTimeoutMultiplier", "ReadTotalTimeoutConstant",
            "WriteTotalTimeoutMultiplier", "WriteTotalTimeoutConstant")]

    _k32.CreateFileW.restype = wintypes.HANDLE
    _k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                 wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    for _fn, _args in (("GetCommState", [wintypes.HANDLE, ctypes.POINTER(_DCB)]),
                       ("SetCommState", [wintypes.HANDLE, ctypes.POINTER(_DCB)]),
                       ("SetCommTimeouts", [wintypes.HANDLE, ctypes.POINTER(_COMMTIMEOUTS)]),
                       ("PurgeComm", [wintypes.HANDLE, wintypes.DWORD]),
                       ("CloseHandle", [wintypes.HANDLE]),
                       ("ReadFile", [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
                                     ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]),
                       ("WriteFile", [wintypes.HANDLE, wintypes.LPCVOID, wintypes.DWORD,
                                      ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID])):
        getattr(_k32, _fn).argtypes = _args
        getattr(_k32, _fn).restype = wintypes.BOOL


class _Win32SerialTransport(Transport):
    """Puerto serie nativo Win32 (8N1, sin control de flujo, DTR/RTS desactivados)."""

    def __init__(self, port, baudrate):
        self.port, self.baudrate, self._h = port, baudrate, None

    def _check(self, ok, what):
        if not ok:
            raise TransportError("%s fallo en %s (error %d)" % (what, self.port, ctypes.get_last_error()))

    def open(self):
        h = _k32.CreateFileW("\\\\.\\" + self.port, 0xC0000000, 0, None, 3, 0, None)
        if h in (None, _INVALID):
            raise TransportError("No se puede abrir %s (error %d). ¿Lo usa otro programa?"
                                 % (self.port, ctypes.get_last_error()))
        self._h = h
        self._apply_state()
        self.flush_input()

    def _apply_state(self):
        dcb = _DCB()
        dcb.DCBlength = ctypes.sizeof(_DCB)
        self._check(_k32.GetCommState(self._h, ctypes.byref(dcb)), "GetCommState")
        dcb.BaudRate, dcb.ByteSize, dcb.Parity, dcb.StopBits = self.baudrate, 8, 0, 0
        dcb.fBinary, dcb.fParity, dcb.fOutxCtsFlow, dcb.fOutxDsrFlow = 1, 0, 0, 0
        dcb.fDtrControl, dcb.fRtsControl, dcb.fOutX, dcb.fInX = 0, 0, 0, 0
        dcb.fDsrSensitivity, dcb.fNull, dcb.fAbortOnError = 0, 0, 0
        self._check(_k32.SetCommState(self._h, ctypes.byref(dcb)), "SetCommState")

    def _set_read_timeout(self, ms):
        t = _COMMTIMEOUTS(_MAXDWORD, _MAXDWORD, max(1, ms), 0, 2000)
        self._check(_k32.SetCommTimeouts(self._h, ctypes.byref(t)), "SetCommTimeouts")

    def close(self):
        if self._h:
            _k32.CloseHandle(self._h)
            self._h = None

    def set_baudrate(self, baud):
        self.baudrate = baud
        if self._h:
            self._apply_state()

    def flush_input(self):
        _k32.PurgeComm(self._h, 0x0008 | 0x0002)  # PURGE_RXCLEAR | PURGE_RXABORT

    def write(self, data):
        n = wintypes.DWORD()
        self._check(_k32.WriteFile(self._h, data, len(data), ctypes.byref(n), None), "WriteFile")
        if n.value != len(data):
            raise TransportError("Escritura incompleta en %s" % self.port)

    def read(self, n, timeout=1.5):
        buf = bytearray()
        end = time.monotonic() + timeout
        chunk = ctypes.create_string_buffer(n)
        while len(buf) < n:
            left = end - time.monotonic()
            if left <= 0:
                break
            self._set_read_timeout(int(left * 1000))
            got = wintypes.DWORD()
            self._check(_k32.ReadFile(self._h, chunk, n - len(buf), ctypes.byref(got), None), "ReadFile")
            buf += chunk.raw[:got.value]
        return bytes(buf)
