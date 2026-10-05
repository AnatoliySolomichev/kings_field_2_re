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
    rows, first, selected row, label length, names, counts -- in modes 1, 3
    and 5: mode 3 a second name 0x54 to the right of the first ("names2", 24
    bytes and an end), modes 1 and 5 the count "x N" at x + 0xe9."""
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


PROMPT_WORDS = {0: [0x14, 0x12, 0x04], 1: [0x12, 0x13, 0x0E, 0x11, 0x04]}   # use, store
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
