"""
AstraIRCamera — high-level API for the Orbbec Astra Pro IR/depth stream.

Usage
-----
    from astra_raw import AstraIRCamera

    with AstraIRCamera() as cam:
        ir    = cam.read_ir()        # (480, 640) uint16
        depth = cam.read_depth_mm()  # (480, 640) float32, mm
"""

import threading
import queue
import time

import usb.util

from .transport import find_device, open_device, run_init, read_blob
from .packets import decode_frame
from .ir import ir_to_depth_mm

_READS_PER_BLOB = 64     # matches temp2.py: ~1 MB per accumulation
_QUEUE_MAXSIZE  = 4


class AstraIRCamera:
    """
    Pure Python driver for the Orbbec Astra Pro IR/depth sensor.

    Streams are decoded in a background thread so read_ir() always returns
    the most recent frame without blocking on USB I/O.

    Parameters
    ----------
    reads_per_blob : int
        Number of 16 KB USB reads accumulated before attempting frame decode.
        Lower = higher CPU, possibly higher frame rate.
        Higher = lower CPU, slightly more latency per frame.
    """

    def __init__(self, reads_per_blob: int = _READS_PER_BLOB):
        self._reads_per_blob = reads_per_blob
        self._dev            = None
        self._thread         = None
        self._stop           = threading.Event()
        self._q: queue.Queue = queue.Queue(maxsize=_QUEUE_MAXSIZE)

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def open(self) -> None:
        """Open the camera and start background streaming."""
        self._dev = find_device()
        open_device(self._dev)
        run_init(self._dev)
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def close(self) -> None:
        """Stop streaming and release USB resources."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None
        if self._dev is not None:
            try:
                usb.util.dispose_resources(self._dev)
            except Exception:
                pass
            self._dev = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *_):
        self.close()

    # ── Public API ─────────────────────────────────────────────────────────────

    def read_ir(self, timeout: float = 5.0) -> 'np.ndarray | None':
        """
        Return the most recent IR frame as a (480, 640) uint16 numpy array.

        Values are raw Y11 disparity samples (0 = invalid/no-return).
        Returns None on timeout.

        Parameters
        ----------
        timeout : float — seconds to wait for a frame
        """
        try:
            return self._q.get(timeout=timeout)
        except queue.Empty:
            return None

    def read_ir_vga(self, timeout: float = 5.0) -> 'np.ndarray | None':
        """Alias for read_ir() — returns (480, 640) uint16."""
        return self.read_ir(timeout)

    def read_depth_mm(self, timeout: float = 5.0) -> 'np.ndarray | None':
        """
        Return depth in millimetres as a (480, 640) float32 numpy array.

        Computed from Y11 disparity via depth = 342 000 / disparity.
        0.0 = invalid pixel. Returns None on timeout.
        """
        ir = self.read_ir(timeout)
        if ir is None:
            return None
        return ir_to_depth_mm(ir)

    def read_raw_group(self, timeout: float = 5.0) -> 'bytes | None':
        """
        Return the raw concatenated payload bytes for one frame group,
        before Y11 decoding. Useful for recording or alternative processing.
        Returns None on timeout.
        """
        # Drain a blob and return raw best-group payload
        if self._dev is None:
            return None
        blob = read_blob(self._dev, self._reads_per_blob)
        from .packets import parse_packet_stream, PACKETS_PER_FRAME
        groups = parse_packet_stream(blob)
        if not groups:
            return None
        _, best = max(groups.items(), key=lambda kv: len(kv[1]))
        best.sort(key=lambda x: x[0])
        return b''.join(p for _, p in best[:PACKETS_PER_FRAME])

    # ── Internal ───────────────────────────────────────────────────────────────

    def _loop(self):
        while not self._stop.is_set():
            blob = read_blob(self._dev, self._reads_per_blob)
            frame = decode_frame(blob)
            if frame is not None:
                # Drop oldest if consumer is slow
                if self._q.full():
                    try:
                        self._q.get_nowait()
                    except queue.Empty:
                        pass
                self._q.put_nowait(frame)
