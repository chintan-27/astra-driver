"""
USB transport for the Orbbec Astra Pro depth/IR sensor (VID 2BC5, PID 0x0403).

Handles device discovery, libusb backend selection, and the initialization
sequence required to start bulk streaming on EP 0x81.

Init sequence extracted from usbmon capture of OrbbecSDK v1 on Linux.
"""

import sys
import pathlib
import usb.core
import usb.util

VID   = 0x2BC5
PID   = 0x0403
EP_IN = 0x81

_INIT_CMDS = [
    bytes.fromhex("474d0000 00000000".replace(" ", "")),
    bytes.fromhex("474d0000 28000100".replace(" ", "")),
    bytes.fromhex("474d0000 01000200".replace(" ", "")),
    bytes.fromhex("474d0000 06000300 0300".replace(" ", "")),
    bytes.fromhex("474d0000 01000400".replace(" ", "")),
    bytes.fromhex("474d0100 04000500 0000".replace(" ", "")),
    bytes.fromhex("474d0000 25000600".replace(" ", "")),
    bytes.fromhex("474d0500 16000700 07000000 00000000 0000".replace(" ", "")),
    bytes.fromhex("474d0000 27000800".replace(" ", "")),
    bytes.fromhex("474d0500 16000900 80000000 00000000 0000".replace(" ", "")),
    bytes.fromhex("474d0100 24000a00 0000".replace(" ", "")),
    bytes.fromhex("474d0100 02000b00 0100".replace(" ", "")),
    bytes.fromhex("474d0100 02000c00 0200".replace(" ", "")),
    bytes.fromhex("474d0100 02000d00 0500".replace(" ", "")),
    bytes.fromhex("474d0100 02000e00 0600".replace(" ", "")),
    bytes.fromhex("474d0100 02000f00 0c00".replace(" ", "")),
    bytes.fromhex("474d0100 02001000 0d00".replace(" ", "")),
    bytes.fromhex("474d0100 02001100 0e00".replace(" ", "")),
    bytes.fromhex("474d0100 02001200 1200".replace(" ", "")),
    bytes.fromhex("474d0100 02001300 1300".replace(" ", "")),
    bytes.fromhex("474d0100 02001400 1400".replace(" ", "")),
    bytes.fromhex("474d0100 02001500 1500".replace(" ", "")),
    bytes.fromhex("474d0100 02001600 1600".replace(" ", "")),
    bytes.fromhex("474d0100 02001700 1700".replace(" ", "")),
    bytes.fromhex("474d0100 02001800 3300".replace(" ", "")),
    bytes.fromhex("474d0100 02001900 3400".replace(" ", "")),
    bytes.fromhex("474d0100 02001a00 3500".replace(" ", "")),
    bytes.fromhex("474d0100 02001b00 3600".replace(" ", "")),
    bytes.fromhex("474d0100 02001c00 3700".replace(" ", "")),
    bytes.fromhex("474d0100 02001d00 1900".replace(" ", "")),
    bytes.fromhex("474d0100 02001e00 1a00".replace(" ", "")),
    bytes.fromhex("474d0100 02001f00 1b00".replace(" ", "")),
    bytes.fromhex("474d0100 02002000 4700".replace(" ", "")),
    bytes.fromhex("474d0100 02002100 4800".replace(" ", "")),
    bytes.fromhex("474d0100 02002200 4d00".replace(" ", "")),
    bytes.fromhex("474d0100 02002300 4e00".replace(" ", "")),
    bytes.fromhex("474d0100 02002400 5000".replace(" ", "")),
    bytes.fromhex("474d0100 02002500 5100".replace(" ", "")),
    bytes.fromhex("474d0100 02002600 0f00".replace(" ", "")),
    bytes.fromhex("474d0300 19002700 00000700 2000".replace(" ", "")),
    bytes.fromhex("474d0300 19002800 40000700 1c00".replace(" ", "")),
    bytes.fromhex("474d0400 e6032900 00010000 00000000".replace(" ", "")),
    bytes.fromhex("474d0100 02002a00 1700".replace(" ", "")),
    bytes.fromhex("474d0100 63002b00 0000".replace(" ", "")),
]

_POST_CLEAR_CMDS = [
    bytes.fromhex("474d0200 03002c00 12000300".replace(" ", "")),
    bytes.fromhex("474d0200 03002d00 13000100".replace(" ", "")),
    bytes.fromhex("474d0200 03002e00 14001e00".replace(" ", "")),
    bytes.fromhex("474d0200 03002f00 16000100".replace(" ", "")),
    bytes.fromhex("474d0200 03003000 02000000".replace(" ", "")),
    bytes.fromhex("474d0200 03003100 17000000".replace(" ", "")),
    bytes.fromhex("474d0200 03003200 06000200".replace(" ", "")),
    bytes.fromhex("474d0200 03003300 37000000".replace(" ", "")),
    bytes.fromhex("474d0200 03003400 01000000".replace(" ", "")),
]


def _get_backend():
    import usb.backend.libusb1
    if sys.platform == "darwin":
        for p in [
            "/opt/homebrew/lib/libusb-1.0.dylib",
            "/usr/local/lib/libusb-1.0.dylib",
        ]:
            if pathlib.Path(p).exists():
                return usb.backend.libusb1.get_backend(find_library=lambda x: p)
    if sys.platform == "win32":
        try:
            import libusb_package
            return usb.backend.libusb1.get_backend(
                find_library=libusb_package.find_library
            )
        except ImportError:
            pass
    be = usb.backend.libusb1.get_backend()
    if be is None:
        raise RuntimeError(
            "libusb backend not found. On Windows: pip install libusb-package"
        )
    return be


def find_device():
    """
    Find the Astra Pro depth/IR USB device.
    Returns a usb.core.Device, or raises RuntimeError if not found.
    """
    dev = usb.core.find(idVendor=VID, idProduct=PID, backend=_get_backend())
    if dev is None:
        raise RuntimeError(
            f"Orbbec Astra Pro not found (VID={VID:#06x} PID={PID:#06x}). "
            "Check the camera is plugged in and USB permissions allow access."
        )
    return dev


def open_device(dev):
    """Set configuration and claim interface 0. Errors are non-fatal."""
    try:
        dev.set_configuration()
    except usb.core.USBError:
        pass
    try:
        if dev.is_kernel_driver_active(0):
            dev.detach_kernel_driver(0)
    except Exception:
        pass
    try:
        usb.util.claim_interface(dev, 0)
    except usb.core.USBError:
        pass


def run_init(dev, timeout_ms: int = 5000):
    """
    Send the vendor EP0 init sequence and CLEAR_FEATURE to start streaming.
    Call once after open_device(), before any bulk reads.
    """
    for cmd in _INIT_CMDS:
        try:
            dev.ctrl_transfer(0x40, 0, 0, 0, cmd, timeout_ms)
            dev.ctrl_transfer(0xC0, 0, 0, 0, 512, timeout_ms)
        except Exception:
            pass
    dev.ctrl_transfer(0x02, 0x01, 0x0000, 0x0081, 0, timeout_ms)
    for cmd in _POST_CLEAR_CMDS:
        try:
            dev.ctrl_transfer(0x40, 0, 0, 0, cmd, timeout_ms)
            dev.ctrl_transfer(0xC0, 0, 0, 0, 512, timeout_ms)
        except Exception:
            pass


def read_blob(dev, n_reads: int = 64, read_size: int = 16384,
              timeout_ms: int = 3000) -> bytes:
    """Accumulate n_reads bulk-IN transfers into one bytes object."""
    buf = bytearray()
    for _ in range(n_reads):
        try:
            buf.extend(bytes(dev.read(EP_IN, read_size, timeout=timeout_ms)))
        except usb.core.USBError:
            break
    return bytes(buf)
