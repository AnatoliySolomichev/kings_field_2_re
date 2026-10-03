#!/usr/bin/env python3
"""The menus' drawing, primitive for primitive.

    python3 tools/ui.py            the "use item" screen against inv1 and inv2
    python3 tools/ui.py --check    the counts alone

Every menu screen is built out of a handful of routines that file sprites and
POLY_FT4s into the ordering table (`tools/gpuframe.py` reads a frame of them
back out of a snapshot). With GAME.EXE's `$gp` at **0x8009c214** -- found in
the menu snapshots, where gp + 0x58..0x68 hold the colours the frame was drawn
in and gp + 0x38..0x44 what the menu's opening wrote there -- they are:

    ui_draw_label (0x800261dc)  a label: a DR_TPAGE at depth 4, then per glyph
        a sprite at (x - 1, y - 1) in the text colour (gp + 0x5c..0x64) at
        depth 2 and one at (x, y) in the shadow's (gp + 0x68) at depth 3;
        7 to a glyph, the cell u = (g & 15) * 8, v = (g >> 4) * 15
    sub_8002636c                a number the same way, from the style's
        column: a code under 11 at v = 15 * code, the rest 7 to the right
    sub_80025f38                a label's plate: a quad (x - 6, y - 6) the
        record's size, at depth 50
    sub_80026acc                a frame: corners 33 square, edges 28 long,
        out of records 9 to 17 at 0x8007e588, at depth 50 -- and a frame lower
        than 66 draws its middle row at a negative height, as the game does
    ui_panel (0x80025468)       a list: its title, its rows from x + 13 and
        y + 8 + 16 * row, the columns its mode asks for, the frame, the
        selected row's bar (record 8, depth 49, its colour pulsing with
        gp + 0x4c) and the button legend
    sub_800269c0, sub_80026570  the legend: a 16-square button at depth 6, and
        8-square ASCII letters at depth 5

The "use item" screen (`0x8001aa84`) lists the things 95..149 carried in
inventory_a (`0x8001aea4`), and `ui_menu_label` (`0x80027688`) sets the list
to x 27, y 147, 3 rows of 24-letter names.
"""
import os
import struct
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
GP = 0x8009C214
NAMES = 0x8007F620            # 24-byte rows of glyph codes, item by item
INVENTORY_A = 0x800C85E8
LABEL_STYLE = 0x8007E570      # page 29, the 7 x 15 font
NUMBER_STYLE = 0x8007E564     # page 29, the digits' column
SMALL_STYLE = 0x8007E57C      # page 28, the 8 x 8 letters
RECORDS = 0x8007E588          # 12-byte pieces: tpage, clut, u, v, w, h


def exe():
    import mips
    return mips.load("game")


def record(e, a):
    """(tpage, clut, u, v, w, h) of a 12-byte descriptor."""
    return struct.unpack("<6h", e.bytes(a, 12))


class Frame:
    """An ordering table being filled: add() files at the head of a depth's
    list, as AddPrim does, and order() is the order the GPU draws them."""

    def __init__(self):
        self.ot = defaultdict(list)

    def add(self, depth, prim):
        self.ot[depth].append(prim)

    def tpage(self, depth, tpage):
        self.ot[depth + 1].append({"kind": "tpage", "tpage": tpage})

    def order(self):
        out = []
        tp = None
        for depth in sorted(self.ot, reverse=True):
            for p in reversed(self.ot[depth]):
                if p["kind"] == "tpage":
                    tp = p["tpage"]
                    continue
                q = dict(p)
                if q["kind"] == "sprite":
                    q["tpage"] = tp
                out.append((depth, q))
        return out


class Look:
    """The colours and switches the drawing reads: gp + 0x58 the boxes, + 0x5c
    the text, + 0x68 the shadow, + 0x4c the bar's pulse, + 0x40 and + 0x44 the
    confirm and cancel buttons; 0x801b25e4 the boxes' semi-transparency,
    0x801b25e1 the brightness."""

    def __init__(self, ram=None):
        def w(off):
            return struct.unpack_from("<I", ram, (GP + off) & 0x1FFFFF)[0]
        if ram is None:
            self.box, self.text, self.shadow, self.pulse = 0x78, 0x80, 0x30, 0
            self.confirm, self.cancel, self.semi, self.bright = 3, 1, 1, 0x80
            return
        self.box, self.text, self.shadow = w(0x58) & 0xFF, w(0x5C) & 0xFF, w(0x68) & 0xFF
        self.pulse = w(0x4C)
        self.confirm, self.cancel = w(0x40), w(0x44)
        self.semi = ram[0x801B25E4 & 0x1FFFFF]
        self.bright = ram[0x801B25E1 & 0x1FFFFF]


def rgb(v):
    return v | (v << 8) | (v << 16)


def sprite(x, y, w, h, u, v, clut, colour):
    return {"kind": "sprite", "x": x, "y": y, "w": w, "h": h, "u": u & 0xFF,
            "v": v & 0xFF, "clut": clut, "rgb": colour}


def quad(x, y, w, h, u, v, uw, vh, tpage, clut, colour, semi):
    """ui_prim_quad's corners (x, y) (x+w, y) (x, y+h) (x+w, y+h)."""
    return {"kind": "quad", "pts": [(x, y), (x + w, y), (x, y + h), (x + w, y + h)],
            "uvs": [(u & 0xFF, v & 0xFF), ((u + uw) & 0xFF, v & 0xFF),
                    (u & 0xFF, (v + vh) & 0xFF), ((u + uw) & 0xFF, (v + vh) & 0xFF)],
            "tpage": tpage, "clut": clut, "rgb": colour, "semi": bool(semi)}


def draw_label(f, look, style, x, y, glyphs):
    """ui_draw_label (0x800261dc)."""
    tpage, clut, _u, _v, w, h = style
    f.tpage(3, tpage)
    for i, g in enumerate(glyphs):
        if g == 0xFF:
            break
        u, v = (g & 0xF) << 3, (g >> 4) * 15
        f.add(2, sprite(x + 7 * i - 1, y - 1, w, h, u, v, clut, rgb(look.text)))
        f.add(3, sprite(x + 7 * i, y, w, h, u, v, clut, rgb(look.shadow)))


def draw_number(f, look, style, x, y, chars):
    """sub_8002636c: a number, its codes from the style's column."""
    tpage, clut, su, _v, w, h = style
    f.tpage(3, tpage)
    for i, c in enumerate(chars):
        if c == 0xFF:
            break
        u, v = (su, c * 15) if c < 0xB else (su + 7, (c - 0xB) * 15)
        f.add(2, sprite(x + 7 * i - 1, y - 1, w, h, u, v, clut, rgb(look.text)))
        f.add(3, sprite(x + 7 * i, y, w, h, u, v, clut, rgb(look.shadow)))


def number_digits(value, n, fill, mode):
    """number_digits (0x800277c0): value as n digits right-aligned, the rest
    0xa (fill 0) or 0, with mode 1's 'x' in front, mode 2's 0xd behind and
    the prefixes of modes 3 to 5."""
    ln = n + {1: 1, 2: 1, 3: 2, 5: 2, 4: 3}.get(mode, 0)
    out = [0xA if fill == 0 else 0] * ln + [0xFF]
    last = ln - 1
    if mode == 1:
        out[0] = 0x13
    elif mode == 2:
        out[ln - 1] = 0xD
        last = ln - 2
    elif mode == 3:
        out[0], out[1] = 0xF, 0x10
    elif mode == 4:
        out[0], out[1], out[2] = 0xC, 0x12, 0x10
    elif mode == 5:
        out[0], out[1] = 0xE, 0x11
    i = last
    while i >= 0:
        out[i] = value % 10
        value //= 10
        if value == 0:
            break
        i -= 1
    return out


def title_plate(f, look, rec, x, y):
    """sub_80025f38: the plate under a label."""
    tpage, clut, u, v, w, h = rec
    f.add(50, quad(x - 6, y - 6, w, h, u, v, w, h, tpage, clut, rgb(look.box), look.semi))


def frame(f, look, e, x, y, w, h):
    """sub_80026acc: a frame of w x h out of records 9..17 at 0x8007e588."""
    def rec(k):
        return record(e, RECORDS + 12 * k)
    s5, s6 = x, y
    t0 = h - 0x42
    k = 9
    for s4 in range(6):
        if s4 == 3:
            s5 = x
            k += 3
            s6 = s6 + 0x21 + (t0 if t0 >= 0 else 0)
        tpage, clut, u, v, rw, rh = rec(k)
        if s4 >= 3 and t0 < 0:
            s3, fv = h - 0x21, v + 0x42 - h
        else:
            s3, fv = rh, v
        s0 = rw
        s2 = w - 0x42
        while True:
            f.add(50, quad(s5, s6, s0, s3, u, fv, s0, s3, tpage, clut, rgb(look.box),
                           look.semi))
            s5 += s0
            if s4 not in (1, 4):
                break
            s2 -= s0
            if s2 == 0:
                break
            if s2 < s0:
                s0 = s2
        k += 1
    # the middle rows: records 12, 13, 14, 28 high, the last what is left --
    # which, for a frame lower than 66, is a negative height
    left = t0
    s6 = y + 0x21
    while True:
        for k in (12, 13, 14):
            tpage, clut, u, v, rw, rh = rec(k)
            s3 = rh if not left < rh else left
            s0 = rw
            s2 = w - 0x42
            s5 = x if k == 12 else s5
            while True:
                f.add(50, quad(s5, s6, s0, s3, u, v, s0, s3, tpage, clut, rgb(look.box),
                               look.semi))
                s5 += s0
                if k != 13:
                    break
                s2 -= s0
                if s2 == 0:
                    break
                if s2 < s0:
                    s0 = s2
        s6 += 0x1C
        left -= s3
        if left == 0:
            break


def button(f, look, e, x, y, b):
    """sub_800269c0: a 16-square button, the brightness above 0x80 adding half."""
    tpage, clut, u, v, w, h = record(e, RECORDS + 12 * 3)
    f.tpage(6, tpage)
    s0 = ((look.bright - 0x80) >> 1) if look.bright > 0x80 else 0
    f.add(6, sprite(x, y, w, h, u + (b << 4), v, clut, rgb(s0 + 0x70)))


def small_text(f, look, e, x, y, text, shadow=0, row=0):
    """sub_80026570: ASCII a..z in 8 x 8 letters."""
    tpage, clut, su, sv, w, h = record(e, SMALL_STYLE)
    f.tpage(6, tpage)
    s0 = (((look.bright - 0x80) >> 1) if look.bright > 0x80 else 0) + 0x70
    s6 = 16 if row > 0 else 0
    for i, ch in enumerate(text):
        u = su + (ch - 0x61) * w
        if shadow == 0:
            f.add(5, sprite(x + 8 * i, y, w, h, u, sv + s6, clut, rgb(s0)))
        else:
            f.add(5, sprite(x + 8 * i - 1, y - 1, w, h, u, sv + s6, clut, rgb(look.text)))
            f.add(6, sprite(x + 8 * i, y, w, h, u, sv + s6, clut, rgb(look.shadow)))


def gp_string(e, off):
    raw = e.bytes(GP + off, 16)
    return list(raw[:raw.index(0)])


def bar_colour(look):
    """ui_panel's .L18-.L19: the selected row's bar pulses with gp + 0x4c."""
    a = look.pulse
    if a < 0x30:
        return a + look.box, (a >> 1) + look.box
    return look.box + 0x5F - a, look.box + 0x2F - (a >> 1)


def panel(f, look, e, s, mode):
    """ui_panel (0x80025468) for `s` -- title (x, y, glyphs), x, y, count,
    rows, first, selected row, label length, names, counts -- in mode 1."""
    style = record(e, LABEL_STYLE)
    if s["title"]:
        title_plate(f, look, record(e, RECORDS + 12 * 2), s["tx"], s["ty"])
        draw_label(f, look, style, s["tx"], s["ty"], s["title"])
    for row in range(s["rows"]):
        if row >= s["count"]:
            break
        k = s["first"] + row
        x, y = s["x"] + 0xD, s["y"] + 8 + (row << 4)
        draw_label(f, look, style, x, y, s["names"][k][:s["length"]])
        if mode == 1 and s["counts"][k] != 0xFF:
            draw_number(f, look, record(e, NUMBER_STYLE), s["x"] + 0xE9, y,
                        number_digits(s["counts"][k], 2, 0, 1))
    frame(f, look, e, s["x"], s["y"], 0x10A, (s["rows"] << 4) | 0xC)
    for row in range(s["rows"]):
        if row != s["sel_row"]:
            continue
        c0, c1 = bar_colour(look)
        tpage, clut, u, v, w, h = record(e, RECORDS + 12 * 8)
        f.add(49, quad(s["x"] + 6, s["y"] + (row << 4) + 5, w, h, u, v, w, h,
                       tpage, clut, c0 | (c0 << 8) | (c1 << 16), 1))
    legend(f, look, e, mode)


def legend(f, look, e, mode, two=None):
    """ui_panel's tail (0x80025a2c): the buttons along the bottom -- confirm
    "select", triangle "guide" and cancel "return", or for modes 3, 8, 9, 12
    and the 0x8000 flag only the first and the last."""
    if two is None:
        two = mode in (3, 8, 9, 0xC) or bool(mode & 0x8000)
    if two:
        button(f, look, e, 0x5F, 0xD6, look.confirm)
        small_text(f, look, e, 0x69, 0xD6, gp_string(e, 0x7C))
        button(f, look, e, 0xA0, 0xD6, look.cancel)
        small_text(f, look, e, 0xAA, 0xD6, gp_string(e, 0x74))
        return
    button(f, look, e, 0x42, 0xD6, look.confirm)
    small_text(f, look, e, 0x4C, 0xD6, gp_string(e, 0x7C))
    button(f, look, e, 0x83, 0xD6, 0)
    small_text(f, look, e, 0x8D, 0xD6, gp_string(e, 0xA4))
    button(f, look, e, 0xBC, 0xD6, look.cancel)
    small_text(f, look, e, 0xC6, 0xD6, gp_string(e, 0x74))


def item_list(e, inventory, first=0x5F, last=0x95):
    """0x8001aea4: (names, counts, ids) of the things first..last carried."""
    names, counts, ids = [], [], []
    for i in range(first, last + 1):
        if inventory[i]:
            names.append(list(e.bytes(NAMES + 24 * i, 24)))
            counts.append(inventory[i])
            ids.append(i)
    return names, counts, ids


def use_item_screen(e, look, inventory, selected=0):
    """The "use item" screen's 2D part (0x8001aa84): ui_menu_label(0, 0) and
    the list, sub_80027728 placing the selection."""
    names, counts, ids = item_list(e, inventory)
    lab = e.bytes(0x8007E67C + 4, 16)
    s = {"tx": 0x1F, "ty": 0x20, "title": list(lab), "x": 0x1B, "y": 0x93,
         "rows": 3, "length": 0x18, "count": len(ids), "names": names,
         "counts": counts + [0xFF], "ids": ids}
    # sub_80027728: the index held to the list, the first row and the bar
    n = s["count"]
    sel = min(selected, n - 1) if n else 0
    if n - sel < s["rows"]:
        if n < s["rows"]:
            s["first"], s["sel_row"] = 0, sel
        else:
            s["first"] = n - s["rows"]
            s["sel_row"] = sel - s["first"]
    else:
        s["first"], s["sel_row"] = sel, 0
    f = Frame()
    panel(f, look, e, s, 1)
    return f.order()


def snapshot_ui(name):
    """The frame's 2D primitives in drawing order, both buffers: [[prim]]."""
    import gpuframe
    ram = gpuframe.load(name)
    out = []
    for buf in (0, 1):
        prims = []
        for d, p in gpuframe.frame(ram, buf):
            if p["kind"] in ("sprite", "quad"):
                q = {k: v for k, v in p.items() if k not in ("abr", "raw")}
                if q["kind"] == "sprite":
                    q.pop("semi", None)
                prims.append((d, q))
        out.append(prims)
    return ram, out


def check(out=sys.stdout, verbose=False):
    e = exe()
    ok = bad = 0
    for name in ("inv1", "inv2"):
        path = os.path.join(ROOT, "out", "snap", name + ".ram")
        if not os.path.exists(path):
            continue
        ram, bufs = snapshot_ui(name)
        inv = ram[INVENTORY_A & 0x1FFFFF:(INVENTORY_A & 0x1FFFFF) + 150]
        look = Look(ram)
        sel = ram[(GP + 0x18) & 0x1FFFFF]
        for b, game in enumerate(bufs):
            # the pulse moves between the two frames: take the bar's from it
            bar = [p for _d, p in game if p["kind"] == "quad" and p["uvs"][0] == (0, 88)]
            if bar:
                c = bar[0]["rgb"]
                look.pulse = next((a for a in range(0x60)
                                   if (lambda c0c1: c0c1[0] | (c0c1[0] << 8) | (c0c1[1] << 16))(
                                       bar_colour_with(look, a)) == c), look.pulse)
            model = use_item_screen(e, look, inv, sel)
            got = [(d, p) for d, p in model]
            good = got == game
            ok += good
            bad += not good
            if verbose or not good:
                print(f"  {name} buffer {b}: {len(game)} primitives, the model "
                      f"{len(got)} -- {'the same' if good else 'DIFFER'}", file=out)
                if not good:
                    for i, (g, m) in enumerate(zip(game, got)):
                        if g != m:
                            print(f"    first difference at {i}:\n      game  {g}\n      model {m}",
                                  file=out)
                            break
    print(f"  {ok} of {ok + bad} frames of the \"use item\" screen drawn primitive for "
          f"primitive as the game drew them (tools/ui.py)", file=out)
    return bad == 0


def bar_colour_with(look, a):
    keep = look.pulse
    look.pulse = a
    c = bar_colour(look)
    look.pulse = keep
    return c


if __name__ == "__main__":
    sys.exit(0 if check(verbose="--check" not in sys.argv) else 1)
