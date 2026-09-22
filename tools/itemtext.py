#!/usr/bin/env python3
"""Item id to its description, and to a picture of it.

    python3 tools/itemtext.py               every item, as far as the font reads
    python3 tools/itemtext.py 104           one item
    python3 tools/itemtext.py 104 png       write out/items/104.png to read by eye

**Item `n`'s description is `ITEM.T[390 + n]`**, and its icon is `ITEM.T[540 + n]`.
The formula is in the code at `0x80025044`, which adds 0x186, 0x21c or 0x2b2 to
an index and loads archive 6; and it is confirmed at both ends, because item 104
is the Earth Herb by experiment and `ITEM.T[494]` reads *"Recovery Item. This
herb will heal the wounded body."*, while item 105 is the Antidote and
`ITEM.T[495]` is the medicinal herb that eradicates poison.

That settles the numbering that `tools/overlay.py` reports: when a level asks
`has_item(16)`, item 16 is whatever `ITEM.T[406]` describes.

The catch is the font, not the mapping. These 131 images were never in the
corpus the proportional font was grown on, so a dozen or so glyphs are missing
and the text comes back with `?` in place of them — readable by eye, not yet
clean. Seeding the missing letters from a line read by a human is how the font
was built in the first place, and is what finishes this.
"""
import os
import pickle
import re
import sys

# --- the names, in plain text --------------------------------------------
#
# Every item name in the game is a 24-byte row at 0x8007f620, and it is **not
# a picture**: `a` is 0, `z` is 25, 0x7f is a space and 0xff ends the string.
# Two punctuation codes appear, 0x32 in "seath's sword" and 0x33 in "ryu-ga".
#
# This repository has OCRed item names off rendered images since it started,
# and they were in the executable all along. The OCR read item 0 as "Excel
# Iecor"; it is **excellector**. `tools/itemtext.py names` prints all 150 and
# not one of them needs a glyph template.
#
# Found from 0x8001af88, which builds the inventory page: it walks the item
# array and indexes this table by the id, 24 bytes to a row.

NAME_TABLE = 0x8007F620
NAME_ROW = 24
NAME_COUNT = 150
NAME_CHARS = {0x7F: " ", 0x32: "'", 0x33: "-"}


def name(item_id):
    """The item's name, out of GAME.EXE rather than out of a picture."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import mips
    b = mips.load("game").bytes(NAME_TABLE + NAME_ROW * item_id, NAME_ROW)
    if not b:
        return None
    out = []
    for c in b:
        if c == 0xFF:
            break
        if c < 26:
            out.append(chr(ord("a") + c))
        elif c in NAME_CHARS:
            out.append(NAME_CHARS[c])
        else:
            out.append(f"<{c:02x}>")
    return "".join(out)


def names():
    """`{id: name}` for all 150."""
    return {i: name(i) for i in range(NAME_COUNT)}


def export(out_dir):
    """The names, where the port can read them."""
    import json
    path = os.path.join(out_dir, "itemnames.json")
    with open(path, "w") as fh:
        json.dump({"_note": f"the item names out of GAME.EXE at "
                            f"{NAME_TABLE:#x}, {NAME_ROW} bytes a row: a is 0, "
                            "z is 25, 0x7f a space, 0xff the end. Not OCR",
                   "names": {str(k): v for k, v in names().items() if v}},
                  fh, separators=(",", ":"))
    return path


sys.path.insert(0, "tools")
import propocr                                                       # noqa: E402
import tim                                                           # noqa: E402
from tarc import TArc                                                # noqa: E402

ITEM = "extract/CD/COM/ITEM.T"
DESC = 390        # ITEM.T entry of item n's description
ICON = 540        # ITEM.T entry of item n's icon
ITEMS = 150       # the inventory's own range, 0..149
FONT = "out/propfont_items.pkl"
FALLBACK = "out/propfont_map.pkl"


def image(n, arc=None, base=DESC):
    """(width, height, 1-bit rows) for an item's description image."""
    arc = arc or TArc(ITEM)
    raw = arc.raw(base + n)
    got = tim.parse(raw) if raw else None
    if not got:
        return None
    w, h, px = got[0], got[1], got[2]
    if w < 40 or h < 10:
        return None
    return w, h, bytes(1 if px[y * w + x][0] > 60 else 0
                       for y in range(h) for x in range(w))


def font():
    for p in (FONT, FALLBACK):
        try:
            return pickle.load(open(p, "rb"))
        except OSError:
            continue
    return {}


_WORDS = None


def _dictionary():
    global _WORDS
    if _WORDS is None:
        try:
            _WORDS = {w.strip().lower() for w in open("/usr/share/dict/american-english")}
        except OSError:
            _WORDS = set()
    return _WORDS


def fix_il(s):
    """Capital I and lowercase l are the same bitmap, so pick by the dictionary.

    §3 of FORMATS.md records the same ambiguity in the dialogue font and the
    same cure. Here it turns `ltem` into `Item`, `lt` into `It`, `lchrius` into
    `Ichrius` -- a word that starts with `l`, is not a word, and becomes one (or
    becomes a plausible proper noun) when the `l` is read as `I`.
    """
    words = _dictionary()

    def sub(m):
        w = m.group(0)
        if not w.startswith("l") or len(w) < 2 or w.lower() in words:
            return w
        alt = "I" + w[1:]
        if alt.lower() in words or w[1].isupper() or alt[1:].lower() in words:
            return alt
        return alt if len(w) <= 8 else w
    return re.sub(r"\bl[A-Za-z']+", sub, s)


def text(n, arc=None, f=None, clean=True):
    got = image(n, arc)
    if not got:
        return None
    out = propocr.decode(*got, f if f is not None else font())
    return fix_il(out) if clean else out


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "names":
        for k, n in names().items():
            if n:
                print(f"  {k:3d}  {n}")
        sys.exit(0)

    arc = TArc(ITEM)
    if len(sys.argv) > 1:
        n = int(sys.argv[1])
        if len(sys.argv) > 2 and sys.argv[2] == "png":
            raw = arc.raw(DESC + n)
            w, h, px = tim.parse(raw)[:3]
            os.makedirs("out/items", exist_ok=True)
            tim.write_png(f"out/items/{n}.png", w, h, px)
            print(f"out/items/{n}.png  {w}x{h}   (ITEM.T[{DESC + n}])")
        else:
            print(f"item {n} -> ITEM.T[{DESC + n}]")
            print(" ", " ".join(str(text(n, arc)).split()))
    else:
        f = font()
        got = 0
        for n in range(ITEMS):
            t = text(n, arc, f)
            if t is None:
                continue
            got += 1
            print(f"  {n:3d}: {' '.join(t.split())[:96]}")
        print(f"\n{got} of {ITEMS} items have a description image")
