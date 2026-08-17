#!/usr/bin/env python3
"""`FDAT.T` entry `3n + 1` — the entities placed on a level, and their scripts.

    python3 tools/entities.py           every level, one line each
    python3 tools/entities.py 0         level 0 in full, scripts included

Layout of the entry:

    u32            size of everything below, entity slots and scripts together
    <record>[40]   120 bytes each, a fixed array; unused slots are all 0xff
    ...            the script block, starting at 4 + 40*120 = 4804

A record ends with a list of `u32` offsets into the script block, terminated by
`0xffffffff` and padded with more of the same to the end of the record. The
offsets are **monotonic across the whole level** -- entity 0 owns the first run,
entity 1 the next -- so the block is one sequential stream that the records
carve up, and a record's script count is however many offsets it lists.

Counts are much smaller than the notes used to say: 16 entities on level 0, 12
on level 4, 10 on level 7, not ~121. The old figure came from dividing the
whole entry by the record size, which counts the script block as records.

The records are loaded into RAM at `entity_table`, 0x8018c7e8, keeping the same
120-byte stride, and 13 pieces of code reach them -- among them the same walk
in `object_motion` that steps the object table. Past roughly byte 40 the live
copy has already diverged from the disc, which is what a record being mutated
as the entity acts looks like.

The script bytes themselves are *not* in RAM verbatim, so they are transformed
on load. Their opcodes are undecoded; what is visible is that `0xff` ends a
sequence and that the sequences run 14 to 44 bytes.
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
# The u32 at the head is the size of the whole area, not an offset to the
# scripts: 4 + 12992 lands at the *end*. Taking it for the script base put the
# decode 8192 bytes past where the scripts are, which is where the first pass
# went wrong. The scripts start right after the 40 slots, and at that base the
# disc matches RAM byte for byte over 3000 bytes.


def entry(lv, path=FDAT):
    """(raw entry, script block base, [(record bytes, [script offsets])])"""
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
        for j in range(0x3C, RECORD, 4):
            v = struct.unpack_from("<I", r, j)[0]
            if v == 0xFFFFFFFF:
                break
            offs.append(v)
        recs.append((r, offs))
    return raw, base, recs


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
        print(f"level {lv}: {len(recs)} entities, script block at entry+{base}\n")
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
            print(f"level {lv:2d}: {s['entities']:3d} entities, {s['scripts']:4d} scripts, "
                  f"offsets {s['span'][0]}..{s['span'][1]}")
        print(f"\n{tot['entities']} entities and {tot['scripts']} scripts in the game")
