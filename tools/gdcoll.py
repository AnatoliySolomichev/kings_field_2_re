#!/usr/bin/env python3
"""Export a level's collision so an engine can run the game's own model.

    python3 tools/gdcoll.py 0 out/godot

Writes `coll00.json`: the grid's collision fields per cell, and the tile shapes
they index, as instruction lists. `collision.gd` in the Godot project is a
transcription of `tools/collision.py`, which is itself a transcription of
`tile_collision` — so the engine ends up asking the same question the
PlayStation did and getting the same answer.

Handing the drawn mesh to a physics body is not the same thing and gets four
things visibly wrong: you cannot walk up a ramp, cannot step over a low wall,
cannot climb stairs, and do not fall into water. Every one of those is a
property of this model rather than of the geometry.

**Both layers are exported**, six fields per cell rather than three. A cell is
two five-byte records and `0x800324f0` picks between them by the height of the
query — so a bridge over a room needs both, and exporting only the second one
put the floor of the lower room under a player standing on the upper.

The player's own numbers are read off the code rather than fitted: **radius
0x320 = 800** and **body height 0x6a4 = 1700**, literals in both `player_move`
(`0x8002f398`, `0x8002f328`) and `player_vertical` (`0x8002ed64`, `0x8002ed94`).
The earlier pair reached the same values by a much longer route.

It also writes `movecheck00.json`: frames of `tools/movement.py`, so that
`selftest.gd` can prove the GDScript copy of the movement did not drift from the
Python one.
"""
import json
import os
import sys

sys.path.insert(0, "tools")
import collision as coll                                              # noqa: E402
import movement                                                       # noqa: E402
import tiles                                                          # noqa: E402

W, CELLB = 80, 10
PLAYER_RADIUS, PLAYER_BODY = 0x320, 0x6A4


def export(lv, out="out/godot"):
    lvl = coll.Level(lv)
    used = set()
    cells = []
    for cz in range(W):
        for cx in range(W):
            c = lvl.cell(cx, cz)
            for layer in (0, 5):
                sid = c[layer + 3]
                if sid != 255:
                    used.add(sid)
                cells += [sid, c[layer + 2] & 3, c[layer + 1]]

    shapes = {}
    tail, offs = tiles.table(lv)
    for sid in sorted(used):
        hdr, ins = tiles.shape(tail, offs[sid])
        if hdr is None:
            continue
        shapes[str(sid)] = {
            "scale": hdr[2],
            "ins": [[op, [coll.s16(a) for a in args]] for op, args in ins],
        }

    doc = {
        "level": lv, "w": W, "cell": 0x800, "unit": 1000,
        "radius": PLAYER_RADIUS, "body": PLAYER_BODY,
        "cells": cells, "shapes": shapes,
        # The game's own square root table. It is here because the walking step
        # is speed^2 / isqrt(speed^2) and this root is a unit short on a perfect
        # square, so a port using an exact one walks at the wrong speed.
        "isqrt": list(movement._isqrt_table()),
        # And its trigonometry: one quarter wave, reflected four ways. The step
        # is a product shifted right by 12, so a rounding difference between
        # this and a float sine lands in the position as a whole unit.
        "sin": list(movement._table()),
    }
    os.makedirs(out, exist_ok=True)
    path = f"{out}/coll{lv:02d}.json"
    with open(path, "w") as f:
        json.dump(doc, f, separators=(",", ":"))
    print(f"collision data: {len(used)} shapes, {W * W} cells, "
          f"{os.path.getsize(path) // 1024} KB -> {path}")
    movecheck(lv, lvl, out)
    return path


# Where the player actually stands on level 0, out of a RAM snapshot. Anything
# invented would only prove the two transcriptions agree about empty rock.
START = {0: (95937, -14307, 55151)}


def movecheck(lv, lvl, out="out/godot"):
    """Frames of `tools/movement.py`, for `selftest.gd` to reproduce.

    The Godot copy of the movement is a transcription of a transcription, and
    the only way to know the second one did not drift is to make both run the
    same frames and compare the numbers. Each scenario fixes the horizontal
    step and lets `player_vertical` own the height, which is the half that has
    been wrong twice now.
    """
    start = START.get(lv)
    if start is None:
        return None
    runs = []
    for name, dx, dz, drop, n in (("drop", 0, 0, 0x1800, 90),
                                  ("east", 78, 0, 0, 150),
                                  ("west", -78, 0, 0, 150),
                                  ("north", 0, -78, 0, 150),
                                  ("south", 0, 78, 0, 150)):
        p0 = (start[0], start[1] - drop, start[2])
        p, state, vel = p0, 0, 0
        frames = []
        for _ in range(n):
            p, state, vel = movement.walk_step(lvl, p, dx, dz, state, vel)
            frames.append([p[0], p[1], p[2], state, vel])
        runs.append({"name": name, "start": list(p0), "d": [dx, dz],
                     "frames": frames})
    doc = {"level": lv, "runs": runs}
    path = f"{out}/movecheck{lv:02d}.json"
    with open(path, "w") as f:
        json.dump(doc, f, separators=(",", ":"))
    print(f"movement reference: {len(runs)} runs, "
          f"{sum(len(r['frames']) for r in runs)} frames -> {path}")
    anglecheck(out)
    dircheck(out)
    return path


def dircheck(out="out/godot", n=400):
    """Angle pairs for `selftest.gd` to put through `direction_from_angles`.

    Like `anglecheck`, this holds two copies of one reading together and
    claims nothing more. What makes it worth having is the 16-bit truncation
    between the two rotation stages: it is easy to port a rotation and get
    that wrong, and the answer then differs by one unit in a place nothing
    else would notice.
    """
    import random
    rnd = random.Random(23)
    rows = []
    for _ in range(n):
        p = rnd.randint(-0x1000, 0x1000)
        y = rnd.randint(-0x1000, 0x1000)
        rows.append([p, y, list(movement.direction_from_angles(p, y))])
    path = f"{out}/dircheck.json"
    with open(path, "w") as f:
        json.dump(rows, f, separators=(",", ":"))
    return path


def anglecheck(out="out/godot", n=400):
    """Directions for `selftest.gd` to put through the game's arctangent.

    `vec_angle` is a transcription of a transcription like the movement is,
    and it has no recording behind it -- nothing in this repository has ever
    logged a call to it. What can still be checked is that the two copies agree
    exactly, which is what this is for; that they are both *right* rests on the
    CORDIC table matching atan(2**-i) and on the answers tracking atan2 to
    within the table's own rounding.
    """
    import random
    rnd = random.Random(11)
    rows = []
    for _ in range(n):
        u = rnd.randint(-100000, 100000)
        v = rnd.randint(-100000, 100000)
        rows.append([u, v, movement.vec_angle(u, v)])
    path = f"{out}/anglecheck.json"
    with open(path, "w") as f:
        json.dump(rows, f, separators=(",", ":"))
    return path
