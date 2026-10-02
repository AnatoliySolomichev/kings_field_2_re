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
    doc = {"lid": [list(r) for r in lid_cycle()],
           "big": [list(r) for r in big_cycle()], "flights": flights}
    path = os.path.join(out_dir, "chestcheck.json")
    with open(path, "w") as fh:
        json.dump(doc, fh, separators=(",", ":"))
    return path


if __name__ == "__main__":
    sys.exit(0 if check(verbose="--check" not in sys.argv) else 1)
