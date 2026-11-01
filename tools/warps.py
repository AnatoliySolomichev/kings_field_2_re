#!/usr/bin/env python3
"""The pads that carry the player: opcode 0xeb.

    python3 tools/warps.py            every pad and where it goes
    python3 tools/warps.py --check    the model against the game's own arm
    python3 tools/warps.py --export D warpcheck.json for the self-test

**Opcode `0xeb`** (`object_interpreter+0x32d0`, 0x8004a2e0): 16 objects of
levels 7, 8, 16, 17, 19, 20 and 24, each a flat square 2816 across, lying on the floor of one cell. Its
record is one of warp_to's own records (0x800130f0), but for the facing's size:
`+0x38` the level, `+0x39` and `+0x3a` the block's last two bytes, `+0x3b` and
`+0x3c` the cell, `+0x3d` the height in 128s, `+0x3e` the facing negated, in
16ths. `+0x3f` 0 switches it off altogether, and the levels' own code holds it
there: level 17's slot 63 till flag 0x52, level 19's 85 till the creature in slot
0x14 dies (flag 0x55), with the record's `+0` 0 so that it is not drawn either.
A level of 0xff goes nowhere: level 20's slots 2 and 4 and level 24's 46.

```
+0x3f 0                 nothing at all
+0x38 not 0xff          the player not in its own cell (at its height): +0x40 0
                        in it, +0x40 0: every 0xeb's +0x40 1, and the warp below
level 24                type 0x144 turns 0x80 a frame, 0x145 0x100
```

The loader leaves `+0x40` 1, so a player put down on one is not carried again
till they have stepped off it.

The warp is warp_to's, without its answer and its last screen_fade:
fade_frames(1, 0, 0x1000, 0x100), actors_retire_marked, level_load till nothing
is under way; object_trigger(L, L, L, -, -) for a level not the block in hand, or
(-, -, L, -, -) and spawn_anywhere 1 for that one; level_load again; res_wait;
the player's state, 0x801b2620..0x801b2625 and the 8 bytes of view_angles from
player_pitch; the cell's middle, the height, the facing (the view's yaw too);
fade_frames(1, 0x1000, 0x1000, 0), res_wait, fade_frames(1, 0x1000, 0, -0x100);
object_trigger(-, -, -, +0x39, +0x3a). The tilt at 0x801b2618 is left alone,
which warp_to clears.

So they are a network: 7 and 16; 16 and 17, twice; 8 and 19; 19 and 20; two
pads of 20 into each other; and **24 into 25**, one way, the only way onto the
last level.

**How it is held to the game.** The arm: GAME.EXE's own for every 0xeb record
(`mipsrun.object_arm`), the player in and about the cell at heights about it,
`+0x3f`, `+0x38`, `+0x40`, the view and the block in hand at random, the calls
stood in for and logged, level_load ending a change at once: the same calls and
all of RAM but the stack.
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import levelin                                                       # noqa: E402
import triggers                                                      # noqa: E402
import useitem                                                       # noqa: E402
from levelin import O, Mem                                           # noqa: E402

OP = 0xEB
LEVELS = (7, 8, 16, 17, 19, 20, 24)
NO_LEVEL = 0xFF
BLOCK = 0x8018FAD8           # current_level_block
TURNING_LEVEL = 24
TURNS = {0x144: 0x80, 0x145: 0x100}
UNSET = 0x7F                 # object_trigger's last three: nothing asked
CURRENT_OBJECT, CURRENT_TYPE, OBJECT_TYPES = 0x80198394, 0x80198390, 0x8018FB3C
PLAYER_POS = triggers.PLAYER_POS
PLAYER_ANGLES = useitem.PLAYER_ANGLES
VIEW_ANGLES, VIEW_ADD = useitem.VIEW_ANGLES, useitem.VIEW_ADD
SPAWN_ANYWHERE, PLAYER_STATE = useitem.SPAWN_ANYWHERE, useitem.PLAYER_STATE
OUT = [1, 0, 0x1000, 0x100]
BACK = [[1, 0x1000, 0x1000, 0], [1, 0x1000, 0, -0x100]]


def s32(v):
    v &= 0xFFFFFFFF
    return v - 0x100000000 if v & 0x80000000 else v


def plan(d, block, pitch):
    """The warp in the port's terms, as KFUseItem.warp_plan makes warp_to's:
    the level, the block, whether it is the level in hand, the place, the
    facing and the fades. `d` holds the record's +0x38..+0x3e, `block` the
    five bytes in hand."""
    lv = d["lock"]
    same = lv == block[0]
    trig = [[NO_LEVEL, NO_LEVEL, lv, NO_LEVEL, NO_LEVEL] if same else [lv, lv, lv, NO_LEVEL, NO_LEVEL],
            [NO_LEVEL, NO_LEVEL, NO_LEVEL, d["b39"], d["b3a"]]]
    b = list(block)
    for t in trig:
        for k in range(5):
            if t[k] != NO_LEVEL:
                b[k] = t[k]
    return {"level": b[1], "block": b, "same": same,
            "pos": [(d["b3b"] << 11) + 0x400, -(d["b3d"] << 7), (d["b3c"] << 11) + 0x400],
            "facing": (-(d["b3e"] << 4)) & 0xFFF, "pitch": pitch, "answer": 0,
            "out": OUT, "back": BACK, "clear": False, "tilt": False}


def trigger(a, b, c, d, e):
    return ("trigger", a, b, c, d, e, UNSET, UNSET, UNSET)


def carry(m, r, calls):
    """The warp, over the record at `r`."""
    d = {"lock": m.rd(r + 0x38), "b39": m.rd(r + 0x39), "b3a": m.rd(r + 0x3A),
         "b3b": m.rd(r + 0x3B), "b3c": m.rd(r + 0x3C), "b3d": m.rd(r + 0x3D),
         "b3e": m.rd(r + 0x3E)}
    p = plan(d, [m.rd(BLOCK + i) for i in range(5)], 0)
    lv = d["lock"]
    calls += [("fade", *p["out"]), ("retire",), ("upload",), ("level_load",)]
    if p["same"]:
        calls.append(trigger(NO_LEVEL, NO_LEVEL, lv, NO_LEVEL, NO_LEVEL))
        m.wr(SPAWN_ANYWHERE, 1)
    else:
        calls.append(trigger(lv, lv, lv, NO_LEVEL, NO_LEVEL))
    calls += [("upload",), ("level_load",), ("res_wait",)]
    m.wr(PLAYER_STATE, 0)
    for k in (0, 2, 4):
        m.wr(VIEW_ADD + k, 0, 2)
    for k in (0, 4):
        m.wr(VIEW_ANGLES + k, m.rd(PLAYER_ANGLES + k, 4), 4)
    x, y, z = p["pos"]
    m.wr(PLAYER_POS, x & 0xFFFFFFFF, 4)
    m.wr(PLAYER_POS + 8, z & 0xFFFFFFFF, 4)
    m.wr(PLAYER_POS + 4, y & 0xFFFFFFFF, 4)
    face = (-(d["b3e"] << 4)) & 0xFFFF
    m.wr(PLAYER_ANGLES + 2, face, 2)
    m.wr(VIEW_ANGLES + 2, face, 2)
    back = p["back"]
    calls += [("fade", *back[0]), ("res_wait",),
              ("fade", back[1][0], back[1][1], back[1][2], back[1][3] & 0xFFFFFFFF)]
    calls.append(trigger(NO_LEVEL, NO_LEVEL, NO_LEVEL, d["b39"], d["b3a"]))


def arm(m, k, calls):
    """Opcode 0xeb's arm for the record in slot k over `m`."""
    r = O(k)
    if m.rd(r + 0x3F) == 0:
        return
    if m.rd(r + 0x38) != NO_LEVEL:
        cx, cz = s32(m.rd(r + 0x14, 4)) >> 11, s32(m.rd(r + 0x1C, 4)) >> 11
        if not triggers.player_in_rect(m, cx, cz, 1, 1, s32(m.rd(r + 0x18, 4))):
            m.wr(r + 0x40, 0)
        elif m.rd(r + 0x40) == 0:
            for j in range(levelin.COUNT):
                if m.rd(O(j, 4)) == OP:
                    m.wr(O(j, 0x40), 1)
            carry(m, r, calls)
    if m.rd(BLOCK) == TURNING_LEVEL:
        t = TURNS.get(m.rd(r + 6, 2))
        if t:
            m.wr(r + 0x26, (m.rd(r + 0x26, 2) + t) & 0xFFFF, 2)


def records(ram):
    return [k for k in range(levelin.COUNT) if ram[O(k, 4) & levelin.MASK] == OP]


def hooks(cpu, calls):
    def stack(c, n):
        return [c.rd(c.r[29] + 0x10 + 4 * k, 4) for k in range(n)]

    def load(c):
        calls.append(("level_load",))
        c.wr(useitem.BUSY, 2, 0)

    cpu.hooks.update({
        useitem.WARP_FADE: lambda c: calls.append(("fade", c.r[4], c.r[5], c.r[6], c.r[7])),
        useitem.RETIRE: lambda c: calls.append(("retire",)),
        useitem.WARP_UPLOAD: lambda c: calls.append(("upload",)),
        useitem.LEVEL_LOAD: load,
        useitem.OBJECT_TRIGGER: lambda c: calls.append(
            ("trigger", c.r[4] & 0xFF, c.r[5] & 0xFF, c.r[6] & 0xFF, c.r[7] & 0xFF,
             *[v & 0xFF for v in stack(c, 4)])),
        useitem.RES_WAIT: lambda c: calls.append(("res_wait",)),
    })


def scene(rng, base, k):
    """The machine with record k's world drawn at random around it."""
    import mipsrun
    cpu = mipsrun.CPU(bytes(base.ram))
    cpu.hooks.update(base.hooks)
    r = O(k)
    x, y, z = (s32(cpu.rd(r + 0x14 + 4 * i, 4)) for i in range(3))
    px, pz = (x & ~0x7FF) + rng.randrange(0x800), (z & ~0x7FF) + rng.randrange(0x800)
    if rng.random() < 0.3:
        px += rng.choice((-0x800, 0x800))
    if rng.random() < 0.3:
        pz += rng.choice((-0x800, 0x800))
    py = y + rng.choice((0, 0, -0x400, 0x400, 0x7FF, 0x800, 0x801, -0xC80, -0xC81, 0x2000))
    for a, v in ((PLAYER_POS, px), (PLAYER_POS + 4, py), (PLAYER_POS + 8, pz)):
        cpu.wr(a, 4, v & 0xFFFFFFFF)
    if rng.random() < 0.2:
        cpu.wr(r + 0x3F, 1, rng.choice((0, 1, 0xFF)))
    if rng.random() < 0.1:
        cpu.wr(r + 0x38, 1, NO_LEVEL)
    for j in records(cpu.ram):
        cpu.wr(O(j, 0x40), 1, rng.choice((0, 0, 1, 0xFF)))
    block = [rng.choice((cpu.rd(r + 0x38, 1), base.level, rng.randrange(28))), base.level,
             rng.randrange(28), rng.randrange(28), rng.randrange(28)]
    for i, b in enumerate(block):
        cpu.wr(BLOCK + i, 1, b)
    for a in (PLAYER_ANGLES, PLAYER_ANGLES + 2, PLAYER_ANGLES + 4, PLAYER_ANGLES + 6,
              VIEW_ANGLES, VIEW_ANGLES + 2, VIEW_ADD, VIEW_ADD + 2, VIEW_ADD + 4):
        cpu.wr(a, 2, rng.randrange(0x10000))
    cpu.wr(PLAYER_STATE, 1, rng.choice((0, 1, 2)))
    cpu.wr(SPAWN_ANYWHERE, 1, 0)
    return cpu


def check(out=sys.stdout, per_record=60, seed=131):
    import mipsrun
    rng = random.Random(seed)
    alike = n = fired = same = 0
    first = None
    for lv in LEVELS:
        base = mipsrun.level_cpu(lv)
        base.level = lv
        for k in records(base.ram):
            for _ in range(per_record):
                cpu = scene(rng, base, k)
                m = Mem(bytes(cpu.ram))
                calls, game = [], []
                hooks(cpu, game)
                mipsrun.object_arm(cpu, k)
                m.wr(CURRENT_OBJECT, O(k), 4)
                m.wr(CURRENT_TYPE, OBJECT_TYPES + 24 * m.rd(O(k, 6), 2), 4)
                arm(m, k, calls)
                n += 1
                fired += bool(calls)
                same += bool(calls) and m.rd(SPAWN_ANYWHERE) == 1
                why = None
                if calls != game:
                    why = next((f"calls: model {a}, game {b}" for a, b in zip(calls, game)
                                if a != b), f"calls: model {len(calls)}, game {len(game)}")
                else:
                    a, b = m.ram, cpu.ram
                    for lo, hi in ((0, levelin.STACK_LO), (levelin.STACK_HI, len(a))):
                        if a[lo:hi] != b[lo:hi]:
                            i = next(i for i in range(lo, hi) if a[i] != b[i])
                            why = (f"{0x80000000 | i:#x}: model {a[i]:#x}, game {b[i]:#x} "
                                   f"({levelin._where(0x80000000 | i)})")
                            break
                if why is None:
                    alike += 1
                elif first is None:
                    first = f"level {lv} slot {k}: {why}"
    print(f"opcode 0xeb, the game's own arm: {alike} of {n} runs over the 16 pads agree -- the "
          f"calls in order and all of RAM but the stack; {fired} carried the player, {same} on "
          f"the block in hand", file=out)
    if first:
        print(f"  first difference: {first}", file=out)
    return alike == n


class Scripted:
    """A world for the self-test: every question logged with its answer."""

    def __init__(self, rng, log, level):
        self.rng, self.log, self.level = rng, log, level

    def rect(self, cx, cz, w, h, y):
        ans = int(self.rng.random() < 0.5)
        self.log.append(["rect", cx, cz, w, h, y, ans])
        return ans

    def carry(self, d):
        self.log.append(["carry"])
        d["b40"] = 1


def step(d, w):
    """The arm on the port's dictionary; `w` the world (rect, carry, level)."""
    if d["b3f"] == 0:
        return
    if d["lock"] != NO_LEVEL:
        if not w.rect(d["x"] >> 11, d["z"] >> 11, 1, 1, d["y"]):
            d["b40"] = 0
        elif d["b40"] == 0:
            w.carry(d)
    if w.level == TURNING_LEVEL:
        d["yaw"] = (d["yaw"] + TURNS.get(d["type"], 0)) & 0xFFFF


def export(out_dir, frames=24, seed=137):
    """warpcheck.json: for godot/selftest.gd, runs of step and plans."""
    import json
    import objload
    rng = random.Random(seed)
    runs, plans = [], []
    for lv in LEVELS:
        ld = objload.Load(lv)
        for k, o in sorted(ld.recs.items()):
            if o["op"] != OP:
                continue
            t = o["tail"]
            d = {"slot": k, "type": o["type"], "lock": t[0], "b39": t[1], "b3a": t[2], "b3b": t[3],
                 "b3c": t[4], "b3d": t[5], "b3e": t[6], "b3f": t[7], "b40": t[8], "x": o["x"],
                 "y": o["y"], "z": o["z"], "yaw": o["angles"][1] & 0xFFFF}
            run = {"d": dict(d), "level": lv, "frames": []}
            for _ in range(frames):
                if rng.random() < 0.1:
                    d["b3f"] = rng.choice((0, 0xFF))
                b3f, log = d["b3f"], []
                step(d, Scripted(rng, log, lv))
                run["frames"].append({"b3f": b3f, "calls": log, "out": [d["b40"], d["yaw"]]})
            runs.append(run)
            if t[0] != NO_LEVEL:
                for _ in range(4):
                    block = [rng.choice((t[0], lv)), lv, rng.randrange(28), rng.randrange(28),
                             rng.randrange(28)]
                    pitch = rng.randrange(0x1000)
                    plans.append({"d": dict(d), "block": block, "pitch": pitch,
                                  "plan": plan(d, block, pitch)})
    path = os.path.join(out_dir, "warpcheck.json")
    with open(path, "w") as fh:
        json.dump({"runs": runs, "plans": plans}, fh, separators=(",", ":"))
    return path


def show(out=sys.stdout):
    import objload
    for lv in LEVELS:
        ld = objload.Load(lv)
        for k, o in sorted(ld.recs.items()):
            if o["op"] != OP:
                continue
            t = o["tail"]
            to = "nowhere" if t[0] == NO_LEVEL else (
                f"level {t[0]} cell ({t[3]}, {t[4]}) y {-(t[5] << 7)} facing "
                f"{(-(t[6] << 4)) & 0xFFF:#x}, block {t[1]} {t[2]}")
            print(f"level {lv:2d} slot {k:3d} ({o['x'] >> 11:2d}, {o['z'] >> 11:2d}) type "
                  f"{o['type']} -> {to}", file=out)


def main():
    a = sys.argv[1:]
    if "--export" in a:
        print(export(a[a.index("--export") + 1]))
        return 0
    if "--check" in a:
        return 0 if check() else 1
    show()
    return 0


if __name__ == "__main__":
    sys.exit(main())
