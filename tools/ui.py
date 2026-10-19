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
    the text, + 0x68 the shadow, + 0x4c the bar's pulse, + 0x50 a second
    pulse frame_begin steps beside it and never puts back (OPTION 2's values
    light with it), + 0x40 and + 0x44 the confirm and cancel buttons;
    0x801b25e4 the boxes' semi-transparency, 0x801b25e1 the brightness."""

    def __init__(self, ram=None):
        def w(off):
            return struct.unpack_from("<I", ram, (GP + off) & 0x1FFFFF)[0]
        if ram is None:
            self.box, self.text, self.shadow, self.pulse = 0x78, 0x80, 0x30, 0
            self.confirm, self.cancel, self.semi, self.bright = 3, 1, 1, 0x80
            self.pulse2 = 0
            return
        self.box, self.text, self.shadow = w(0x58) & 0xFF, w(0x5C) & 0xFF, w(0x68) & 0xFF
        self.pulse = w(0x4C)
        self.pulse2 = w(0x50)
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


def lit_plate(f, look, rec, x, y, pulse=None):
    """sub_80026020 (rec, label, pulse): a plate in the pulsing colour -- of
    the selection's pulse (gp+0x4c) for every caller but ui_display_values, which
    hands it the second (gp+0x50)."""
    c0, c1 = bar_colour(look) if pulse is None else bar_colour_with(look, pulse)
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
    # the legend by the fourth argument (0x800253c4): 0 the confirm button at
    # 0x5f, 1 button 9 at 0x5b (OPTION 1 and 2), anything else none (no caller
    # passes one); "select", then the cancel button and "return", each time
    if legend_mode == 0:
        legend(f, look, e, 0, two=True)
        return
    if legend_mode == 1:
        button(f, look, e, 0x5B, 0xD6, 9)
    small_text(f, look, e, 0x69, 0xD6, gp_string(e, 0x7C))
    button(f, look, e, 0xA0, 0xD6, look.cancel)
    small_text(f, look, e, 0xAA, 0xD6, gp_string(e, 0x74))


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


# --- system: BUTTON CONFIG ----------------------------------------------------

BUTTON_WORDS = 0x8001135C       # four 8-byte words: attack, event, magic, status
ACTION_WORDS = 0x8001137C       # nine 16-byte: move left .. turn right
SCHEME_NAMES = 0x8001140C       # seven 8-byte: type a .. type g
# options_screen's two switches, read with their delay slots: for each action
# scheme the word beside each of the four buttons, and for each movement
# scheme the action beside each of the six after them
OPTION_ACTIONS = ((0, 1, 2, 3), (2, 1, 0, 3), (0, 3, 2, 1), (2, 3, 0, 1))
OPTION_MOVES = ((0, 1, 2, 3, 4, 5), (1, 3, 0, 2, 4, 5), (0, 2, 1, 3, 4, 5),
                (7, 1, 8, 3, 4, 6), (1, 3, 7, 8, 4, 6), (7, 8, 1, 3, 4, 6),
                (3, 0, 1, 2, 4, 5))


def c_string(e, at, n):
    """The bytes at `at`, up to the first NUL within n."""
    b = bytes(e.bytes(at, n))
    return list(b.split(b"\0")[0])


def options_page(f, look, e, action, move, row):
    """options_screen (0x80023fd4), BUTTON CONFIG's page: buttons 0..3 at x
    0x89 from y 0x31, 14 apart, each with its word for the action scheme
    beside it at x 0x9b; buttons 4..9 from y 0x6f with their actions for the
    movement scheme; "action" and the action scheme's name at (0x32, 0x32)
    and (0x3a, 0x40), "move" and the movement scheme's at (0x32, 0x70) and
    (0x3a, 0x7e) -- all with their shadows; the pulsing bar 0x35 x 0xf at x
    0x37 on the row chosen (y 0x3c or 0x7a); the frame 0x102 x 0xb0 at
    (0x1f, 0x20); and its own legend, button 9 "select" and the cancel's
    "return"."""
    for i in range(4):
        button(f, look, e, 0x89, 0x31 + 14 * i, i)
        small_text(f, look, e, 0x9B, 0x32 + 14 * i,
                   c_string(e, BUTTON_WORDS + 8 * OPTION_ACTIONS[action][i], 8), 1, 0)
    for i in range(6):
        button(f, look, e, 0x89, 0x6F + 14 * i, 4 + i)
        small_text(f, look, e, 0x9B, 0x70 + 14 * i,
                   c_string(e, ACTION_WORDS + 16 * OPTION_MOVES[move][i], 16), 1, 0)
    small_text(f, look, e, 0x32, 0x32, c_string(e, 0x8009C2A8, 8), 1, 0)
    small_text(f, look, e, 0x3A, 0x40, c_string(e, SCHEME_NAMES + 8 * action, 8), 1, 0)
    small_text(f, look, e, 0x32, 0x70, c_string(e, 0x8009C2B0, 8), 1, 0)
    small_text(f, look, e, 0x3A, 0x7E, c_string(e, SCHEME_NAMES + 8 * move, 8), 1, 0)
    c0, c1 = bar_colour(look)
    tpage, clut, u, v, w, h = record(e, RECORDS + 12 * 8)
    f.add(49, quad(0x37, 0x7A if row else 0x3C, 0x35, 0xF, u, v, w, h,
                   tpage, clut, c0 | (c0 << 8) | (c1 << 16), 1))
    frame(f, look, e, 0x1F, 0x20, 0x102, 0xB0)
    button(f, look, e, 0x5B, 0xD6, 9)
    small_text(f, look, e, 0x69, 0xD6, c_string(e, 0x8009C290, 8), 0, 0)
    button(f, look, e, 0xA0, 0xD6, look.cancel)
    small_text(f, look, e, 0xAA, 0xD6, c_string(e, 0x8009C288, 8), 0, 0)


def button_config_press(st, press, cancel):
    """One pad word on BUTTON CONFIG (0x8001f31c): the cancel leaves; UP or
    DOWN turns between the two rows, the action scheme (0) and the movement
    scheme (1); LEFT lowers the row's scheme and RIGHT raises it, held to
    0..3 and 0..6. `st` holds "action", "move", "row"; True when it leaves,
    and then the caller stores the two and runs apply_control_scheme."""
    if press & cancel:
        return True
    if press & (UP | DOWN):
        st["row"] = 1 if st["row"] == 0 else 0
    elif press & LEFT:
        k = "move" if st["row"] else "action"
        if st[k]:
            st[k] -= 1
    elif press & RIGHT:
        k = "move" if st["row"] else "action"
        st[k] = min(st[k] + 1, 6 if st["row"] else 3)
    return False


def options_check(out=sys.stdout):
    """BUTTON CONFIG against the game's own code over menu1: options_screen
    drawn for every action scheme, movement scheme and row, at two pulses;
    and the screen (0x8001f31c) run whole on random runs of pad words, the
    two scheme bytes it leaves and the words it reads."""
    import random
    import mipsrun
    path = os.path.join(ROOT, "out", "snap", "menu1.ram")
    if not os.path.exists(path):
        print("  no menu1 snapshot to run the options over", file=out)
        return True
    e = exe()
    base = bytearray(open(path, "rb").read())
    ok = runs = 0
    first = None
    for action in range(4):
        for move in range(7):
            for row in (0, 1):
                for pulse in (0x11, 0x47):
                    prims, _cpu = mipsrun.frame(base, [(0x80023FD4, action, move, row)], pulse)
                    look = Look(base)
                    look.pulse = pulse
                    f = Frame()
                    options_page(f, look, e, action, move, row)
                    got = mipsrun.two_d(prims)
                    want = [(d, p) for d, p in f.order()]
                    runs += 1
                    ok += got == want
                    if got != want and first is None:
                        k = next((j for j, (a, b) in enumerate(zip(got, want)) if a != b),
                                 min(len(got), len(want)))
                        first = (f"action {action} move {move} row {row}: {len(got)} primitives, "
                                 f"the model {len(want)}; at {k}: game "
                                 f"{got[k] if k < len(got) else None} model "
                                 f"{want[k] if k < len(want) else None}")
    print(f"  BUTTON CONFIG's page as the game's own options_screen draws it over menu1: "
          f"{ok} of {runs} frames primitive for primitive", file=out)
    if first:
        print("  first difference: " + first, file=out)
    cancel = struct.unpack_from("<I", base, (GP + 0x3C) & 0x1FFFFF)[0]
    confirm = struct.unpack_from("<I", base, (GP + 0x38) & 0x1FFFFF)[0]
    rng = random.Random(0xB077)
    ok2 = 0
    first2 = None
    n = 120
    for i in range(n):
        st = {"action": rng.randrange(4), "move": rng.randrange(7), "row": 0}
        words = [UP, DOWN, LEFT, RIGHT, LEFT, RIGHT, confirm, cancel]
        presses = [rng.choice(words[:-1]) for _ in range(rng.randrange(0, 20))]
        if rng.randrange(4):
            presses.append(cancel)
        g = game_button_config(base, st["action"], st["move"], presses)
        used = 0
        left = False
        for p in presses:
            used += 1
            if button_config_press(st, p, cancel):
                left = True
                break
        m = (left, used, st["action"], st["move"], None if left else st["row"])
        ok2 += g == m
        if g != m and first2 is None:
            first2 = f"run {i}: game {g} model {m}"
    print(f"  BUTTON CONFIG run whole by the game's own code, the pad scripted: {ok2} of {n} "
          f"runs end alike, read as many words and leave the two schemes (and, still up, "
          f"the row) alike", file=out)
    if first2:
        print("  first difference: " + first2, file=out)
    return ok == runs and ok2 == n


def game_button_config(base, action, move, presses):
    """0x8001f31c run whole over `base` with 0x801b25e2 and e3 laid in and
    pad_read_latch answering `presses` a word at a time, the drawing and
    apply_control_scheme stood in for: (returned, words read, the action
    scheme, the movement scheme, the row) -- the two bytes it stored when it
    returned, and while it is still up the registers it keeps them in until
    then ($s1, $s2; the row $s3)."""
    import mipsrun
    cpu = mipsrun.menu_cpu(base)
    cpu.ram[0x1B25E2] = action
    cpu.ram[0x1B25E3] = move
    script = list(presses)
    read = [0]
    held = []

    def latch(c):
        if not script:
            held.extend((c.r[17] & 0xFF, c.r[18] & 0xFF, c.r[19]))
            raise _Out
        read[0] += 1
        return script.pop(0)

    cpu.hooks[0x800279A4] = latch
    for at in (0x80027A40, 0x800279D8, 0x80026FE4, 0x800270F8, 0x80023FD4, 0x8001F4C0):
        cpu.hooks[at] = lambda c: 0
    try:
        cpu.call(0x8001F31C)
    except _Out:
        return (False, read[0]) + tuple(held)
    return True, read[0], cpu.ram[0x1B25E2], cpu.ram[0x1B25E3], None


# --- system: OPTION 2, the display ----------------------------------------------

# the five bytes OPTION 2 sets, in its rows' order: the panel's style, the
# compass's (0..2 each), the turning model in the lists, the walking bob, and
# the menus' boxes clear or solid (0 or 1 each); a new character's (sub_8002b64c)
DISPLAY_BYTES = (0x801B25DD, 0x801B25DE, 0x801B25DF, 0x801B25E0, 0x801B25E4)
DISPLAY_DEFAULT = (2, 2, 1, 1, 1)
# ui_display_values's words, immediates in its code: three plates' letters for the
# two styles, and "on"/"off" -- "clear"/"solid" on the last row
STYLE_LETTERS = ([0x00, 0xFF], [0x01, 0xFF], [0x02, 0xFF])
WORD_ON = [0x7F, 0x7F, 0x0E, 0x0D, 0xFF]
WORD_OFF = [0x7F, 0x7F, 0x0E, 0x05, 0x05, 0xFF]
WORD_CLEAR = [0x02, 0x0B, 0x04, 0x00, 0x11, 0xFF]
WORD_SOLID = [0x12, 0x0E, 0x0B, 0x08, 0x03, 0xFF]


def display_values(f, look, e, values):
    """ui_display_values (0x800246bc): OPTION 2's five values beside its lines.
    The two styles, rows at y 0x3a and 0x54, are three plates (record 5) at x
    0xab, 0xc7 and 0xe3 lettered A, B, C -- A lit for 2, B for 1, C for 0 --
    each letter 4 to the right of its plate's place; the three switches, from
    y 0x6e, 26 apart, are two smaller plates (record 1) at 0xab and 0xe5,
    "on" and "off" ("clear" and "solid" on the last), the first lit for 1.
    A plate lit is sub_80026020's and its word ui_draw_label's; the others
    ui_label_plate's and sub_80026158's."""
    style = record(e, LABEL_STYLE)
    big = record(e, RECORDS + 12 * 5)
    small = record(e, RECORDS + 12 * 1)
    y = 0x3A
    for row in range(2):
        v = values[row]
        lit = 0 if v == 2 else 1 if v == 1 else 2
        for i, x in enumerate((0xAB, 0xC7, 0xE3)):
            if i == lit:
                lit_plate(f, look, big, x, y, look.pulse2)
                draw_label(f, look, style, x + 4, y, STYLE_LETTERS[i])
            else:
                title_plate(f, look, big, x, y)
                dim_label(f, look, style, x + 4, y, STYLE_LETTERS[i])
        y += 0x1A
    for row in range(3):
        one, two = (WORD_CLEAR, WORD_SOLID) if row == 2 else (WORD_ON, WORD_OFF)
        if values[2 + row] == 1:
            lit_plate(f, look, small, 0xAB, y, look.pulse2)
            draw_label(f, look, style, 0xAB, y, one)
            title_plate(f, look, small, 0xE5, y)
            dim_label(f, look, style, 0xE5, y, two)
        else:
            title_plate(f, look, small, 0xAB, y)
            dim_label(f, look, style, 0xAB, y, one)
            lit_plate(f, look, small, 0xE5, y, look.pulse2)
            draw_label(f, look, style, 0xE5, y, two)
        y += 0x1A


def display_page(f, look, e, values, row):
    """OPTION 2's frame: sub_800252f4(5, 5, row, 1) -- page 5's five lines,
    the row chosen lit -- and ui_display_values's values beside them."""
    menu_page(f, look, e, 5, 5, row, legend_mode=1)
    display_values(f, look, e, values)


def display_press(st, press, confirm, cancel):
    """One pad word on OPTION 2 (0x8001f004): UP and DOWN move round the five
    rows; the confirm, RIGHT or LEFT change the row's value -- the two styles
    stepping 2, 1, 0, 2 on the confirm and RIGHT and the other way on LEFT,
    the three switches turned over by any of them (v < 1) -- and the cancel
    leaves. `st` holds "values" (five) and "row"; True when it leaves, the
    caller then storing the five and running panel_colours."""
    v = st["values"]
    r = st["row"]
    if press & UP:
        st["row"] = 4 if r == 0 else r - 1
    elif press & DOWN:
        st["row"] = 0 if r == 4 else r + 1
    elif press & (confirm | RIGHT | LEFT):
        if r >= 2:
            v[r] = 1 if v[r] < 1 else 0
        elif press & (confirm | RIGHT):
            v[r] = 2 if v[r] == 0 else v[r] - 1
        else:
            v[r] = 0 if v[r] == 2 else v[r] + 1
    elif press & cancel:
        return True
    return False


def panel_look(semi, bright):
    """panel_colours (0x8001f274): the menus' colours for the panel's switch (0x801b25e4)
    and the brightness (0x801b25e1) -- clear (1): boxes 0x78, the shadow 0x30
    and the text 0x80 plus half of what the brightness is over 0x80; solid
    (0): boxes 0x57, the shadow 0x80 and the text 0x30 less that half. The
    halving rounds toward zero. {"box", "text", "shadow"} as gp+0x58, +0x5c
    (+0x60, +0x64 the same) and +0x68."""
    half = int((bright - 0x80) / 2)
    if semi == 0:
        text = 0x30 - half if bright >= 0x81 else 0x30
        return {"box": 0x57, "text": text & 0xFFFFFFFF, "shadow": 0x80}
    return {"box": 0x78, "text": (half + 0x80) & 0xFFFFFFFF, "shadow": 0x30}


def game_display(base, values, presses):
    """0x8001f004 run whole over `base` with the five bytes laid in and
    pad_read_latch answering `presses` a word at a time, the drawing stood in
    for: (returned, words read, the five values, the row) -- the bytes it
    stored when it returned, and while it is still up the five it keeps on
    its stack (sp+0x10) and the row ($s1)."""
    import mipsrun
    cpu = mipsrun.menu_cpu(base)
    for a, v in zip(DISPLAY_BYTES, values):
        cpu.ram[a & 0x1FFFFF] = v
    script = list(presses)
    read = [0]
    held = []

    def latch(c):
        if not script:
            held.append([c.rd(c.r[29] + 0x10 + k, 1) for k in range(5)])
            held.append(c.r[17])
            raise _Out
        read[0] += 1
        return script.pop(0)

    cpu.hooks[0x800279A4] = latch
    for at in (0x80027A40, 0x800279D8, 0x80026FE4, 0x800270F8, 0x800252F4, 0x800246BC):
        cpu.hooks[at] = lambda c: 0
    try:
        cpu.call(0x8001F004)
    except _Out:
        return False, read[0], held[0], held[1]
    return True, read[0], [cpu.ram[a & 0x1FFFFF] for a in DISPLAY_BYTES], None


def display_check(out=sys.stdout):
    """OPTION 2 against the game's own code over menu1: the page and its
    values drawn for every value of the five and a row each; the screen run
    whole on random runs of pad words; and the colours of panel_colours for both
    panels at brightnesses across the byte."""
    import random
    import mipsrun
    path = os.path.join(ROOT, "out", "snap", "menu1.ram")
    if not os.path.exists(path):
        print("  no menu1 snapshot to run the options over", file=out)
        return True
    e = exe()
    base = bytearray(open(path, "rb").read())
    at = 0x801F0000
    ok = runs = 0
    first = None
    k = 0
    for a in range(3):
        for b in range(3):
            for c in range(2):
                for d in range(2):
                    for p in range(2):
                        values = [a, b, c, d, p]
                        row, pulse = k % 5, (0x0B, 0x33, 0x52)[k % 3]
                        pulse2 = (0x21, 0x44, 0x5F, 0x00)[k % 4]
                        k += 1
                        ram = bytearray(base)
                        ram[at & 0x1FFFFF:(at & 0x1FFFFF) + 5] = bytes(values)
                        # frame_begin steps gp+0x50 as it does gp+0x4c
                        struct.pack_into("<I", ram, (GP + 0x50) & 0x1FFFFF, (pulse2 - 1) % 0x60)
                        # every other frame with the panel solid, in the colours
                        # panel_colours gives it
                        if k % 2:
                            lk = panel_look(0, ram[0x1B25E1])
                            ram[0x1B25E4] = 0
                            for o, v in ((0x58, lk["box"]), (0x5C, lk["text"]), (0x60, lk["text"]),
                                         (0x64, lk["text"]), (0x68, lk["shadow"])):
                                struct.pack_into("<I", ram, (GP + o) & 0x1FFFFF, v)
                        prims, _cpu = mipsrun.frame(ram, [(0x800252F4, 5, 5, row, 1),
                                                          (0x800246BC, at)], pulse)
                        look = Look(ram)
                        look.pulse, look.pulse2 = pulse, pulse2
                        f = Frame()
                        display_page(f, look, e, values, row)
                        got = mipsrun.two_d(prims)
                        want = [(dd, pp) for dd, pp in f.order()]
                        runs += 1
                        ok += got == want
                        if got != want and first is None:
                            j = next((i for i, (x, y) in enumerate(zip(got, want)) if x != y),
                                     min(len(got), len(want)))
                            first = (f"values {values} row {row}: {len(got)} primitives, the "
                                     f"model {len(want)}; at {j}: game "
                                     f"{got[j] if j < len(got) else None} model "
                                     f"{want[j] if j < len(want) else None}")
    print(f"  OPTION 2's page and values as the game's own sub_800252f4 and ui_display_values "
          f"draw them over menu1: {ok} of {runs} frames primitive for primitive, half "
          f"with the panel solid", file=out)
    if first:
        print("  first difference: " + first, file=out)
    confirm = struct.unpack_from("<I", base, (GP + 0x38) & 0x1FFFFF)[0]
    cancel = struct.unpack_from("<I", base, (GP + 0x3C) & 0x1FFFFF)[0]
    rng = random.Random(0xD15)
    ok2, n = 0, 120
    first2 = None
    for i in range(n):
        values = [rng.randrange(3), rng.randrange(3), rng.randrange(2), rng.randrange(2),
                  rng.randrange(2)]
        presses = [rng.choice((UP, DOWN, LEFT, RIGHT, confirm, confirm, 0x10))
                   for _ in range(rng.randrange(0, 20))]
        if rng.randrange(4):
            presses.append(cancel)
        g = game_display(base, values, presses)
        st = {"values": list(values), "row": 0}
        used, left = 0, False
        for p in presses:
            used += 1
            if display_press(st, p, confirm, cancel):
                left = True
                break
        m = (left, used, st["values"], None if left else st["row"])
        ok2 += g == m
        if g != m and first2 is None:
            first2 = f"run {i}: game {g} model {m}"
    print(f"  OPTION 2 run whole by the game's own code, the pad scripted: {ok2} of {n} runs "
          f"end alike, read as many words and leave the five values (and, still up, the "
          f"row) alike", file=out)
    if first2:
        print("  first difference: " + first2, file=out)
    ok3 = n3 = 0
    first3 = None
    for semi in (0, 1):
        for bright in (0x00, 0x40, 0x7F, 0x80, 0x81, 0x82, 0x83, 0xA0, 0xC0, 0xFF):
            cpu = mipsrun.menu_cpu(base)
            cpu.ram[0x1B25E4], cpu.ram[0x1B25E1] = semi, bright
            cpu.call(0x8001F274)
            g = [cpu.rd(GP + o, 4) for o in (0x58, 0x5C, 0x60, 0x64, 0x68)]
            lk = panel_look(semi, bright)
            m = [lk["box"], lk["text"], lk["text"], lk["text"], lk["shadow"]]
            n3 += 1
            ok3 += g == m
            if g != m and first3 is None:
                first3 = f"panel {semi} brightness {bright:#x}: game {g} model {m}"
    print(f"  panel_colours, the game's own, for both panels and {n3 // 2} "
          f"brightnesses: {ok3} of {n3} alike", file=out)
    if first3:
        print("  first difference: " + first3, file=out)
    return ok == runs and ok2 == n and ok3 == n3


# --- system: OPTION 1, the sound and the brightness ---------------------------

SOUND_BYTES = (0x801B25DB, 0x801B25DC, 0x801B25E1)


def sound_values(ram_bytes):
    """menu_sound's three sliders from the bytes it starts from: the sound
    effects' 0x801b25db as it is, the music's 0x801b25dc one more unless 0,
    the brightness 0x801b25e1 plus 0xc0 (0x40..0xc0 as 0..0x80)."""
    sfx, music, bright = ram_bytes
    return [sfx, 0 if music == 0 else (music + 1) & 0xFF, (bright + 0xC0) & 0xFF]


def sound_bytes(values):
    """menu_sound's end: the three bytes it stores back."""
    return [values[0] & 0xFF, 0 if values[1] == 0 else (values[1] - 1) & 0xFF,
            (values[2] + 0x40) & 0xFF]


def sound_sliders(f, look, e, values):
    """sub_80024a78: a slider for each of the three -- the track (record 7)
    at (0xa5, 0x34) at depth 0x32, the knob (record 6, its u 16 on with the
    panel clear) at x 0xac + 96 * v / 128, y 0x3c, at depth 0x31 -- 26
    apart, both in the boxes' grey."""
    tr = record(e, RECORDS + 12 * 7)
    kn = record(e, RECORDS + 12 * 6)
    f.tpage(0x32, tr[0])
    for i in range(3):
        f.add(0x32, sprite(0xA5, 0x34 + 0x1A * i, tr[4], tr[5], tr[2], tr[3], tr[1],
                           rgb(look.box)))
        f.add(0x31, sprite(0xAC + ((96 * values[i]) >> 7), 0x3C + 0x1A * i, kn[4], kn[5],
                           kn[2] + (look.semi << 4), kn[3], kn[1], rgb(look.box)))


def sound_page(f, look, e, values, row):
    """OPTION 1's frame: sub_800252f4(4, 3, row, 1) and the sliders."""
    menu_page(f, look, e, 4, 3, row, legend_mode=1)
    sound_sliders(f, look, e, values)


def sound_press(st, press, cancel):
    """One pad word on OPTION 1 (0x8001ec84): UP and DOWN round the three
    rows; RIGHT moves the row's slider 3 on, to 0x80 at most; LEFT 3 back, to
    0; the cancel leaves. True when it leaves."""
    v, r = st["values"], st["row"]
    if press & UP:
        st["row"] = 2 if r == 0 else r - 1
    elif press & DOWN:
        st["row"] = 0 if r == 2 else r + 1
    elif press & RIGHT:
        v[r] = min((v[r] + 3) & 0xFF, 0x80)
    elif press & LEFT:
        v[r] = v[r] - 3 if v[r] >= 3 else 0
    elif press & cancel:
        return True
    return False


def game_sound(base, bytes_, presses):
    """0x8001ec84 run whole over `base` with the three bytes laid in, the pad
    scripted, the drawing and the sound stood in for: (returned, words read,
    the three values as sound_values has them, the row)."""
    import mipsrun
    cpu = mipsrun.menu_cpu(base)
    for a, v in zip(SOUND_BYTES, bytes_):
        cpu.ram[a & 0x1FFFFF] = v
    script = list(presses)
    read = [0]
    held = []

    def latch(c):
        if not script:
            held.append([c.rd(c.r[29] + 0x10 + k, 1) for k in range(3)])
            held.append(c.r[17])
            raise _Out
        read[0] += 1
        return script.pop(0)

    cpu.hooks[0x800279A4] = latch
    for at in (0x80027A40, 0x800279D8, 0x80026FE4, 0x800270F8, 0x800252F4, 0x80024A78,
               0x800677E8, 0x80015790):
        cpu.hooks[at] = lambda c: 0
    try:
        cpu.call(0x8001EC84)
    except _Out:
        return False, read[0], held[0], held[1], None
    text = [cpu.rd(GP + o, 4) for o in (0x5C, 0x60, 0x64)]
    return True, read[0], [cpu.ram[a & 0x1FFFFF] for a in SOUND_BYTES], None, text


def sound_check(out=sys.stdout):
    """OPTION 1 against the game's own code over menu1: the page and its
    sliders drawn for values across the range, a row each, half with the
    panel solid; and the screen run whole on random runs of pad words --
    the three bytes it stores and the text colours it sets."""
    import random
    import mipsrun
    path = os.path.join(ROOT, "out", "snap", "menu1.ram")
    if not os.path.exists(path):
        print("  no menu1 snapshot to run the options over", file=out)
        return True
    e = exe()
    base = bytearray(open(path, "rb").read())
    rng = random.Random(0x50D)
    at = 0x801F0000
    ok = n = 0
    first = None
    for k in range(48):
        values = [rng.choice((0, 1, 3, 0x40, 0x7F, 0x80, rng.randrange(0x81))) for _ in range(3)]
        row, pulse = k % 3, rng.randrange(0x60)
        ram = bytearray(base)
        ram[at & 0x1FFFFF:(at & 0x1FFFFF) + 3] = bytes(values)
        if k % 2:
            lk = panel_look(0, ram[0x1B25E1])
            ram[0x1B25E4] = 0
            for o, v in ((0x58, lk["box"]), (0x5C, lk["text"]), (0x60, lk["text"]),
                         (0x64, lk["text"]), (0x68, lk["shadow"])):
                struct.pack_into("<I", ram, (GP + o) & 0x1FFFFF, v)
        prims, _cpu = mipsrun.frame(ram, [(0x800252F4, 4, 3, row, 1), (0x80024A78, at)], pulse)
        look = Look(ram)
        look.pulse = pulse
        f = Frame()
        sound_page(f, look, e, values, row)
        got = mipsrun.two_d(prims)
        want = [(d, p) for d, p in f.order()]
        n += 1
        ok += got == want
        if got != want and first is None:
            j = next((i for i, (x, y) in enumerate(zip(got, want)) if x != y), min(len(got), len(want)))
            first = (f"values {values} row {row}: {len(got)} primitives, the model {len(want)}; "
                     f"at {j}: game {got[j] if j < len(got) else None} model "
                     f"{want[j] if j < len(want) else None}")
    print(f"  OPTION 1's page and sliders as the game's own sub_800252f4 and sub_80024a78 "
          f"draw them over menu1: {ok} of {n} frames primitive for primitive", file=out)
    if first:
        print("  first difference: " + first, file=out)
    cancel = struct.unpack_from("<I", base, (GP + 0x3C) & 0x1FFFFF)[0]
    ok2, n2 = 0, 160
    first2 = None
    for i in range(n2):
        bytes_ = [rng.randrange(0x81), rng.choice((0, rng.randrange(0x80))),
                  rng.randrange(0x40, 0xC1)]
        presses = [rng.choice((UP, DOWN, LEFT, RIGHT, RIGHT, 0x40)) for _ in range(rng.randrange(0, 40))]
        if rng.randrange(4):
            presses.append(cancel)
        semi = rng.randrange(2)
        b2 = bytearray(base)
        b2[0x1B25E4] = semi
        g = game_sound(b2, bytes_, presses)
        st = {"values": sound_values(bytes_), "row": 0}
        used, left = 0, False
        for p in presses:
            used += 1
            if sound_press(st, p, cancel):
                left = True
                break
        if left:
            stored = sound_bytes(st["values"])
            if semi:
                t = panel_look(1, stored[2])["text"]
                text = [t, t, t]
            else:
                text = [struct.unpack_from("<I", base, (GP + o) & 0x1FFFFF)[0] for o in (0x5C, 0x60, 0x64)]
            m = (True, used, stored, None, text)
        else:
            m = (False, used, st["values"], st["row"], None)
        ok2 += g == m
        if g != m and first2 is None:
            first2 = f"run {i}: game {g} model {m}"
    print(f"  OPTION 1 run whole by the game's own code, the pad scripted: {ok2} of {n2} runs "
          f"end alike, read as many words and leave the three bytes, the text colours (and, "
          f"still up, the row) alike", file=out)
    if first2:
        print("  first difference: " + first2, file=out)
    return ok == n and ok2 == n2


# --- system: QUIT GAME ------------------------------------------------------------

QUIT_YES = (0xAB, 0xA2, [0x18, 0x04, 0x12, 0xFF])      # "yes", an immediate in its code
QUIT_NO = (0xE5, 0xA2, [0x0D, 0x0E, 0xFF])             # "no"


def quit_page(f, look, e, sel):
    """QUIT GAME's frame (0x8001f8b4): the system page with its last line
    lit, sub_800252f4(3, 5, 4, 0), and the two answers, sub_80025b24 -- "yes"
    at (0xab, 0xa2), "no" at (0xe5, 0xa2), the chosen one lit."""
    menu_page(f, look, e, 3, 5, 4, 0)
    options(f, look, e, QUIT_YES, QUIT_NO, sel)


def quit_press(sel, press, confirm, cancel):
    """One pad word on QUIT GAME: any of the four directions turns between
    the answers; the confirm answers 0 on "yes" -- which also sets
    0x800102f8, overlay_arg, to 1 -- and -1 on "no"; the cancel answers -1.
    (sel, the answer or None). It starts on "no", 1."""
    if press & (UP | DOWN | LEFT | RIGHT):
        return 1 - sel, None
    if press & confirm:
        return sel, 0 if sel == 0 else -1
    if press & cancel:
        return sel, -1
    return sel, None


def game_quit(base, presses):
    """0x8001f8b4 run whole over `base`, the pad scripted, the drawing stood
    in for: (returned, its answer, words read, overlay_arg, the answer lit)."""
    import mipsrun
    cpu = mipsrun.menu_cpu(base)
    cpu.wr(0x800102F8, 1, 0)
    script = list(presses)
    read = [0]
    held = []

    def latch(c):
        if not script:
            held.append(c.r[18])
            raise _Out
        read[0] += 1
        return script.pop(0)

    cpu.hooks[0x800279A4] = latch
    for at in (0x80027A40, 0x800279D8, 0x80026FE4, 0x800270F8, 0x800252F4, 0x80025B24):
        cpu.hooks[at] = lambda c: 0
    try:
        v = cpu.call(0x8001F8B4)
    except _Out:
        return False, None, read[0], cpu.rd(0x800102F8, 1), held[0]
    return True, mipsrun.s32(v), read[0], cpu.rd(0x800102F8, 1), None


def quit_check(out=sys.stdout):
    """QUIT GAME against the game's own code over menu1: its frame for both
    answers lit at a few pulses, and the question run whole on scripted pad
    words -- its answer, the words read and overlay_arg."""
    import random
    import mipsrun
    path = os.path.join(ROOT, "out", "snap", "menu1.ram")
    if not os.path.exists(path):
        print("  no menu1 snapshot to run QUIT GAME over", file=out)
        return True
    e = exe()
    base = bytearray(open(path, "rb").read())
    ok = n = 0
    first = None
    at = 0x801F0000
    for sel in (0, 1):
        for pulse in (0x03, 0x2F, 0x30, 0x5E):
            ram = bytearray(base)
            for k, (x, y, g) in enumerate((QUIT_YES, QUIT_NO)):
                o = (at & 0x1FFFFF) + 0x40 * k
                struct.pack_into("<hh", ram, o, x, y)
                ram[o + 4:o + 4 + len(g)] = bytes(g)
            prims, _cpu = mipsrun.frame(ram, [(0x800252F4, 3, 5, 4, 0),
                                              (0x80025B24, at, at + 0x40, sel)], pulse)
            look = Look(ram)
            look.pulse = pulse
            f = Frame()
            quit_page(f, look, e, sel)
            got = mipsrun.two_d(prims)
            want = [(d, p) for d, p in f.order()]
            n += 1
            ok += got == want
            if got != want and first is None:
                j = next((i for i, (a, b) in enumerate(zip(got, want)) if a != b), min(len(got), len(want)))
                first = f"sel {sel}: at {j}: game {got[j] if j < len(got) else None} model {want[j] if j < len(want) else None}"
    print(f"  QUIT GAME's frame as the game's own sub_800252f4 and sub_80025b24 draw it over "
          f"menu1: {ok} of {n} frames primitive for primitive", file=out)
    if first:
        print("  first difference: " + first, file=out)
    confirm = struct.unpack_from("<I", base, (GP + 0x38) & 0x1FFFFF)[0]
    cancel = struct.unpack_from("<I", base, (GP + 0x3C) & 0x1FFFFF)[0]
    rng = random.Random(0x0917)
    ok2, n2 = 0, 100
    first2 = None
    for i in range(n2):
        presses = [rng.choice((UP, DOWN, LEFT, RIGHT, 0x10, 0x80)) for _ in range(rng.randrange(0, 8))]
        if rng.randrange(5):
            presses.append(rng.choice((confirm, confirm, cancel)))
        g = game_quit(base, presses)
        sel, used, ans = 1, 0, None
        for p in presses:
            used += 1
            sel, ans = quit_press(sel, p, confirm, cancel)
            if ans is not None:
                break
        m = ((True, ans, used, 1 if ans == 0 else 0, None) if ans is not None
             else (False, None, used, 0, sel))
        ok2 += g == m
        if g != m and first2 is None:
            first2 = f"run {i}: game {g} model {m}"
    print(f"  QUIT GAME run whole by the game's own code, the pad scripted: {ok2} of {n2} runs "
          f"answer alike, read as many words and leave overlay_arg alike", file=out)
    if first2:
        print("  first difference: " + first2, file=out)
    return ok == n and ok2 == n2


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
           # BUTTON CONFIG's words: options_screen's three tables and two headings
           "options": {"buttons": [c_string(e, BUTTON_WORDS + 8 * k, 8) for k in range(4)],
                       "actions": [c_string(e, ACTION_WORDS + 16 * k, 16) for k in range(9)],
                       "schemes": [c_string(e, SCHEME_NAMES + 8 * k, 8) for k in range(7)],
                       "action": c_string(e, 0x8009C2A8, 8), "move": c_string(e, 0x8009C2B0, 8)},
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
    # BUTTON CONFIG's page (which the game's own options_screen holds,
    # options_check) and runs of pad words through button_config_press
    for action, move, row, pulse in ((0, 0, 0, 0x12), (3, 0, 1, 0x40), (1, 4, 0, 0x2B),
                                     (2, 6, 1, 0x05), (3, 3, 0, 0x5E)):
        look.pulse = pulse
        f = Frame()
        options_page(f, look, e, action, move, row)
        cases.append({"screen": "options", "action": action, "move": move, "row": row,
                      "sel": row, "pulse": pulse, "prims": [[d, p] for d, p in f.order()]})
    rng = random.Random(0xB078)
    oruns = []
    for i in range(40):
        st = {"action": rng.randrange(4), "move": rng.randrange(7), "row": 0}
        start = dict(st)
        presses = [rng.choice((UP, DOWN, LEFT, RIGHT, 0x40)) for _ in range(rng.randrange(0, 16))]
        if rng.randrange(3):
            presses.append(0x20)
        used, left = 0, False
        for p in presses:
            used += 1
            if button_config_press(st, p, 0x20):
                left = True
                break
        oruns.append({"start": start, "presses": presses, "left": left, "used": used,
                      "end": st})
    cases.append({"screen": "options_runs", "runs": oruns, "sel": 0, "pulse": 0, "prims": []})
    # OPTION 2's page (which the game's own sub_800252f4 and ui_display_values hold,
    # display_check), some with the panel solid, runs through display_press,
    # and the colours of panel_colours
    for values, row, pulse, pulse2, semi in (([2, 2, 1, 1, 1], 0, 0x12, 0x40, 1),
                                             ([0, 1, 0, 1, 0], 3, 0x4C, 0x07, 0),
                                             ([1, 0, 1, 0, 1], 4, 0x30, 0x5A, 1),
                                             ([2, 1, 0, 0, 0], 2, 0x01, 0x33, 0)):
        dlook = Look()
        dlook.pulse, dlook.pulse2 = pulse, pulse2
        if semi == 0:
            lk = panel_look(0, dlook.bright)
            dlook.box, dlook.text, dlook.shadow, dlook.semi = lk["box"], lk["text"], lk["shadow"], 0
        f = Frame()
        display_page(f, dlook, e, values, row)
        cases.append({"screen": "display", "values": values, "row": row, "sel": row,
                      "pulse": pulse, "pulse2": pulse2, "semi": semi,
                      "prims": [[d, p] for d, p in f.order()]})
    druns = []
    for i in range(40):
        st = {"values": [rng.randrange(3), rng.randrange(3), rng.randrange(2), rng.randrange(2),
                         rng.randrange(2)], "row": 0}
        start = {"values": list(st["values"]), "row": 0}
        presses = [rng.choice((UP, DOWN, LEFT, RIGHT, 0x40)) for _ in range(rng.randrange(0, 16))]
        if rng.randrange(3):
            presses.append(0x20)
        used, left = 0, False
        for p in presses:
            used += 1
            if display_press(st, p, 0x40, 0x20):
                left = True
                break
        druns.append({"start": start, "presses": presses, "left": left, "used": used,
                      "end": st})
    # QUIT GAME's frame (which the game's own holds, quit_check) and runs
    for sel, pulse in ((0, 0x10), (1, 0x44)):
        qlook = Look()
        qlook.pulse = pulse
        f = Frame()
        quit_page(f, qlook, e, sel)
        cases.append({"screen": "quit", "sel": sel, "pulse": pulse,
                      "prims": [[d, p] for d, p in f.order()]})
    for i in range(20):
        presses = [rng.choice((UP, DOWN, LEFT, RIGHT, 0x10)) for _ in range(rng.randrange(0, 8))]
        presses.append(rng.choice((0x40, 0x20, 0x40)))
        sel, used, ans = 1, 0, None
        for p in presses:
            used += 1
            sel, ans = quit_press(sel, p, 0x40, 0x20)
            if ans is not None:
                break
        druns.append({"kind": "quit", "presses": presses, "used": used, "sel": sel,
                      "answer": ans, "start": {"values": [], "row": 0}, "left": True,
                      "end": {"values": [], "row": 0}})
    # OPTION 1's page (which the game's own sub_800252f4 and sub_80024a78
    # hold, sound_check) and runs through sound_press
    for values, row, pulse in (([0x80, 0x51, 0x80], 0, 0x12), ([0, 3, 0x7F], 2, 0x40),
                               ([0x40, 0x80, 0x01], 1, 0x5B)):
        slook = Look()
        slook.pulse = pulse
        f = Frame()
        sound_page(f, slook, e, values, row)
        cases.append({"screen": "sound", "values": values, "row": row, "sel": row,
                      "pulse": pulse, "prims": [[d, p] for d, p in f.order()]})
    for i in range(30):
        st = {"values": [rng.randrange(0x81), rng.randrange(0x81), rng.randrange(0x81)], "row": 0}
        start = {"values": list(st["values"]), "row": 0}
        presses = [rng.choice((UP, DOWN, LEFT, RIGHT, 0x40)) for _ in range(rng.randrange(0, 30))]
        if rng.randrange(3):
            presses.append(0x20)
        used, left = 0, False
        for p in presses:
            used += 1
            if sound_press(st, p, 0x20):
                left = True
                break
        druns.append({"kind": "sound", "start": start, "presses": presses, "left": left,
                      "used": used, "end": st})
    cases.append({"screen": "display_runs", "runs": druns,
                  "looks": [[semi, bright, panel_look(semi, bright)]
                            for semi in (0, 1) for bright in (0x40, 0x80, 0x81, 0xA0, 0xC0)],
                  "sel": 0, "pulse": 0, "prims": []})
    # ui_ratings_page as the game's own code draws it, run over menu1's RAM by
    # tools/mipsrun.py -- when that snapshot is here
    menu1 = os.path.join(ROOT, "out", "snap", "menu1.ram")
    if os.path.exists(menu1):
        import mipsrun
        ram = open(menu1, "rb").read()
        # apply_control_scheme, the game's own, for every movement and action
        # scheme: the fourteen slots it leaves
        schemes = []
        for move in range(7):
            for action in range(4):
                cpu = mipsrun.menu_cpu(ram)
                cpu.ram[0x1B25E2], cpu.ram[0x1B25E3] = action, move
                cpu.call(0x8001F4C0)
                schemes.append({"move": move, "action": action,
                                "slots": [cpu.rd(0x80081868 + 2 * k, 2) for k in range(14)]})
        cases.append({"screen": "schemes", "schemes": schemes, "sel": 0, "pulse": 0,
                      "prims": []})
        for off, dfn, prims in mipsrun.ratings_cases(ram):
            cases.append({"screen": "ratings", "offense": off, "defense": dfn,
                          "sel": 0, "pulse": 0, "prims": [[d, p] for d, p in prims],
                          "look": "menu1"})
        for page, n in ((1, 2), (2, 2), (3, 5)):
            for sel, pulse, prims in mipsrun.page_cases(ram, page, n):
                cases.append({"screen": "page", "page": page, "n": n, "sel": sel,
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
    menus = options_check(out) and menus
    menus = display_check(out) and menus
    menus = sound_check(out) and menus
    menus = quit_check(out) and menus
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
