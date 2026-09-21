#!/usr/bin/env python3
"""A software copy of the game's collision, and the harness that proved it.

    python3 tools/collision.py            check it against the game's own answers
    python3 tools/collision.py walls 0    the wall planes of level 0, as geometry

`tile_collision` (`0x8003260c`) is a pure function of a position, a radius and
one cell: it walks that cell's tile shape and returns a bitmask of what the
position is up against. Every rule below is its MIPS, transcribed -- nothing
here is inferred from how the maps look.

**How it was established.** `emu/bp13.lua` logs the arguments at entry and the
mask at exit, which the routine has not returned yet, so the labels are the
game's own rather than a reading of shared memory. Against every logged call
carrying the fifth argument — 4264 of them — this file reproduces the mask
**exactly, without exception**. Three older lines, recorded before that argument
was captured, are the only misses in the log as a whole.

**This is collision, not rendering.** The working copy of the tile shapes at
`0x801e4464` has exactly three references in `GAME.EXE`: the routine that copies
it in, and the two inside `tile_shape_reader`. Nothing draws from it. The shapes
below are what the player bumps into; what the player *sees* is built elsewhere,
and a second dispatch table sits immediately after this one at `0x80011be0`,
pointing into a separate cluster at `0x80035954`.

## The mask

Each handler contributes its own bits, so the answer says what kind of surface
was met, not merely that one was:

    1 | 4   a wall            (0x20, 0x21, 0x22, 0x24)
        4   a floor           (0x10, 0x30, 0x33, 0x34)
    2 | 4   a diagonal wall   (0x23)
        8   a ceiling         (0x11)

That matters because the earlier answer scored 90.6 % on a permissive metric
and was still badly wrong. This is a different kind of evidence: the game
states the answer, and the copy either matches it or does not.

## The shape

`cell[+8]` indexes 254 shapes; each is a program of variable-length
instructions, `hw0` a scale and `hw1` the instruction count.

    a3 = (radius * hw0) >> 12       the shape scales the radius
    t6 = 0x800 - a3
    tx = X & 0x7ff,  tz = Z & 0x7ff a cell is 0x800 across
    cur = 100000                    the nearest surface so far

## The instructions

`0x20`/`0x21`/`0x22` are **walls**: a plane inside the cell, not an edge of it.

    face = (op[3] + cell[+7]) & 3
    lateral, per face:  0: tx <= op0 + a3     2: tx >= t6 - op0
                        1: tz >= t6 - op0     3: tz <= op0 + a3
    0x21 takes that OR the next face's, 0x22 takes AND -- an L and a corner
    lo = op1 + base, hi = op2 + base
    if y - 128 < lo and hi < cur:  cur = hi
                                   if y > hi:  mask |= 5

`0x30` is a **sloping floor**, all four faces meeting at `0x80033030`:

    h = op0 + base - ((q / op5) + 1) * op4
    q is tz, tx, 0x800 - tz, 0x800 - tx for faces 0..3
    the lateral extent is tested on the other axis
    if h < cur:  cur = h;  if h < y:  mask |= 4

`0x24` is a wall of **limited length**: measured from its own face, it occupies
`op0..op1` rather than the whole cell, which is what a pillar or a free standing
segment needs. Heights and blocking are `0x20`'s, and it shares its tail.

`0x33` and `0x34` are **corner slopes**: the height follows the nearer of the
two axes for `0x33` and the farther for `0x34` — an inner corner against an
outer one, and the handlers differ by one instruction.

    q = min(tx, tz) or max(tx, tz), and their three rotations
    h = op0 + base - ((q / op3) + 1) * op2

`0x10` is a flat floor at `op0 + base`, under the same rule as `0x30`.

`0x11` is a **ceiling**: a slab from `op0 + base` down to `op1 + base`. With the
head between the two it sets bit 3; clear of it, the slab becomes the nearest
surface instead.

`0x23` is a **wall at 45 degrees** and `0x32` a **floor sloping along a
diagonal**. These are what the `tx ± tz` values in the prologue are for, a
question left open from the first reading of it. `0x23` takes one of them
against a threshold, cutting the cell cornerwise; `0x32` runs its height along
one, clamped into `op1..op2` so the slope can start and stop partway.

`base` is the cell's own height, `-128 * cell[+6]`, formed at `0x80033bec` as a
`negu` and a shift by 7. The grid is at `0x801d4464`, a cell at `+ cz*800 +
cx*10`, both of them constants in the code at `0x80033b8c`.
"""
import re
import sys

sys.path.insert(0, "tools")
import tiles  # noqa: E402

GRID, W, CELL = 0x801D4464, 80, 10
WALLOPS = {0x20, 0x21, 0x22}
HOFF = 128                 # only for log lines older than `arg5`. The routine
                           # uses `s3 = y - (arg5 & 0x0fffffff)`, and arg5 is a
                           # real argument that ranges 0..1997 — it is the body
                           # height the caller is asking about, so no constant
                           # can stand in for it.
WALL_BIT, FLOOR_BIT, CEIL_BIT, DIAG_BIT = 5, 4, 8, 6


def s16(v):
    return v - 0x10000 if v > 0x7FFF else v


class Level:
    def __init__(self, lv, grid=None):
        self.tail, self.offs = tiles.table(lv)
        self.grid = grid or open("out/grid_live_lv0.bin", "rb").read()
        self.cache = {}

    def shape(self, sid):
        if sid not in self.cache:
            self.cache[sid] = (tiles.shape(self.tail, self.offs[sid])
                               if sid != 255 else (None, []))
        return self.cache[sid]

    def cell(self, cx, cz):
        o = (cz * W + cx) * CELL
        return self.grid[o:o + CELL]


def lateral(op, face, tx, tz, op0, a3, t6):
    """The wall test of handlers 0x20 (one plane), 0x21 (either), 0x22 (both)."""
    def plane(f):
        return (tx <= op0 + a3 if f == 0 else
                tz >= t6 - op0 if f == 1 else
                tx >= t6 - op0 if f == 2 else
                tz <= op0 + a3)
    if op == 0x20:
        return plane(face)
    a, b = plane(face), plane((face + 1) & 3)
    return (a or b) if op == 0x21 else (a and b)


def slab(face, tx, tz, a3, op):
    """Handler 0x24: a wall of limited length rather than a half-plane.

    Measured from the face's own side, the wall occupies `op0..op1` — a free
    standing segment or a pillar, which is why it needs two bounds where 0x20
    needs one.
    """
    u = (tx if face == 0 else 0x800 - tz if face == 1 else
         0x800 - tx if face == 2 else tz)
    return s16(op[0]) - a3 <= u <= s16(op[1]) + a3


def diagonal(face, tx, tz, op, outer=False):
    """Handlers 0x33 and 0x34: a corner slope.

    The height follows one of the two axis distances — the nearer for `0x33`,
    the farther for `0x34`, which is the same surface turned inside out: an
    inner corner against an outer one. The two handlers are identical but for
    `move $a0, $a2` against `move $a2, $a0`.

    The diagonal is in *plan*, not in pitch: lines of equal height run
    cornerwise, while the steepness is `op2 / op3` and is usually gentle. Level
    0 cell (46,22) falls one height unit across the whole cell, which reads as
    flat ground in play.
    """
    pick = max if outer else min
    q = (pick(tx, tz) if face == 0 else
         pick(tx, 0x800 - tz) if face == 1 else
         pick(0x800 - tx, 0x800 - tz) if face == 2 else
         pick(0x800 - tx, tz))
    div = s16(op[3])
    if div == 0:
        return None
    return s16(op[0]) - (q // div + 1) * s16(op[2])


def diag_wall(face, tx, tz, a3, op):
    """Handler 0x23: a wall at 45 degrees.

    This is what the prologue's `tx ± tz` values are for. Each face takes one of
    them against a threshold, so the blocked region is a half-plane cut
    cornerwise across the cell rather than along an axis.
    """
    d, adj = ((tx - tz, -0x800) if face == 0 else
              (-tx - tz, -0x1000) if face == 1 else
              (tz - tx, -0x800) if face == 2 else
              (tx + tz, 0))
    return d <= s16(op[0]) + a3 + adj


def diag_ramp(face, tx, tz, op):
    """Handler 0x32: a floor sloping along a diagonal.

    The height runs with `a2`, a cornerwise coordinate, clamped into `op1..op2`
    — so the slope starts and stops partway across the cell instead of spanning
    it the way 0x30 does. Note there is no `+ 1` here where 0x30 has one.
    """
    a2 = (0x800 + tz - tx if face == 0 else
          tx + tz if face == 1 else
          0x800 + tx - tz if face == 2 else
          0x1000 - tx - tz)
    op1, op2, op4, op5 = s16(op[1]), s16(op[2]), s16(op[4]), s16(op[5])
    if a2 < op1 or op5 == 0:
        return None
    a2 = min(a2, op2)
    return s16(op[0]) - ((a2 - op1) // op5) * op4


def ceiling(s3, base, cur, op):
    """Handler 0x11: a slab overhead.

        top = op0 + base, bot = op1 + base
        head between them  -> mask bit 3
        head clear of it   -> it becomes the nearest surface instead

    Returns (mask bit, new nearest).
    """
    top = s16(op[0]) + base
    if not s3 < top:
        return 0, cur
    bot = s16(op[1]) + base
    if bot < s3:
        return CEIL_BIT, cur
    return 0, min(cur, bot)


def ramp(face, tx, tz, a3, t6, op):
    """Handler 0x30: the height offset of a sloping floor, or None if outside."""
    op0, op1, op2, op4, op5 = (s16(op[0]), s16(op[1]), s16(op[2]),
                               s16(op[4]), s16(op[5]))
    if op5 == 0:
        return None
    if face == 0:
        span, q = op1 - a3 <= tx <= op2 + a3, tz
    elif face == 1:
        span, q = t6 - op2 <= tz <= a3 + 0x800 - op1, tx
    elif face == 2:
        span, q = t6 - op2 <= tx <= a3 + 0x800 - op1, 0x800 - tz
    else:
        span, q = op1 - a3 <= tz <= op2 + a3, 0x800 - tx
    return op0 - (q // op5 + 1) * op4 if span else None


def notch(face, tx, tz, a3, op):
    """Handler 0x25: a wall whose footprint is an L rather than a rectangle.

    207 uses on all 28 levels, and this routine ignored it entirely until the
    switch table was read -- which is a good candidate for "some low walls can
    be walked through". The dispatch indexes at `opcode - 0x10`, so the arm is
    the one at `0x80032d3c`.

    In the face's own frame -- `u` along it, `v` across, the same rotation the
    other lateral handlers use -- the region is

        u >= op0 - a3   and   v <= op3 + a3   and
        not (u > op1 + a3 and v < op2 - a3)

    so it is a quadrant with a bite taken out of the far corner. The first two
    bounds are the outer edges and the third is the notch, and the code says it
    in exactly that shape: a pair of tests that only reject together
    (`0x80032da0` and `0x80032db8`) and then two that reject on their own.
    """
    u = (tx if face == 0 else 0x800 - tz if face == 1 else
         0x800 - tx if face == 2 else tz)
    v = (tz if face == 0 else tx if face == 1 else
         0x800 - tz if face == 2 else 0x800 - tx)
    op0, op1, op2, op3 = (s16(op[0]), s16(op[1]), s16(op[2]), s16(op[3]))
    if op1 + a3 < u and v < op2 - a3:
        return False
    return not (u < op0 - a3 or op3 + a3 < v)


def layer_of(c, ymid):
    """Which of a cell's two layers a query at `ymid` belongs to (`0x800324f0`).

    A cell is two five-byte layers, 0 and 5, each with its own height, rotation
    and shape at `+1`, `+2`, `+3`. Heights count upward in units of 128, so the
    query's own height is `-(ymid >> 7)`, and the rule is simply "stand on the
    layer whose floor is not above you", with the other one taken when the
    nearer is absent. `tile_collision` never sees this: it is handed a cell and
    a base, which is why the harness below could ignore layers entirely.
    """
    ha, hb = c[1], c[6]
    hu = (-(ymid >> 7)) & 0xFFFF
    if hb < ha:
        return 5 if (hu < ha and hb) else 0
    return 0 if (hu < hb and ha) else 5


FAR = 100000               # what the routine seeds the nearest surface with,
                           # at 0x80032658 -- so "nothing found" reads back as
                           # 100000 rather than as a stale value


# The three extra surfaces, at the addresses the routine leaves them at.
# Opcodes 0x17, 0x18 and 0x19 write one each, and nothing else in the game
# writes them. `sync_player_pos` (0x80028d54) is the only reader: each frame it
# takes `surface + 0x640` less the player's eye -- Y plus the bob plus the
# landing crouch -- into 0x801b2638, 0x801b263c and 0x801b2640, and when the
# eye has gone past one it calls 0x80030a6c, which puts the player into state
# 0x11 and plays sound 0x6e. So these are planes that do something to you when
# you are under them, which is why no recording in this repository has ever hit
# one: nobody drowned while a breakpoint was armed.
SURFACES = {0x17: 0x801E6484, 0x18: 0x801E647C, 0x19: 0x801E6480}


def collide(lvl, x, y, z, radius, base=None, cx=None, cz=None, arg5=None,
            layer=5, nearest=False, extra=None):
    """The mask tile_collision would return for this position in this cell.

    With `nearest`, returns `(mask, cur)` instead: `cur` is the nearest surface
    the routine leaves at `0x801e6474`, which is what the callers use as a floor
    height. It is seeded to 100000 at entry, so an untouched query says 100000
    rather than whatever the last caller left there.
    """
    def answer(mask, cur):
        return (mask, cur) if nearest else mask

    cx = x >> 11 if cx is None else cx
    cz = z >> 11 if cz is None else cz
    if not (0 <= cx < W and 0 <= cz < W):
        return answer(0, FAR)
    c = lvl.cell(cx, cz)
    sid, rot = c[layer + 3], c[layer + 2] & 3
    base = -128 * c[layer + 1] if base is None else base
    hdr, ins = lvl.shape(sid)
    if hdr is None:
        return answer(0, FAR)
    a3 = (radius * hdr[2]) >> 12
    t6 = 0x800 - a3
    tx, tz = x & 0x7FF, z & 0x7FF
    s3 = y - (HOFF if arg5 is None else (arg5 & 0x0FFFFFFF))
    # The top nibble of arg5 is a flag field, split off at 0x800326b0 and used
    # by exactly one handler, 0x18. The rest of the routine never looks at it.
    flags = 0 if arg5 is None else (arg5 & 0xF0000000)
    cur, mask = FAR, 0
    floor_locked = False              # [sp+0x10], which 0x18 sets and 0x10 obeys
    for op, args in ins:
        if op == 0x10 and args and not floor_locked:
            h = s16(args[0]) + base
            cur = min(cur, h)
            if cur < y:
                mask |= FLOOR_BIT
        elif op == 0x30 and len(args) >= 6:
            d = ramp((s16(args[3]) + rot) & 3, tx, tz, a3, t6, args)
            if d is not None and d + base < cur:
                cur = d + base
                if cur < y:
                    mask |= FLOOR_BIT
        elif op == 0x23 and len(args) >= 4:
            if not diag_wall((s16(args[3]) + rot) & 3, tx, tz, a3, args):
                continue
            lo, hi = s16(args[1]) + base, s16(args[2]) + base
            if s3 < lo and hi < cur:
                cur = hi
                if y > hi:
                    mask |= DIAG_BIT
        elif op == 0x32 and len(args) >= 6:
            d = diag_ramp((s16(args[3]) + rot) & 3, tx, tz, args)
            if d is not None and d + base < cur:
                cur = d + base
                if cur < y:
                    mask |= FLOOR_BIT
        elif op == 0x11 and len(args) >= 2:
            bit, cur = ceiling(s3, base, cur, args)
            mask |= bit
        elif op in (0x33, 0x34) and len(args) >= 4:
            d = diagonal((s16(args[1]) + rot) & 3, tx, tz, args, op == 0x34)
            if d is not None and d + base < cur:
                cur = d + base
                if cur < y:
                    mask |= FLOOR_BIT
        elif op == 0x24 and len(args) >= 5:
            if not slab((s16(args[4]) + rot) & 3, tx, tz, a3, args):
                continue
            lo, hi = s16(args[2]) + base, s16(args[3]) + base
            if s3 < lo and hi < cur:
                cur = hi
                if y > hi:
                    mask |= WALL_BIT
        elif op in SURFACES and args:
            h = s16(args[0]) + base
            if extra is not None:
                extra[SURFACES[op]] = h
            if op != 0x18:
                continue
            if flags & 0x80000000:                 # 0x80033a30, `bgez $fp`
                cur = h                            # set, not reduced
                if h < y:
                    mask |= FLOOR_BIT
                    floor_locked = True
            if flags & 0x40000000:                 # 0x80033a5c
                if extra is not None:
                    extra[0x801E6478] = h
                if not (h < s3):
                    mask |= CEIL_BIT
        elif op == 0x25 and len(args) >= 7:
            if not notch((s16(args[6]) + rot) & 3, tx, tz, a3, args):
                continue
            lo, hi = s16(args[4]) + base, s16(args[5]) + base
            if s3 < lo and hi < cur:
                cur = hi
                if y > hi:
                    mask |= WALL_BIT
        elif op in WALLOPS and len(args) >= 4:
            if not lateral(op, (s16(args[3]) + rot) & 3, tx, tz,
                           s16(args[0]), a3, t6):
                continue
            lo, hi = s16(args[1]) + base, s16(args[2]) + base
            if s3 < lo and hi < cur:
                cur = hi
                if y > hi:
                    mask |= WALL_BIT
    return answer(mask, cur)


LOGLINE = re.compile(
    r"([0-9a-f]{8}) mask=\s*(-?\d+) x=\s*(\d+) y=\s*(\d+) z=\s*(\d+) "
    r"r=\s*(\d+) cell=([0-9a-f]{8}) base=\s*(\d+)(?: arg5=\s*(\d+))? lv=\s*(\d+)")


def _s32(v):
    return v - 2 ** 32 if v >= 2 ** 31 else v


def log_rows(path="out/lua_bp13.log"):
    """The calls emu/bp13.lua recorded. `arg5` is absent in older lines."""
    out = []
    for line in open(path):
        m = LOGLINE.match(line)
        if not m:
            continue
        ra, mask, x, y, z, r, cell, base, arg5, lv = m.groups()
        out.append({"ra": ra, "mask": int(mask),
                    "x": _s32(int(x)), "y": _s32(int(y)), "z": _s32(int(z)),
                    "r": int(r), "cell": int(cell, 16), "base": _s32(int(base)),
                    "arg5": int(arg5) if arg5 is not None else None,
                    "lv": int(lv)})
    return out


def verify(path="out/lua_bp13.log", only_arg5=False):
    """Against the game's own answers, logged by emu/bp13.lua."""
    rows = log_rows(path)
    if only_arg5:
        rows = [r for r in rows if r["arg5"] is not None]
    lvl = Level(0)
    ok, miss = 0, {}
    for r in rows:
        off = r["cell"] - GRID
        cx, cz = (off // CELL) % W, (off // CELL) // W
        got = collide(lvl, r["x"], r["y"], r["z"], r["r"], r["base"], cx, cz,
                      r["arg5"])
        if got == r["mask"]:
            ok += 1
        else:
            c = lvl.cell(cx, cz)
            ops = {op for op, _ in lvl.shape(c[8])[1]}
            miss[(r["mask"], got, tuple(sorted(ops)))] = \
                miss.get((r["mask"], got, tuple(sorted(ops))), 0) + 1
    print(f"{ok} of {len(rows)} calls reproduced exactly "
          f"({ok * 100 / len(rows):.1f} %)")
    for (want, got, ops), n in sorted(miss.items()):
        print(f"  game said {want}, we said {got}, {n}x — shape uses "
              + " ".join(f"{o:#04x}" for o in ops))
    return ok, len(rows)


def walls(lv, lvl=None):
    """Every wall plane on a level, as (cx, cz, face, offset, low, high).

    `0x24` is included at its near bound: it is a slab from `op0` to `op1` and
    the near face is what a plan view wants. `0x25` is included at `op0` for
    the same reason -- its footprint is an L and `op0` is the outer edge, the
    one a plan view draws.

    This walks the **upper** layer only (`c[8]`, `c[6]`, `c[7]`), which is what
    it has always done; a shape in the lower layer contributes nothing here.
    """
    lvl = lvl or Level(lv)
    for cz in range(W):
        for cx in range(W):
            c = lvl.cell(cx, cz)
            if c[8] == 255:
                continue
            base, rot = -128 * c[6], c[7] & 3
            for op, args in lvl.shape(c[8])[1]:
                if op in WALLOPS and len(args) >= 4:
                    yield (cx, cz, (s16(args[3]) + rot) & 3, s16(args[0]),
                           s16(args[1]) + base, s16(args[2]) + base)
                elif op == 0x24 and len(args) >= 5:
                    yield (cx, cz, (s16(args[4]) + rot) & 3, s16(args[0]),
                           s16(args[2]) + base, s16(args[3]) + base)
                elif op == 0x25 and len(args) >= 7:
                    yield (cx, cz, (s16(args[6]) + rot) & 3, s16(args[0]),
                           s16(args[4]) + base, s16(args[5]) + base)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "walls":
        lv = int(sys.argv[2]) if len(sys.argv) > 2 else 0
        n = 0
        for cx, cz, face, off, lo, hi in walls(lv):
            print(f"({cx:2d},{cz:2d}) face {face}  offset {off:5d}  "
                  f"height {hi:7d}..{lo:7d}")
            n += 1
        print(f"\n{n} wall planes on level {lv}")
    else:
        verify()
