"""Read one depth frame and print statistics — no OpenCV needed."""
from astra_raw import AstraIRCamera

with AstraIRCamera() as cam:
    depth = cam.read_depth_mm()

if depth is not None:
    valid = (depth > 0) & (depth < 8000)
    print(f"shape : {depth.shape}")
    print(f"valid : {100 * valid.mean():.1f}%")
    print(f"range : {depth[valid].min():.0f} – {depth[valid].max():.0f} mm")
