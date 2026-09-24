#!/usr/bin/env python3
"""`FDAT.T` entry `3n + 1` — the entities placed on a level, and their blocks.

    python3 tools/entities.py           every level, one line each
    python3 tools/entities.py 0         level 0 in full

Layout of the entry:

    u32            size of everything below, entity slots and blocks together
    <record>[40]   120 bytes each, a fixed array; unused slots are all 0xff
    ...            the block area, starting at 4 + 40*120 = 4804

A record ends with **sixteen** `u32` offsets into that area, at `+0x38`
through `+0x74`, and `entity_table_init` (`0x80053084`) is what says so: it
walks 40 records, and for each one walks 16 words from `+0x38`, turning
`0xffffffff` into a null pointer and everything else into `offset +
entity_scripts`, where `entity_scripts` is `entity_table + 0x12c0` — the
40*120 bytes of records, so the same base the file uses. Unused slots are
`0xffffffff` and sit at the tail.

**The list starts at `+0x38`, not at `+0x3c`.** Reading it from `+0x3c` drops
each entity's first block and shifts every conclusion drawn from the rest by
one, which is how `tools/escript.py` came to decode 1086 things that are not
scripts; `emu/bp21.lua` caught it in play.

Each block begins with a **kind byte**, and `0xff` at `+4`. Only kind `0x70`
is a conversation — `script_interpreter` tests for exactly that — and it is
always block 0. On level 0 six entities have one and the other ten have a
block 0 of kind 0x00/0x06/0x1a instead. Across the game there are 43.

Nothing in `GAME.EXE` reads blocks 1..15: `script_interpreter` and
`script_prescan` both load `record+0x38` at a fixed offset and no other code
touches the area. They are relocated for the level's own overlay, and what
they mean is **not settled**. What is visible is that their kind bytes repeat
across entities — every entity on level 0 has a `0x00`, and all but one end
with a `0x02` then a `0x03`.

The records are loaded into RAM at `entity_table`, 0x8018c7e8, keeping the
120-byte stride, and 13 pieces of code reach them. Past roughly byte 40 the
live copy has already diverged from the disc, which is what a record being
mutated as the entity acts looks like.
"""
import collections
import struct
import sys

sys.path.insert(0, "tools")
from tarc import TArc                                                # noqa: E402

FDAT = "extract/CD/COM/FDAT.T"
RECORD = 120
SLOTS = 40                     # the entity array is fixed; unused slots are 0xff
ENTITY_TABLE = 0x8018C7E8      # where the records land in RAM
ENTITY_SCRIPTS = 0x8018DAA8    # entity_table + 0x12c0, the block area
PTRS = 0x38                    # the first of the block offsets in a record
PTR_SLOTS = 16                 # how many entity_table_init relocates
CONVERSATION = 0x70            # the block kind script_interpreter runs
# The u32 at the head is the size of the whole area, not an offset to the
# scripts: 4 + 12992 lands at the *end*. Taking it for the script base put the
# decode 8192 bytes past where the scripts are, which is where the first pass
# went wrong. The scripts start right after the 40 slots, and at that base the
# disc matches RAM byte for byte over 3000 bytes.


def entry(lv, path=FDAT):
    """(raw entry, block area base, [(record bytes, [block offsets])])

    The offsets are the sixteen `u32` at `record+0x38`, in the order
    `entity_table_init` relocates them, with the nulls dropped.
    """
    raw = TArc(path).raw(lv * 3 + 1)
    if len(raw) < 8:
        return None, None, []
    base = 4 + SLOTS * RECORD
    body = raw[4:]
    # A populated record ends in the terminator run and carries the constant
    # at +1; the array stops where that stops holding.
    last = -1
    for k in range(SLOTS):
        r = body[k * RECORD:(k + 1) * RECORD]
        if r[-4:] == b"\xff\xff\xff\xff" and r[1] == 0x04:
            last = k
        elif last >= 0 and k - last > 3:
            break
    recs = []
    for k in range(last + 1):
        r = body[k * RECORD:(k + 1) * RECORD]
        offs = []
        for j in range(PTRS, PTRS + 4 * PTR_SLOTS, 4):
            v = struct.unpack_from("<I", r, j)[0]
            if v == 0xFFFFFFFF:
                continue
            offs.append(v)
        recs.append((r, offs))
    return raw, base, recs


def blocks(lv, path=FDAT):
    """[(offset of the data, length)] for entry `3n + 1`, which is a chain.

    `level_load` walks it as one: it reads a `u32` length, uses the bytes
    after it, then steps over both and reads the next. Six blocks, and the
    offsets are the same on every level:

    | # | at | bytes | where it goes |
    | --- | --- | --- | --- |
    | 0 | 4 | 12992 | `entity_table`, 0xcb0 words -- the 40 records and the blocks they point at |
    | 1 | 13000 | 3200 | `actor_table_build` |
    | 2 | 16204 | 768 | `0x8019175c` -- **32 more rows of `object_type_table`, starting at type 300** |
    | 3 | 16976 | 8400 | `load_object_placement` |
    | 4 | 25380 | 2048 | `level_props_init` -- 128 records of 16, the models a level places itself |
    | 5 | 27432 | 640 | `0x801ba6fc` -- 160 rectangles, the map the game draws |

    So `4 + the entry's first u32` is where the *second* block begins, not the
    end of anything: this file used to treat that word as "the size of
    everything below", which is true only of block 0.
    """
    raw = TArc(path).raw(lv * 3 + 1)
    out, o = [], 0
    while o + 4 <= len(raw):
        n = struct.unpack_from("<I", raw, o)[0]
        if n == 0 or o + 4 + n > len(raw):
            break
        out.append((o + 4, n))
        o += 4 + n
    return raw, out


TYPE_BLOCK = 2                 # the block holding the level's own type rows


def level_type_rows(lv, path=FDAT):
    """The 32 `object_type_table` rows a level brings with it, types 300..331."""
    raw, bs = blocks(lv, path)
    if len(bs) <= TYPE_BLOCK:
        return []
    o, n = bs[TYPE_BLOCK]
    return [raw[o + 24 * i:o + 24 * (i + 1)] for i in range(n // 24)]


def spans(raw, base, recs):
    """offset -> (start, end) for every block on the level.

    A block runs to whichever block starts next, whoever owns it: the offsets
    are one ascending sequence over the whole area.
    """
    flat = sorted({v for _, o in recs for v in o})
    out = {}
    for i, a in enumerate(flat):
        b = flat[i + 1] if i + 1 < len(flat) else len(raw) - base
        out[a] = (a, b)
    return out


def cut(raw, base, flat):
    """offset -> its slice, each running to the next offset anywhere on the level.

    The offsets are one global ascending sequence, so a script ends where the
    next one begins whether or not that next one belongs to the same entity.
    """
    out = {}
    for i, a in enumerate(flat):
        b = flat[i + 1] if i + 1 < len(flat) else a + 16
        out[a] = raw[base + a:base + b]
    return out


def u16(r, off):
    return struct.unpack_from("<H", r, off)[0]


def summary(lv):
    raw, base, recs = entry(lv)
    if not recs:
        return None
    flat = sorted(v for _, o in recs for v in o)
    return {"level": lv, "entities": len(recs), "scripts": len(flat),
            "block": base, "span": (flat[0], flat[-1]) if flat else None}


if __name__ == "__main__":
    if len(sys.argv) > 1:
        lv = int(sys.argv[1])
        raw, base, recs = entry(lv)
        flat = sorted(v for _, o in recs for v in o)
        pieces = cut(raw, base, flat)
        print(f"level {lv}: {len(recs)} entities, block area at entry+{base}\n")
        for k, (r, offs) in enumerate(recs):
            print(f"[{k:2d}] kind={r[0]:#04x} +0x12={u16(r, 0x12):5d} "
                  f"+0x14={u16(r, 0x14):5d} +0x16={u16(r, 0x16):4d} "
                  f"scale={u16(r, 0x18):#06x}  {len(offs)} scripts")
            print(f"     head {r[:24].hex(' ')}")
            print(f"     stats {' '.join(str(u16(r, j)) for j in range(0x1e, 0x38, 2))}")
            for a in offs:
                print(f"     +{a:5d} {pieces[a].hex(' ')}")
            print()
    else:
        tot = collections.Counter()
        for lv in range(28):
            s = summary(lv)
            if not s:
                continue
            tot["entities"] += s["entities"]
            tot["scripts"] += s["scripts"]
            print(f"level {lv:2d}: {s['entities']:3d} entities, {s["scripts"]:4d} blocks,   "
                  f"offsets {s['span'][0]}..{s['span'][1]}")
        print(f"\n{tot['entities']} entities and {tot["scripts"]} blocks in the game")
