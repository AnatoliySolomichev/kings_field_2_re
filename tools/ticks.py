#!/usr/bin/env python3
"""What a level does every frame: every level's entry 1, against the overlays' own.

    python3 tools/ticks.py            what each level's entry 1 does
    python3 tools/ticks.py --check    the model against the overlays' own code
    python3 tools/ticks.py --export D tickcheck.json for the self-test

**Entry 1** (`level_hooks + 4`) is what `level_overlay_tick` (`0x8005eb20`),
seventh in game_main's frame, calls before anything else, once a frame of
the game. Twenty-two levels' is `jr $ra`; six do something:

```
level 0   rand() under 0x2000: object 158's +0x10 (u16) moves by 16 times the
          word at 0x8009c21c, which turns over past 0x800 and the halfword
          back to 0 at 0x1000 -- a flicker the port does not draw. With story
          flags 1 and 2 set and 7 clear, the three men by the house: once the
          player is "far" from man 1, men 0 and 1 held (category 8) and man 2
          up (1). "Far" is the source's `dx ^ 2 + dz ^ 2 >= 401` with dx, dz
          the cells from the player to man 1 (truncated, as C divides) --
          which C reads as dx ^ (dz + 2) ^ 2, an exclusive or: the compiler
          kept the slip (0x801e86c0: addiu 2, xor, xori 2). Whenever dx is
          below 0, never.
level 1   flag 0xa set and 0xb clear, the player 20 cells or more from
          creature 20 (dx*dx + dz*dz >= 401, the squares this time): flag 0xb
          1, creatures 20, 25 and 40 held, 10, 23 and 24 up -- the son cured
          (entry 2's blood herb) and gone home once out of sight
level 2   the feet not in the aquarian boots (0x4b, 0x801b25d8): once
          (object 82's +0x40 to 1), every one of objects 100..116 (opcode
          0x5f) whose +0x3f is not 1 gets +0x3f 1 and state 1; in them, object
          82 (opcode 0xa6, the lake's switch) at rest with +0x40 set gets state
          4, and +0x40 0 -- the switch's pattern laid again
level 8   flags 0x2c 1 and 0x2e 0 (the word at 0x2c masked 0xff00ff, so
          0x2d is not asked), creature 1 not in state 1, and the
          view (0x801b260a) not within 0x258 of the way to it (facing_test,
          vec_angle): creature 1 state 0 and category 2 -- it appears when
          the player looks away
level 17  the same for creature 15 by flag 0x51; and every frame creature
          56's +3 (its floor) 0
level 26  skill 3 not 0 and flag 0x5f clear: flag 0x5f 1
```

**How it is held to the game.** `check()` runs each level's own entry 1 out
of its overlay with `tools/mipsrun.py` over the level as its own loader
leaves it, with the flags, the creatures' categories, states and places
about the player, the player's place and view, the feet, the lake's
switch and its seventeen, object 158's +0x10, the word at 0x8009c21c and
skill 3 at random, `rand` answering a sequence and vec_angle and facing_test
running as the game's: the model must draw as many rolls and leave the same
RAM, all of it but the stack.
"""
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import levelin                                                       # noqa: E402
import useitem                                                       # noqa: E402
from levelin import A, F, O, MASK, Mem                               # noqa: E402

ENTRY = 1                          # level_hooks + 4
RAND = 0x800796C0
PLAYER_POS = 0x801B25F0            # x, y, z
VIEW_YAW = 0x801B260A              # view_angles + 2, s16
FEET = 0x801B25D8                  # equip_armour's slot 3
SKILL_3 = 0x801B251E
FLICKER = 0x8009C21C               # level 0's word: +1 or -1, 16 a step
FAR = 0x191                        # 401: 20 cells, squared
BOOTS = 0x4B
SWITCH, STONES = 82, range(100, 117)


def s32(v):
    v &= 0xFFFFFFFF
    return v - 0x100000000 if v & 0x80000000 else v


def cells(a, b):
    """(a - b) / 2048 as C divides: toward 0."""
    d = s32(a - b)
    return (d + 0x7FF if d < 0 else d) >> 11


def _faced(m, k):
    """facing_test(view yaw, vec_angle(creature k - player), 0x258)."""
    import ai
    dx = s32(m.rd(A(k, 0x2C), 4) - m.rd(PLAYER_POS, 4))
    dz = s32(m.rd(A(k, 0x34), 4) - m.rd(PLAYER_POS + 8, 4))
    b = ai.vec_angle(dx, dz) & 0xFFFF
    b = b - 0x10000 if b & 0x8000 else b
    yaw = m.rd(VIEW_YAW, 2)
    yaw = yaw - 0x10000 if yaw & 0x8000 else yaw
    return ai.facing_test(yaw, b, 0x258)


def _appear(m, k):
    """Level 8's and 17's: creature k not in state 1 and not in view --
    state 0, category 2."""
    if m.rd(A(k, 9)) == 1:
        return
    if not _faced(m, k):
        m.wr(A(k, 9), 0)
        m.wr(A(k), 2)


def entry1(lv, m, rand):
    """Level `lv`'s entry 1 over the RAM `m`; `rand` answers as the game's."""
    f = lambda k: m.rd(F(k))                                     # noqa: E731
    if lv == 0:
        if s32(rand()) < 0x2000:
            a = O(158, 0x10)
            m.wr(a, m.rd(a, 2) + (m.rd(FLICKER, 4) << 4), 2)
        v = m.rd(O(158, 0x10), 2)
        if v > 0x800:
            m.wr(FLICKER, -s32(m.rd(FLICKER, 4)), 4)
            if v >= 0x1000:
                m.wr(O(158, 0x10), 0, 2)
        if f(1) and f(2) and not f(7):
            dx = cells(m.rd(A(1, 0x2C), 4), m.rd(PLAYER_POS, 4))
            dz = cells(m.rd(A(1, 0x34), 4), m.rd(PLAYER_POS + 8, 4))
            if s32(dx ^ (dz + 2) ^ 2) >= FAR:              # dx ^ 2 + dz ^ 2, as C reads it
                m.wr(A(0), 8)
                m.wr(A(1), 8)
                m.wr(A(2), 1)
    elif lv == 1:
        if f(0xA) and not f(0xB):
            dx = cells(m.rd(A(20, 0x2C), 4), m.rd(PLAYER_POS, 4))
            dz = cells(m.rd(A(20, 0x34), 4), m.rd(PLAYER_POS + 8, 4))
            if s32(dx * dx + dz * dz) >= FAR:
                m.wr(F(0xB), 1)
                levelin.cats(m, ((20, 8), (10, 1), (25, 8), (23, 1), (24, 1), (40, 8)))
    elif lv == 2:
        if m.rd(FEET) != BOOTS:
            if m.rd(O(SWITCH, 0x40)) != 1:
                for k in STONES:
                    if m.rd(O(k, 0x3F)) != 1:
                        m.wr(O(k, 0x3F), 1)
                        m.wr(O(k, 8), 1, 2)
            m.wr(O(SWITCH, 0x40), 1)
        else:
            if m.rd(O(SWITCH, 8), 2) == 0 and m.rd(O(SWITCH, 0x40)):
                m.wr(O(SWITCH, 8), 4, 2)
            m.wr(O(SWITCH, 0x40), 0)
    elif lv == 8:
        if m.rd(F(0x2C), 4) & 0xFF00FF == 1:        # flags 0x2c and 0x2e; 0x2d not asked
            _appear(m, 1)
    elif lv == 17:
        if f(0x51) == 1:
            _appear(m, 15)
        m.wr(A(56, 3), 0)
    elif lv == 26:
        if m.rd(SKILL_3, 2) and not f(0x5F):
            m.wr(F(0x5F), 1)


# --- against the overlays' own ---------------------------------------------------

def game_run(cpu, rolls):
    """The overlay's own entry 1 over the machine's RAM, rand answering
    `rolls` in turn: the number drawn."""
    drawn = [0]

    def rand(c):
        drawn[0] += 1
        return rolls[drawn[0] - 1]
    hooks = struct.unpack_from("<I", cpu.ram, useitem.LEVEL_HOOKS & MASK)[0]
    entry = struct.unpack_from("<I", cpu.ram, (hooks + 4 * ENTRY) & MASK)[0]
    cpu.hooks = dict(cpu.hooks)
    cpu.hooks[RAND] = rand
    cpu.call(entry)
    return drawn[0]


# the creatures each level's entry 1 asks about
WHO = {0: (0, 1, 2), 1: (20, 10, 25, 23, 24, 40), 8: (1,), 17: (15, 56)}
NEAR = {0: 1, 1: 20, 8: 1, 17: 15}


def cases(lv, n, rng, snap="a1"):
    """`n` runs of level `lv`'s entry 1: [(the machine, the rolls)]."""
    import mipsrun
    base = mipsrun.level_cpu(lv, snap)
    ram0 = bytes(base.ram)
    put = useitem._put
    out = []
    for _ in range(n):
        cpu = mipsrun.CPU(ram0)
        cpu.hooks.update(base.hooks)
        for k in (1, 2, 7, 0xA, 0xB, 0x2C, 0x2D, 0x2E, 0x2F, 0x51, 0x5F):
            put(cpu, F(k), 1, rng.choice((0, 0, 1, 1, 1, 2, rng.randrange(0x100))))
        px, pz = rng.randrange(0x40000), rng.randrange(0x40000)
        put(cpu, PLAYER_POS, 4, px)
        put(cpu, PLAYER_POS + 4, 4, rng.randrange(-0x2000, 0x2000))
        put(cpu, PLAYER_POS + 8, 4, pz)
        put(cpu, VIEW_YAW, 2, rng.randrange(0x10000))
        for k in WHO.get(lv, ()):
            put(cpu, A(k), 1, rng.choice((1, 2, 8, 0xFF)))
            put(cpu, A(k, 3), 1, rng.randrange(4))
            put(cpu, A(k, 9), 1, rng.choice((0, 1, 1, 2, 3)))
            reach = rng.choice((0x800, 0x8000, 0x10000, 0x20000))
            put(cpu, A(k, 0x2C), 4, px + rng.randrange(-reach, reach))
            put(cpu, A(k, 0x34), 4, pz + rng.randrange(-reach, reach))
        put(cpu, FEET, 1, rng.choice((BOOTS, BOOTS, 0xFF, rng.randrange(0x100))))
        put(cpu, O(SWITCH, 8), 2, rng.choice((0, 0, 1, 2, 3, 4)))
        put(cpu, O(SWITCH, 0x40), 1, rng.choice((0, 1, 0xFF, 2)))
        for k in STONES:
            put(cpu, O(k, 8), 2, rng.choice((0, 1, 2, 3, 0x63)))
            put(cpu, O(k, 0x3F), 1, rng.choice((0, 1, 1, 2)))
        put(cpu, O(158, 0x10), 2, rng.choice((0, 0x7F8, 0x800, 0x808, 0xFF8, 0x1000,
                                              rng.randrange(0x10000))))
        put(cpu, FLICKER, 4, rng.choice((1, -1, 1, rng.randrange(1 << 32))))
        put(cpu, SKILL_3, 2, rng.choice((0, 0, 1, 0x20)))
        rolls = [rng.randrange(0x8000) for _ in range(4)]
        out.append((cpu, rolls))
    return out


def compare(cpu, lv, rolls):
    """One run both ways: (what it did, None) when they agree, else what differs."""
    m = Mem(bytes(cpu.ram))
    it = iter(rolls)
    drawn = [0]

    def rand():
        drawn[0] += 1
        return next(it)
    entry1(lv, m, rand)
    n = game_run(cpu, rolls)
    what = (lv, tuple(sorted((a, m.ram[a & MASK]) for a in m.written
                             if m.ram[a & MASK] != m.read.get(a, -1))))
    if drawn[0] != n:
        return what, f"rolls: model {drawn[0]}, game {n}"
    a, b = m.ram, cpu.ram
    for lo, hi in ((0, levelin.STACK_LO), (levelin.STACK_HI, len(a))):
        if a[lo:hi] != b[lo:hi]:
            for i in range(lo, hi):
                if a[i] != b[i]:
                    return what, f"{0x80000000 | i:#x}: model {a[i]:#x}, game {b[i]:#x}" \
                        f" ({levelin._where(0x80000000 | i)})"
    return what, None


def check(out=sys.stdout, per_level=60, seed=71, verbose=False):
    """The model against every level's own entry 1."""
    rng = random.Random(seed)
    ok = n = 0
    seen = {}
    told = False
    for lv in range(28):
        try:
            runs = cases(lv, per_level, rng)
        except Exception as e:                                     # noqa: BLE001
            print(f"  level {lv}: no machine ({e})", file=out)
            continue
        for cpu, rolls in runs:
            n += 1
            what, why = compare(cpu, lv, rolls)
            if why is None:
                ok += 1
                seen[what] = seen.get(what, 0) + 1
            elif not told or verbose:
                told = True
                print(f"  level {lv}: {why}", file=out)
    for lv in range(28):
        ways = [w for w in seen if w[0] == lv]
        if len(ways) > 1:
            print(f"  level {lv:2d}: {sum(seen[w] for w in ways):4d} runs, {len(ways)} different "
                  f"outcomes", file=out)
    print(f"entry 1, against the overlays' own over 28 levels: {ok} of {n} runs agree -- "
          f"the rolls drawn and all of RAM but the stack", file=out)
    return ok == n


def export(out_dir, per_level=20, seed=73):
    """tickcheck.json: runs of the model over the six levels that have an
    entry 1 -- the bytes it read, the rolls and the bytes it wrote -- which
    godot/selftest.gd holds godot/ticks.gd to."""
    import json
    rng = random.Random(seed)
    rows = []
    for lv in (0, 1, 2, 8, 17, 26):
        for cpu, rolls in cases(lv, per_level, rng):
            m = Mem(bytes(cpu.ram))
            it = iter(rolls)
            drawn = [0]

            def rand():
                drawn[0] += 1
                return next(it)
            entry1(lv, m, rand)
            rows.append({"level": lv, "rolls": rolls[:drawn[0]],
                         "read": [[a, v] for a, v in sorted(m.read.items())],
                         "wrote": [[a, m.ram[a & MASK]] for a in sorted(m.written)]})
    path = os.path.join(out_dir, "tickcheck.json")
    with open(path, "w") as fh:
        json.dump({"cases": rows}, fh, separators=(",", ":"))
    return path


def main():
    a = sys.argv[1:]
    if "--export" in a:
        print(export(a[a.index("--export") + 1] if len(a) > a.index("--export") + 1
                     else os.path.join(useitem.ROOT, "out", "godot")))
        return
    if "--check" in a:
        sys.exit(0 if check(verbose="-v" in a) else 1)
    print(__doc__.split("**How it is held")[0])


if __name__ == "__main__":
    main()
