#!/usr/bin/env python3
"""What a conversation's `0xf4` runs: every level's entry 4, against the overlays' own.

    python3 tools/hooks.py              every level's arms, one line each
    python3 tools/hooks.py --check      the model against the overlays' own code
    python3 tools/hooks.py --export D   hookcheck.json, the runs the self-test
                                        holds godot/talk.gd to

`0xf4 a` in a conversation calls the level's own **entry 4** (`level_hooks +
0x10`) with the creature and `a` (`script_interpreter+0x1b8`), and
`tools/quest.py` reads which arm each conversation asks for. This is what
each arm does, read off the overlays' MIPS -- fifteen levels, 45 arms:

```
level 0   0  flags[3] = the three pieces of Ichrius (0x82..0x84) and the
             sword (2) held
          1  all four held: flags[1] 1, answered, the four taken, and the
             sword put down if it is in hand (equip_weapon(0xff))
          2  flags[2] 1, flags[4] the play clock's minute (play_minutes
             % 60), flags[5] (player_exp % 10000) / 100, slot 1's category
             8 and slot 2's 1
          3  nothing
          4  flags[6] 1 when the minute is under flags[4] or at flags[4]
             + 10 or past it, or the same of the experience against flags[5]
          5  flags[1] = the three pieces held
level 1   0  flags[0xd] 0: 1, and stamp_rect(2, 0x4e, 0, 0x1b, 0x11, 1, 7,
             0, 0x2f) -- a strip of seven cells at (27, 17) from the block
             at (78, 0)
          1  object_give(0x74)          2  object_give(0x72)
level 2   0..3  flags[0x10] 0x68, 0x6c, 0x6d, 0x6b -- the thing slot 4 asks
             for next (FORMATS.md, "The levels' own use of a thing")
          4  object_give(0x56)          5  object_give(0x52)
level 3   0  flags[0x77] = 0x7c held
          1  a frame without the panel (render_frame_bare) and the pack's
             chooser (0x80021d94); buttons ~bind_use; nothing chosen
             (below 0): flags[0x74] 0, flags[0x72] 0x68; else flags[0x75]
             0, flags[0x74] 1, flags[0x72] the thing chosen
          2  object_give(flags[0x72])
level 4   0  flags[0x17] not 1: 1, object_give(0x7b)
          1  flags[0x18] not 1: 1, object_give(0x5f)
          2  0x84 held: flags[0x1a] 1
          3  slot 8's category 8        4  flags[0x16] 1
level 5   0  every object of opcode 0x56 off: scale 0, +0x38 0, +0 0,
             opcode 0xff; 0x66 held: taken; object_give(0x82), flags[0x1e] 1
          1  flags[0x1d] 0: object_give(0x60), flags[0x1d] 1
          2  object_give(0x66)
level 6   0  flags[0x22] 1              1  object_give(0x80)
          2  flags[0x21] 1              3  object_give(0x83), flags[0x24] 1
          4  the light: 0x8005d948(0x200, 0, 0, 0, 0x80, 0xc8, 0x80) and
             back (0x200, 0x80, 0xc8, 0x80, 0, 0, 0), 0x8003da10(0, 0, 0,
             0, 1); flags[0x27] 1 and spells 0x38, 0x3a, 0x3c, 0x3e, 0x40
             and 0x4c unlocked -- the lesson in Varde's wood
          5  object_give(0xa)
level 7   0  flags[0x2a] 1
level 8   0  the light as level 6's; flags[0x2d] 1 and spells 0x36, 0x37,
             0x42..0x4b unlocked
          1  flags[0x2e] 1, slot 1's category 8
level 9   0  flags[0x33] 1              1  flags[0x34] 1
level 10  0  object_give(0x90)          1  flags[0x39] 0: 1
level 13  0  flags[0x42] 0: 1, flags[0x43] 0
level 17  0  flags[0x52] not 1: 1, and five things given and put on --
             0x29, 0x31, 0x46, 0x4f, 0x3c (equip_armour in slots 0..4);
             object 63's +0 2 and +0x3f 0xff
          1  flags[0x53] 1: 2, the light (0x200, 0, 0, 0, 0xc8, 0xc8,
             0xc8) and back, skill 4 + 0x1e (unbounded), skill_unlock(4),
             the stats; slot 56's category 8 and its +3 0
level 22  0  flags[0x5b] 1              1  flags[0x5c] 1
level 26  0  flags[0x60] 0: 1, object_signal(0xf2), sound_key_fits
```

An arm past the table (or a level with none) does nothing.

**How it is held to the game.** `check()` runs each level's own entry 4 out
of its overlay with `tools/mipsrun.py`, over the level as its own
load_object_placement leaves it (`mipsrun.level_cpu`): every arm, and one
past the last, with the story flags it reads, the pack, the categories, the
skills, the spells, the play clock, the experience, the weapon in hand and
the chooser's answer drawn at random. What it calls beyond what it runs is
stood in for and logged -- object_give, stamp_rect, equip_weapon,
equip_armour, the light (0x8005d948), 0x8003da10, render_frame_bare, the
chooser, sound_key_fits, player_recalc_stats, announce and the level's own
entry 11 (take_item's) -- and has_item, take_item, skill_unlock and
object_signal run as the game's. The model must give the same calls in
order, the same flags, pack, categories, the creatures' +3, skills, spells,
answer and buttons, and all 396 object records byte for byte: 2400 of 2400.

**In the port** `godot/talk.gd hook` is the same arms over a world
`godot/loot.gd _hook` hands it out of the port, and the self-test holds it to
`export()`'s runs (`hookcheck.json`).
"""
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import useitem                                                       # noqa: E402

MASK = 0x1FFFFF
LEVEL_HOOKS = useitem.LEVEL_HOOKS
HOOK = 4                            # entry 4: level_hooks + 0x10
OBJECT_GIVE = 0x8005DB30
STAMP_RECT = 0x800445B8
EQUIP_WEAPON = 0x8002BDC0
EQUIP_ARMOUR = 0x8002BB84
LIGHT = 0x8005D948                  # frames of the light moving between two colours
DA10 = 0x8003DA10
BARE = 0x80030568                   # render_frame_bare
CHOOSER = 0x80021D94                # the pack's chooser, ui_panel mode 0xc
PLAY_MINUTES = 0x801B2588
PLAYER_EXP = 0x801B24E4
WEAPON = 0x801B25AF                 # equipped_weapon
BUTTONS = 0x801B265C
BIND_USE = 0x80081876

PIECES = (0x82, 0x83, 0x84)         # Ichrius' eye, wings, crown
SWORD = 2
SPELLS_6 = (0x38, 0x3A, 0x3C, 0x3E, 0x40, 0x4C)
SPELLS_8 = (0x36, 0x37) + tuple(range(0x42, 0x4C))
# what each level's arms hand over through object_give (level 3's arm 2 the
# thing flags[0x72] names, 0x68 when nothing was chosen)
GIVES = {1: (0x74, 0x72), 2: (0x56, 0x52), 3: (0x68,), 4: (0x7B, 0x5F), 5: (0x82, 0x60, 0x66),
         6: (0x80, 0x83, 0xA), 10: (0x90,), 17: (0x29, 0x31, 0x46, 0x4F, 0x3C)}
ARMS = {0: 6, 1: 3, 2: 6, 3: 3, 4: 5, 5: 3, 6: 6, 7: 1, 8: 2, 9: 2, 10: 2, 13: 1,
        17: 2, 22: 2, 26: 1}


def world_of(ram):
    """useitem's world, and what the hooks read besides: the creatures' +3,
    the scale triple of every object, the play clock, the experience, the
    weapon in hand, the buttons and USE's binding."""
    w = useitem.world_of(ram)

    def rd(a, n):
        return int.from_bytes(ram[a & MASK:(a & MASK) + n], "little")
    w["floors"] = [rd(useitem.ACTORS + useitem.ACTOR_STRIDE * k + 3, 1)
                   for k in range(useitem.ACTOR_N)]
    for o in w["objects"]:
        r = useitem.OBJECTS + useitem.STRIDE * o["slot"]
        o["scale"] = [rd(r + 0x2C + 2 * i, 2) for i in range(3)]
    w["minutes"] = rd(PLAY_MINUTES, 4)
    w["exp"] = rd(PLAYER_EXP, 4)
    w["weapon"] = rd(WEAPON, 1)
    w["buttons"] = rd(BUTTONS, 2)
    w["bind_use"] = rd(BIND_USE, 2)
    return w


def write_back(ram, w):
    useitem.write_back(ram, w)
    for k, v in enumerate(w["floors"]):
        ram[(useitem.ACTORS + useitem.ACTOR_STRIDE * k + 3) & MASK] = v
    for o in w["objects"]:
        r = (useitem.OBJECTS + useitem.STRIDE * o["slot"]) & MASK
        for i, v in enumerate(o["scale"]):
            struct.pack_into("<H", ram, r + 0x2C + 2 * i, v)


def s32(v):
    v &= 0xFFFFFFFF
    return v - (1 << 32) if v & 0x80000000 else v


def tdiv(a, b):
    """a / b as the CPU's div leaves it: towards zero."""
    q = abs(a) // abs(b)
    return q if (a < 0) == (b < 0) else -q


def has(w, item):
    return w["inv_a"][item] + w["inv_b"][item] > 0


def hook(w, lv, arm):
    """Entry 4 of level `lv` with `arm` over the world `w`, which it changes
    as the overlay's code changes RAM: [the calls it makes beyond what it
    runs, in order]."""
    calls = []
    f = w["flags"]

    def give(t):
        calls.append(("give", t))

    def take(t):
        useitem.take_item(w, calls, t)

    def light(*a):
        calls.append(("light",) + a)
    if lv == 0:
        if arm == 0:
            f[3] = 1 if has(w, SWORD) and all(has(w, p) for p in PIECES) else 0
        elif arm == 1:
            if all(has(w, p) for p in PIECES) and has(w, SWORD):
                f[1] = 1
                w["answer"] = 1
                for t in PIECES + (SWORD,):
                    take(t)
                if w["weapon"] == SWORD:
                    calls.append(("equip_weapon", 0xFF))
        elif arm == 2:
            mins = w["minutes"] % 60
            exp = s32(w["exp"])
            w["cats"][1] = 8
            f[2] = 1
            w["cats"][2] = 1
            f[4] = mins & 0xFF
            f[5] = tdiv(exp - 10000 * tdiv(exp, 10000), 100) & 0xFF
        elif arm == 4:
            mins = w["minutes"] % 60
            if mins < f[4] or not mins < f[4] + 10:
                f[6] = 1
            exp = s32(w["exp"])
            e = tdiv(exp - 10000 * tdiv(exp, 10000), 100)
            if e < f[5] or not e < f[5] + 10:
                f[6] = 1
        elif arm == 5:
            f[1] = 1 if all(has(w, p) for p in PIECES) else 0
    elif lv == 1:
        if arm == 0:
            if f[0xD] == 0:
                f[0xD] = 1
                calls.append(("stamp", 2, 0x4E, 0, 0x1B, 0x11, 1, 7, 0, 0x2F))
        elif arm == 1:
            give(0x74)
        elif arm == 2:
            give(0x72)
    elif lv == 2:
        if arm < 4:
            f[0x10] = (0x68, 0x6C, 0x6D, 0x6B)[arm]
        elif arm == 4:
            give(0x56)
        elif arm == 5:
            give(0x52)
    elif lv == 3:
        if arm == 0:
            f[0x77] = 1 if has(w, 0x7C) else 0
        elif arm == 1:
            calls.append(("bare",))
            calls.append(("choose",))
            got = s32(w["chosen"])
            w["buttons"] = ~w["bind_use"] & 0xFFFF
            if got < 0:
                f[0x74] = 0
                f[0x72] = 0x68
            else:
                f[0x75] = 0
                f[0x74] = 1
                f[0x72] = got & 0xFF
        elif arm == 2:
            give(f[0x72])
    elif lv == 4:
        if arm in (0, 1):
            k = 0x17 if arm == 0 else 0x18
            if f[k] != 1:
                f[k] = 1
                give(0x7B if arm == 0 else 0x5F)
        elif arm == 2:
            if has(w, 0x84):
                f[0x1A] = 1
        elif arm == 3:
            w["cats"][8] = 8
        elif arm == 4:
            f[0x16] = 1
    elif lv == 5:
        if arm == 0:
            for o in w["objects"]:
                if o["op"] == 0x56:
                    o["scale"] = [0, 0, 0]
                    o["b38"] = 0
                    o["b0"] = 0
                    o["op"] = 0xFF
            if has(w, 0x66):
                take(0x66)
            give(0x82)
            f[0x1E] = 1
        elif arm == 1:
            if f[0x1D] == 0:
                give(0x60)
                f[0x1D] = 1
        elif arm == 2:
            give(0x66)
    elif lv == 6:
        if arm == 0:
            f[0x22] = 1
        elif arm == 1:
            give(0x80)
        elif arm == 2:
            f[0x21] = 1
        elif arm == 3:
            give(0x83)
            f[0x24] = 1
        elif arm == 4:
            light(0x200, 0, 0, 0, 0x80, 0xC8, 0x80)
            light(0x200, 0x80, 0xC8, 0x80, 0, 0, 0)
            calls.append(("da10", 0, 0, 0, 0, 1))
            f[0x27] = 1
            for s in SPELLS_6:
                w["spells"][s] = 1
        elif arm == 5:
            give(0xA)
    elif lv == 7:
        if arm == 0:
            f[0x2A] = 1
    elif lv == 8:
        if arm == 0:
            light(0x200, 0, 0, 0, 0x80, 0xC8, 0x80)
            light(0x200, 0x80, 0xC8, 0x80, 0, 0, 0)
            f[0x2D] = 1
            for s in SPELLS_8:
                w["spells"][s] = 1
        elif arm == 1:
            f[0x2E] = 1
            w["cats"][1] = 8
    elif lv == 9:
        if arm in (0, 1):
            f[0x33 + arm] = 1
    elif lv == 10:
        if arm == 0:
            give(0x90)
        elif arm == 1:
            if f[0x39] == 0:
                f[0x39] = 1
    elif lv == 13:
        if arm == 0 and f[0x42] == 0:
            f[0x42] = 1
            f[0x43] = 0
    elif lv == 17:
        if arm == 0:
            if f[0x52] != 1:
                f[0x52] = 1
                for slot, t in enumerate((0x29, 0x31, 0x46, 0x4F, 0x3C)):
                    give(t)
                    calls.append(("equip_armour", t, slot))
                o = w["objects"][63]
                o["b0"] = 2
                o["b3f"] = 0xFF
        elif arm == 1:
            if f[0x53] == 1:
                f[0x53] = 2
                light(0x200, 0, 0, 0, 0xC8, 0xC8, 0xC8)
                light(0x200, 0xC8, 0xC8, 0xC8, 0, 0, 0)
                w["skills"][4] = (w["skills"][4] + 0x1E) & 0xFFFF
                useitem.skill_unlock(w, calls, 4)
                calls.append(("recalc",))
                w["cats"][56] = 8
                w["floors"][56] = 0
    elif lv == 22:
        if arm in (0, 1):
            f[0x5B + arm] = 1
    elif lv == 26:
        if arm == 0 and f[0x60] == 0:
            f[0x60] = 1
            useitem.object_signal(w, 0xF2)
            calls.append(("sound_key_fits",))
    return calls


# --- against the overlays' own ---------------------------------------------------

def _stack(c, n):
    return tuple(c.rd(c.r[29] + 0x10 + 4 * i, 4) for i in range(n))


def game_run(cpu, arm, chosen):
    """The overlay's own entry 4 over the machine's RAM: [the calls it made
    beyond what it ran, in order]."""
    calls = []
    hooks = struct.unpack_from("<I", cpu.ram, LEVEL_HOOKS & MASK)[0]
    entry = lambda n: struct.unpack_from("<I", cpu.ram, (hooks + 4 * n) & MASK)[0]   # noqa: E731
    r = lambda c: tuple(c.r[4:8])                                              # noqa: E731
    cpu.hooks = dict(cpu.hooks)
    cpu.hooks.update({
        OBJECT_GIVE: lambda c: calls.append(("give", c.r[5])),
        STAMP_RECT: lambda c: calls.append(("stamp",) + r(c) + _stack(c, 5)),
        EQUIP_WEAPON: lambda c: calls.append(("equip_weapon", c.r[4])),
        EQUIP_ARMOUR: lambda c: calls.append(("equip_armour", c.r[4], c.r[5])),
        LIGHT: lambda c: calls.append(("light",) + r(c) + _stack(c, 3)),
        DA10: lambda c: calls.append(("da10",) + r(c) + _stack(c, 1)),
        BARE: lambda c: calls.append(("bare",)),
        CHOOSER: lambda c: (calls.append(("choose",)), chosen)[1],
        useitem.SOUND_KEY_FITS: lambda c: calls.append(("sound_key_fits",)),
        useitem.RECALC: lambda c: calls.append(("recalc",)),
        useitem.ANNOUNCE: lambda c: calls.append(("announce", c.r[4])),
        entry(11): lambda c: calls.append(("hook", "take")),
        entry(6): lambda c: calls.append(("hook", "give")),
    })
    cpu.call(entry(HOOK), useitem.ACTORS, arm)
    return calls


ASKED = {0: (1, 2, 3, 4, 5, 6), 1: (0xD,), 2: (0x10,), 3: (0x72, 0x74, 0x75, 0x77),
         4: (0x16, 0x17, 0x18, 0x1A), 5: (0x1D, 0x1E), 6: (0x21, 0x22, 0x24, 0x27),
         7: (0x2A,), 8: (0x2D, 0x2E), 9: (0x33, 0x34), 10: (0x39,), 13: (0x42, 0x43),
         17: (0x52, 0x53), 22: (0x5B, 0x5C), 26: (0x60,)}
HELD = PIECES + (SWORD, 0x7C, 0x84, 0x66)


def cases(lv, n, rng, snap="a1"):
    """`n` runs of level `lv`'s entry 4: [(the machine, the arm, the
    chooser's answer)], laid out at random."""
    import mipsrun
    base = mipsrun.level_cpu(lv, snap)
    ram0 = bytes(base.ram)
    put = useitem._put
    out = []
    for _ in range(n):
        cpu = mipsrun.CPU(ram0)
        cpu.hooks.update(base.hooks)
        arm = rng.randrange(ARMS.get(lv, 1) + 1)
        for k in ASKED.get(lv, ()):
            put(cpu, useitem.FLAGS + k, 1, rng.choice((0, 0, 1, 1, 2, rng.randrange(0x100))))
        for t in HELD:
            put(cpu, useitem.INV_A + t, 1, rng.choice((0, 0, 1, 2)))
            put(cpu, useitem.INV_B + t, 1, rng.choice((0, 0, 0, 1)))
        for k in range(useitem.ACTOR_N):
            if rng.random() < 0.05:
                put(cpu, useitem.ACTORS + useitem.ACTOR_STRIDE * k, 1, rng.choice((0, 1, 2, 8)))
        for k in range(5):
            put(cpu, useitem.SKILLS + 2 * k, 2, rng.choice((0, 5, 0x3E7, 0xFFF0, rng.randrange(1000))))
        for i in range(96):
            if rng.random() < 0.3:
                put(cpu, useitem.SPELL_TABLE + 24 * i, 1, rng.choice((0, 1)))
        put(cpu, PLAY_MINUTES, 4, rng.choice((0, 59, 60, rng.randrange(1 << 20), rng.randrange(1 << 32))))
        put(cpu, PLAYER_EXP, 4, rng.choice((0, 9999, 10000, rng.randrange(1 << 24))))
        put(cpu, WEAPON, 1, rng.choice((SWORD, SWORD, 0, 0xFF, rng.randrange(0x20))))
        put(cpu, BIND_USE, 2, rng.randrange(0x10000))
        for k in range(useitem.COUNT):
            r = useitem.OBJECTS + useitem.STRIDE * k
            if lv == 5 and rng.random() < 0.05:
                put(cpu, r + 4, 1, 0x56)
            if lv == 26 and rng.random() < 0.05:
                put(cpu, r + 0x38, 1, 0xF2)
        chosen = rng.choice((-1, -1, rng.randrange(0x60, 0x96), rng.randrange(0x100)))
        cpu.level = lv
        out.append((cpu, arm, chosen))
    return out


FIELDS = ("flags", "inv_a", "inv_b", "cats", "floors", "skills", "spells", "answer", "buttons")


def compare(cpu, lv, arm, chosen):
    """One run both ways: (what it did, None) when they agree, else what differs."""
    ram = bytes(cpu.ram)
    w = world_of(ram)
    w["chosen"] = chosen & 0xFFFFFFFF
    w["answer"] = useitem.s32(cpu.rd(useitem.ANSWER, 4)) & 0xFFFFFFFF
    want = hook(w, lv, arm)
    got = game_run(cpu, arm, chosen & 0xFFFFFFFF)
    after = world_of(bytes(cpu.ram))
    after["answer"] = cpu.rd(useitem.ANSWER, 4)
    what = f"level {lv:2d} arm {arm}: " + (", ".join(c[0] for c in want) or "no call")
    if want != got:
        return what, f"calls: model {want}, game {got}"
    for f in FIELDS:
        if w[f] != after[f]:
            return what, f"{f}: model {w[f]}, game {after[f]}"
    mine = bytearray(ram)
    write_back(mine, w)
    lo, hi = useitem.OBJECTS & MASK, (useitem.OBJECTS & MASK) + useitem.STRIDE * useitem.COUNT
    if bytes(mine[lo:hi]) != bytes(cpu.ram[lo:hi]):
        for i in range(lo, hi):
            if mine[i] != cpu.ram[i]:
                k, off = divmod(i - lo, useitem.STRIDE)
                return what, f"object {k} +{off:#x}: model {mine[i]:#x}, game {cpu.ram[i]:#x}"
    return what, None


def check(out=sys.stdout, per_arm=40, seed=23, verbose=False):
    """The model against every level's own entry 4, every arm and one past."""
    rng = random.Random(seed)
    ok = n = 0
    seen = {}
    told = False
    for lv in sorted(ARMS):
        for cpu, arm, chosen in cases(lv, per_arm * (ARMS[lv] + 1), rng):
            n += 1
            what, why = compare(cpu, lv, arm, chosen)
            if why is None:
                ok += 1
                seen[what] = seen.get(what, 0) + 1
            elif not told or verbose:
                told = True
                print(f"  {what}: {why}", file=out)
    for what in sorted(seen):
        print(f"  {seen[what]:4d}  {what}", file=out)
    print(f"entry 4, against the overlays' own over {len(ARMS)} levels: {ok} of {n} runs agree "
          f"-- calls, flags, pack, categories, skills, spells and all 396 object records",
          file=out)
    return ok == n


OBJECT_LEVELS = (5, 17, 26)     # the levels whose arms touch the objects


def compact(w, lv):
    """A world as the self-test reads it: the fields the arms read and
    write, and on the levels whose arms touch them, every object as a row of
    useitem.OBJECT_FIELDS and its scale (the triple's first, the three alike)."""
    out = {k: list(w[k]) for k in ("flags", "inv_a", "inv_b", "cats", "floors", "skills",
                                   "spells")}
    for k in ("answer", "weapon", "minutes", "exp", "chosen", "buttons", "bind_use"):
        out[k] = w[k]
    out["objects"] = [[o[f] for f in useitem.OBJECT_FIELDS] + [o["scale"][0]]
                      for o in w["objects"] if lv in OBJECT_LEVELS and o["type"] != 0xFF]
    return out


def export(out_dir, per_arm=6, seed=29):
    """hookcheck.json: runs of the model, every level's arms and one past,
    which godot/selftest.gd holds godot/talk.gd's hook to."""
    import json
    rng = random.Random(seed)
    rows = []
    for lv in sorted(ARMS):
        for cpu, arm, chosen in cases(lv, per_arm * (ARMS[lv] + 1), rng):
            w = world_of(bytes(cpu.ram))
            w["chosen"] = useitem.s32(chosen)
            w["answer"] = 0
            before = compact(w, lv)
            calls = hook(w, lv, arm)
            after = compact(w, lv)
            want = {"calls": [list(c) for c in calls]}
            for k in after:
                if after[k] != before[k]:
                    want[k] = after[k]
            rows.append({"level": lv, "arm": arm, "world": before, "want": want})
    path = os.path.join(out_dir, "hookcheck.json")
    with open(path, "w") as fh:
        json.dump({"fields": list(useitem.OBJECT_FIELDS) + ["scale"], "cases": rows}, fh,
                  separators=(",", ":"))
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
