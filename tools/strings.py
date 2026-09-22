#!/usr/bin/env python3
"""The strings that are not pictures.

    python3 tools/strings.py            the tables, decoded
    python3 tools/strings.py --scan     look for more of them
    python3 tools/strings.py --godot    write them out for the port

"No string in this game is ASCII; it is all pre-rendered images" has been the
first thing this project's notes say about text, and it is right about
everything the player reads in a box. It is wrong about the one table anybody
would want first.

**`0x8007f530` is 191 rows of 24 bytes in the plainest encoding there is:**

```
0x00..0x19   a to z          0x32  an apostrophe     "seath's sword"
0x7f         a space         0x33  a hyphen          "ryu-ga"
0xff         the end
```

and the rows are three things one after another:

| rows | what |
| --- | --- |
| 0..9 | the memory card's messages -- "cannot save", "data error" |
| 10..159 | the **150 item names** -- item `n` is row `10 + n` |
| 160..190 | the **31 spell names** -- fire ball, meteor, lightning bolt |

All 191 decode without one unknown code. The OCR that has read item names off
rendered glyphs since this project started gave item 0 as *"Excel Iecor"*; the
game calls it **excellector**.

The spell names land where the spell subsystem needed them: `spell_table`
(`0x801b77ec`) is 24-byte records whose `+0x16` is the MP cost, `skill_unlock`
sets a record's `+0` when a skill crosses a threshold, and there are 31 of
them. FORMATS.md, "The five rolled stats are skills".

Found by following the menus down rather than by looking for text: `0x8001af88`
builds the inventory page by walking the item array and indexing a 24-byte
table by the id.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mips                                                          # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

TABLE = 0x8007F530
ROW = 24
ROWS = 191
CHARS = {0x7F: " ", 0x32: "'", 0x33: "-"}
SECTIONS = [(0, 10, "card", "the memory card's messages"),
            (10, 160, "item", "the item names, item n is row 10 + n"),
            (160, 191, "spell", "the spell names")]


def decode(b):
    """One row, or None if it is not this encoding at all."""
    out = []
    for c in b:
        if c == 0xFF:
            return "".join(out)
        if c < 26:
            out.append(chr(ord("a") + c))
        elif c in CHARS:
            out.append(CHARS[c])
        else:
            return None
    return None


def row(n, exe=None, table=TABLE, width=ROW):
    e = exe or mips.load("game")
    b = e.bytes(table + width * n, width)
    return decode(b) if b else None


def table(exe=None):
    """`{section: {index: string}}` for the whole of it."""
    e = exe or mips.load("game")
    out = {}
    for lo, hi, name, _why in SECTIONS:
        out[name] = {n - lo: row(n, e) for n in range(lo, hi)}
    return out


def unused(s):
    """A row the game does not use reads as a single `a`, which is a zero."""
    return s is None or s in ("", "a")


def scan(exe=None, width=ROW, least=8, out=sys.stdout):
    """Look for other tables in the same encoding.

    Most of what this finds is binary that happens to decode -- a run of zero
    bytes is a run of `a`s -- so anything whose rows are all `a` is dropped and
    what is left still wants reading rather than believing.
    """
    e = exe or mips.load("game")
    runs, cur = [], []
    a = e.base
    while a < e.end - width:
        s = row(0, e, a, width)
        if s is not None and not unused(s):
            cur.append((a, s))
            a += width
        else:
            if len(cur) >= least:
                runs.append(cur)
            cur = []
            a += 4
    if len(cur) >= least:
        runs.append(cur)
    print(f"{len(runs)} runs of {least} or more rows of {width} bytes", file=out)
    for r in runs:
        print(f"  {r[0][0]:#010x}  {len(r):4d} rows   "
              + ", ".join(repr(x[1]) for x in r[:4]), file=out)
    return runs


def export(out_dir):
    t = table()
    path = os.path.join(out_dir, "strings.json")
    with open(path, "w") as fh:
        json.dump({"_note": f"GAME.EXE {TABLE:#x}, {ROWS} rows of {ROW} bytes: "
                            "a is 0, z is 25, 0x7f a space, 0xff the end. The "
                            "memory card's messages, the 150 item names and "
                            "the 31 spell names",
                   **{k: {str(i): v for i, v in d.items() if not unused(v)}
                      for k, d in t.items()}},
                  fh, separators=(",", ":"))
    return path


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "--scan":
        scan()
    elif a and a[0] == "--godot":
        print("wrote " + os.path.relpath(export("out/godot"), ROOT))
    else:
        t = table()
        for _lo, _hi, name, why in SECTIONS:
            d = t[name]
            live = {i: v for i, v in d.items() if not unused(v)}
            print(f"\n=== {name}: {len(live)} of {len(d)} rows used -- {why}")
            for i, v in sorted(live.items()):
                print(f"  {i:3d}  {v}")
