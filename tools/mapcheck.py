#!/usr/bin/env python3
"""Score our idea of where the walls are against the game's own map.

`ITEM.T` 721 is the level-0 map the game hands the player: 160x160 for an
80x80 grid, so exactly two pixels a cell, two colours, walls drawn as lines on
cell edges. That makes it ground truth we cannot get any other way, and this
harness exists to test wall predicates against it.

    python3 tools/mapcheck.py

**The per-edge score below is permissive and has misled once.** It counts a hit
when ink appears anywhere in the two-pixel band along an edge, and on a map this
densely drawn that is nearly always true, so a wrong predicate can score above
90 %. Use `agreement()` as well: it rasterises a prediction at the map's own
2px-per-cell scale and compares pixel for pixel, which is what caught a wall
decode that scored 90.6 % here and agreed with the map on 12 % of its ink.

What it already establishes:

  * the map is **Z-flipped** against our grid, the same way community maps are
    — that orientation scores 72 % recall where every other scores about 23 %;
  * **no cell field predicts the walls.** Void boundaries catch 9 % of the
    drawn edges, height changes 18 %, the `+9` bit 26 %, and a change in the
    tile shape id at `+8` 63 % at 40 % precision, which is the best of a poor
    field.

So walls are not a property of the cell. They live inside the **tile shapes**,
the variable-length records that `+8` indexes (FORMATS.md section 4), and this
harness is how a decode of those records gets checked.
"""
import struct
import sys
import zlib

sys.path.insert(0, "tools")
from maps import levels, cell, W, H                                  # noqa: E402

MAP0 = "out/ITEM/0721_0_160x160.png"


def read_png(path):
    """(width, height, rows) for a plain 8-bit RGBA PNG."""
    d = open(path, "rb").read()
    pos, idat, w, h = 8, b"", 0, 0
    while pos < len(d):
        n = struct.unpack(">I", d[pos:pos + 4])[0]
        kind = d[pos + 4:pos + 8]
        if kind == b"IHDR":
            w, h = struct.unpack(">II", d[pos + 8:pos + 16])
        elif kind == b"IDAT":
            idat += d[pos + 8:pos + 8 + n]
        pos += 12 + n
    raw = zlib.decompress(idat)
    bpp, stride, out = 4, w * 4, []
    prev, i = bytearray(stride), 0
    for _ in range(h):
        f = raw[i]
        i += 1
        line = bytearray(raw[i:i + stride])
        i += stride
        for x in range(stride):
            a = line[x - bpp] if x >= bpp else 0
            b = prev[x]
            c = prev[x - bpp] if x >= bpp else 0
            if f == 1:
                line[x] = (line[x] + a) & 255
            elif f == 2:
                line[x] = (line[x] + b) & 255
            elif f == 3:
                line[x] = (line[x] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc
                                      else b if pb <= pc else c)) & 255
        out.append(bytes(line))
        prev = line
    return w, h, out


def load(level=0, path=MAP0):
    w, h, px = read_png(path)
    grid = dict(levels())[level]

    def ink(x, y):
        return 0 <= x < w and 0 <= y < h and px[y][x * 4] > 20

    def C(x, z, off):
        return cell(grid, x, H - 1 - z, off)          # the map is Z-flipped
    return ink, C


def score(pred, ink, C):
    """(precision, recall) of a predicate over every cell edge."""
    def solid(x, z):
        return not (0 <= x < W and 0 <= z < H) or C(x, z, 8) == 255
    tp = fp = fn = 0
    for z in range(H - 1):
        for x in range(W - 1):
            edges = ((x + 1, z, any(ink(c, 2 * z + r)
                                    for c in (2 * x + 1, 2 * x + 2) for r in (0, 1))),
                     (x, z + 1, any(ink(2 * x + c, r)
                                    for r in (2 * z + 1, 2 * z + 2) for c in (0, 1))))
            for nx, nz, drawn in edges:
                p = pred(C, solid, x, z, nx, nz)
                tp += drawn and p
                fp += p and not drawn
                fn += drawn and not p
    return tp / max(tp + fp, 1), tp / max(tp + fn, 1), tp, fp, fn


def agreement(edges, ink, w=160, h=160):
    """Pixel-for-pixel overlap between a predicted wall set and the game's map.

    `edges` is an iterable of (cell x, cell z, dx, dz) in the map's own
    orientation. Returns (ours only, theirs only, agreeing).
    """
    mine = set()
    for x, z, dx, dz in edges:
        x0, y0 = x * 2, z * 2
        if dx:
            cx = x0 + (1 if dx > 0 else 0)
            mine |= {(cx, y0), (cx, y0 + 1)}
        else:
            cy = y0 + (0 if dz > 0 else 1)
            mine |= {(x0, cy), (x0 + 1, cy)}
    theirs = {(x, y) for y in range(h) for x in range(w) if ink(x, y)}
    return len(mine - theirs), len(theirs - mine), len(mine & theirs)


PREDICATES = {
    "neighbour is solid": lambda C, S, x, z, nx, nz: S(x, z) != S(nx, nz),
    "height differs": lambda C, S, x, z, nx, nz: (
        not S(x, z) and not S(nx, nz) and C(x, z, 6) != C(nx, nz, 6)),
    "+9 bit 0x40": lambda C, S, x, z, nx, nz: bool(
        (0 if S(x, z) else C(x, z, 9) & 0x40) or (0 if S(nx, nz) else C(nx, nz, 9) & 0x40)),
    "tile shape +8 differs": lambda C, S, x, z, nx, nz: (
        not S(x, z) and not S(nx, nz) and C(x, z, 8) != C(nx, nz, 8)),
}


if __name__ == "__main__":
    ink, C = load()
    print(f"{'predicate':24s} {'precision':>10s} {'recall':>8s}")
    for name, pred in PREDICATES.items():
        p, r, tp, fp, fn = score(pred, ink, C)
        print(f"  {name:22s} {p * 100:8.1f}% {r * 100:7.1f}%   tp{tp} fp{fp} fn{fn}")
