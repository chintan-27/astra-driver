# orbbec-astra-raw

Unofficial pure-Python driver for the **Orbbec Astra Pro** IR / depth sensor.

Works without the broken OpenNI2 / pyorbbecsdk stack. Reverse-engineered from
raw USB traffic. No compiled extensions, no kernel drivers.

## Supported hardware

| Device | VID:PID |
|--------|---------|
| Orbbec Astra Pro depth/IR sensor | `2BC5:0403` |

The color camera (`2BC5:0501`) is a standard UVC webcam — use OpenCV's
`VideoCapture` directly.

## Install

```bash
# Core library only (numpy arrays, no viewer)
pip install orbbec-astra-raw

# With live viewer (requires OpenCV)
pip install orbbec-astra-raw[viewer]
```

## Quick start

```python
from astra_raw import AstraIRCamera

with AstraIRCamera() as cam:
    ir    = cam.read_ir()        # (480, 640) uint16 — raw Y11 values
    depth = cam.read_depth_mm()  # (480, 640) float32 — millimetres (0 = invalid)
```

## CLI

```bash
# Live three-panel viewer: Depth | IR | Color
astra-ir-view

# Save one IR frame to PNG
astra-ir-save frame.png

# Dump one raw frame payload to binary
astra-ir-dump frame.bin
```

### Viewer keys

| Key | Action |
|-----|--------|
| `q` | quit |
| `s` | save depth / IR / color PNGs to `/tmp/` |
| `g` / `h` | IR gamma down / up |
| `j` / `k` | IR lo-percentile down / up |
| `n` / `m` | IR hi-percentile down / up |
| `u` | toggle median blur |
| `c` | toggle CLAHE |
| `t` | toggle temporal smoothing on depth |
| `p` | toggle speckle filter on depth |

## API

```python
from astra_raw import AstraIRCamera, decode_y11_msb, parse_packet_stream

cam = AstraIRCamera()
cam.open()

ir    = cam.read_ir()           # (480, 640) uint16
depth = cam.read_depth_mm()     # (480, 640) float32 mm
raw   = cam.read_raw_group()    # bytes — undecoded Y11 payload

cam.close()

# Lower-level helpers
groups = parse_packet_stream(blob)   # {gid: [(seq, payload), ...]}
vals   = decode_y11_msb(payload)     # 1-D uint16 array
```

## OS notes

| Platform | Status |
|----------|--------|
| macOS (Apple Silicon) | works without sudo |
| Linux | requires a udev rule for non-root USB access |
| Windows | requires Zadig to bind WinUSB to `2BC5:0403` |

### Linux udev rule

```
# /etc/udev/rules.d/99-orbbec-astra.rules
SUBSYSTEM=="usb", ATTRS{idVendor}=="2bc5", ATTRS{idProduct}=="0403", MODE="0666"
```

Then: `sudo udevadm control --reload && sudo udevadm trigger`

### Windows

Install [Zadig](https://zadig.akeo.ie/), select **ASTRA Pro** (PID 0403),
install **WinUSB**, then run your Python script normally.

## How it works

The sensor streams 3072-byte packets on USB bulk endpoint `0x81`. Each packet
has a 12-byte header (`magic` + `seq` + `gid`) followed by 3060 bytes of Y11
payload. Grouping 137 packets by their `gid` field assembles one frame.

The payload is decoded as 11-bit MSB-first (big-endian bit order) samples,
reshaped to 1280x240, center-cropped to 640x240, and resized to 640x480.

Depth is estimated as `K / disparity` where `K = 342 000`
(focal-length x baseline x sub-pixel-factor for this sensor).

## License

MIT
