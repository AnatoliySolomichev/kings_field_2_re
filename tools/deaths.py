#!/usr/bin/env python3
"""What a level does when one of its creatures dies: every level's entry 19, against the overlays' own.

    python3 tools/deaths.py            what each level's entry 19 does
    python3 tools/deaths.py --check    the model against the overlays' own code
    python3 tools/deaths.py --export D deathcheck.json for the self-test

**Entry 19** (`level_hooks + 0x4c`) is what `actor_tick` (`0x80050868`,
`actor_tick+0x7c0`) calls with the creature's record once a dying creature's
count (`+0x70`) has run past `0x26` -- the body gone -- and before it goes by
its category (`+0`): 1 `actor_retire` (never back), 2 state 0 and home, 5
the slot freed (`0xff`), anything else state 2 and home. So a hook that
writes the creature's own `+0` changes how it goes. Every level's works out
the slot as `(a0 - actor_table) / 0x88` and asks about it; fifteen levels'
is `jr $ra`, thirteen do something:

```
level 0   slot 0x20, flag 8 clear: flag 8 1, and object 344's lock 0xf1
          lifted (0xff)
level 1   slot 0x18 or 0x28, flag 0xc clear: flag 0xc 1
level 2   slot 4, the lake's caretaker: flag 0x15 1, the switch (object 82)
          state 1 and lock 3 -- the lake's third pattern (FORMATS.md,
          "Level 2's lake")
level 6   slot 3: its own category 1, so it is retired for good
level 8   slot 1, flag 0x2c 1: flag 0x2c 2 and its own category 8 (state 2,
          home: the one entry 1 makes appear when the player looks away)
level 11  slot 3: flag 0x3c 1; object 20's +0 and +0x3c 0, and the object
          its +0x3a names, unless 0xffff or free, +0 2 and lock 0xff; object
          33's +0x3e 0
level 12  slots 0x32, 0x33, 0x34: flags 0x3e, 0x3f, 0x40, each once, and
          object_signal(0x64, 0x65, 0x66)
level 13  slots 0..12: a bit each in the halfword at flag 0x44 (0x44 and
          0x45); every death, the halfword 0x1fff -- all thirteen -- sets
          flag 0x46
level 15  slot 3, flag 0x49 clear: flag 1, creatures 4 and 5 category 8,
          and objects 0x73 and 0x74 dissolved; slot 0x28, flag 0x4a:
          creatures 10 and 11, objects 0x75 and 0x76. The dissolve
          (0x801e85b8) runs sixteen frames of its own -- res_wait, the two
          uploads, camera_pose and render_frame -- with +5 0x32, +2 5 and
          +0x10 up by 0x100 a frame to 0xfff, and frees both (+6 0xff)
level 17  slots 0xb, 0xc, 0xd, flags 0x4e, 0x4f, 0x50 once: creature 0x10,
          0x37 or 0x2e category 8 and object 0x50, 0x51 or 5 state 1 with
          +0x3f 1; slot 0xf, flag 0x51 1: flag 2 and its own category 8;
          slot 0x38: its own category 1 and floor (+3) 0
level 19  slot 0x14: flag 0x55 1, object 85's +0x3f 0xff and +0 2
level 25  slot 0, flag 0x67 clear: the ending. Flag 0x67 1, swing_clock -1,
          light_table_reset, render_flags_reset, light_table_step,
          sub_80030e14 (the status), sixty-four frames of the master volume
          (sub_800699d8) from 0x7d down by 2 to 0, DrawSync and VSync each;
          the volume 0; the music stopped if it plays (0x801b0a04 1: the
          three calls on its handle 0x801b0a08, and the word 0); the word at
          $gp+0x1e4 3 -- game_main's END.EXE with overlay_arg 2, all three
          movies -- and fade_frames(0x82, 0, 0x1000, 0x40)
level 27  slot 0, the player not in state 0x11: flag 0x65 1 (level_overlay_
          tick's: the short ending, or on); and with thing 0x10 in the pack,
          flag 0x66 1, 0x10 taken, 0x11 given, and in hand 0x10 becomes 0x11
          (equip_weapon) -- with 0x66 level_overlay_tick warps on instead of
          ending
```

**How it is held to the game.** `check()` runs each level's own entry 19 out
of its overlay with `tools/mipsrun.py` over the level as its own loader
leaves it, a slot at random -- most of them the ones the level asks about --
with the flags, the creatures' categories, the objects' bytes it reads and
writes, the pack's 0x10 and 0x11, the weapon in hand, the player's state,
the music's word and handle at random; GAME.EXE's own has_item, take_item,
give_item and object_signal run, and what touches the hardware -- the
lighting, the status, the sound, the frames, the fade, equip_weapon -- is
stood in for and logged: the model must make the same calls in order and
leave the same RAM, all of it but the stack.
"""
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import givetake                                                      # noqa: E402
import levelin                                                       # noqa: E402
import useitem                                                       # noqa: E402
from levelin import A, F, O, MASK, Mem                               # noqa: E402

ENTRY = 19                         # level_hooks + 0x4c
EXIT = 0x8009C3F8                  # $gp + 0x1e4: game_main stops on it
SWING_CLOCK = 0x801B25A4           # s16
PLAYER_STATE = 0x801B25E5
IN_HAND = 0x801B25AF               # equipped_weapon
MUSIC_ON, MUSIC = 0x801B0A04, 0x801B0A08   # the music's word and its handle (s16)

LIGHT_TABLE_RESET = 0x800341E8
RENDER_FLAGS_RESET = 0x80034180
LIGHT_TABLE_STEP = 0x80034300
STATUS = 0x80030E14                # sub_80030e14, the player's status a frame
VOLUME = 0x800699D8                # (l, r): the master volume, by 129
MUSIC_STOP = (0x800677E8, 0x80071F9C, 0x80072CE8)   # on the handle, in turn
FADE_FRAMES = 0x80046C00
EQUIP_WEAPON = 0x8002BDC0
RES_WAIT, RES_UPLOAD_SPU, RES_UPLOAD_VRAM = 0x80019AB4, 0x80015A48, 0x80018CD0
CAMERA_POSE, RENDER_FRAME = 0x8002B330, 0x800422B8
DRAW_SYNC, VSYNC = 0x80079BA0, 0x8007910C

# the slots each level's entry 19 asks about
SLOTS = {0: (0x20,), 1: (0x18, 0x28), 2: (4,), 6: (3,), 8: (1,), 11: (3,),
         12: (0x32, 0x33, 0x34), 13: tuple(range(13)), 15: (3, 0x28),
         17: (0xB, 0xC, 0xD, 0xF, 0x38), 19: (0x14,), 25: (0,), 27: (0,)}
LEVELS = tuple(sorted(SLOTS))


def s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def held(m, k, n):
    """0x801e86d8 (level 15) and 0x801e8924 (level 17): n creatures from
    slot k category 8."""
    for i in range(n):
        m.wr(A(k + i), 8)


def dissolve(m, a, b):
    """Level 15's 0x801e85b8: objects a and b +5 0x32, +2 5, sixteen frames
    of their +0x10 up by 0x100 to 0xfff, then both free (+6 0xff)."""
    for k in (a, b):
        m.wr(O(k, 5), 0x32)
    for k in (a, b):
        m.wr(O(k, 2), 5)
    for _ in range(16):
        for k in (a, b):
            m.wr(O(k, 0x10), m.rd(O(k, 0x10), 2) + 0x100, 2)
        for k in (a, b):
            if m.rd(O(k, 0x10), 2) >= 0xFFF:
                m.wr(O(k, 0x10), 0xFFF, 2)
        m.calls += [("res_wait",), ("res_upload_spu",), ("res_upload_vram",),
                    ("camera_pose",), ("render_frame",)]
    for k in (a, b):
        m.wr(O(k, 6), 0xFF, 2)


def started(m, k, v):
    """Level 17's 0x801e8958 with 1: object k +0x3f 1 and state 1 (with 0,
    +0x3f 0; nothing else calls it with 0 here)."""
    m.wr(O(k, 0x3F), v)
    m.wr(O(k, 8), 1, 2)


def entry19(lv, m, k):
    """Level `lv`'s entry 19 over the RAM `m`, for the creature in slot `k`."""
    f = lambda n: m.rd(F(n))                                     # noqa: E731
    if lv == 0:
        if k == 0x20 and not f(8):
            m.wr(F(8), 1)
            levelin.lock_lift(m, 344, 0xF1)
    elif lv == 1:
        if k in (0x18, 0x28) and not f(0xC):
            m.wr(F(0xC), 1)
    elif lv == 2:
        if k == 4:
            m.wr(F(0x15), 1)
            m.wr(O(82, 8), 1, 2)
            m.wr(O(82, 0x38), 3)
    elif lv == 6:
        if k == 3:
            m.wr(A(k), 1)
    elif lv == 8:
        if k == 1 and f(0x2C) == 1:
            m.wr(F(0x2C), 2)
            m.wr(A(1), 8)
    elif lv == 11:
        if k == 3:
            m.wr(F(0x3C), 1)
            m.wr(O(20), 0)
            link = m.rd(O(20, 0x3A), 2)
            m.wr(O(20, 0x3C), 0)
            if link != 0xFFFF and m.rd(O(link, 6), 2) != 0xFF:
                m.wr(O(link), 2)
                m.wr(O(link, 0x38), 0xFF)
            m.wr(O(33, 0x3E), 0)
    elif lv == 12:
        if k in (0x32, 0x33, 0x34) and not f(0x3E + k - 0x32):
            m.wr(F(0x3E + k - 0x32), 1)
            levelin.object_signal(m, 0x64 + k - 0x32)
    elif lv == 13:
        if k < 13:
            bit = 1 << k
            m.wr(F(0x44), m.rd(F(0x44)) | bit)
            m.wr(F(0x45), m.rd(F(0x45)) | (bit >> 8))
        if m.rd(F(0x44), 2) == 0x1FFF:
            m.wr(F(0x46), 1)
    elif lv == 15:
        if k == 3 and not f(0x49):
            m.wr(F(0x49), 1)
            held(m, 4, 2)
            dissolve(m, 0x73, 0x74)
        elif k == 0x28 and not f(0x4A):
            m.wr(F(0x4A), 1)
            held(m, 0xA, 2)
            dissolve(m, 0x75, 0x76)
    elif lv == 17:
        arms = {0xB: (0x4E, 0x10, 0x50), 0xC: (0x4F, 0x37, 0x51), 0xD: (0x50, 0x2E, 5)}
        if k in arms:
            flag, who, obj = arms[k]
            if not f(flag):
                m.wr(F(flag), 1)
                held(m, who, 1)
                started(m, obj, 1)
        elif k == 0xF:
            if f(0x51) == 1:
                m.wr(F(0x51), 2)
                m.wr(A(15), 8)
        elif k == 0x38:
            m.wr(A(56), 1)
            m.wr(A(56, 3), 0)
    elif lv == 19:
        if k == 0x14:
            m.wr(F(0x55), 1)
            m.wr(O(85, 0x3F), 0xFF)
            m.wr(O(85), 2)
    elif lv == 25:
        if k == 0 and not f(0x67):
            m.wr(F(0x67), 1)
            m.wr(SWING_CLOCK, 0xFFFF, 2)
            m.calls += [("light_table_reset",), ("render_flags_reset",), ("light_table_step",),
                        ("status",)]
            v = 0x7D
            for _ in range(64):
                a = v if v >= 0 else 0
                m.calls += [("volume", a, a), ("draw_sync", 0), ("vsync", 0)]
                v -= 2
            m.calls.append(("volume", 0, 0))
            if m.rd(MUSIC_ON, 4) == 1:
                h = s16(m.rd(MUSIC, 2)) & 0xFFFFFFFF
                m.calls += [("music", MUSIC_STOP[0], h, 0, 0), ("music", MUSIC_STOP[1], h),
                            ("music", MUSIC_STOP[2], h)]
                m.wr(MUSIC_ON, 0, 4)
            m.wr(EXIT, 3, 4)
            m.calls.append(("fade_frames", 0x82, 0, 0x1000, 0x40))
    elif lv == 27:
        if k == 0 and m.rd(PLAYER_STATE) != 0x11:
            m.wr(F(0x65), 1)
            if m.has(0x10) > 0:
                m.wr(F(0x66), 1)
                givetake.take_item(lv, m, 0x10)
                givetake.give_item(lv, m, 0x11)
                if m.rd(IN_HAND) == 0x10:
                    m.calls.append(("equip_weapon", 0x11))


# --- against the overlays' own ---------------------------------------------------

def game_run(cpu, k):
    """The overlay's own entry 19 for the creature in slot `k` over the
    machine's RAM: [the calls it made that the model logs, in order]."""
    calls = []
    hooks = struct.unpack_from("<I", cpu.ram, useitem.LEVEL_HOOKS & MASK)[0]
    entry = struct.unpack_from("<I", cpu.ram, (hooks + 4 * ENTRY) & MASK)[0]

    def log(*what):
        return lambda c: calls.append(what)
    cpu.hooks = dict(cpu.hooks)
    cpu.hooks.update({
        LIGHT_TABLE_RESET: log("light_table_reset"),
        RENDER_FLAGS_RESET: log("render_flags_reset"),
        LIGHT_TABLE_STEP: log("light_table_step"),
        STATUS: log("status"),
        VOLUME: lambda c: calls.append(("volume", c.r[4], c.r[5])),
        MUSIC_STOP[0]: lambda c: calls.append(("music", MUSIC_STOP[0], c.r[4], c.r[5], c.r[6])),
        MUSIC_STOP[1]: lambda c: calls.append(("music", MUSIC_STOP[1], c.r[4])),
        MUSIC_STOP[2]: lambda c: calls.append(("music", MUSIC_STOP[2], c.r[4])),
        DRAW_SYNC: lambda c: calls.append(("draw_sync", c.r[4])),
        VSYNC: lambda c: calls.append(("vsync", c.r[4])),
        FADE_FRAMES: lambda c: calls.append(("fade_frames",) + tuple(c.r[4:8])),
        EQUIP_WEAPON: lambda c: calls.append(("equip_weapon", c.r[4])),
        RES_WAIT: log("res_wait"),
        RES_UPLOAD_SPU: log("res_upload_spu"),
        RES_UPLOAD_VRAM: log("res_upload_vram"),
        CAMERA_POSE: log("camera_pose"),
        RENDER_FRAME: log("render_frame"),
        useitem.ANNOUNCE: lambda c: calls.append(("announce", c.r[4])),
    })
    cpu.call(entry, A(k))
    return calls


def cases(lv, n, rng, snap="a1"):
    """`n` runs of level `lv`'s entry 19: [(the machine, the slot)]."""
    import mipsrun
    base = mipsrun.level_cpu(lv, snap)
    ram0 = bytes(base.ram)
    put = useitem._put
    asked = SLOTS.get(lv, ())
    out = []
    for _ in range(n):
        cpu = mipsrun.CPU(ram0)
        cpu.hooks.update(base.hooks)
        if asked and rng.random() < 0.8:
            k = rng.choice(asked)
        else:
            k = rng.randrange(200)
        for fl in (8, 0xC, 0x15, 0x2C, 0x3C, 0x3E, 0x3F, 0x40, 0x46, 0x49, 0x4A, 0x4E, 0x4F,
                   0x50, 0x51, 0x55, 0x65, 0x66, 0x67):
            put(cpu, F(fl), 1, rng.choice((0, 0, 1, 1, 2, rng.randrange(0x100))))
        full = 0x1FFF & ~(1 << rng.randrange(13))
        put(cpu, F(0x44), 2, rng.choice((0, full, full, 0x1FFF, 0xFFFF, rng.randrange(0x10000))))
        for j in (1, 3, 4, 5, 10, 11, 15, 0x10, 0x2E, 0x37, 56, k):
            put(cpu, A(j), 1, rng.choice((0, 1, 2, 5, 8, 0xFF)))
            put(cpu, A(j, 3), 1, rng.randrange(4))
        put(cpu, O(344, 0x38), 1, rng.choice((0xF1, 0xF1, 0xFF, 0xF0)))
        put(cpu, O(82, 8), 2, rng.choice((0, 1, 2, 3)))
        put(cpu, O(82, 0x38), 1, rng.choice((0, 1, 3)))
        link = rng.choice((0xFFFF, rng.randrange(396), rng.randrange(396)))
        put(cpu, O(20, 0x3A), 2, link)
        put(cpu, O(20), 1, rng.choice((0, 2, 0x80)))
        if link != 0xFFFF:
            put(cpu, O(link, 6), 2, rng.choice((0xFF, 0xFF, 0x12C, rng.randrange(0x150))))
            put(cpu, O(link, 0x38), 1, rng.choice((0, 0xC8, 0xFF)))
        put(cpu, O(33, 0x3E), 1, rng.choice((0, 0xFF)))
        for j in (0x73, 0x74, 0x75, 0x76):
            put(cpu, O(j, 0x10), 2, rng.choice((0, 0x80, 0xF00, 0xFF80, rng.randrange(0x10000))))
            put(cpu, O(j, 2), 1, rng.randrange(8))
            put(cpu, O(j, 5), 1, rng.choice((0, 0xFF)))
        for j in (0x50, 0x51, 5, 85):
            put(cpu, O(j, 8), 2, rng.choice((0, 1, 2)))
            put(cpu, O(j, 0x3F), 1, rng.choice((0, 1, 0xFF)))
            put(cpu, O(j), 1, rng.choice((0, 2)))
        for t in (0x10, 0x11):
            put(cpu, levelin.INV_A + t, 1, rng.choice((0, 0, 1, 2, givetake.CAP)))
            put(cpu, levelin.INV_B + t, 1, rng.choice((0, 0, 1, givetake.CAP)))
        put(cpu, IN_HAND, 1, rng.choice((0x10, 0x10, 0x11, 0xFF, 3)))
        put(cpu, PLAYER_STATE, 1, rng.choice((0, 0, 0x11, 0x10)))
        put(cpu, MUSIC_ON, 4, rng.choice((0, 1, 1, 2)))
        put(cpu, MUSIC, 2, rng.choice((0, 3, 0xFFFF, rng.randrange(0x10000))))
        put(cpu, SWING_CLOCK, 2, rng.choice((0xFFFF, 0, 0x40)))
        put(cpu, EXIT, 4, 0)
        out.append((cpu, k))
    return out


def compare(cpu, lv, k):
    """One run both ways: (what it did, None) when they agree, else what differs."""
    m = Mem(bytes(cpu.ram))
    entry19(lv, m, k)
    got = game_run(cpu, k)
    what = (lv, k, hash((tuple(m.calls), tuple(sorted((a, m.ram[a & MASK]) for a in m.written
                                                      if m.ram[a & MASK] != m.read.get(a, -1))))))
    if m.calls != got:
        return what, f"slot {k}: calls: model {m.calls[:6]}..., game {got[:6]}..."
    a, b = m.ram, cpu.ram
    for lo, hi in ((0, levelin.STACK_LO), (levelin.STACK_HI, len(a))):
        if a[lo:hi] != b[lo:hi]:
            for i in range(lo, hi):
                if a[i] != b[i]:
                    return what, (f"slot {k}: {0x80000000 | i:#x}: model {a[i]:#x}, game "
                                  f"{b[i]:#x} ({levelin._where(0x80000000 | i)})")
    return what, None


def check(out=sys.stdout, per_level=60, seed=79, verbose=False):
    """The model against every level's own entry 19."""
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
        for cpu, k in runs:
            n += 1
            what, why = compare(cpu, lv, k)
            if why is None:
                ok += 1
                seen[what] = seen.get(what, 0) + 1
            elif not told or verbose:
                told = True
                print(f"  level {lv}: {why}", file=out)
    for lv in LEVELS:
        ways = [w for w in seen if w[0] == lv]
        print(f"  level {lv:2d}: {sum(seen[w] for w in ways):3d} runs, {len(ways)} different "
              f"outcomes", file=out)
    print(f"entry 19, against the overlays' own over 28 levels: {ok} of {n} runs agree -- "
          f"the calls in order and all of RAM but the stack", file=out)
    return ok == n


def export(out_dir, per_level=16, seed=83):
    """deathcheck.json: runs of the model over the thirteen levels that have
    an entry 19 -- the slot, the bytes it read, the bytes it wrote and its
    calls -- which godot/selftest.gd holds godot/deaths.gd to."""
    import json
    rng = random.Random(seed)
    rows = []
    for lv in LEVELS:
        for cpu, k in cases(lv, per_level, rng):
            m = Mem(bytes(cpu.ram))
            entry19(lv, m, k)
            rows.append({"level": lv, "slot": k,
                         "read": [[a, v] for a, v in sorted(m.read.items())],
                         "wrote": [[a, m.ram[a & MASK]] for a in sorted(m.written)],
                         "calls": [list(c) for c in m.calls]})
    path = os.path.join(out_dir, "deathcheck.json")
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
