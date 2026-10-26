#!/usr/bin/env python3
"""The rectangles that do something when the player is in them: opcode 0xe1 and every level's entry 3, against the game's own.

    python3 tools/triggers.py            every level's trigger rectangles
    python3 tools/triggers.py --check    the model against the game's own arm
                                         and the overlays' own entry 3
    python3 tools/triggers.py --export D triggercheck.json for the self-test

**Opcode `0xe1`** (`object_interpreter+0x3858`, 0x8004a868) is a rectangle of
cells -- the record's `+0x14 >> 11`, `+0x1c >> 11`, `+0x38` by `+0x39`, its
`+0x18` the height `player_in_rect` asks the player's to be near -- and while
the player stands in it, unless `+0x40` says it has fired, by `+0x3a & 0xf`:
0 the level's own **entry 3** (`level_hooks + 0xc`) with the record, 1
`object_signal(+0x3b)`, 2 story flag `0xa7 + +0x3b` set to `+0x3c`; `+0x3a`
bit 7 clear sets `+0x40` to 1 first, so it fires once, and stepping out
clears it. The game's 50 are all mode 0 -- 34 of them every frame (bit 7) --
on fourteen levels, so every one is the level's own code.

**Entry 3** switches on the record's `+0x3b`, and runs only while the player
is in the record's own rectangle:

```
10    levels 0..7, 9..11: the warp's arrival -- a rectangle of the level's
      own about the cell a warp puts the player in (warp_to's records); in
      it with 0x801b25ee set (warp_to's own byte), stamp_rect of three cells
      from the one template; in the record's rectangle but out of that one,
      from the other, and 0x801b25ee cleared
0, 1  level 2: gate 44's lock back to 0x9a unless flag 0x12 (0), or open,
      0x9a to 0xff (1); level 4: gate 115's x the record's less 0x400 unless
      flag 0x19 (0), or plus 0x3ff (1) -- the side it was crossed from
0     level 0: once flag 6 is 1 and 7 is 0 (the clock, entry 4's arms 2 and
      4), the three men held, objects 214, 62, 195 and 172 shown and 111
      hidden -- and the arrival after; level 6: the stamp at (58, 53), six
      by two, from (0x4a, 5) or (0x44, 5) by whether the feet wear 0x4b
      (0x801b25d8)
0, 1  level 9: with flag 0x34, out of the rectangle at (54, 15), slot 2 held
      and object 249 shown (0); object 58 -- flag 0x35 0: drawn, the
      sound when the player is thrown (state 0x10), effect_hurt_player at
      it; 1: lifted over sixteen frames of the game (+0x10 up to 0xfff) and
      gone, the flag 2; 2: gone (1); flags 0x7b..0x7e all set make 0x35 1
0x62  level 14: player_take_hit (effect 3, nothing else) while in the
0x63  record's rectangle at its height + 0xc80 (0x62), or anywhere in it
      (0x63): the floor that burns
0..   level 17: flag 0x51 (0); with 0x38 held, the light, armour 0x39 for
      0x38 (put on in slot 4 if 0x38 was), the light back (1); a hit of
      effect 0x40 and 0x63 of the second attack for each of flags
      0x4e..0x50 clear (0x61); a hit of effect 0x43 at the player (0x63)
0..2  level 26: flag 0x5e (0); flag 0x61 set (1) or cleared (2), the stats
```

**How it is held to the game.** `check()` runs GAME.EXE's own arm for each
of the levels' 0xe1 records with `tools/mipsrun.py` (`object_arm`), over the
level as its loader leaves it, the player in and about the rectangle, `+0x40`,
the flags, the pack, the warp's byte, the thing in hand and the player's
state at random -- the arm's player_in_rect running, and the level's own entry
3 out of its overlay -- with stamp_rect, player_take_hit, effect_hurt_player,
sound_cue_at, the light (0x8005d948), equip_armour, the frame's routines and
give_item's and take_item's hooks stood in for and logged: the model must
make the same calls and leave the same RAM, all of it but the stack.
"""
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import levelin                                                       # noqa: E402
import useitem                                                       # noqa: E402

from levelin import A, O, F, Mem, MASK                               # noqa: E402

TRIGGER_OP = 0xE1
WARPED = 0x801B25EE              # warp_to's own byte: the player came by a warp
PLAYER_POS = 0x801B25F0
PLAYER_STATE = 0x801B25E5
IN_HAND = 0x801B25D8             # the thing in the hand's slot (equip_armour slot 5)
SLOT_4 = 0x801B25D6              # equip_armour slot 4
STAMP_RECT = 0x800445B8
TAKE_HIT = 0x8002AB18            # player_take_hit
HURT = 0x8002B114                # effect_hurt_player
SOUND_AT = 0x80015654            # sound_cue_at
LIGHT = 0x8005D948
EQUIP_ARMOUR = 0x8002BB84
RECALC = 0x80029500
ANNOUNCE = 0x80041EEC
RENDER_FRAME = 0x800422B8
QUIET = (0x80019AB4, 0x80015A48, 0x80018CD0, 0x8002B330)   # res_wait, res_upload_spu,
                                                           # res_upload_vram, camera_pose
FLAG_BASE = 0xA7                 # mode 2's story flags


def player_in_rect(m, cx, cz, w, h, y=0x8000):
    """player_in_rect (0x80046884): the player's own cell in the rectangle,
    and, unless `y` is 0x8000, the player's height not below y + 0x800 nor
    above y - 0xc80."""
    px = useitem.s32(m.rd(PLAYER_POS, 4)) >> 11
    pz = useitem.s32(m.rd(PLAYER_POS + 8, 4)) >> 11
    if not (cx <= px < cx + w and cz <= pz < cz + h):
        return False
    if y == 0x8000:
        return True
    py = useitem.s32(m.rd(PLAYER_POS + 4, 4))
    return not (y + 0x800 < py) and not (py < y - 0xC80)


# the warp's arrival on each level (selector 10): the rectangle, then the
# template the three cells come from in it (warped) and out of it, and the
# rest of stamp_rect's arguments: (sz, dx, dz, w, h)
ARRIVALS = {
    0: ((9, 0x37, 3, 3), 0x4A, 0x4D, (0, 9, 0x37, 3, 1)),
    1: ((0x1C, 6, 9, 0xB), 0x48, 0x4B, (0, 0x1F, 0x10, 3, 1)),
    2: ((0x38, 0x23, 3, 3), 0x4A, 0x4D, (0, 0x38, 0x25, 3, 1)),
    3: ((6, 0x1E, 3, 4), 0x4A, 0x4D, (0, 6, 0x21, 3, 1)),
    4: ((0x37, 0xC, 3, 3), 0x4A, 0x4D, (0, 0x37, 0xC, 3, 1)),
    5: ((0x1C, 0x1E, 3, 4), 0x4A, 0x4D, (0, 0x1C, 0x21, 3, 1)),
    6: ((0x1F, 0x41, 7, 0xC), 0x4A, 0x4D, (4, 0x21, 0x41, 3, 1)),
    7: ((0x12, 0x1C, 3, 3), 0x15, 0x18, (0x4F, 0x12, 0x1E, 3, 1)),
    9: ((0x24, 0x36, 7, 0xC), 0x2A, 0x2D, (0x4F, 0x26, 0x36, 3, 1)),
    10: ((0x24, 0x32, 3, 3), 0x4A, 0x4D, (5, 0x24, 0x32, 3, 1)),
    11: ((0x39, 0x21, 3, 3), 0x4A, 0x4D, (0, 0x39, 0x23, 3, 1)),
}


def s32(v):
    return useitem.s32(v)


def arrival(lv, m):
    rect, warped, plain, rest = ARRIVALS[lv]
    if player_in_rect(m, *rect):
        if m.rd(WARPED) == 0:
            return
        sx = warped
    else:
        sx = plain
        m.wr(WARPED, 0)
    m.calls.append(("stamp", 2, sx) + rest + (0, 0x2F))


def hit(m, *args):
    """player_take_hit (0x8002ab18): logged with its four arguments and the
    eight words on the stack."""
    m.calls.append(("hit",) + args)


def entry3(lv, m, k):
    """Level `lv`'s entry 3 with record `k` over the RAM `m`."""
    r = O(k)
    sel = m.rd(r + 0x3B)
    f = lambda i: m.rd(F(i))                                      # noqa: E731
    if lv == 0:
        if sel not in (0, 10):
            return
        if sel == 0 and f(6) == 1 and f(7) == 0:
            for i in (0, 1, 2):
                m.wr(A(i), 8)
            m.wr(O(214), 2)
            m.wr(O(214, 0x3C), 0xFF)
            m.wr(O(177, 0x3E), 0xFF)
            m.wr(O(111), 0)
            m.wr(O(111, 0x3C), 0)
            m.wr(O(182, 0x3E), 0)
            for i in (62, 195, 172):
                m.wr(O(i), 2)
                m.wr(O(i, 0x38), 0xFF)
        arrival(lv, m)
    elif lv in (1, 3, 5, 7, 10, 11):
        if sel == 10:
            arrival(lv, m)
    elif lv == 2:
        if sel == 0:
            if f(0x12) == 0 and m.rd(O(44, 0x38)) != 0x9A:
                m.wr(O(44, 0x38), 0x9A)
        elif sel == 1:
            if m.rd(O(44, 0x38)) == 0x9A:
                m.wr(O(44, 0x38), 0xFF)
        elif sel == 10:
            arrival(lv, m)
    elif lv == 4:
        if sel == 0:
            if f(0x19) == 0:
                m.wr(O(115, 0x14), s32(m.rd(r + 0x14, 4)) - 0x400, 4)
        elif sel == 1:
            m.wr(O(115, 0x14), s32(m.rd(r + 0x14, 4)) + 0x3FF, 4)
        elif sel == 10:
            arrival(lv, m)
    elif lv == 6:
        if sel == 0:
            sx = 0x4A if m.rd(IN_HAND) == 0x4B else 0x44
            m.calls.append(("stamp", 2, sx, 5, 0x3A, 0x35, 6, 2, 0, 0x2F))
        elif sel == 10:
            arrival(lv, m)
    elif lv == 9:
        if sel == 0:
            if f(0x34) == 1 and not player_in_rect(m, 0x36, 0xF, 0xA, 4):
                m.wr(A(2), 8)
                m.wr(O(249), 2)
                m.wr(O(249, 0x3C), 0xFF)
                m.wr(O(262, 0x3E), 0xFF)
        elif sel == 1:
            v = f(0x35)
            if v == 0:
                if all(f(i) for i in (0x7B, 0x7C, 0x7D, 0x7E)):
                    m.wr(F(0x35), 1)
                m.wr(O(58), 2)
                at = O(58, 0x14)
                if m.rd(PLAYER_STATE) == 0x10:
                    m.calls.append(("sound_at", 0x28, at, 0x78, 0))
                m.calls.append(("hurt", at, 0, 0x1000, 0x8000, 0x1000) + (0x40,) * 9
                               + (0x400, 0xA))
            elif v == 1:
                m.wr(O(58), 2)
                m.wr(O(58, 5), 0x32)
                m.wr(O(58, 2), 5)
                m.wr(O(58, 0x10), 0, 2)
                for _ in range(16):
                    t = m.rd(O(58, 0x10), 2) + 0x100
                    m.wr(O(58, 0x10), t, 2)
                    if m.rd(O(58, 0x10), 2) >= 0xFFF:
                        m.wr(O(58, 0x10), 0xFFF, 2)
                    m.calls.append(("frame",))
                m.wr(O(58, 6), 0xFF, 2)
                m.wr(O(58, 4), 0xFF)
                m.wr(O(58), 0)
                m.wr(F(0x35), 2)
            else:
                m.wr(O(58, 6), 0xFF, 2)
                m.wr(O(58, 4), 0xFF)
                m.wr(O(58), 0)
        elif sel == 10:
            arrival(lv, m)
    elif lv == 14:
        if sel == 0x62:
            x, z = s32(m.rd(r + 0x14, 4)) >> 11, s32(m.rd(r + 0x1C, 4)) >> 11
            if not player_in_rect(m, x, z, m.rd(r + 0x38), m.rd(r + 0x39),
                                  s32(m.rd(r + 0x18, 4)) + 0xC80):
                return
        if sel in (0x62, 0x63):
            hit(m, 0, 0, 0, 3, 0, 0, 0, 0, 0, 0, 0, 0)
    elif lv == 17:
        if sel == 0:
            if f(0x51) == 0:
                m.wr(F(0x51), 1)
        elif sel == 1:
            if m.has(0x38) > 0:
                m.calls.append(("light", 0x200, 0, 0, 0, 0x64, 0x64, 0x64))
                if m.rd(SLOT_4) == 0x38:
                    m.calls.append(("equip_armour", 0x39, 4))
                take(m, 0x38)
                give(m, 0x39)
                m.calls.append(("light", 0x200, 0x64, 0x64, 0x64, 0, 0, 0))
        elif sel == 0x61:
            for i in (0x4E, 0x4F, 0x50):
                if f(i) == 0:
                    hit(m, 0, 0, 0, 0x40, 0, 0x63, 0, 0, 0, 0, 0, 0)
        elif sel == 0x63:
            hit(m, 0, 0, 0, 0x43, 0, 0, 0, 0, 0, 0, 0, PLAYER_POS)
    elif lv == 26:
        if sel == 0:
            if f(0x5E) != 1:
                m.wr(F(0x5E), 1)
        elif sel == 1:
            if f(0x61) != 1:
                m.wr(F(0x61), 1)
                m.calls.append(("recalc",))
        elif sel == 2:
            if f(0x61) != 0:
                m.wr(F(0x61), 0)
                m.calls.append(("recalc",))


def take(m, item):
    """take_item (0x8005d7f8): one from the first array that has one, and the
    level's entry 11."""
    for base in (levelin.INV_A, levelin.INV_B):
        if m.rd(base + item):
            m.wr(base + item, m.rd(base + item) - 1)
            m.calls.append(("hook", "take"))
            return


def give(m, item):
    """give_item (0x8005d898): one more in the first array under 99 and the
    level's entry 6; both full, announce 0xb."""
    for base in (levelin.INV_A, levelin.INV_B):
        if m.rd(base + item) < 0x63:
            m.wr(base + item, m.rd(base + item) + 1)
            m.calls.append(("hook", "give"))
            return
    m.calls.append(("announce", 0xB))


def arm(lv, m, k):
    """Opcode 0xe1's arm (0x8004a868) for record `k`."""
    r = O(k)
    x, z = s32(m.rd(r + 0x14, 4)) >> 11, s32(m.rd(r + 0x1C, 4)) >> 11
    if not player_in_rect(m, x, z, m.rd(r + 0x38), m.rd(r + 0x39), s32(m.rd(r + 0x18, 4))):
        m.wr(r + 0x40, 0)
        return
    if m.rd(r + 0x40):
        return
    mode = m.rd(r + 0x3A)
    if not mode & 0x80:
        m.wr(r + 0x40, 1)
    sel = mode & 0xF
    if sel == 0:
        entry3(lv, m, k)
    elif sel == 1:
        levelin.object_signal(m, m.rd(r + 0x3B))
    elif sel == 2:
        m.wr(F(FLAG_BASE + m.rd(r + 0x3B)), m.rd(r + 0x3C))


# --- against the game's own ---------------------------------------------------

def _stack(c, n):
    return tuple(c.rd(c.r[29] + 0x10 + 4 * i, 4) for i in range(n))


def game_run(cpu, k):
    """GAME.EXE's own arm for record `k` (and the level's entry 3 out of its
    overlay): [the calls it made that the model logs, in order]."""
    import mipsrun
    calls = []
    hooks = struct.unpack_from("<I", cpu.ram, useitem.LEVEL_HOOKS & MASK)[0]
    entry = lambda n: struct.unpack_from("<I", cpu.ram, (hooks + 4 * n) & MASK)[0]   # noqa: E731
    r4 = lambda c: tuple(c.r[4:8])                                             # noqa: E731
    cpu.hooks = dict(cpu.hooks)
    cpu.hooks.update({
        STAMP_RECT: lambda c: calls.append(("stamp",) + r4(c) + _stack(c, 5)),
        TAKE_HIT: lambda c: calls.append(("hit",) + r4(c) + _stack(c, 8)),
        HURT: lambda c: calls.append(("hurt",) + r4(c) + _stack(c, 12)),
        SOUND_AT: lambda c: calls.append(("sound_at",) + r4(c)),
        LIGHT: lambda c: calls.append(("light",) + r4(c) + _stack(c, 3)),
        EQUIP_ARMOUR: lambda c: calls.append(("equip_armour", c.r[4], c.r[5])),
        RECALC: lambda c: calls.append(("recalc",)),
        ANNOUNCE: lambda c: calls.append(("announce", c.r[4])),
        RENDER_FRAME: lambda c: calls.append(("frame",)),
        entry(11): lambda c: calls.append(("hook", "take")),
        entry(6): lambda c: calls.append(("hook", "give")),
    })
    for a in QUIET:
        cpu.hooks[a] = lambda c: 0
    mipsrun.object_arm(cpu, k)
    return calls


def records(lv):
    """The level's 0xe1 records, as its own loader leaves them: [slot]."""
    import objload
    return [k for k, o in sorted(objload.Load(lv).recs.items()) if o["op"] == TRIGGER_OP]


def cases(lv, n, rng, snap="a1"):
    """`n` runs of each 0xe1 record of level `lv`: [(the machine, the slot)]."""
    import mipsrun
    ks = records(lv)
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
            cx, cz = useitem.s32(cpu.rd(r + 0x14, 4)) >> 11, useitem.s32(cpu.rd(r + 0x1C, 4)) >> 11
            w, h, y = cpu.rd(r + 0x38, 1), cpu.rd(r + 0x39, 1), useitem.s32(cpu.rd(r + 0x18, 4))
            if rng.random() < 0.7:
                px = (cx + rng.randrange(max(w, 1))) * 0x800 + rng.randrange(0x800)
                pz = (cz + rng.randrange(max(h, 1))) * 0x800 + rng.randrange(0x800)
            else:
                px = (cx - 2 + rng.randrange(w + 4)) * 0x800 + rng.randrange(0x800)
                pz = (cz - 2 + rng.randrange(h + 4)) * 0x800 + rng.randrange(0x800)
            py = y + rng.choice((0, -0x400, 0x400, -0xD00, 0x900, rng.randrange(-0x1000, 0x1000)))
            put(cpu, PLAYER_POS, 4, px)
            put(cpu, PLAYER_POS + 4, 4, py)
            put(cpu, PLAYER_POS + 8, 4, pz)
            put(cpu, r + 0x40, 1, rng.choice((0, 0, 0, 1)))
            put(cpu, WARPED, 1, rng.choice((0, 1)))
            put(cpu, PLAYER_STATE, 1, rng.choice((0, 0x10)))
            put(cpu, IN_HAND, 1, rng.choice((0x4B, 0xFF, 0x20)))
            put(cpu, SLOT_4, 1, rng.choice((0x38, 0xFF, 0x30)))
            for t in (0x38, 0x39):
                put(cpu, levelin.INV_A + t, 1, rng.choice((0, 1, 0x63)))
                put(cpu, levelin.INV_B + t, 1, rng.choice((0, 0, 1, 0x63)))
            for f in (6, 7, 0x12, 0x19, 0x34, 0x35, 0x4E, 0x4F, 0x50, 0x51, 0x5E, 0x61,
                      0x7B, 0x7C, 0x7D, 0x7E):
                put(cpu, F(f), 1, rng.choice((0, 0, 1, 1, 2)))
            put(cpu, O(44, 0x38), 1, rng.choice((0x9A, 0x9B, 0xFF)))
            put(cpu, O(58, 0x10), 2, rng.randrange(0x1000))
            out.append((cpu, k))
    return out


STACK_LO, STACK_HI = levelin.STACK_LO, levelin.STACK_HI


def compare(cpu, lv, k):
    """One run both ways: (what it did, None) when they agree, else what differs."""
    ram = bytes(cpu.ram)
    m = Mem(ram)
    # what object_interpreter's loop publishes before it switches: the
    # record and its type row (object_arm does the same)
    m.wr(0x80198394, O(k), 4)
    m.wr(0x80198390, useitem.TYPES + 24 * m.rd(O(k, 6), 2), 4)
    arm(lv, m, k)
    got = game_run(cpu, k)
    what = (lv, hash((tuple(m.calls), tuple(sorted((a, m.ram[a & MASK]) for a in m.written)))))
    if m.calls != got:
        return what, f"slot {k}: calls: model {m.calls}, game {got}"
    a, b = m.ram, cpu.ram
    for lo, hi in ((0, STACK_LO), (STACK_HI, len(a))):
        if a[lo:hi] != b[lo:hi]:
            for i in range(lo, hi):
                if a[i] != b[i]:
                    return what, (f"slot {k}: {0x80000000 | i:#x}: model {a[i]:#x}, game "
                                  f"{b[i]:#x} ({levelin._where(0x80000000 | i)})")
    return what, None


def check(out=sys.stdout, per_record=30, seed=41, verbose=False):
    """The model against the game's own arm and every level's entry 3."""
    rng = random.Random(seed)
    ok = n = 0
    seen = {}
    told = False
    for lv in range(28):
        try:
            runs = cases(lv, per_record, rng)
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
    for lv in range(28):
        ways = [w for w in seen if w[0] == lv]
        if ways:
            print(f"  level {lv:2d}: {sum(seen[w] for w in ways):4d} runs, {len(ways)} different "
                  f"outcomes", file=out)
    print(f"opcode 0xe1 and entry 3, against the game's own over 28 levels: {ok} of {n} runs "
          f"agree -- the calls and all of RAM but the stack", file=out)
    return ok == n


def export(out_dir, per_record=4, seed=43):
    """triggercheck.json: runs of the model over every 0xe1 record -- the
    bytes it read, the calls and the bytes it wrote -- which godot/selftest.gd
    holds godot/triggers.gd to."""
    import json
    rng = random.Random(seed)
    rows = []
    for lv in range(28):
        try:
            runs = cases(lv, per_record, rng)
        except Exception:                                          # noqa: BLE001
            continue
        for cpu, k in runs:
            m = Mem(bytes(cpu.ram))
            arm(lv, m, k)
            rows.append({"level": lv, "slot": k,
                         "read": [[a, v] for a, v in sorted(m.read.items())],
                         "calls": [list(c) for c in m.calls],
                         "wrote": [[a, m.ram[a & MASK]] for a in sorted(m.written)]})
    path = os.path.join(out_dir, "triggercheck.json")
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
    for lv in range(28):
        try:
            ks = records(lv)
        except Exception:                                          # noqa: BLE001
            continue
        if ks:
            print(f"level {lv:2d}: 0xe1 records {ks}")


if __name__ == "__main__":
    main()
