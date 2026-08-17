#!/usr/bin/env python3
"""What the game writes into a save, field by field.

    python3 tools/savemap.py              the layout
    python3 tools/savemap.py save1        read those fields out of a RAM snapshot

Two routines face each other: `save_serialise` at `0x8005f7bc` copies globals
into a buffer, and `save_restore` at `0x8005ffd0` copies them back. Reading both
and keeping only what they agree on gives **57 fields** — the agreement is the
check, since a mistake in either direction would not line up with the other.

`data/savemap.json` holds the result: for each global, the offset it occupies in
the save. It is worth more than a list of offsets, because it also answers a
different question — *which* of the many unnamed words in the player block are
real state. Anything the game bothers to persist is state; anything it does not
is scratch.

What this does **not** describe is the layout on the memory card. The card block
is 8192 bytes and this buffer is far larger, so the card gets a subset or a
packing of it; §11 shows `level_state` landing at card offset 1288, which is not
its offset here.
"""
import json
import os
import struct
import sys

sys.path.insert(0, "tools")
import syms                                                          # noqa: E402

MAP = os.path.join(os.path.dirname(__file__), "..", "data", "savemap.json")
SERIALISE = 0x8005F7BC
RESTORE = 0x8005FFD0


def load(path=MAP):
    """[(global address, save offset, name)] sorted by save offset."""
    d = json.load(open(path))
    out = [(int(k, 16), v["save_offset"], v["name"]) for k, v in d.items()]
    return sorted(out, key=lambda t: t[1])


def read(ram, fields=None):
    """global -> its current value in a RAM image, sized by the save field."""
    fields = fields or load()
    out = {}
    for addr, off, name in fields:
        o = addr & 0x1FFFFF
        # the save offset spacing tells us the width the game used
        out[name if not name.startswith("0x") else f"{addr:#010x}"] = (
            struct.unpack_from("<I", ram, o)[0])
    return out


if __name__ == "__main__":
    fields = load()
    if len(sys.argv) > 1:
        ram = open(f"out/snap/{sys.argv[1]}.ram", "rb").read()
        print(f"{len(fields)} persisted fields, read out of {sys.argv[1]}:\n")
        for addr, off, name in fields:
            o = addr & 0x1FFFFF
            v = struct.unpack_from("<I", ram, o)[0]
            print(f"  save +{off:#06x}  {syms.label(addr):24s} = {v:#010x} ({v & 0xFFFF})")
    else:
        print(f"{len(fields)} fields the game persists, "
              f"agreed by {syms.label(SERIALISE)} and {syms.label(RESTORE)}:\n")
        for addr, off, name in fields:
            print(f"  save +{off:#06x}  <-  {syms.label(addr)}")
