#!/usr/bin/env python3
"""`RTIM.T` — a level's textures, as blocks to be pushed into video memory.

    python3 tools/rtim.py 0            the blocks level 0 uploads
    python3 tools/rtim.py 0 vram       rebuild its VRAM and write out/vram_lv0.png
    python3 tools/rtim.py 0 page 7     one 64x256 texture page, as the GPU sees it
    python3 tools/rtim.py --check      the rebuilt VRAM against every snapshot

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

**Half of what the GPU samples is not in `RTIM.T` at all.** The objects'
pages, `0x0b` to `0x0f`, and a good part of the CLUT rows come from **`FDAT.T`
entry 96**, in exactly this format: `init_level_state` reads it once at game
start through `vram_stream` (`0x80018c60`, archive 4, entry 96), which queues
a request of type `0x40` (`0x80019e48`) whose buffer `res_upload_vram` feeds to
`LoadImage` block by block -- checking each header's doubled rect as it goes,
stopping at a zero size. `level_load` sends `RTIM.T[lv]` down the same path
(`vram_stream(3, lv)`), so a level's VRAM is **entry 96 first and the level's
own blocks on top**, which is what `level_vram` builds.

It had been looked for and not found, because the search took whole rows of a
page and the stream stores a page as 64x64-pixel squares. Against the
snapshots, the halfwords the two streams write match on 2 868 728 of 2 998 544,
and on the object pages 779 760 of 782 320 -- every one of the 2 560 left being
the water, which `texture_scroll_step` scrolls a row a frame (godot/scroll.gd).
The rest is the interface and whatever the game uploads as it runs.

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


def vram(entry, path=RTIM, buf=None):
    """The 1024x512 framebuffer these blocks build, as u16 per pixel.

    With `buf`, the blocks are laid over it rather than over nothing.
    """
    buf = bytearray(VW * VH * 2) if buf is None else buf
    for x, y, w, h, data in blocks(entry, path):
        for row in range(h):
            off = ((y + row) * VW + x) * 2
            buf[off:off + w * 2] = data[row * w * 2:(row + 1) * w * 2]
    return buf


FDAT = "extract/CD/COM/FDAT.T"
RESIDENT = 96          # the FDAT.T entry init_level_state streams at game start


SCROLL = 0x8009C214     # the rect game_main hands texture_scroll_add


def level_vram(lv):
    """What the GPU holds once level `lv` is loaded: entry 96, then RTIM.T[lv].

    And one MoveImage: `game_main` registers the water scroll with the rect at
    `SCROLL`, (1016, 96, 32, 32) in pixels, and `texture_scroll_add`
    (`0x800350fc`) copies that square to a stash 32 halfwords to its left,
    which is where `texture_scroll_step` rebuilds it from every frame. The
    square itself is left as the stream wrote it -- the scroll's offset 0.
    """
    import mips
    buf = vram(lv, RTIM, vram(RESIDENT, FDAT))
    x, y, w, h = struct.unpack("<4h", mips.load("game").bytes(SCROLL, 8))
    w >>= 2                                   # kind 1: four pixels a halfword
    for row in range(y, y + h):
        a = (row * VW + x) * 2
        buf[a - 0x40:a - 0x40 + w * 2] = buf[a:a + w * 2]
    return buf


def check():
    """The rebuilt VRAM against each snapshot, over what the streams write."""
    import glob
    written = bytearray(VW * VH)
    for x, y, w, h, _ in blocks(RESIDENT, FDAT):
        for row in range(h):
            written[(y + row) * VW + x:(y + row) * VW + x + w] = b"\1" * w
    total = [0, 0, 0, 0]
    for path in sorted(glob.glob("out/snap/*.vram")):
        ram = path[:-5] + ".ram"
        if not os.path.exists(ram):
            continue
        r = open(ram, "rb").read()
        if r[0x191A5C + 6] == 0:          # no level was ever loaded: no table
            continue
        lv = r[0x18FAD9]
        mine = written[:]
        for x, y, w, h, _ in blocks(lv):
            for row in range(h):
                mine[(y + row) * VW + x:(y + row) * VW + x + w] = b"\1" * w
        snap = open(path, "rb").read()
        model = level_vram(lv)
        idx = [i for i in range(VW * VH) if mine[i]]
        ok = sum(1 for i in idx if snap[2 * i:2 * i + 2] == model[2 * i:2 * i + 2])
        obj = [i for i in idx if (i % VW) >= 704 and i // VW < 256]
        ok_obj = sum(1 for i in obj if snap[2 * i:2 * i + 2] == model[2 * i:2 * i + 2])
        print(f"{os.path.basename(path)}  level {lv}: {ok} of {len(idx)} halfwords "
              f"match; the object pages 0x0b-0x0f {ok_obj} of {len(obj)}")
        total = [total[0] + ok, total[1] + len(idx), total[2] + ok_obj,
                 total[3] + len(obj)]
    print(f"over every snapshot: {total[0]} of {total[1]} halfwords, the object "
          f"pages {total[2]} of {total[3]}")


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
    if sys.argv[1:2] == ["--check"]:
        check()
        sys.exit(0)
    lv = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    what = sys.argv[2] if len(sys.argv) > 2 else "list"
    if what == "vram":
        p = png(level_vram(lv), f"out/vram_lv{lv:02d}.png")
        print("wrote", p)
    elif what == "page":
        tp = int(sys.argv[3], 0)
        cl = int(sys.argv[4], 0) if len(sys.argv) > 4 else 0x7A00
        os.makedirs("out/tex", exist_ok=True)
        out = f"out/tex/lv{lv:02d}_page{tp:02x}_clut{cl:04x}.png"
        tim.write_png(out, 256, 256, page4(level_vram(lv), tp, cl))
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
