#!/usr/bin/env python3
"""The traps: opcodes 0x51 and 0x52.

    python3 tools/traps.py            every trap, by level
    python3 tools/traps.py --check    the models against the game's own arms
    python3 tools/traps.py --export D trapcheck.json for the self-test

Two arms of one kind: a model that moves by its clock `+0xa`, and two of its
vertices (one for 0x52) that strike whatever stands at them.

**Opcode `0x51`** (`object_interpreter+0x2178`, 0x80049188), 73 objects on
levels 0, 12, 15 and 18. `+0x3a` is the clock's step, in fours; `+0x3b` 0xff
says it runs from the start, 0xfe that it never does -- level 0's four and
level 18's twenty-five of type 219, which the loader takes away -- and
anything else is a rectangle, `+0x3b` by `+0x3c` from its own cell, the player
in which starts it. `+0x38` 0xff is its going; object_signal of its `+0x3d`
turns that between 0 and 0xff, which is what the levers of levels 12, 15 and
18 do.

```
state 0   +0x38 0: state 2, +1 1, the clock 0.  +0x3b 0xfe: nothing.  The
          rectangle answering, or 0xff: state 1, +1 0, the clock and +0x40 0,
          the type's sound (+0x16, plus 0x1f0; 0xff: 0x1e)
state 1   the swing. A rectangle's at clock 0: object_set_present(1, row +0x17)
          and sound 0x1e. +0x38 0 with a step of the end left: state 2, +1 1,
          the clock 0. The clock on by the step; at 0xfff or more a
          rectangle's ends -- the clock and the state 0, object_set_present(0)
          -- and a free one goes round with the sound, & 0xfff. A free one
          sounds again as it passes 0x800. Then the strike
state 2   +1 1: the clock on 0x40; at 0xfff or more, 0xfff, and with +0x38
          0xff state 3. The strike
state 3   the clock back 0x40; under 0, 0 and state 0. The strike
```

**Opcode `0x52`** (0x80049888), 21 objects on levels 15 and 18: the same on
another plan. `+0x3b`, `+0x3c`, `+0x3d` by `+0x3e` is a rectangle given
outright; a `+0x3d` not 0xff means it comes and goes with its run; the type's
sound is its own, unmoved; 0x1e sounds as the clock passes 0x5dc; one vertex,
the row's u16 at `+0xc`, and states 2 and 3 strike nothing. Its object_signal
id is `+0x3f`.

**The strike.** The point (`0x80046760`) is `model_vertex` of the model at +1
and the clock, each axis by the object's scale, turned by its angles with the
yaw a half turn on, from its place. `collide_query(point, row +0xe, row +0x10,
0x90)` asks the creatures and the player. Anything there, and `+0x40` clear:
`+0x40` 1 and `actor_attack_player(mask, 0x80, 0, 0x1388, 5, +0x39, row
+0x12..+0x15, 0, 0, 0, 0, 0, the point)` -- the mask whole, so a creature and
the player at once strike neither. Nothing there: `+0x40` 0. So a trap strikes
once a meeting.

`object_set_present` (0x80044b40) writes 0xfc into its own cell's tile with the
scale 0x1000, or the row's byte +0x17 with the scale 0; a trap that comes and
goes is the floor's own tile till then.

**How it is held to the game.** Every trap of a level, its own arm a frame in
slot order over `mipsrun.level_cpu`, the models put in RAM so that the game's
own `object_vertex_point` and `model_vertex` run; the locks turned as object_signal
turns them, the player moved in and out of the rectangles, `collide_query`
answered at random and `actor_attack_player` logged: the same calls and, every
frame, all of RAM but the stack.
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import levelin                                                       # noqa: E402
import movement                                                      # noqa: E402
import triggers                                                      # noqa: E402
from levelin import O, Mem                                           # noqa: E402

SWING_OP, POP_OP = 0x51, 0x52
OPS = (SWING_OP, POP_OP)
LEVELS = (0, 12, 15, 18)
COLLIDE_QUERY, ATTACK = 0x80033F38, 0x800533E8
OBJECT_SOUND, MODEL_PTR = 0x8004482C, 0x800405E8
OBJECT_TYPES = 0x8018FB3C
CURRENT_OBJECT, CURRENT_TYPE = 0x80198394, 0x80198390
LEVEL_GRID = 0x801D4464
FORCED = 0x801B2574          # objects_forced_present
SCALE = 0x2C
PLAYER_POS = triggers.PLAYER_POS
QUERY = 0x90                 # the creatures and the player
STRENGTH, STAT = 0x1388, 5
SHUT = 0xFC                  # the tile draw_terrain does not draw
NEVER, FREE = 0xFE, 0xFF
THE_END = 0xFFF
REST_STEP = 0x40
SOUND = 0x1E
BIG_STEP_TYPE = 0xDE         # steps in sixteens, not fours; no 0x51 has it
HEAP = 0x80100000            # where the check's machine keeps the models


def s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def s32(v):
    v &= 0xFFFFFFFF
    return v - 0x100000000 if v & 0x80000000 else v


def row_of(raw):
    """What the arms read of a type's 24-byte row."""
    u16 = lambda o: raw[o] | (raw[o + 1] << 8)                       # noqa: E731
    return {"v0": raw[0xC], "v1": raw[0xD], "v16": u16(0xC), "radius": u16(0xE),
            "height": u16(0x10), "att": [raw[0x12], raw[0x13], raw[0x14], raw[0x15]],
            "sound": raw[0x16], "tile": raw[0x17]}


def _hit(d, row, w, p, mask):
    """.L200: the strike."""
    if d["b40"] != 0:
        return
    d["b40"] = 1
    w.attack(mask, d["b39"], row["att"], p)


def _strike(d, row, w, verts):
    for v in verts:
        p = w.vertex(d, v)
        mask = w.query(p, row["radius"], row["height"], QUERY)
        if mask:
            _hit(d, row, w, p, mask)
            return
    d["b40"] = 0


def _rest(d):
    """State 2's start."""
    d["state"], d["b1"], d["ha"] = 2, 1, 0


def _end_rest(d):
    """State 2's clock at its end."""
    d["ha"] = (d["ha"] + REST_STEP) & 0xFFFF
    if d["ha"] >= THE_END:
        d["ha"] = THE_END
        if d["lock"] == 0xFF:
            d["state"], d["b1"] = 3, 1


def _back(d):
    """State 3's clock."""
    d["ha"] = (d["ha"] - REST_STEP) & 0xFFFF
    if d["ha"] & 0x8000:
        d["state"], d["ha"] = 0, 0


def swing(d, row, w):
    """Opcode 0x51's arm on `d`; `w` the world (rect, vertex, query, attack,
    sound, present)."""
    st = d["state"]
    step = d["b3a"] << (4 if d["type"] == BIG_STEP_TYPE else 2)
    verts = (row["v0"], row["v1"])
    tone = SOUND if row["sound"] == 0xFF else row["sound"] + 0x1F0
    if st == 0:
        if d["lock"] == 0:
            _rest(d)
            return
        a = d["b3b"]
        if a == NEVER:
            return
        if a != FREE and not w.rect(d["x"] >> 11, d["z"] >> 11, a, d["b3c"], d["y"]):
            return
        d["state"], d["b1"], d["ha"], d["b40"] = 1, 0, 0, 0
        w.sound(tone)
    elif st == 1:
        if d["b3b"] != FREE and d["ha"] == 0:
            w.present(d, 1, row["tile"])
            w.sound(SOUND)
        if d["lock"] == 0 and d["ha"] >= 0x1000 - step:
            _rest(d)
            return
        d["ha"] = (d["ha"] + step) & 0xFFFF
        if d["ha"] >= THE_END:
            if d["b3b"] != FREE:
                d["ha"], d["state"] = 0, 0
                w.present(d, 0, row["tile"])
                return
            w.sound(tone)
            d["ha"] &= 0xFFF
        if 0x800 <= d["ha"] < step + 0x800 and d["b3b"] == FREE and row["sound"] != 0xFF:
            w.sound(row["sound"] + 0x1F0)
        _strike(d, row, w, verts)
    elif st == 2:
        _end_rest(d)
        _strike(d, row, w, verts)
    elif st == 3:
        _back(d)
        _strike(d, row, w, verts)


def pop(d, row, w):
    """Opcode 0x52's arm on `d`."""
    st = d["state"]
    step = d["b3a"] << 2
    if st == 0:
        if d["lock"] == 0:
            _rest(d)
            return
        a = d["b3b"]
        if a == NEVER:
            return
        if a != FREE and not w.rect(a, d["b3c"], d["b3d"], d["b3e"], d["y"]):
            return
        d["state"], d["b1"], d["ha"], d["b40"] = 1, 0, 0, 0
        w.sound(row["sound"])
    elif st == 1:
        if d["b3d"] != FREE:
            if d["ha"] == 0:
                w.present(d, 1, row["tile"])
                w.sound(row["sound"])
            elif 0x5DC <= d["ha"] < step + 0x5DC:
                w.sound(SOUND)
        if d["lock"] == 0 and d["ha"] >= 0x1000 - step:
            _rest(d)
            return
        d["ha"] = (d["ha"] + step) & 0xFFFF
        if d["ha"] >= THE_END:
            if d["b3d"] != FREE:
                d["ha"], d["state"] = 0, 0
                w.present(d, 0, row["tile"])
                return
            w.sound(row["sound"])
            d["ha"] &= 0xFFF
        _strike(d, row, w, (row["v16"],))
    elif st == 2:
        _end_rest(d)
    elif st == 3:
        _back(d)


def step(d, row, w):
    (swing if d["op"] == SWING_OP else pop)(d, row, w)


def point(md, d, vertex):
    """0x80046760: vertex `vertex` of the model at +1 and the clock, each axis
    by the scale, turned by the angles with the yaw a half turn on, from the
    object's place."""
    import effects
    import weapon
    v = effects.model_vertex(md, d["b1"], d["ha"], vertex)
    v = [s16((v[i] * s16(d["scale"])) >> 12) for i in range(3)]
    r = weapon.vec_rotate((s16(d["ax"]), s16(d["yaw"] + 0x800), s16(d["az"])), v)
    return [s32(r[0] + d["x"]), s32(r[1] + d["y"]), s32(r[2] + d["z"])]


def record(m, k):
    """The arm's fields of slot k out of `m`."""
    r = O(k)
    return {"slot": k, "op": m.rd(r + 4), "type": m.rd(r + 6, 2), "state": m.rd(r + 8, 2),
            "ha": m.rd(r + 0xA, 2), "b0": m.rd(r), "b1": m.rd(r + 1),
            "lock": m.rd(r + 0x38), "b39": m.rd(r + 0x39), "b3a": m.rd(r + 0x3A),
            "b3b": m.rd(r + 0x3B), "b3c": m.rd(r + 0x3C), "b3d": m.rd(r + 0x3D),
            "b3e": m.rd(r + 0x3E), "b40": m.rd(r + 0x40),
            "x": s32(m.rd(r + 0x14, 4)), "y": s32(m.rd(r + 0x18, 4)), "z": s32(m.rd(r + 0x1C, 4)),
            "ax": m.rd(r + 0x24, 2), "yaw": m.rd(r + 0x26, 2), "az": m.rd(r + 0x28, 2),
            "scale": m.rd(r + SCALE, 2)}


def store(m, d):
    """What an arm changes of the record, back into `m`."""
    r = O(d["slot"])
    m.wr(r + 8, d["state"], 2)
    m.wr(r + 0xA, d["ha"], 2)
    m.wr(r + 1, d["b1"])
    m.wr(r + 0x40, d["b40"])
    for i in range(3):
        m.wr(r + SCALE + 2 * i, d["scale"], 2)


class World:
    """The model's side of a frame: what the arm asks, and what it does, kept
    to set beside the game's."""

    def __init__(self, m, models, log):
        self.m, self.models, self.log = m, models, log
        self.answers = []

    def rect(self, cx, cz, w, h, y):
        return triggers.player_in_rect(self.m, cx, cz, w, h, y)

    def vertex(self, d, v):
        return point(self.models[d["type"]], d, v)

    def query(self, p, r, h, flags):
        self.log.append(("query", p[0], p[1], p[2], r, h, flags))
        return self.answers.pop(0) if self.answers else 0

    def attack(self, mask, pct, att, p):
        self.log.append(("attack", mask, 0x80, 0, STRENGTH, STAT, pct, *att, 0, 0, 0, 0, 0,
                         p[0], p[1], p[2]))

    def sound(self, s):
        self.log.append(("sound", s))

    def present(self, d, on, tile):
        """object_set_present (0x80044b40)."""
        cell = LEVEL_GRID + (d["z"] >> 11) * 800 + (d["x"] >> 11) * 10
        cell += 0 if d["b0"] == 1 else 5
        if on or s16(self.m.rd(FORCED, 2)) != 0:
            self.m.wr(cell, SHUT)
            d["scale"] = 0x1000
        else:
            self.m.wr(cell, tile)
            d["scale"] = 0


def records(ram):
    return [k for k in range(levelin.COUNT) if ram[O(k, 4) & levelin.MASK] in OPS]


def load_models(lv, cpu, slots):
    """The models of `slots`, read off the disc and put in the machine's RAM:
    {type: tools/anim.py's Model}, {model: where}. model_ptr gives the game's
    own model_vertex the place."""
    import anim
    import level3d
    models, where = {}, {}
    at = HEAP
    for k in slots:
        t = cpu.rd(O(k, 6), 2)
        if t in models:
            continue
        md = anim.load(level3d.lift_model(t, lv))
        models[t] = md
        where[t + 0x100] = at
        cpu.ram[at & levelin.MASK:(at & levelin.MASK) + len(md.raw)] = md.raw
        at = (at + len(md.raw) + 3) & ~3
    return models, where


def machine(lv, rng):
    """A machine with level `lv` in it and its traps' models: (cpu, models)."""
    import mipsrun
    base = mipsrun.level_cpu(lv)
    cpu = mipsrun.CPU(bytes(base.ram))
    cpu.hooks.update(base.hooks)
    slots = records(cpu.ram)
    models, where = load_models(lv, cpu, slots)

    def model_ptr(c):
        c.wr(c.r[5], 4, where.get(c.r[4] & 0xFFFF, 0))
        return 0
    cpu.hooks[MODEL_PTR] = model_ptr
    return cpu, models


def run(lv, rng, frames, seen):
    """One run of a level: (frames alike, frames, the first difference)."""
    import mipsrun
    cpu, models = machine(lv, rng)
    slots = records(cpu.ram)
    game = []

    def query(c):
        sp = c.r[29]
        mask = rng.choice((0, 0, 0, 0, 0, 0, 0x80, 0x10, 0x90))
        game.append(("query", s32(c.r[4]), s32(c.r[5]), s32(c.r[6]), c.r[7], c.rd(sp + 0x10, 4),
                     c.rd(sp + 0x14, 4)))
        answers.append(mask)
        return mask

    def attack(c):
        sp = c.r[29]
        p = c.rd(sp + 0x3C, 4)
        game.append(("attack", c.r[4], c.r[5], c.r[6], c.r[7])
                    + tuple(c.rd(sp + o, 4) for o in range(0x10, 0x3C, 4))
                    + tuple(s32(c.rd(p + 4 * i, 4)) for i in range(3)))
        return 0

    def noise(c):
        game.append(("sound", c.r[5]))
        return 0
    answers = []
    cpu.hooks[COLLIDE_QUERY] = query
    cpu.hooks[ATTACK] = attack
    cpu.hooks[OBJECT_SOUND] = noise
    if rng.random() < 0.2:
        cpu.wr(FORCED, 2, 1)
    m = Mem(bytes(cpu.ram))
    rects = []
    for k in slots:
        r = O(k)
        if cpu.rd(r + 4, 1) == POP_OP and cpu.rd(r + 0x3B, 1) < NEVER:
            rects.append((cpu.rd(r + 0x3B, 1), cpu.rd(r + 0x3C, 1), s32(cpu.rd(r + 0x18, 4))))
    # a lock turned means animation 1, which only the models with an id have
    signalled = [k for k in slots if cpu.rd(O(k, 4), 1) == POP_OP
                 or models[cpu.rd(O(k, 6), 2)].nanim > 1]
    alike = n = 0
    first = None
    for f in range(frames):
        if rects and rng.random() < 0.04:
            cx, cz, y = rng.choice(rects)
            for a, v in ((PLAYER_POS, (cx << 11) + 0x400), (PLAYER_POS + 4, y),
                         (PLAYER_POS + 8, (cz << 11) + 0x400)):
                cpu.wr(a, 4, v)
                m.wr(a, v, 4)
        for k in signalled:
            if rng.random() < 0.006:             # as object_signal turns it
                r = O(k)
                v = 0xFF if m.rd(r + 0x38) == 0 else 0
                cpu.wr(r + 0x38, 1, v)
                m.wr(r + 0x38, v)
        del game[:]
        del answers[:]
        log = []
        w = World(m, models, log)
        for k in slots:
            mipsrun.object_arm(cpu, k)
            m.wr(CURRENT_OBJECT, O(k), 4)
            d = record(m, k)
            m.wr(CURRENT_TYPE, OBJECT_TYPES + 24 * d["type"], 4)
            w.answers = list(answers)
            del answers[:]
            step(d, row_of(bytes(m.ram[(OBJECT_TYPES + 24 * d["type"]) & levelin.MASK:]
                                 [:24])), w)
            store(m, d)
            seen.add((d["op"], d["state"]))
        n += 1
        why = None
        if log != game:
            why = next((f"calls: model {a}, game {b}" for a, b in zip(log, game) if a != b),
                       f"calls: model {len(log)}, game {len(game)}")
        else:
            a, b = m.ram, cpu.ram
            for lo, hi in ((0, levelin.STACK_LO), (levelin.STACK_HI, len(a))):
                if a[lo:hi] != b[lo:hi]:
                    for i in range(lo, hi):
                        if a[i] != b[i]:
                            why = (f"{0x80000000 | i:#x}: model {a[i]:#x}, game {b[i]:#x} "
                                   f"({levelin._where(0x80000000 | i)})")
                            break
                    break
        if why is None:
            alike += 1
        elif first is None:
            first = f"level {lv} frame {f}: {why}"
    return alike, n, first


def check(out=sys.stdout, runs=3, frames=300, seed=111):
    rng = random.Random(seed)
    alike = n = 0
    first = None
    seen = set()
    for lv in LEVELS:
        for _ in range(runs):
            a, f, why = run(lv, rng, frames, seen)
            alike += a
            n += f
            first = first or why
    print(f"opcodes 0x51 and 0x52, the game's own arms, object_vertex_point and model_vertex: {alike} of "
          f"{n} frames over the 94 traps of four levels agree -- the calls in order and all of "
          f"RAM but the stack; {len(seen)} states seen", file=out)
    if first:
        print(f"  first difference: {first}", file=out)
    return alike == n


class Scripted(World):
    """A world for the self-test: every question logged with its answer, so
    godot/selftest.gd can put the same to godot/traps.gd and ask the same in
    the same order."""

    def __init__(self, rng, log):
        self.rng, self.log = rng, log

    def rect(self, cx, cz, w, h, y):
        ans = int(self.rng.random() < 0.15)
        self.log.append(["rect", cx, cz, w, h, y, ans])
        return ans

    def vertex(self, d, v):
        p = [self.rng.randrange(0x28000), -self.rng.randrange(0x4000),
             self.rng.randrange(0x28000)]
        self.log.append(["vertex", v, *p])
        return p

    def query(self, p, r, h, flags):
        ans = self.rng.choice((0, 0, 0, 0, 0x80, 0x10, 0x90))
        self.log.append(["query", p[0], p[1], p[2], r, h, flags, ans])
        return ans

    def attack(self, mask, pct, att, p):
        self.log.append(["attack", mask, pct, *att, *p])

    def sound(self, s):
        self.log.append(["sound", s])

    def present(self, d, on, tile):
        self.log.append(["present", on, tile])
        d["scale"] = 0x1000 if on else 0


def export(out_dir, frames=80, seed=113):
    """trapcheck.json: for godot/selftest.gd, runs of the models' frames -- the
    object, its row, each frame's lock and the questions and answers in order
    -- and vertex points of level 0's type 219 as `point` answers them."""
    import json
    import objload
    import level3d
    rng = random.Random(seed)
    runs = []
    for lv in (12, 15, 18):
        ld = objload.Load(lv)
        slots = [k for k, o in sorted(ld.recs.items()) if o["op"] in OPS]
        for k in rng.sample(slots, min(12, len(slots))):
            o = ld.recs[k]
            t = o["tail"]
            d = {"slot": k, "op": o["op"], "type": o["type"], "state": 0, "ha": 0, "b0": o["b0"],
                 "b1": o["b1"], "lock": t[0], "b39": t[1], "b3a": t[2], "b3b": t[3], "b3c": t[4],
                 "b3d": t[5], "b3e": t[6], "b40": t[8], "x": o["x"], "y": o["y"], "z": o["z"],
                 "ax": 0, "yaw": o["angles"][1] & 0xFFFF, "az": 0, "scale": o["scale"][0]}
            row = row_of(bytes(ld.rows[o["type"]]))
            run_ = {"d": dict(d), "row": row, "frames": []}
            for _ in range(frames):
                if rng.random() < 0.03:
                    d["lock"] = 0xFF if d["lock"] == 0 else 0
                log = []
                step(d, row, Scripted(rng, log))
                run_["frames"].append({"lock": d["lock"], "calls": log,
                                       "out": [d["state"], d["ha"], d["b1"], d["b40"],
                                               d["scale"]]})
            runs.append(run_)
    import anim
    md = anim.load(level3d.lift_model(219, 0))
    pts = []
    for _ in range(40):
        d = {"b1": 0, "ha": rng.randrange(0x1000), "scale": rng.choice((0x1000, 0x800, 0x1FE0)),
             "ax": rng.choice((0, 0, rng.randrange(0x1000))), "yaw": rng.randrange(0x10000),
             "az": rng.choice((0, 0, rng.randrange(0x1000))), "x": rng.randrange(0x28000),
             "y": -rng.randrange(0x4000), "z": rng.randrange(0x28000)}
        v = rng.randrange(md.nvert)
        pts.append({"d": d, "vertex": v, "p": point(md, d, v)})
    path = os.path.join(out_dir, "trapcheck.json")
    with open(path, "w") as fh:
        json.dump({"runs": runs, "points": pts, "model": level3d.lift_model(219, 0)}, fh,
                  separators=(",", ":"))
    return path


def show(out=sys.stdout):
    import objload
    for lv in LEVELS:
        ld = objload.Load(lv)
        for k, o in sorted(ld.recs.items()):
            if o["op"] not in OPS:
                continue
            t = o["tail"]
            by = (f"free" if t[3] == FREE else "never" if t[3] == NEVER else f"{t[3]} by {t[4]}") \
                if o["op"] == SWING_OP else \
                ("free" if t[3] == FREE else "never" if t[3] == NEVER
                 else f"({t[3]}, {t[4]}) {t[5]} by {t[6]}")
            print(f"level {lv:2d} slot {k:3d} {o['op']:#x} ({o['x'] >> 11:2d}, {o['z'] >> 11:2d}) "
                  f"type {o['type']} step {t[2]} {by} id "
                  f"{t[5] if o['op'] == SWING_OP else t[7]:#x}", file=out)


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
