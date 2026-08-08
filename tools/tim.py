#!/usr/bin/env python3
"""PlayStation TIM image decoder + scanner for embedded TIMs in a blob."""
import struct

TIM_ID = 0x10


def _rgb(v):
    r = (v & 0x1F) << 3
    g = ((v >> 5) & 0x1F) << 3
    b = ((v >> 10) & 0x1F) << 3
    a = 0 if (v == 0) else 255          # pure 0 = fully transparent in PSX
    return (r | r >> 5, g | g >> 5, b | b >> 5, a)


def parse(buf, pos=0):
    """Parse one TIM at `pos`. Returns (width, height, pixels RGBA, nextpos) or None."""
    if pos + 8 > len(buf):
        return None
    ident, flags = struct.unpack_from("<II", buf, pos)
    if ident != TIM_ID or (flags & ~0x0F) != 0:
        return None
    pmode = flags & 7
    hasclut = bool(flags & 8)
    if pmode > 3:
        return None
    p = pos + 8
    cluts = []
    if hasclut:
        if p + 12 > len(buf):
            return None
        bnum, cx, cy, cw, ch = struct.unpack_from("<IHHHH", buf, p)
        if bnum < 12 or p + bnum > len(buf) or cw == 0 or ch == 0:
            return None
        raw = buf[p + 12:p + bnum]
        for i in range(ch):
            row = struct.unpack_from("<%dH" % cw, raw, i * cw * 2)
            cluts.append([_rgb(v) for v in row])
        p += bnum
    if p + 12 > len(buf):
        return None
    bnum, dx, dy, w, h = struct.unpack_from("<IHHHH", buf, p)
    if bnum < 12 or p + bnum > len(buf) or w == 0 or h == 0 or h > 4096:
        return None
    data = buf[p + 12:p + bnum]
    nxt = p + bnum

    if pmode == 0:
        width = w * 4
        pal = cluts[0] if cluts else [(i * 17,) * 3 + (255,) for i in range(16)]
        px = []
        for i in range(width * h // 2):
            if i >= len(data):
                break
            b = data[i]
            px.append(pal[b & 15])
            px.append(pal[b >> 4])
    elif pmode == 1:
        width = w * 2
        pal = cluts[0] if cluts else [(i,) * 3 + (255,) for i in range(256)]
        px = [pal[b] if b < len(pal) else (0, 0, 0, 0) for b in data[:width * h]]
    elif pmode == 2:
        width = w
        px = [_rgb(v) for v in struct.unpack_from("<%dH" % (width * h), data, 0)]
    else:  # 24bpp
        width = (w * 2) // 3
        px = [(data[i], data[i + 1], data[i + 2], 255)
              for i in range(0, width * h * 3, 3)]

    px += [(0, 0, 0, 0)] * (width * h - len(px))
    return width, h, px[:width * h], nxt, (dx, dy), cluts


def scan(buf):
    """Find every TIM in a blob. Yields (offset, result)."""
    pos = 0
    n = len(buf)
    while pos + 8 <= n:
        if buf[pos] == TIM_ID and buf[pos + 1] == 0 and buf[pos + 2] == 0 and buf[pos + 3] == 0:
            r = parse(buf, pos)
            if r:
                yield pos, r
                pos = r[3]
                continue
        pos += 4


def write_png(path, w, h, px):
    """Minimal RGBA PNG writer (no external deps)."""
    import zlib
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        for x in range(w):
            raw.extend(px[y * w + x])
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(bytes(raw), 6))
           + chunk(b"IEND", b""))
    open(path, "wb").write(png)
