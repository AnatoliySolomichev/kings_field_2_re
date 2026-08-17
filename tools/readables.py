#!/usr/bin/env python3
"""Every object in the world you can read, and what it says.

    python3 tools/readables.py            all snapshots
    python3 tools/readables.py b          one of them

The path is short and entirely in `0x8005e2d0`, the object interaction handler:

    lhu   $a1, 0x26($s0)     the object's own facing
    addiu $a1, $a1, 0x800    turned around
    jal   0x80016a2c         is the player looking at it, within 0x155?
    beqz  $v0, skip
    lhu   $a1, 0x38($s0)     the object's +0x38, as a halfword
    ori   $a0, $zero, 6      archive 6 is ITEM.T
    addiu $a1, $a1, 0x96
    jal   load_entry         show ITEM.T[150 + it]

So the text an object shows is `ITEM.T[150 + u16 at +0x38]`, and 150 is exactly
where the signs and nameplates start in our index of that archive. The gate is
geometric: you have to be facing it.

`+0x38` is part of the union every object class reads differently, so the index
only means anything for the classes that read. **Type 299 is the readable one**
-- 13 of them on level 0, 4 on level 4 -- with types 159, 314 and 317 also
landing in range. Everything else puts values there that run past the end of
the archive, which is how you can tell them apart.

Placement has since been decoded off the disc (`tools/placement.py`), so this
covers **all 28 levels** with no emulator involved. Pass a snapshot name to read
the live table instead, which shows what the player has already changed.
"""
import glob
import os
import struct
import sys

sys.path.insert(0, "tools")
import objects as O                                                  # noqa: E402

TEXT_BASE = 0x96          # ITEM.T entry 150, where the signs begin
READABLE = 299            # the type that reads as a sign or a plaque


def readables(buf, names=None):
    """[(object, text index, text)] for everything with a usable text index."""
    names = names if names is not None else O.names()
    out = []
    for o in O.table(buf):
        off = o["addr"] - O.RAM_BASE
        f38 = struct.unpack_from("<H", buf, off + 0x38)[0]
        if f38 == 0xFFFF:
            continue
        entry = TEXT_BASE + f38
        if entry >= 970:                  # past the end of ITEM.T, so not text
            continue
        out.append((o, entry, names.get(entry, "")))
    return out


def split(found):
    """(confirmed, candidates) -- type 299 is the readable one, the rest are not.

    Accepting anything whose index happens to resolve pulls in noise: four
    type-297 objects sitting in a row at the edge of level 4 all carry 0 there
    and would each read as the inn sign. Type is the honest filter.
    """
    sure = [t for t in found if t[0]["id"] == READABLE]
    maybe = [t for t in found if t[0]["id"] != READABLE and t[2]]
    return sure, maybe


def from_disc(names=None):
    """[(level, cell x, cell z, ITEM.T entry, text)] for every readable in the game."""
    import placement
    names = names if names is not None else O.names()
    out = []
    for lv in range(28):
        for o in placement.objects(lv):
            if o["type"] != READABLE or o["text"] is None:
                continue
            cx, cz, entry = o["cx"], o["cz"], TEXT_BASE + o["text"]
            if entry >= 970:
                continue
            out.append((lv, cx, cz, entry, names.get(entry, "")))
    return out


if __name__ == "__main__":
    if not sys.argv[1:]:
        names = O.names()
        rows = from_disc(names)
        print(f"{len(rows)} readable objects across all 28 levels\n")
        for lv, cx, cz, entry, text in rows:
            print(f"  level {lv:2d} cell ({cx:2d},{cz:2d})  ITEM[{entry}]"
                  f"   {text[:56] if text else '(not decoded)'}")
        sys.exit(0)
    want = sys.argv[1:]
    names = O.names()
    for label in want:
        path = f"out/snap/{label}.ram"
        if not os.path.exists(path):
            continue
        buf = open(path, "rb").read()
        sure, maybe = split(readables(buf, names))
        if not sure and not maybe:
            continue
        print(f"=== {label} ===")
        for title, group in (("readable objects", sure), ("other types, unconfirmed", maybe)):
            if not group:
                continue
            print(f"  -- {title} --")
            for o, entry, text in sorted(group, key=lambda t: (t[0]["z"], t[0]["x"])):
                cx, cz = o["x"] // O.CELL, o["z"] // O.CELL
                print(f"    cell ({cx:2d},{cz:2d})  type {o['id']:3d}  ITEM[{entry}]"
                      f"   {text[:56] if text else '(not decoded)'}")
        print()
