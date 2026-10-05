#!/usr/bin/env python3
"""GAME.EXE's small routines asked by GAME.EXE itself, for the port's copies.

    python3 tools/routines.py          each routine: how many calls, and a few

The port carries its own copies of the game's arithmetic -- the sine table,
the square root that comes back one short on a square, the bearings, the
range tests -- and most of them are held to the game only through what they
add up to: a creature's step, a door's swing. This asks the routines
themselves. `tools/mipsrun.py` runs each over a snapshot's RAM (the code is
in it) on a few hundred inputs drawn from a fixed seed -- the corners too:
zeros, signs, the octant edges, the limits of a range -- and writes what the
game answered to `routinecheck.json`, which `godot/selftest.gd` puts to the
port's functions one call at a time.

What takes a pointer is given one: the position or the angles are written to
a scratch area of RAM first. `player_in_rect` reads the player's position from
`player_pos`, so that is written too.
"""
import json
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SNAP = "a1"
SCRATCH = 0x801FF000          # above the stack mipsrun runs on
PLAYER_POS = 0x801B25F0

GAME_SIN, GAME_COS = 0x80076CC4, 0x80076DA0
ARCTAN_UNIT, VEC_ANGLE, RATAN2 = 0x800742AC, 0x80016AB8, 0x80074380
GAME_ISQRT = 0x80074508
IN_RANGE, IN_ORIENTED_RECT = 0x80016EC8, 0x80016D3C
FACING_TEST, APPROACH, FIXED_MADD = 0x80016A2C, 0x80015FDC, 0x80017158
PLAYER_IN_RECT = 0x80046884


def s32(v):
    v &= 0xFFFFFFFF
    return v - 0x100000000 if v & 0x80000000 else v


def _pos(cpu, at, p):
    for i, v in enumerate(p):
        cpu.wr(at + 4 * i, 4, v & 0xFFFFFFFF)


def cases(n=300, snap=SNAP):
    """{routine: [[args..., the game's answer], ...]}."""
    import mipsrun
    path = os.path.join(ROOT, "out", "snap", snap + ".ram")
    if not os.path.exists(path):
        return {}
    cpu = mipsrun.CPU(open(path, "rb").read())
    rng = random.Random(0x4B4632)
    out = {}

    def call(addr, *args):
        return s32(cpu.call(addr, *[a & 0xFFFFFFFF for a in args]))

    # the circle: every angle once, and some outside it either way
    angles = list(range(0x1000)) + [rng.randrange(-0x8000, 0x8000) for _ in range(n)]
    out["game_sin"] = [[a, call(GAME_SIN, a)] for a in angles]
    out["game_cos"] = [[a, call(GAME_COS, a)] for a in angles]
    out["arctan_unit"] = [[r, call(ARCTAN_UNIT, r)]
                          for r in list(range(0, 0x1001, 16)) + [rng.randrange(0, 0x1001) for _ in range(n)]]

    def pair(lim):
        k = rng.randrange(6)
        if k == 0:
            return 0, rng.randrange(-lim, lim)
        if k == 1:
            return rng.randrange(-lim, lim), 0
        if k == 2:
            v = rng.randrange(-lim, lim)
            return v, v * rng.choice((1, -1))
        return rng.randrange(-lim, lim), rng.randrange(-lim, lim)
    vecs = [pair(0x10000) for _ in range(n)] + [pair(0x400) for _ in range(n)] + [(0, 0)]
    out["vec_angle"] = [[u, v, call(VEC_ANGLE, u, v)] for u, v in vecs]
    out["ratan2"] = [[y, x, call(RATAN2, y, x)] for y, x in vecs]
    roots = [0, 1, 2, 3, 4, 40000, 0x7FFFFFFF] + [rng.randrange(0, 1 << rng.randrange(1, 31))
                                                  for _ in range(n * 2)]
    out["game_isqrt"] = [[x, call(GAME_ISQRT, x)] for x in roots]

    rows = []
    for _ in range(n * 2):
        p = (rng.randrange(-0x20000, 0x20000), rng.randrange(-0x8000, 0x2000),
             rng.randrange(-0x20000, 0x20000))
        r = rng.randrange(0, 0x2000)
        q = (p[0] + rng.randrange(-r - 0x400, r + 0x400), p[1] + rng.randrange(-0x1000, 0x1000),
             p[2] + rng.randrange(-r - 0x400, r + 0x400))
        top, own = rng.randrange(0, 0x1000), rng.randrange(0, 0x1000)
        if rng.randrange(8) == 0:
            q = (q[0], 0xFFFF, q[2])                    # the height test skipped
        _pos(cpu, SCRATCH, p)
        rows.append([*p, *q, r, top, own,
                     call(IN_RANGE, SCRATCH, q[0], q[1], q[2], r, top, own)])
    out["in_range"] = rows

    rows = []
    for _ in range(n * 2):
        p = (rng.randrange(-0x20000, 0x20000), rng.randrange(-0x8000, 0x2000),
             rng.randrange(-0x20000, 0x20000))
        a, b = rng.randrange(0x40, 0x1000), rng.randrange(0x40, 0x1000)
        q = (p[0] + rng.randrange(-0x1400, 0x1400), p[1] + rng.randrange(-0x1000, 0x1000),
             p[2] + rng.randrange(-0x1400, 0x1400))
        ang = rng.randrange(0, 0x1000)
        top, own = rng.randrange(0, 0x1000), rng.randrange(0, 0x1000)
        if rng.randrange(8) == 0:
            q = (q[0], 0xFFFF, q[2])                    # the height test skipped
        _pos(cpu, SCRATCH, p)
        cpu.wr(SCRATCH + 0x10, 2, 0)
        cpu.wr(SCRATCH + 0x12, 2, ang)
        cpu.wr(SCRATCH + 0x14, 2, 0)
        rows.append([ang, *p, *q, a, b, top, own,
                     call(IN_ORIENTED_RECT, SCRATCH + 0x10, SCRATCH, q[0], q[1], q[2],
                          a, b, top, own)])
    out["in_oriented_rect"] = rows

    out["facing_test"] = [[a, b, t, call(FACING_TEST, a, b, t)] for a, b, t in
                          ((rng.randrange(-0x2000, 0x2000), rng.randrange(-0x2000, 0x2000),
                            rng.randrange(0, 0x900)) for _ in range(n))]
    out["approach"] = [[c, t, s, call(APPROACH, c, t, s)] for c, t, s in
                       ((rng.randrange(-0x2000, 0x2000), rng.randrange(-0x2000, 0x2000),
                         rng.randrange(-0x400, 0x400)) for _ in range(n))]
    out["fixed_madd"] = [[a, b, t, call(FIXED_MADD, a, b, t)] for a, b, t in
                         ((rng.randrange(-0x40000, 0x40000), rng.randrange(-0x40000, 0x40000),
                           rng.randrange(0, 0x1001)) for _ in range(n))]

    rows = []
    for _ in range(n * 2):
        p = (rng.randrange(0, 80 << 11), rng.randrange(-0x8000, 0), rng.randrange(0, 80 << 11))
        cx, cz = (p[0] >> 11) + rng.randrange(-3, 2), (p[2] >> 11) + rng.randrange(-3, 2)
        w, h = rng.randrange(1, 5), rng.randrange(1, 5)
        y = 0x8000 if rng.randrange(4) == 0 else p[1] + rng.randrange(-0x1000, 0x1000)
        _pos(cpu, PLAYER_POS, p)
        rows.append([*p, cx, cz, w, h, y, call(PLAYER_IN_RECT, cx, cz, w, h, y)])
    out["player_in_rect"] = rows
    return out


def export(out_dir):
    """routinecheck.json for godot/selftest.gd."""
    c = cases()
    if not c:
        return None
    path = os.path.join(out_dir, "routinecheck.json")
    with open(path, "w") as fh:
        json.dump({"snapshot": SNAP, "routines": c}, fh, separators=(",", ":"))
    return path


if __name__ == "__main__":
    for name, rows in cases().items():
        print(f"{name:18s} {len(rows):5d} calls, e.g. {rows[len(rows) // 2]}")
