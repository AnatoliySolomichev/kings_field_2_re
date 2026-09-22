#!/usr/bin/env python3
"""The spells: what they cost, what element they are, and what unlocks them.

    python3 tools/spells.py             all 31, with their names
    python3 tools/spells.py --raw       every one of the 96 records
    python3 tools/spells.py --check     the disc against a RAM snapshot
    python3 tools/spells.py --godot     write them out for the port

The table is **`FDAT.T` entry 97 block 4**, 2304 bytes: 96 records of 24, and
95 of them are byte for byte what a RAM snapshot holds at `0x801b77ec`. The one
that differs is record 29, whose `+0` is 1 in RAM and 0 on the disc -- because
`+0` is the **unlocked** flag and a fresh character has exactly one spell.

What is read of a record:

| | |
| --- | --- |
| +0 | **unlocked**. `skill_unlock` sets it to 1 when a skill crosses a threshold |
| +0x05 | a one-bit **group**: 1, 2, 4, 8, 0x10, in that order down the table. 1 is fire and 2 is earth, from the names; the other three are not settled |
| +0x16 | the **MP cost**. `cast_spell` reads it, doubles it when equipment byte `0x801b25d4` holds `0x26` and halves it when `0x801b25d5` holds `0x2e`, and announces 9 when the player is short |

The names are the last 31 rows of the string table at `0x8007f530` --
`tools/strings.py` -- and they line up with the records one for one: record 0
is *fire ball* at 3 MP, record 30 is *blessings* at 18.

Six of the 31 have no name and they sit at 3, 10, 14, 18, 22 and 24, which is
the end of each group -- so the elements have room for more spells than the
game ships.
"""
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import strings                                                       # noqa: E402
from tarc import TArc                                                # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
FDAT = os.path.join(ROOT, "extract", "CD", "COM", "FDAT.T")
ENTRY, OFFSET, COUNT, ROW = 97, 13796, 96, 24
LIVE = 0x801B77EC
NAMED = 31                 # the rows the string table has names for
# +5 is a one-bit mask and it groups the table into five runs, which is read.
# **Which element each bit is, is not.** The names make two of them certain --
# 1 is fire (fire ball, fire wall, fire storm, flame) and 2 is earth (stone,
# earth wave, meteor) -- and the other three do not line up with a guess: bit 4
# holds *haze* and *bortecth* while bit 8 holds *wind cutter*, *tornado* and
# *walwind*, so calling 4 "wind" would be wrong in the obvious direction.
ELEMENTS = {1: "fire", 2: "earth"}


def rows(path=FDAT):
    raw = TArc(path).raw(ENTRY)
    return [raw[OFFSET + ROW * k:OFFSET + ROW * (k + 1)] for k in range(COUNT)]


def spells(path=FDAT):
    """`[{id, name, element, mp, unlocked}]` for the 31 the names cover."""
    names = strings.table()["spell"]
    out = []
    for k, r in enumerate(rows(path)[:NAMED]):
        out.append({"id": k,
                    "name": None if strings.unused(names.get(k))
                    else names[k],
                    "group": ELEMENTS.get(r[5], r[5]),
                    "mp": struct.unpack_from("<H", r, 0x16)[0],
                    "unlocked": r[0]})
    return out


def check(snap=None, out=sys.stdout):
    snap = snap or os.path.join(ROOT, "out", "snap", "b.ram")
    if not os.path.exists(snap):
        print("no snapshot to check against", file=out)
        return 0, 0
    ram = open(snap, "rb").read()
    base = LIVE - 0x80000000
    disc = rows()
    same = 0
    for k in range(COUNT):
        live = ram[base + ROW * k:base + ROW * (k + 1)]
        if live == disc[k]:
            same += 1
        else:
            d = [i for i in range(ROW) if live[i] != disc[k][i]]
            print(f"  record {k} differs at {', '.join(hex(i) for i in d)}"
                  f"  disc {disc[k][d[0]]} live {live[d[0]]}", file=out)
    print(f"{same} of {COUNT} records identical to the live table", file=out)
    return same, COUNT


def export(out_dir):
    path = os.path.join(out_dir, "spells.json")
    with open(path, "w") as fh:
        json.dump({"_note": f"FDAT.T entry {ENTRY} at offset {OFFSET}, "
                            f"{COUNT} records of {ROW} bytes; +0 unlocked, "
                            "+5 a group bit, +0x16 the MP cost. The names are "
                            "the last 31 rows of the string table at 0x8007f530",
                   "spells": spells()}, fh, separators=(",", ":"))
    return path


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "--check":
        check()
    elif a and a[0] == "--godot":
        print("wrote " + os.path.relpath(export("out/godot"), ROOT))
    elif a and a[0] == "--raw":
        for k, r in enumerate(rows()):
            if any(r):
                print(f"  {k:3d}  {r.hex()}")
    else:
        print(" id  name              group    MP  unlocked")
        for s in spells():
            print(f"  {s['id']:2d}  {str(s['name'] or '-'):16s} "
                  f"{str(s['group']):8s} {s['mp']:4d}  {s['unlocked']}")
