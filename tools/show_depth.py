"""
Astra Pro live viewer — Depth | IR | Color  (1920×480 window)

Packet format: 3072-byte packets, 12-byte header, 137 packets/frame,
Y11 MSB-first, 1280×240 → center crop 640×240 → resize to 640×480.

Keys:
  q       quit
  s       save panels to /tmp/
  g / h   IR gamma  down / up
  j / k   IR lo-percentile  down / up
  n / m   IR hi-percentile  down / up
  u       toggle median blur on IR
  c       toggle CLAHE on IR
  t       toggle temporal smoothing on depth
  p       toggle speckle filter on depth
"""
import sys, pathlib, time, threading, queue
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import numpy as np
import cv2
import usb.core, usb.util

from astra_depth.platform import get_backend
from astra_depth.openni_init import run_init
from astra_depth.frame import decode_frame, ir_to_depth_mm

# ── USB ───────────────────────────────────────────────────────────────────────
backend = get_backend()
dev = usb.core.find(idVendor=0x2BC5, idProduct=0x0403, backend=backend)
if dev is None:
    sys.exit("Camera not found (2BC5:0403)")
try:
    dev.set_configuration()
except Exception:
    pass
try:
    usb.util.claim_interface(dev, 0)
except Exception:
    pass

print("Init…")
run_init(dev)
print("Streaming…")

# ── Reader thread ─────────────────────────────────────────────────────────────
frame_q: queue.Queue = queue.Queue(maxsize=2)

def _reader():
    while True:
        blob = bytearray()
        try:
            for _ in range(64):
                data = dev.read(0x81, 16384, timeout=3000)
                blob.extend(bytes(data))
        except Exception as e:
            print(f"[reader] {e}")
            time.sleep(0.05)
            continue
        frame = decode_frame(bytes(blob))
        if frame is not None:
            try:
                frame_q.put_nowait(frame)
            except queue.Full:
                pass

threading.Thread(target=_reader, daemon=True).start()

# ── Color camera ──────────────────────────────────────────────────────────────
color_cap = cv2.VideoCapture(0)
if color_cap.isOpened():
    color_cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
    color_cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    print("Color camera opened.")
else:
    color_cap = None
    print("Color camera not found.")

# ── Display params ────────────────────────────────────────────────────────────
gamma_value  = 0.80
p_lo         = 16.0
p_hi         = 89.0
use_median   = True
use_clahe    = False
use_temporal = True   # EMA smoothing on depth
use_speckle  = True   # speckle filter on depth

H, W = 480, 640
_clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

# Temporal state
_prev_depth: np.ndarray = None
_TEMPORAL_W = 0.35   # weight on previous frame (lower = faster response)


def process_depth(depth_mm: np.ndarray) -> np.ndarray:
    """Speckle filter + temporal EMA on depth_mm (float32)."""
    global _prev_depth

    out = depth_mm.copy()

    # Speckle removal: treat depth as disparity-like int for filterSpeckles
    if use_speckle:
        d_int = np.clip(out, 0, 32767).astype(np.int16)
        cv2.filterSpeckles(d_int, 0, 400, 150)
        out = np.where(d_int > 0, d_int.astype(np.float32), 0.0)

    # Temporal EMA — only blend where both frames agree within 200 mm
    if use_temporal and _prev_depth is not None and _prev_depth.shape == out.shape:
        both_valid = (out > 0) & (_prev_depth > 0)
        close      = np.abs(out - _prev_depth) < 200
        blend_mask = both_valid & close
        out[blend_mask] = (_TEMPORAL_W * _prev_depth[blend_mask] +
                           (1 - _TEMPORAL_W) * out[blend_mask])

    _prev_depth = out.copy()
    return out


def colorize_ir(img, lo, hi, gamma, median, clahe):
    """Percentile stretch + gamma + optional median/CLAHE → BGR."""
    f = img.astype(np.float32)
    lo_v = np.percentile(f, lo)
    hi_v = np.percentile(f, hi)
    if hi_v <= lo_v:
        return np.zeros((H, W, 3), dtype=np.uint8)
    f = np.clip((f - lo_v) / (hi_v - lo_v), 0.0, 1.0)
    f = np.power(f, gamma)
    u8 = (f * 255).astype(np.uint8)
    if clahe:
        u8 = _clahe.apply(u8)
    if median:
        u8 = cv2.medianBlur(u8, 3)
    return cv2.cvtColor(u8, cv2.COLOR_GRAY2BGR)


def colorize_depth(depth_mm: np.ndarray) -> np.ndarray:
    """Percentile-stretched JET. Near=red, far=blue. Black=void."""
    valid = (depth_mm > 0) & (depth_mm < 8000)
    norm  = np.zeros((H, W), dtype=np.float32)
    if valid.any():
        v  = depth_mm[valid]
        lo = float(np.percentile(v, 2))
        hi = float(np.percentile(v, 98))
        if hi > lo:
            norm[valid] = np.clip(1.0 - (v - lo) / (hi - lo), 0, 1)
    d8  = (norm * 255).astype(np.uint8)
    col = cv2.applyColorMap(d8, cv2.COLORMAP_JET)
    col[d8 == 0] = 0
    return col


def filter_status():
    s  = 'T' if use_temporal else '-'
    s += 'P' if use_speckle  else '-'
    s += 'C' if use_clahe    else '-'
    s += 'M' if use_median   else '-'
    return f'[{s}]'


print("Q=quit  S=save  G/H=γ  J/K=lo  N/M=hi  U=median  C=CLAHE  T=temporal  P=speckle")
fc  = 0
t0  = time.monotonic()
fps = 0.0

while True:
    try:
        raw = frame_q.get(timeout=5.0)
    except queue.Empty:
        print("waiting for frames…")
        continue

    fc += 1
    if fc % 5 == 0:
        t1  = time.monotonic()
        fps = 5 / max(t1 - t0, 1e-6)
        t0  = t1

    depth_mm  = ir_to_depth_mm(raw)
    depth_mm  = process_depth(depth_mm)
    depth_col = colorize_depth(depth_mm)
    ir_bgr    = colorize_ir(raw, p_lo, p_hi, gamma_value, use_median, use_clahe)

    # Color panel
    if color_cap is not None:
        color_cap.grab()
        ret, c = color_cap.read()
        color_bgr = cv2.resize(c, (W, H)) if ret else np.zeros((H, W, 3), np.uint8)
    else:
        color_bgr = np.zeros((H, W, 3), np.uint8)
        cv2.putText(color_bgr, "No color camera", (150, 240),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (80, 80, 80), 1)

    # HUD
    valid_d = (depth_mm > 0) & (depth_mm < 8000)
    d_range = (f"{int(depth_mm[valid_d].min())}-{int(depth_mm[valid_d].max())}mm"
               if valid_d.any() else "no depth")
    cv2.putText(depth_col, f"DEPTH {filter_status()} {fps:.1f}fps  {d_range}",
                (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    cv2.putText(ir_bgr, f"IR  g={gamma_value:.2f} lo={p_lo:.0f} hi={p_hi:.0f}",
                (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (220, 220, 220), 1)
    cv2.putText(color_bgr, "COLOR", (8, 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (220, 220, 220), 1)

    cv2.imshow("Astra Pro — Depth | IR | Color",
               np.hstack([depth_col, ir_bgr, color_bgr]))

    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        break
    elif key == ord('s'):
        cv2.imwrite('/tmp/depth.png',   depth_col)
        cv2.imwrite('/tmp/ir.png',      ir_bgr)
        cv2.imwrite('/tmp/color.png',   color_bgr)
        print(f"Saved /tmp/{{depth,ir,color}}.png  (frame #{fc})")
    elif key == ord('g'):
        gamma_value = max(0.1, gamma_value - 0.05)
    elif key == ord('h'):
        gamma_value = min(2.0, gamma_value + 0.05)
    elif key == ord('j'):
        p_lo = max(0.0, p_lo - 0.5)
    elif key == ord('k'):
        p_lo = min(30.0, p_lo + 0.5)
    elif key == ord('n'):
        p_hi = max(50.0, p_hi - 0.5)
    elif key == ord('m'):
        p_hi = min(100.0, p_hi + 0.5)
    elif key == ord('u'):
        use_median = not use_median
        print(f"median -> {use_median}")
    elif key == ord('c'):
        use_clahe = not use_clahe
        print(f"CLAHE -> {use_clahe}")
    elif key == ord('t'):
        use_temporal = not use_temporal
        _prev_depth  = None
        print(f"temporal -> {use_temporal}")
    elif key == ord('p'):
        use_speckle = not use_speckle
        print(f"speckle -> {use_speckle}")

cv2.destroyAllWindows()
if color_cap is not None:
    color_cap.release()
usb.util.dispose_resources(dev)
