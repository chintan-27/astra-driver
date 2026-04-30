"""
IR and depth image processing utilities.

All functions accept numpy arrays and return numpy arrays.
OpenCV is required only for colorize_* and process_depth helpers.
The core decode path (packets.py) has no OpenCV dependency.
"""

import numpy as np

# Disparity-to-depth constant for Y11:
# K = fx(570) × baseline(75 mm) × sub_pixel_factor(8 for 11-bit)
DISP_K: float = 342_000.0


def ir_to_depth_mm(ir: np.ndarray, K: float = DISP_K) -> np.ndarray:
    """
    Convert Y11 disparity values to depth in millimetres.

    depth = K / disparity  (0 where disparity == 0)

    Parameters
    ----------
    ir : (H, W) uint16 — Y11 disparity frame from decode_frame()
    K  : disparity constant (default 342 000)

    Returns
    -------
    (H, W) float32 — depth in mm; 0 = invalid/no-return pixel
    """
    depth = np.zeros(ir.shape, dtype=np.float32)
    valid = ir > 0
    depth[valid] = K / ir[valid].astype(np.float32)
    return depth


def stretch(img: np.ndarray, lo_pct: float = 16.0, hi_pct: float = 89.0,
            gamma: float = 0.80) -> np.ndarray:
    """
    Percentile stretch + gamma correction → uint8 [0, 255].

    Parameters
    ----------
    img     : (H, W) array of any numeric dtype
    lo_pct  : lower percentile for black point
    hi_pct  : upper percentile for white point
    gamma   : exponent applied after normalisation (< 1 = brighter)

    Returns
    -------
    (H, W) uint8
    """
    f = img.astype(np.float32)
    lo = float(np.percentile(f, lo_pct))
    hi = float(np.percentile(f, hi_pct))
    if hi <= lo:
        return np.zeros(img.shape, dtype=np.uint8)
    f = np.clip((f - lo) / (hi - lo), 0.0, 1.0)
    return (np.power(f, gamma) * 255).astype(np.uint8)


def colorize_ir(ir: np.ndarray, lo_pct: float = 16.0, hi_pct: float = 89.0,
                gamma: float = 0.80, median: bool = True,
                clahe: bool = False) -> np.ndarray:
    """
    Render a Y11 IR frame as a BGR uint8 image suitable for cv2.imshow.

    Requires OpenCV.

    Parameters
    ----------
    ir      : (H, W) uint16 from decode_frame()
    lo_pct  : lower percentile clip
    hi_pct  : upper percentile clip
    gamma   : brightness curve (< 1 = brighter)
    median  : apply 3×3 median blur (reduces speckle)
    clahe   : apply CLAHE for local contrast enhancement

    Returns
    -------
    (H, W, 3) uint8 BGR
    """
    import cv2
    u8 = stretch(ir, lo_pct, hi_pct, gamma)
    if clahe:
        u8 = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(u8)
    if median:
        u8 = cv2.medianBlur(u8, 3)
    return cv2.cvtColor(u8, cv2.COLOR_GRAY2BGR)


def colorize_depth(depth_mm: np.ndarray, min_mm: float = 0,
                   max_mm: float = 8000) -> np.ndarray:
    """
    Render a depth_mm array as a JET BGR image. Near=red, far=blue, void=black.

    Requires OpenCV.

    Parameters
    ----------
    depth_mm : (H, W) float32 from ir_to_depth_mm()
    min_mm   : minimum valid depth
    max_mm   : maximum valid depth

    Returns
    -------
    (H, W, 3) uint8 BGR
    """
    import cv2
    valid = (depth_mm > min_mm) & (depth_mm < max_mm)
    norm  = np.zeros(depth_mm.shape, dtype=np.float32)
    if valid.any():
        v  = depth_mm[valid]
        lo = float(np.percentile(v, 2))
        hi = float(np.percentile(v, 98))
        if hi > lo:
            norm[valid] = np.clip(1.0 - (v - lo) / (hi - lo), 0.0, 1.0)
    d8  = (norm * 255).astype(np.uint8)
    col = cv2.applyColorMap(d8, cv2.COLORMAP_JET)
    col[d8 == 0] = 0
    return col
