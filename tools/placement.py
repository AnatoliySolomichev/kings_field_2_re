#!/usr/bin/env python3
"""Where every object on every level stands, straight off the disc.

    python3 tools/placement.py            all 28 levels, counted
    python3 tools/placement.py 0          level 0, every object

This is the table that took six attempts to find, and it was never a table you
could search for: the level payload is a **chain of length-prefixed blocks**,
and the placement is the fourth link inside `FDAT.T` entry `3n + 1`. Walking the
chain finds it; grepping never could.

    entry 3n+1  @0     len 12992   entities and their scripts
                @12996 len  3200
                @16200 len   768
                @16972 len  8400   <- 350 records of 24 bytes: the placement
                @25376 len  2048
                @27428 len   640

`load_object_placement` (`0x80044d9c`) walks that block against the object array,
`+0x18` on one side and `+0x44` on the other, for `0x15d` slots. Record layout,
read off the code and confirmed against a RAM snapshot slot by slot -- **350 of
350 type ids match**:

| Offset | Meaning |
| --- | --- |
| +0 | **2 on a placed object, 255 on an unused slot** -- the liveness test |
| +1 | cell Z |
| +2 | cell X |
| +3 | always 255 |
| +4 | `u16` type id |
| +6 | `u16` **rotation**; the live record holds `(-this) mod 4096`, which is the same Z mirror the maps are drawn with -- 336 of 347 |
| +8 | `u16` fine X within the cell |
| +10 | `u16` fine Z within the cell |
| +12, +13 | undecoded -- non-zero on only 68 and 48 records, so a match against a mostly-zero live field means nothing |
| +14 | always 65535 |
| +16..+23 | copied straight into the object's `+0x38`..`+0x3f` -- `+18` matches live `+0x3a` on **347 of 347** records |

Height is not in the record: world Y comes from the terrain, `-128` times the
cell's height byte.

`+0` is the field to test, not the type id. Filtering on the type alone lets
2104 unused slots through across the game, which carry stale types.
"""
import collections
import struct
import sys

sys.path.insert(0, "tools")
from tarc import TArc                                                # noqa: E402

FDAT = "extract/CD/COM/FDAT.T"
BLOCK = 16976        # start of the placement block inside entry 3n+1
RECORD = 24
SLOTS = 350
EMPTY = 0xFFFF
PLACED = 2           # byte +0 of a record that is actually in the world
TEXT_BASE = 0x96     # ITEM.T entry 150, where the signs start
READABLE = 299


def chain(raw):
    """[(offset, length)] for every length-prefixed block in an entry."""
    out, p = [], 0
    while p + 4 <= len(raw):
        n = struct.unpack_from("<I", raw, p)[0]
        if n == 0 or p + 4 + n > len(raw):
            break
        out.append((p + 4, n))
        p += 4 + n
    return out


def objects(lv, path=FDAT):
    """[{slot, type, cx, cz, x, z, h, rot, text}] for every object on a level.

    `h` is the object's height **above the terrain**, a signed 16-bit at offset
    12 of the record, and it is what makes a chest a chest: the body stands at
    `h = 0`, the lid at `h = -640` -- one body-height up, since Y points down --
    and what is in it at `h = -256` (an item the lid hides until it is opened;
    it was taken for a lock plate once). Putting them all on the floor, which is
    what this project did while the field was thought not to exist, draws the
    lid inside the body.

    **The two fine offsets are the other way round from how this used to read
    them.** The `u16` at +8 is the offset along **Z** and the one at +10 along
    **X**; swapping them puts 345 of 347 objects where the game has them
    instead of 112. A player spotted it first -- a healing herb sitting a little
    to one side of where it should be -- and every object whose offset is not
    the middle of its cell was displaced the same way.

    Checked against the game: `y = -128 * cell[+6] + h` reproduces the live
    object table's Y for **345 of level 0's 347 placed objects**. The two it
    misses are both type 280, whose records are full of `0xff` filler and whose
    live Y is a round -12800, so something else places them.
    """
    raw = TArc(path).raw(lv * 3 + 1)
    if len(raw) < BLOCK + SLOTS * RECORD:
        return []
    seg = raw[BLOCK:BLOCK + SLOTS * RECORD]
    out = []
    for k in range(SLOTS):
        r = seg[k * RECORD:(k + 1) * RECORD]
        if r[0] != PLACED:
            continue
        t = struct.unpack_from("<H", r, 4)[0]
        f38 = struct.unpack_from("<H", r, 16)[0]
        out.append({"slot": k, "type": t, "cx": r[2], "cz": r[1],
                    "x": r[2] * 2048 + struct.unpack_from("<H", r, 10)[0],
                    "z": r[1] * 2048 + struct.unpack_from("<H", r, 8)[0],
                    "rot": struct.unpack_from("<H", r, 6)[0] % 4096,
                    "h": struct.unpack_from("<h", r, 12)[0],
                    "text": None if f38 == EMPTY else f38})
    return out


def names():
    """ITEM.T entry -> its decoded first line, for putting words on signs."""
    try:
        import objects as O
        return O.names()
    except Exception:
        return {}


if __name__ == "__main__":
    if len(sys.argv) > 1:
        lv = int(sys.argv[1])
        nm = names()
        rows = objects(lv)
        print(f"level {lv}: {len(rows)} objects placed\n")
        for o in rows:
            say = ""
            if o["text"] is not None and TEXT_BASE + o["text"] < 970:
                say = nm.get(TEXT_BASE + o["text"], "")
                say = f'   "{say[:48]}"' if say else f"   ITEM[{TEXT_BASE + o['text']}]"
            print(f"  slot {o['slot']:3d}  type {o['type']:3d}  "
                  f"cell ({o['cx']:2d},{o['cz']:2d}){say}")
    else:
        tot = 0
        print("objects placed on each level, from the disc:\n")
        for lv in range(28):
            rows = objects(lv)
            if not rows:
                continue
            tot += len(rows)
            readable = sum(1 for o in rows if o["type"] == READABLE)
            kinds = len({o["type"] for o in rows})
            print(f"  level {lv:2d}: {len(rows):3d} objects, {kinds:3d} distinct types,"
                  f" {readable:2d} readable")
        print(f"\n{tot} objects across the game")
