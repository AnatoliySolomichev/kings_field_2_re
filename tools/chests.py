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
    return bad == 0 and lying


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
    doc = {"lid": [list(r) for r in lid_cycle()],
           "big": [list(r) for r in big_cycle()], "flights": flights,
           "falls": falls, "keys": key_cases()}
    path = os.path.join(out_dir, "chestcheck.json")
    with open(path, "w") as fh:
        json.dump(doc, fh, separators=(",", ":"))
    return path


if __name__ == "__main__":
    if "--keys" in sys.argv:
        key_report()
        sys.exit(0)
    sys.exit(0 if check(verbose="--check" not in sys.argv) else 1)
