#!/usr/bin/env python3
"""`RTIM.T` — a level's textures, as blocks to be pushed into video memory.

    python3 tools/rtim.py 0            the blocks level 0 uploads
    python3 tools/rtim.py 0 vram       rebuild its VRAM and write out/vram_lv0.png
    python3 tools/rtim.py 0 page 7     one 64x256 texture page, as the GPU sees it

Not TIM files despite the name: 28 entries, one per level, each a run of

    s16 x, y, w, h        where in the 1024x512 framebuffer this goes
    s16 x, y, w, h        **the same rect a second time** -- a 16-byte header
    u16[w * h]            the halfwords themselves

which is what a game hands `LoadImage`. A 4-bit texture arrives as `w` a quarter
of its pixel width, since four pixels share a halfword, and a CLUT arrives as a
16x1 block of colours.

That makes the whole level's texture memory reconstructible offline: lay every
block into a 1024x512 buffer and the result is what the GPU samples when it
draws the tile models out of `RTMD.T` (FORMATS.md section 4).

`vram` writes that buffer straight out and it **looks like noise**, correctly:
four-bit indices shown as sixteen-bit colour cannot look like anything else. The
readable view is `page`, which expands one page through a CLUT. Level 0 page 7
with CLUT `0x7a00` — the one every primitive of tile model 174 asks for — comes
out as brickwork, cobble and rough clay.
"""
import os
import struct
import sys

sys.path.insert(0, "tools")
import tim                                                            # noqa: E402
from tarc import TArc                                                 # noqa: E402

RTIM = "extract/CD/COM/RTIM.T"
VW, VH = 1024, 512


def blocks(entry, path=RTIM):
    """Yield (x, y, w, h, halfwords) for every upload in the entry."""
    d = TArc(path).raw(entry)

    def rect(p):
        """A header is the rect written twice; that is what makes it findable."""
        if p + 16 > len(d) or d[p:p + 8] != d[p + 8:p + 16]:
            return None
        x, y, w, h = struct.unpack_from("<4h", d, p)
        if not (0 <= x and 0 <= y and 0 < w and 0 < h
                and x + w <= VW and y + h <= VH and p + 16 + w * h * 2 <= len(d)):
            return None
        return x, y, w, h

    p = 0
    while p < len(d):
        r = rect(p)
        if r is None:
            # blocks are padded to an alignment this does not need to know:
            # step to wherever the next doubled rect begins
            p += 4
            continue
        x, y, w, h = r
        yield x, y, w, h, d[p + 16:p + 16 + w * h * 2]
        p += 16 + w * h * 2


def vram(entry, path=RTIM):
    """The 1024x512 framebuffer this level's blocks build, as u16 per pixel."""
    buf = bytearray(VW * VH * 2)
    for x, y, w, h, data in blocks(entry, path):
        for row in range(h):
            off = ((y + row) * VW + x) * 2
            buf[off:off + w * 2] = data[row * w * 2:(row + 1) * w * 2]
    return buf


def png(buf, path, x=0, y=0, w=VW, h=VH):
    px = []
    for row in range(y, y + h):
        base = row * VW * 2
        for col in range(x, x + w):
            v = buf[base + col * 2] | (buf[base + col * 2 + 1] << 8)
            r, g, b = (v & 31) << 3, ((v >> 5) & 31) << 3, ((v >> 10) & 31) << 3
            px.append((r | r >> 5, g | g >> 5, b | b >> 5, 255))
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tim.write_png(path, w, h, px)
    return path


def page4(buf, tpage, clut):
    """A 4-bit texture page, expanded through its CLUT into RGBA pixels.

    `tpage` bits 0-3 are X in units of 64, bit 4 is Y in units of 256.
    `clut` is X in units of 16 and Y outright.
    """
    px0, py0 = (tpage & 0xF) * 64, ((tpage >> 4) & 1) * 256
    cx, cy = (clut & 0x3F) * 16, (clut >> 6) & 0x1FF
    pal = []
    for i in range(16):
        off = (cy * VW + cx + i) * 2
        v = buf[off] | (buf[off + 1] << 8)
        r, g, b = (v & 31) << 3, ((v >> 5) & 31) << 3, ((v >> 10) & 31) << 3
        pal.append((r | r >> 5, g | g >> 5, b | b >> 5, 0 if v == 0 else 255))
    out = []
    for row in range(256):
        for col in range(256):                    # 4bpp: 64 halfwords wide
            off = ((py0 + row) * VW + px0 + (col >> 2)) * 2
            v = buf[off] | (buf[off + 1] << 8)
            out.append(pal[(v >> (4 * (col & 3))) & 0xF])
    return out


if __name__ == "__main__":
    lv = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    what = sys.argv[2] if len(sys.argv) > 2 else "list"
    if what == "vram":
        p = png(vram(lv), f"out/vram_lv{lv:02d}.png")
        print("wrote", p)
    elif what == "page":
        tp = int(sys.argv[3], 0)
        cl = int(sys.argv[4], 0) if len(sys.argv) > 4 else 0x7A00
        os.makedirs("out/tex", exist_ok=True)
        out = f"out/tex/lv{lv:02d}_page{tp:02x}_clut{cl:04x}.png"
        tim.write_png(out, 256, 256, page4(vram(lv), tp, cl))
        print("wrote", out)
    else:
        n = tot = 0
        span = {}
        for x, y, w, h, _ in blocks(lv):
            n += 1
            tot += w * h * 2
            span[(y // 256, x // 64)] = span.get((y // 256, x // 64), 0) + 1
        print(f"RTIM.T[{lv}]: {n} blocks, {tot} bytes of video memory")
        print("blocks by 64x256 page:")
        for (py, pxx), c in sorted(span.items()):
            print(f"   page x{pxx:2d} y{py}   {c}")
