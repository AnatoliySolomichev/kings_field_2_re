#!/usr/bin/env python3
"""Render the King's Field II level grids from FDAT.T.

Each level occupies three consecutive FDAT entries:
  [n+0] 4-byte header, an 80x80 grid of 10-byte cells (64000 bytes), then a
        table of 254 offsets into variable-length event scripts;
  [n+1] a table of 120-byte entity records;
  [n+2] a pointer block relocated to 0x801e8xxx.

Cell bytes that carry information: [5] and [8] are 255 in solid rock, [6] is a
height (100 at the base level) and [7] is a small enum.
"""
import sys

sys.path.insert(0, "tools")
from tarc import TArc          # noqa: E402
import tim                     # noqa: E402

CELL, W, H = 10, 80, 80
GRID = CELL * W * H


def levels(path="extract/CD/COM/FDAT.T"):
    """Yield (index, grid bytes) for every populated level."""
    t = TArc(path)
    for n in range(0, 84, 3):
        raw = t.raw(n)
        if len(raw) < 4 + GRID:
            continue
        yield n // 3, raw[4:4 + GRID]


def cell(grid, x, y, off):
    return grid[(y * W + x) * CELL + off]


def render(grid, scale=4):
    """Solid rock dark, walkable floor shaded by its height byte."""
    heights = [cell(grid, x, y, 6) for y in range(H) for x in range(W)
               if cell(grid, x, y, 8) != 255]
    lo, hi = (min(heights), max(heights)) if heights else (0, 1)
    rng = max(hi - lo, 1)
    px = []
    for row in range(H * scale):
        y = row // scale
        for col in range(W * scale):
            x = col // scale
            if cell(grid, x, y, 8) == 255:
                px.append((24, 22, 30, 255))            # solid
            else:
                t = (cell(grid, x, y, 6) - lo) / rng
                g = int(90 + 150 * t)
                px.append((g, int(g * 0.93), int(g * 0.78), 255))
    return W * scale, H * scale, px


def sheet(items, path, cols=6, scale=2, pad=4):
    tw, th = W * scale, H * scale
    gw, gh = tw + pad * 2, th + pad * 2
    rows = (len(items) + cols - 1) // cols
    Wp, Hp = cols * gw, rows * gh
    out = [(12, 12, 16, 255)] * (Wp * Hp)
    for k, (idx, grid) in enumerate(items):
        w, h, px = render(grid, scale)
        ox, oy = (k % cols) * gw + pad, (k // cols) * gh + pad
        for y in range(h):
            for x in range(w):
                out[(oy + y) * Wp + ox + x] = px[y * w + x]
    tim.write_png(path, Wp, Hp, out)
    return Wp, Hp


if __name__ == "__main__":
    import os
    os.makedirs("out/maps", exist_ok=True)
    got = list(levels())
    for idx, grid in got:
        w, h, px = render(grid)
        tim.write_png(f"out/maps/level{idx:02d}.png", w, h, px)
        walk = sum(1 for y in range(H) for x in range(W) if cell(grid, x, y, 8) != 255)
        print(f"level {idx:2d}: {walk:5d} walkable cells of {W*H}")
    print("sheet:", sheet(got, "out/maps/all.png"))
