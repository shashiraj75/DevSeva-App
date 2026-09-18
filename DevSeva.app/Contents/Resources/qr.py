# DevSeva — © 2026 Raviraj Shetty. All rights reserved.
"""QR codes for phone access (offline). Uses the bundled MIT-licensed qrcodegen by Project Nayuki."""
import struct
import zlib
from urllib.parse import quote
from qrcodegen import QrCode


def access_link(scheme, host, port, code):
    """Legacy link format retained for existing printed QR sheets."""
    return f'{scheme}://{host}:{port}/#code={quote(code)}'


def android_access_link(scheme, host, port, code):
    """QR link format that survives Android camera handoff to Chrome."""
    return f'{scheme}://{host}:{port}/?code={quote(code)}'


def matrix(text):
    qr = QrCode.encode_text(text, QrCode.Ecc.MEDIUM)
    return [[qr.get_module(x, y) for x in range(qr.get_size())] for y in range(qr.get_size())]


def png(text, scale=8, border=4):
    """Black-on-white PNG bytes (crisp, no smoothing)."""
    grid = matrix(text)
    size = (len(grid) + 2 * border) * scale
    rows = []
    white = b'\xff'
    for y in range(size):
        gy = y // scale - border
        line = bytearray(b'\x00')
        for x in range(size):
            gx = x // scale - border
            dark = 0 <= gy < len(grid) and 0 <= gx < len(grid) and grid[gy][gx]
            line += b'\x00' if dark else white
        rows.append(bytes(line))

    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    header = struct.pack('>IIBBBBB', size, size, 8, 0, 0, 0, 0)  # 8-bit greyscale
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header) + chunk(b'IDAT', zlib.compress(b''.join(rows), 9)) + chunk(b'IEND', b'')


def photo(tk_module, master, text, pixels=300, border=4):
    """A Tk PhotoImage of the QR code, about `pixels` wide."""
    grid = matrix(text)
    cells = len(grid) + 2 * border
    scale = max(2, pixels // cells)
    image = tk_module.PhotoImage(master=master, width=cells, height=cells)
    rows = []
    for y in range(cells):
        gy = y - border
        rows.append('{' + ' '.join('#000000' if 0 <= gy < len(grid) and 0 <= x - border < len(grid) and grid[gy][x - border]
                                   else '#ffffff' for x in range(cells)) + '}')
    image.put(' '.join(rows))
    return image.zoom(scale, scale)
