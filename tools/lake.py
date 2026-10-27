#!/usr/bin/env python3
"""Level 2's lake: opcode 0x5f's stamp switches, and the switch over them (opcode 0xa6, the level's entry 9).

    python3 tools/lake.py            the seventeen and the switch's six patterns
    python3 tools/lake.py --check    the model against the game's own arms and
                                     level 2's own entry 9
    python3 tools/lake.py --export D lakecheck.json and lake.json for the port

**Opcode `0x5f`** (`object_interpreter+0x20a8`, `0x800490b8`) is a pair of
templates and a place: in state 1 it lays, by `+0x3f`, a stamp_rect of
`+0x3d` by `+0x3e` cells from the template at (`+0x3b + +0x3d`, `+0x3c`) to
(`+0x39`, `+0x3a`), turned by the record's yaw (`+0x26`), mask `0x2d` -- the
tile, the rotation, the shape and the fence -- and goes to state 2 (`+0x3f`
0), 3 (`+0x3f` 1) or stays (anything else); in state 2 it lays the template
at `+0x3b` itself and ends (state `0x63`); in state 3 it ends. So `+0x3f` 0
leaves the first template laid, 1 the second. Twenty in the game: level 2's
objects 100..116 (type `0x122`, locks `0xc8..0xd8`) and level 17's 5, 80 and
81. What starts one is `object_signal` (its lock: state 1, `+0x3f` turned
over) or the level's own code.

**Level 2's switch** is object 82 (type `0x12e`, opcode `0xa6`, cell (5,
40)), whose arm is the level's own **entry 9** (`level_hooks + 0x24`, which
object_interpreter calls for the 191 opcodes that have no arm of their
own): state 1 -- object_sound with its type row's `+0xf`, `+1` the lock less
1 (5 for lock 0), state 2, `+0xa` 0; state 2 -- `+0xa` up by `0x80` a frame to
`0xfff`, then state 3; state 3 -- the position `(+1 + 1) mod 6`, and for each
of the seventeen a word of the overlay's (`0x801e8f80`): its bit for the
position set, a stone whose lock is still its own (`0xc8 + i`) and `+0x3f`
not 0 gets `+0x3f` 0 and state 1; clear, a stone whose `+0x3f` is not 1 gets
1 and state 1; then `+0x40` `0xff` and state 0; state 4 -- `+1` as in state
1 and state 3 at once, no sound. Its lock is 0 as placed (position 0) and 3
once the caretaker is dead (entry 19, or entry 5 by flag `0x15`: state 1).
The level's entry 1 lays every stone's second template while the aquarian
boots are off, and state 4 -- the pattern again -- when they go on
(tools/ticks.py).

**How it is held to the game.** `check()` runs GAME.EXE's own arm with
`tools/mipsrun.py` (`object_arm`) for each of the twenty, from every state
with `+0x3f`, the templates' bytes and the yaw at random, and for object 82
-- object_interpreter's escape into level 2's entry 9 out of its overlay --
from every state, with its lock, `+1`, `+0xa`, `+0x40` and the seventeen's
locks, `+0x3f` and states at random; stamp_rect and object_sound logged: the
model must make the same calls and leave the same RAM, all of it but the
stack.
"""
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import levelin                                                       # noqa: E402
import useitem                                                       # noqa: E402
from levelin import O, MASK, Mem                                     # noqa: E402

OP_STAMP, OP_SWITCH = 0x5F, 0xA6
STAMP_RECT, OBJECT_SOUND = 0x800445B8, 0x8004482C
OBJECT_TYPES = 0x8018FB3C          # object_type_table: 24 bytes a type
CURRENT_OBJECT, CURRENT_TYPE = 0x80198394, 0x80198390
MASK_STAMP = 0x2D                  # tile, rotation, shape, fence
SWITCH, STONES, COUNT = 82, 100, 17
PATTERNS = 0x801E8F80              # level 2's overlay: a word a stone, a bit a position
POSITIONS = 6
DONE = 0x63


def s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def _stamp(m, r, sx):
    m.calls.append(("stamp", 2, sx, m.rd(r + 0x3C), m.rd(r + 0x39), m.rd(r + 0x3A),
                    m.rd(r + 0x3D), m.rd(r + 0x3E), s16(m.rd(r + 0x26, 2)) & 0xFFFFFFFF,
                    MASK_STAMP))


def arm5f(m, k):
    """Opcode 0x5f's arm (0x800490b8) for record `k` over the RAM `m`."""
    r = O(k)
    st = m.rd(r + 8, 2)
    if st == 1:
        b = m.rd(r + 0x3F)
        if b == 0:
            m.wr(r + 8, 2, 2)
        elif b == 1:
            m.wr(r + 8, 3, 2)
        _stamp(m, r, m.rd(r + 0x3B) + m.rd(r + 0x3D))
    elif st == 2:
        m.wr(r + 8, DONE, 2)
        _stamp(m, r, m.rd(r + 0x3B))
    elif st == 3:
        m.wr(r + 8, DONE, 2)


def _position(m, r):
    """+1 from the lock: the lock less 1, or 5 for 0."""
    lock = m.rd(r + 0x38)
    m.wr(r + 1, (lock - 1) & 0xFF if lock else 5)


def entry9(lv, m, k):
    """Level `lv`'s entry 9 with record `k` the current object."""
    r = O(k)
    if lv != 2 or m.rd(r + 4) != OP_SWITCH:
        return
    st = m.rd(r + 8, 2)
    if st == 1:
        row = OBJECT_TYPES + 24 * m.rd(r + 6, 2)
        m.calls.append(("sound", r, m.rd(row + 0xF)))
        _position(m, r)
        m.wr(r + 8, 2, 2)
        m.wr(r + 0xA, 0, 2)
    elif st == 2:
        v = (m.rd(r + 0xA, 2) + 0x80) & 0xFFFF
        m.wr(r + 0xA, v, 2)
        if v >= 0x1000:
            m.wr(r + 0xA, 0xFFF, 2)
            m.wr(r + 8, 3, 2)
    elif st == 3:
        bit = 1 << ((m.rd(r + 1) + 1) % POSITIONS)
        for i in range(COUNT):
            s = O(STONES + i)
            if m.rd(PATTERNS + 4 * i, 4) & bit:
                if m.rd(s + 0x38) == 0xC8 + i and m.rd(s + 0x3F) != 0:
                    m.wr(s + 0x3F, 0)
                    m.wr(s + 8, 1, 2)
            elif m.rd(s + 0x3F) != 1:
                m.wr(s + 0x3F, 1)
                m.wr(s + 8, 1, 2)
        m.wr(r + 0x40, 0xFF)
        m.wr(r + 8, 0, 2)
    elif st == 4:
        _position(m, r)
        m.wr(r + 8, 3, 2)


def arm(lv, m, k):
    """Record `k`'s turn: object_interpreter's loop publishing it
    (current_object, current_object_type), then opcode 0x5f's arm or the
    escape into entry 9."""
    m.wr(CURRENT_OBJECT, O(k), 4)
    m.wr(CURRENT_TYPE, OBJECT_TYPES + 24 * m.rd(O(k, 6), 2), 4)
    if m.rd(O(k, 4)) == OP_STAMP:
        arm5f(m, k)
    else:
        entry9(lv, m, k)


def patterns(lv=2):
    """The seventeen words at 0x801e8f80 of level 2's overlay."""
    import overlay
    from tarc import TArc
    raw = TArc(overlay.FDAT).raw(lv * 3 + 2)
    return [struct.unpack_from("<I", raw, PATTERNS - overlay.BASE + 4 * i)[0] for i in range(COUNT)]


# --- against the game's own ---------------------------------------------------

def _stack(c, n):
    return tuple(c.rd(c.r[29] + 0x10 + 4 * i, 4) for i in range(n))


def game_run(cpu, k):
    """GAME.EXE's own arm for record `k` (and level 2's entry 9 out of its
    overlay): [the calls it made that the model logs, in order]."""
    import mipsrun
    calls = []
    cpu.hooks = dict(cpu.hooks)
    cpu.hooks[STAMP_RECT] = lambda c: calls.append(("stamp",) + tuple(c.r[4:8]) + _stack(c, 5))
    cpu.hooks[OBJECT_SOUND] = lambda c: calls.append(("sound", c.r[4], c.r[5]))
    mipsrun.object_arm(cpu, k)
    return calls


def records(ram):
    """The opcode-0x5f and 0xa6 records in `ram` -- as the game's own
    load_object_placement leaves them, which is where object 82 gets its
    0xa6 (tools/objload.py's reading has 0xff: the level's own hook)."""
    return [k for k in range(levelin.COUNT) if ram[O(k, 4) & MASK] in (OP_STAMP, OP_SWITCH)]


def cases(lv, n, rng, snap="a1"):
    """`n` runs of each record of level `lv`: [(the machine, the slot)]."""
    import mipsrun
    base = mipsrun.level_cpu(lv, snap)
    ram0 = bytes(base.ram)
    ks = records(ram0)
    put = useitem._put
    out = []
    for k in ks:
        for _ in range(n * 8 if k == SWITCH else n):     # the switch's five states, more ways
            cpu = mipsrun.CPU(ram0)
            cpu.hooks.update(base.hooks)
            r = O(k)
            put(cpu, r + 8, 2, rng.choice((0, 1, 1, 2, 3, 4, DONE)))
            put(cpu, r + 0x3F, 1, rng.choice((0, 1, 0xFF, 2)))
            put(cpu, r + 0x26, 2, rng.choice((0, 0x400, 0x800, 0xC00, rng.randrange(0x10000))))
            if rng.random() < 0.3:
                for off in (0x39, 0x3A, 0x3B, 0x3C, 0x3D, 0x3E):
                    put(cpu, r + off, 1, rng.randrange(0x100))
            if k == SWITCH:
                put(cpu, r + 0x38, 1, rng.choice((0, 3, 1, 6, rng.randrange(0x100))))
                put(cpu, r + 1, 1, rng.randrange(0x100))
                put(cpu, r + 0xA, 2, rng.choice((0, 0xF00, 0xF80, 0xFFF, rng.randrange(0x10000))))
                put(cpu, r + 0x40, 1, rng.choice((0, 1, 0xFF)))
                for i in range(COUNT):
                    s = O(STONES + i)
                    put(cpu, s + 0x38, 1, rng.choice((0xC8 + i, 0xC8 + i, 0xFF, 0xC8)))
                    put(cpu, s + 0x3F, 1, rng.choice((0, 1, 1, 0xFF)))
                    put(cpu, s + 8, 2, rng.choice((0, 1, 2, 3, DONE)))
            out.append((cpu, k))
    return out


def compare(cpu, lv, k):
    """One run both ways: (what it did, None) when they agree, else what differs."""
    m = Mem(bytes(cpu.ram))
    arm(lv, m, k)
    got = game_run(cpu, k)
    what = (lv, k, tuple(c[0] for c in m.calls),
            tuple(sorted((a, m.ram[a & MASK]) for a in m.written)))
    if m.calls != got:
        return what, f"calls: model {m.calls}, game {got}"
    a, b = m.ram, cpu.ram
    for lo, hi in ((0, levelin.STACK_LO), (levelin.STACK_HI, len(a))):
        if a[lo:hi] != b[lo:hi]:
            for i in range(lo, hi):
                if a[i] != b[i]:
                    return what, f"{0x80000000 | i:#x}: model {a[i]:#x}, game {b[i]:#x}" \
                        f" ({levelin._where(0x80000000 | i)})"
    return what, None


def check(out=sys.stdout, per_record=24, seed=79, verbose=False):
    """The model against the game's own arms, and level 2's entry 9."""
    rng = random.Random(seed)
    ok = n = stamps = sounds = 0
    told = False
    for lv in (2, 17):
        for cpu, k in cases(lv, per_record, rng):
            n += 1
            what, why = compare(cpu, lv, k)
            if why is None:
                ok += 1
                stamps += what[2].count("stamp")
                sounds += what[2].count("sound")
            elif not told or verbose:
                told = True
                print(f"  level {lv}, slot {k}: {why}", file=out)
    print(f"  {stamps} stamps laid, the switch's sound {sounds} times", file=out)
    print(f"opcode 0x5f and level 2's entry 9, against the game's own: {ok} of {n} runs agree "
          f"-- the calls and all of RAM but the stack", file=out)
    return ok == n


def export(out_dir, per_record=6, seed=83):
    """lakecheck.json: runs of the model -- the bytes it read, the calls and
    the bytes it wrote -- which godot/selftest.gd holds godot/lake.gd to; and
    lake.json, the seventeen words the switch reads, for the port."""
    import json
    rng = random.Random(seed)
    rows = []
    for lv in (2, 17):
        for cpu, k in cases(lv, per_record, rng):
            m = Mem(bytes(cpu.ram))
            arm(lv, m, k)
            rows.append({"level": lv, "slot": k,
                         "read": [[a, v] for a, v in sorted(m.read.items())],
                         "calls": [list(c) for c in m.calls],
                         "wrote": [[a, m.ram[a & MASK]] for a in sorted(m.written)]})
    path = os.path.join(out_dir, "lakecheck.json")
    with open(path, "w") as fh:
        json.dump({"cases": rows}, fh, separators=(",", ":"))
    with open(os.path.join(out_dir, "lake.json"), "w") as fh:
        json.dump({"_note": "level 2's overlay, 0x801e8f80: a word a stone, a bit a position "
                            "(tools/lake.py wrote it)", "patterns": patterns()}, fh)
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
    import mipsrun
    ram = mipsrun.level_cpu(2).ram
    pats = patterns()
    print("  stone  cell      laid at   template 0  template 1  size  position 0..5")
    for i in range(COUNT):
        r = O(STONES + i) & MASK
        x, z = struct.unpack_from("<i", ram, r + 0x14)[0] >> 11, struct.unpack_from("<i", ram, r + 0x1C)[0] >> 11
        b = ram[r + 0x38:r + 0x40]
        print(f"  {STONES + i:5d}  ({x:2d}, {z:2d})  ({b[1]:2d}, {b[2]:2d})  ({b[3]:2d}, {b[4]:2d})"
              f"    ({b[3] + b[5]:2d}, {b[4]:2d})    {b[5]}x{b[6]}   "
              f"{''.join('0' if pats[i] >> p & 1 else '1' for p in range(POSITIONS))}")
    print("  (the position's +0x3f for a stone whose lock is its own: 0 the first template, 1 the second)")


if __name__ == "__main__":
    main()
