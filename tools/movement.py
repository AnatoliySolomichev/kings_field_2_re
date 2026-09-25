#!/usr/bin/env python3
"""The player's own movement, transcribed from `player_move` and checked.

    python3 tools/movement.py            check it against the game's own answers
    python3 tools/movement.py model      print the constants, with their sources
    python3 tools/movement.py fall 0     drop the player and print the arc

**Withdrawn: `player_move` is not the walking movement.** It was written here
that `0x8002f320` "is the only code that writes the player's Y during ordinary
play". `emu/bp14.lua` says otherwise, and that is the whole point of it: in a
recorded session the routine ran **69 times, every one of them in player state
0x10 or 0x11** — the knockback after dying — while the control point watched the
position change eight hundred times without it. The transcription below is
right about the routine; the claim about which routine mattered was not, and it
came from reading callers instead of asking the game.

Walking is `player_vertical` (`0x8002ed60`) for the height and `0x8002e3f8`,
reached through `0x8002f9bc`, for the ground plane. The controller
(`0x80030fcc`) runs `0x8002fe1c`, `0x8002f5c0`, `0x8002f9bc` and then
`0x8002ed60` on the ordinary path, and calls `player_move` only on two other
branches. `walk_step` below is `player_vertical`'s grounded state.

**Not `actor_move_horizontal` either.** That routine (`0x8004dbc8`, its inner
label at `0x8004dca0`) belongs to the monsters. Its actor comes from the pointer
at `0x8018fab4`, which `actor_select` (`0x8004da2c`) fills from the 0x88-byte
table at `0x80185da8` — and no entry of that table carries the player's position
in any snapshot we have. Its vertical half is `0x8004e330`.

## player_move, which does run -- when you are thrown

Position is three s32 at `0x801b25f0`, velocity three s16 at `0x801b266c`.
One frame:

    n = p + v
    if collide(n) is clear:                       commit
    n.y = p.y                                     # try at the current height
    if collide(n) is clear:  v.y = 1;             slide by 0x20, then commit
    if mask & ~0x205:                             refuse, nothing moves
    if surface + 0x100 < p.y:                     refuse -- the step is too high
    n.y = surface                                 # step up onto it
                                                  slide by 0x38, then commit

    commit:  p = n;  v.y = v.y + 0x20

`slide` shortens the horizontal velocity by a fixed amount rather than
projecting it along the wall, and stops the player outright when what is left is
shorter than that amount. It is the *velocity* that is shortened, so the effect
lands on the following frame; this frame commits the candidate it already has.

Three readings worth naming, because they are what the Godot build had wrong:

* **Gravity is `+0x20` a frame, unconditionally**, applied on every commit —
  there is no grounded state and no place where the velocity is zeroed on
  landing. Standing still, the player's Y does not change while `v.y` cycles
  1, 0x21, 1, 0x21: the full move is refused by the floor, the horizontal-only
  move is clear, so `v.y` is reset to 1 and the position commits unchanged. The
  player therefore rests up to 0x21 units above the surface, not on it.
* **A step up is at most `0x100`** — two height units of 128 — measured from the
  nearest surface the blocked query found, and it is taken with no further
  check. That is the stair rule, and it is why the guessed "snap to the floor"
  policy got stairs and gentle rises wrong in both directions.
* **A wall is steppable.** `mask & ~0x205` is the hard block, and `5` is exactly
  what a wall handler contributes, so a wall low enough passes the `0x100` test
  and is climbed. Low walls being solid in the port was this, not a missing
  opcode.

Everything above is read off the MIPS. The one thing that is not: the integer
square root behind `0x80016c08` is taken to be `floor(sqrt(x))`, which is what
the PlayStation library's `SquareRoot0` computes; it is used only by the slide.
"""
import math
import os
import re
import sys

sys.path.insert(0, "tools")
import collision  # noqa: E402

R = 0x320          # radius passed at 0x8002f398
BODY = 0x6A4       # body height, the fifth argument, 0x8002f328
LAYERS = 0x31      # the sixth: tile collision | objects | actors, 0x8002f330
GRAVITY = 0x20     # 0x8002f408
STEP_UP = 0x100    # 0x8002f578
SLIDE_WALL = 0x20  # 0x8002f4a0
SLIDE_STEP = 0x38  # 0x8002f590
SOFT = 0x205       # `and $v0, $v1, -0x206` at 0x8002f55c
FALL_V = 0x12C     # 0x8002f3b0
FALL_DROP = 0x5000  # 0x8002f3d4
GRID_MAX = 0x27FFF  # 0x800324f0's bound: 80 cells of 0x800


def s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v >= 0x8000 else v


def trunc(a, b):
    """MIPS `div`, which truncates toward zero where Python floors."""
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


def vlen(a, b):
    """`0x80016c08`: the length of (a, b), quantised to eight."""
    return math.isqrt((a >> 3) ** 2 + (b >> 3) ** 2) << 3


def query(lvl, x, y, z, radius=R, body=BODY, ymid=None):
    """`0x80033f38` with the player's flags, as far as the tiles go.

    The wrapper picks the cell and the layer from the *middle* of the body —
    `y - ((arg5 << 4) >> 5)`, at `0x80033d38` — and only then asks
    `tile_collision` about the feet. Objects and actors, which the player's
    `0x31` also asks about, are not modelled here; a mask carrying their bits
    shows up in the check below as a call this file does not claim.

    `ymid` overrides that, because the *other* wrapper does it differently:
    `0x80033b10` passes a flat `y - 0x500` at `0x80033b44` where this one halves
    the body height. The two disagree by 430 units, which is a third of a height
    unit and enough to land in the wrong layer of a cell.
    """
    if ymid is None:
        ymid = y - (((body << 4) & 0xFFFFFFFF) >> 5)
    cx, cz = x >> 11, z >> 11
    if not (0 <= x <= GRID_MAX and 0 <= z <= GRID_MAX):
        return 0, collision.FAR
    lay = collision.layer_of(lvl.cell(cx, cz), ymid)
    return collision.collide(lvl, x, y, z, radius, cx=cx, cz=cz, arg5=body,
                             layer=lay, nearest=True)


def surface(lvl, x, y, z, radius=R, body=BODY):
    """`0x80033b10`: the nearest surface alone, the way `player_vertical` asks.

    Same tile collision, but the layer comes off a flat `y - 0x500` and the
    answer is `0x801e6474` rather than the mask.
    """
    return query(lvl, x, y, z, radius, body, ymid=y - 0x500)[1]


# The game's own trigonometry, out of its own table.
#
# `0x80076da0` is cosine and `0x80076cc4` is sine, both over 0x1000 to the turn
# and both reading one quarter wave of 1025 entries at 0x8009a2e0, reflected
# four ways. Getting this from `math` instead would be close and not equal, and
# `player_horizontal` shifts the product right by 12, so a rounding difference
# lands in the position as a whole unit.
SIN_TABLE = 0x8009A2E0


def _table():
    import struct
    import disasm
    base, _entry, text = disasm.load_text()
    off = SIN_TABLE - base
    return struct.unpack_from("<1025h", text, off)


_S = None


def _q(j):
    global _S
    if _S is None:
        _S = _table()
    return _S[j]


def game_sin(a):
    """`0x80076cc4`, odd, 0x1000 to the turn, 4096 to the unit."""
    if a < 0:
        return -game_sin(-a)
    a &= 0xFFF
    if a < 0x401:
        return _q(a)
    if a < 0x801:
        return _q(0x800 - a)
    if a < 0xC01:
        return -_q(a - 0x800)
    return -_q(0x1000 - a)


def game_cos(a):
    """`0x80076da0`, even, the same table a quarter turn along."""
    a = abs(a) & 0xFFF
    if a < 0x401:
        return _q(0x400 - a)
    if a < 0x801:
        return -_q(a - 0x400)
    if a < 0xC01:
        return -_q(0xC00 - a)
    return _q(a - 0xC00)


def _s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v >= 0x8000 else v


def rot_matrix_x(a):
    """`0x80016598`: nine halfwords, a rotation about the first axis."""
    s, c = game_sin(a), game_cos(a)
    return (0x1000, 0, 0,
            0, c, -s,
            0, s, c)


def rot_matrix_y(a):
    """`0x8001660c`: the same for the second axis."""
    s, c = game_sin(a), game_cos(a)
    return (c, 0, -s,
            0, 0x1000, 0,
            s, 0, c)


def apply_matrix(m, v):
    """`ApplyMatrixLV` (0x80074840): MVMVA with no translation, MAC1..3 out.

    The GTE shifts each row's dot product right by 12, and the routine stores
    the **MAC** registers rather than IR, so nothing is saturated to 16 bits
    here. The caller does that itself.
    """
    return tuple(sum(m[3 * r + k] * v[k] for k in range(3)) >> 12
                 for r in range(3))


def direction_from_angles(pitch, yaw):
    """`direction_from_angles` (0x800167cc): a pair of angles to a unit vector.

    Rotate (0, 0, 0x1000) by the **negated** first angle about the first axis
    and then by the second about the second. Between the two stages the game
    copies the three 32-bit results into a 16-bit `SVECTOR`, so the truncation
    is part of the answer, not an accident of the port.
    """
    v = apply_matrix(rot_matrix_x(-pitch), (0, 0, 0x1000))
    v = tuple(_s16(x) for x in v)
    w = apply_matrix(rot_matrix_y(yaw), v)
    return tuple(_s16(x) for x in w)


# The game's own arctangent: `vec_angle` (0x80016ab8) with `arctan_unit`
# (0x800742ac) under it. Twelve CORDIC iterations over the table at
# 0x8009591c, which holds atan(2**-i) in the game's 0x1000-to-the-turn units --
# 511, 302, 159, 81, 41, 20, 10, 5, 3, 1, 0, 0, against 512.00, 302.25, 159.70,
# 81.07 ... computed. Nineteen routines call it, all of them things that turn
# towards something.

CORDIC = 0x8009591C
_C = None


def _cordic_table():
    global _C
    if _C is None:
        import struct
        import disasm
        base, _entry, text = disasm.load_text()
        _C = list(struct.unpack_from("<12i", text, CORDIC - base))
    return _C


def arctan_unit(ratio):
    """`0x800742ac`: a ratio in 12-bit fixed point to an angle.

    CORDIC in vectoring mode -- rotate (0x1000, ratio) towards the axis and
    accumulate what each rotation was worth. Twelve iterations, and the last
    two table entries are zero, so the answer settles before it runs out.
    """
    t = _cordic_table()
    x, y, z = 0x1000, ratio, 0
    for i in range(12):
        if y >= 0:
            x, y, z = x + (y >> i), y - (x >> i), z + t[i]
        else:
            x, y, z = x - (y >> i), y + (x >> i), z - t[i]
    return z


def _idiv(a, b):
    """MIPS `div`: truncating, not floor, which Python's // is not."""
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


def vec_angle(u, v):
    """`0x80016ab8`: the direction of (u, v), 0x1000 to the turn.

    The larger component is the denominator, so the ratio never leaves
    [-1, 1], and the quadrant is put back with 0x400, 0x800 and 0xc00. `u` is
    the first argument and `v` the second; what they are in world terms is the
    caller's business, and the nineteen callers do not agree with each other.
    """
    if abs(v) >= abs(u):
        if v > 0:
            return (-arctan_unit(_idiv(u << 12, v))) & 0xFFF
        if v < 0:
            return 0x800 - arctan_unit(_idiv(u << 12, v))
        return 0
    if u < 0:
        return arctan_unit(_idiv(v << 12, u)) + 0x400
    return arctan_unit(_idiv(v << 12, u)) + 0xC00


# The game's own integer square root, and it is *not* floor(sqrt(x)).
#
# `0x80074508` normalises through the GTE's leading-zero count, indexes a
# 192-entry table at 0x80096150 and shifts back -- the PlayStation library's
# SquareRoot0. For a perfect square it comes back one short: 40000 gives 199,
# not 200. That one unit is not a curiosity. The walking step is
# `speed^2 / isqrt(speed^2)`, so the error turns 200 into 201, and a replay
# using math.isqrt disagreed with the game on 1394 frames out of 3632 for that
# reason alone.
ISQRT_TABLE = 0x80096150


def _isqrt_table():
    import struct
    import disasm
    base, _entry, text = disasm.load_text()
    return struct.unpack_from("<192h", text, ISQRT_TABLE - base)


_IS = None


def game_isqrt(x):
    """`0x80074508`. Exact transcription, table and all."""
    global _IS
    if _IS is None:
        _IS = _isqrt_table()
    x &= 0xFFFFFFFF
    if x == 0:
        return 0
    lzc = 32 - x.bit_length()          # what the GTE leaves in LZCR
    if lzc == 0x20:
        return 0
    t2 = lzc & ~1
    t1 = (0x1F - t2) >> 1
    t3 = t2 - 0x18
    t4 = (x << t3) & 0xFFFFFFFF if t3 >= 0 else x >> (0x18 - t2)
    idx = t4 - 0x40
    if not 0 <= idx < 192:
        return 0
    return ((_IS[idx] << t1) & 0xFFFFFFFF) >> 12


def step_distances(strafe_speed, forward_speed):
    """`0x8002fc94`: the two distances, from the two speeds.

    Not the speeds themselves. Each is `speed^2 / isqrt(strafe^2 + forward^2)`,
    keeping the speed's sign -- which normalises a diagonal to one speed and,
    because the square root comes back a unit short, makes a straight walk one
    unit longer than the speed says.

    Returns (forward distance, strafe distance).
    """
    a, b = s16(strafe_speed), s16(forward_speed)
    h = s16(game_isqrt(a * a + b * b))
    if h == 0:
        return 0, 0
    fwd = trunc(b * b, h)
    stf = trunc(a * a, h)
    return (-fwd if b < 0 else fwd), (-stf if a < 0 else stf)


# -- objects: what the player's 0x31 asks after the tiles -------------------
#
# collide_query (0x80033f38) goes on to the things in the level only when the
# cell under the query has an occupancy count -- byte +2 of its first layer,
# `& 0xfc`, which grid_mark (0x80033c4c) adds 4 to for everything within its
# radius + 0x800. load_object_placement marks every solid object that way, and
# creatures mark themselves as they move. The player marks itself too, but
# player_controller takes its own mark off (grid_mark(.., -1) at 0x80031008)
# before it moves and puts it back (at 0x800320d8) after, so the player's own
# query never sees it. Then flag 0x10 asks actor_spot_taken and flag 0x20
# object_collide (0x80045ac8), whose answer lands at collide_object
# (0x801e6490) and turns on bit 0x20 of the mask.

RATAN_TABLE = 0x8009594C
_RT = None


def ratan_table():
    global _RT
    if _RT is None:
        import struct
        import disasm
        base, _entry, text = disasm.load_text()
        _RT = struct.unpack_from("<1025h", text, RATAN_TABLE - base)
    return _RT


def ratan2(y, x):
    """`0x80074380`, the library's ratan2: 1025 entries at `0x8009594c`.

    The smaller of |y| and |x| over the larger, scaled to 1024, indexes the
    table; the octant is put back with `0x400 -`, `0x800 -` and a negation.
    When both are 0 it answers 0.
    """
    rt = ratan_table()
    negx, negy = x < 0, y < 0
    x, y = abs(x), abs(y)
    if x == 0 and y == 0:
        return 0
    if y < x:
        t = y // (x >> 10) if y & 0x7FE00000 else (y << 10) // x
        v = rt[t]
    else:
        t = x // (y >> 10) if x & 0x7FE00000 else (x << 10) // y
        v = 0x400 - rt[t]
    if negx:
        v = 0x800 - v
    return -v if negy else v


def in_range(pos, x, y, z, r, top, own):
    """`0x80016ec8`: the distance from `pos` to (x, z), or -1.

    Square first, then the height: a thing standing at `pos` with its top `top`
    above its feet, against one at y with its top `own` above -- they overlap
    unless one is wholly above the other (Y grows downward). y = 0xffff skips
    the height. Then the distance, to eight, through the game's own root.
    """
    dx = pos[0] - x
    if dx < -r or dx > r:
        return -1
    dz = pos[2] - z
    if dz < -r or dz > r:
        return -1
    if y != 0xFFFF:
        if pos[1] < y:
            if pos[1] < y - own:
                return -1
        elif y < pos[1] - top:
            return -1
    d = game_isqrt((dx >> 3) * (dx >> 3) + (dz >> 3) * (dz >> 3)) << 3
    return -1 if d > r else d


def in_oriented_rect(ang, pos, x, y, z, a, b, top, own):
    """`0x80016d3c`: (x, z) inside a rectangle turned by `ang`, or -1.

    The offset goes to polar -- its length by the root, its bearing by
    vec_angle -- and back out along the rectangle's own axes: `cos(bearing -
    ang + 0x400)` across and `sin(..)` along, each times the length. The height
    test is in_range's.
    """
    ddx, ddz = (pos[0] - x) >> 3, (pos[2] - z) >> 3
    d = game_isqrt(ddx * ddx + ddz * ddz) << 3
    t = vec_angle(x - pos[0], z - pos[2]) & 0xFFFF
    rel = t - _s16(ang) + 0x400
    lx = (game_cos(rel) * d) >> 12
    lz = (game_sin(rel) * d) >> 12
    if lx < -a or lx > a or lz < -b or lz > b:
        return -1
    if y != 0xFFFF:
        if pos[1] < y:
            if pos[1] < y - own:
                return -1
        elif y < pos[1] - top:
            return -1
    return d


def solids(lvl):
    """The level's objects as object_collide sees them, slot order, cached.

    From `tools/objload.py` after its first frame: every record with a type and
    a byte +0 that is not zero, whose type row gives it a shape. Each carries
    what the push-out reads besides -- `sub_80033d84` (0x80033d84) sets the
    radius at 0x801e64b0 from the object's own byte +3: the row's +4 scaled by
    the object's +0x38 on bit 0x10, else the row's +0x10 on bit 4, else the
    row's +4. The order matters for a type with a radius *and* bit 4, which
    object_collide tests as a circle and player_horizontal slides along as a
    rectangle; none is placed on level 0, but the rule is the game's.
    """
    got = getattr(lvl, "_solids", None)
    if got is not None:
        return got
    import objcoll
    import objload
    ld = objload.Load(lvl.lv).first_frame()
    out = []
    for k in sorted(ld.recs):
        r = ld.recs[k]
        if r["type"] == 0xFF or r["b0"] == 0:
            continue
        row = ld.rows[r["type"]]
        kind, a, b = objcoll.shape(row, r["tail"][0], r["flags"])
        if kind == "none":
            continue
        if r["flags"] & 0x10:
            push = a
        elif r["flags"] & 4:
            push = row[0x10] | (row[0x11] << 8)
        else:
            push = row[4] | (row[5] << 8)
        out.append({"slot": k, "type": r["type"], "kind": kind, "a": a, "b": b,
                    "flags": r["flags"], "pos": (r["x"], r["y"], r["z"]),
                    "top": r["height"], "ang": r["angles"][1], "push": push})
    lvl._solids = out
    return out


def object_collide(objs, x, y, z, r=R, own=BODY):
    """`0x80045ac8`: the first object (x, y, z) runs into, or None.

    A circle grows by the querier's radius; a rectangle's two half-extents both
    do. The object's top is its +0xc, and `own` is the querier's height.
    """
    for o in objs:
        if o["kind"] == "circle":
            hit = in_range(o["pos"], x, y, z, o["a"] + r, o["top"], own)
        else:
            hit = in_oriented_rect(o["ang"], o["pos"], x, y, z, o["a"] + r,
                                   o["b"] + r, o["top"], own)
        if hit != -1:
            return o
    return None


def query_all(lvl, x, y, z):
    """`collide_query` with the player's 0x31, objects included.

    Returns (mask, nearest surface, the object hit or None). Creatures, bit
    0x10, are not here: their positions are not in the recording.
    """
    mask, cur = query(lvl, x, y, z)
    cx, cz = x >> 11, z >> 11
    if not (0 <= cx < 80 and 0 <= cz < 80) or not lvl.cell(cx, cz)[2] & 0xFC:
        return mask, cur, None
    o = object_collide(solids(lvl), x, y, z)
    return (mask | 0x20 if o else mask), cur, o


STEP_UP = 0x500        # the most player_horizontal lets a step climb
SHRINK = 0x16          # how much shorter each retry of a refused step is
AROUND = 0x370         # how far past an object's radius the push-out puts you
RECT_TRIES = (0x400, 0x400, 0x3E8, 0x3E8, 0x418, 0x418)


def horizontal(lvl, p, angle, dist, state=0, objects=True):
    """`player_horizontal` (`0x8002e3f8`): a step of `dist` along `angle`.

    X takes the cosine and Z the sine, shifted right by 12, and the step is
    asked of `collide_query` at the player's height with flags `0x31`. What
    happens when the answer is not clear, read off the listing in its order:

    * **a step up** is taken anyway if the mask has nothing outside `0x207`,
      the surface it found is no more than `0x500` above the feet, the player
      state (`0x801b25e5`) is 0 and the ceiling leaves room for the body --
      that is what stops a wall being climbed: its top is the surface, and it
      is higher than `0x500`;
    * **an object with a rectangle** (its byte +3 has bit 4) turns the step
      into the rectangle's frame -- its bearing less `0x400` less the object's
      angle at +0x26, worked out on the first try and kept -- and keeps one
      axis of it: the second on tries 1, 3 and 5 unless that is zero, the first
      on 2, 4 and 6 likewise. It turns back by the object's angle plus `0x400`,
      `0x3e8` or `0x418` -- a quarter turn and then 24 either side of it, so a
      corner that stops the square slide gets a slightly skewed one. Six tries;
      the seventh falls through to the push-out;
    * **anything else in the way** -- a round object, or a creature -- is gone
      round: the target moves to the object's centre plus its radius plus
      `0x370`, along the bearing from the centre to where the step was going,
      each part rounded towards zero. If the second target runs into a thing as
      well, the player stays where it is;
    * otherwise, a wall: the same step is **tried shorter**, `0x16` at a time,
      once, and the longest clear one is taken;
    * then it **slides**: first with the X part dropped, then with only the X
      part, and against a diagonal wall (mask bit 2) along the diagonal the
      cell's rotation says -- `(dx + dz) / 2` both ways for rotations 0 and 2,
      `(dx - dz) / 2` and its negative for 1 and 3;
    * and if none of that is clear, it stays.

    Not here: the push the tile collision leaves at `0x801e6498` and
    `0x801e649c` for a clear step close to a wall, the ceiling test, and the
    creatures. `objects=False` leaves the objects out as well.

    The caller (`0x8002f9bc`) makes this call twice a frame: once at `angle`
    with the forward distance and once at `angle + 0x400` with the strafe.
    """
    x, y, z = p
    s4 = (game_cos(angle) * dist) >> 12
    s2 = (game_sin(angle) * dist) >> 12
    first_x, first_z = s4, s2
    shrunk = diag = False
    tries = pushes = 0
    rel = 0
    for _ in range(64):
        tx, tz = x + s4, z + s2
        if objects:
            mask, cur, obj = query_all(lvl, tx, y, tz)
        else:
            (mask, cur), obj = query(lvl, tx, y, tz), None
        if mask == 0:
            return (tx, y, tz), True
        blocked = False
        if mask & ~0x207 == 0:
            if not cur + STEP_UP < y and state == 0:
                return (tx, y, tz), True
            if not mask & 2:
                blocked = True
        if obj is not None and obj["flags"] & 4 and tries < 6:
            tries += 1
            d = abs(dist)
            if tries == 1:
                rel = _s16(ratan2(s2, s4) - 0x400 - (obj["ang"] & 0xFFFF))
            u = (d * game_cos(rel)) >> 12
            v = (d * game_sin(rel)) >> 12
            if tries & 1:
                u = 0 if v else u
            else:
                v = 0 if u else v
            turn = _s16(obj["ang"]) + RECT_TRIES[tries - 1]
            c, s = game_cos(turn), game_sin(turn)
            s4 = ((u * c) >> 12) - ((v * s) >> 12)
            s2 = ((u * s) >> 12) + ((v * c) >> 12)
            continue
        if mask & 0x30:
            pushes += 1
            if pushes == 2:
                break
            ox, _oy, oz = obj["pos"]
            b = ratan2(s2 - (oz - z), s4 - (ox - x))
            r = obj["push"] + AROUND
            s4 = trunc(game_cos(b) * r, 4096) + ox - x
            s2 = trunc(game_sin(b) * r, 4096) + oz - z
            continue
        if not shrunk:
            shrunk = True
            s0 = dist - SHRINK
            while s0 >= 0:
                vx, vz = game_cos(angle) * s0, game_sin(angle) * s0
                nx = x + ((vx + 0xFFF if vx < 0 else vx) >> 12)
                nz = z + ((vz + 0xFFF if vz < 0 else vz) >> 12)
                s0 -= SHRINK
                q = query_all(lvl, nx, y, nz)[0] if objects else query(lvl, nx, y, nz)[0]
                if q == 0:
                    x, z = nx, nz
                    break
        if blocked or mask & 1:
            if s4 != 0:
                s4 = 0
                continue
            if s2 != 0:
                s4, s2 = first_x, 0
                continue
        if not mask & 2:
            break
        if diag:
            if s4 != 0:
                s4 = 0
                continue
            if s2 != 0:
                s4, s2 = first_x, 0
                continue
            break
        cx, cz = tx >> 11, tz >> 11
        c = lvl.cell(cx, cz) if 0 <= cx < 80 and 0 <= cz < 80 else bytes(10)
        lay = collision.layer_of(c, y - (((BODY << 4) & 0xFFFFFFFF) >> 5))
        if c[lay + 2] & 3 in (0, 2):
            s4 = s2 = (first_x + first_z) >> 1
        else:
            s4 = (first_x - first_z) >> 1
            s2 = -s4
        diag = True
    return (x, y, z), (x, z) != (p[0], p[2])


# The forward/back acceleration, out of 0x8002f9bc. `max` is 0x801b2664 and is
# written only at 0x80031188 and 0x800313e4 -- so if walking speed is a stat,
# that is where it is set, which is the open question in BACKLOG.md 5b.
def accelerate(speed, forward, back, cap, decay=3):
    """One frame of a speed ramp, `0x8002f9bc`.

    Pressing accelerates by `max / 4` either way; letting go decays, and the
    decay clamps at zero by sign rather than by comparison. **The two ramps
    decay at different rates** — the forward speed by `max / 8` (`sra 3` at
    `0x8002fad4`) and the strafe by `max / 4` (`sra 2` at `0x8002fc38`) — which
    is why `decay` is a parameter. Both were caught by a replay before they were
    read: `max / 4` for the forward one overshot on 85 frames, and `max / 8` for
    the strafe on four.
    """
    if forward:
        return min(s16(speed + (cap >> 2)), cap)
    if back:
        return max(s16(speed - (cap >> 2)), -cap)
    step = cap >> decay
    if speed > 0:
        return max(speed - step, 0)
    if speed < 0:
        return min(speed + step, 0)
    return 0


def walk_step(lvl, p, dx, dz, state=0, vel=0, momentum=0):
    """One frame of `player_vertical` (`0x8002ed60`), every state it has.

    **This, not `player_move`, is how the player moves.** Two recordings settled
    it: `emu/bp14.lua` showed `player_move` running only in the knockback after
    dying, and `emu/bp15.lua` — a write watchpoint on the coordinates themselves,
    which cannot be wrong about which routine to watch — named every instruction
    that stores the player's height, and all of them are here.

    Grounded, this is not a physics model at all but a rate limiter: the height
    moves towards the surface by at most 0x80, 0x100 or 0x200 a frame, and
    inside 0x80 it is *placed* on the surface exactly. The falling states are
    where a velocity appears, and there are two of them with different
    accelerations, which is the part no amount of reading would have made
    believable:

    | state | entered when | height | velocity |
    | --- | --- | --- | --- |
    | `0` | landing | rate limiter towards the surface | none |
    | `0x10` | the surface is 0x201..0x400 below | `y += v` until `surface + 0x64 < y` | `+0x50` |
    | `0x20` | the surface is more than 0x400 above | `y += v` until it meets the surface | `+0x0a` from `-0x96` |
    | `0x40` | the surface is more than 0x400 below | `y += v` while the *collision* is clear | `+0x28` from `0x28` |
    | `0x50` | landing out of `0x40` | none: it falls straight through into state 0 | `-0x12c`, for the camera |

    `0x10` and `0x40` are both falls and the shorter one accelerates twice as
    fast. Both were checked against the game frame by frame; see `verify15`.

    Returns (position, state, velocity).
    """
    x, y, z = p
    x, z = x + dx, z + dz

    if state == 0x20:                               # 0x8002ee50, rising
        surf = surface(lvl, x, y, z)
        ny = y + vel
        if not (surf < ny and vel < 0):
            if surf < y:
                ny = surf
            state = 0
        return (x, ny, z), state, s16(vel + 0xA)

    if state == 0x10:                               # 0x8002edf4, a short drop
        surf = surface(lvl, x, y, z)
        ny = y + vel
        if surf + 0x64 < ny:
            return (x, surf, z), 0, s16(vel + 0x50)
        return (x, ny, z), state, s16(vel + 0x50)

    if state == 0x40:                               # 0x8002eec8, a real fall
        ny = y + vel
        mask, surf = query(lvl, x, ny, z)           # the mask, not the surface
        if mask == 0:
            return (x, ny, z), state, s16(vel + 0x28)
        if vel < 0:
            return (x, y, z), state, 0              # into a ceiling: stopped
        landed = surf if vel < 0x200 else surf - (vel >> 1)
        return (x, landed, z), 0x50, vel

    # state 0x50 is the landing recoil and owns no height of its own: after its
    # bookkeeping at 0x8002f068 it falls straight through into state 0's code.
    if state == 0x50:
        vel = s16(vel - 0x12C)
        state = 0 if vel <= 0 else 0x50

    surf = surface(lvl, x, y, z)                    # 0x8002f120, grounded
    if surf >= collision.FAR:
        return (x, y, z), state, vel
    d = surf - y
    if d < 0:                                       # the surface is above: rise
        if d < -0x400:                              # 0x8002f194: too far, launch
            return (x, y, z), 0x20, (-0x96 if momentum < 0xC9 else -0x12C)
        if d < -0x200:
            return (x, y - 0x200, z), state, vel
        if d < -0x100:
            return (x, y - 0x100, z), state, vel
        if d < -0x80:
            return (x, y - 0x80, z), state, vel
        return (x, surf, z), state, vel             # inside 0x80: placed on it
    if d == 0:
        return (x, y, z), state, vel
    if query(lvl, x, y + 1, z)[0]:                  # 0x8002f1e0: blocked below
        return (x, y, z), state, vel
    if d < 0x81:
        return (x, surf, z), state, vel             # inside 0x80: placed on it
    if d < 0x101:
        return (x, y + 0x80, z), state, vel
    if d < 0x201:
        return (x, y + 0x100, z), state, vel
    return (x, y, z), (0x10 if d < 0x401 else 0x40), 0x28


# Every instruction in player_vertical that stores the player's Y, and which
# branch of the model it is. `emu/bp15.lua` reports the one the game took, so
# the check below is not "is the height plausible" but "did we pick the same
# instruction the PlayStation did".
Y_STORE = {
    0x8002F160: "rise 0x80",
    0x8002F168: "rise placed",
    0x8002F17C: "rise 0x100",
    0x8002F190: "rise 0x200",
    0x8002F210: "drop 0x80",
    0x8002F21C: "drop placed",
    0x8002F23C: "drop 0x100",
    0x8002EE10: "state 0x10 move",
    0x8002EE3C: "state 0x10 land",
    0x8002EE78: "state 0x20 move",
    0x8002EE94: "state 0x20 land",
    0x8002EF10: "state 0x40 move",
    0x8002EFF4: "state 0x40 land",
}
# The two that land write Y a second time in the same frame, after the move
# store; they are checked with it rather than on their own.
Y_SECOND = {0x8002EE3C: 0x8002EE10, 0x8002EE94: 0x8002EE78}


def branch(lvl, p, state, vel):
    """Which of `Y_STORE` this frame would take, and the height it would leave.

    The same decisions as `walk_step`, reported rather than applied, so a
    sampled log can be checked line by line without having to replay frames.
    """
    x, y, z = p
    surf = surface(lvl, x, y, z)
    # The two moving states always store the moved height first -- 0x8002ee78 is
    # in a branch's delay slot and 0x8002ee10 is on the straight path -- and only
    # then store the surface again if they landed. So the store a watchpoint sees
    # first is the move, on a landing frame as much as on any other. Expecting
    # the landing store here was the checker's mistake, not the model's, and it
    # cost the run one line out of thirty-seven.
    if state == 0x20:
        return 0x8002EE78, y + vel
    if state == 0x10:
        return 0x8002EE10, y + vel
    if state == 0x40:
        ny = y + vel
        mask, fsurf = query(lvl, x, ny, z)
        if mask == 0:
            return 0x8002EF10, ny
        if vel < 0:
            return None, y
        return 0x8002EFF4, fsurf
    if surf >= collision.FAR:
        return None, y
    d = surf - y
    if d < 0:
        if d < -0x400:
            return None, y                       # goes to state 0x20, no store
        if d < -0x200:
            return 0x8002F190, y - 0x200
        if d < -0x100:
            return 0x8002F17C, y - 0x100
        if d < -0x80:
            return 0x8002F160, y - 0x80
        return 0x8002F168, surf
    if d == 0 or query(lvl, x, y + 1, z)[0]:
        return None, y
    if d < 0x81:
        return 0x8002F21C, surf
    if d < 0x101:
        return 0x8002F210, y + 0x80
    if d < 0x201:
        return 0x8002F23C, y + 0x100
    return None, y                               # goes to state 0x10 or 0x40


BP15 = re.compile(
    r"Y\s+pc=([0-9a-f]{8}) ra=[0-9a-f]{8} n=\s*\d+\s+pos=\s*(-?\d+)\s+"
    r"(-?\d+)\s+(-?\d+)\s+vstate=\s*(\d+) vvel=\s*(-?\d+)\s+"
    r"pstate=\s*(\d+)\s+vel=.*lv=(\d+)")


def verify15(path="out/lua_bp15.log"):
    """Against the stores `emu/bp15.lua` caught the game make.

    A watchpoint samples rather than following every frame, so this does not
    replay a walk. It asks the sharper question instead: at the moment the game
    stored the player's height, with the position, state and velocity it had,
    does the model reach the *same instruction*? There are thirteen of them and
    they are the whole policy, so picking the right one is picking the right
    rule.

    Lines at the two landing stores are skipped: they are a second write in a
    frame whose first write already moved Y, so the height they carry is not a
    frame's starting height.
    """
    rows = []
    if os.path.exists(path):
        for line in open(path):
            m = BP15.match(line)
            if m:
                pc, x, y, z, vs, vv, ps, lv = m.groups()
                rows.append((int(pc, 16), (int(x), int(y), int(z)),
                             int(vs), int(vv), int(ps), int(lv)))
    if not rows:
        print(f"no stores in {path}.\n"
              "Record one: ./emu/run.sh debug bp15.lua, then walk flat ground,\n"
              "stairs up and down, and off a ledge.")
        return 0, 0
    lvls, ok, bad, skipped = {}, 0, {}, 0
    for pc, p, vs, vv, _ps, lv in rows:
        if pc not in Y_STORE or pc in Y_SECOND:
            skipped += 1
            continue
        lvl = lvls.setdefault(lv, level(lv))
        got, _ny = branch(lvl, p, vs, vv)
        if got == pc:
            ok += 1
        else:
            key = (Y_STORE[pc], Y_STORE.get(got, hex(got) if got else "no store"))
            bad[key] = bad.get(key, 0) + 1
    total = ok + sum(bad.values())
    print(f"{ok} of {total} of the game's own height stores chosen exactly "
          f"({ok * 100 // max(total, 1)} %)")
    for (want, got), n in sorted(bad.items()):
        print(f"  game took '{want}', we take '{got}', {n}x")
    if skipped:
        print(f"  ({skipped} lines outside player_vertical or second-in-frame, "
              "not checked)")

    # And the arithmetic, where the log gives consecutive frames of the same
    # store: the height must advance by exactly the velocity and the velocity by
    # exactly the constant. This is what puts a number on 0x50 and 0x0a rather
    # than on the shape of the code.
    ACCEL = {0x8002EE10: 0x50, 0x8002EE78: 0xA, 0x8002EF10: 0x28}
    steps = miss = 0
    prev = {}
    for pc, p, vs, vv, _ps, _lv in rows:
        if pc not in ACCEL:
            prev.pop(pc, None)
            continue
        if pc in prev:
            (py, pv) = prev[pc]
            if py + pv == p[1] and pv + ACCEL[pc] == vv:
                steps += 1
            else:
                miss += 1
        prev[pc] = (p[1], vv)
    if steps or miss:
        print(f"{steps} of {steps + miss} consecutive falling frames advance by "
              f"exactly the velocity, and the velocity by its state's own constant")
    return ok, total


def level(lv):
    if lv == 0:
        return collision.Level(0)
    import maps
    grid = dict(maps.levels())[lv]
    return collision.Level(lv, grid)


def fall(lv=0, cx=None, cz=None, height=0x2000):
    """Drop the player from `height` above the floor and print the arc."""
    lvl = level(lv)
    cx = 40 if cx is None else cx
    cz = 40 if cz is None else cz
    x, z = cx * 0x800 + 0x400, cz * 0x800 + 0x400
    surf = surface(lvl, x, 0, z)
    if surf >= collision.FAR:
        print(f"cell ({cx},{cz}) has no surface — pick another")
        return
    p, state, vel = (x, surf - height, z), 0, 0
    print(f"cell ({cx},{cz}) surface {surf}, dropped from {surf - height}")
    after = None
    for f in range(400):
        p, state, vel = walk_step(lvl, p, 0, 0, state, vel)
        if state == 0 and after is None and f > 2:
            after = 0
        print(f"  frame {f:3d}  y={p[1]:8d}  ({surf - p[1]:6d} above the "
              f"surface)  state {state:#04x}  v={vel:6d}")
        if after is not None:
            after += 1
            if after > 6:
                break


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "model":
        for k in ("R", "BODY", "LAYERS", "GRAVITY", "STEP_UP", "SLIDE_WALL",
                  "SLIDE_STEP", "SOFT", "FALL_V", "FALL_DROP"):
            print(f"  {k:11s} {globals()[k]:#7x}  {globals()[k]}")
    elif arg == "fall":
        fall(int(sys.argv[2]) if len(sys.argv) > 2 else 0,
             *[int(a) for a in sys.argv[3:5]])
    else:
        # `movement.py bp15` is what AGENT.md and TOOLS.md tell you to run, and
        # it was handing "bp15" to open() as a path -- so the acceptance test
        # for the whole vertical model reported "no stores" whether or not a
        # recording existed. A bare name means the log of that name under out/.
        if arg and not os.path.sep in arg and not arg.endswith(".log"):
            arg = f"out/lua_{arg}.log"
        verify15(arg or "out/lua_bp15.log")
