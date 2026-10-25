#!/usr/bin/env python3
"""Orladin's key: what it opens -- the seals, its pedestals, and what rises.

    python3 tools/seals.py            every seal and pedestal of the game, the
                                      model against the game's own arms
    python3 tools/seals.py --check    the counts alone

Orladin's key (0x88) is `use_item`'s (`0x8005d300`, tools/useitem.py): a
type-0xa2 object whose +0x38 asks for it becomes 0xfe, and a free type-0x102
pedestal takes the key -- its +0x38 the key's number, +8 0 -- with the key's
own object made in the gold ring (350 + its +0x39). What follows is two arms
of `object_interpreter`, and a third that the first hands on.

**A seal** -- opcode 0x17's arm (`0x8004847c`), 19 of them on levels 14, 16
and 17: the record's +0x3a names a thing (class 0x40) it holds, +0x3c the
key's model below the floor, and the arm switches on +8 through eight arms
from `0x8001244c`, its count the byte at +0x40:

    state 0   +0x38 already 0xfe -- a seal opened on an earlier visit: its
              opcode 0xff, +0 0, state 8. Else the thing taken away
              (object_mode 0, and 3 with 0) -- the chests' path, 0x80048b38
              -- and state 1
    state 1   +0x38 0xfe (use_item): the thing put back (object_mode 1, the
              seal's +0), the count 0, the key's +0x38 0 (never to be
              taken), the key 0x7530 higher, its +0xe -0xb4, state 2
    state 2   the count + 1; the key at the seal plus fixed_madd from
              (0, -0x200, 0) to (0, 0, 0) (0x8009c2f4, 0x8009c2fc, turned by
              the seal's angles) count * 0x1000 / 0x28 of the way, its yaw
              + 0x100; at 0x28 object_sound(the seal, row +0xf), the count
              0, state 3
    state 3   the count + 1; at 0x15, state 4
    state 4   +0x10 0x400 and +5 0x32 -- the lighting class render_walk
              blends the model's towards by +0x10 -- and +2's low three bits
              5, semi-transparent at rate 1, the seal's and the key's; state 5
    state 5   +0x10 + 0xc0 while it is under 0x1000; then the key's opcode
              and type 0xff and its +0 0, +0x10 0x1000, the seal's +0 0, the
              count 0, state 6
    state 6   the count + 1: under 0x20 the thing 0x30 higher; at 0x20 its
              opcode 0x10 and its +0x40 its height, state 7
    state 7   object_mode 2 -- the thing free to take -- and 3 with 0; the
              seal's opcode 0xff, state 8

so the key rises into the seal and turns there for 0x28 frames, waits 0x15,
both fade for sixteen, and the thing inside lifts 0x5d0 in 31 frames and is
free to take. **Opcode 0x10** (`0x8004b1d4`), which nothing places, is what
it is handed: +0x26 + 0x80 a frame and the height its +0x40 plus
`game_sin(+0x26) >> 6` -- it turns, and bobs 64 up and down every 32 frames.

**Orladin's pedestal** -- opcode 0x1a's arm (`0x8004b000`), 18 on the same
levels: `object_use_state` (`0x80046914`) with the key (slot 350 + +0x39),
`(0, -100, 300)` and `(0, 0, 64)` (`0x8009c328`, `0x8009c330`), 0 and 20 --
as Silviera's pedestal does with its own two (tools/chests.py), the key of
type 0x88 lying on its side (+0x24 0x400) and its +0xe 0x64 -- and on its
answer the key's +0x38 0 (never taken back), the object +0x3b names ORs
+0x3a into its lock -- a gate, which USE then opens -- and state 3; then

    state 3   +5 0x32 and +2's low bits 5, the pedestal's and the key's,
              state 4
    state 4   +0x10 + 0x100, both, until 0xfff: both 0xfff, state 5
    state 5   both types 0xff, state 0x63

so the key comes down onto it in twenty frames, the gate's lock takes the
bits, and pedestal and key fade and are gone.

**How it is held to the game.** `check()` runs GAME.EXE's own arms with
`tools/mipsrun.py` over each of the three levels as its own
`load_object_placement` leaves them (`mipsrun.level_cpu`), every seal from its
first frame -- its lock asking for the key, then 0xfe a few frames on, as
use_item leaves it; and again with the lock 0xfe from the first frame, an
earlier visit's -- and every pedestal, the key made in the gold ring as
use_item makes it (the game's own `init_object_record`, the ring's place at
random), each arm in slot order with `object_mode`, `vec_rotate`,
`fixed_madd`, `game_sin`, `object_use_state` and the levels' own entry 9
(the key's opcode 0x70: `jr $ra` on all three) running, `object_sound`
logged. Every frame, every field of every record in play -- the seal, the
thing and the key; the pedestal and the key, and the gate's lock -- and the
sounds must be the model's.
"""
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import chests                                                        # noqa: E402
import movement                                                      # noqa: E402
import weapon                                                        # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

SEAL_OP, BOB_OP, PEDESTAL_OP = 0x17, 0x10, 0x1A
OFF, OPENED = 0xFF, 0xFE
SEAL_FROM, SEAL_TO = (0, -0x200, 0), (0, 0, 0)     # 0x8009c2f4, 0x8009c2fc
SEAL_FRAMES = 0x28            # the key's rise, and the turn with it
SEAL_SPIN = 0x100             # its yaw a frame
SEAL_WAIT = 0x15              # state 3
SEAL_RAISE = 0x7530           # the key brought up from below the floor at state 1
SEAL_KEY_LIGHT = -0xB4        # and its +0xe
FADE_BITS, FADE_LIGHT = 5, 0x32   # +2's low three bits and +5, the fade
SEAL_FADE_FROM, SEAL_FADE_STEP = 0x400, 0xC0
RISE, RISE_FRAMES = 0x30, 0x20    # what the thing does at state 6
BOB_TURN = 0x80
PED_START, PED_END = (0, -100, 300), (0, 0, 64)    # 0x8009c328, 0x8009c330
PED_FRAMES, PED_FADE = 20, 0x100
PED_FADED = 0xFFF
GOLD_RING = 350               # 0x80197754: object_table + 68 * 350
KEY_OP, AT_REST = 0x70, 0x63
GOLD_TYPE = 0x95              # object_mode 0 leaves gold's angles alone
ORLADIN_KEY = 0x88


def s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def s32(v):
    v &= 0xFFFFFFFF
    return v - 0x100000000 if v & 0x80000000 else v


def count(r):
    """The byte at +0x40, the seal's and the pedestal's count."""
    return r["w40"] & 0xFF


def set_count(r, n):
    r["w40"] = (r["w40"] & 0xFFFFFF00) | (n & 0xFF)


# --- the model ------------------------------------------------------------------

def object_mode(r, mode, value=0):
    """`object_mode` (0x80044900) on a class-0x40 record. 0 takes it away --
    +0 and +0x38 0 -- and, but for gold, takes its angles from +0x3a..+0x3c
    again (a byte of 0xff leaves one alone, the rest << 6) and, with +0x39 0,
    hands it opcode 0x10 with its height at +0x40; 1 puts +0 back; 2 frees it
    to take (+0x38 0xff); 3 writes +0xe."""
    if mode == 0:
        r["b0"] = 0
        r["tail"][0] = 0
        if r["type"] == GOLD_TYPE:
            return
        for i in range(3):
            if r["tail"][2 + i] != 0xFF:
                r["angles"][i] = (r["tail"][2 + i] << 6) & 0xFFFF
        if r["tail"][1] == 0:
            r["op"] = BOB_OP
            r["w40"] = r["pos"][1] & 0xFFFFFFFF
    elif mode == 1:
        r["b0"] = value & 0xFF
    elif mode == 2:
        r["tail"][0] = 0xFF
    elif mode == 3:
        r["light"] = s16(value)


def init_object_record(r):
    """`init_object_record` (0x800448b8)."""
    r.update({"b0": 0, "b1": 0x80, "b2": 0, "op": 0xFF, "b5": 0xFF, "clk": 0,
              "light": 0, "fade": 0, "angles": [0, 0, 0],
              "scale": [0x1000, 0x1000, 0x1000]})


def fade(r):
    """+2's low three bits 5 and +5 0x32: semi-transparent at rate 1, the
    lighting blended towards class 0x32 by +0x10."""
    r["b2"] = (r["b2"] & 0xF8) | FADE_BITS
    r["b5"] = FADE_LIGHT


def seal_step(s, a, b, sounds):
    """One frame of opcode 0x17's arm (0x8004847c) on the seal `s`, the thing
    `a` its +0x3a names and the key `b` its +0x3c names. `sounds` gets
    (slot, id) for object_sound."""
    st = s["state"]
    if st == 0:
        if s["tail"][0] == OPENED:
            s["op"] = OFF
            s["b0"] = 0
            s["state"] = 8
        else:
            object_mode(a, 0)
            object_mode(a, 3, 0)
            s["state"] = 1
    elif st == 1:
        if s["tail"][0] == OPENED:
            object_mode(a, 1, s["b0"])
            set_count(s, 0)
            b["tail"][0] = 0
            b["pos"][1] = s32(b["pos"][1] - SEAL_RAISE)
            s["state"] = 2
            b["light"] = SEAL_KEY_LIGHT
    elif st == 2:
        v = weapon.vec_rotate(s["angles"], SEAL_FROM)
        w = weapon.vec_rotate(s["angles"], SEAL_TO)
        n = (count(s) + 1) & 0xFF
        set_count(s, n)
        t = (n << 12) // SEAL_FRAMES
        b["pos"] = [s32(chests.lerp(v[i], w[i], t) + s["pos"][i]) for i in range(3)]
        b["angles"][1] = (b["angles"][1] + SEAL_SPIN) & 0xFFFF
        if n >= SEAL_FRAMES:
            sounds.append((s["slot"], s["sound"]))
            set_count(s, 0)
            s["state"] = 3
    elif st == 3:
        n = (count(s) + 1) & 0xFF
        set_count(s, n)
        if n >= SEAL_WAIT:
            s["state"] = 4
    elif st == 4:
        s["fade"] = SEAL_FADE_FROM
        fade(s)
        fade(b)
        s["state"] = 5
    elif st == 5:
        if s["fade"] < 0x1000:
            s["fade"] = (s["fade"] + SEAL_FADE_STEP) & 0xFFFF
        else:
            b["op"] = OFF
            b["b0"] = 0
            b["type"] = 0xFF
            s["fade"] = 0x1000
            s["b0"] = 0
            set_count(s, 0)
            s["state"] = 6
    elif st == 6:
        n = (count(s) + 1) & 0xFF
        set_count(s, n)
        if n < RISE_FRAMES:
            a["pos"][1] = s32(a["pos"][1] - RISE)
        else:
            a["op"] = BOB_OP
            a["w40"] = a["pos"][1] & 0xFFFFFFFF
            s["state"] = 7
    elif st == 7:
        object_mode(a, 2)
        object_mode(a, 3, 0)
        s["op"] = OFF
        s["state"] = 8


def bob_step(r):
    """One frame of opcode 0x10's arm (0x8004b1d4): the yaw + 0x80, the
    height +0x40 plus game_sin(yaw) >> 6."""
    r["angles"][1] = (r["angles"][1] + BOB_TURN) & 0xFFFF
    r["pos"][1] = s32(s32(r["w40"]) + (movement.game_sin(s16(r["angles"][1])) >> 6))


def use_state(p, key, start, end, frames, sounds, busy=0):
    """`object_use_state` (0x80046914) with a fifth argument of 0, on full
    records: at state 0 with a lock other than 0xff the key is made --
    init_object_record, opcode 0x70, the pedestal's +0, +1 0x80, set where
    `start` puts it, the pedestal's slot at its u16 +0x40 and its yaw; type
    0x88 lies on its side (+0x24 0x400, +0xe 0x64), 0x85 has +0xe -0xdc --
    the count 0, or frames - 1 if the key's +0x38 is not 0, and state 1;
    then (and at state 1) the count + 1 and the key fixed_madd from `start`
    to `end` (both turned by the pedestal's angles) count / frames of the way;
    at `frames` object_sound(the key, 0x12) unless a level change is under
    way, the key's +0x38 0xff, state 0x63, and True."""
    if p["state"] == 0:
        if p["tail"][0] == 0xFF:
            return False
        set_count(p, frames - 1 if key["tail"][0] != 0 else 0)
        p["state"] = 1
        init_object_record(key)
        key["op"] = KEY_OP
        key["b0"] = p["b0"]
        if key["type"] == 0x85:
            key["light"] = -0xDC
        elif key["type"] == ORLADIN_KEY:
            key["angles"][0] = 0x400
            key["light"] = 0x64
        key["b1"] = 0x80
        v = weapon.vec_rotate(p["angles"], start)
        key["pos"] = [s32(v[i] + p["pos"][i]) for i in range(3)]
        key["w40"] = (key["w40"] & 0xFFFF0000) | (p["slot"] & 0xFFFF)
        key["angles"][1] = p["angles"][1]
    elif p["state"] != 1:
        return False
    v = weapon.vec_rotate(p["angles"], start)
    w = weapon.vec_rotate(p["angles"], end)
    n = (count(p) + 1) & 0xFF
    set_count(p, n)
    t = (n << 12) // frames
    key["pos"] = [s32(chests.lerp(v[i], w[i], t) + p["pos"][i]) for i in range(3)]
    if n < frames:
        return False
    if not busy:
        sounds.append((key["slot"], 0x12))
    key["tail"][0] = 0xFF
    p["state"] = AT_REST
    return True


def pedestal_step(p, key, target, sounds):
    """One frame of opcode 0x1a's arm (0x8004b000) on Orladin's pedestal `p`,
    its key (slot 350 + its +0x39; None while that is past the table, which
    the game reads only once the lock is not 0xff) and `target`, the record
    +0x3b names, of which only the lock (+0x38) is touched."""
    if key is not None and use_state(p, key, PED_START, PED_END, PED_FRAMES, sounds):
        key["tail"][0] = 0
        target["tail"][0] |= p["tail"][2]
        p["state"] = 3
    st = p["state"]
    if st == 3:
        fade(p)
        fade(key)
        p["state"] = 4
    elif st == 4:
        p["fade"] = (p["fade"] + PED_FADE) & 0xFFFF
        key["fade"] = (key["fade"] + PED_FADE) & 0xFFFF
        if p["fade"] >= PED_FADED:
            p["fade"] = key["fade"] = PED_FADED
            p["state"] = 5
    elif st == 5:
        p["type"] = 0xFF
        key["type"] = 0xFF
        p["state"] = AT_REST


# --- against the game's own -------------------------------------------------------

OBJECT_SOUND = 0x8004482C
INIT_OBJECT_RECORD = 0x800448B8


def rec_of(cpu, slot):
    """The record in `slot` as the model keeps it -- every field of it."""
    import mipsrun
    b = mipsrun.OBJECT_TABLE + mipsrun.OBJECT_STRIDE * slot
    rd = cpu.rd
    r = {"slot": slot, "b0": rd(b, 1), "b1": rd(b + 1, 1), "b2": rd(b + 2, 1),
         "b3": rd(b + 3, 1), "op": rd(b + 4, 1), "b5": rd(b + 5, 1), "type": rd(b + 6, 2),
         "state": rd(b + 8, 2), "clk": rd(b + 0xA, 2), "wc": rd(b + 0xC, 2),
         "light": s16(rd(b + 0xE, 2)), "fade": rd(b + 0x10, 2), "w12": rd(b + 0x12, 2),
         "pos": [s32(rd(b + 0x14 + 4 * i, 4)) for i in range(3)],
         "w20": rd(b + 0x20, 4), "angles": [rd(b + 0x24 + 2 * i, 2) for i in range(3)],
         "w2a": rd(b + 0x2A, 2), "scale": [rd(b + 0x2C + 2 * i, 2) for i in range(3)],
         "w32": rd(b + 0x32, 4), "w36": rd(b + 0x36, 2),
         "tail": [rd(b + 0x38 + i, 1) for i in range(8)], "w40": rd(b + 0x40, 4)}
    typ = r["type"]
    row = mipsrun.OBJECT_TYPES + 24 * typ
    r["cls"] = rd(row, 1) if typ != 0xFF else 0xFF
    r["sound"] = rd(row + 0xF, 1) if typ != 0xFF else 0
    return r


FIELDS = ("b0", "b1", "b2", "b3", "op", "b5", "type", "state", "clk", "wc", "light", "fade",
          "w12", "pos", "w20", "angles", "w2a", "scale", "w32", "w36", "tail", "w40")


def same(a, b):
    """The fields of two records that differ."""
    return [f for f in FIELDS if a[f] != b[f]]


def _runner(cpu):
    """object_sound logged on the machine: [(slot, id)]."""
    import mipsrun
    log = []

    def sound(c):
        log.append(((c.r[4] - mipsrun.OBJECT_TABLE) // mipsrun.OBJECT_STRIDE, c.r[5] & 0xFF))
        return 0
    cpu.hooks[OBJECT_SOUND] = sound
    return log


def _arms(cpu, slots):
    """One pass of object_interpreter over `slots`, in slot order: each
    record's own arm, a record whose opcode is 0xff skipped."""
    import mipsrun
    for k in sorted(slots):
        if cpu.rd(mipsrun.OBJECT_TABLE + mipsrun.OBJECT_STRIDE * k + 4, 1) != OFF:
            mipsrun.object_arm(cpu, k)


_BASE = {}


def level_ram(lv):
    """The level as its own load_object_placement leaves it (cached)."""
    import mipsrun
    if lv not in _BASE:
        _BASE[lv] = bytes(mipsrun.level_cpu(lv).ram)
    return _BASE[lv]


def objects_of(lv, op):
    """The slots of level `lv` whose opcode is `op`, after the load."""
    import mipsrun
    ram = level_ram(lv)
    base = mipsrun.OBJECT_TABLE & 0x1FFFFF
    return [k for k in range(396) if ram[base + mipsrun.OBJECT_STRIDE * k + 4] == op]


def seal_game_run(lv, slot, opened_at, frames=200):
    """The game's own arm for the seal in `slot`, its lock made 0xfe on frame
    `opened_at` (0: before the first), beside the model: (frames alike,
    frames, the states it went through)."""
    import mipsrun
    cpu = mipsrun.object_cpu(level_ram(lv))
    heard = _runner(cpu)
    s = rec_of(cpu, slot)
    a_slot = s["tail"][2] | s["tail"][3] << 8
    b_slot = s["tail"][4] | s["tail"][5] << 8
    slots = sorted({slot, a_slot, b_slot})
    model = {k: rec_of(cpu, k) for k in slots}
    sounds = []
    alike = n = 0
    states = []
    for f in range(frames):
        if f == opened_at:
            cpu.wr(mipsrun.OBJECT_TABLE + mipsrun.OBJECT_STRIDE * slot + 0x38, 1, OPENED)
            model[slot]["tail"][0] = OPENED
        _arms(cpu, slots)
        for k in slots:
            r = model[k]
            if r["op"] == SEAL_OP:
                seal_step(r, model[a_slot], model[b_slot], sounds)
            elif r["op"] == BOB_OP:
                bob_step(r)
        if not states or states[-1] != model[slot]["state"]:
            states.append(model[slot]["state"])
        ok = all(not same(model[k], rec_of(cpu, k)) for k in slots) and sounds == heard
        n += 1
        alike += ok
    return alike, n, states


def pedestal_game_run(lv, slot, rng, frames=60):
    """The game's own arm for Orladin's pedestal in `slot`: a few frames free,
    then what use_item's arm leaves -- the lock 0x88, the state 0, the key
    made in the gold ring at a place drawn at random (the game's own
    init_object_record, its type 0x88, +0x38 0, +0x3c the count) and the
    pedestal's +0x39 that place -- and the frames after, beside the model:
    (frames alike, frames, the states)."""
    import mipsrun
    cpu = mipsrun.object_cpu(level_ram(lv))
    heard = _runner(cpu)
    ot, st = mipsrun.OBJECT_TABLE, mipsrun.OBJECT_STRIDE
    p0 = rec_of(cpu, slot)
    target = p0["tail"][3]
    ring = rng.randrange(10)
    k_slot = GOLD_RING + ring
    used_at = rng.randrange(1, 6)
    drops = rng.randrange(0x10000)
    model = {slot: p0, target: rec_of(cpu, target)}
    sounds = []
    alike = n = 0
    states = []
    for f in range(frames):
        if f == used_at:
            pb, kb = ot + st * slot, ot + st * k_slot
            cpu.wr(pb + 0x38, 1, ORLADIN_KEY)
            cpu.wr(pb + 8, 2, 0)
            cpu.call(INIT_OBJECT_RECORD, kb)
            cpu.wr(kb + 0x3C, 2, drops)
            cpu.wr(kb + 6, 2, ORLADIN_KEY)
            cpu.wr(kb + 0x38, 1, 0)
            cpu.wr(pb + 0x39, 1, ring)
            model[slot] = rec_of(cpu, slot)
            model[k_slot] = rec_of(cpu, k_slot)
        slots = [slot, k_slot] if k_slot in model else [slot]
        _arms(cpu, slots)
        p = model[slot]
        key = model.get(GOLD_RING + p["tail"][1]) if p["tail"][1] < 10 else None
        pedestal_step(p, key, model[target], sounds)
        if not states or states[-1] != p["state"]:
            states.append(p["state"])
        got = {k: rec_of(cpu, k) for k in model}
        ok = all(not same(model[k], got[k]) for k in model if k != target) \
            and model[target]["tail"][0] == got[target]["tail"][0] and sounds == heard
        n += 1
        alike += ok
    return alike, n, states


LEVELS = (14, 16, 17)


def check(out=sys.stdout, verbose=False, seed=17):
    """Every seal twice -- opened in play, and opened before -- and every
    pedestal three times, against the game's own arms."""
    rng = random.Random(seed)
    seal_ok = seal_n = runs = 0
    ped_ok = ped_n = pruns = 0
    paths = set()
    for lv in LEVELS:
        for slot in objects_of(lv, SEAL_OP):
            for opened_at in (0, rng.randrange(1, 8)):
                a, n, states = seal_game_run(lv, slot, opened_at)
                seal_ok += a
                seal_n += n
                runs += 1
                paths.add(tuple(states))
                if verbose or a != n:
                    print(f"  level {lv} seal {slot}, opened on frame {opened_at}: "
                          f"{a} of {n} frames, states {states}", file=out)
        for slot in objects_of(lv, PEDESTAL_OP):
            for _ in range(3):
                a, n, states = pedestal_game_run(lv, slot, rng)
                ped_ok += a
                ped_n += n
                pruns += 1
                if verbose or a != n:
                    print(f"  level {lv} pedestal {slot}: {a} of {n} frames, "
                          f"states {states}", file=out)
    print(f"  the seals (opcode 0x17, and 0x10 on what they hold): {seal_ok} of "
          f"{seal_n} frames of the game's own arms over levels 14, 16 and 17, "
          f"{runs} runs -- every field of the seal, the thing and the key, and "
          f"the sounds; {len(paths)} paths: "
          + "; ".join(" ".join(str(s) for s in p) for p in sorted(paths)), file=out)
    print(f"  Orladin's pedestals (opcode 0x1a, object_use_state): {ped_ok} of "
          f"{ped_n} frames, {pruns} runs -- every field of the pedestal and the "
          f"key, the gate's lock, the sounds", file=out)
    return seal_ok == seal_n and ped_ok == ped_n


def export(out_dir):
    """sealcheck.json for godot/selftest.gd: a seal turned each way, a frame
    at a time from its first, opened on frame 3 -- and once opened before --
    and a pedestal each way: the records the model starts from and its frames
    of each: the seal's [state, count, +0x10, +0, +2, +5, the thing's +0,
    +0x38, op, y, yaw, +0x40, the key's x, y, z, yaw, +0, +2, +5, type,
    +0x38], the pedestal's [state, count, +0x10, +2, +5, type, the key's x,
    y, z, angles, op, +0, +2, +5, type, +0x38, +0x10, u16 +0x40, the gate's
    lock]."""
    import json
    seals, pedestals = [], []
    for ang in (0, 0x400, 0x800):
        for opened_at in (3, 0):
            s = {"slot": 10, "b0": 2, "b2": 0, "op": SEAL_OP, "b5": OFF, "type": 0xA2,
                 "state": 0, "fade": 0, "pos": [133120, -6164, 66560],
                 "angles": [0, ang, 0], "tail": [ORLADIN_KEY, 0, 184, 0, 183, 0, 0xFF, 0xFF],
                 "w40": 0xFFFFFFFF, "sound": 0x12, "light": 0}
            a = {"slot": 184, "b0": 2, "b2": 0, "op": OFF, "b5": OFF, "type": 0x6F,
                 "state": 0, "fade": 0, "pos": [134144, -5064, 66560], "angles": [0, 0, 0],
                 "tail": [0xFF] * 8, "w40": 0xFFFFFFFF, "light": -80}
            b = {"slot": 183, "b0": 2, "b2": 0, "op": OFF, "b5": OFF, "type": ORLADIN_KEY,
                 "state": 0, "fade": 0, "pos": [134144, 25136, 66560], "angles": [0, 0, 0],
                 "tail": [0xFF] * 8, "w40": 0xFFFFFFFF, "light": 0}
            start = {"seal": json.loads(json.dumps(s)), "thing": json.loads(json.dumps(a)),
                     "key": json.loads(json.dumps(b)), "opened_at": opened_at}
            rows, sounds = [], []
            for f in range(140):
                if f == opened_at:
                    s["tail"][0] = OPENED
                if s["op"] == SEAL_OP:
                    seal_step(s, a, b, sounds)
                if a["op"] == BOB_OP:
                    bob_step(a)
                rows.append([s["state"], count(s), s["fade"], s["b0"], s["b2"], s["b5"],
                             a["b0"], a["tail"][0], a["op"], a["pos"][1], a["angles"][1],
                             s32(a["w40"]), *b["pos"], b["angles"][1], b["b0"], b["b2"],
                             b["b5"], b["type"], b["tail"][0]])
            start["frames"] = rows
            seals.append(start)
        p = {"slot": 22, "b0": 2, "b2": 0, "op": PEDESTAL_OP, "b5": OFF, "type": 0x102,
             "state": 0, "fade": 0, "pos": [121856, -6144, 107008], "angles": [0, ang, 0],
             "tail": [ORLADIN_KEY, 2, 3, 20, 0xFF, 0xFF, 0xFF, 0xFF], "w40": 0xFFFFFFFF,
             "light": 100}
        k = {"slot": GOLD_RING + 2, "b0": 0, "b2": 0, "op": OFF, "b5": OFF,
             "type": ORLADIN_KEY, "state": 0, "fade": 0, "pos": [0, 0, 0], "angles": [0, 0, 0],
             "tail": [0, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF], "w40": 0xFFFFFFFF,
             "light": 0}
        g = {"tail": [0xFC]}
        start = {"pedestal": json.loads(json.dumps(p)), "key": json.loads(json.dumps(k))}
        rows, sounds = [], []
        for f in range(45):
            pedestal_step(p, k, g, sounds)
            rows.append([p["state"], count(p), p["fade"], p["b2"], p["b5"], p["type"],
                         *k["pos"], *k["angles"], k["op"], k["b0"], k["b2"], k["b5"],
                         k["type"], k["tail"][0], k["fade"], k["w40"] & 0xFFFF, g["tail"][0]])
        start["frames"] = rows
        pedestals.append(start)
    path = os.path.join(out_dir, "sealcheck.json")
    with open(path, "w") as fh:
        json.dump({"seals": seals, "pedestals": pedestals}, fh, separators=(",", ":"))
    return path


if __name__ == "__main__":
    sys.exit(0 if check(verbose="--check" not in sys.argv) else 1)
