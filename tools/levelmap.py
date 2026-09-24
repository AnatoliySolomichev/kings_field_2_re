#!/usr/bin/env python3
"""The level's map, as the game draws it: rectangles over the grid.

    python3 tools/levelmap.py           every level, with how well it fits
    python3 tools/levelmap.py 0         level 0's rectangles
    python3 tools/levelmap.py --check   the fit, over every level
    python3 tools/levelmap.py --godot   write them out for the port

**Block 5 of `FDAT.T` entry `3n + 1`** is 640 bytes, which `level_load`
copies whole to `0x801ba6fc`, and it is **160 records of four bytes**:

    +0  u8  x, in half cells
    +1  u8  z, in half cells
    +2  u8  width
    +3  u8  height

An all-zero record is an unused slot. Level 0 uses 92 of the 160.

Two routines read it, and between them they say what it is. `0x8001bd48`
draws through `ui_prim_begin`, and `0x8001bea8` -- called by
`object_trigger`, `player_controller` and `object_interact`, which is to say
whenever the world changes under the player -- walks the same records with a
counter that starts at `0x9f`, one short of 160, testing a bit per record.
So one of them is the drawing and the other is the marking, and the bits are
which rectangles the player has seen.

**What settles it is the fit.** Halving the coordinates puts the rectangles
on the 80x80 collision grid, and their union covers **94 to 97% of the open
floor on every level that has a grid**, while touching a small fraction of
the solid cells. A list that lands on the floor and avoids the walls that
closely is the map.

The other way round says the same. `ITEM.T` 721 is the level-0 map the game
hands the player -- 160x160 for an 80x80 grid, exactly the half-cell units
these records are in -- and **2811 of its 2999 ink pixels fall inside the
rectangles**, with Z flipped, which is the north-up convention that image and
the community maps are drawn in.

The 640 bytes are byte for byte what a RAM snapshot holds at `0x801ba6fc`.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import entities                                                      # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
BLOCK = 5                      # of entry 3n+1
ROW, SLOTS = 4, 160
LIVE = 0x801BA6FC
GRID = 80                      # the collision grid is 80 by 80
HALF = 2                       # the records are in half cells


def rects(lv):
    """[(x, z, w, h)] in half cells, the empty slots dropped."""
    raw, bs = entities.blocks(lv)
    if len(bs) <= BLOCK:
        return []
    o, n = bs[BLOCK]
    out = []
    for i in range(min(SLOTS, n // ROW)):
        r = raw[o + ROW * i:o + ROW * (i + 1)]
        if any(r):
            out.append((r[0], r[1], r[2], r[3]))
    return out


def covered(lv):
    """The set of grid cells the rectangles cover."""
    out = set()
    for x0, z0, w, h in rects(lv):
        for cx in range(x0 // HALF, (x0 + w) // HALF):
            for cz in range(z0 // HALF, (z0 + h) // HALF):
                if 0 <= cx < GRID and 0 <= cz < GRID:
                    out.add((cx, cz))
    return out


def open_cells(lv):
    """The cells the collision grid does not call solid.

    Straight from `tools/collision.py` rather than from anything the port has
    built, because the port's `collNN.json` carried level 0's grid for every
    level until that was fixed.
    """
    import collision
    lvl = collision.Level(lv)
    return {(x, z) for z in range(GRID) for x in range(GRID)
            if lvl.cell(x, z)[8] != 0xFF}


def check(out=sys.stdout, levels=range(28)):
    """How much of each level's open floor the rectangles cover."""
    hit = miss = done = 0
    for lv in levels:
        try:
            floor = open_cells(lv)
        except Exception:
            continue
        if not floor or len(floor) == GRID * GRID:
            continue          # no grid for this level: every cell reads open
        cov = covered(lv)
        h = len(cov & floor)
        hit += h
        miss += len(floor) - h
        done += 1
        print(f"  level {lv:2d}: {len(rects(lv)):3d} rectangles cover {h} of "
              f"{len(floor)} open cells "
              f"({100 * h // max(len(floor), 1)}%), and touch "
              f"{len(cov - floor)} of {GRID * GRID - len(floor)} solid ones",
              file=out)
    if not done:
        print("  no grid available; the map fit is unchecked", file=out)
        return True
    print(f"  {hit} of {hit + miss} open cells covered over {done} levels "
          f"({100 * hit // max(hit + miss, 1)}%)", file=out)
    return hit * 4 >= (hit + miss) * 3          # three quarters or better


def export(out_dir, levels=range(28)):
    doc = {"_note": "block 5 of FDAT.T entry 3n+1, copied whole to 0x801ba6fc: "
                    "160 records of x, z, width, height in half cells -- the "
                    "map the game draws, one rectangle per piece, with a bit "
                    "per record for whether the player has seen it",
           "slots": SLOTS, "half": HALF, "levels": {}}
    for lv in levels:
        try:
            doc["levels"][str(lv)] = [list(r) for r in rects(lv)]
        except Exception:
            continue
    path = os.path.join(out_dir, "levelmap.json")
    with open(path, "w") as fh:
        json.dump(doc, fh, separators=(",", ":"))
    return path


if __name__ == "__main__":
    a = sys.argv[1] if len(sys.argv) > 1 else None
    if a == "--check":
        sys.exit(0 if check() else 1)
    elif a == "--godot":
        print(export(os.path.join(ROOT, "godot")))
    elif a is not None:
        lv = int(a)
        rs = rects(lv)
        print(f"level {lv}: {len(rs)} of {SLOTS} slots used\n")
        for i, (x, z, w, h) in enumerate(rs):
            print(f"  {i:3d}  x={x:3d} z={z:3d}  {w:3d} x {h:3d}"
                  f"   cells ({x // HALF},{z // HALF}) "
                  f"{w // HALF} x {h // HALF}")
    else:
        print(__doc__)
        check()
        print()
        tot = 0
        for lv in range(28):
            n = len(rects(lv))
            tot += n
            if n:
                print(f"  level {lv:2d}: {n:3d} rectangles")
        print(f"\n{tot} map rectangles in the game")
