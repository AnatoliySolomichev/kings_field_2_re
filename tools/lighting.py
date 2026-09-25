#!/usr/bin/env python3
"""The 64 lighting records at `tile_look`, built off the disc as the game does.

    python3 tools/lighting.py --check    against out/tile_look.bin and every snapshot

`tile_look` (`0x801aeefc`) is 64 records of 108 bytes, one per lighting class
-- `cell[+9] & 0x3f` picks one -- and the port bakes its vertex colours from
it. It is zero in GAME.EXE, so the port read it out of a RAM snapshot,
`out/tile_look.bin`. Two routines fill it, and both are short:

**`light_table_reset`** (`0x800341e8`), the first call of every frame, copies
64 sources of 48 bytes from `light_table_source` (`0x80081c8c`):

    record[0x00:0x14] = source[0x00:0x14]    the light direction matrix
    record[0x50:0x6c] = source[0x14:0x30]    the colour matrix, the background
                                             colour and two arguments

leaving `record[0x14:0x50]` alone, and sets the flag at `0x801aeef8`. Its
earlier description, "twice per entry, the near and far copies", read the two
halves of one copy as two copies.

**`light_table_step`** (`0x80034300`), when that flag is set, calls
`light_matrix_turn` (`0x80016290`) three times per record, writing the
direction matrix turned a quarter, a half and three quarters about Y into
`+0x14`, `+0x28` and `+0x3c` -- the orientations `draw_tile` picks by
`cell[+7] & 3`. Each row `(a, b, c)` becomes `(-c, b, a)`, `(-a, b, -c)` and
`(c, b, -a)`. It was described as "the interpolation that moves torchlight";
it is a rotation, run whenever the table is reset.

The sources: `init_level_state` copies `FDAT.T` entry 97 block 5, 2304 bytes,
over the first 48, and the last 16 are GAME.EXE's own data behind it. Nothing
here depends on the level, and the check says so: **6912 of 6912 bytes** on
level 0's snapshots and on level 4's.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fdat                                                           # noqa: E402
from tarc import TArc                                                 # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SOURCE = 0x80081C8C              # light_table_source
TILE_LOOK = 0x801AEEFC
RECORDS, SRC, REC = 64, 48, 108
BLOCK = 5                        # of FDAT.T entry 97


def _s16(v):
    return ((v + 0x8000) & 0xFFFF) - 0x8000


def turn(m, r):
    """`light_matrix_turn`: nine halfwords turned r quarter turns about Y."""
    v = struct.unpack_from("<9h", m, 0)
    out = []
    for row in range(3):
        a, b, c = v[3 * row:3 * row + 3]
        out += {1: (-c, b, a), 2: (-a, b, -c), 3: (c, b, -a)}[r]
    return struct.pack("<9h", *(_s16(x) for x in out))


def source():
    """The 64 sources: entry 97 block 5, then GAME.EXE's own 16."""
    import mips
    raw = TArc(fdat.FDAT).raw(97)
    o, n = fdat.chain(raw)[BLOCK]
    rest = mips.load("game").bytes(SOURCE + n, RECORDS * SRC - n)
    return raw[o:o + n] + rest


def table():
    """The 6912 bytes `tile_look` holds after a reset and a step."""
    src = source()
    out = bytearray()
    for i in range(RECORDS):
        s = src[SRC * i:SRC * (i + 1)]
        rec = bytearray(REC)
        rec[0x00:0x14] = s[0x00:0x14]
        for r in (1, 2, 3):
            rec[0x14 * r:0x14 * r + 18] = turn(s, r)
        rec[0x50:0x6C] = s[0x14:0x30]
        out += rec
    return bytes(out)


def check():
    import glob
    mine = table()
    path = os.path.join(ROOT, "out", "tile_look.bin")
    if os.path.exists(path):
        old = open(path, "rb").read()
        print(f"out/tile_look.bin: {sum(a == b for a, b in zip(mine, old))} of "
              f"{len(old)} bytes")
    agree = total = 0
    for ram in sorted(glob.glob(os.path.join(ROOT, "out", "snap", "*.ram"))):
        r = open(ram, "rb").read()
        if r[0x191A5C + 6] == 0:          # no level ever loaded
            continue
        base = TILE_LOOK & 0x1FFFFF
        t = r[base:base + RECORDS * REC]
        same = sum(a == b for a, b in zip(mine, t))
        agree, total = agree + same, total + len(t)
        print(f"{os.path.basename(ram)}  level {r[0x18FAD9]}: {same} of {len(t)} bytes")
    print(f"over every snapshot: {agree} of {total} bytes")


if __name__ == "__main__":
    check()
