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


# ui_panel's modes with no count column: 2 and 3 (.L11), 4, 8 and 9 (the
# flag at sp+0x48) and 0x10, which has its own
NO_COUNTS = (2, 3, 4, 8, 9, 0x10)


def panel(f, look, e, s, mode):
    """ui_panel (0x80025468) for `s` -- title (x, y, glyphs), x, y, count,
    rows, first, selected row, label length, names, counts -- in modes 1, 2,
    3, 4, 5 and 0x10: mode 3 a second name 0x54 to the right of the first
    ("names2", 24 bytes and an end), modes 1 and 5 the count "x N" at x +
    0xe9, modes 2 and 4 the cost behind the MP sign, 0x10 both."""
    style = record(e, LABEL_STYLE)
    m = mode & 0xFFF
    if s["title"]:
        title_plate(f, look, record(e, RECORDS + 12 * 2), s["tx"], s["ty"])
        draw_label(f, look, style, s["tx"], s["ty"], s["title"])
    for row in range(s["rows"]):
        if row >= s["count"]:
            break
        k = s["first"] + row
        x, y = s["x"] + 0xD, s["y"] + 8 + (row << 4)
        draw_label(f, look, style, x, y, s["names"][k][:s["length"]])
        if m == 3:
            draw_label(f, look, style, x + 0x54, y, list(s["names2"][k][:0x18]) + [0xFF])
        if m in (2, 4) and s["costs"][k] != -1:
            # .L8, for modes 2 and 4 alike: the u32 column (+0x30), three
            # digits behind the MP sign
            x += 0xCE
            draw_number(f, look, record(e, NUMBER_STYLE), x, y,
                        number_digits(s["costs"][k], 3, 0, 3))
        if m == 0x10:
            # .L14: the thing's count, then a spell's cost, each moving the
            # place on from where the last left it
            if s["counts"][k] != 0xFF:
                x += 0xDC
                draw_number(f, look, record(e, NUMBER_STYLE), x, y,
                            number_digits(s["counts"][k], 2, 0, 1))
            if s["costs"][k] != -1:
                x += 0xCE
                draw_number(f, look, record(e, NUMBER_STYLE), x, y,
                            number_digits(s["costs"][k], 3, 0, 3))
        if m not in NO_COUNTS and s["counts"][k] != 0xFF:
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
    if m == 7:
        quantity(f, look, e, s.get("qty", 1))
    legend(f, look, e, mode)


QTY_WORD = [0x10, 0x13, 0x18, 0xFF]              # "qty"


def quantity(f, look, e, qty):
    """ui_quantity(0) (0x80025db8), ui_panel's for mode 7 after the bar: a plate at
    (0xb7, 0x2e) with "QTY" on it, and the quantity (gp+0x48) in two digits
    0x54 to the right. Its 1 (the shops' modes) moves it to y 0x4a and draws
    the gold first (sub_80025e80); not here."""
    title_plate(f, look, record(e, RECORDS + 12 * 2), 0xB7, 0x2E)
    draw_label(f, look, record(e, LABEL_STYLE), 0xB7, 0x2E, QTY_WORD)
    draw_number(f, look, record(e, NUMBER_STYLE), 0xB7 + 0x54, 0x2E,
                number_digits(qty, 2, 0, 1))


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


def lit_plate(f, look, rec, x, y):
    """sub_80026020: a plate in the selection's pulsing colour."""
    c0, c1 = bar_colour(look)
    tpage, clut, u, v, w, h = rec
    f.add(50, quad(x - 6, y - 6, w, h, u, v, w, h, tpage, clut,
                   c0 | (c0 << 8) | (c1 << 16), look.semi))


def dim_label(f, look, style, x, y, glyphs):
    """sub_80026158: a label not chosen -- the text colour 0x57 (0x47 and 0x57
    with the boxes opaque) while it is drawn."""
    keep = look.text
    tpage, clut, _u, _v, w, h = style
    f.tpage(3, tpage)
    if look.semi:
        col = 0x57 | (0x57 << 8) | (keep << 16)
    else:
        col = 0x47 | (0x47 << 8) | (0x57 << 16)
    for i, g in enumerate(glyphs):
        if g == 0xFF:
            break
        u, v = (g & 0xF) << 3, (g >> 4) * 15
        f.add(2, sprite(x + 7 * i - 1, y - 1, w, h, u, v, clut, col))
        f.add(3, sprite(x + 7 * i, y, w, h, u, v, clut, rgb(look.shadow)))


def options(f, look, e, one, two, sel):
    """sub_80025b24: a prompt's two answers, (x, y, glyphs) each -- the chosen
    one on a lit plate in the text colour, the other on a plain plate dimmed."""
    rec = record(e, RECORDS + 12 * 1)
    style = record(e, LABEL_STYLE)
    if sel == 0:
        lit_plate(f, look, rec, one[0], one[1])
        title_plate(f, look, rec, two[0], two[1])
        draw_label(f, look, style, *one)
        dim_label(f, look, style, *two)
    else:
        title_plate(f, look, rec, one[0], one[1])
        lit_plate(f, look, rec, two[0], two[1])
        dim_label(f, look, style, *one)
        draw_label(f, look, style, *two)


PROMPT_WORDS = {0: [0x14, 0x12, 0x04], 1: [0x12, 0x13, 0x0E, 0x11, 0x04],   # use, store
                0xA: [0x0C, 0x0E, 0x15, 0x04]}                             # move
CANCEL = [0x02, 0x00, 0x0D, 0x02, 0x04, 0x0B]                              # cancel


def menu_page(f, look, e, page, n, sel, legend_mode=0):
    """sub_800252f4: a page of the menu's labels -- its title (the line 8 of
    the page before, if it has a place), its n lines on plates, the chosen one
    lit, the others dimmed -- and the two-button legend."""
    style = record(e, LABEL_STYLE)
    plate = record(e, RECORDS + 12 * 2)
    base = 0x8007E660 + 252 * page

    def line(a):
        x, y = struct.unpack("<hh", e.bytes(a, 4))
        return x, y, list(e.bytes(a + 4, 16))
    tx, ty, tg = line(base)
    if tx != 0:
        title_plate(f, look, plate, tx, ty)
        draw_label(f, look, style, tx, ty, tg)
    for i in range(n):
        # ui_menu_label writes 31 and 32 whatever the record says; the menu's
        # lines are drawn where the record says
        x, y, g = line(base + 0x1C * (i + 1))
        if i == sel:
            lit_plate(f, look, plate, x, y)
            draw_label(f, look, style, x, y, g)
        else:
            title_plate(f, look, plate, x, y)
            dim_label(f, look, style, x, y, g)
    if legend_mode in (0, 1):
        legend(f, look, e, 0, two=True)


STATUS_LABELS = {"experience": 0x8007F350, "level": 0x8007F368,
                 "condition": 0x8007F3B0, "gold": 0x8007F458}
# the condition line, the first that holds: paralysed (0x801b2568), cursed
# (0x801b255e), slowed (turn_slow_timer), poisoned (poison_frames), in the
# dark (0x801b2562), and otherwise normal
CONDITIONS = (("paralyze", 0x8007F3C8), ("curse", 0x8007F3E0), ("slow", 0x8007F3F8),
              ("poison", 0x8007F410), ("dark", 0x8007F428), (None, 0x8007F440))
# the five skills' icons: (working skill, u, CLUT), in the order drawn
SKILL_ICONS = ((4, 0x00, 0x7D04), (0, 0x10, 0x7D44), (1, 0x20, 0x7D84),
               (3, 0x30, 0x7DC4), (2, 0x40, 0x7E04))
ICON_PAGE, ICON_V, ICON_SIZE, ICON_DEPTH = 0x1D, 0xC0, 0xE, 0x1E


def status_page(f, look, e, ps):
    """ui_status_page (0x800227ec), behind the menu's main page every frame:
    experience, level, HP and MP over their maxima, the effective stat and
    0x801b2530 + 1, the five working skills under their icons, the condition
    and the gold, in a frame. `ps` holds the values: "exp", "level", "hp",
    "hp_max", "mp", "mp_max", "stat", "wis" (0x801b2530), "working" (five),
    the conditions by name, "gold"."""
    style, nstyle = record(e, LABEL_STYLE), record(e, NUMBER_STYLE)
    # the two records on the stack: a label at sp+0x20, a number at sp+0x40
    lx, ly = 0xA3, 0x24
    lg = list(e.bytes(STATUS_LABELS["experience"], 20))
    draw_label(f, look, style, lx, ly, lg)
    nx, ny = lx + 0x4D, ly
    draw_number(f, look, nstyle, nx, ny, number_digits(ps["exp"], 7, 0, 0))
    ly += 0x11
    lg[:20] = list(e.bytes(STATUS_LABELS["level"], 20))
    draw_label(f, look, style, lx, ly, lg)
    ny += 0x11
    draw_number(f, look, nstyle, nx, ny, number_digits(ps["level"], 7, 0, 0))
    for which, first in (("hp", 0x07), ("mp", 0x0C)):
        lg[0] = first
        if which == "hp":
            lg[1], lg[2] = 0x0F, 0xFF                  # "HP", then "MP" off it
        ly += 0x11
        draw_label(f, look, style, lx, ly, lg)
        nx, ny = lx + 0x3F, ny + 0x11
        draw_number(f, look, nstyle, nx, ny, number_digits(ps[which], 4, 0, 0))
        nx += 0x1C
        draw_number(f, look, nstyle, nx, ny, [0x14, 0xFF])         # the stroke
        nx += 7
        draw_number(f, look, nstyle, nx, ny, number_digits(ps[which + "_max"], 4, 0, 0))
    lg[:8] = [0x0F, 0x16, 0x11, 0x3B, 0x16, 0x08, 0x12, 0xFF]
    ly += 0x11
    draw_label(f, look, style, lx, ly, lg)
    nx, ny = lx + 0x46, ly
    draw_number(f, look, nstyle, nx, ny, number_digits(ps["stat"], 5, 0, 0))
    nx = lx + 0x62
    draw_number(f, look, nstyle, nx, ny, number_digits(ps["wis"] + 1, 4, 0, 0))
    lg[0], lg[1] = 0x3B, 0xFF
    lx += 0x69
    draw_label(f, look, style, lx, ly, lg)
    lx = 0xA3
    lg[:4] = [0x0C, 0x00, 0x06, 0xFF]
    ly += 0x11
    draw_label(f, look, style, lx, ly, lg)
    lx += 0x23
    for i, (k, u, clut) in enumerate(SKILL_ICONS):
        if i in (2, 4):
            lx, ly = 0xC6, ly + 0xF
        elif i:
            lx += 0x31
        f.add(ICON_DEPTH, quad(lx, ly - 1, ICON_SIZE, ICON_SIZE, u, ICON_V, ICON_SIZE,
                               ICON_SIZE, ICON_PAGE, clut, rgb(0x80), False))
        nx, ny = lx, ly
        draw_number(f, look, nstyle, nx, ny, number_digits(ps["working"][k], 6, 0, 0))
    lx = 0xA3
    ly += 0x11
    lg[:12] = list(e.bytes(STATUS_LABELS["condition"], 12))
    draw_label(f, look, style, lx, ly, lg)
    nx, ny = lx + 0x38, ny + 0x11
    text = next(a for name, a in CONDITIONS if name is None or ps.get(name))
    draw_label(f, look, style, nx, ny, list(e.bytes(text, 12)))
    ly += 0x11
    lg[:10] = list(e.bytes(STATUS_LABELS["gold"], 10))
    draw_label(f, look, style, lx, ly, lg)
    nx, ny = lx + 0x4D, ny + 0x11
    draw_number(f, look, nstyle, nx, ny, number_digits(ps["gold"], 7, 0, 0))
    frame(f, look, e, 0x9B, 0x1A, 0x8D, 0xB4)


def status_of(ram):
    """What ui_status_page reads, out of a RAM snapshot."""
    def u16(a):
        return struct.unpack_from("<H", ram, a & 0x1FFFFF)[0]
    def s16(a):
        return struct.unpack_from("<h", ram, a & 0x1FFFFF)[0]
    def u32(a):
        return struct.unpack_from("<I", ram, a & 0x1FFFFF)[0]
    return {"exp": u32(0x801B24E4), "level": ram[0x801B24F0 & 0x1FFFFF],
            "hp": u16(0x801B24FC), "hp_max": u16(0x801B24FA), "mp": u16(0x801B2500),
            "mp_max": u16(0x801B24FE), "stat": u16(0x801B2524), "wis": u16(0x801B2530),
            "working": [u16(0x801B2526 + 2 * k) for k in range(5)],
            "paralyze": s16(0x801B2568), "curse": s16(0x801B255E),
            "slow": s16(0x801B2566), "poison": s16(0x801B255C), "dark": s16(0x801B2562),
            "gold": u32(0x801B2534)}


def main_page(e, look, ps, sel):
    """pause_menu's frame on its main page: the status page, then the six
    lines of page 0 (sub_800252f4(0, 6, sel, 0))."""
    f = Frame()
    status_page(f, look, e, ps)
    menu_page(f, look, e, 0, 6, sel)
    return f.order()


EQUIP_HEADINGS = 0x8007F230    # ten 24-byte rows: WEAPON, MAGIC .. ITEM 2, [] BUTTON
TAKE_OFF = 0x8007F338          # the chooser's last row, ten bytes
SPELL_NAMES = 0x80080430       # 24-byte rows, spell by spell
# ui_equip_page's line -> (first, last) of the things it lists, and the slot
# of equip_armour (0x8002bb84) it hands the choice to; line 0 is the weapon's
EQUIP_RANGES = {0: (0x00, 0x21), 2: (0x33, 0x3E), 3: (0x22, 0x29), 4: (0x2A, 0x32),
                5: (0x3F, 0x47), 6: (0x48, 0x50), 7: (0x51, 0x5E), 8: (0x51, 0x5E)}
ARMOUR_SLOT = {2: 4, 3: 0, 4: 1, 5: 2, 6: 3, 7: 5, 8: 6}
# equip_armour's slot -> the worn byte, 0x801b25d4 + n
WORN_OF_SLOT = {0: 0, 1: 1, 2: 3, 3: 4, 4: 2, 5: 5, 6: 6}


def equip_ids(st):
    """sub_8001c9c0's ten bytes: the weapon, magic A, then the shield, head,
    body, arms, feet and the two items (0x801b25d6, d4, d5, d7, d8, d9, da),
    and magic B or, with none, the button's item."""
    w = st["worn"]
    last = st["spell_b"] if st["spell_b"] != 0xFF else st["item_b"]
    return [st["weapon"], st["spell_a"], w[2], w[0], w[1], w[3], w[4], w[5], w[6], last]


def equip_names(e, st):
    """sub_8001c9c0 (0x8001c9c0): the ten lines' names -- a spell's from
    0x80080430 for magic A and for the button while it holds a spell, a
    thing's from 0x8007f620 otherwise, and 0xff for nothing."""
    out = []
    for i, ident in enumerate(equip_ids(st)):
        if ident == 0xFF:
            out.append([0xFF] + [0] * 23)
        elif i == 1 or (i == 9 and st["spell_b"] != 0xFF):
            out.append(list(e.bytes(SPELL_NAMES + 24 * ident, 24)))
        else:
            out.append(list(e.bytes(NAMES + 24 * ident, 24)))
    return out


def equipment_screen(e, look, st, sel):
    """sub_8001c7a8's frame: ui_panel(s, 3) -- no title, the ten headings
    from x 0x1b + 13 and the names beside them, from y 0x23."""
    s = {"tx": 0, "ty": 0x20, "title": [], "x": 0x1B, "y": 0x23, "rows": 10,
         "length": 0x18, "count": 10, "first": 0, "sel_row": sel,
         "names": [list(e.bytes(EQUIP_HEADINGS + 24 * i, 24)) for i in range(10)],
         "names2": equip_names(e, st), "counts": [0xFF] * 10}
    f = Frame()
    panel(f, look, e, s, 3)
    return f.order()


def equip_list(e, inventory, line, st):
    """ui_equip_page's list (0x8001cbb8) for one of the lines: what is
    carried in the line's range, and "TAKE OFF"; for an item line the other
    item line's thing counted one less. The answer has the place of what is
    worn now as "sel"."""
    inv = list(inventory)
    if line in (7, 8):
        other = st["worn"][6 if line == 7 else 5]
        if other != 0xFF:
            inv[other] -= 1
    first, last = EQUIP_RANGES[line]
    names, counts, ids = item_list(e, inv, first, last)
    names.append(list(e.bytes(TAKE_OFF, 10)) + [0] * 14)
    counts.append(0xFF)
    ids.append(0xFF)
    now = equip_ids(st)[line]
    sel = 0
    for i in range(len(ids) - 1):
        if ids[i] == now:
            sel = i
    lab = e.bytes(0x8007E67C + 2 * 28 + 4, 16)
    s = {"tx": 0x1F, "ty": 0x20, "title": list(lab), "x": 0x1B, "y": 0x93,
         "rows": 3, "length": 0x18, "count": len(ids), "names": names,
         "counts": counts, "ids": ids}
    place(s, sel)
    return s


SPELL_TABLE = 0x801B77EC
NO_SPELL = 0xFF


def spell_rows(e, table, first, last):
    """sub_8001c6c0: (names, costs, ids) of the spells first..last whose +0
    is 1 -- `table` the 96 records' bytes, a name off SPELL_NAMES and the
    cost off +0x16."""
    names, costs, ids = [], [], []
    for k in range(first, last + 1):
        rec = table[24 * k:24 * k + 24]
        if rec[0] == 1:
            names.append(list(e.bytes(SPELL_NAMES + 24 * k, 24)))
            costs.append(struct.unpack_from("<H", rec, 0x16)[0])
            ids.append(k)
    return names, costs, ids


def magic_list(e, table, st):
    """sub_8001d0c4's list: the attacking spells 0..0x16 unlocked, their MP
    beside them, and "TAKE OFF"; four rows from y 0x83, the selection on
    magic A."""
    names, costs, ids = spell_rows(e, table, 0, 0x16)
    names.append(list(e.bytes(TAKE_OFF, 10)) + [0] * 14)
    costs.append(-1)
    ids.append(NO_SPELL)
    lab = e.bytes(0x8007E67C + 2 * 28 + 4, 16)
    out = {"tx": 0x1F, "ty": 0x20, "title": list(lab), "x": 0x1B, "y": 0x83,
           "rows": 4, "length": 0x18, "count": len(ids), "names": names,
           "costs": costs, "counts": [0xFF] * len(ids), "ids": ids}
    sel = 0
    for i in range(len(ids) - 1):
        if ids[i] == st["spell_a"]:
            sel = i
            break
    place(out, sel)
    return out


def use_magic_list(e, table, selected=0):
    """menu_use_magic's list (0x8001c48c): the healing and protecting spells
    0x17..0x1e whose +0 is 1, their MP beside them, under ui_menu_label(0,
    1)'s title "USE MAGIC" -- four rows from y 0x83, no "TAKE OFF" -- the
    selection put back where gp+0x19 left it (list_place)."""
    names, costs, ids = spell_rows(e, table, 0x17, 0x1E)
    lab = e.bytes(0x8007E67C + 1 * 28 + 4, 16)
    out = {"tx": 0x1F, "ty": 0x20, "title": list(lab), "x": 0x1B, "y": 0x83,
           "rows": 4, "length": 0x18, "count": len(ids), "names": names,
           "costs": costs, "counts": [0xFF] * len(ids), "ids": ids}
    place(out, selected)
    return out


BUTTON_THINGS = (0x65, 0x92)


def button_list(e, inventory, table, st):
    """sub_8001d3a0's list: the things 0x65..0x92 carried (not 0x85), with
    their counts, then every spell unlocked with its MP, then "TAKE OFF"; the
    selection on the button's spell or, with none, its thing."""
    inv = list(inventory)
    inv[0x85] = 0
    names, counts, items = item_list(e, inv, *BUTTON_THINGS)
    spells = [NO_SPELL] * len(items)
    costs = [-1] * len(items)
    sn, sc, si = spell_rows(e, table, 0, 0x1E)
    names += sn
    counts += [0xFF] * len(si)
    costs += sc
    spells += si
    items += [0xFF] * len(si)
    names.append(list(e.bytes(TAKE_OFF, 10)) + [0] * 14)
    counts.append(0xFF)
    costs.append(-1)
    spells.append(NO_SPELL)
    items.append(0xFF)
    lab = e.bytes(0x8007E67C + 2 * 28 + 4, 16)
    out = {"tx": 0x1F, "ty": 0x20, "title": list(lab), "x": 0x1B, "y": 0x93,
           "rows": 3, "length": 0x18, "count": len(items), "names": names,
           "costs": costs, "counts": counts, "items": items, "spells": spells}
    sel = 0
    if not (st["spell_b"] == 0xFF and st["item_b"] == 0xFF):
        for i in range(len(items)):
            if (items[i] == st["item_b"]) if st["spell_b"] == 0xFF else (spells[i] == st["spell_b"]):
                sel = i
                break
    place(out, sel)
    return out


def list_screen(e, look, s, mode, prompt=None, word=0):
    """A chooser's frame: ui_panel(s, mode), or while ui_prompt(s, word,
    mode) asks, the list in mode | 0x8000 under the kind's word -- "USE",
    "STORE", "MOVE" -- and "CANCEL"."""
    f = Frame()
    if prompt is None:
        panel(f, look, e, s, mode)
    else:
        panel(f, look, e, s, mode | 0x8000)
        options(f, look, e, (45, 58, PROMPT_WORDS[word] + [0xFF]), (45, 84, CANCEL + [0xFF]),
                prompt)
    return f.order()


# --- the pad on a list: ui_menu_chrome and ui_prompt ----------------------

UP, DOWN, LEFT, RIGHT = 0x1000, 0x4000, 0x8000, 0x2000


def chrome(s, press, kind, confirm, cancel):
    """ui_menu_chrome's pad (0x800222fc): one word read, one thing done, in
    this order -- an empty list goes at any button; UP and DOWN move the
    selection (wrapping, the rows shown moving only at their edge); with kind
    2 (the storage) RIGHT raises the quantity (s["qty"], gp+0x48) while the
    chosen row's count holds one more, and with any kind LEFT lowers it to no
    less than 1; the confirm asks (mode 1), the cancel leaves (-1). Kind 1,
    the shops' gold check, is not here. Returns (mode, result): mode 0 or 1,
    result -0x63 for nothing or -1."""
    n = s["count"]
    if n == 0:
        return (0, -1) if press else (0, -0x63)
    rows = s["rows"]
    if press & UP:
        if s["sel"]:
            s["sel"] -= 1
            if s["sel_row"]:
                s["sel_row"] -= 1
            else:
                s["first"] -= 1
        else:
            s["sel"] = n - 1
            if n < rows:
                s["first"], s["sel_row"] = 0, n - 1
            else:
                s["first"], s["sel_row"] = n - rows, rows - 1
    elif press & DOWN:
        if s["sel"] < n - 1:
            s["sel"] += 1
            if s["sel_row"] == rows - 1:
                s["first"] += 1
            else:
                s["sel_row"] += 1
        else:
            s["sel"] = s["first"] = s["sel_row"] = 0
    elif press & RIGHT:
        if kind == 2 and s["counts"][s["sel"]] >= s["qty"] + 1:
            s["qty"] += 1
    elif press & LEFT:
        if kind and s["qty"] >= 2:
            s["qty"] -= 1
    elif press & confirm:
        return 1, -0x63
    elif press & cancel:
        return 0, -1
    return 0, -0x63


def prompt_press(sel, press, confirm, cancel):
    """One word of ui_prompt's loop (0x80024c70): UP or DOWN turns between
    its two answers, the confirm answers -- 0 for the first, -1 for the
    second -- and the cancel answers -1. (sel, answer or None)."""
    if press & (UP | DOWN):
        return 1 - sel, None
    if press & confirm:
        return sel, -sel
    if press & cancel:
        return sel, -1
    return sel, None


# --- storage: item_menu, its two lists --------------------------------------

STORE_LAST = 0x95              # the two lists run over 0..0x95


def store_rows(e, inventory, st, first=0, last=STORE_LAST):
    """item_list_unheld (0x8001af88): item_list's (names, counts, ids), but a thing worn or
    held -- the weapon (0x801b25af), the seven worn bytes 0x801b25d4..da,
    the button's thing (0x801b25ad) -- counted one less, two less when both
    item slots (d9, da) hold it, and left out when that leaves none."""
    held = [st["weapon"]] + list(st["worn"]) + [st["item_b"]]
    names, counts, ids = [], [], []
    for i in range(first, last + 1):
        c = inventory[i]
        if c == 0:
            continue
        if i in held:
            c = (c - 2 if i == st["worn"][5] == st["worn"][6] else c - 1) & 0xFF
        if c == 0:
            continue
        names.append(list(e.bytes(NAMES + 24 * i, 24)))
        counts.append(c)
        ids.append(i)
    return names, counts, ids


def storage_list(e, which, inventory, st=None, cursor=0):
    """item_menu's two lists, under ui_menu_label(2, which): "STORE" (0,
    menu_store) the things carried as item_list_unheld counts them, "TAKE OUT"
    (1, menu_take_out) the things in storage (inventory_b) as item_list does;
    three rows from y 0x93, the selection where gp+0x1a or gp+0x1b left it,
    the quantity 1 as ui_menu_label leaves it."""
    if which == 0:
        names, counts, ids = store_rows(e, inventory, st)
    else:
        names, counts, ids = item_list(e, inventory, 0, STORE_LAST)
    lab = e.bytes(0x8007E67C + 252 * 2 + 28 * which + 4, 16)
    out = {"tx": 0x1F, "ty": 0x20, "title": list(lab), "x": 0x1B, "y": 0x93, "rows": 3,
           "length": 0x18, "count": len(ids), "names": names, "counts": counts,
           "costs": [-1] * len(ids), "ids": ids, "which": which, "qty": 1,
           "mode": 0, "prompt": 0}
    place(out, cursor)
    return out


def storage_press(s, press, inv_a, inv_b, confirm, cancel):
    """One pad word on the storage's list (menu_store for which 0,
    menu_take_out for 1): while the list is up (s["mode"] 0) the list's
    ui_menu_chrome with kind 2 -- its confirm refused, back to the list with
    sound 0xe, when the chosen row's count is under the quantity or the other
    side would reach 100 -- and while ui_prompt(s, 1 or 0xa, 7) asks (mode
    1, s["prompt"] the answer lit) "STORE" or "MOVE", and "CANCEL" back to
    the list. The first answer moves the quantity across; `inv_a`, `inv_b`
    change in place. None while the screen is up, -1 when it goes, or the id
    of the thing moved."""
    if s["mode"] == 1:
        s["prompt"], ans = prompt_press(s["prompt"], press, confirm, cancel)
        if ans is None:
            return None
        if ans == 0:
            i, q = s["ids"][s["sel"]], s["qty"]
            if s["which"] == 0:
                inv_a[i], inv_b[i] = (inv_a[i] - q) & 0xFF, (inv_b[i] + q) & 0xFF
            else:
                inv_a[i], inv_b[i] = (inv_a[i] + q) & 0xFF, (inv_b[i] - q) & 0xFF
            return i
        s["mode"] = 0
        return None
    mode, result = chrome(s, press, 2, confirm, cancel)
    if result == -1:
        return -1
    if mode == 1:
        k = s["sel"]
        other = inv_b if s["which"] == 0 else inv_a
        if not (s["counts"][k] < s["qty"] or other[s["ids"][k]] + s["qty"] >= 0x64):
            s["mode"], s["prompt"] = 1, 0
    return None


def storage_run(s, presses, inv_a, inv_b, confirm, cancel):
    """storage_press over `presses` until the screen goes: (how it ended --
    None while still up, -1 left, or the id moved -- and the words read)."""
    used = 0
    for press in presses:
        used += 1
        end = storage_press(s, press, inv_a, inv_b, confirm, cancel)
        if end is not None:
            return end, used
    return None, used


def _lay_list(ram, s, at=0x801F0000):
    """A list record as ui_menu_label leaves it and the page fills it, in
    free RAM: the title, x, y, count, rows, first, selection, its row, the
    length, and the names, counts and costs it points at."""
    o = at & 0x1FFFFF
    rec = bytearray(0x34)
    struct.pack_into("<hh", rec, 0, s["tx"], s["ty"])
    rec[4:4 + len(s["title"])] = bytes(s["title"])
    rec[0x1C:0x24] = bytes([s["x"], s["y"], s["count"], s["rows"], s["first"],
                            s["sel"], s["sel_row"], s["length"]])
    names = o + 0x100
    counts = names + 24 * len(s["names"]) + 8
    costs = counts + len(s["counts"]) + 8
    costs += (-costs) & 3
    struct.pack_into("<IIII", rec, 0x24, 0x80000000 | names, 0, 0x80000000 | counts,
                     0x80000000 | costs)
    ram[o:o + len(rec)] = rec
    for i, n in enumerate(s["names"]):
        ram[names + 24 * i:names + 24 * i + 24] = bytes(n[:24]) + bytes(24 - len(n[:24]))
    ram[counts:counts + len(s["counts"])] = bytes(s["counts"])
    for i, c in enumerate(s["costs"]):
        struct.pack_into("<i", ram, costs + 4 * i, c)
    return at


class _Built(Exception):
    """menu_use_magic has built its list: the stop at its next call."""


def game_use_magic_list(ram, table, cursor):
    """menu_use_magic's own start (0x8001c48c up to its call of 0x80027bb4,
    after list_place), run by tools/mipsrun.py over `ram` with the spell
    table's records `table` and gp+0x19 = `cursor`: the list it built on
    its stack, read back as use_magic_list's fields."""
    import mipsrun
    cpu = mipsrun.menu_cpu(ram)
    cpu.ram[SPELL_TABLE & 0x1FFFFF:(SPELL_TABLE & 0x1FFFFF) + len(table)] = table
    cpu.wr(GP + 0x19, 1, cursor)
    got = {}

    def built(c):
        sp = c.r[29]
        r = bytes(c.rd(sp + 0x18 + i, 1) for i in range(0x34))
        n = r[0x1E]
        names_at, costs_at = struct.unpack_from("<I", r, 0x24)[0], struct.unpack_from("<I", r, 0x30)[0]
        got.update({
            "tx": struct.unpack_from("<h", r, 0)[0], "ty": struct.unpack_from("<h", r, 2)[0],
            "title": list(r[4:20]), "x": r[0x1C], "y": r[0x1D], "count": n,
            "rows": r[0x1F], "first": r[0x20], "sel": r[0x21], "sel_row": r[0x22],
            "length": r[0x23],
            "names": [[c.rd(names_at + 24 * k + i, 1) for i in range(24)] for k in range(n)],
            "costs": [mipsrun.s32(c.rd(costs_at + 4 * k, 4)) for k in range(n)],
            "ids": [c.rd(sp + 0x280 + k, 1) for k in range(n)]})
        raise _Built

    cpu.hooks[0x80027BB4] = built
    try:
        cpu.call(0x8001C48C)
    except _Built:
        pass
    return got


def panel_check(out=sys.stdout, n=40):
    """The MAGIC and BUTTON lists, ui_panel modes 4 and 0x10, and the USE
    MAGIC screen's, mode 2, with their prompts' 0x8000, against the game's
    own ui_panel run by tools/mipsrun.py over menu1's RAM with each list laid
    in: the 2D primitives alike."""
    import random
    import mipsrun
    path = os.path.join(ROOT, "out", "snap", "menu1.ram")
    if not os.path.exists(path):
        print("  no menu1 snapshot to run ui_panel over", file=out)
        return True
    e = exe()
    base = bytearray(open(path, "rb").read())
    t = SPELL_TABLE & 0x1FFFFF
    tally = {}
    first = None

    def run(which, s, mode, pulse, cursor=None):
        # with a cursor, the game's own list_place puts the selection, the
        # first row and the bar's row before ui_panel draws -- over what the
        # model's place laid, which then has to agree with it
        nonlocal first
        ram = bytearray(base)
        at = _lay_list(ram, s)
        calls = [] if cursor is None else [(0x80027728, at, cursor)]
        prims, _cpu = mipsrun.frame(ram, calls + [(0x80025468, at, mode)], pulse)
        look = Look(ram)
        look.pulse = pulse
        f = Frame()
        panel(f, look, e, s, mode)
        got = mipsrun.two_d(prims)
        want = [(d, p) for d, p in f.order()]
        same = got == want
        ok, runs = tally.get(which, (0, 0))
        tally[which] = (ok + same, runs + 1)
        if not same and first is None:
            k = next((j for j, (a, b) in enumerate(zip(got, want)) if a != b), min(len(got), len(want)))
            first = (f"{which} mode {mode:#x}: {len(got)} primitives, the model {len(want)}; "
                     f"at {k}: game {got[k] if k < len(got) else None} model {want[k] if k < len(want) else None}")

    rng = random.Random(0x7A4E1)
    for i in range(n):
        table = bytearray(base[t:t + 24 * 96])
        for k in range(31):
            table[24 * k] = 1 if rng.randrange(3) else 0
        inv = [0] * 150
        for k in rng.sample(range(0x65, 0x93), rng.randrange(0, 12)):
            inv[k] = rng.randrange(1, 99)
        st = {"spell_a": rng.choice((0xFF, rng.randrange(0, 0x17))),
              "spell_b": rng.choice((0xFF, 0xFF, rng.randrange(0, 0x1F))),
              "item_b": rng.choice((0xFF, rng.randrange(0x65, 0x93)))}
        for which in ("magic", "button"):
            s = magic_list(e, table, st) if which == "magic" else button_list(e, inv, table, st)
            if s["count"] > s["rows"] and rng.randrange(2):
                place(s, rng.randrange(s["count"]))
            mode = 4 if which == "magic" else 0x10
            if rng.randrange(3) == 0:
                mode |= 0x8000
            run(which, s, mode, rng.randrange(0x60))
    # USE MAGIC on a generator of its own, so the lists above stay the ones
    # they were: eight spells 0x17..0x1e, each unlocked or not -- none, some
    # or all -- and the cursor anywhere gp+0x19 can hold it, placed by the
    # game's own list_place
    rng = random.Random(0x7A4E2)
    built_ok = 0
    first_built = None
    for i in range(n):
        table = bytearray(base[t:t + 24 * 96])
        p = (0, 0.5, 1)[i % 3]
        for k in range(0x17, 0x1F):
            table[24 * k] = 1 if rng.random() < p else 0
        cursor = rng.randrange(0x100) if i % 2 else rng.randrange(9)
        s = use_magic_list(e, table, cursor)
        g = game_use_magic_list(base, table, cursor)
        keys = [k for k in g if k != "counts"]
        built_ok += all(g[k] == s[k] for k in keys)
        if first_built is None and not all(g[k] == s[k] for k in keys):
            k = next(k for k in keys if g[k] != s[k])
            first_built = f"use magic's list, {k}: game {g[k]} model {s[k]}"
        mode = 2 | (0x8000 if rng.randrange(3) == 0 else 0)
        run("use magic", s, mode, rng.randrange(0x60), cursor)
    # the storage's lists, mode 7 -- the count and the quantity plate --
    # with the quantity (gp+0x48) laid in too
    rng = random.Random(0x7A4E3)
    for i in range(n):
        which = i & 1
        inv = [0] * 150
        for k in rng.sample(range(0x96), rng.randrange(0, 12)):
            inv[k] = rng.randrange(1, 100)
        st = {"weapon": 0xFF, "worn": [0xFF] * 7, "item_b": 0xFF}
        s = storage_list(e, which, inv, st, rng.randrange(8))
        s["qty"] = rng.choice((1, 2, rng.randrange(1, 100), 99))
        base_qty = bytearray(base)
        struct.pack_into("<I", base_qty, (GP + 0x48) & 0x1FFFFF, s["qty"])
        saved, base = base, base_qty
        run("storage", s, 7 | (0x8000 if rng.randrange(3) == 0 else 0), rng.randrange(0x60))
        base = saved
    ok = sum(v[0] for v in tally.values())
    runs = sum(v[1] for v in tally.values())
    print(f"  the MAGIC, BUTTON, USE MAGIC and storage lists, ui_panel's modes 4, 0x10, 2 and 7 as "
          f"the game's own draws them over menu1: {ok} of {runs} frames primitive for "
          f"primitive (" + ", ".join(f"{w} {a} of {b}" for w, (a, b) in tally.items()) + ")",
          file=out)
    if first:
        print("  first difference: " + first, file=out)
    print(f"  the USE MAGIC list as the game's own menu_use_magic builds it, up to "
          f"list_place: {built_ok} of {n}", file=out)
    if first_built:
        print("  first difference: " + first_built, file=out)
    return ok == runs and built_ok == n


class _Out(Exception):
    """The scripted pad has no more words: the screen is still up."""


INVENTORY_B = 0x800C867E
STORAGE_SCREENS = (0x8001DEE4, 0x8001E1B4)      # "store", "take out"


def game_storage_run(base, which, inv_a, inv_b, st, cursor, presses):
    """menu_store (which 0) or menu_take_out (1) run whole by
    tools/mipsrun.py over `base`, the inventories, the worn and held bytes and
    the cursor (gp+0x1a, gp+0x1b) laid in, each pad_read_latch answered with
    the next of `presses` and the drawing, the models and the guide stood in
    for: (returned, words read, inventory_a, inventory_b, gp+0x48, the
    cursor)."""
    import mipsrun
    cpu = mipsrun.menu_cpu(base)
    a, b = INVENTORY_A & 0x1FFFFF, INVENTORY_B & 0x1FFFFF
    cpu.ram[a:a + 150] = bytes(inv_a)
    cpu.ram[b:b + 150] = bytes(inv_b)
    cpu.ram[0x1B25AF] = st["weapon"]
    cpu.ram[0x1B25AD] = st["item_b"]
    cpu.ram[0x1B25D4:0x1B25DB] = bytes(st["worn"])
    where = GP + 0x1A + which
    cpu.wr(where, 1, cursor)
    script = list(presses)
    read = [0]

    def latch(c):
        if not script:
            raise _Out
        read[0] += 1
        return script.pop(0)

    cpu.hooks[0x800279A4] = latch                      # pad_read_latch
    for at in (0x80027A40, 0x800279D8,                 # pad_wait_release, pad_drain_press
               0x80026FE4, 0x800270F8,                 # frame_begin, frame_end
               0x80025468, 0x80025B24,                 # ui_panel, the prompt's answers
               0x80025BE8, 0x80027A9C, 0x80024F88):    # the model, its load, the guide
        cpu.hooks[at] = lambda c: 0
    try:
        cpu.call(STORAGE_SCREENS[which])
        returned = True
    except _Out:
        returned = False
    return (returned, read[0], list(cpu.ram[a:a + 150]), list(cpu.ram[b:b + 150]),
            cpu.rd(GP + 0x48, 4), cpu.rd(where, 1))


STORAGE_ARRAYS = ((0x50, 0xE90, 0xF28), (0x50, 0x770, 0x808))   # names, counts, ids on each frame


def game_storage_list(base, which, inv_a, inv_b, st, cursor):
    """The list menu_store or menu_take_out builds, run by tools/mipsrun.py
    to its first ui_menu_chrome and read off its stack as storage_list's
    fields."""
    import mipsrun
    cpu = mipsrun.menu_cpu(base)
    a, b = INVENTORY_A & 0x1FFFFF, INVENTORY_B & 0x1FFFFF
    cpu.ram[a:a + 150] = bytes(inv_a)
    cpu.ram[b:b + 150] = bytes(inv_b)
    cpu.ram[0x1B25AF] = st["weapon"]
    cpu.ram[0x1B25AD] = st["item_b"]
    cpu.ram[0x1B25D4:0x1B25DB] = bytes(st["worn"])
    cpu.wr(GP + 0x1A + which, 1, cursor)
    got = {}
    names, counts, ids = STORAGE_ARRAYS[which]

    def built(c):
        sp = c.r[29]
        r = bytes(c.rd(sp + 0x18 + i, 1) for i in range(0x34))
        n = r[0x1E]
        got.update({
            "tx": struct.unpack_from("<h", r, 0)[0], "ty": struct.unpack_from("<h", r, 2)[0],
            "title": list(r[4:20]), "x": r[0x1C], "y": r[0x1D], "count": n,
            "rows": r[0x1F], "first": r[0x20], "sel": r[0x21], "sel_row": r[0x22],
            "length": r[0x23],
            "names": [[c.rd(sp + names + 24 * k + i, 1) for i in range(24)] for k in range(n)],
            "counts": [c.rd(sp + counts + k, 1) for k in range(n)],
            "ids": [c.rd(sp + ids + k, 1) for k in range(n)],
            "qty": c.rd(GP + 0x48, 4)})
        raise _Out

    cpu.hooks[0x800222FC] = built                     # ui_menu_chrome
    cpu.hooks[0x80027A9C] = lambda c: 0               # the model's load
    try:
        cpu.call(STORAGE_SCREENS[which])
    except _Out:
        pass
    return got


def storage_check(out=sys.stdout, n=200):
    """The storage's two screens, against the game's own run whole over
    menu1's RAM: random carried and stored things -- some worn or held, some
    in both item slots, some near 99 -- and a random run of pad words; how
    it ends, how many words it read, both inventories, the quantity and the
    cursor alike."""
    import random
    path = os.path.join(ROOT, "out", "snap", "menu1.ram")
    if not os.path.exists(path):
        print("  no menu1 snapshot to run the storage over", file=out)
        return True
    e = exe()
    base = bytearray(open(path, "rb").read())
    confirm = struct.unpack_from("<I", base, (GP + 0x38) & 0x1FFFFF)[0]
    cancel = struct.unpack_from("<I", base, (GP + 0x3C) & 0x1FFFFF)[0]
    rng = random.Random(0x5704A6E)
    ok = 0
    first = None
    ends = {"left": 0, "moved": 0, "up": 0}
    built_ok = 0
    first_built = None
    for i in range(n):
        which = i & 1
        inv_a, inv_b = [0] * 150, [0] * 150
        for k in rng.sample(range(0x96), rng.randrange(0, 14)):
            inv_a[k] = rng.choice((1, 2, 3, rng.randrange(1, 100), 98, 99))
        for k in rng.sample(range(0x96), rng.randrange(0, 14)):
            inv_b[k] = rng.choice((1, 2, rng.randrange(1, 100), 97, 99))
        if rng.randrange(2):
            # the other side nearly full of one listed thing, for the refusal
            mine = [k for k in range(0x96) if (inv_b if which else inv_a)[k]]
            if mine:
                (inv_a if which else inv_b)[rng.choice(mine)] = rng.randrange(95, 100)
        carried = [k for k in range(0x96) if inv_a[k]] or [0xFF]
        worn = [rng.choice(carried + [0xFF] * 3) for _ in range(7)]
        if rng.randrange(4) == 0:
            worn[6] = worn[5]
        st = {"weapon": rng.choice(carried + [0xFF]), "worn": worn,
              "item_b": rng.choice(carried + [0xFF] * 3)}
        cursor = rng.randrange(0x100) if rng.randrange(4) == 0 else rng.randrange(6)
        words = [UP, DOWN, LEFT, RIGHT, RIGHT, confirm, confirm, cancel]
        presses = [rng.choice(words) for _ in range(rng.randrange(1, 16))]
        if rng.randrange(4) == 0:
            # the quantity raised on one row, then another chosen: the refusal
            presses = ([RIGHT] * rng.randrange(2, 7) + [rng.choice((UP, DOWN)), confirm]
                       + presses)
        g = game_storage_run(base, which, inv_a, inv_b, st, cursor, presses)
        s = storage_list(e, which, inv_b if which else inv_a, st, cursor)
        gl = game_storage_list(base, which, inv_a, inv_b, st, cursor)
        keys = [k for k in gl if k in s]
        built_ok += all(gl[k] == s[k] for k in keys)
        if first_built is None and not all(gl[k] == s[k] for k in keys):
            k = next(k for k in keys if gl[k] != s[k])
            first_built = (f"case {i} ({'take out' if which else 'store'})'s list, {k}: "
                           f"game {gl[k]} model {s[k]}")
        ma, mb = list(inv_a), list(inv_b)
        end, used = storage_run(s, presses, ma, mb, confirm, cancel)
        m = (end is not None, used, ma, mb, s["qty"], s["sel"])
        same = g == m
        ok += same
        ends["up" if end is None else "left" if end == -1 else "moved"] += 1
        if not same and first is None:
            k = next(j for j in range(6) if g[j] != m[j])
            name = ("returned", "words read", "inventory_a", "inventory_b", "quantity", "cursor")[k]
            first = f"case {i} ({'take out' if which else 'store'}), {name}: game {g[k]} model {m[k]}"
    print(f"  the storage's STORE and TAKE OUT, as the game's own menu_store and "
          f"menu_take_out run them press by press over menu1: {ok} of {n} runs alike "
          f"({ends['moved']} moved something, {ends['left']} left, {ends['up']} still up)",
          file=out)
    if first:
        print("  first difference: " + first, file=out)
    print(f"  their lists as the game's own builds them, to the first ui_menu_chrome: "
          f"{built_ok} of {n}", file=out)
    if first_built:
        print("  first difference: " + first_built, file=out)
    return ok == n and built_ok == n


def place(s, sel):
    """sub_80027728: the index held to the list, the first row shown and the
    bar's row."""
    n = s["count"]
    sel = min(sel, n - 1) if n else 0
    s["sel"] = sel
    if n - sel < s["rows"]:
        if n < s["rows"]:
            s["first"], s["sel_row"] = 0, sel
        else:
            s["first"] = n - s["rows"]
            s["sel_row"] = sel - s["first"]
    else:
        s["first"], s["sel_row"] = sel, 0


def equip_list_screen(e, look, s, prompt=None):
    """ui_equip_page's frame, ui_panel(s, 5): the list with its counts and
    three buttons -- or, while ui_prompt(s, 5, 5) asks, the list in mode
    5 | 0x8000 under "USE" and "CANCEL"."""
    f = Frame()
    if prompt is None:
        panel(f, look, e, s, 5)
    else:
        panel(f, look, e, s, 5 | 0x8000)
        options(f, look, e, (45, 58, PROMPT_WORDS[0] + [0xFF]), (45, 84, CANCEL + [0xFF]),
                prompt)
    return f.order()


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
    place(s, selected)
    f = Frame()
    panel(f, look, e, s, 1)
    return f.order()


def pages_used(e):
    """The (texture page, CLUT) pairs the menus draw from."""
    out = set()
    for a in (LABEL_STYLE, NUMBER_STYLE, SMALL_STYLE):
        t, c = record(e, a)[:2]
        out.add((t, c))
    for _k, _u, clut in SKILL_ICONS:                     # ui_status_page's icons
        out.add((ICON_PAGE, clut))
    for k in range(18):
        t, c = record(e, RECORDS + 12 * k)[:2]
        if t:
            out.add((t, c))
    return sorted(out)


def export(out_dir):
    """ui.json and ui/ for godot/menu.gd: the descriptors, the label table,
    the item names, the legend's words, and every page the menus draw from
    under each CLUT, split as hud.py splits them: the texels drawn solid, and
    the ones with STP that a semi-transparent primitive blends."""
    import json
    import rtim
    import tim
    e = exe()
    vram = rtim.level_vram(0)
    os.makedirs(os.path.join(out_dir, "ui"), exist_ok=True)
    pages = {}
    for tpage, clut in pages_used(e):
        key = f"{tpage}_{clut:04x}"
        stp = [q[3] == 128 for q in rtim.page4(vram, tpage & ~0x60, clut, semi=True)]
        plain = rtim.page4(vram, tpage & ~0x60, clut, semi=False)
        clear = (0, 0, 0, 0)
        solid = [clear if t else p for p, t in zip(plain, stp)]
        blend = [p if t else clear for p, t in zip(plain, stp)]
        tim.write_png(os.path.join(out_dir, "ui", key + "_solid.png"), 256, 256, solid)
        tim.write_png(os.path.join(out_dir, "ui", key + "_semi.png"), 256, 256, blend)
        pages[key] = {"tpage": tpage, "clut": clut, "abr": (tpage >> 5) & 3}
    recs = {hex(a): list(record(e, a)) for a in
            [LABEL_STYLE, NUMBER_STYLE, SMALL_STYLE, 0x8007E778, 0x8007E794] +
            [RECORDS + 12 * k for k in range(18)]}
    labels = []
    for page in range(10):
        rows = []
        for line in range(9):
            a = 0x8007E67C + 252 * page + 28 * line
            x, y = struct.unpack("<hh", e.bytes(a, 4))
            rows.append([x, y, list(e.bytes(a + 4, 16))])
        labels.append(rows)
    doc = {"_note": "the menus' descriptors, labels and pages; tools/ui.py",
           "records": recs, "labels": labels, "page_minus": list(
               struct.unpack("<hh", e.bytes(0x8007E660, 4))),
           "names": [list(e.bytes(NAMES + 24 * i, 24)) for i in range(150)],
           "words": {"select": gp_string(e, 0x7C), "guide": gp_string(e, 0xA4),
                     "return": gp_string(e, 0x74)},
           "pages": pages,
           # ui_status_page's words: its four labels and the six conditions
           # ui_ratings_page's two headings, OFFENSE and DEFENSE
           "ratings": {"offense": list(e.bytes(0x8007F380, 10)),
                       "defense": list(e.bytes(0x8007F398, 10))},
           # the equipment screens': the ten headings, "TAKE OFF", the spells' names
           "equip": {"headings": [list(e.bytes(EQUIP_HEADINGS + 24 * i, 24))
                                  for i in range(10)],
                     "take_off": list(e.bytes(TAKE_OFF, 10)),
                     "spells": [list(e.bytes(SPELL_NAMES + 24 * i, 24)) for i in range(31)]},
           "status": {"labels": {k: list(e.bytes(a, {"experience": 20, "level": 20,
                                                       "condition": 12, "gold": 10}[k]))
                                 for k, a in STATUS_LABELS.items()},
                      "conditions": [[name or "", list(e.bytes(a, 12))]
                                     for name, a in CONDITIONS]},
           # what the snapshots hold at gp + 0x58..0x68 and + 0x40, + 0x44
           "look": {"box": 0x78, "text": 0x80, "shadow": 0x30, "confirm": 3,
                    "cancel": 1, "semi": 1, "bright": 0x80},
           "cases": export_cases(e)}
    path = os.path.join(out_dir, "ui.json")
    with open(path, "w") as fh:
        json.dump(doc, fh, separators=(",", ":"))
    return path


def export_cases(e):
    """The primitive lists of a few screens, for godot/selftest.gd to match."""
    look = Look()
    inv = [0] * 150
    inv[104], inv[105], inv[107], inv[147] = 2, 1, 1, 12
    cases = []
    for sel in (0, 1, 3):
        for pulse in (0x10, 0x39):
            look.pulse = pulse
            cases.append({"screen": "use_item", "inventory": {"104": 2, "105": 1,
                          "107": 1, "147": 12}, "sel": sel, "pulse": pulse,
                          "prims": [[d, p] for d, p in use_item_screen(e, look, inv, sel)]})
    for sel in (0, 1):
        look.pulse = 0x22
        f = Frame()
        options(f, look, e, (45, 58, PROMPT_WORDS[0] + [0xFF]), (45, 84, CANCEL + [0xFF]), sel)
        cases.append({"screen": "prompt", "sel": sel, "pulse": 0x22,
                      "prims": [[d, p] for d, p in f.order()]})
    for sel in (0, 3, 5):
        look.pulse = 0x44
        f = Frame()
        menu_page(f, look, e, 0, 6, sel)
        cases.append({"screen": "menu", "sel": sel, "pulse": 0x44,
                      "prims": [[d, p] for d, p in f.order()]})
    for st, sel in EQUIP_CASES:
        look.pulse = 0x17
        cases.append({"screen": "equip", "equip": st, "sel": sel, "pulse": 0x17,
                      "prims": [[d, p] for d, p in equipment_screen(e, look, st, sel)]})
    inv = [0] * 150
    for k, v in EQUIP_INVENTORY.items():
        inv[int(k)] = v
    for line, prompt in ((0, None), (4, None), (7, None), (3, 0), (8, 1)):
        st = EQUIP_CASES[1][0]
        look.pulse = 0x31
        s = equip_list(e, inv, line, st)
        cases.append({"screen": "equip_list", "equip": st, "line": line,
                      "inventory": EQUIP_INVENTORY, "prompt": prompt, "pulse": 0x31,
                      "sel": s["sel"],
                      "prims": [[d, p] for d, p in equip_list_screen(e, look, s, prompt)]})
    # the MAGIC and BUTTON lines' lists (whose drawing the game's own ui_panel
    # holds, panel_check), from the disc's spell table with some unlocked
    import spells as _spells
    table = bytearray(b"".join(_spells.rows()))
    for k in (0, 6, 0xD, 0x13, 0x17, 0x1A, 0x1D, 0x1E):
        table[24 * k] = 1
    binv = [0] * 150
    for k, v in ((0x68, 3), (0x6B, 1), (0x85, 1), (0x92, 2)):
        binv[k] = v
    for st in ({"spell_a": 0xD, "spell_b": 0x1D, "item_b": 0xFF},
               {"spell_a": 0xFF, "spell_b": 0xFF, "item_b": 0x6B},
               {"spell_a": 0x13, "spell_b": 0xFF, "item_b": 0xFF}):
        for prompt in (None, 0):
            look.pulse = 0x2C
            ms = magic_list(e, table, st)
            cases.append({"screen": "magic_list", "table": table.hex(), "equip": st,
                          "prompt": prompt, "sel": ms["sel"], "pulse": 0x2C,
                          "prims": [[d, p] for d, p in list_screen(e, look, ms, 4, prompt)]})
            bs = button_list(e, binv, table, st)
            cases.append({"screen": "button_list", "table": table.hex(), "equip": st,
                          "inventory": {str(k): v for k, v in enumerate(binv) if v},
                          "prompt": prompt, "sel": bs["sel"], "pulse": 0x2C,
                          "prims": [[d, p] for d, p in list_screen(e, look, bs, 0x10, prompt)]})
    # the USE MAGIC screen's list, mode 2 (both of which the game's own
    # menu_use_magic and ui_panel hold, panel_check), at a few cursors
    for cursor, prompt in ((0, None), (2, None), (5, 0), (0xC8, 1)):
        look.pulse = 0x1B
        us = use_magic_list(e, table, cursor)
        cases.append({"screen": "use_magic", "table": table.hex(), "cursor": cursor,
                      "prompt": prompt, "sel": us["sel"], "pulse": 0x1B,
                      "prims": [[d, p] for d, p in list_screen(e, look, us, 2, prompt)]})
    # the storage's two lists, mode 7 (which the game's own ui_panel holds,
    # panel_check), their prompts, and runs of pad words through
    # storage_press (which the game's own two screens hold, storage_check)
    sinv_a, sinv_b = [0] * 150, [0] * 150
    for k, v in ((0, 1), (0x22, 1), (0x33, 2), (0x68, 5), (0x6B, 1), (0x6D, 98), (0x85, 1),
                 (0x92, 3)):
        sinv_a[k] = v
    for k, v in ((0x68, 96), (0x6D, 2), (0x77, 1), (0x8B, 1)):
        sinv_b[k] = v
    sst = {"weapon": 0, "worn": [0x22, 0xFF, 0x33, 0xFF, 0xFF, 0x6B, 0x6B], "item_b": 0x92}
    for which, cursor, qty, prompt in ((0, 0, 1, None), (0, 4, 3, None), (0, 1, 2, 0),
                                       (1, 0, 1, None), (1, 3, 12, 1)):
        look.pulse = 0x3A
        ss = storage_list(e, which, sinv_b if which else sinv_a, sst, cursor)
        ss["qty"] = qty
        cases.append({"screen": "storage", "which": which, "cursor": cursor, "qty": qty,
                      "inventory": {str(k): v for k, v in enumerate(sinv_b if which else sinv_a) if v},
                      "equip": sst, "prompt": prompt, "sel": ss["sel"], "pulse": 0x3A,
                      "prims": [[d, p] for d, p in list_screen(e, look, ss, 7, prompt,
                                                             0xA if which else 1)]})
    import random
    rng = random.Random(0x5704A6F)
    runs = []
    for i in range(40):
        which = i & 1
        words = [UP, DOWN, LEFT, RIGHT, RIGHT, 0x40, 0x40, 0x20]
        presses = [rng.choice(words) for _ in range(rng.randrange(1, 14))]
        if i % 4 == 0:
            presses = [RIGHT] * rng.randrange(2, 7) + [rng.choice((UP, DOWN)), 0x40] + presses
        cursor = rng.randrange(6)
        ma, mb = list(sinv_a), list(sinv_b)
        ss = storage_list(e, which, mb if which else ma, sst, cursor)
        end, used = storage_run(ss, presses, ma, mb, 0x40, 0x20)
        runs.append({"which": which, "cursor": cursor, "presses": presses,
                     "end": -0x63 if end is None else end, "used": used, "qty": ss["qty"],
                     "sel": ss["sel"], "inventory_a": ma, "inventory_b": mb})
    cases.append({"screen": "storage_runs", "inventory_a": sinv_a, "inventory_b": sinv_b,
                  "equip": sst, "runs": runs, "sel": 0, "pulse": 0, "prims": []})
    # ui_ratings_page as the game's own code draws it, run over menu1's RAM by
    # tools/mipsrun.py -- when that snapshot is here
    menu1 = os.path.join(ROOT, "out", "snap", "menu1.ram")
    if os.path.exists(menu1):
        import mipsrun
        ram = open(menu1, "rb").read()
        for off, dfn, prims in mipsrun.ratings_cases(ram):
            cases.append({"screen": "ratings", "offense": off, "defense": dfn,
                          "sel": 0, "pulse": 0, "prims": [[d, p] for d, p in prims],
                          "look": "menu1"})
        for page in (1, 2):
            for sel, pulse, prims in mipsrun.page_cases(ram, page, 2):
                cases.append({"screen": "page", "page": page, "n": 2, "sel": sel,
                              "pulse": pulse, "prims": [[d, p] for d, p in prims],
                              "look": "menu1"})
    for ps in STATUS_CASES:
        look.pulse = 0x2A
        cases.append({"screen": "main", "sel": 2, "pulse": 0x2A, "status": ps,
                      "prims": [[d, p] for d, p in main_page(e, look, ps, 2)]})
    return cases


# A fresh character's things, and a well-dressed one's, for the equipment
# screens; and what the second carries
EQUIP_CASES = [
    ({"weapon": 0, "spell_a": 0x1D, "spell_b": 0xFF, "item_b": 0xFF,
      "worn": [0xFF, 42, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]}, 0),
    ({"weapon": 5, "spell_a": 0x1D, "spell_b": 0xFF, "item_b": 0x68,
      "worn": [34, 43, 52, 63, 72, 81, 0xFF]}, 4),
    ({"weapon": 0xFF, "spell_a": 0xFF, "spell_b": 0x13, "item_b": 0x68,
      "worn": [0xFF] * 7}, 9),
]
EQUIP_INVENTORY = {"0": 1, "5": 1, "9": 1, "34": 1, "35": 1, "42": 1, "43": 1,
                   "52": 1, "63": 1, "72": 1, "81": 2, "83": 1, "104": 3}


# A fresh character (as the snapshots hold one), and one with everything up
# and each condition in turn, for the port's copy to draw alike.
STATUS_CASES = [
    {"exp": 0, "level": 1, "hp": 50, "hp_max": 50, "mp": 30, "mp_max": 30, "stat": 20,
     "wis": 0, "working": [0, 0, 0, 0, 10], "gold": 0},
    {"exp": 123456, "level": 27, "hp": 7, "hp_max": 412, "mp": 999, "mp_max": 999,
     "stat": 123, "wis": 3, "working": [999, 1, 22, 333, 45], "gold": 9876543,
     "poison": 1},
    {"exp": 48, "level": 2, "hp": 57, "hp_max": 57, "mp": 34, "mp_max": 34, "stat": 21,
     "wis": 4, "working": [0, 0, 0, 0, 11], "gold": 51, "paralyze": 1, "dark": 1},
    {"exp": 5, "level": 1, "hp": 1, "hp_max": 50, "mp": 0, "mp_max": 30, "stat": 10,
     "wis": 0, "working": [0, 0, 0, 0, 5], "gold": 0, "curse": 1},
    {"exp": 5, "level": 1, "hp": 1, "hp_max": 50, "mp": 0, "mp_max": 30, "stat": 10,
     "wis": 0, "working": [0, 0, 0, 0, 5], "gold": 0, "slow": 1},
    {"exp": 5, "level": 1, "hp": 1, "hp_max": 50, "mp": 0, "mp_max": 30, "stat": 10,
     "wis": 1, "working": [0, 0, 0, 0, 5], "gold": 0, "dark": 1},
]


MODEL_DEPTH = 0x100     # the thing's turning model is filed deeper than any 2D part


def snapshot_ui(name):
    """The frame's 2D primitives in drawing order, both buffers: [[prim]] --
    the sprites and textured quads above the turning model's depths."""
    import gpuframe
    ram = gpuframe.load(name)
    out = []
    for buf in (0, 1):
        prims = []
        for d, p in gpuframe.frame(ram, buf):
            if p["kind"] in ("sprite", "quad") and d < MODEL_DEPTH:
                q = {k: v for k, v in p.items() if k not in ("abr", "raw")}
                if q["kind"] == "sprite":
                    q.pop("semi", None)
                prims.append((d, q))
        out.append(prims)
    return ram, out


def stack_lists(ram):
    """The list records on the menus' stack: {address: record} -- found by
    what ui_menu_label leaves in them (x 0x1b, length 0x18) and the y and
    rows of the two kinds, three rows at 0x93 or the equipment's ten at
    0x23."""
    out = {}
    for a in range(0x1F0000, 0x200000 - 0x40, 2):
        if ram[a + 0x1C] == 0x1B and ram[a + 0x23] == 0x18 \
                and (ram[a + 0x1D], ram[a + 0x1F]) in ((0x93, 3), (0x23, 10)):
            out[0x80000000 | a] = {"count": ram[a + 0x1E], "rows": ram[a + 0x1F],
                                   "first": ram[a + 0x20], "sel": ram[a + 0x21],
                                   "sel_row": ram[a + 0x22]}
    return out


def equip_state(ram):
    """The slots equip_names reads, out of a snapshot."""
    return {"weapon": ram[0x1B25AF], "spell_a": ram[0x1B25AB], "spell_b": ram[0x1B25AC],
            "item_b": ram[0x1B25AD], "worn": list(ram[0x1B25D4:0x1B25DB])}


def snapshot_screens(e, ram, name):
    """What the model draws for a menu snapshot, for each way the frame could
    be -- [(what, primitives)] -- out of the snapshot's own state: the
    inventory, the player's slots and figures, and the list records on the
    stack (the selection and the rows shown, as ui_menu_chrome left them)."""
    look = Look(ram)
    lists = stack_lists(ram)
    inv = ram[INVENTORY_A & 0x1FFFFF:(INVENTORY_A & 0x1FFFFF) + 150]
    three = [r for r in lists.values() if r["rows"] == 3]
    ten = [r for r in lists.values() if r["rows"] == 10]
    out = []
    for pulse in range(0x60):
        look.pulse = pulse
        if name.startswith("inv") and three:
            r = three[0]
            names, counts, ids = item_list(e, inv)
            lab = e.bytes(0x8007E67C + 4, 16)
            s = {"tx": 0x1F, "ty": 0x20, "title": list(lab), "x": 0x1B, "y": 0x93,
                 "rows": 3, "length": 0x18, "count": len(ids), "names": names,
                 "counts": counts + [0xFF], "ids": ids,
                 "first": r["first"], "sel_row": r["sel_row"], "sel": r["sel"]}
            f = Frame()
            panel(f, look, e, s, 1)
            out.append((f"use item, row {r['sel_row']} of the rows from {r['first']}, "
                        f"pulse {pulse:#x}", f.order()))
        elif name.startswith("menu"):
            for sel in range(6):
                out.append((f"main page, line {sel}, pulse {pulse:#x}",
                            main_page(e, look, status_of(ram), sel)))
        elif name.startswith("equip") and ten:
            st = equip_state(ram)
            line = ten[0]["sel"]
            out.append((f"equipment, line {line}, pulse {pulse:#x}",
                        equipment_screen(e, look, st, line)))
            if three and line in EQUIP_RANGES:
                r = three[0]
                s = equip_list(e, list(inv), line, st)
                s["first"], s["sel_row"], s["sel"] = r["first"], r["sel_row"], r["sel"]
                for prompt in (None, 0, 1):
                    out.append((f"equipment list, line {line}, row {r['sel_row']}, "
                                f"prompt {prompt}, pulse {pulse:#x}",
                                equip_list_screen(e, look, s, prompt)))
    return out


def check_menus(out=sys.stdout, verbose=False, names=("menu1", "equip1", "equip2",
                                                     "equip3", "equip4", "inv3")):
    """The main page, the equipment screens and a scrolled "use item" list
    against the snapshots of them, frame for frame: each buffer has to be,
    primitive for primitive, one of the frames the model draws from the
    snapshot's own state."""
    e = exe()
    ok = bad = 0
    for name in names:
        path = os.path.join(ROOT, "out", "snap", name + ".ram")
        if not os.path.exists(path):
            continue
        ram, bufs = snapshot_ui(name)
        cands = snapshot_screens(e, ram, name)
        for b, game in enumerate(bufs):
            hit = next((what for what, prims in cands if prims == game), None)
            ok += hit is not None
            bad += hit is None
            if verbose or hit is None:
                print(f"  {name} buffer {b}: {len(game)} primitives -- "
                      f"{hit if hit else 'NO FRAME OF THE MODEL'}", file=out)
                if hit is None and cands:
                    best = max(cands, key=lambda c: sum(1 for x, y in zip(c[1], game) if x == y))
                    i = next((i for i, (x, y) in enumerate(zip(best[1], game)) if x != y),
                             min(len(best[1]), len(game)))
                    print(f"    nearest: {best[0]}, {len(best[1])} primitives, first "
                          f"difference at {i}:", file=out)
                    if i < len(game):
                        print(f"      game  {game[i]}", file=out)
                    if i < len(best[1]):
                        print(f"      model {best[1][i]}", file=out)
    print(f"  {ok} of {ok + bad} frames of the main page, the equipment screens and a "
          f"scrolled list drawn primitive for primitive as the game drew them", file=out)
    return bad == 0


def check(out=sys.stdout, verbose=False):
    menus = check_menus(out, verbose)
    menus = panel_check(out) and menus
    menus = storage_check(out) and menus
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
    return bad == 0 and menus


def bar_colour_with(look, a):
    keep = look.pulse
    look.pulse = a
    c = bar_colour(look)
    look.pulse = keep
    return c


if __name__ == "__main__":
    sys.exit(0 if check(verbose="--check" not in sys.argv) else 1)
