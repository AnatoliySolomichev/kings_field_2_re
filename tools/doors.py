#!/usr/bin/env python3
"""The swinging door's arm, and the recording it is checked against.

    python3 tools/doors.py            the checks, with the frames that differ
    python3 tools/doors.py --check    the checks alone

The swinging doors against emu/bp24.lua, and the lift doors (opcodes 3 to 5,
lift_step) and the gates (opcode 2, gate_step) against emu/bp27.lua.

`object_interpreter`'s arm for opcode 1 (`0x8004814c`) runs once a frame for
every class-1 door, and `godot/doors.gd` is its port; this is the same arm in
Python so that `emu/bp24.lua`'s recording can hold it to account. bp24 stops at
the head of the arm, so each line is the door **before** that frame's step:
its state (+8), counter (+0x40), yaw (+0x26), and the player's position -- the
one the arm sees, since `game_main` runs `object_interpreter` before
`player_controller` -- and the collision shape of the doorway's two cells,
which the stamps change. Locked replay: take the logged door, run one step with
the logged player, compare with the next line.

The step, as read (FORMATS.md, "A door that swings"):

    state 1          -> state 2, counter 0, the view yaw kept for the shove
    counter < 0x20   yaw += 0x20; at 0x18 stamp the open doorway (template
                     p[+0x13] + 0); at 0x1f jump the counter to 0x118
    counter 0x12c    stay while the player is within 0x5dc + 0x320 of the
                     point 0x400 along yaw0 (player_in_range, 0x80028e48),
                     else stamp the closed doorway (template + 2) and go on
    counter < 0x14c  yaw -= 0x20
    after            state 0
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import movement                                                      # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OPENING, STAMP_OPEN, LAST_SWING = 0x20, 0x18, 0x1F
WAIT_FROM, CLOSE_AT, DONE_AT = 0x118, 0x12C, 0x14C
SWING, CLEAR, PLAYER_R, PLAYER_BODY = 0x20, 0x5DC, 0x320, 0x6A4
MASK = 0x2D
LINE = re.compile(r"vb=(\d+) slot=(\d+) st=(\d+) ctr=(\d+) yaw=(-?\d+) "
                  r"yaw0=(-?\d+) side=(-?\d+) pos=(-?\d+) (-?\d+) (-?\d+) "
                  r"shapes=(-?\d+),(-?\d+)")


def doors(lv=0):
    """{slot: the loader's record} for every swinging door, and the loader."""
    import objload
    ld = objload.Load(lv)
    return {k: r for k, r in ld.recs.items() if r["op"] == 1}, ld


def step(d, player, grid_stamp):
    """One frame of the arm on `d` (state, counter, yaw, yaw0, x, y, z,
    height); `grid_stamp(shift)` lays a template down."""
    if d["state"] == 0:
        return
    if d["state"] == 1:
        d["state"], d["counter"] = 2, 0
    n = d["counter"]
    d["counter"] = n + 1
    if n < OPENING:
        d["yaw"] += SWING
        if n == STAMP_OPEN:
            grid_stamp(0)
        elif n == LAST_SWING:
            d["counter"] = WAIT_FROM
        return
    if n < CLOSE_AT:
        return
    if n < DONE_AT:
        if n == CLOSE_AT:
            a = d["yaw0"]
            qx = d["x"] + ((movement.game_cos(a) * 0x400) >> 12)
            qz = d["z"] + ((movement.game_sin(a) * 0x400) >> 12)
            if movement.in_range(player, qx, d["y"], qz, CLEAR + PLAYER_R,
                                 PLAYER_BODY, d["height"]) != -1:
                d["counter"] = CLOSE_AT
                return
            grid_stamp(2)
        d["yaw"] -= SWING
        return
    d["state"] = 0


# -- the doors that lift ----------------------------------------------------
#
# Opcodes 3, 4 and 5 are one arm written out three times (0x800470c4,
# 0x80047290, 0x80047444), each with its own pair of stamp_table tables -- the
# ones load_object_placement stamps shut at load (objload.DOOR_TABLES): the
# first sets the doorway's collision shape, the second its drawn tile. Both
# name two cells, the door's own and the one behind it, (0, 0) and (0, -1)
# turned by the yaw, and write layer 1 -- the drawn one -- when the record's
# b0 is not 1:
#
#   op 3   shape 0x81 shut, 0xb2 open (0x800828dc)   tile 0x7d (0x800828fc)
#   op 4   the same shapes                           tile 0x7f (0x8008291c)
#   op 5   shape 0xc1 shut, 0xdf open (0x8008293c)   tile 0x1a (0x8008295c)
#
# and the open tile is 0xfc, which draw_terrain does not draw. So a lift door is a
# piece of wall until it moves: the grid draws it, and the model only takes
# over while it moves or stands open.
LIFT_OPS = (3, 4, 5)
LIFT_RATE = 0x48          # the counter a frame, up and down
LIFT_PASSABLE = 0xC18     # the counter at which the doorway is stamped open
LIFT_OPEN = 0xFFF         # where it stops
LIFT_WAIT = 0x14          # the state it counts up to while standing open
LIFT_CLEAR = (0x700, 0xC80)   # collide_query's radius and height, flags 0xc0


def lift_stamps(ld, r):
    """(shape table, tile table), each [(cx, cz, the entry's 8 bytes)], for a
    lift door -- stamp_table's cells worked out once, as objload does them."""
    import objload
    c, s = movement.game_cos(r["angles"][1]), movement.game_sin(r["angles"][1])
    out = []
    for tb in objload.DOOR_TABLES[r["op"]]:
        rows, e = [], tb
        while ld.exe.bytes(e, 1)[0] != 0xFF:
            ent = ld.exe.bytes(e, 10)
            ddx, ddz = objload.s8(ent[8]), objload.s8(ent[9])
            rows.append((((ddx * c - ddz * s) >> 12) + (r["x"] >> 11),
                         ((ddz * c + ddx * s) >> 12) + (r["z"] >> 11),
                         bytes(ent[:8])))
            e += 10
        out.append(rows)
    return out


def lift_step(d, clear, stamp):
    """One frame of the arm (0x800470c4) on `d` (state, counter, scale);
    `clear()` is collide_query's answer about the doorway, `stamp(table, sel)`
    lays table 0 (the shape) or 1 (the tile) down at `sel`."""
    st = d["state"]
    if st == 0:
        return
    if st == 1:
        if d["counter"] == 0:
            stamp(1, 1)                        # the tile away: the model shows
            d["scale"] = 0x1000
        d["counter"] = (d["counter"] + LIFT_RATE) & 0xFFFF
        if d["counter"] == LIFT_PASSABLE:
            stamp(0, 1)
        if d["counter"] >= 0x1000:
            d["counter"], d["state"] = LIFT_OPEN, 2
        return
    if st == LIFT_WAIT:
        if clear():
            stamp(0, 0)                        # solid again, before it drops
            d["state"] = 0x15
        return
    if st == 0x15:
        d["counter"] = (d["counter"] - LIFT_RATE) & 0xFFFF
        if d["counter"] and d["counter"] < 0x8000:
            return
        stamp(1, 0)                            # the tile back, the model gone
        d["counter"] = d["state"] = d["scale"] = 0
        return
    d["state"] = (st + 1) & 0xFFFF


# The gates: opcode 2 (0x800475f8), level 4's walls. The same rise as a lift
# door -- 0x48 a frame, 0xfff, eighteen frames, the wait, the drop -- but
# stamp_rect lays the doorway down, from one of three templates a gate's width
# apart: the type row's +0xd cells from the record's p[+0x13] (the template's
# x, p[+0x14] its z) is "moving", that plus +0xd again "shut", the first "open".
# The model stands while shut and rises with the counter. A gate whose lock is
# odd and between 0x96 and 0xc6 opens of itself and never shuts; the others
# open to USE (object_interact's arm for classes 0 to 2: state 0, the lock
# 0xff, or 0xfd or 0xfe unless the type is 0xae) -- which the pedestals give
# them, a bit of the lock each.
GATE_OPS = (2,)
GATE_CLEAR = 0x1130       # collide_query's radius for the doorway
GATE_OPEN, GATE_MOVING, GATE_SHUT = 0, 1, 2      # the template, in gate widths


def gate_auto(lock):
    """0x80047644: a lock of 0x96..0xc6 (the byte plus 0x6a under 0x31)."""
    return ((lock + 0x6A) & 0xFF) < 0x31


def gate_step(d, clear, stamp):
    """One frame of opcode 2's arm (0x800475f8) on `d` (state, counter, lock);
    `clear()` answers collide_query(the gate, 0x1130, 0xc80, 0xc0), `stamp(k)`
    lays the template k gate-widths along down."""
    st = d["state"]
    if st == 0:
        if gate_auto(d["lock"]) and d["lock"] & 1:
            d["state"] = 1
        return
    if st == 1:
        if d["counter"] == 0:
            stamp(GATE_MOVING)
        d["counter"] = (d["counter"] + LIFT_RATE) & 0xFFFF
        if d["counter"] == LIFT_PASSABLE:
            stamp(GATE_OPEN)
        if d["counter"] >= 0x1000:
            d["counter"], d["state"] = LIFT_OPEN, 2
        return
    if st == LIFT_WAIT:
        if gate_auto(d["lock"]) and d["lock"] & 1:
            return                             # it opened itself; it stays so
        if clear():
            d["state"] = 0x15
            stamp(GATE_MOVING)
        return
    if st == 0x15:
        d["counter"] = (d["counter"] - LIFT_RATE) & 0xFFFF
        if d["counter"] and d["counter"] < 0x8000:
            return
        d["counter"] = d["state"] = 0
        stamp(GATE_SHUT)
        return
    d["state"] = (st + 1) & 0xFFFF


def gate_cycle(wait=0, lock=0xFF, frames=None):
    """A gate's run from USE as [(state, counter, the template last laid)],
    the doorway taken for `wait` frames of state 0x14."""
    d = {"state": 1, "counter": 0, "lock": lock}
    laid = [GATE_SHUT]
    held = [wait]
    rows = []

    def clear():
        if held[0] > 0:
            held[0] -= 1
            return False
        return True

    def stamp(k):
        laid[0] = k
    for _ in range(frames or 200):
        gate_step(d, clear, stamp)
        rows.append((d["state"], d["counter"], laid[0]))
        if d["state"] == 0:
            break
    return rows


def lift_clear(d, player, creatures=()):
    """collide_query(x, y, z, 0x700, 0xc80, 0xc0) is 0: no awake creature
    in_range of the doorway at its radius + 0x700 (actor_in_range, 0x8004d838)
    and the player not within 0x700 + 0x320 (player_in_range). The cell's
    occupancy count, which the query looks at first, needs no asking: the
    player marks every cell within 0x320 + 0x800 of itself and a creature
    within its radius + 0x800, which covers every point either can be in range
    from."""
    r, own = LIFT_CLEAR
    for a in creatures:
        if movement.in_range(a[:3], d["x"], d["y"], d["z"], a[3] + r, a[4],
                             own) != -1:
            return False
    return player is None or movement.in_range(
        player, d["x"], d["y"], d["z"], r + PLAYER_R, PLAYER_BODY, own) == -1


def lift_cycle(wait=0, frames=None):
    """A lift door's run from USE, as [(state, counter, scale, shape, tile)]
    after each frame, with the doorway taken for `wait` frames of state 0x14:
    the cases godot/selftest.gd holds doors.gd to."""
    d = {"state": 1, "counter": 0, "scale": 0}
    sel = [0, 0]
    rows = []
    held = [wait]

    def clear():
        if held[0] > 0:
            held[0] -= 1
            return False
        return True

    def stamp(t, v):
        sel[t] = v
    for _ in range(frames or 200):
        lift_step(d, clear, stamp)
        rows.append((d["state"], d["counter"], d["scale"], sel[0], sel[1]))
        if d["state"] == 0:
            break
    return rows


LIFT_LINE = re.compile(r"vb=(\d+) slot=(\d+) op=(\d+) st=(\d+) ctr=(\d+) "
                       r"scale=(\d+) pos=(-?\d+) (-?\d+) (-?\d+) "
                       r"cells=(-?\d+),(-?\d+) (-?\d+),(-?\d+)")


LIFT_QUERY = re.compile(r"Q vb=(\d+) slot=(\d+) op=\d+ mask=(\d+) actor=(-?\d+)"
                        r"(?: model=(\d+) st=(\d+) at=(-?\d+) (-?\d+) (-?\d+) "
                        r"r=(\d+) h=(\d+) flags=(-?\d+))?")


LIFT_ACTOR = re.compile(r"A vb=(\d+) slot=(\d+) actor=(\d+) model=(\d+) "
                        r"at=(-?\d+) (-?\d+) (-?\d+) r=(\d+) h=(\d+) flags=(-?\d+)")


def lift_load(path=None):
    """bp27's door lines, each with the doorway test's answer that frame when
    the log has one: q = (mask, the creature as [x, y, z, radius, height] or
    None)."""
    path = path or os.path.join(ROOT, "out", "lua_bp27.log")
    rows = []
    if not os.path.exists(path):
        return rows
    queries, near = {}, {}
    # A log can hold several sessions, one after another, each with its own
    # vertical-blank count from wherever the emulator was: a line belongs to
    # the session the last "armed" header began, and is matched only in it.
    session = 0
    for line in open(path):
        if line.startswith("=== bp27") and "armed" in line:
            session += 1
            continue
        m = LIFT_LINE.match(line)
        if m:
            g = [int(x) for x in m.groups()]
            rows.append({"session": session, "vb": g[0], "slot": g[1], "op": g[2],
                         "st": g[3], "ctr": g[4], "scale": g[5], "p": (g[6], g[7], g[8]),
                         "cells": ((g[9], g[10]), (g[11], g[12]))})
            continue
        m = LIFT_QUERY.match(line)
        if m:
            g = [None if x is None else int(x) for x in m.groups()]
            who = None if g[3] < 0 else [g[6], g[7], g[8], g[9], g[10]]
            queries[(session, g[0], g[1])] = (g[2], who)
            continue
        m = LIFT_ACTOR.match(line)
        if m:
            g = [int(x) for x in m.groups()]
            near.setdefault((session, g[0], g[1]), []).append(
                {"actor": g[2], "model": g[3], "pos": (g[4], g[5], g[6]),
                 "r": g[7], "h": g[8], "flags": g[9]})
    for r in rows:
        r["q"] = queries.get((r["session"], r["vb"], r["slot"]))
        r["near"] = near.get((r["session"], r["vb"], r["slot"]), [])
    return rows


def actor_in_range(near, d):
    """actor_in_range (0x8004d838) on bp27's A lines: the first awake creature,
    model 0x6e aside, in range of the door at its radius + 0x700, its height as
    the top and 0xc80 the door's. The skip mask is 0 in object_interpreter.
    Flags 0x10 and 0x400000 move the point it is asked at, and are not here."""
    for a in sorted(near, key=lambda a: a["actor"]):
        if a["model"] == 0x6E:
            continue
        if movement.in_range(a["pos"], d["x"], d["y"], d["z"], a["r"] + LIFT_CLEAR[0],
                             a["h"], LIFT_CLEAR[1]) != -1:
            return a
    return None


def lift_check(out=sys.stdout, verbose=False):
    """emu/bp27.lua's lines, a step at a time: the logged door and player
    through lift_step, against the next line of the same slot -- state,
    counter, scale, and the tile and shape of the door's two cells."""
    rows = lift_load()
    if not rows:
        print("  no out/lua_bp27.log: ./emu/run.sh debug bp27.lua, open a lift door",
              file=out)
        return True
    import objload
    ld = objload.Load(0)
    by = {}
    for r in rows:
        by.setdefault((r["session"], r["slot"]), []).append(r)
    ok = bad = used = unseen = held = freed = held_by = reopened = 0
    for (_session, slot), rs in sorted(by.items()):
        rec = ld.recs.get(slot)
        if rec is None or rec["op"] not in LIFT_OPS:
            continue
        tables = lift_stamps(ld, rec)
        # the entry's first shape and tile bytes go to layer 1 unless b0 is 1;
        # the log carries layer 1's tile and shape
        k1 = 0 if rec["b0"] != 1 else 1
        order = [(x, z) for x, z, _q in tables[0]]
        used += sum(1 for r in rs if r["st"] == 1 and r["ctr"] == 0)
        for a, b in zip(rs, rs[1:]):
            if a["st"] == 0:
                continue                        # USE, object_interact: not the arm
            d = {"state": a["st"], "counter": a["ctr"], "scale": a["scale"],
                 "x": rec["x"], "y": rec["y"], "z": rec["z"]}
            cells = {xz: list(v) for xz, v in zip(order, a["cells"])}

            def stamp(t, sel, cells=cells, tables=tables):
                for x, z, q in tables[t]:
                    c = cells.get((x, z))
                    if c is None:
                        continue
                    k = sel * 4 + k1
                    if q[k] != 0xFC:
                        c[1] = q[k]
                    if q[k + 2] != 0xFF:
                        c[0] = q[k + 2]
            # The creatures: collide_query's own bit 0x10 when the log has its
            # answer -- the slot it found is overwritten before it returns, so
            # that is all it can say -- the player by player_in_range here.
            if a["q"] is not None:
                by_creature = bool(a["q"][0] & 0x10)
                held_by += by_creature and a["st"] == LIFT_WAIT

                def clear(d=d, a=a, cr=by_creature):
                    return not cr and lift_clear(d, a["p"])
            else:
                def clear(d=d, a=a):
                    return lift_clear(d, a["p"])
            lift_step(d, clear, stamp)
            got = (d["state"], d["counter"], d["scale"],
                   tuple(tuple(cells[xz]) for xz in order))
            want = (b["st"], b["ctr"], b["scale"], b["cells"])
            if got == want:
                ok += 1
                if a["st"] == LIFT_WAIT:
                    held += b["st"] == LIFT_WAIT
                    freed += b["st"] == 0x15
            elif got[0] == 0 and b["st"] == 1 and got[1:] == want[1:]:
                # shut on this frame and opened again by USE before the next:
                # object_interact sets state 1 on a door at state 0, and the
                # arm's line the frame after shows it
                reopened += 1
            elif (a["st"] == b["st"] == LIFT_WAIT and a["q"] is None
                  and a["ctr"] == b["ctr"] and a["cells"] == b["cells"]):
                # The game held the doorway and the player was out of reach:
                # what collide_query's 0xc0 asks besides the player is the
                # creatures, and a log without Q lines does not carry them.
                unseen += 1
            else:
                bad += 1
                if verbose:
                    print(f"  slot {slot} vb {a['vb']}: model {got}, game {want}",
                          file=out)
    print(f"  {ok} of {ok + bad} steps of a lift door reproduced -- state, counter, "
          f"scale and its two cells' tile and shape; {used} lifts from USE, "
          f"{held} frames held, {freed} let go"
          + (f"; {reopened} shut and opened again by USE in the same frame"
             if reopened else ""),
          file=out)
    if held_by:
        print(f"  {held_by} of the waiting frames held by a creature by the game's "
              f"own answer (bit 0x10 of collide_query); which one, the A lines say "
              f"where the log has them (below)", file=out)
    if unseen:
        print(f"  {unseen} more at 0x14 where the game held the doorway with the "
              f"player out of reach: a creature, which a log without Q lines does "
              f"not carry", file=out)
    # The Q lines: collide_query's own answer. Its bit 0x80 is
    # player_in_range's, so it must say what lift_clear's player test says, frame
    # by frame; bit 0x10 is actor_in_range's, which overwrites the creature's
    # slot with -1 before it returns (0x800340a8), so the log cannot name it.
    pq = pbad = creature = listed = agree = 0
    holders = {}
    for r in rows:
        if r["q"] is None or r["slot"] not in ld.recs:
            continue
        d = ld.recs[r["slot"]]
        mask = r["q"][0]
        near = movement.in_range(r["p"], d["x"], d["y"], d["z"],
                                 LIFT_CLEAR[0] + PLAYER_R, PLAYER_BODY,
                                 LIFT_CLEAR[1]) != -1
        pq += 1
        if near != bool(mask & 0x80):
            pbad += 1
            if verbose:
                print(f"  slot {r['slot']} vb {r['vb']}: player {r['p']}, the game "
                      f"says {mask:#x}", file=out)
        creature += bool(mask & 0x10)
        if r["near"] or mask & 0x10:
            named = actor_in_range(r["near"], d)
            if r["near"]:
                listed += 1
                agree += bool(named) == bool(mask & 0x10)
                if named:
                    holders[(named["actor"], named["model"])] = \
                        holders.get((named["actor"], named["model"]), 0) + 1
    if listed:
        print(f"  {agree} of {listed} answers with the creatures listed: actor_in_range "
              f"on them finds one exactly when the game's bit 0x10 is set; held by "
              + ", ".join(f"slot {k} (model {m}) {n} times"
                          for (k, m), n in sorted(holders.items())), file=out)
    if pq:
        print(f"  {pq - pbad} of {pq} of the game's doorway answers have the player "
              f"in reach exactly when player_in_range does; {creature} also "
              f"name a creature", file=out)
    return bad == 0 and pbad == 0


def export(out_dir):
    """liftcheck.json: lift_cycle's frames for godot/selftest.gd, a door let
    shut at once and one kept open by something in its doorway."""
    import json
    runs = [{"wait": w, "frames": [list(f) for f in lift_cycle(w)]}
            for w in (0, 7)]
    gates = [{"wait": w, "lock": lk, "frames": [list(f) for f in gate_cycle(w, lk, 120)]}
             for w, lk in ((0, 0xFF), (9, 0xFE), (0, 0x97))]
    path = os.path.join(out_dir, "liftcheck.json")
    with open(path, "w") as fh:
        json.dump({"runs": runs, "gates": gates}, fh, separators=(",", ":"))
    return path


def load(path=None):
    path = path or os.path.join(ROOT, "out", "lua_bp24.log")
    rows = []
    if not os.path.exists(path):
        return rows
    for line in open(path):
        m = LINE.match(line)
        if m:
            g = [int(x) for x in m.groups()]
            rows.append({"vb": g[0], "slot": g[1], "st": g[2], "ctr": g[3],
                         "yaw": g[4], "yaw0": g[5], "p": (g[7], g[8], g[9]),
                         "shapes": (g[10], g[11])})
    return rows


def check(out=sys.stdout, verbose=False):
    rows = load()
    if not rows:
        print("  no out/lua_bp24.log: ./emu/run.sh debug bp24.lua, open a door",
              file=out)
        return True
    recs, ld = doors(0)
    by = {}
    for r in rows:
        by.setdefault(r["slot"], []).append(r)
    ok = bad = moving = used = 0
    for slot, rs in sorted(by.items()):
        rec = recs.get(slot)
        if rec is None:
            continue
        tail = rec["tail"]
        tr = ld.rows[rec["type"]]
        dx, dz = tail[1], tail[2]
        grid = bytearray(ld.grid)

        def stamp(shift, grid=grid):
            ld.grid, keep = grid, ld.grid
            ld.stamp_rect(rec["b0"], tail[3] + shift, tail[4], dx, dz,
                          tr[0xD], tr[0xE], rec["angles"][1], MASK)
            ld.grid = keep

        def shapes(grid=grid):
            return tuple(grid[((dz + i) * 80 + dx) * 10 + 8] for i in (0, 1))
        for a, b in zip(rs, rs[1:]):
            if a["st"] == 0 and b["st"] == 0:
                continue
            if a["st"] == 0 and b["st"] == 1:
                used += 1                      # object_interact, on USE: not the arm
                continue
            moving += 1
            d = {"state": a["st"], "counter": a["ctr"], "yaw": a["yaw"],
                 "yaw0": a["yaw0"], "x": rec["x"], "y": rec["y"], "z": rec["z"],
                 "height": rec["height"]}
            if a["shapes"] != shapes():
                # take the game's doorway as the starting point
                for i, sh in enumerate(a["shapes"]):
                    grid[((dz + i) * 80 + dx) * 10 + 8] = sh
            step(d, a["p"], stamp)
            got = (d["state"], d["counter"], d["yaw"], shapes())
            want = (b["st"], b["ctr"], b["yaw"], b["shapes"])
            if got == want:
                ok += 1
            else:
                bad += 1
                if verbose:
                    print(f"  slot {slot} vb {a['vb']}: model {got}, game {want}",
                          file=out)
    print(f"  {ok} of {ok + bad} steps of a moving door reproduced -- state, "
          f"counter, yaw and the doorway's two shapes; opened {used} times by "
          f"USE", file=out)
    return bad == 0


GATE_LINE = re.compile(r"G vb=(\d+) lv=(\d+) slot=(\d+) st=(\d+) ctr=(\d+) "
                       r"lock=(\d+) pos=(-?\d+) (-?\d+) (-?\d+) cells=([\d,]*)")
GATE_QUERY = re.compile(r"GQ vb=(\d+) slot=(\d+) mask=(\d+)")
FENCE = 1000                 # bp27 adds it to a cell's shape when +9 has 0x40


def gate_load(path=None):
    """bp27's G lines, each with the doorway test's mask that frame (its GQ
    line) or None."""
    path = path or os.path.join(ROOT, "out", "lua_bp27.log")
    rows, queries = [], {}
    if not os.path.exists(path):
        return rows
    session = 0
    for line in open(path):
        if line.startswith("=== bp27") and "armed" in line:
            session += 1
            continue
        m = GATE_LINE.match(line)
        if m:
            g = m.groups()
            rows.append({"session": session, "vb": int(g[0]), "lv": int(g[1]),
                         "slot": int(g[2]), "st": int(g[3]), "ctr": int(g[4]),
                         "lock": int(g[5]), "p": tuple(int(x) for x in g[6:9]),
                         "cells": tuple(int(x) for x in g[9].split(",") if x)})
            continue
        m = GATE_QUERY.match(line)
        if m:
            queries[(session, int(m.group(1)), int(m.group(2)))] = int(m.group(3))
    for r in rows:
        r["q"] = queries.get((r["session"], r["vb"], r["slot"]))
    return rows


def doorway(ld, rec):
    """The doorway's cells as bp27 lists them: (+0x39, +0x3a) on, the type's
    +0xd by +0xe, across and along swapped for an odd quarter turn."""
    import objload
    tr = ld.rows[rec["type"]]
    w, h = tr[0xD], tr[0xE]
    rot = (-(objload.s16(rec["angles"][1]) >> 10)) & 3
    nx, nz = (h, w) if rot & 1 else (w, h)
    dx, dz = rec["tail"][1], rec["tail"][2]
    return [(dx + c, dz + r) for r in range(nz) for c in range(nx)]


def gate_check(out=sys.stdout, verbose=False):
    """emu/bp27.lua's G lines, a step at a time: the logged gate through
    gate_step -- the doorway test the game's own mask when the log has it --
    and its stamps through the loader's stamp_rect, against the next line of
    the same gate: state, counter, lock, and the doorway's shapes and fence."""
    rows = gate_load()
    if not rows:
        print("  no gate lines in out/lua_bp27.log: ./emu/run.sh debug bp27.lua, "
              "open gate 96 on level 4", file=out)
        return True
    import objload
    loads = {}
    by = {}
    for r in rows:
        by.setdefault((r["session"], r["lv"], r["slot"]), []).append(r)
    ok = bad = used = 0
    for (_session, lv, slot), rs in sorted(by.items()):
        if lv not in loads:
            loads[lv] = objload.Load(lv)
        ld = loads[lv]
        rec = ld.recs.get(slot)
        if rec is None or rec["op"] not in GATE_OPS:
            continue
        tr = ld.rows[rec["type"]]
        t = rec["tail"]
        cells = doorway(ld, rec)
        used += sum(1 for r in rs if r["st"] == 1 and r["ctr"] == 0)
        for a, b in zip(rs, rs[1:]):
            if a["st"] == 0:
                continue                        # USE, object_interact: not the arm
            for (x, z), v in zip(cells, a["cells"]):
                o = ld.cell(x, z)
                ld.grid[o + 8] = v % FENCE
                ld.grid[o + 9] = (ld.grid[o + 9] & 0xBF) | (0x40 if v >= FENCE else 0)
            d = {"state": a["st"], "counter": a["ctr"], "lock": a["lock"]}

            def stamp(k, ld=ld, rec=rec, t=t, tr=tr):
                ld.stamp_rect(rec["b0"], t[3] + k * tr[0xD], t[4], t[1], t[2],
                              tr[0xD], tr[0xE], rec["angles"][1], MASK)

            def clear(a=a, rec=rec):
                if a["q"] is not None:
                    return a["q"] == 0
                return movement.in_range(a["p"], rec["x"], rec["y"], rec["z"],
                                         GATE_CLEAR + PLAYER_R, PLAYER_BODY,
                                         LIFT_CLEAR[1]) == -1
            gate_step(d, clear, stamp)
            got = (d["state"], d["counter"], d["lock"],
                   tuple(ld.grid[ld.cell(x, z) + 8]
                         + (FENCE if ld.grid[ld.cell(x, z) + 9] & 0x40 else 0)
                         for x, z in cells))
            want = (b["st"], b["ctr"], b["lock"], b["cells"])
            if got == want:
                ok += 1
            else:
                bad += 1
                if verbose:
                    print(f"  level {lv} gate {slot} vb {a['vb']}: model {got}, "
                          f"game {want}", file=out)
    print(f"  {ok} of {ok + bad} steps of a gate reproduced -- state, counter, lock "
          f"and the doorway's shapes and fence; {used} opened", file=out)
    return bad == 0


if __name__ == "__main__":
    v = "--check" not in sys.argv
    a = check(verbose=v)
    b = lift_check(verbose=v)
    c = gate_check(verbose=v)
    sys.exit(0 if a and b and c else 1)
