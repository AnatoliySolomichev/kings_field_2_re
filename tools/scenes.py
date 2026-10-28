#!/usr/bin/env python3
"""The scenes: cutscene_step, the rectangles that start them (opcode 0xe4) and every level's entry 10, against the game's own.

    python3 tools/scenes.py            the scene records and where each starts
    python3 tools/scenes.py --check    the three models against the game's own code
    python3 tools/scenes.py --export D scenes.json and scenecheck.json for the port

**What starts a scene.** Opcode `0xe4` (`object_interpreter+0x3998`,
0x8004a9a8) is a rectangle of cells -- the record's `+0x14 >> 11`, `+0x1c >>
11`, `+0x38` by `+0x39`, the height not asked (0x8000) -- naming a scene at
`+0x3a`. With no scene under way (`cutscene_number` 0xff) and the player in
it: `cutscene_phase` 1 and the number. With its own scene the number and the
player out of it: the number back to 0xff if the phase is 0 (the scene over,
or never begun) or 0x10 (refused by its mark). Nine such rectangles, on the
seven levels that have an entry 10:

```
level 2   object 97   (13, 9)  1x1   scene 15     level 20  object 6   (38, 16) 3x2  scene 5
level 4   object 93   (22, 10) 1x1   scene 12               object 7   (39, 6)  1x1  scene 10
level 13  object 58   (55, 24) 1x1   scene 13     level 24  object 138 (6, 46)  3x1  scene 6
          object 85   (50, 6)  3x4   scene 4      level 26  object 172 (54, 69) 1x1  scene 14
level 17  object 84   (68, 43) 3x3   scene 9
```

(A conversation's inn starts one too, `script_interpreter`'s service arm, and
level_overlay_tick its two, tools/ticks.py.)

**cutscene_step** (0x80061940), from game_main every frame and from
player_controller's state 8: nothing while the number is 0xff; else
`cutscene_record` = seq_data (0x801e7edc) + 52 * number, and by the phase
(`lh`, below 0x11 unsigned):

```
1     the record's +1, its mark: 0xff none -- 2; bit 0x80, the flag set -- 2,
      clear 0x10; else the flag clear 2, set 0x10. 2 starts the player's
      walk to the scene's place (state 7, sub_80030810 with the number)
2     cutscene_pending 1 -- the walk over -- phase 4; pending 0
4     the level's entry 10 with the number, str_play (the movie: the
      record's +0, \\STR\\Snn.S under 0x10, a dream above); with story flag
      0x5d at 1 (level 24's entry 10 sets it), the flag 2, pending 1, the
      phase 0 and the number 0xff, player_state_reset, the screen moved,
      DrawSync and warp_to(0xc); then the phase 8 either way and the walk
      back (state 9, sub_80030864)
8     pending 1 -- the walk back over -- phase 0 and the level's entry 7
      with the number; pending 0
16    phase 1 again
```

**Entry 10** (`level_hooks + 0x28`), before the movie, with the scene:

```
level 2   scene 15: flag 0x6f        level 4   scene 12: flag 0x6d
level 13  scene 4: flag 0x42 set, object 20 freed (+6 0xff), creature 30
          held (8) and gone (+9 3); scene 13: flag 0x6e
level 17  scene 9: object 50's +0 0, objects 52..61's +0 2, stamp_rect(2,
          0x3b, 0x4c, 0x47, 0x30, 3, 4, 0, 0x2f), creature 56 up (2) at
          state 0
level 20  scene 5: stamp_rect(2, 0x4d, 0, 0x26, 0xc, 3, 5, 0, 0x2f); scene
          10: with thing 0x7d, 0x7d taken, 0x10 given -- the sword level 27's
          ending asks after -- and flag 0x59
level 24  any scene: flag 0x5d -- cutscene_step's warp after scene 6
level 26  scene 14: flag 0x70
```

**How it is held to the game.** `step_check()` runs GAME.EXE's own
cutscene_step over a level as its loader leaves it, the number, the phase,
pending, the marks, flag 0x5d and the player's view at random, its own
sub_80030810, sub_80030864 and player_state_reset run, the level's entries
10 and 7, str_play, MoveImage, DrawSync and warp_to stood in for and logged:
the model must make the same calls in order and leave the same RAM, all of
it but the stack. `arm_check()` runs object_interpreter's own arm for every
0xe4 record with the player in and about it and the number and phase at
random (mipsrun.object_arm). `entry_check()` runs every level's own entry 10
out of its overlay, the scene, the flags, the objects and creatures it
writes and the pack at random, GAME.EXE's has_item, take_item and give_item
run, stamp_rect logged.
"""
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import givetake                                                      # noqa: E402
import levelin                                                       # noqa: E402
import triggers                                                      # noqa: E402
import useitem                                                       # noqa: E402
from levelin import A, F, O, MASK, Mem                               # noqa: E402

SEQ_DATA, STRIDE = 0x801E7EDC, 52
CUT_NUMBER, CUT_RECORD = 0x801E8260, 0x801E825C
CUT_PENDING, CUT_PHASE = 0x801E824E, 0x801E824C
FLAG_WARP = 0x5D                   # level 24's entry 10 sets it: warp_to(0xc) after
PLAYER_STATE, SCENE_ARG, WALK = 0x801B25E5, 0x801B266C, 0x801B266D
VIEW, SAVED = 0x801B2610, 0x801B266E   # pitch, facing, roll, +6: kept as the walk starts
RESET_HALVES = (0x2648, 0x2646, 0x261C, 0x261A, 0x2618, 0x2624, 0x2622, 0x2620,
                0x262C, 0x262A, 0x2628)  # player_state_reset's, under 0x801b0000
DRAW_BUFFER, DRAW_ENV, DISP_ENV = 0x801AEAE8, 0x801A91BC, 0x801A9274
SCENE_OP = 0xE4
ENTRY_SCENE, ENTRY_AFTER = 10, 7   # level_hooks + 0x28 and + 0x1c

CUTSCENE_STEP = 0x80061940
STR_PLAY, MOVE_IMAGE, DRAW_SYNC, WARP_TO = 0x80060D20, 0x80079E90, 0x80079BA0, 0x8005C864
STAMP_RECT = 0x800445B8

# FDAT entry 97's seventh length-prefixed block is the table (tools/story.py)
CUT_TABLE_ENTRY, CUT_BLOCK = 97, 6


def s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def records():
    """The sixteen 52-byte scene records off the disc, as init_level_state
    lays them at seq_data."""
    from tarc import TArc
    import placement
    raw = TArc(placement.FDAT).raw(CUT_TABLE_ENTRY)
    p, blocks = 0, []
    while p + 4 <= len(raw):
        ln = struct.unpack_from("<I", raw, p)[0]
        if ln == 0 or p + 4 + ln > len(raw):
            break
        blocks.append(bytes(raw[p + 4:p + 4 + ln]))
        p += 4 + ln
    t = blocks[CUT_BLOCK]
    return [t[i * STRIDE:(i + 1) * STRIDE] for i in range(len(t) // STRIDE)]


# --- the models -------------------------------------------------------------------

def player_state(m, st, n):
    """sub_800307f4 (8), sub_80030810 (7), sub_80030864 (9): the state and
    its scene; 7 and 9 also zero the walk's count and keep the view's eight
    bytes from 0x801b2610 at 0x801b266e."""
    m.wr(PLAYER_STATE, st)
    m.wr(SCENE_ARG, n)
    if st == 8:
        return
    m.wr(WALK, 0)
    for i in range(8):
        m.wr(SAVED + i, m.rd(VIEW + i))


def state_reset(m):
    """player_state_reset (0x8003078c): state 0, both speeds, the three view
    offsets of each kind and the nod 0."""
    m.wr(PLAYER_STATE, 0)
    for lo in RESET_HALVES:
        m.wr(0x801B0000 + lo, 0, 2)


def step(m, entry):
    """cutscene_step over `m`. `entry(n, k)` is the level's entry n with k."""
    n = m.rd(CUT_NUMBER)
    if n == 0xFF:
        return
    rec = SEQ_DATA + STRIDE * n
    m.wr(CUT_RECORD, rec, 4)
    ph = m.rd(CUT_PHASE, 2)              # lh, then unsigned below 0x11
    if ph >= 0x11:
        return
    if ph == 1:
        b = m.rd(rec + 1)
        if b == 0xFF:
            v = 2
        elif b & 0x80:
            v = 2 if m.rd(F(b & 0x7F)) else 0x10
        else:
            v = 0x10 if m.rd(F(b)) else 2
        m.wr(CUT_PHASE, v, 2)
        if v == 2:
            player_state(m, 7, n)
    elif ph == 2:
        if s16(m.rd(CUT_PENDING, 2)) == 1:
            m.wr(CUT_PHASE, 4, 2)
        m.wr(CUT_PENDING, 0, 2)
    elif ph == 4:
        entry(ENTRY_SCENE, n)
        m.calls.append(("str_play",))
        if m.rd(F(FLAG_WARP)) == 1:
            m.wr(F(FLAG_WARP), 2)
            m.wr(CUT_PENDING, 1, 2)
            m.wr(CUT_PHASE, 0, 2)
            m.wr(CUT_NUMBER, 0xFF)
            state_reset(m)
            i = m.rd(DRAW_BUFFER)
            m.calls.append(("move_image", (DISP_ENV + 20 * i) & 0xFFFFFFFF,
                            s16(m.rd(DRAW_ENV + 92 * i, 2)) & 0xFFFFFFFF,
                            s16(m.rd(DRAW_ENV + 2 + 92 * i, 2)) & 0xFFFFFFFF))
            m.calls += [("draw_sync", 0), ("warp_to", 0xC)]
        m.wr(CUT_PHASE, 8, 2)
        player_state(m, 9, n)
    elif ph == 8:
        if s16(m.rd(CUT_PENDING, 2)) == 1:
            m.wr(CUT_PHASE, 0, 2)
            entry(ENTRY_AFTER, n)
        m.wr(CUT_PENDING, 0, 2)
    elif ph == 16:
        m.wr(CUT_PHASE, 1, 2)


def arm(m, k):
    """Opcode 0xe4's arm for the record in slot k."""
    r = O(k)
    cx = useitem.s32(m.rd(r + 0x14, 4)) >> 11
    cz = useitem.s32(m.rd(r + 0x1C, 4)) >> 11
    w, h = m.rd(r + 0x38), m.rd(r + 0x39)
    n = m.rd(CUT_NUMBER)
    if n == 0xFF:
        if triggers.player_in_rect(m, cx, cz, w, h):
            m.wr(CUT_PHASE, 1, 2)
            m.wr(CUT_NUMBER, m.rd(r + 0x3A))
    elif n == m.rd(r + 0x3A):
        if not triggers.player_in_rect(m, cx, cz, w, h):
            ph = s16(m.rd(CUT_PHASE, 2))
            if ph == 0 or ph == 0x10:
                m.wr(CUT_NUMBER, 0xFF)


def stamp(m, *args):
    m.calls.append(("stamp",) + args)


def entry10(lv, m, n):
    """Level `lv`'s entry 10 with scene `n`, over `m`."""
    n &= 0xFF
    if lv == 2:
        if n == 0xF:
            m.wr(F(0x6F), 1)
    elif lv == 4:
        if n == 0xC:
            m.wr(F(0x6D), 1)
    elif lv == 13:
        if n == 4 and m.rd(F(0x42)):
            m.wr(O(20, 6), 0xFF, 2)
            m.wr(A(30), 8)
            m.wr(A(30, 9), 3)
        if n == 0xD:
            m.wr(F(0x6E), 1)
    elif lv == 17:
        if n == 9:
            m.wr(O(50), 0)
            for k in range(52, 62):
                m.wr(O(k), 2)
            stamp(m, 2, 0x3B, 0x4C, 0x47, 0x30, 3, 4, 0, 0x2F)
            m.wr(A(56, 9), 0)
            m.wr(A(56), 2)
    elif lv == 20:
        if n == 5:
            stamp(m, 2, 0x4D, 0, 0x26, 0xC, 3, 5, 0, 0x2F)
        if n == 0xA and m.has(0x7D) > 0:
            givetake.take_item(lv, m, 0x7D)
            givetake.give_item(lv, m, 0x10)
            m.wr(F(0x59), 1)
    elif lv == 24:
        m.wr(F(FLAG_WARP), 1)
    elif lv == 26:
        if n == 0xE:
            m.wr(F(0x70), 1)


ENTRY10_LEVELS = (2, 4, 13, 17, 20, 24, 26)


# --- against the game's own ------------------------------------------------------

def _stack(c, n):
    return tuple(c.rd(c.r[29] + 0x10 + 4 * i, 4) for i in range(n))


def _entry(cpu, n):
    hooks = struct.unpack_from("<I", cpu.ram, useitem.LEVEL_HOOKS & MASK)[0]
    return struct.unpack_from("<I", cpu.ram, (hooks + 4 * n) & MASK)[0]


def step_run(cpu):
    """GAME.EXE's own cutscene_step: [the calls it made that the model logs]."""
    calls = []
    r = lambda c, k: tuple(c.r[4:4 + k])                                       # noqa: E731
    cpu.hooks = dict(cpu.hooks)
    cpu.hooks.update({
        _entry(cpu, ENTRY_SCENE): lambda c: calls.append(("entry", ENTRY_SCENE, c.r[4])),
        _entry(cpu, ENTRY_AFTER): lambda c: calls.append(("entry", ENTRY_AFTER, c.r[4])),
        STR_PLAY: lambda c: calls.append(("str_play",)),
        MOVE_IMAGE: lambda c: calls.append(("move_image",) + r(c, 3)),
        DRAW_SYNC: lambda c: calls.append(("draw_sync",) + r(c, 1)),
        WARP_TO: lambda c: calls.append(("warp_to",) + r(c, 1)),
    })
    cpu.call(CUTSCENE_STEP)
    return calls


MARKS = (0x09, 0x43, 0x57, 0x5D, 0x54, 0x58, 0x7B, 0x7C, 0x7D, 0x7E)


def step_cases(lv, n, rng, snap="a1"):
    import mipsrun
    base = mipsrun.level_cpu(lv, snap)
    ram0 = bytes(base.ram)
    put = useitem._put
    out = []
    for _ in range(n):
        cpu = mipsrun.CPU(ram0)
        cpu.hooks.update(base.hooks)
        put(cpu, CUT_NUMBER, 1, rng.choice(list(range(16)) + [0xFF, 0xFF, rng.randrange(0x100)]))
        put(cpu, CUT_PHASE, 2, rng.choice((0, 1, 1, 2, 2, 4, 4, 8, 8, 0x10, 0x10, 3,
                                           rng.randrange(0x12), 0xFFFF)))
        put(cpu, CUT_PENDING, 2, rng.choice((0, 1, 1, 0xFFFF, 2)))
        for f in MARKS:
            put(cpu, F(f), 1, rng.choice((0, 0, 1, 2, rng.randrange(0x100))))
        put(cpu, F(FLAG_WARP), 1, rng.choice((0, 1, 1, 2)))
        put(cpu, PLAYER_STATE, 1, rng.choice((0, 7, 8, 9, 0x10)))
        for i in range(8):
            put(cpu, VIEW + i, 1, rng.randrange(0x100))
        put(cpu, DRAW_BUFFER, 1, rng.choice((0, 1)))
        out.append(cpu)
    return out


def step_compare(cpu):
    m = Mem(bytes(cpu.ram))
    step(m, lambda n, k: m.calls.append(("entry", n, k)))
    got = step_run(cpu)
    what = hash((tuple(m.calls), tuple(sorted((a, m.ram[a & MASK]) for a in m.written
                                              if m.ram[a & MASK] != m.read.get(a, -1)))))
    if m.calls != got:
        return what, f"calls: model {m.calls}, game {got}"
    return what, _ram_diff(m.ram, cpu.ram)


def _ram_diff(a, b):
    for lo, hi in ((0, levelin.STACK_LO), (levelin.STACK_HI, len(a))):
        if a[lo:hi] != b[lo:hi]:
            for i in range(lo, hi):
                if a[i] != b[i]:
                    return (f"{0x80000000 | i:#x}: model {a[i]:#x}, game {b[i]:#x} "
                            f"({levelin._where(0x80000000 | i)})")
    return None


def arm_cases(lv, n, rng, snap="a1"):
    """`n` runs of each 0xe4 record of level `lv`: [(the machine, the slot)]."""
    import mipsrun
    import objload
    ks = [k for k, o in sorted(objload.Load(lv).recs.items()) if o["op"] == SCENE_OP]
    if not ks:
        return []
    base = mipsrun.level_cpu(lv, snap)
    ram0 = bytes(base.ram)
    put = useitem._put
    out = []
    for k in ks:
        r = O(k)
        for _ in range(n):
            cpu = mipsrun.CPU(ram0)
            cpu.hooks.update(base.hooks)
            cx = useitem.s32(cpu.rd(r + 0x14, 4)) >> 11
            cz = useitem.s32(cpu.rd(r + 0x1C, 4)) >> 11
            w, h, sc = cpu.rd(r + 0x38, 1), cpu.rd(r + 0x39, 1), cpu.rd(r + 0x3A, 1)
            if rng.random() < 0.6:
                px = (cx + rng.randrange(max(w, 1))) * 0x800 + rng.randrange(0x800)
                pz = (cz + rng.randrange(max(h, 1))) * 0x800 + rng.randrange(0x800)
            else:
                px = (cx - 2 + rng.randrange(w + 4)) * 0x800 + rng.randrange(0x800)
                pz = (cz - 2 + rng.randrange(h + 4)) * 0x800 + rng.randrange(0x800)
            put(cpu, triggers.PLAYER_POS, 4, px)
            put(cpu, triggers.PLAYER_POS + 4, 4, rng.randrange(-0x4000, 0x4000))
            put(cpu, triggers.PLAYER_POS + 8, 4, pz)
            put(cpu, CUT_NUMBER, 1, rng.choice((0xFF, 0xFF, sc, sc, rng.randrange(16))))
            put(cpu, CUT_PHASE, 2, rng.choice((0, 0, 1, 2, 4, 8, 0x10, 0x10, rng.randrange(0x12))))
            out.append((cpu, k))
    return out


def arm_compare(cpu, k):
    import mipsrun
    m = Mem(bytes(cpu.ram))
    m.wr(0x80198394, O(k), 4)
    m.wr(0x80198390, useitem.TYPES + 24 * m.rd(O(k, 6), 2), 4)
    arm(m, k)
    calls = []
    cpu.hooks = dict(cpu.hooks)
    for a in triggers.QUIET:
        cpu.hooks[a] = lambda c: 0
    mipsrun.object_arm(cpu, k)
    what = hash(tuple(sorted((a, m.ram[a & MASK]) for a in m.written
                             if m.ram[a & MASK] != m.read.get(a, -1))))
    if calls:
        return what, f"calls: {calls}"
    return what, _ram_diff(m.ram, cpu.ram)


def entry_run(cpu, n):
    """The overlay's own entry 10 with scene n: [the calls the model logs]."""
    calls = []
    cpu.hooks = dict(cpu.hooks)
    cpu.hooks.update({
        STAMP_RECT: lambda c: calls.append(("stamp",) + tuple(c.r[4:8]) + _stack(c, 5)),
        useitem.ANNOUNCE: lambda c: calls.append(("announce", c.r[4])),
    })
    cpu.call(_entry(cpu, ENTRY_SCENE), n)
    return calls


SCENES_OF = {2: (15,), 4: (12,), 13: (4, 13), 17: (9,), 20: (5, 10), 24: (6,), 26: (14,)}


def entry_cases(lv, n, rng, snap="a1"):
    import mipsrun
    base = mipsrun.level_cpu(lv, snap)
    ram0 = bytes(base.ram)
    put = useitem._put
    out = []
    for _ in range(n):
        cpu = mipsrun.CPU(ram0)
        cpu.hooks.update(base.hooks)
        sc = rng.choice(SCENES_OF.get(lv, (0,)) * 3 + (rng.randrange(16), rng.randrange(0x100)))
        for f in (0x42, 0x59, 0x5D, 0x6D, 0x6E, 0x6F, 0x70):
            put(cpu, F(f), 1, rng.choice((0, 0, 1, 2)))
        for k in (20, 50) + tuple(range(52, 62)):
            put(cpu, O(k), 1, rng.choice((0, 2, 0x80)))
            put(cpu, O(k, 6), 2, rng.choice((0xFF, 0x12C, rng.randrange(0x150))))
        for j in (30, 56):
            put(cpu, A(j), 1, rng.choice((0, 1, 2, 8, 0xFF)))
            put(cpu, A(j, 9), 1, rng.choice((0, 1, 2, 3)))
        for t in (0x7D, 0x10):
            put(cpu, levelin.INV_A + t, 1, rng.choice((0, 0, 1, 2, givetake.CAP)))
            put(cpu, levelin.INV_B + t, 1, rng.choice((0, 0, 1, givetake.CAP)))
        out.append((cpu, sc))
    return out


def entry_compare(cpu, lv, n):
    m = Mem(bytes(cpu.ram))
    entry10(lv, m, n)
    got = entry_run(cpu, n)
    what = (lv, hash((tuple(m.calls), tuple(sorted((a, m.ram[a & MASK]) for a in m.written
                                                   if m.ram[a & MASK] != m.read.get(a, -1))))))
    if m.calls != got:
        return what, f"scene {n}: calls: model {m.calls}, game {got}"
    d = _ram_diff(m.ram, cpu.ram)
    return what, (f"scene {n}: {d}" if d else None)


def _tally(name, runs, compare, out, verbose):
    ok = n = 0
    seen = set()
    told = False
    for args in runs:
        n += 1
        what, why = compare(*args)
        if why is None:
            ok += 1
            seen.add(what)
        elif not told or verbose:
            told = True
            print(f"  {name}: {why}", file=out)
    return ok, n, len(seen)


def check(out=sys.stdout, seed=97, verbose=False):
    rng = random.Random(seed)
    good = True
    runs = []
    for lv in (0, 2, 13, 20, 24, 27):
        runs += [(cpu,) for cpu in step_cases(lv, 160, rng)]
    ok, n, ways = _tally("cutscene_step", runs, step_compare, out, verbose)
    print(f"cutscene_step, the game's own: {ok} of {n} runs agree -- the calls in order and "
          f"all of RAM but the stack, {ways} different outcomes", file=out)
    good &= ok == n
    runs = []
    for lv in range(28):
        runs += arm_cases(lv, 60, rng)
    ok, n, ways = _tally("opcode 0xe4", runs, arm_compare, out, verbose)
    print(f"opcode 0xe4, the game's own arm: {ok} of {n} runs over its nine rectangles agree "
          f"-- all of RAM but the stack, {ways} different outcomes", file=out)
    good &= ok == n
    runs = []
    for lv in range(28):
        try:
            runs += [(cpu, lv, sc) for cpu, sc in entry_cases(lv, 60, rng)]
        except Exception as e:                                     # noqa: BLE001
            print(f"  level {lv}: no machine ({e})", file=out)
    ok, n, ways = _tally("entry 10", runs, entry_compare, out, verbose)
    print(f"entry 10, against the overlays' own over 28 levels: {ok} of {n} runs agree -- "
          f"the calls and all of RAM but the stack, {ways} different outcomes", file=out)
    good &= ok == n
    return good


def export(out_dir, seed=101):
    """scenes.json (the sixteen records, for the port) and scenecheck.json:
    runs of the three models -- the bytes read, the bytes written, the calls
    -- which godot/selftest.gd holds godot/scenes.gd to."""
    import json
    rng = random.Random(seed)
    path = os.path.join(out_dir, "scenes.json")
    with open(path, "w") as fh:
        json.dump({"records": [list(r) for r in records()]}, fh, separators=(",", ":"))

    def row(kind, m, **kw):
        d = {"kind": kind, "read": [[a, v] for a, v in sorted(m.read.items())],
             "wrote": [[a, m.ram[a & MASK]] for a in sorted(m.written)],
             "calls": [list(c) for c in m.calls]}
        d.update(kw)
        return d
    rows = []
    for lv in (0, 13, 24):
        for cpu in step_cases(lv, 40, rng):
            m = Mem(bytes(cpu.ram))
            step(m, lambda n, k: m.calls.append(("entry", n, k)))
            rows.append(row("step", m))
    for lv in range(28):
        for cpu, k in arm_cases(lv, 8, rng):
            m = Mem(bytes(cpu.ram))
            arm(m, k)
            rows.append(row("arm", m, slot=k))
    for lv in ENTRY10_LEVELS:
        for cpu, sc in entry_cases(lv, 16, rng):
            m = Mem(bytes(cpu.ram))
            entry10(lv, m, sc)
            rows.append(row("entry10", m, level=lv, scene=sc))
    cpath = os.path.join(out_dir, "scenecheck.json")
    with open(cpath, "w") as fh:
        json.dump({"cases": rows}, fh, separators=(",", ":"))
    return path, cpath


def show(out=sys.stdout):
    print(__doc__.split("**How it is held")[0], file=out)
    for i, r in enumerate(records()):
        gate = "none" if r[1] == 0xFF else f"flag {r[1] & 0x7F:#x}" + (" set" if r[1] & 0x80 else
                                                                       " clear")
        print(f"  record {i:2d}: movie {r[0]:#04x}, plays while {gate}", file=out)


def main():
    a = sys.argv[1:]
    if "--export" in a:
        print(export(a[a.index("--export") + 1] if len(a) > a.index("--export") + 1
                     else os.path.join(useitem.ROOT, "out", "godot")))
        return
    if "--check" in a:
        sys.exit(0 if check(verbose="-v" in a) else 1)
    show()


if __name__ == "__main__":
    main()
