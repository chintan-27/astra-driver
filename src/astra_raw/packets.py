"""
Packet parsing and Y11 decoding for the Orbbec Astra Pro IR stream.

Confirmed format (reverse-engineered from raw USB capture):
  Magic:            52 42 00 72  (4 bytes)
  Packet size:      3072 bytes
  Header:           12 bytes — magic(4) + seq_le_u32(4) + gid_le_u32(4)
  Payload:          3060 bytes per packet
  Packets per frame: 137 (packets sharing the same gid form one frame)
  Pixel format:     Y11 MSB-first — 11-bit values, big-endian bit packing
  Raw raster:       1280 × 240
  Output:           center crop x=320..960 → resize to 640 × 480
"""

import struct
import numpy as np

MAGIC             = b'\x52\x42\x00\x72'
PACKET_SIZE       = 3072
HEADER_SIZE       = 12
PAYLOAD_SIZE      = PACKET_SIZE - HEADER_SIZE   # 3060
PACKETS_PER_FRAME = 137

RAW_W, RAW_H     = 1280, 240
CROP_X           = 320
CROP_W, CROP_H   = 640, 240
OUT_W, OUT_H     = 640, 480


def parse_packet_stream(blob: bytes) -> dict:
    """
    Scan a raw USB blob for MAGIC-delimited 3072-byte packets.

    Returns a dict mapping gid → list of (seq, payload_bytes) tuples.
    Each gid value corresponds to one captured frame group.
    """
    groups: dict = {}
    pos = 0
    while True:
        i = blob.find(MAGIC, pos)
        if i == -1:
            break
        if i + PACKET_SIZE <= len(blob):
            pkt = blob[i:i + PACKET_SIZE]
            seq = struct.unpack_from('<I', pkt, 4)[0]
            gid = struct.unpack_from('<I', pkt, 8)[0]
            payload = pkt[HEADER_SIZE:]
            groups.setdefault(gid, []).append((seq, payload))
        pos = i + 1
    return groups


def decode_y11_msb(buf: bytes) -> np.ndarray:
    """
    Unpack MSB-first 11-bit samples from a raw byte buffer.

    Each 11 consecutive bits (big-endian order) form one uint16 sample.
    Returns a 1-D uint16 numpy array.
    """
    bits = np.unpackbits(np.frombuffer(buf, dtype=np.uint8), bitorder='big')
    count = len(bits) // 11
    if count == 0:
        return np.zeros(0, dtype=np.uint16)
    bits = bits[:count * 11].reshape(count, 11)
    weights = (1 << np.arange(10, -1, -1, dtype=np.uint32))
    return (bits.astype(np.uint32) * weights).sum(axis=1).astype(np.uint16)


def decode_frame(blob: bytes) -> 'np.ndarray | None':
    """
    Decode one IR frame from a raw USB blob.

    Pipeline:
      1. parse_packet_stream → pick the largest group (most complete frame)
      2. Sort packets by seq, take up to PACKETS_PER_FRAME
      3. Concatenate payloads → decode_y11_msb → reshape to 1280×240
      4. Center-crop to 640×240 → resize to 640×480

    Returns a (OUT_H, OUT_W) = (480, 640) uint16 array, or None if the blob
    contains no usable frame group.
    """
    try:
        import cv2
        _resize = lambda img: cv2.resize(img, (OUT_W, OUT_H),
                                         interpolation=cv2.INTER_LINEAR)
    except ImportError:
        import numpy as _np
        _resize = lambda img: _np.repeat(
            _np.repeat(img, OUT_H // CROP_H, axis=0), OUT_W // CROP_W, axis=1)

    groups = parse_packet_stream(blob)
    if not groups:
        return None

    _, best_packets = max(groups.items(), key=lambda kv: len(kv[1]))
    if len(best_packets) < 10:
        return None

    best_packets.sort(key=lambda x: x[0])
    joined = b''.join(p for _, p in best_packets[:PACKETS_PER_FRAME])

    vals = decode_y11_msb(joined)
    n = RAW_W * RAW_H
    if len(vals) < n:
        vals = np.pad(vals, (0, n - len(vals)))
    else:
        vals = vals[:n]

    raw = vals.reshape(RAW_H, RAW_W)
    cropped = raw[:CROP_H, CROP_X:CROP_X + CROP_W]
    return _resize(cropped)
