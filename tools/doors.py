#!/usr/bin/env python3
"""The swinging door's arm, and the recording it is checked against.

    python3 tools/doors.py            the check, with the frames that differ
    python3 tools/doors.py --check    the check alone

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


if __name__ == "__main__":
    sys.exit(0 if check(verbose="--check" not in sys.argv) else 1)
