#!/usr/bin/env python3
"""Checksums on the entries inside a .T container.

Every entry ends with a 4-byte checksum and the game refuses an entry whose
sum does not match, which is why editing a TIM inside one of these archives
freezes the game. The algorithm came from the KingsFieldRE wiki, which
documents the first US game rather than this one; it is reproduced here because
it turned out to hold on this disc too:

    sum = 0x12345678
    for each little-endian u32 of the entry, up to but not including the
    trailing checksum word:
        sum += word          (mod 2**32)

Verified across the nine archives on our disc: FDAT, ITEM, MO, MOF, RTMD,
STALK and TALK match on every single entry. RTIM matches on none and VAB on
134 of 356 -- raw texture pages and sound banks are not checksummed, which is
the same exception the wiki notes.

Since confirmed from the other side as well. A read watchpoint over a loading
level caught the game running it: `0x80019b1c` seeds `$a3` with 0x12345678 via
an lui/ori pair and sums words in a loop at `0x80019b8c`, over a length taken
as sectors shifted left by 9 -- that is, 512 words per sector.

    python3 tools/tsum.py extract/CD/COM/*.T
"""
import os
import struct
import sys

sys.path.insert(0, "tools")
from tarc import TArc                                                # noqa: E402

SEED = 0x12345678


def checksum(block):
    """The value that belongs in the last word of `block`."""
    s = SEED
    for (w,) in struct.iter_unpack("<I", block[:len(block) - 4]):
        s = (s + w) & 0xFFFFFFFF
    return s


def verify(block):
    if len(block) < 8:
        return None
    return checksum(block) == struct.unpack_from("<I", block, len(block) - 4)[0]


def stamp(block):
    """Return `block` with its trailing checksum word made correct again.

    This is the step an edited entry needs before it goes back on the disc.
    """
    return block[:len(block) - 4] + struct.pack("<I", checksum(block))


def main():
    for path in sys.argv[1:]:
        t = TArc(path)
        ok = bad = empty = 0
        for i in range(t.count):
            block = t.raw(i)
            if not block:
                empty += 1
                continue
            ok, bad = (ok + 1, bad) if verify(block) else (ok, bad + 1)
        print(f"{os.path.basename(path):10s} {ok:5d} match  {bad:5d} do not  "
              f"{empty:5d} empty")


if __name__ == "__main__":
    main()
