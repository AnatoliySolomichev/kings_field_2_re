#!/usr/bin/env python3
"""Level 7's teleports: opcode 0xe8 and the pedestal that wakes them (entry 9), against the game's own.

    python3 tools/teleports.py            the twelve teleports and where each goes
    python3 tools/teleports.py --check    the models against the game's own arm,
                                          object_use_state and the overlay's entry 9
    python3 tools/teleports.py --export D teleportcheck.json for the self-test

**Opcode `0xe8`** (`object_interpreter+0x365c`, 0x8004a66c) is a rectangle of
cells given outright -- the record's `+0x38`, `+0x39`, `+0x3a` by `+0x3b`,
its `+0x18` the height `player_in_rect` asks the player's to be near -- and a
place: the cell `+0x3c`, `+0x3d`, the layer `+0x3e` (1 the lower, else the
upper) and the facing `-(+0x3f << 4)`. With the player in it and its `+0x40`
0: screen_capture (the frame kept, 320 by 240), every 0xe8 record's `+0x40`
1, `grid_mark` of the player's cells cleared, the player at the cell's
middle (`<< 11` and 0x400), the layer (0x801b2644) 0 or 5, the facing, and
`place_player_on_terrain`; the view's yaw (0x801b260a) the facing with the
three offsets on, and screen_capture again. Out of it, a `+0x40` other than
0xff back to 0. And either way `+0xa` 0x40 on, held to 0xfff. The loader
leaves `+0x40` 0xff, so none of them works until something clears it.

**The pedestal** (slot 12, opcode `0xa7`, type 0x140) is what clears it.
Ichrius' key (thing 0x85) used on it -- level 7's entry 2, `put_key` --
leaves it the lock 0x85 and state 0 and the key in the ring
(pedestal_put_key, 380 + `+0x39`). Opcode `0xa7` is one of the 191 that
object_interpreter hands to the level's **entry 9** (`level_hooks + 0x24`);
level 7's runs `object_use_state` over the pedestal and the key with the
overlay's two vectors -- (0, -1600, 1024) to (0, -1600, 256), turned by the
pedestal's angles -- 0 and twenty frames, and on the frame the key comes to
rest every 0xe8 record's `+1` is 0x81 and its `+0x40` 0, and use_answer 1.

**How it is held to the game.** The arm: GAME.EXE's own for every 0xe8
record of level 7 (`mipsrun.object_arm`), the player in and about the
rectangle at heights about it, `+0x40` and `+0xa` at random,
screen_capture, grid_mark and place_player_on_terrain stood in for and
logged; the same calls and all of RAM but the stack. The pedestal: frames
of the game's own arm and object_use_state, the key put at random as
pedestal_put_key leaves it, the pedestal, the key and all twelve teleports
compared field by field every frame (tools/seals.py's way), and use_answer.
"""
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import levelin                                                       # noqa: E402
import triggers                                                      # noqa: E402
import useitem                                                       # noqa: E402
from levelin import O, MASK, Mem                                     # noqa: E402

LEVEL = 7
TELEPORT_OP = 0xE8
PEDESTAL_OP = 0xA7
PLAYER_POS = triggers.PLAYER_POS
LAYER = 0x801B2644                # the floor the player stands on: 0 the lower, 5 the upper
FACING = 0x801B2612
VIEW_YAW = 0x801B260A
YAW_OFFSETS = (0x801B261A, 0x801B2622, 0x801B262A)   # the tilt's, the scene's, the nod's
USE_ANSWER = 0x801BA984
COUNT = levelin.COUNT
KEY_RING = 380                    # pedestal_put_key's ring, 0x80197f4c = object_table + 68 * 380
KEY_START = (0, -1600, 1024)      # overlay 7's 0x801e8908, where the key is set down
KEY_END = (0, -1600, 256)         # 0x801e8910, where it comes to rest
KEY_FRAMES = 0x14
HAND_KEY = 0x85

SCREEN_CAPTURE, GRID_MARK, PLACE = 0x8003DAEC, 0x80033C4C, 0x8002B760


def s32(v):
    v &= 0xFFFFFFFF
    return v - 0x100000000 if v & 0x80000000 else v


def arm(m, k):
    """Opcode 0xe8's arm for the record in slot k, over `m`."""
    r = O(k)
    if triggers.player_in_rect(m, m.rd(r + 0x38), m.rd(r + 0x39), m.rd(r + 0x3A),
                               m.rd(r + 0x3B), s32(m.rd(r + 0x18, 4))):
        if m.rd(r + 0x40) == 0:
            m.calls.append(("capture", 1))
            for j in range(COUNT):
                if m.rd(O(j, 4)) == TELEPORT_OP:
                    m.wr(O(j, 0x40), 1)
            m.calls.append(("grid_mark", m.rd(PLAYER_POS, 4), m.rd(PLAYER_POS + 8, 4), 0x320,
                            0xFFFFFFFF))
            m.wr(PLAYER_POS, (m.rd(r + 0x3C) << 11) + 0x400, 4)
            m.wr(PLAYER_POS + 8, (m.rd(r + 0x3D) << 11) + 0x400, 4)
            m.wr(LAYER, 0 if m.rd(r + 0x3E) == 1 else 5, 2)
            m.wr(FACING, -(m.rd(r + 0x3F) << 4), 2)
            m.calls.append(("place",))
            m.wr(VIEW_YAW, m.rd(FACING, 2) + sum(m.rd(a, 2) for a in YAW_OFFSETS), 2)
            m.calls.append(("capture", 0xFFFFFFFF))
    elif m.rd(r + 0x40) != 0xFF:
        m.wr(r + 0x40, 0)
    m.wr(r + 0xA, (m.rd(r + 0xA, 2) + 0x40) & 0xFFF, 2)


def records():
    """Level 7's 0xe8 records as its loader leaves them: [slot]."""
    import objload
    return [k for k, o in sorted(objload.Load(LEVEL).recs.items()) if o["op"] == TELEPORT_OP]


def game_run(cpu, k):
    """GAME.EXE's own arm for record k: [the calls the model logs]."""
    import mipsrun
    calls = []
    cpu.hooks = dict(cpu.hooks)
    cpu.hooks.update({
        SCREEN_CAPTURE: lambda c: calls.append(("capture", c.r[7])),
        GRID_MARK: lambda c: calls.append(("grid_mark",) + tuple(c.r[4:8])),
        PLACE: lambda c: calls.append(("place",)),
    })
    mipsrun.object_arm(cpu, k)
    return calls


def cases(n, rng, snap="a1"):
    """`n` runs of each 0xe8 record: [(the machine, the slot)]."""
    import mipsrun
    base = mipsrun.level_cpu(LEVEL, snap)
    ram0 = bytes(base.ram)
    put = useitem._put
    out = []
    for k in records():
        r = O(k)
        for _ in range(n):
            cpu = mipsrun.CPU(ram0)
            cpu.hooks.update(base.hooks)
            cx, cz = cpu.rd(r + 0x38, 1), cpu.rd(r + 0x39, 1)
            w, h, y = cpu.rd(r + 0x3A, 1), cpu.rd(r + 0x3B, 1), s32(cpu.rd(r + 0x18, 4))
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
            for j in records():
                put(cpu, O(j, 0x40), 1, rng.choice((0, 0, 1, 0xFF)))
            put(cpu, r + 0xA, 2, rng.choice((0, 0xFC0, 0xFFF, rng.randrange(0x10000))))
            put(cpu, FACING, 2, rng.randrange(0x10000))
            for a in YAW_OFFSETS:
                put(cpu, a, 2, rng.choice((0, 0, rng.randrange(0x10000))))
            put(cpu, LAYER, 2, rng.choice((0, 5)))
            out.append((cpu, k))
    return out


def compare(cpu, k):
    m = Mem(bytes(cpu.ram))
    m.wr(0x80198394, O(k), 4)
    m.wr(0x80198390, useitem.TYPES + 24 * m.rd(O(k, 6), 2), 4)
    arm(m, k)
    got = game_run(cpu, k)
    what = hash((tuple(m.calls), tuple(sorted((a, m.ram[a & MASK]) for a in m.written
                                              if m.ram[a & MASK] != m.read.get(a, -1)))))
    if m.calls != got:
        return what, f"slot {k}: calls: model {m.calls}, game {got}"
    a, b = m.ram, cpu.ram
    for lo, hi in ((0, levelin.STACK_LO), (levelin.STACK_HI, len(a))):
        if a[lo:hi] != b[lo:hi]:
            for i in range(lo, hi):
                if a[i] != b[i]:
                    return what, (f"slot {k}: {0x80000000 | i:#x}: model {a[i]:#x}, game "
                                  f"{b[i]:#x} ({levelin._where(0x80000000 | i)})")
    return what, None


# --- the pedestal ------------------------------------------------------------------

def pedestal_step(p, key, teleports, sounds):
    """One frame of opcode 0xa7's escape into level 7's entry 9, on the
    pedestal `p` (tools/seals.py's records), its key (380 + its +0x39, or
    None) and the twelve teleports: object_use_state with the overlay's two
    vectors, and on the frame the key comes to rest every teleport's +1 0x81
    and +0x40 0. True on that frame (use_answer 1)."""
    import seals
    if p["op"] != PEDESTAL_OP or key is None:
        return False
    if not seals.use_state(p, key, KEY_START, KEY_END, KEY_FRAMES, sounds):
        return False
    for t in teleports:
        t["b1"] = 0x81
        t["w40"] = t["w40"] & 0xFFFFFF00
    return True


def pedestal_game_run(rng, frames=48):
    """The game's own arm for the pedestal over level 7: a few frames free,
    then what use_item and pedestal_put_key leave -- the lock 0x85 and state 0,
    the key in a ring slot drawn at random (init_object_record, type 0x85,
    +0x38 0) and the pedestal's +0x39 its place -- and the frames after,
    beside the model: (frames alike, frames, the states)."""
    import mipsrun
    import seals
    cpu = mipsrun.object_cpu(seals.level_ram(LEVEL))
    heard = seals._runner(cpu)
    ot, st = mipsrun.OBJECT_TABLE, mipsrun.OBJECT_STRIDE
    ped = seals.objects_of(LEVEL, PEDESTAL_OP)[0]
    tps = seals.objects_of(LEVEL, TELEPORT_OP)
    ring = rng.randrange(16)
    k_slot = KEY_RING + ring
    used_at = rng.randrange(1, 6)
    for j in tps:
        cpu.wr(ot + st * j + 0x40, 1, rng.choice((0xFF, 0xFF, 1)))
        cpu.wr(ot + st * j + 1, 1, rng.choice((0x80, 0)))
    model = {k: seals.rec_of(cpu, k) for k in [ped] + tps}
    sounds, answers = [], 0
    alike = n = 0
    states = []
    cpu.wr(USE_ANSWER, 4, 0)
    for f in range(frames):
        if f == used_at:
            pb, kb = ot + st * ped, ot + st * k_slot
            cpu.wr(pb + 0x38, 1, HAND_KEY)
            cpu.wr(pb + 8, 2, 0)
            cpu.call(seals.INIT_OBJECT_RECORD, kb)
            cpu.wr(kb + 6, 2, HAND_KEY)
            cpu.wr(kb + 0x38, 1, 0)
            cpu.wr(pb + 0x39, 1, ring)
            model[ped] = seals.rec_of(cpu, ped)
            model[k_slot] = seals.rec_of(cpu, k_slot)
        slots = [ped, k_slot] if k_slot in model else [ped]
        seals._arms(cpu, slots)
        p = model[ped]
        key = model.get(KEY_RING + p["tail"][1]) if p["tail"][1] < 16 else None
        if pedestal_step(p, key, [model[j] for j in tps], sounds):
            answers += 1
        if not states or states[-1] != p["state"]:
            states.append(p["state"])
        got = {k: seals.rec_of(cpu, k) for k in model}
        ok = all(not seals.same(model[k], got[k]) for k in model) and sounds == heard \
            and (cpu.rd(USE_ANSWER, 4) != 0) == (answers > 0)
        n += 1
        alike += ok
    return alike, n, states


def check(out=sys.stdout, per_record=40, seed=71, verbose=False):
    rng = random.Random(seed)
    good = True
    ok = n = 0
    seen = set()
    told = False
    for cpu, k in cases(per_record, rng):
        n += 1
        what, why = compare(cpu, k)
        if why is None:
            ok += 1
            seen.add(what)
        elif not told or verbose:
            told = True
            print(f"  opcode 0xe8: {why}", file=out)
    print(f"opcode 0xe8, the game's own arm: {ok} of {n} runs over level 7's twelve teleports "
          f"agree -- the calls in order and all of RAM but the stack, {len(seen)} different "
          f"outcomes", file=out)
    good &= ok == n
    alike = frames = 0
    ends = set()
    for _ in range(30):
        a, f, states = pedestal_game_run(rng)
        alike += a
        frames += f
        ends.add(tuple(states))
    print(f"level 7's pedestal, the game's own arm, object_use_state and entry 9: {alike} of "
          f"{frames} frames agree -- the pedestal, the key and the twelve teleports field by "
          f"field, the sound and use_answer; {len(ends)} ways through", file=out)
    good &= alike == frames
    return good


def export(out_dir, per_record=6, seed=73):
    """teleportcheck.json: runs of the arm's model -- the bytes read, the
    bytes written, the calls -- which godot/selftest.gd holds
    godot/teleports.gd to."""
    import json
    rng = random.Random(seed)
    rows = []
    for cpu, k in cases(per_record, rng):
        m = Mem(bytes(cpu.ram))
        arm(m, k)
        rows.append({"slot": k, "read": [[a, v] for a, v in sorted(m.read.items())],
                     "wrote": [[a, m.ram[a & MASK]] for a in sorted(m.written)],
                     "calls": [list(c) for c in m.calls]})
    path = os.path.join(out_dir, "teleportcheck.json")
    with open(path, "w") as fh:
        json.dump({"cases": rows}, fh, separators=(",", ":"))
    return path


def show(out=sys.stdout):
    import objload
    L = objload.Load(LEVEL)
    for k in records():
        t = L.recs[k]["tail"]
        print(f"  slot {k:3d}: cell ({t[0]}, {t[1]}) {t[2]}x{t[3]} -> ({t[4]}, {t[5]}), "
              f"{'lower' if t[6] == 1 else 'upper'}, facing {(-(t[7] << 4)) & 0xFFF:#05x}",
              file=out)


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
