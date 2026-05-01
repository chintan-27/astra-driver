"""
orbbec-astra-raw — unofficial Python driver for the Orbbec Astra Pro IR sensor.

Quick start
-----------
    from astra_raw import AstraIRCamera

    with AstraIRCamera() as cam:
        ir    = cam.read_ir()        # (480, 640) uint16 — Y11 disparity
        depth = cam.read_depth_mm()  # (480, 640) float32 — millimetres
        color = cam.read_color()     # (480, 640, 3) uint8 BGR, or None
"""

from .camera import AstraIRCamera
from .packets import decode_y11_msb, parse_packet_stream, decode_frame
from .ir import ir_to_depth_mm, stretch, colorize_ir, colorize_depth

__version__ = "0.2.0"
__all__ = [
    "AstraIRCamera",
    "decode_y11_msb",
    "parse_packet_stream",
    "decode_frame",
    "ir_to_depth_mm",
    "stretch",
    "colorize_ir",
    "colorize_depth",
]
