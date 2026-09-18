# DevSeva — © 2026 Raviraj Shetty. All rights reserved.
"""DevSeva app icon (a lit diya on maroon), drawn in code so no image files are needed.

Used for the phone "Add to Home Screen" icon on iPhone and Android.
"""
import math
import struct
import zlib
from functools import lru_cache
from pathlib import Path

MAROON = (122, 46, 14)
SAFFRON = (229, 138, 0)
BOWL_DARK = (176, 88, 10)
FLAME_OUT = (255, 170, 30)
FLAME_IN = (255, 236, 150)
GLOW = (255, 196, 90)


def _mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _colour(x, y, maskable):
    """x, y in 0..1 (y downwards). Returns (r, g, b, a)."""
    # Background: full square for maskable icons (Android crops it), rounded square otherwise.
    if not maskable:
        r = 0.2
        cx, cy = min(max(x, r), 1 - r), min(max(y, r), 1 - r)
        if (x - cx) ** 2 + (y - cy) ** 2 > r * r:
            return (0, 0, 0, 0)
    scale = 0.78 if maskable else 1.0  # keep the drawing inside Android's safe zone
    u = (x - 0.5) / scale + 0.5
    v = (y - 0.5) / scale + 0.5
    colour = _mix(MAROON, (150, 60, 20), max(0.0, 1 - v) * 0.5)
    # soft glow around the flame
    d = math.hypot(u - 0.5, v - 0.40)
    if d < 0.32:
        colour = _mix(colour, GLOW, (1 - d / 0.32) ** 2 * 0.35)
    # bowl: lower half of an ellipse with a flat rim
    bx, by, bw, bh = 0.5, 0.60, 0.30, 0.17
    if v >= by and ((u - bx) / bw) ** 2 + ((v - by) / bh) ** 2 <= 1:
        shade = (u - (bx - bw)) / (2 * bw)
        colour = _mix(SAFFRON, BOWL_DARK, abs(shade - 0.35) * 1.2)
    if abs(v - by) < 0.018 and abs(u - bx) < bw * 1.02:
        colour = (255, 190, 80)
    # foot of the lamp
    if 0.76 <= v <= 0.80 and abs(u - bx) < 0.12:
        colour = BOWL_DARK
    # flame: teardrop (circle at the bottom, tapering to a point on top)
    fx, fy, fr, top = 0.5, 0.47, 0.085, 0.20
    if top <= v <= fy + fr:
        if v >= fy:
            inside = math.hypot(u - fx, v - fy) <= fr
            inner = math.hypot(u - fx, (v - fy) * 1.2) <= fr * 0.55
        else:
            t = (fy - v) / (fy - top)
            half = fr * math.cos(t * math.pi / 2) ** 1.2 * (1 + 0.15 * math.sin(t * math.pi))
            inside = abs(u - fx) <= half
            inner = abs(u - fx) <= half * 0.5 and t < 0.6
        if inside:
            colour = FLAME_IN if inner else FLAME_OUT
    return colour + (255,)


@lru_cache(maxsize=8)
def png(size=180, maskable=False):
    """Return the current DevSeva logo for phone/PWA branding."""
    logo = Path(__file__).with_name('assets') / 'devseva-logo.png'
    if logo.exists():
        return logo.read_bytes()
    samples = ((0.25, 0.25), (0.75, 0.25), (0.25, 0.75), (0.75, 0.75))
    rows = []
    for py in range(size):
        row = bytearray(b'\x00')
        for px in range(size):
            acc = [0, 0, 0, 0]
            for sx, sy in samples:
                c = _colour((px + sx) / size, (py + sy) / size, maskable)
                acc[0] += c[0] * c[3]
                acc[1] += c[1] * c[3]
                acc[2] += c[2] * c[3]
                acc[3] += c[3]
            alpha = acc[3] / 4
            if acc[3]:
                row += bytes((int(acc[0] / acc[3]), int(acc[1] / acc[3]), int(acc[2] / acc[3]), int(alpha)))
            else:
                row += b'\x00\x00\x00\x00'
        rows.append(bytes(row))

    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    header = struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header) + chunk(b'IDAT', zlib.compress(b''.join(rows), 9))
            + chunk(b'IEND', b''))


def manifest():
    return {
        'name': 'DevSeva — temple counter',
        'short_name': 'DevSeva',
        'description': 'Seva bookings and event-day counter, connected to the DevSeva laptop on this Wi-Fi.',
        'start_url': '/',
        'scope': '/',
        'display': 'standalone',
        'orientation': 'portrait',
        'background_color': '#f6efe4',
        'theme_color': '#7a2e0e',
        'icons': [
            {'src': '/icon-192.png', 'sizes': '192x192', 'type': 'image/png', 'purpose': 'any'},
            {'src': '/icon-512.png', 'sizes': '512x512', 'type': 'image/png', 'purpose': 'any'},
            {'src': '/icon-512-maskable.png', 'sizes': '512x512', 'type': 'image/png', 'purpose': 'maskable'},
        ],
    }


# Desktop emblem derived from the supplied DevSeva logo. Embedded so the
# existing standalone build includes the artwork without external file paths.
_DESKTOP_LOGOS = {
    28: (
        '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'
    ),
    44: (
        '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'
        'RU5ErkJggg=='
    ),
    96: (
        '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'
        'RU5ErkJggg=='
    ),
}


def desktop_png(size):
    """Transparent desktop branding at native display sizes."""
    import base64
    return base64.b64decode(_DESKTOP_LOGOS[size])
