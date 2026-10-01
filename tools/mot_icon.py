"""Generate assets/mot.ico: a bold "M." on a dark rounded square with a teal dot.

Pure stdlib - no downloads, no Pillow. Pixels are rasterised with 4x supersampling
and packed as one uncompressed 32-bit BMP per size inside a single .ico container.
"""
from __future__ import annotations

import struct
from pathlib import Path

# Colours match the app: background #0c0d10, ink #e7e8ea, accent teal #14b8a6.
BG = (12, 13, 16)
BORDER = (46, 50, 58)
INK = (231, 232, 234)
ACCENT = (20, 184, 166)

SIZES = (16, 24, 32, 48, 64, 128, 256)
SAMPLES = 4  # supersampling factor per axis

# The mark, in canvas units (0.0 - 1.0), so one drawing serves every size.
_SQUARE_R = 0.20  # corner radius of the dark square
_EDGE = 0.030  # width of the subtle outline
_X0, _Y0, _X1, _Y1 = 0.16, 0.27, 0.60, 0.75  # bounding box of the letter
_XM = (_X0 + _X1) / 2
_VERTEX_Y = _Y0 + 0.60 * (_Y1 - _Y0)  # where the middle V of the M stops
_HALF = 0.052  # half stroke width - bold
_DOT_X, _DOT_Y, _DOT_R = 0.735, 0.692, 0.058  # the teal period

# The four strokes of an M: two stems and the two halves of the middle V.
_STROKES = (
    (_X0, _Y0, _X0, _Y1),
    (_X1, _Y0, _X1, _Y1),
    (_X0, _Y0, _XM, _VERTEX_Y),
    (_XM, _VERTEX_Y, _X1, _Y0),
)


def _seg_dist(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    """Distance from a point to a line segment."""
    vx, vy = bx - ax, by - ay
    wx, wy = px - ax, py - ay
    length2 = vx * vx + vy * vy
    t = 0.0 if length2 == 0 else max(0.0, min(1.0, (wx * vx + wy * vy) / length2))
    dx, dy = wx - t * vx, wy - t * vy
    return (dx * dx + dy * dy) ** 0.5


def _square_sdf(x: float, y: float) -> float:
    """Signed distance to the rounded square centred on the canvas (< 0 = inside)."""
    qx = abs(x - 0.5) - (0.5 - _SQUARE_R)
    qy = abs(y - 0.5) - (0.5 - _SQUARE_R)
    outside = (max(qx, 0.0) ** 2 + max(qy, 0.0) ** 2) ** 0.5
    return outside + min(max(qx, qy), 0.0) - _SQUARE_R


def _colour_at(x: float, y: float) -> tuple[int, int, int] | None:
    """Colour of one canvas point, or None where the icon is transparent."""
    sdf = _square_sdf(x, y)
    if sdf > 0:
        return None
    colour = BORDER if sdf > -_EDGE else BG
    for stroke in _STROKES:
        if _seg_dist(x, y, *stroke) <= _HALF:
            return INK
    if ((x - _DOT_X) ** 2 + (y - _DOT_Y) ** 2) ** 0.5 <= _DOT_R:
        return ACCENT
    return colour


def render(size: int, samples: int = SAMPLES) -> bytes:
    """Top-down BGRA rows for one square size."""
    out = bytearray(size * size * 4)
    total = samples * samples
    step = 1.0 / samples
    for row in range(size):
        for col in range(size):
            red = green = blue = hits = 0
            for sy in range(samples):
                y = (row + (sy + 0.5) * step) / size
                for sx in range(samples):
                    x = (col + (sx + 0.5) * step) / size
                    colour = _colour_at(x, y)
                    if colour is None:
                        continue
                    red += colour[0]
                    green += colour[1]
                    blue += colour[2]
                    hits += 1
            if not hits:
                continue
            at = (row * size + col) * 4
            out[at] = blue // hits
            out[at + 1] = green // hits
            out[at + 2] = red // hits
            out[at + 3] = 255 if hits == total else max(1, 255 * hits // total)
    return bytes(out)


def _bmp_image(size: int) -> bytes:
    """One .ico image entry: BITMAPINFOHEADER + bottom-up BGRA + bottom-up AND mask."""
    pixels = render(size)
    xor = bytearray()
    for row in range(size - 1, -1, -1):
        xor += pixels[row * size * 4 : (row + 1) * size * 4]

    stride = ((size + 31) // 32) * 4
    mask = bytearray()
    for row in range(size - 1, -1, -1):
        bits = bytearray(stride)
        for col in range(size):
            if pixels[(row * size + col) * 4 + 3] == 0:
                bits[col // 8] |= 0x80 >> (col % 8)
        mask += bits

    header = struct.pack(
        "<IiiHHIIiiII",
        40, size, size * 2, 1, 32, 0,  # header, w, h (XOR + AND), planes, bpp, raw
        len(xor) + len(mask), 0, 0, 0, 0,
    )
    return header + bytes(xor) + bytes(mask)


def write_ico(path: Path, sizes: tuple[int, ...] = SIZES) -> Path:
    """Write one .ico holding every size. Returns the path."""
    images = [_bmp_image(size) for size in sizes]
    count = len(images)
    offset = 6 + 16 * count
    entries = bytearray()
    body = bytearray()
    for size, image in zip(sizes, images):
        entries += struct.pack(
            "<BBBBHHII",
            size % 256, size % 256, 0, 0, 1, 32, len(image), offset,
        )
        offset += len(image)
        body += image
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(struct.pack("<HHH", 0, 1, count) + bytes(entries) + bytes(body))
    return path


if __name__ == "__main__":
    target = write_ico(Path(__file__).resolve().parents[1] / "assets" / "mot.ico")
    print(f"wrote {target} ({target.stat().st_size} bytes)")
