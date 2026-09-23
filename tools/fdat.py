#!/usr/bin/env python3
"""`FDAT.T`, entry by entry and block by block.

    python3 tools/fdat.py              every entry, with its blocks
    python3 tools/fdat.py 97           one entry in full
    python3 tools/fdat.py --shape      the entries grouped by what they look like
    python3 tools/fdat.py --doc        regenerate FDAT.md

Every entry in this archive is a **chain of length-prefixed blocks**: a `u32`
of length, that many bytes, then the next one, until a zero length or the end.
`tools/placement.py` has read it that way for the level entries since the
object placement was found; this points the same reader at all 132 and writes
down what comes out, which is how the object type table turned up.

The archive is `3n + 0`, `3n + 1`, `3n + 2` for each of the 28 levels -- the
grid, the entities and placement, and the level's own code -- and then entries
84 upwards, which are shared. **Entry 97 is the game's common data**, and its
eleven blocks are:

| block | length | what |
| --- | --- | --- |
| 0 | 7200 | the **object type table**, 300 rows of 24; byte +0 is the behaviour opcode and the render class |
| 3 | 1200 | the **level table**, 100 rows of 12, the last one zero; HP, MP, a stat gain and the experience for the next level |
| 4 | 2304 | the **spell table**, 96 records of 24 |
| 5 | 2304 | the **lighting table's source**, 48 entries of 48 bytes |

and the other eight are not identified yet. The two unnamed per-level blocks
are at least *placed*: `level_load` copies them to `0x8019175c` and
`0x801ba6fc`, which abut `object_table` and `story_flags`. Naming one of them is a matter of
finding what reads it, and `out/rdis/game.json` answers that: every routine's
`reads` list is in there.
"""
import collections
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tarc import TArc                                                # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
FDAT = os.path.join(ROOT, "extract", "CD", "COM", "FDAT.T")
LEVELS = 28

# What is known about a block, by (entry, index). Anything not here is
# unidentified on purpose -- a guess in this table would read exactly like the
# three that were established.
KNOWN = {
    (97, 0): "object_type_table -- 300 rows of 24, byte +0 is the behaviour "
             "opcode and the render class (tools/objops.py)",
    (97, 3): "the level table -- 100 rows of 12, the last zero: HP max, MP "
             "max, a gain for the stat at +0x36, and the experience for the "
             "next level (tools/levelup.py)",
    (97, 4): "the **spell table** -- 96 records of 24: +0 unlocked, +5 a group "
             "bit, +0x16 the MP cost. 95 of the 96 are byte for byte what a "
             "RAM snapshot holds at 0x801b77ec (tools/spells.py)",
    (97, 6): "832 bytes that block 8 indexes -- the counts in that index sum "
             "to exactly 832 -- copied to 0x801e7edc. cutscene_step, "
             "player_controller and level_overlay_tick read into it. What the "
             "sequences hold is not established",
    (97, 8): "an **index into block 6**: 39 records of 4 bytes, `(id, count, "
             "u16 offset)`, ids 0..43 with gaps, and the offsets accumulate by "
             "the counts exactly. 0x80060800 expands it into 0x80198468 at "
             "startup and 0x800608ec looks an id up there -- which is what "
             "script_interpreter calls for an entity that is not a talker",
    (97, 5): "the **lighting table's source**, 48 entries of 48 bytes, which "
             "light_table_reset expands into tile_look's 108-byte records at "
             "the top of every frame -- the last 16 of its 64 entries come "
             "from GAME.EXE's own data past this block. An earlier note called "
             "this the creature animation frames and that is withdrawn: "
             "draw_tile loads a record straight into the GTE's light matrices",
}

# The same for every level, keyed by the entry's place in the 3n cycle. All 28
# of the `3n + 1` entries have exactly the same six blocks, which is what makes
# the shape listing worth reading: a format that holds 28 times is a format.
PER_LEVEL = {
    (0, 0): "the 80x80 grid -- 6400 cells of 10 bytes, two five-byte layers "
            "each (tools/maps.py)",
    (0, 1): "the tile shape programs, the only block whose length differs by "
            "level (tools/tiles.py)",
    (1, 0): "40 entity records of 120 bytes, then their scripts -- the script "
            "block starts at 4804 (tools/entities.py, tools/escript.py)",
    (1, 1): "the actor table -- 200 records of 16 (tools/actors.py)",
    (1, 3): "the object placement -- 350 records of 24 (tools/placement.py)",
    (1, 4): "2048 bytes of tile shapes, copied to 0x801e4464",
    # The two that are not identified are at least *placed*: level_load copies
    # each to a fixed address, and both sit immediately before a table that is
    # known, which is worth writing down even though nothing has been found
    # reading either of them yet.
    (1, 2): "copied to 0x8019175c by level_load -- which is exactly 0x300 "
            "below object_table, so it abuts it. Nothing has been found "
            "reading it",
    (1, 5): "copied to 0x801ba6fc by level_load, 0x28c below story_flags. "
            "Nothing has been found reading it",
}


def chain(raw):
    """`[(offset, length)]` for every length-prefixed block in an entry."""
    out, p = [], 0
    while p + 4 <= len(raw):
        n = struct.unpack_from("<I", raw, p)[0]
        if n == 0 or p + 4 + n > len(raw):
            break
        out.append((p + 4, n))
        p += 4 + n
    return out


def entries(path=FDAT):
    a = TArc(path)
    return [(i, a.raw(i)) for i in range(a.count)]


def kind(i):
    """What an entry is, from its index."""
    if i < LEVELS * 3:
        return ("the grid", "the entities and placement",
                "the level's own code")[i % 3] + f", level {i // 3}"
    return "shared"


def show(which=None, out=sys.stdout):
    a = TArc(FDAT)
    print(f"FDAT.T: {a.count} entries", file=out)
    for i in range(a.count):
        if which is not None and i != which:
            continue
        raw = a.raw(i)
        cs = chain(raw)
        if which is None and not cs:
            continue
        print(f"\n  entry {i:3d}  {len(raw):7d} bytes  {kind(i)}"
              f"  -- {len(cs)} block{'s' if len(cs) != 1 else ''}", file=out)
        for n, (off, ln) in enumerate(cs):
            note = KNOWN.get((i, n), "")
            if not note and i < LEVELS * 3:
                note = PER_LEVEL.get((i % 3, n), "")
            print(f"     {n:2d}  at {off:6d}  {ln:7d} bytes  "
                  f"{raw[off:off + 12].hex()}" + (f"  {note}" if note else ""),
                  file=out)


def shapes(out=sys.stdout):
    """Entries grouped by their block lengths, so the pattern shows."""
    a = TArc(FDAT)
    by = collections.defaultdict(list)
    for i in range(a.count):
        cs = chain(a.raw(i))
        by[tuple(ln for _o, ln in cs)].append(i)
    print(f"{len(by)} distinct block shapes over {a.count} entries", file=out)
    for shape, which in sorted(by.items(), key=lambda kv: -len(kv[1])):
        s = ", ".join(str(x) for x in shape[:8]) or "(no chain)"
        if len(shape) > 8:
            s += f", ... {len(shape)} blocks"
        print(f"\n  {len(which):3d} entries: {s}", file=out)
        print(f"      {', '.join(str(x) for x in which[:20])}"
              + (" ..." if len(which) > 20 else ""), file=out)


def document(path=None):
    path = path or os.path.join(ROOT, "FDAT.md")
    import io
    a, b = io.StringIO(), io.StringIO()
    show(None, a)
    shapes(b)
    with open(path, "w") as fh:
        p = lambda *x: print(*x, file=fh)                           # noqa: E731
        p("# FDAT.T, block by block")
        p()
        p("Generated by `tools/fdat.py --doc`. Do not edit it; what is *known*")
        p("about a block is the `KNOWN` table in that file, and everything")
        p("else here is counted off the archive.")
        p()
        p("Every entry is a chain of length-prefixed blocks: a `u32` of")
        p("length, that many bytes, then the next, until a zero length or the")
        p("end. The archive is `3n+0`, `3n+1`, `3n+2` per level -- the grid,")
        p("the entities and placement, and the level's own code -- then")
        p("entries 84 upwards, which are shared.")
        p()
        p("## The shapes")
        p()
        p("```")
        p(b.getvalue().rstrip())
        p("```")
        p()
        p("## Every entry")
        p()
        p("```")
        p(a.getvalue().rstrip())
        p("```")
    return path


if __name__ == "__main__":
    argv = sys.argv[1:]
    if argv and argv[0] == "--doc":
        print("wrote " + os.path.relpath(document(), ROOT))
    elif argv and argv[0] == "--shape":
        shapes()
    elif argv:
        show(int(argv[0], 0))
    else:
        show()
