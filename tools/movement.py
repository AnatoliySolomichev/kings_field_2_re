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


def horizontal(lvl, p, angle, dist):
    """`player_horizontal` (`0x8002e3f8`): a step of `dist` along `angle`.

    X takes the cosine and Z the sine, both shifted right by 12, and the whole
    step is refused if the collision at the destination is not clear. The
    *slide* along a refused wall is not modelled: it turns on the wall's own
    facing, which `tile_collision` leaves at `0x801e6498` and `0x801e649c` and
    which `tools/collision.py` does not compute. Until it does, a step into a
    wall stops dead here where the game would slide along it.

    The caller (`0x8002f9bc`) makes this call twice a frame: once at `angle`
    with the forward distance and once at `angle + 0x400` with the strafe.
    """
    x, y, z = p
    nx = x + ((game_cos(angle) * dist) >> 12)
    nz = z + ((game_sin(angle) * dist) >> 12)
    if query(lvl, nx, y, nz)[0]:
        return (x, y, z), False
    return (nx, y, nz), True


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
        verify15(sys.argv[1] if len(sys.argv) > 1 else "out/lua_bp15.log")
