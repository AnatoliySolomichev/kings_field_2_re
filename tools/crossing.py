#!/usr/bin/env python3
"""Walking from one level into the next.

    python3 tools/crossing.py           each level's crossings
    python3 tools/crossing.py --check   against the crossings bp16 recorded

The levels are pieces of one world, and nothing marks a seam: the player walks
on, and the level under them changes. What does it is an object of opcode
**0xe0** -- type 280, drawn as nothing -- whose arm in `object_interpreter`
(`0x8004a7f8`) asks `player_in_rect` whether the player's cell is in the
rectangle of cells the record names, `+0x38` wide and `+0x39` deep from the
object's own cell, and within its height (the record's y, unless 0x8000: the
player's y above y - 0xc80 and not below y + 0x800). If so, at
`object_trigger_args` it calls

    object_trigger(+0x3a, +0x3b, +0x3c, +0x3d, +0x3e, +0x40, +0x41, +0x42)

The first five are a level block -- the five bytes at `0x8018fad8`, the level
itself second, 0xff meaning "as it is" -- and `object_trigger` (`0x80017c78`)
starts a change only when nothing is changing already and the block is not the
one in hand: the pending block at `0x8018fae4`, the flag `0x8018fad4` set,
`level_load`'s state machine (`0x80018358`) started at 0. The last three are a
**shift in cells**, kept at `0x8018faed`: when `level_load` has the new grid
it calls `world_shift(+0x40 * 2048, -(+0x42 * 128), +0x41 * 2048)` over the
player, the effects, the objects and the creatures -- unless the first is
0x7f, no shift. Level 0's crossing to level 4 is at cell 46 of its southern
edge, z 70 to 79, and shifts z by -70: level 4's z 0..9 is level 0's 70..79.
Its way back, level 4's cell 52, shifts by +70.

**Checked against bp16**: the recording walks from level 0 into level 4 and
back. Each time the player's z jumps by 70 cells nine frames after the frame
the model has them step into the crossing's rectangle -- the frames
`level_load` spends reading the new grid off the disc -- by exactly the shift
the model takes from the record; and the model fires nowhere else.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OPCODE = 0xE0
NO_SHIFT = 0x7F
ANY_Y = 0x8000
CELL = 11                       # a cell is 2048 units
LOAD_FRAMES = 9                 # trigger to shift, both crossings bp16 caught
NEW_GAME = (0x1F000, -0x3C00, 0x4000)   # new_character's place: a death, not a crossing


def s8(v):
    return v - 0x100 if v & 0x80 else v


def triggers(lv):
    """Level lv's crossing objects, in slot order: [{slot, cx, cz, w, h, y,
    block (5 bytes), shift (3, s8) or None}].

    load_object_placement's arm for class 0xe0 (0x80045668) reads the
    placement record's fine offsets -- p[+0xa], p[+8], p[+0xc], which place
    any other object inside its cell -- as **the cell the player is to stand
    in on the other side**: it takes them back off the position, leaving the
    cell's corner and the floor's height, and keeps target minus own cell at
    +0x40 (x), +0x41 (z) and +0x42 (height in 128s) -- or 0x7f in all three
    when p[+0xa] is 0xff, no shift."""
    import objload
    ld = objload.Load(lv)
    out = []
    for slot, r in sorted(ld.recs.items()):
        if r["op"] != OPCODE or r["type"] == 0xFF:
            continue
        t, p = r["tail"], r["p"]
        fine = struct.unpack_from("<h", p, 0xC)[0]
        y = r["y"] - fine                            # the floor's own height
        if struct.unpack_from("<h", p, 0xA)[0] == 0xFF:
            shift = None
        else:
            shift = (s8((p[0xA] - p[2]) & 0xFF), s8((p[8] - p[1]) & 0xFF),
                     s8((p[0xC] - ((-y) >> 7)) & 0xFF))
        out.append({"slot": slot, "cx": p[2], "cz": p[1], "w": t[0], "h": t[1],
                    "y": y, "block": list(t[2:7]), "shift": shift})
    return out


def own_block(lv, trig=None):
    """The block a level is in hand as: what its own crossings that keep it
    ask for -- level 0's [0, 0, 0, 0, 0], level 4's [4, 4, 4, 13, 15], as the
    snapshots hold them at 0x8018fad8 -- or the level in all five."""
    for t in trig if trig is not None else triggers(lv):
        if t["block"][1] == lv and 0xFF not in t["block"]:
            return list(t["block"])
    return [lv] * 5


def player_in_rect(p, cx, cz, w, h, y):
    """player_in_rect (0x80046884): the player's cell in the rectangle, and
    their y within the object's height unless that is 0x8000."""
    px, py, pz = p[0] >> CELL, p[1], p[2] >> CELL
    if not (cx <= px < cx + w and cz <= pz < cz + h):
        return False
    if y == ANY_Y:
        return True
    return not (y + 0x800 < py) and not (py < y - 0xC80)


def target(block, current):
    """The block a trigger asks for, its 0xff bytes taken from the one in
    hand -- and whether that is a change at all."""
    want = [c if b == 0xFF else b for b, c in zip(block, current)]
    return want, want != list(current)


def fire(lv, p, current, busy=False, trig=None):
    """object_interpreter's 0xe0 arms over level lv for one frame: the first
    trigger, in slot order, the player stands in that asks for another block,
    as (trigger, the block) -- or None. Nothing starts while a change is
    under way (0x8018fad4)."""
    if busy:
        return None
    for t in trig if trig is not None else triggers(lv):
        if not player_in_rect(p, t["cx"], t["cz"], t["w"], t["h"], t["y"]):
            continue
        want, change = target(t["block"], current)
        if change:
            return t, want
    return None


def shifted(p, shift):
    """world_shift's three: x and z by whole cells, y by 128 the other way."""
    if shift is None:
        return p
    dx, dz, dy = shift[0] << CELL, shift[1] << CELL, -(shift[2] << 7)
    return (p[0] + dx, p[1] + dy, p[2] + dz)


def check(out=sys.stdout, path=None):
    """bp16's frames, level by level: the model's triggers against the jumps
    of the player's position the log holds."""
    import replay
    rows, _ = replay.load(path) if path else replay.load()
    trig = {}
    fired, jumps = [], []
    block = None
    busy_until = -1
    for a, b in zip(rows, rows[1:]):
        if b["f"] != a["f"] + 1:
            block = None
            continue
        lv = a["lv"]
        if lv not in trig:
            trig[lv] = triggers(lv)
        if block is None or block[1] != lv:
            block = own_block(lv, trig[lv])
        dz = b["p"][2] - a["p"][2]
        dx = b["p"][0] - a["p"][0]
        if (abs(dz) > 0x10000 or abs(dx) > 0x10000) and tuple(b["p"]) != NEW_GAME:
            jumps.append((b["f"], dx, dz))
        if a["f"] <= busy_until:
            continue
        hit = fire(lv, a["p"], block, trig=trig[lv])
        if hit:
            t, want = hit
            fired.append((a["f"], lv, t["slot"], want, t["shift"]))
            busy_until = a["f"] + LOAD_FRAMES + 120
            block = want
    ok = 0
    for f, lv, slot, want, shift in fired:
        j = next((j for j in jumps if j[0] == f + LOAD_FRAMES), None)
        good = j is not None and shift is not None \
            and (round(j[1] / 2048), round(j[2] / 2048)) == (shift[0], shift[1])
        ok += good
        print(f"  frame {f}: level {lv}'s slot {slot} asks for level {want[1]} "
              f"(block {want}), shift {shift} -- "
              + (f"the log's player jumps by {round(j[2] / 2048)} cells {LOAD_FRAMES} frames later"
                 if j else "NO JUMP in the log"), file=out)
    stray = [j for j in jumps if not any(j[0] == f + LOAD_FRAMES for f, *_ in fired)]
    for j in stray:
        print(f"  frame {j[0]}: a jump of ({j[1]}, {j[2]}) the model does not make", file=out)
    print(f"  {ok} of {len(fired)} crossings the model makes are the log's, "
          f"{len(stray)} of its jumps not the model's", file=out)
    return ok == len(fired) and not stray and fired


def export(out_dir, lv):
    """crossNN.json for godot/crossing.gd: the level's crossing objects."""
    import json
    path = os.path.join(out_dir, f"cross{lv:02d}.json")
    with open(path, "w") as fh:
        json.dump(triggers(lv), fh, separators=(",", ":"))
    return path


if __name__ == "__main__":
    if "--check" in sys.argv:
        sys.exit(0 if check() else 1)
    for lv in range(28):
        try:
            ts = triggers(lv)
        except Exception:
            continue
        for t in ts:
            print(f"level {lv:2d} slot {t['slot']:3d}: cells ({t['cx']},{t['cz']}) "
                  f"{t['w']}x{t['h']} -> block {t['block']} shift {t['shift']}")
