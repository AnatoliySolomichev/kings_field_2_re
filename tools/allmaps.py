#!/usr/bin/env python3
"""Every level, drawn with every object on it, straight from the disc.

    python3 tools/allmaps.py             out/maps/all/*.png and an index page
    python3 tools/allmaps.py 4           just level 4

No emulator and no snapshot: the terrain comes from `FDAT.T` entry `3n + 0` and
the objects from the placement block in `3n + 1` (`tools/placement.py`). Drawn
**north up**, which is the grid with Z flipped -- the same convention the
community maps and the game's own map use.

Walls are **not** drawn. A first decode of the tile shapes looked right by the
per-edge score in `tools/mapcheck.py` and was wrong: laid over the game's own
map pixel for pixel it agreed on 12 % of the ink. Terrain here is height and
void only, which is honest, until the shapes are read properly.

A readable object also gets a tick showing which way it faces, because the game
only shows its text when the player is looking at it -- so the facing is the
difference between a sign you can read and one you cannot find.

Objects are coloured by what the type table says they are, so a glance separates
the furniture from the things that do something:

    gold        the single class-0x20 type
    consumable  class 0x17
    container   class 0x16
    readable    type 299 -- a sign, a grave, a plaque
    interactive anything else with a class byte set
    scenery     class 0

The class byte comes from `object_types` in RAM, so a snapshot is used for it
when one exists; without one everything falls back to scenery and the map still
draws.
"""
import os
import sys

sys.path.insert(0, "tools")
import placement                                                     # noqa: E402
import tiles                                                         # noqa: E402
import tim                                                           # noqa: E402
from maps import levels, cell, W, H                                  # noqa: E402

OUT = "out/maps/all"
SCALE = 8
CELL = 2048

COLOURS = {
    "gold":        (255, 205, 70),
    "consumable":  (120, 230, 140),
    "container":   (235, 150, 60),
    "readable":    (110, 190, 255),
    "interactive": (230, 110, 130),
    "scenery":     (130, 125, 140),
}


def classes():
    """object type -> class byte, from a snapshot if we have one."""
    import glob
    import objects as O
    for p in sorted(glob.glob("out/snap/*.ram")):
        try:
            buf = open(p, "rb").read()
            out = {i: O.obj_class(buf, i) for i in range(O.NTYPES)}
            if any(out.values()):
                return out
        except OSError:
            continue
    return {}


def kind(t, cls):
    if t == placement.READABLE:
        return "readable"
    c = cls.get(t)
    if c == 0x20:
        return "gold"
    if c == 0x17:
        return "consumable"
    if c == 0x16:
        return "container"
    if c:
        return "interactive"
    return "scenery"


WALL_INK = (32, 28, 38, 255)


def draw_walls(px, w, h, grid, wl, scale):
    """One dark line along every cell side the tile shape declares as a wall."""
    for z in range(H):
        for x in range(W):
            for dx, dz in tiles.cell_walls(grid, wl, x, z, cell):
                # north up, so z is mirrored for display
                x0, y0 = x * scale, (H - 1 - z) * scale
                if dx:
                    cx = x0 + (scale - 1 if dx > 0 else 0)
                    for k in range(scale):
                        if 0 <= y0 + k < h and 0 <= cx < w:
                            px[(y0 + k) * w + cx] = WALL_INK
                else:
                    cy = y0 + (0 if dz > 0 else scale - 1)
                    for k in range(scale):
                        if 0 <= cy < h and 0 <= x0 + k < w:
                            px[cy * w + x0 + k] = WALL_INK


def draw(lv, grid, cls, scale=SCALE):
    from maps import render
    w, h, px = render(grid, scale)
    # walls are not drawn: the tile-shape decode that produced them agreed with
    # the game's own map on 12 % of its ink, so they were wrong. See FORMATS.md.
    rows = placement.objects(lv)
    for o in rows:
        col = COLOURS[kind(o["type"], cls)]
        # north up: the grid with Z flipped, for display only
        cx = int(o["x"] / CELL * scale)
        cy = int((H - 1 - o["z"] / CELL) * scale)
        k = kind(o["type"], cls)
        r = 2 if k == "scenery" else 4
        # a dark ring first, so a pale marker still reads against pale floor
        for dy in range(-r - 1, r + 2):
            for dx in range(-r - 1, r + 2):
                d = dx * dx + dy * dy
                x, y = cx + dx, cy + dy
                if not (0 <= x < w and 0 <= y < h):
                    continue
                if d <= r * r:
                    px[y * w + x] = col + (255,)
                elif d <= (r + 1) * (r + 1):
                    px[y * w + x] = (20, 18, 24, 255)
        if k == "readable":
            # which way it faces: the record's rotation, mirrored like the map
            import math
            ang = -o["rot"] / 4096 * 2 * math.pi
            for step in range(r + 1, r + 8):
                x = int(cx + math.sin(ang) * step)
                y = int(cy - math.cos(ang) * step)
                if 0 <= x < w and 0 <= y < h:
                    px[y * w + x] = col + (255,)
    return w, h, px, rows


def main(only=None):
    os.makedirs(OUT, exist_ok=True)
    cls = classes()
    grids = dict(levels())
    made = []
    for lv in sorted(grids):
        if only is not None and lv != only:
            continue
        w, h, px, rows = draw(lv, grids[lv], cls)
        path = f"{OUT}/level{lv:02d}.png"
        tim.write_png(path, w, h, px)
        made.append((lv, path, len(rows)))
        print(f"  level {lv:2d}: {len(rows):3d} objects -> {path}")
    if only is None and made:
        page = ["<title>King's Field II - every level</title>",
                "<style>body{background:#14141a;color:#d8d4cc;font:14px system-ui;"
                "margin:24px}h2{font-weight:600;margin:28px 0 8px}"
                "img{image-rendering:pixelated;border:1px solid #333;max-width:100%}"
                "div{display:inline-block;margin:0 18px 18px 0;vertical-align:top}"
                "span{color:#8a8694}</style>",
                "<h1>Every level, with every object</h1>",
                "<p><span>terrain from FDAT 3n+0, objects from the placement block "
                "in 3n+1, drawn north up</span></p>",
                "<p>" + "  ".join(
                    f"<b style='color:rgb{c}'>&#9679;</b> {k}" for k, c in COLOURS.items()) + "</p>"]
        for lv, path, n in made:
            rel = os.path.relpath(path, OUT)
            page.append(f"<div><h2>Level {lv} <span>{n} objects</span></h2>"
                        f"<img src='{rel}' width='420'></div>")
        open(f"{OUT}/index.html", "w").write("\n".join(page))
        print(f"\n{len(made)} maps -> {OUT}/index.html")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
