"""
CLI entry points for orbbec-astra-raw.

Commands installed by pyproject.toml:
  astra-ir-view   — live viewer (requires opencv-python)
  astra-ir-save   — save one IR frame to a PNG file
  astra-ir-dump   — dump one raw frame payload to a .bin file
"""

import sys
import numpy as np


def _require_cv2():
    try:
        import cv2
        return cv2
    except ImportError:
        sys.exit("opencv-python is required for this command.\n"
                 "Install it with:  pip install orbbec-astra-raw[viewer]")


# ── astra-ir-view ──────────────────────────────────────────────────────────────

def cmd_view():
    """Live three-panel viewer: Depth | IR | Color."""
    cv2 = _require_cv2()
    from .camera import AstraIRCamera
    from .ir import colorize_ir, colorize_depth, ir_to_depth_mm

    H, W = 480, 640
    gamma   = 0.80
    lo, hi  = 16.0, 89.0
    median  = True
    clahe   = False
    speckle = True
    temporal = True
    _prev_depth = [None]
    _clahe_obj  = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

    def _process_depth(d):
        out = d.copy()
        if speckle:
            d_int = np.clip(out, 0, 32767).astype(np.int16)
            cv2.filterSpeckles(d_int, 0, 400, 150)
            out = np.where(d_int > 0, d_int.astype(np.float32), 0.0)
        if temporal and _prev_depth[0] is not None:
            prev = _prev_depth[0]
            if prev.shape == out.shape:
                both = (out > 0) & (prev > 0)
                close = np.abs(out - prev) < 200
                mask  = both & close
                out[mask] = 0.35 * prev[mask] + 0.65 * out[mask]
        _prev_depth[0] = out.copy()
        return out

    def _ir_bgr(frame):
        u8 = _clahe_obj.apply(
            np.clip(((frame.astype(np.float32) - np.percentile(frame, lo)) /
                     max(np.percentile(frame, hi) - np.percentile(frame, lo), 1)
                     ).clip(0, 1) ** gamma * 255, 0, 255).astype(np.uint8)
        ) if clahe else (
            np.clip(((frame.astype(np.float32) - np.percentile(frame, lo)) /
                     max(np.percentile(frame, hi) - np.percentile(frame, lo), 1)
                     ).clip(0, 1) ** gamma * 255, 0, 255).astype(np.uint8)
        )
        if median:
            u8 = cv2.medianBlur(u8, 3)
        return cv2.cvtColor(u8, cv2.COLOR_GRAY2BGR)

    color_cap = cv2.VideoCapture(0)
    if color_cap.isOpened():
        color_cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        color_cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    print("astra-ir-view  Q=quit S=save G/H=γ J/K=lo N/M=hi U=median C=CLAHE T=temporal P=speckle")

    with AstraIRCamera() as cam:
        fc = 0
        import time
        t0 = time.monotonic()
        fps = 0.0

        while True:
            frame = cam.read_ir(timeout=5.0)
            if frame is None:
                print("waiting for frame…")
                continue

            fc += 1
            if fc % 5 == 0:
                t1 = time.monotonic(); fps = 5 / max(t1 - t0, 1e-6); t0 = t1

            depth    = _process_depth(ir_to_depth_mm(frame))
            depth_col = colorize_depth(depth)
            ir_bgr_   = _ir_bgr(frame)

            if color_cap.isOpened():
                color_cap.grab()
                ret, c = color_cap.read()
                color_bgr = cv2.resize(c, (W, H)) if ret else np.zeros((H, W, 3), np.uint8)
            else:
                color_bgr = np.zeros((H, W, 3), np.uint8)

            vd = (depth > 0) & (depth < 8000)
            rng = (f"{int(depth[vd].min())}-{int(depth[vd].max())}mm"
                   if vd.any() else "—")
            cv2.putText(depth_col, f"DEPTH {fps:.1f}fps {rng}", (8, 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            cv2.putText(ir_bgr_,   f"IR g={gamma:.2f} lo={lo:.0f} hi={hi:.0f}", (8, 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (220, 220, 220), 1)
            cv2.putText(color_bgr, "COLOR", (8, 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (220, 220, 220), 1)

            cv2.imshow("Astra Pro — Depth | IR | Color",
                       np.hstack([depth_col, ir_bgr_, color_bgr]))

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('s'):
                cv2.imwrite('/tmp/depth.png', depth_col)
                cv2.imwrite('/tmp/ir.png', ir_bgr_)
                cv2.imwrite('/tmp/color.png', color_bgr)
                print(f"Saved /tmp/{{depth,ir,color}}.png (frame #{fc})")
            elif key == ord('g'): gamma = max(0.1, gamma - 0.05)
            elif key == ord('h'): gamma = min(2.0, gamma + 0.05)
            elif key == ord('j'): lo    = max(0.0,  lo - 0.5)
            elif key == ord('k'): lo    = min(30.0, lo + 0.5)
            elif key == ord('n'): hi    = max(50.0, hi - 0.5)
            elif key == ord('m'): hi    = min(100.0, hi + 0.5)
            elif key == ord('u'): median  = not median
            elif key == ord('c'): clahe   = not clahe
            elif key == ord('t'): temporal = not temporal; _prev_depth[0] = None
            elif key == ord('p'): speckle  = not speckle

    cv2.destroyAllWindows()
    if color_cap.isOpened():
        color_cap.release()


# ── astra-ir-save ─────────────────────────────────────────────────────────────

def cmd_save():
    """Save one IR frame as a PNG. Usage: astra-ir-save [output.png]"""
    cv2 = _require_cv2()
    from .camera import AstraIRCamera
    from .ir import stretch

    out = sys.argv[1] if len(sys.argv) > 1 else "ir_frame.png"
    print(f"Capturing one frame → {out}")
    with AstraIRCamera() as cam:
        frame = cam.read_ir(timeout=10.0)
    if frame is None:
        sys.exit("Timed out waiting for frame.")
    u8 = stretch(frame)
    cv2.imwrite(out, u8)
    print(f"Saved {out}  shape={frame.shape} max={frame.max()}")


# ── astra-ir-dump ─────────────────────────────────────────────────────────────

def cmd_dump():
    """Dump one raw frame payload as binary. Usage: astra-ir-dump [output.bin]"""
    from .camera import AstraIRCamera

    out = sys.argv[1] if len(sys.argv) > 1 else "ir_raw.bin"
    print(f"Capturing raw group → {out}")
    with AstraIRCamera() as cam:
        raw = cam.read_raw_group(timeout=10.0)
    if raw is None:
        sys.exit("Timed out waiting for frame.")
    with open(out, 'wb') as f:
        f.write(raw)
    print(f"Saved {out}  {len(raw)} bytes")
