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

**And the rest of `level_overlay_tick`**, after the level's entry 1: story
flag `0x65` -- level 27's creature-death hook sets it (tools/deaths.py) --
at 1 becomes 2, and then by flag `0x66`:

```
0x66 set    warp_to(0xd) -- level 24; the music down, the volume
            (0x801b25dc, OPTION 1's) by 2 a VSync to 0 or 1 on the handle
            (0x800677e8); res_wait; res_upload_wait and level_load while
            level_change_busy is 1; scene 7 (cutscene_number 7, its record
            0x801e8048, str_play: \\STR\\S07.S), cutscene_pending -1, phase 0,
            number 0xff; player_state_reset; the master volume 0x7f;
            object_trigger(0xff, 0xff, 0xff, 9, 0xb, 0x7f, 0x7f, 0x7f); the
            displayed buffer moved onto the one drawn (MoveImage), DrawSync,
            fade_frames(1, 0, 0, 0), res_wait -- and the game goes on
0x66 clear  the music down; the master volume 0; the music stopped if it
            plays; fade_frames(1, 0, 0x1000, 0x100); scene 8 (\\STR\\S08.S);
            and game_exit 4 -- END.EXE with overlay_arg 3, M6 alone
```

**How it is held to the game.** `check()` runs each level's own entry 1 out
of its overlay with `tools/mipsrun.py` over the level as its own loader
leaves it, with the flags, the creatures' categories, states and places
about the player, the player's place and view, the feet, the lake's
switch and its seventeen, object 158's +0x10, the word at 0x8009c21c and
skill 3 at random, `rand` answering a sequence and vec_angle and facing_test
running as the game's: the model must draw as many rolls and leave the same
RAM, all of it but the stack. `whole_check()` runs GAME.EXE's own
level_overlay_tick the same way -- the level's entry 1 reached through its
`jalr` -- with flags `0x65` and `0x66`, the music's volume, word and handle,
level_change_busy and the draw buffer at random too, and what it calls past
the level's code stood in for and logged (warp_to, the music, the frames,
the loads, str_play, player_state_reset, object_trigger, MoveImage, the
fade), level_load clearing level_change_busy after one to three calls: the
model must make the same calls in order, draw as many rolls and leave the
same RAM.
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


FLAG_DONE, FLAG_ON = 0x65, 0x66       # level 27's: the boss dead, thing 0x10 had
MUSIC_VOLUME = 0x801B25DC          # OPTION 1's music volume, a byte
MUSIC_ON, MUSIC = 0x801B0A04, 0x801B0A08
MUSIC_VOL, MUSIC_STOP = 0x800677E8, (0x800677E8, 0x80071F9C, 0x80072CE8)
LEVEL_CHANGE_BUSY = 0x8018FAD4
DRAW_BUFFER, DRAW_ENV, DISP_ENV = 0x801AEAE8, 0x801A91BC, 0x801A9274
CUT_NUMBER, CUT_RECORD = 0x801E8260, 0x801E825C
CUT_PENDING, CUT_PHASE = 0x801E824E, 0x801E824C
SCENES = {7: 0x801E8048, 8: 0x801E807C}   # seq_data + 52 * n
GAME_EXIT = 0x8009C3F8
WARP_ON = 0xD                      # warp_to's record: level 24


def s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def music_down(m):
    """The music's volume down by 2 a VSync from OPTION 1's, (v >> 1) of
    them, on the handle at 0x801b0a08."""
    v = m.rd(MUSIC_VOLUME)
    for _ in range(v >> 1):
        v -= 2
        h = s16(m.rd(MUSIC, 2)) & 0xFFFFFFFF
        a = v if v >= 0 else 0
        m.calls += [("music", MUSIC_VOL, h, a, a), ("draw_sync", 0), ("vsync", 0)]


def scene(m, n):
    """cutscene_number n, its record, str_play (0x80061bc4), and the
    machine left at rest."""
    m.wr(CUT_NUMBER, n)
    m.wr(CUT_RECORD, SCENES[n], 4)
    m.calls.append(("str_play",))
    m.wr(CUT_PENDING, 0xFFFF, 2)
    m.wr(CUT_PHASE, 0, 2)
    m.wr(CUT_NUMBER, 0xFF)


def finale(m, level_load):
    """level_overlay_tick after the level's entry 1: flag 0x65 at 1. The
    warp on to level 24 with flag 0x66, else the short ending.
    `level_load` runs a step of the level's load over `m`."""
    if m.rd(F(FLAG_DONE)) != 1:
        return
    m.wr(F(FLAG_DONE), 2)
    if m.rd(F(FLAG_ON)):
        m.calls.append(("warp_to", WARP_ON))
        music_down(m)
        m.calls.append(("res_wait",))
        while True:
            m.calls += [("res_upload_wait",), ("level_load",)]
            level_load(m)
            if s16(m.rd(LEVEL_CHANGE_BUSY, 2)) != 1:
                break
        scene(m, 7)
        m.calls += [("player_state_reset",), ("volume", 0x7F, 0x7F),
                    ("object_trigger", 0xFF, 0xFF, 0xFF, 9, 0xB, 0x7F, 0x7F, 0x7F)]
        i = m.rd(DRAW_BUFFER)
        m.calls.append(("move_image", (DISP_ENV + 20 * i) & 0xFFFFFFFF,
                        s16(m.rd(DRAW_ENV + 92 * i, 2)) & 0xFFFFFFFF,
                        s16(m.rd(DRAW_ENV + 2 + 92 * i, 2)) & 0xFFFFFFFF))
        m.calls += [("draw_sync", 0), ("fade_frames", 1, 0, 0, 0), ("res_wait",)]
    else:
        music_down(m)
        m.calls.append(("volume", 0, 0))
        if m.rd(MUSIC_ON, 4) == 1:
            h = s16(m.rd(MUSIC, 2)) & 0xFFFFFFFF
            m.calls += [("music", MUSIC_STOP[0], h, 0, 0), ("music", MUSIC_STOP[1], h),
                        ("music", MUSIC_STOP[2], h)]
            m.wr(MUSIC_ON, 0, 4)
        m.calls.append(("fade_frames", 1, 0, 0x1000, 0x100))
        scene(m, 8)
        m.wr(GAME_EXIT, 4, 4)


def overlay_tick(lv, m, rand, level_load):
    """level_overlay_tick whole: the level's entry 1, then the finale."""
    entry1(lv, m, rand)
    finale(m, level_load)


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
    entry 1 -- the bytes it read, the rolls and the bytes it wrote -- and of
    level_overlay_tick whole on four levels, with its calls and the number of
    level_load calls that clear level_change_busy, which godot/selftest.gd
    holds godot/ticks.gd to."""
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
    # level_overlay_tick whole, the flag 0x65 branch both ways, on a few levels
    whole = []
    for lv in (0, 2, 24, 27):
        for cpu, rolls, loads in whole_cases(lv, 12, rng):
            m = Mem(bytes(cpu.ram))
            it = iter(rolls)
            drawn = [0]

            def rand():
                drawn[0] += 1
                return next(it)
            overlay_tick(lv, m, rand, loader(loads))
            whole.append({"level": lv, "rolls": rolls[:drawn[0]], "loads": loads,
                          "read": [[a, v] for a, v in sorted(m.read.items())],
                          "wrote": [[a, m.ram[a & MASK]] for a in sorted(m.written)],
                          "calls": [list(c) for c in m.calls]})
    path = os.path.join(out_dir, "tickcheck.json")
    with open(path, "w") as fh:
        json.dump({"cases": rows, "whole": whole}, fh, separators=(",", ":"))
    return path


# --- level_overlay_tick whole, against GAME.EXE's own --------------------------

LEVEL_OVERLAY_TICK = 0x8005EB20
WARP_TO, RES_WAIT, RES_UPLOAD_WAIT, LEVEL_LOAD = 0x8005C864, 0x80019AB4, 0x80019538, 0x80018358
STR_PLAY_CALL, PLAYER_STATE_RESET = 0x80061BC4, 0x8003078C
VOLUME, OBJECT_TRIGGER, MOVE_IMAGE = 0x800699D8, 0x80017C78, 0x80079E90
FADE_FRAMES, DRAW_SYNC, VSYNC = 0x80046C00, 0x80079BA0, 0x8007910C


def loader(loads):
    """level_load as the check stands it in: level_change_busy 0 at the
    `loads`th call."""
    n = [0]

    def step(m):
        n[0] += 1
        if n[0] == loads:
            m.wr(LEVEL_CHANGE_BUSY, 0, 2)
    return step


def whole_run(cpu, rolls, loads):
    """GAME.EXE's own level_overlay_tick over the machine's RAM: (the rolls
    drawn, [the calls it made past the level's code, in order])."""
    calls = []
    drawn = [0]
    n = [0]

    def rand(c):
        drawn[0] += 1
        return rolls[drawn[0] - 1]

    def load(c):
        calls.append(("level_load",))
        n[0] += 1
        if n[0] == loads:
            c.wr(LEVEL_CHANGE_BUSY, 2, 0)

    def log(*what):
        return lambda c: calls.append(what)
    r = lambda c, k: tuple(c.r[4:4 + k])                                       # noqa: E731
    stack = lambda c, k: tuple(c.rd(c.r[29] + 0x10 + 4 * i, 4) for i in range(k))   # noqa: E731
    cpu.hooks = dict(cpu.hooks)
    cpu.hooks.update({
        RAND: rand,
        WARP_TO: lambda c: calls.append(("warp_to",) + r(c, 1)),
        MUSIC_STOP[0]: lambda c: calls.append(("music", MUSIC_STOP[0]) + r(c, 3)),
        MUSIC_STOP[1]: lambda c: calls.append(("music", MUSIC_STOP[1]) + r(c, 1)),
        MUSIC_STOP[2]: lambda c: calls.append(("music", MUSIC_STOP[2]) + r(c, 1)),
        DRAW_SYNC: lambda c: calls.append(("draw_sync",) + r(c, 1)),
        VSYNC: lambda c: calls.append(("vsync",) + r(c, 1)),
        RES_WAIT: log("res_wait"),
        RES_UPLOAD_WAIT: log("res_upload_wait"),
        LEVEL_LOAD: load,
        STR_PLAY_CALL: log("str_play"),
        PLAYER_STATE_RESET: log("player_state_reset"),
        VOLUME: lambda c: calls.append(("volume",) + r(c, 2)),
        OBJECT_TRIGGER: lambda c: calls.append(("object_trigger",) + r(c, 4) + stack(c, 4)),
        MOVE_IMAGE: lambda c: calls.append(("move_image",) + r(c, 3)),
        FADE_FRAMES: lambda c: calls.append(("fade_frames",) + r(c, 4)),
    })
    cpu.call(LEVEL_OVERLAY_TICK)
    return drawn[0], calls


def whole_cases(lv, n, rng, snap="a1"):
    """`n` runs of level_overlay_tick on level `lv`: [(machine, rolls, loads)]."""
    put = useitem._put
    out = []
    for cpu, rolls in cases(lv, n, rng, snap):
        put(cpu, F(FLAG_DONE), 1, rng.choice((1, 1, 1, 0, 2, rng.randrange(0x100))))
        put(cpu, F(FLAG_ON), 1, rng.choice((0, 0, 1, rng.randrange(0x100))))
        put(cpu, MUSIC_VOLUME, 1, rng.choice((0, 1, 0x50, 0x7F, 0x80, rng.randrange(0x100))))
        put(cpu, MUSIC_ON, 4, rng.choice((0, 1, 1, 2)))
        put(cpu, MUSIC, 2, rng.choice((0, 3, 0xFFFF, rng.randrange(0x10000))))
        put(cpu, LEVEL_CHANGE_BUSY, 2, rng.choice((0, 1, 1)))
        put(cpu, DRAW_BUFFER, 1, rng.choice((0, 1)))
        put(cpu, GAME_EXIT, 4, 0)
        out.append((cpu, rolls, rng.choice((1, 1, 2, 3))))
    return out


def whole_compare(cpu, lv, rolls, loads):
    """One run both ways: (what it did, None) when they agree, else what differs."""
    m = Mem(bytes(cpu.ram))
    it = iter(rolls)
    drawn = [0]

    def rand():
        drawn[0] += 1
        return next(it)
    overlay_tick(lv, m, rand, loader(loads))
    n, got = whole_run(cpu, rolls, loads)
    what = (lv, hash((tuple(m.calls), tuple(sorted((a, m.ram[a & MASK]) for a in m.written
                                                   if m.ram[a & MASK] != m.read.get(a, -1))))))
    if drawn[0] != n:
        return what, f"rolls: model {drawn[0]}, game {n}"
    if m.calls != got:
        return what, f"calls: model {m.calls[:5]}..., game {got[:5]}..."
    a, b = m.ram, cpu.ram
    for lo, hi in ((0, levelin.STACK_LO), (levelin.STACK_HI, len(a))):
        if a[lo:hi] != b[lo:hi]:
            for i in range(lo, hi):
                if a[i] != b[i]:
                    return what, f"{0x80000000 | i:#x}: model {a[i]:#x}, game {b[i]:#x}" \
                        f" ({levelin._where(0x80000000 | i)})"
    return what, None


def whole_check(out=sys.stdout, per_level=40, seed=89, verbose=False):
    """The model against GAME.EXE's own level_overlay_tick on every level."""
    rng = random.Random(seed)
    ok = n = 0
    ways = {"rest": 0, "on": 0, "end": 0}
    told = False
    for lv in range(28):
        try:
            runs = whole_cases(lv, per_level, rng)
        except Exception as e:                                     # noqa: BLE001
            print(f"  level {lv}: no machine ({e})", file=out)
            continue
        for cpu, rolls, loads in runs:
            n += 1
            done, on = cpu.rd(F(FLAG_DONE), 1), cpu.rd(F(FLAG_ON), 1)
            what, why = whole_compare(cpu, lv, rolls, loads)
            if why is None:
                ok += 1
                ways["rest" if done != 1 else "on" if on else "end"] += 1
            elif not told or verbose:
                told = True
                print(f"  level {lv}: {why}", file=out)
    print(f"level_overlay_tick whole, against GAME.EXE's own over 28 levels: {ok} of {n} runs "
          f"agree -- the rolls, the calls in order and all of RAM but the stack ({ways['end']} "
          f"short endings, {ways['on']} warps on, {ways['rest']} with flag 0x65 not 1)", file=out)
    return ok == n


def main():
    a = sys.argv[1:]
    if "--export" in a:
        print(export(a[a.index("--export") + 1] if len(a) > a.index("--export") + 1
                     else os.path.join(useitem.ROOT, "out", "godot")))
        return
    if "--check" in a:
        one = check(verbose="-v" in a)
        two = whole_check(verbose="-v" in a)
        sys.exit(0 if one and two else 1)
    print(__doc__.split("**How it is held")[0])


if __name__ == "__main__":
    main()
