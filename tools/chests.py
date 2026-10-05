#!/usr/bin/env python3
"""Chests, and what the player picks up out of them and off the floor.

    python3 tools/chests.py            the lid against the snapshots, with detail
    python3 tools/chests.py --check    the same, the counts alone

A small chest is three objects in one cell: the body (type 155, class 0xff,
a solid rectangle), the lid (class 6, opcode 6) 0x280 above it, and what is
in it (class 0x40), which the lid hides on its first frame. A big chest is
one object of class 7 with its contents beside it, and a class-0xe5 record
for its body. FORMATS.md, "Chests, and picking things up", has the reading.

**The lid** -- `object_interpreter`'s arm for opcode 6 (`0x80048790`), on the
record's state (+8), its X angle (+0x24) and an angular velocity (+0x40):

    state 0   the lock (+0x38) already 0xfe: the angle 0xa00, state 3. Else
              the contents (the slot at +0x3a) hidden -- object_mode 0 and
              3 -- and state 1
    state 1   the lock 0xfe (object_interact wrote it): the velocity -0x10,
              state 2, the contents put back (object_mode 1, the lid's +0),
              a sound
    state 2   the velocity spring_to(0xa00, angle, velocity, 8, 4), the
              angle += it; under 0xc00 the contents can be taken (object_mode
              2); at rest on 0xa00, state 3. A trap byte (+0x3c) other than
              0xff fires an effect each frame -- not here.

**The big chest** -- opcode 7 (`0x80048960`): state 0 adds 0xc8 to its
contents' +0xe and hides them as the lid does; state 1 waits for the lock to
read 0xfe; state 2 counts +0xa up by 0x80 a frame, and at 0xfff the contents
can be taken and it is state 3. The counter is the clock of its model's
animation, as for a lift door.

**Taking something** -- `object_give` (`0x8005db30`), from `object_interact`
on USE for a class-0x40 object whose +0x38 is 0xff. Gold (the type row's +1
is 0x20) is counted at once: `announce(0x19, +0x3a)`, the gold, the type
0xff. Anything else runs a sequence of its own frames, the world stopped:

    the view's pitch levels -- to 0 under 0x800, else 0xfff -- while the
    thing flies in nine frames (t = 0, 0x200 .. 0x1000) from where it lies to
    a point 0x5dc + row[+0xe] ahead of the eye and 0x1f4 + row[+0xc] below
    it (and row[+0xc] lower again), turning to face the player
    then it turns 0x40 a frame until a button is pressed -- all released
    first, then any; a press during the flight cuts it short
    USE: give_item. If that fails, as for anything else: turn back by 0x100
    a frame to within 0x80 of facing the player, and fly back in nine
    frames. If it took: (arrows 0x93 add 4..9 more, light arrows 0x94 four)
    fly to 0x1f4 left of and below the eye in nine frames, and the type 0xff.

**A key** -- `use_item`'s arm for the royal, copper, silver, magician's, jail,
dwarves' and Lyn's keys (`0x8005d188`) asks `find_object` for each object in
front of `player_pos` itself (0x320 past the type's reach, 0x6a4 as the
point's height, within 0x200 of the facing) and tries the key on it
(`0x80046608`, `key_test` below): 1 the lock was the key's own number and is
0xff now, so USE opens it as any other -- a sound, and that is all; 3 or 4
"Wrong key!"; 0 or 2 the next object; none left, "Nothing Happens". The key
is kept. `python3 tools/chests.py --keys` lists which lock takes which key.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import knock                                                         # noqa: E402
import weapon                                                        # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

LID_OPEN = 0xA00         # the angle the lid springs to
LID_KICK = -0x10         # its velocity when it starts
LID_ACCEL, LID_FRICTION = 8, 4
LID_FREE = 0xC00         # under it, what is inside can be taken
BIG_RATE = 0x80          # the big chest's counter a frame
BIG_LIGHT = 0xC8         # what it adds to its contents' +0xe at state 0
OPENED, LOCK_FREE = 0xFE, 0xFF
GOLD = 0x20              # type row +1 of the gold
EYE = 0x640
FLIGHT = 0x200           # t a frame, nine frames each way
SPIN = 0x40              # the turn a frame while it waits
TURN_BACK, TURN_TOL = 0x100, 0x80
ARROWS, LIGHT_ARROWS = 0x93, 0x94


def s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v >= 0x8000 else v


def lid_step(d, mode):
    """One frame of opcode 6's arm on `d` (state, angle, vel, lock);
    `mode(m, value)` is object_mode on the contents."""
    st = d["state"]
    if st == 0:
        if d["lock"] == OPENED:
            d["angle"], d["state"] = LID_OPEN, 3
        else:
            mode(0, 0)
            mode(3, 0)
            d["state"] = 1
    elif st == 1:
        if d["lock"] == OPENED:
            d["vel"], d["state"] = LID_KICK, 2
            mode(1, 2)
    elif st == 2:
        d["vel"] = s16(knock.spring(LID_OPEN, d["angle"], d["vel"],
                                    LID_ACCEL, LID_FRICTION))
        d["angle"] = (d["angle"] + d["vel"]) & 0xFFF
        if d["angle"] < LID_FREE:
            mode(2, 0)
        if d["vel"] == 0 and d["angle"] == LID_OPEN:
            d["state"] = 3


def big_step(d, mode):
    """One frame of opcode 7's arm on `d` (state, counter, lock)."""
    st = d["state"]
    if st == 0:
        mode(4, BIG_LIGHT)                     # the contents' +0xe, added to
        if d["lock"] == OPENED:
            d["counter"], d["state"] = 0xFFF, 3
        else:
            mode(0, 0)
            mode(3, 0)
            d["state"] = 1
    elif st == 1:
        if d["lock"] == OPENED:
            d["state"] = 2
            mode(1, 2)
    elif st == 2:
        d["counter"] = (d["counter"] + BIG_RATE) & 0xFFFF
        if d["counter"] >= 0xFFF:
            mode(2, 0)
            d["counter"], d["state"] = 0xFFF, 3


def cycle(step, d, frames=200):
    """[(state, angle or counter, vel, contents present, takeable)] from USE."""
    c = {"present": 0, "free": 0}

    def mode(m, v):
        if m == 0:
            c["present"], c["free"] = 0, 0
        elif m == 1:
            c["present"] = v
        elif m == 2:
            c["free"] = 1
    rows = []
    step(d, mode)                               # the first frame: hide them
    d["lock"] = OPENED                          # USE
    for _ in range(frames):
        step(d, mode)
        rows.append((d["state"], d.get("angle", d.get("counter")), d.get("vel", 0),
                     c["present"], c["free"]))
        if d["state"] == 3:
            break
    return rows


def lid_cycle():
    return cycle(lid_step, {"state": 0, "angle": 0, "vel": 0, "lock": LOCK_FREE})


def big_cycle():
    return cycle(big_step, {"state": 0, "counter": 0, "lock": LOCK_FREE})


# -- object_give ----------------------------------------------------------

def angle_lerp(a, b, t):
    """0x80017170: from a towards b the short way round, by t / 0x1000."""
    d = (s16(b) - s16(a)) & 0xFFF
    if d >= 0x801:
        d -= 0x1000
    return (a + ((d * t) >> 12)) & 0xFFF


def lerp(a, b, t):
    """fixed_madd (0x80017158): a + ((b - a) * t >> 12)."""
    return a + (((b - a) * t) >> 12)


def eye_point(player, pitch, facing, v, dy):
    """0x8005be28: v turned by (-pitch, facing, 0) about the eye, and dy more
    down: the point the flight aims at."""
    x, y, z = weapon.vec_rotate((s16(-pitch), facing, 0), v)
    return [x + player[0], y - EYE + dy + player[1], z + player[2]]


def level_pitch(p):
    """What object_give levels the view to: 0 under 0x800, 0xfff above."""
    p &= 0xFFF
    if p < 0x800:
        return 0
    return 0xFFF if p < 0xFFF else p


def give_frames(pos, angles, row_c, row_e, player, view_pitch, facing,
                press, take):
    """The frames object_give draws: [(x, y, z, ax, ay, az, pitch)].

    `press` is the frame of the wait (counting from the first frame of the
    flight) on which a button goes down, `take` whether it is USE and
    give_item took it."""
    out = []
    s7 = view_pitch & 0xFFF
    s3 = level_pitch(view_pitch)
    start = list(pos)
    a0 = list(angles)
    front = eye_point(player, s3, facing, (0, 0x1F4 + row_c, 0x5DC + row_e), row_c)
    a1 = [0, (facing + 0x800) & 0xFFF, 0]
    obj = {"p": list(pos), "a": list(angles)}
    pitch = s7
    n = 0
    t = 0
    pressed = False
    while t <= 0x1000:
        if n == press:
            pressed = True
            break
        obj["p"] = [lerp(start[i], front[i], t) for i in range(3)]
        obj["a"] = [angle_lerp(a0[0], a1[0], t), angle_lerp(a0[1], a1[1], t),
                    angle_lerp(a0[2], a1[2], t)]
        pitch = angle_lerp(s7, s3, t)
        out.append((*obj["p"], *obj["a"], pitch))
        n += 1
        t += FLIGHT
    while not pressed:
        if n == press:
            break
        obj["a"][1] = (obj["a"][1] + SPIN) & 0xFFFF
        out.append((*obj["p"], *obj["a"], pitch))
        n += 1
    if take:
        pocket = eye_point(player, s3, facing, (-0x1F4, 0x1F4, 0), 0)
        a_from = list(obj["a"])
        frm, to = pocket, list(obj["p"])
    else:
        while not knock.facing_test(obj["a"][1], (facing + 0x800) & 0xFFF, TURN_TOL):
            obj["a"][1] = (obj["a"][1] + TURN_BACK) & 0xFFF
            out.append((*obj["p"], *obj["a"], pitch))
        obj["a"][1] = (facing + 0x800) & 0xFFF
        a_from = list(a0)
        frm, to = start, list(obj["p"])
    a_to = list(obj["a"])
    s3 = pitch
    t = 0x1000
    while t >= 0:
        obj["p"] = [lerp(frm[i], to[i], t) for i in range(3)]
        obj["a"] = [angle_lerp(a_from[0], a_to[0], t), angle_lerp(a_from[1], a_to[1], t),
                    angle_lerp(a_from[2], a_to[2], t)]
        pitch = angle_lerp(s7, s3, t)
        out.append((*obj["p"], *obj["a"], pitch))
        t -= FLIGHT
    return out


# -- what falls -----------------------------------------------------------
#
# A dying creature's gold (spawn_gold, 0x80046294) and its thing
# (spawn_thing, 0x800460bc) are objects made on the spot, in rings of slots from 350, with
# their +0x38 0xff -- free to take as they fall. The gold falls by opcode
# 0x62; a thing by its type row's +1:
#
#   0x10, 0x13, 0x16           0x60  falls, then tips over to lie flat
#   0x17                       0x61  sinks at 20 a frame, spinning
#   0x11 0x12 0x14 0x15 0x18
#   0x19 0x20                  0x62  falls and bounces
#   0x1a .. 0x1f               none: it stays where it was made
#
# and a type whose row's +3 has 0x10 is drawn at twice the size.

DROP_OP = {0x10: 0x60, 0x13: 0x60, 0x16: 0x60, 0x17: 0x61,
           0x11: 0x62, 0x12: 0x62, 0x14: 0x62, 0x15: 0x62, 0x18: 0x62,
           0x19: 0x62, 0x20: 0x62}
LIE_FLAT = (0x5C, 0x86, 0x88, 0x8D, 0x8F)   # 0x62 brings these to an X angle of 0
GOLD_TYPE = 0x95


def drop_object(d, kind):
    """The object a drop makes: spawn_thing's, or spawn_gold's for the gold.
    `d` is tools/ai.py's drop, `kind` the type row's +1."""
    o = {"type": d["type"], "pos": list(d["pos"]), "angles": [0, d["yaw"], 0],
         "state": 0, "vel": 0, "rest": 0, "amount": d["amount"]}
    if d["type"] == GOLD_TYPE:
        o["op"], o["vel"] = 0x62, -0x78          # and +0x2a left at 0
    else:
        o["op"] = DROP_OP.get(kind, 0xFF)
        if o["op"] == 0x62 and d["type"] not in LIE_FLAT:
            o["rest"] = 0x400
    return o


def approach_angle(a, b, step):
    """0x80015f18: a towards b by step the short way round, onto b when the
    step would pass it -- read branch by branch, delay slots included."""
    a &= 0xFFF
    b &= 0xFFF
    if a == b:
        return b
    if a < b:
        if b - a < 0x801:                        # up, without wrapping
            n = s16(a + step)
            return b if b < n else n
        n = (a - step) & 0xFFF                   # down through 0
        if n < 0x800:
            return n
        return n if b < n else b
    if a - b < 0x801:                            # down, without wrapping
        n = s16(a - step)
        return b if n < b else n
    n = (a + step) & 0xFFF                       # up through 0xfff
    if n >= 0x801:
        return n
    return n if n < b else b


def fall_step(o, floor):
    """One frame of opcodes 0x60, 0x61 and 0x62 (0x8004b228, 0x8004b300,
    0x8004b388) on `o` -- state, y (pos[1]), the vertical velocity +0x3e, the
    angles -- `floor` what collide_surface answers under it."""
    op, st = o["op"], o["state"]
    p, ang = o["pos"], o["angles"]
    if op == 0x60:
        if st == 0:
            p[1] += o["vel"]
            o["vel"] = s16(o["vel"] + 0x14)
            if p[1] < floor:
                return
            p[1], o["vel"], o["state"] = floor, 0x10, 1
        elif st == 1:
            ang[0] = (ang[0] + o["vel"]) & 0xFFFF
            o["vel"] = s16(o["vel"] + 0x10)
            if s16(ang[0]) < 0x400:
                return
            ang[0], o["state"] = 0x400, 0x63
    elif op == 0x61:
        if st == 0:
            p[1] += 0x14
            ang[1] = (ang[1] + 0x100) & 0xFFF
            if p[1] < floor:
                return
            p[1], o["state"] = floor, 0x63
    elif op == 0x62:
        if st < 2:
            p[1] += o["vel"]
            ang[0] = (ang[0] + (0xA0 if st == 0 else -0xA0)) & 0xFFF
            o["vel"] = s16(o["vel"] + 0x1E)
            if o["vel"] < 0 or p[1] < floor:
                return
            if o["vel"] < 0x50:
                p[1], o["state"] = floor, 2
            else:
                o["vel"] = -(o["vel"] >> 1)
                o["state"] = 1 if st == 0 else 0
        elif st == 2:
            ang[0] = approach_angle(ang[0], o["rest"], 0xA0) & 0xFFFF
            if s16(ang[0]) == s16(o["rest"]):
                o["state"] = 0x63


def fall_path(op, drop=0x600, vel=0, rest=0, frames=120):
    """[(state, y, vel, x angle, yaw)] of a fall from `drop` above a flat floor
    at 0, for godot/selftest.gd."""
    o = {"op": op, "state": 0, "pos": [0, -drop, 0], "angles": [0, 0, 0],
         "vel": vel, "rest": rest}
    out = []
    for _ in range(frames):
        fall_step(o, 0)
        out.append((o["state"], o["pos"][1], o["vel"], o["angles"][0], o["angles"][1]))
        if o["state"] == 0x63:
            break
    return out


# -- against the game ----------------------------------------------------

def snapshot_chests():
    """[(snapshot, slot, op, state, angle, counter, vel, lock, contents,
    (contents' +0, +0x38, type))] for every chest a snapshot holds."""
    import objload
    ot, rec = objload.OBJECT_TABLE & 0x1FFFFF, objload.REC
    out = []
    for path, lv in objload.snapshots():
        ram = open(path, "rb").read()
        for s in range(396):
            b = ot + s * rec
            if ram[b + 4] not in (6, 7):
                continue
            st, ctr = struct.unpack_from("<HH", ram, b + 8)
            ang = struct.unpack_from("<h", ram, b + 0x24)[0]
            vel = struct.unpack_from("<h", ram, b + 0x40)[0]
            cont = struct.unpack_from("<H", ram, b + 0x3A)[0]
            cb = ot + cont * rec if cont < 396 else None
            cinfo = ((ram[cb], ram[cb + 0x38], struct.unpack_from("<H", ram, cb + 6)[0])
                     if cb is not None else None)
            out.append((os.path.basename(path), lv, s, ram[b + 4], st, ang & 0xFFF,
                        ctr, vel, ram[b + 0x38], cont, cinfo))
    return out


KEY_ITEMS = (135, 137, 138, 139, 140, 142, 144)   # use_item's arm at 0x8005d188
LOCK_OPS = (6, 7, 8, 0x17, 0x18, 0x1A)             # the lock asked whatever the state
STILL_OPS = (0, 1, 2, 3, 4, 5, 0x1B)               # asked while the state (+8) is 0
WRONG_OPS = (0xF, 0x11, 0xA7)                      # wrong whatever the key
ORLADIN_KEY, ORLADIN_LOCK = 136, 0xA2              # 0x8005d300's own lock, by type


def key_test(op, state, lock, key):
    """`0x80046608`: (what it returns, the lock after) for a key tried on an
    object of opcode `op`, state (+8) `state` and lock (+0x38) `lock`."""
    if op in WRONG_OPS:
        return 4, lock
    if op in STILL_OPS and state != 0:
        return 0, lock
    if op not in LOCK_OPS and op not in STILL_OPS:
        return 0, lock
    if lock >= 0xFE:
        return 2, lock
    if lock != key:
        return 3, lock
    return 1, LOCK_FREE


def locks(levels=range(28)):
    """[(level, slot, type, opcode, lock)] of every object on the disc whose
    lock a key is asked about and is not already open."""
    import objload
    out = []
    for lv in levels:
        load = objload.Load(lv)
        for slot, r in sorted(load.recs.items()):
            if r["type"] == 0xFF:
                continue
            if r["op"] in WRONG_OPS or ((r["op"] in LOCK_OPS or r["op"] in STILL_OPS)
                                        and r["tail"][0] < 0xFE):
                out.append((lv, slot, r["type"], r["op"], r["tail"][0]))
    return out


def item_name(e, n):
    """An item's name off its 24-byte row of glyphs (a..z 0..25, 0x7f a
    space, 0x32 an apostrophe, 0xff the end)."""
    import ui
    s = ""
    for g in e.bytes(ui.NAMES + 24 * n, 24):
        if g == 0xFF:
            break
        s += chr(97 + g) if g < 26 else " " if g == 0x7F else "'" if g == 0x32 else "?"
    return s


def key_report(out=sys.stdout):
    import ui
    e = ui.exe()
    name = lambda n: item_name(e, n)                                  # noqa: E731
    for lv, slot, typ, op, lock in locks():
        if op in WRONG_OPS:
            what = "no key: wrong whatever is tried"
        elif typ == ORLADIN_LOCK and lock == ORLADIN_KEY:
            # use_item's arm for it (0x8005d300) asks the type before the test
            what = f"the {name(lock)} ({lock}), by its own arm: opened at once, the key spent"
        elif lock in KEY_ITEMS:
            what = f"the {name(lock)} ({lock})"
        else:
            what = f"no key: lock {lock}, \"Wrong key!\" to any"
        print(f"  level {lv:2d} slot {slot:3d} type {typ:3d} opcode {op:#04x}: {what}",
              file=out)


def key_cases():
    """[op, state, lock, key, result, lock after] for every opcode the test
    tells apart, both states and every lock on the disc, under each key."""
    ops = sorted(set(LOCK_OPS) | set(STILL_OPS) | set(WRONG_OPS)
                 | {9, 0xE, 0x10, 0x12, 0x16, 0x19, 0x1C, 0xA6, 0xA8, 0xFF})
    lock_set = sorted({lk for *_x, lk in locks()} | {0xFD, 0xFE, 0xFF})
    cases = []
    for op in ops:
        for state in (0, 1):
            for lock in lock_set:
                for key in KEY_ITEMS + (136, 141):
                    got, after = key_test(op, state, lock, key)
                    cases.append([op, state, lock, key, got, after])
    return cases


SILVIERA_KEY, PEDESTAL = 141, 0x101
KEY_RING, KEY_RING_SIZE = 380, 16       # pedestal_put_key's find_free_slot(0x17c, 0x10)
KEY_START, KEY_END = (0, -0x600, 0x190), (0, -0x500, 0)   # 0x8009c318, 0x8009c320
KEY_FRAMES = 20                         # the arm's last argument to object_use_state
KEY_OP, AT_REST, NO_KEY = 0x70, 0x63, 0xFF


def put_key(p, item, ring):
    """use_item's arm for Silviera's key (0x8005d244) on a type-0x101
    pedestal whose lock is 0xff, and pedestal_put_key (0x8005c7e8): the lock
    the key's number, the state 0, and the object in slot 380 + ring the
    key's type with +0x38 0 -- returned, as pedestal_step takes it."""
    p["lock"], p["state"], p["ring"] = item, 0, ring
    return {"type": item, "op": 0xFF, "lock": 0, "pos": [0, 0, 0],
            "angles": [0, 0, 0], "b0": 0, "b1": 0x80, "link": 0}


def use_state(p, key):
    """object_use_state (0x80046914) as opcode 0x18's arm calls it, with
    (0x8009c318, 0x8009c320, 0, 20). At state 0 with a lock other than 0xff
    the key is set up -- init_object_record, opcode 0x70, the pedestal's +0,
    +1 0x80, the pedestal's slot at its +0x40 and its yaw at +0x26 -- the
    count (+0x40) 19 if the key's +0x38 is not 0, else 0, and state 1; and
    in the same call, as at state 1, the count goes up and the key stands at
    the pedestal plus fixed_madd from (0, -0x600, 0x190) to (0, -0x500, 0),
    both turned by the pedestal's angles, count / 20 of the way. At 20: a
    sound (0x12), the key's +0x38 0xff -- free to take -- the state 0x63, and
    True."""
    if p["state"] == 0:
        if p["lock"] == 0xFF:
            return False
        p["n"] = KEY_FRAMES - 1 if key["lock"] != 0 else 0
        p["state"] = 1
        key.update({"op": KEY_OP, "b0": p["b0"], "b1": 0x80, "link": p["slot"],
                    "angles": [0, p["angles"][1], 0]})
    if p["state"] != 1:
        return False
    p["n"] = (p["n"] + 1) & 0xFF
    t = (p["n"] << 12) // KEY_FRAMES
    a = weapon.vec_rotate(p["angles"], KEY_START)
    b = weapon.vec_rotate(p["angles"], KEY_END)
    key["pos"] = [lerp(a[i], b[i], t) + p["pos"][i] for i in range(3)]
    if p["n"] < KEY_FRAMES:
        return False
    key["lock"] = 0xFF
    p["state"] = AT_REST
    return True


def pedestal_step(p, key, gate):
    """One frame of opcode 0x18's arm (0x8004aeb8): the pedestal `p` (slot,
    state, lock, ring, n, pos, angles, b0, tail), its key -- the object in
    slot 380 + its ring -- and the object its tail[3] names, `gate` (lock).
    A pedestal not at state 0 whose key is gone (taken: the type 0xff) goes
    back to state 0 with the lock 0xff, and the gate loses its mask (tail[5],
    or tail[2] when that is 0xff); then use_state, and on the frame the key
    comes to rest the gate's lock takes tail[2]. True on that frame."""
    t = p["tail"]
    if p["state"] != 0 and key is not None and key["type"] == NO_KEY:
        p["lock"], p["state"] = 0xFF, 0
        gate["lock"] &= ~(t[5] if t[5] != 0xFF else t[2]) & 0xFF
    if key is None or not use_state(p, key):
        return False
    gate["lock"] |= t[2]
    return True


def pedestal_run(p, gate, item=SILVIERA_KEY, ring=0, frames=KEY_FRAMES + 2):
    """The key put on `p` and the frames after, as [(state, n, key x, y, z,
    the key's +0x38, the gate's lock)]."""
    key = put_key(p, item, ring)
    rows = []
    for _ in range(frames):
        pedestal_step(p, key, gate)
        rows.append((p["state"], p["n"], *key["pos"], key["lock"], gate["lock"]))
    return rows, key


def check_pedestal(out=sys.stdout, before="silv1", after="silv2"):
    """use_item's arm for Silviera's key (0x8005d244) on a pedestal, against a
    snapshot before and one after: the pedestal's lock 0xff becomes the key,
    the key leaves the pack, and pedestal_put_key (0x8005c7e8) puts it in the
    ring of slots 380..395 -- the new object of the key's type, its +0x40 the
    pedestal's slot, the pedestal's +0x39 the ring index -- standing on it."""
    paths = [os.path.join(ROOT, "out", "snap", n + ".ram") for n in (before, after)]
    if not all(os.path.exists(p) for p in paths):
        return True
    import objload
    a, b = (open(p, "rb").read() for p in paths)
    ot, rec = objload.OBJECT_TABLE & 0x1FFFFF, objload.REC

    def obj(r, k):
        o = r[ot + k * rec:ot + (k + 1) * rec]
        return {"type": struct.unpack_from("<H", o, 6)[0], "op": o[4],
                "state": struct.unpack_from("<H", o, 8)[0], "lock": o[0x38],
                "ring": o[0x39], "x": struct.unpack_from("<i", o, 0x14)[0],
                "y": struct.unpack_from("<i", o, 0x18)[0],
                "z": struct.unpack_from("<i", o, 0x1C)[0], "link": o[0x40]}
    pedestals = [k for k in range(396) if obj(b, k)["type"] == PEDESTAL
                 and obj(a, k)["lock"] == 0xFF and obj(b, k)["lock"] == SILVIERA_KEY]
    def full(r, k):
        o = obj(r, k)
        raw = r[ot + k * rec:ot + (k + 1) * rec]
        o.update({"b0": raw[0], "b1": raw[1], "tail": list(raw[0x38:0x40]),
                  "angles": list(struct.unpack_from("<3h", raw, 0x24)),
                  "scale": list(struct.unpack_from("<3h", raw, 0x2C)),
                  "n": raw[0x40]})
        return o
    claims = []
    have = (a[0xC85E8 + SILVIERA_KEY], b[0xC85E8 + SILVIERA_KEY])    # inventory_a
    claims.append(("the key leaves the pack", have[1] == have[0] - 1))
    claims.append(("one pedestal's lock goes from 0xff to the key", len(pedestals) == 1))
    if pedestals:
        k = pedestals[0]
        p = obj(b, k)
        slot = KEY_RING + p["ring"]
        o = obj(b, slot)
        claims += [
            ("its +0x39 is a place in the ring of 16", p["ring"] < KEY_RING_SIZE),
            ("the object there has the key's type", o["type"] == SILVIERA_KEY),
            ("and was free before", obj(a, slot)["type"] == 0xFF),
            ("its +0x40 is the pedestal's slot", o["link"] == k),
            ("it stands on the pedestal", (o["x"], o["z"]) == (p["x"], p["z"]) and o["y"] < p["y"]),
        ]
        # and the 20 frames after, from silv1's pedestal and gate: opcode
        # 0x18's arm with object_use_state, against silv2
        p0, p1 = full(a, k), full(b, k)
        g0, g1 = full(a, p0["tail"][3]), full(b, p0["tail"][3])
        ped = {"slot": k, "state": p0["state"], "lock": p0["lock"], "ring": p0["ring"],
               "n": p0["n"], "pos": [p0["x"], p0["y"], p0["z"]], "angles": p0["angles"],
               "b0": p0["b0"], "tail": p0["tail"]}
        gate = {"lock": g0["lock"]}
        _rows, key = pedestal_run(ped, gate, SILVIERA_KEY, p["ring"])
        k1 = full(b, slot)
        claims += [
            ("the pedestal at rest (0x63), its count at 20",
             (ped["state"], ped["n"]) == (p1["state"], p1["n"]) == (AT_REST, KEY_FRAMES)),
            ("the key where object_use_state leaves it",
             key["pos"] == [k1["x"], k1["y"], k1["z"]]),
            ("its angles the pedestal's, its scale 0x1000",
             key["angles"] == k1["angles"] and k1["scale"] == [0x1000] * 3),
            ("its +0 the pedestal's, +1 0x80, opcode 0x70",
             (key["b0"], key["b1"], key["op"]) == (k1["b0"], k1["b1"], k1["op"])),
            ("free to take: its +0x38 0xff", key["lock"] == k1["lock"] == 0xFF),
            ("the gate's lock with the pedestal's mask",
             gate["lock"] == g1["lock"] and g1["lock"] != g0["lock"]),
        ]
    ok = sum(1 for _w, c in claims if c)
    for what, c in claims:
        if not c:
            print(f"  {before} -> {after}: not so: {what}", file=out)
    print(f"  {ok} of {len(claims)} of what Silviera's key does to a pedestal hold "
          f"between {before} and {after}"
          + (f" (slot {pedestals[0]}, the key put in slot {KEY_RING + obj(b, pedestals[0])['ring']})"
             if pedestals else ""), file=out)
    return ok == len(claims)


PEDESTAL_LINE = None


def pedestal_lines(path=None):
    """emu/bp27.lua's P lines: a pedestal each time it changes -- its state,
    lock, ring place, count, its key (opcode, type, +0x38, x, y, z) and the
    lock of the object it serves."""
    import re
    global PEDESTAL_LINE
    if PEDESTAL_LINE is None:
        PEDESTAL_LINE = re.compile(
            r"P vb=(\d+) lv=(\d+) slot=(\d+) st=(\d+) lock=(\d+) ring=(\d+) n=(\d+) "
            r"key=(\d+),(\d+),(\d+),(-?\d+),(-?\d+),(-?\d+) gate=(\d+),(\d+)")
    path = path or os.path.join(ROOT, "out", "lua_bp27.log")
    rows, session = [], 0
    if not os.path.exists(path):
        return rows
    for line in open(path):
        if line.startswith("=== bp27") and "armed" in line:
            session += 1
            continue
        m = PEDESTAL_LINE.match(line)
        if m:
            g = [int(x) for x in m.groups()]
            rows.append({"session": session, "vb": g[0], "lv": g[1], "slot": g[2],
                         "st": g[3], "lock": g[4], "ring": g[5], "n": g[6],
                         "key": {"op": g[7], "type": g[8], "lock": g[9],
                                 "pos": [g[10], g[11], g[12]]},
                         "gate": g[13], "gate_lock": g[14]})
    return rows


def pedestal_check(out=sys.stdout, verbose=False):
    """bp27's P lines against use_state: each line of a key on its way down or
    at rest holds the place the count puts it at, and the gate's lock has the
    pedestal's mask from the frame it comes to rest; a pedestal set back to 0
    has taken the mask away again."""
    rows = pedestal_lines()
    if not rows:
        print("  no pedestal lines in out/lua_bp27.log: ./emu/run.sh debug bp27.lua, "
              "put Silviera's key on a pedestal on level 4", file=out)
        return True
    import objload
    loads = {}
    ok = bad = 0
    last = {}
    for r in rows:
        if r["lv"] not in loads:
            loads[r["lv"]] = objload.Load(r["lv"])
        rec = loads[r["lv"]].recs.get(r["slot"])
        if rec is None:
            continue
        t = rec["tail"]
        claims = []
        if r["st"] in (1, AT_REST) and r["key"]["op"] == KEY_OP:
            n = r["n"]
            a = weapon.vec_rotate(rec["angles"], KEY_START)
            b = weapon.vec_rotate(rec["angles"], KEY_END)
            tt = (n << 12) // KEY_FRAMES
            want = [lerp(a[i], b[i], tt) + (rec["x"], rec["y"], rec["z"])[i] for i in range(3)]
            claims.append(("the key where the count puts it", r["key"]["pos"] == want))
            if r["st"] == AT_REST:
                claims.append(("at rest: the count 20 and the key free",
                               n == KEY_FRAMES and r["key"]["lock"] == 0xFF))
                claims.append(("the gate's lock has the mask", r["gate_lock"] & t[2] == t[2]))
        prev = last.get((r["session"], r["slot"]))
        if prev is not None and prev["st"] != 0 and r["st"] == 0:
            mask = t[5] if t[5] != 0xFF else t[2]
            claims.append(("set back: the lock 0xff and the mask gone from the gate",
                           r["lock"] == 0xFF and r["gate_lock"] & mask == 0))
        last[(r["session"], r["slot"])] = r
        for what, good in claims:
            ok += good
            bad += not good
            if verbose and not good:
                print(f"  level {r['lv']} pedestal {r['slot']} vb {r['vb']}: not so: {what}",
                      file=out)
    print(f"  {ok} of {ok + bad} of what bp27's pedestal lines say hold "
          f"({len(rows)} lines)", file=out)
    return bad == 0


PEDESTAL_PUT_KEY = 0x8005C7E8


def pedestal_game_runs(snap="silv1"):
    """The game's own code for a key put on a pedestal, run by
    tools/mipsrun.py over a level-4 snapshot taken before it, beside the
    model: use_item's part (the lock the key, the state 0), the game's
    pedestal_put_key, then the opcode-0x18 arm frame by frame -- with
    object_use_state, vec_rotate and its MVMVA -- and last the key taken (its
    type 0xff) for the reset. For pedestals 108 (a half turn), 192 (none) and
    110 (a quarter): [(slot, frames alike, frames)]."""
    import mipsrun
    path = os.path.join(ROOT, "out", "snap", snap + ".ram")
    if not os.path.exists(path):
        return []
    ram = open(path, "rb").read()
    out = []
    ot, stride = mipsrun.OBJECT_TABLE, mipsrun.OBJECT_STRIDE
    for slot in (108, 192, 110):
        cpu = mipsrun.object_cpu(ram)
        rec = ot + stride * slot
        if cpu.rd(rec + 0x38, 1) != 0xFF:
            continue
        raw = bytes(cpu.rd(rec + i, 1) for i in range(stride))
        ped = {"slot": slot, "state": 0, "lock": SILVIERA_KEY,
               "ring": 0xFF, "n": raw[0x40],
               "pos": list(struct.unpack_from("<3i", raw, 0x14)),
               "angles": list(struct.unpack_from("<3h", raw, 0x24)),
               "b0": raw[0], "tail": list(raw[0x38:0x40])}
        gslot = ped["tail"][3]
        grec = ot + stride * gslot
        gate = {"lock": cpu.rd(grec + 0x38, 1)}
        cpu.wr(rec + 0x38, 1, SILVIERA_KEY)          # use_item: the lock, the state
        cpu.wr(rec + 8, 2, 0)
        cpu.call(PEDESTAL_PUT_KEY, rec, SILVIERA_KEY)
        ring = cpu.rd(rec + 0x39, 1)
        key = put_key(ped, SILVIERA_KEY, ring)
        krec = ot + stride * (KEY_RING + ring)
        alike = n = 0
        for f in range(KEY_FRAMES + 4):
            if f == KEY_FRAMES + 3:                   # the key taken back
                cpu.wr(krec + 6, 2, NO_KEY)
                key["type"] = NO_KEY
            mipsrun.object_arm(cpu, slot)
            pedestal_step(ped, key, gate)
            game = (cpu.rd(rec + 8, 2), cpu.rd(rec + 0x38, 1), cpu.rd(rec + 0x40, 1),
                    [mipsrun.s32(cpu.rd(krec + 0x14 + 4 * i, 4)) for i in range(3)],
                    cpu.rd(krec + 4, 1), cpu.rd(krec + 0x38, 1), cpu.rd(krec + 0x40, 2),
                    [cpu.rd(krec + 0x24 + 2 * i, 2) for i in range(3)],
                    cpu.rd(grec + 0x38, 1))
            model = (ped["state"], ped["lock"], ped["n"], key["pos"], key["op"],
                     key["lock"], key["link"], [a & 0xFFFF for a in key["angles"]],
                     gate["lock"])
            n += 1
            alike += game == model
        out.append((slot, alike, n))
    return out


def pedestal_game_check(out=sys.stdout):
    """pedestal_game_runs, counted."""
    runs = pedestal_game_runs()
    if not runs:
        return True
    alike = sum(r[1] for r in runs)
    n = sum(r[2] for r in runs)
    print(f"  {alike} of {n} frames of the game's own pedestal arm and object_use_state, "
          f"run over silv1 by tools/mipsrun.py from its own pedestal_put_key, are "
          f"pedestal_step's -- the pedestal's state, lock and count, the key's place, "
          f"opcode, +0x38, +0x40 and angles, the gate's lock; pedestals "
          f"{', '.join(str(r[0]) for r in runs)}, each to rest and then the key taken",
          file=out)
    return alike == n


def check(out=sys.stdout, verbose=False):
    """The lid's path against every chest the snapshots caught after USE:
    one still moving has to be a frame of it, one at rest its end, and what
    is inside present and free to take from the frame the path says."""
    path = lid_cycle()
    seen = {(a, v): i for i, (_s, a, v, _p, _f) in enumerate(path)}
    ok = bad = 0
    for snap, lv, slot, op, st, ang, ctr, vel, lock, cont, cinfo in snapshot_chests():
        if op != 6 or lock != OPENED:
            continue
        if st == 2:
            i = seen.get((ang, vel))
            good = i is not None and cinfo is not None and cinfo[0] == 2 \
                and (cinfo[1] == 0xFF) == bool(path[i][4])
            what = f"moving: angle {ang:#x}, velocity {vel}, frame {i} of the path"
        else:
            good = st == 3 and ang == LID_OPEN and vel == 0
            what = f"at rest: angle {ang:#x}, velocity {vel}"
        if cinfo is not None:
            what += (f"; inside, slot {cont}: +0 {cinfo[0]}, +0x38 {cinfo[1]:#x}, "
                     f"type {cinfo[2]:#x}")
        ok += good
        bad += not good
        if verbose or not good:
            print(f"  {snap} level {lv} slot {slot}: {what} -- "
                  f"{'agrees' if good else 'DIFFERS'}", file=out)
    print(f"  {ok} of {ok + bad} opened lids in the snapshots on the path "
          f"tools/chests.py takes ({len(path)} frames from USE to rest)", file=out)
    lying = check_drops(out, verbose)
    put = check_pedestal(out)
    held = pedestal_check(out, verbose)
    ran = pedestal_game_check(out)
    return bad == 0 and lying and put and held and ran


def check_drops(out=sys.stdout, verbose=False):
    """The things lying in the drop rings of the snapshots (slots 350..379),
    at rest: the velocity each keeps is the last of its fall, which the fall
    from half a level-0 creature's height gives -- gold from -0x78, a thing
    from 0 -- if the creature stood on the floor the thing lands on. Which
    creature it was the snapshot does not say, so any kind will do."""
    import json
    import objload
    kinds = json.load(open(os.path.join(ROOT, "out", "godot", "ai00.json")))["kinds"]
    heights = sorted({kd["height"] for kd in kinds.values()})
    ot, rec = objload.OBJECT_TABLE & 0x1FFFFF, objload.REC
    seen, ok, bad = set(), 0, 0
    for path, lv in objload.snapshots():
        if lv != 0:
            continue
        ram = open(path, "rb").read()
        for slot in range(350, 380):
            b = ot + slot * rec
            if ram[b + 4] != 0x62 or struct.unpack_from("<H", ram, b + 8)[0] != 0x63:
                continue
            vel = struct.unpack_from("<h", ram, b + 0x3E)[0]
            xa = struct.unpack_from("<h", ram, b + 0x24)[0]
            key = (slot, struct.unpack_from("<i", ram, b + 0x14)[0], vel)
            if key in seen:
                continue
            seen.add(key)
            v0 = -0x78 if slot < 360 else 0
            fits = [h for h in heights
                    if fall_path(0x62, h >> 1, v0, 0)[-1][2] == vel]
            good = bool(fits) and xa == 0
            ok += good
            bad += not good
            if verbose or not good:
                print(f"  {os.path.basename(path)} slot {slot}: at rest, velocity {vel}, "
                      f"X angle {xa} -- the fall from half of height {fits} "
                      f"{'gives it' if good else 'does not'}", file=out)
    print(f"  {ok} of {ok + bad} things lying in the drop rings rest as a fall "
          f"from half a creature's height leaves them", file=out)
    return bad == 0


def export(out_dir):
    """chestcheck.json: the lid's and the big chest's frames, and two
    flights of object_give, for godot/selftest.gd."""
    import json
    flights = []
    for take, press in ((True, 14), (False, 12), (True, 5)):
        args = {"pos": [49672, -9182, 7680], "angles": [2304, 1024, 1024],
                "c": 80, "e": -300, "player": [48000, -8832, 7500],
                "pitch": 0x7c0, "facing": 0x3a0, "press": press, "take": take}
        frames = give_frames(args["pos"], args["angles"], args["c"], args["e"],
                             args["player"], args["pitch"], args["facing"],
                             press, take)
        flights.append({"args": args, "frames": [list(f) for f in frames]})
    falls = []
    for op, drop, vel, rest in ((0x60, 0x600, 0, 0), (0x61, 0x600, 0, 0),
                                (0x62, 812, -0x78, 0), (0x62, 812, 0, 0x400),
                                (0x62, 2000, -0x78, 0)):
        falls.append({"op": op, "drop": drop, "vel": vel, "rest": rest,
                      "frames": [list(f) for f in fall_path(op, drop, vel, rest)]})
    # level 4's pedestal 108 (cell (33,23)), turned 0x800, and one at no
    # turn, each to rest and then the key taken back: the reset
    pedestals = []
    for pos, ang, tail in (([68072, -14080, 48000], [0, 2048, 0], [255, 255, 2, 91, 255, 2, 255, 255]),
                           ([60952, -14080, 50304], [0, 0, 0], [255, 255, 1, 91, 255, 1, 255, 255]),
                           ([12000, -18688, 133000], [0, 1024, 0], [255, 255, 3, 92, 255, 255, 255, 255])):
        ped = {"slot": 108, "state": 0, "lock": 0xFF, "ring": 0xFF, "n": 0xFF, "pos": pos,
               "angles": ang, "b0": 2, "tail": tail}
        gate = {"lock": 0xFC}
        rows, key = pedestal_run(ped, gate)
        key["type"] = NO_KEY                      # taken back
        pedestal_step(ped, key, gate)
        rows.append((ped["state"], ped["n"], *key["pos"], ped["lock"], gate["lock"]))
        pedestals.append({"pos": pos, "angles": ang, "tail": tail,
                          "frames": [list(r) for r in rows]})
    doc = {"lid": [list(r) for r in lid_cycle()],
           "big": [list(r) for r in big_cycle()], "flights": flights,
           "falls": falls, "keys": key_cases(), "pedestals": pedestals}
    path = os.path.join(out_dir, "chestcheck.json")
    with open(path, "w") as fh:
        json.dump(doc, fh, separators=(",", ":"))
    return path


if __name__ == "__main__":
    if "--keys" in sys.argv:
        key_report()
        sys.exit(0)
    sys.exit(0 if check(verbose="--check" not in sys.argv) else 1)
