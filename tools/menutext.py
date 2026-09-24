#!/usr/bin/env python3
"""The menu's own words, out of `ui_label_table`.

    python3 tools/menutext.py           every label, by page and line
    python3 tools/menutext.py --godot   write them out for the port

`ui_menu_label` (`0x80027688`) is called by fifteen screens and it does one
thing: `dest+4` gets sixteen bytes from

    ui_label_table + 252 * page + 28 * line + 4

and `dest+0`, `dest+2` get the constants 31 and 32. The table (`0x8007e67c`)
is **28-byte records, nine to a 252-byte page**: a `u16` x, a `u16` y, then
the label.

The label is **not ASCII**. It is the game's own glyph alphabet, and the
alphabet falls out of the words themselves:

    0x00..0x19   a..z          `14 12 04` is `use`
    0x20..0x29   0..9          `0e 0f 13 08 0e 0d 7f 21` is `option 1`
    0x35         /             `12 13 00 13 14 12 35 ...` is `status/records`
    0x7f         space
    0xff         end of the label

Only 0x21 and 0x22 of the digits appear, in `option 1` and `option 2`, so the
rest of that run is inferred from their positions rather than read.

The x and y in the record are **not what `ui_menu_label` uses** -- it writes
31 and 32 whatever the record says -- so something else reads them, or they
are left over from an earlier layout.

**Line 8 is the page's title, not its ninth item.** Every line 8 in the table
sits at x 31, y 32, which is exactly the pair `ui_menu_label` writes, while
lines 0..7 run down a column from y 58 in steps of 26. And each title repeats
the item that opens it: page 1's is `status/records`, which is page 0's line
3; page 2's is `storage`, page 0's line 4.

What comes out is the whole menu, and two pages of it answer questions asked
elsewhere in this repository. Page 7 is `stay` / `do not stay` -- the inn,
which is what `script_interpreter` opens when a talker's header `+0x12` is in
the 0x30 range. Page 8 is `intellectual` / `blacksmith` -- the choice the
blacksmith on level 3 offers, which `tools/quest.py` found as a conversation
opening a menu and reading the answer back into two story flags.
"""
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mips                                                          # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
TABLE = 0x8007E67C
PAGE, ROW = 252, 28
LINES = PAGE // ROW            # nine records to a page
TEXT_AT = 4                    # the label starts past the two u16
END, SPACE, SLASH = 0xFF, 0x7F, 0x35


def glyph(c):
    if c < 26:
        return chr(ord("a") + c)
    if 0x20 <= c <= 0x29:
        return "0123456789"[c - 0x20]
    if c == SPACE:
        return " "
    if c == SLASH:
        return "/"
    return f"[{c:02x}]"


def label(rec):
    """The text of one record, or None when the slot is empty."""
    if not any(rec):
        return None
    body = rec[TEXT_AT:]
    if END not in body:
        return None                       # no terminator: not a label
    out = []
    for c in body:
        if c == END:
            break
        out.append(glyph(c))
    return "".join(out)


def table(exe=None):
    """[(page, line, x, y, text)] for every label in the table."""
    e = exe or mips.load("game")
    rows, page = [], 0
    while True:
        blob = e.bytes(TABLE + PAGE * page, PAGE)
        if not blob or not any(blob):
            break
        for line in range(LINES):
            rec = blob[ROW * line:ROW * (line + 1)]
            t = label(rec)
            if t is None:
                continue
            x, y = struct.unpack_from("<HH", rec, 0)
            rows.append((page, line, x, y, t))
        page += 1
        if page > 64:
            break
    return rows


def export(out_dir):
    rows = table()
    path = os.path.join(out_dir, "menutext.json")
    with open(path, "w") as fh:
        json.dump({"_note": "ui_label_table at 0x8007e67c, read by ui_menu_label: "
                            "28-byte records nine to a page, u16 x, u16 y and a "
                            "0xff-terminated label in the game's own glyph "
                            "alphabet (0x00..0x19 = a..z, 0x20.. = digits, "
                            "0x35 = slash, 0x7f = space)",
                   "labels": [{"page": p, "line": n, "x": x, "y": y, "text": t}
                              for p, n, x, y, t in rows]}, fh)
    return path


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--godot":
        print(export(os.path.join(ROOT, "godot")))
    else:
        print(__doc__)
        rows = table()
        print(f"{len(rows)} labels over {1 + max(p for p, *_ in rows)} pages\n")
        last = None
        for p, n, x, y, t in rows:
            if p != last:
                print(f"  page {p}")
                last = p
            print(f"    line {n}  x={x:3d} y={y:3d}  {t}")
