#!/usr/bin/env python3
"""The levers: opcode 0x53, and what they move -- 0x56, the trees, and 0x58, the slabs.

    python3 tools/levers.py            every lever and what its signal reaches
    python3 tools/levers.py --check    the models against the game's own arms
    python3 tools/levers.py --export D levercheck.json for the self-test

**Opcode `0x53`** (`object_interpreter+0x1c6c`, 0x80048c7c): 24 objects on
levels 5, 10, 12, 13, 15 and 18. The record's `+0x38` says which way it stands
(2 and 3, turned over each use; 0 and 1 go once), `+0x39` the id it hands
`object_signal`, the u16 at `+0x3a` its clock's step (0xffff: 0x100), `+0x3c`
1 to signal as it starts and anything else as it ends, `+0x3d` the thing that
works it (0xff: USE, while `+0x3e` is not 0). The loader leaves state 9, whose
one frame stands a lever of `+0x38` 3 at the clock's end -- which is how one
pulled on an earlier visit comes back pulled: level_state_write keeps a
`+0x38` of 2 or more.

```
state 1   the sound (unless the type's +0xf is 0xf); +0x3c 1: the signal.
          +0x38 2: 3, state 2.  3: 2, state 3.  0, 1: state 2
state 2   the clock +0xa by the step; a +0xf of 0xf sounds as it passes 0x400;
          from 0x1000, 0xfff and "the end"
state 3   the clock back; a +0xf of 0xf sounds as it passes 0xc00; at 0 or
          under, 0 and "the end"
the end   +0x3c not 1: the signal.  +0x38 1: the sound, state 4.  0: state
          0x63.  2, 3: state 0
state 4   the clock back; at 0 or under, state 0x63
state 9   +0x38 3: the clock 0xfff.  State 0
```

The type's `+0xf` is the sound, with 0x1f0 on on level 13.

**Opcode `0x56`** (0x80049fcc): level 5's seventeen trees of Varde's wood. Each
holds its scale (`+0x2c`, `+0x2e`, `+0x30`) and with it the circle
object_collide stops the player at: the type's row has `+3` bit 0x10, so the
radius 0x700 is taken by `+0x38` / 128. `object_signal` of its `+0x3a` turns
`+0x39` between 0 and 0xff, so a lever swaps the two of a pair -- one grows
where the other shrinks, and the way through the wood moves.

```
state 0   +0x39 0: state 2, the scale 0, +0x38 0, +0 0 -- gone at once
          else: the scale 0x1000, +0x38 0x80, +0 2, state 1
state 1   +0x39 0: state 2
state 2   the scale down 0x80; at 0 or under, 0, +0x38 0, +0 0, and with
          +0x39 0xff state 3
state 3   +0 2, the scale up 0x100; from 0x1000, 0x1000, +0x38 0x80, state 0
```

**Opcode `0x58`** (0x8004ab40): level 13's four slabs. `object_signal` of its
`+0x39` puts it in state 1 and turns `+0x38` between 0 and 1. State 1: `+0x38`
0 state 2, 1 state 3, either with sound 0x14, and `stamp_rect` of the template
one width along (`+0x3c` + `+0x3e`, `+0x3d`, to `+0x3a`, `+0x3b`, `+0x3e` by
`+0x3f`, turned by the yaw, mask 0x2d) -- whichever it is. State 2: the clock
down 0x40; at 0 or under 0, state 0x63 and the template at `+0x3c` laid. State
3: the clock up 0x40; from 0x1000, 0xfff and state 0x63.

**How it is held to the game.** Every lever, tree and slab of a level, its
own arm a frame in slot order over `mipsrun.level_cpu` from the loader's
states, the levers worked at random, `+0x38`, `+0x3c` and the step at random;
object_sound and stamp_rect stood in for and logged, `object_signal` the
game's own -- the same calls and, every frame, all of RAM but the stack.
"""
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import levelin                                                       # noqa: E402
import useitem                                                       # noqa: E402
from levelin import O, MASK, Mem                                     # noqa: E402

LEVER_OP, TREE_OP, SLAB_OP = 0x53, 0x56, 0x58
OPS = (LEVER_OP, TREE_OP, SLAB_OP)
LEVELS = (5, 10, 12, 13, 15, 18)
OBJECT_TYPES = 0x8018FB3C
CURRENT_LEVEL = 0x8018FAD8
CURRENT_OBJECT, CURRENT_TYPE = 0x80198394, 0x80198390
STAMP_RECT, OBJECT_SOUND = 0x800445B8, 0x8004482C
SCALE = 0x2C                 # +0x2c, +0x2e, +0x30
ONE = 0x1000
DONE = 0x63
PLAIN = 0xF                  # a type's +0xf that sounds in passing
MASK_STAMP = 0x2D
SLAB_SOUND = 0x14
LEVEL_13 = 0xD
LEVEL_13_SOUNDS = 0x1F0


def s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def signal(m, sig):
    """object_signal over the records' bytes: useitem.object_signal's."""
    objs = []
    for k in range(levelin.COUNT):
        r = O(k)
        objs.append({"op": m.rd(r + 4), "state": m.rd(r + 8, 2), "b38": m.rd(r + 0x38),
                     "b39": m.rd(r + 0x39), "h3a": m.rd(r + 0x3A, 2), "b3d": m.rd(r + 0x3D),
                     "b3f": m.rd(r + 0x3F)})
    useitem.object_signal({"objects": objs}, sig)
    for k, o in enumerate(objs):
        r = O(k)
        if o["state"] != m.rd(r + 8, 2):
            m.wr(r + 8, o["state"], 2)
        for off, key in ((0x38, "b38"), (0x39, "b39"), (0x3F, "b3f")):
            if o[key] != m.rd(r + off):
                m.wr(r + off, o[key])


def _sound(m, r, s):
    m.calls.append(("sound", r, s))


def _lever_end(m, r, tone):
    """.L123: the end of a swing."""
    if m.rd(r + 0x3C) != 1:
        signal(m, m.rd(r + 0x39))
    b = m.rd(r + 0x38)
    if b == 1:
        _sound(m, r, tone)
        m.wr(r + 8, 4, 2)
    elif b == 0:
        m.wr(r + 8, DONE, 2)
    elif b < 4:
        m.wr(r + 8, 0, 2)


def lever(m, k):
    """Opcode 0x53's arm for the record in slot k."""
    r = O(k)
    row = OBJECT_TYPES + 24 * m.rd(r + 6, 2)
    tone = m.rd(row + 0xF)
    if m.rd(CURRENT_LEVEL) == LEVEL_13:
        tone += LEVEL_13_SOUNDS
    step = m.rd(r + 0x3A, 2)
    if step == 0xFFFF:
        step = 0x100
    st = m.rd(r + 8, 2)
    if st == 1:
        if tone != PLAIN:
            _sound(m, r, tone)
        if m.rd(r + 0x3C) == 1:
            signal(m, m.rd(r + 0x39))
        b = m.rd(r + 0x38)
        if b == 2:
            m.wr(r + 8, 2, 2)
            m.wr(r + 0x38, 3)
        elif b == 3:
            m.wr(r + 8, 3, 2)
            m.wr(r + 0x38, 2)
        elif b < 2:
            m.wr(r + 8, 2, 2)
    elif st == 2:
        c = (m.rd(r + 0xA, 2) + step) & 0xFFFF
        m.wr(r + 0xA, c, 2)
        if tone == PLAIN and 0x400 < c <= step + 0x400:
            _sound(m, r, PLAIN)
        if c >= ONE:
            m.wr(r + 0xA, 0xFFF, 2)
            _lever_end(m, r, tone)
    elif st == 3:
        c = m.rd(r + 0xA, 2)
        if tone == PLAIN and 0xC00 < c <= step + 0xC00:
            _sound(m, r, PLAIN)
        c = (c - step) & 0xFFFF
        m.wr(r + 0xA, c, 2)
        if s16(c) <= 0:
            m.wr(r + 0xA, 0, 2)
            _lever_end(m, r, tone)
    elif st == 4:
        c = (m.rd(r + 0xA, 2) - step) & 0xFFFF
        m.wr(r + 0xA, c, 2)
        if s16(c) <= 0:
            m.wr(r + 8, DONE, 2)
    elif st == 9:
        if m.rd(r + 0x38) == 3:
            m.wr(r + 0xA, 0xFFF, 2)
        m.wr(r + 8, 0, 2)


def _scale(m, r, v):
    for i in range(3):
        m.wr(r + SCALE + 2 * i, v, 2)


def tree(m, k):
    """Opcode 0x56's arm for the record in slot k."""
    r = O(k)
    st = m.rd(r + 8, 2)
    if st == 0:
        if m.rd(r + 0x39) == 0:
            m.wr(r + 8, 2, 2)
            _scale(m, r, 0)
            m.wr(r + 0x38, 0)
            m.wr(r, 0)
        else:
            _scale(m, r, ONE)
            m.wr(r + 0x38, 0x80)
            m.wr(r + 8, 1, 2)
            m.wr(r, 2)
    elif st == 1:
        if m.rd(r + 0x39) == 0:
            m.wr(r + 8, 2, 2)
    elif st == 2:
        for i in range(3):
            m.wr(r + SCALE + 2 * i, m.rd(r + SCALE + 2 * i, 2) - 0x80, 2)
        if s16(m.rd(r + SCALE, 2)) <= 0:
            _scale(m, r, 0)
            m.wr(r + 0x38, 0)
            m.wr(r, 0)
            if m.rd(r + 0x39) == 0xFF:
                m.wr(r + 8, 3, 2)
    elif st == 3:
        m.wr(r, 2)
        for i in range(3):
            m.wr(r + SCALE + 2 * i, m.rd(r + SCALE + 2 * i, 2) + 0x100, 2)
        if s16(m.rd(r + SCALE, 2)) >= ONE:
            _scale(m, r, ONE)
            m.wr(r + 8, 0, 2)
            m.wr(r + 0x38, 0x80)


def _slab_stamp(m, r, sx):
    m.calls.append(("stamp", m.rd(r), sx, m.rd(r + 0x3D), m.rd(r + 0x3A), m.rd(r + 0x3B),
                    m.rd(r + 0x3E), m.rd(r + 0x3F), s16(m.rd(r + 0x26, 2)) & 0xFFFFFFFF,
                    MASK_STAMP))


def slab(m, k):
    """Opcode 0x58's arm for the record in slot k."""
    r = O(k)
    st = m.rd(r + 8, 2)
    if st == 1:
        b = m.rd(r + 0x38)
        if b == 0:
            m.wr(r + 8, 2, 2)
            _sound(m, r, SLAB_SOUND)
        elif b == 1:
            m.wr(r + 8, 3, 2)
            _sound(m, r, SLAB_SOUND)
        _slab_stamp(m, r, m.rd(r + 0x3C) + m.rd(r + 0x3E))
    elif st == 2:
        c = (m.rd(r + 0xA, 2) - 0x40) & 0xFFFF
        m.wr(r + 0xA, c, 2)
        if s16(c) <= 0:
            m.wr(r + 8, DONE, 2)
            m.wr(r + 0xA, 0, 2)
            _slab_stamp(m, r, m.rd(r + 0x3C))
    elif st == 3:
        c = (m.rd(r + 0xA, 2) + 0x40) & 0xFFFF
        m.wr(r + 0xA, c, 2)
        if c >= ONE:
            m.wr(r + 0xA, 0xFFF, 2)
            m.wr(r + 8, DONE, 2)


ARMS = {LEVER_OP: lever, TREE_OP: tree, SLAB_OP: slab}


def busy(op, state, b39, scale):
    """Would this record's arm change anything this frame? A tree gone stays
    in state 2 for good, writing its noughts every frame; the check holds a
    frame this calls idle to change nothing."""
    if op == LEVER_OP:
        return state in (1, 2, 3, 4, 9)
    if op == TREE_OP:
        if state == 2:
            return scale != 0 or b39 == 0xFF
        return state in (0, 3) or (state == 1 and b39 == 0)
    return state in (1, 2, 3)


def arm(m, k):
    """The arm of the record in slot k, by its opcode."""
    ARMS[m.rd(O(k, 4))](m, k)


def records(ram):
    """The slots of these three opcodes in `ram`, as the game's own
    load_object_placement leaves them."""
    return [k for k in range(levelin.COUNT) if ram[O(k, 4) & MASK] in OPS]


def _stack(c, n):
    return tuple(c.rd(c.r[29] + 0x10 + 4 * i, 4) for i in range(n))


def machine(lv, base, rng):
    """A machine of `base`'s RAM with its levers' numbers drawn at random."""
    import mipsrun
    cpu = mipsrun.CPU(bytes(base.ram))
    cpu.hooks.update(base.hooks)
    cpu.wr(CURRENT_LEVEL, 1, lv)
    for k in records(cpu.ram):
        r = O(k)
        if cpu.rd(r + 4, 1) != LEVER_OP:
            continue
        if rng.random() < 0.5:
            cpu.wr(r + 0x38, 1, rng.choice((0, 1, 2, 3, 3, 2, 5)))
        if rng.random() < 0.3:
            cpu.wr(r + 0x3C, 1, rng.choice((0, 1, 0xFF)))
        if rng.random() < 0.3:
            cpu.wr(r + 0x3A, 2, rng.choice((0x20, 0x80, 0x180, 0xFFFF, 0x7F, 0x1000)))
    return cpu


def idle_of(m, k):
    """busy() as the port asks it, of the record's bytes."""
    r = O(k)
    return not busy(m.rd(r + 4), m.rd(r + 8, 2), m.rd(r + 0x39), m.rd(r + SCALE, 2))


def run(lv, base, rng, frames, seen):
    """One run of a level: (frames alike, frames, the first difference)."""
    import mipsrun
    cpu = machine(lv, base, rng)
    calls = []
    cpu.hooks[STAMP_RECT] = lambda c: calls.append(("stamp",) + tuple(c.r[4:8]) + _stack(c, 5))
    cpu.hooks[OBJECT_SOUND] = lambda c: calls.append(("sound", c.r[4], c.r[5]))
    slots = records(cpu.ram)
    levers = [k for k in slots if cpu.rd(O(k, 4), 1) == LEVER_OP]
    m = Mem(bytes(cpu.ram))
    alike = n = 0
    first = None
    for f in range(frames):
        for k in levers:
            if rng.random() < 0.03 and cpu.rd(O(k, 8), 2) == 0:
                cpu.wr(O(k, 8), 2, 1)
                m.wr(O(k, 8), 1, 2)
        del calls[:]
        del m.calls[:]
        for k in slots:
            mipsrun.object_arm(cpu, k)
            row = OBJECT_TYPES + 24 * m.rd(O(k, 6), 2)
            m.wr(CURRENT_OBJECT, O(k), 4)
            m.wr(CURRENT_TYPE, row, 4)
            idle = idle_of(m, k)
            was, said = bytes(m.ram), len(m.calls)
            arm(m, k)
            if idle:
                seen.add("idle")
                if was != bytes(m.ram) or len(m.calls) != said:
                    m.calls.append(("not idle", k))
            seen.add((m.rd(O(k, 4)), m.rd(O(k, 8), 2)))
        n += 1
        why = None
        if m.calls != calls:
            why = f"calls: model {m.calls}, game {calls}"
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


def check(out=sys.stdout, runs=4, frames=300, seed=101):
    import mipsrun
    rng = random.Random(seed)
    alike = n = 0
    first = None
    seen = set()
    count = 0
    for lv in LEVELS:
        base = mipsrun.level_cpu(lv)
        count += len(records(base.ram))
        for _ in range(runs):
            a, f, why = run(lv, base, rng, frames, seen)
            alike += a
            n += f
            first = first or why
    print(f"opcodes 0x53, 0x56 and 0x58, the game's own arms and object_signal: {alike} of {n} "
          f"frames over the {count} levers, trees and slabs of six levels agree -- the calls in "
          f"order and all of RAM but the stack; {len(seen - {'idle'})} states seen, and every arm "
          f"busy() calls idle changes nothing", file=out)
    if first:
        print(f"  first difference: {first}", file=out)
    return alike == n


def export(out_dir, per_level=30, seed=103):
    """levercheck.json: arms of the models -- the bytes read, the bytes
    written, the calls -- which godot/selftest.gd holds godot/levers.gd to."""
    import json
    import mipsrun
    rng = random.Random(seed)
    rows = []
    for lv in LEVELS:
        base = mipsrun.level_cpu(lv)
        cpu = machine(lv, base, rng)
        m = Mem(bytes(cpu.ram))
        slots = records(m.ram)
        for k in slots:
            if m.rd(O(k, 4)) == LEVER_OP and rng.random() < 0.5:
                m.wr(O(k, 8), 1, 2)
        for f in range(per_level):
            for k in slots:
                m.read.clear()
                m.written.clear()
                del m.calls[:]
                if m.rd(O(k, 4)) == LEVER_OP and m.rd(O(k, 8), 2) == 0 and rng.random() < 0.1:
                    m.wr(O(k, 8), 1, 2)
                    m.read.clear()
                    m.written.clear()
                was = bytes(m.ram)
                arm(m, k)
                if m.written or m.calls:
                    rows.append({"slot": k, "read": [[a, v] for a, v in sorted(m.read.items())],
                                 "wrote": [[a, m.ram[a & MASK]] for a in sorted(m.written)],
                                 "calls": [list(c) for c in m.calls],
                                 "moved": was != bytes(m.ram) or bool(m.calls)})
    path = os.path.join(out_dir, "levercheck.json")
    with open(path, "w") as fh:
        json.dump({"cases": rows[:: max(1, len(rows) // 400)]}, fh, separators=(",", ":"))
    return path


def show(out=sys.stdout):
    import objload
    for lv in LEVELS:
        ld = objload.Load(lv)
        for k, o in sorted(ld.recs.items()):
            if o["op"] != LEVER_OP:
                continue
            t = o["tail"]
            sig = t[1]
            hit = []
            for j, q in sorted(ld.recs.items()):
                u, op = q["tail"], q["op"]
                if (op <= 5 or op == 0x1B) and (u[0] == sig or (0x96 <= sig <= 0xC6
                                                                and u[0] & 0xFE == sig)):
                    hit.append(f"door {j}")
                elif op == 0x51 and u[5] == sig:
                    hit.append(f"trap {j}")
                elif op in (0x52, 0x55, 0x5A) and u[7] == sig:
                    hit.append(f"{op:#x} {j}")
                elif op == TREE_OP and u[2] == sig:
                    hit.append(f"tree {j}")
                elif op == SLAB_OP and u[1] == sig:
                    hit.append(f"slab {j}")
            print(f"level {lv:2d} slot {k:3d} ({o['x'] >> 11:2d}, {o['z'] >> 11:2d}) type "
                  f"{o['type']} +0x38 {t[0]} id {sig:#x} by "
                  f"{'USE' if t[5] == 0xFF else f'thing {t[5]:#x}'}: {', '.join(hit)}", file=out)


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
