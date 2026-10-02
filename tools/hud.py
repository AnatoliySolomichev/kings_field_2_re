#!/usr/bin/env python3
"""The panel in the top-left corner: HP and MP, and the two meters under them.

    python3 tools/hud.py            the sprite table, and the check
    python3 tools/hud.py --check    the formulas against every snapshot's RAM
    python3 tools/hud.py --godot    hud.json and the page's pictures for the port

It is thirty sprites in a table of GAME.EXE, `hud_sprites` at `0x800819b4`,
0x14 bytes each and ended by 0xff:

    +0    on       rewritten by render_frame every frame
    +1    abr      the blend: SetDrawTPage(tpage | (abr & 3) << 5), unless 0xff
    +2,3  u, v     in the page
    +4,5  w, h
    +6,8  x, y     on the 320x240 screen, s16
    +0xe  clut
    +0x10 tpage    0x1e -- the 4-bit page at (896, 256), which entry 96 loads
    +0x12 depth    the ordering-table index, 24 to 40: in front of the world

`sub_80041e68` (`0x80041e68`), called by `render_frame` between the compass and
the terrain, walks it and hands every record whose +0 is set to
`sub_80041ad4`, which builds a SPRT (code 0x64, semi-transparent) coloured by
the brightness byte at `0x801b25e1` three times, and a DR_TPAGE before it.

`render_frame` switches the table by the style byte at `0x801b25dd` -- records
0 to 12 on its bit 0, 15 to 29 on its bit 1, 13 and 14 never -- and writes the
numbers into it, so **the live table in RAM is the game's own answer** and the
check below reads it back. `render_frame_bare` (`0x80030568`), which the menus, the conversations
and `object_interact` call, draws a frame with the style and the compass's
both set to 0 and puts them back after: the panel is gone while they are up.

    style 2   (new_character's default, sub_8002b64c; the options can change it)
      records 17-19  u = 12 * digit + 128 of HP % 1000: hundreds, tens, ones
      records 22-24  the same of MP
      record 25      w = weapon_meter * 64 / 5000   (0x801b2502)
      record 26      w = magic_meter * 64 / 5000    (0x801b2506)
    style 1
      record 4       w = 48 * HP / HP max           (0x801b24fc, 0x801b24fa)
      record 5       w = weapon_meter * 48 / 5000
      record 6       w = 48 * MP / MP max           (0x801b2500, 0x801b24fe)
      record 7       w = magic_meter * 48 / 5000

The division by 5000 is a multiply by 0x68db8bad and a shift of 43; each
width is also written into the record's +0xa, which nothing draws from.
"""
import glob
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SPRITES = 0x800819B4
STRIDE = 0x14
HP, HP_MAX, MP, MP_MAX = 0x801B24FC, 0x801B24FA, 0x801B2500, 0x801B24FE
WEAPON, MAGIC = 0x801B2502, 0x801B2506
STYLE, BRIGHT = 0x801B25DD, 0x801B25E1
DIV5000 = 0x68DB8BAD            # the multiply-high render_frame divides by
ROWS_STYLE1 = range(0, 13)
ROWS_STYLE2 = range(15, 30)


def parse(raw):
    """[sprite] out of the table's bytes, up to the 0xff that ends it."""
    out = []
    for k in range(64):
        rec = raw[k * STRIDE:(k + 1) * STRIDE]
        if len(rec) < STRIDE or rec[0] == 0xFF:
            break
        x, y = struct.unpack_from("<hh", rec, 6)
        clut, tpage, depth = struct.unpack_from("<HHh", rec, 0xE)
        out.append({"index": k, "on": rec[0], "abr": rec[1], "u": rec[2],
                    "v": rec[3], "w": rec[4], "h": rec[5], "x": x, "y": y,
                    "clut": clut, "tpage": tpage, "depth": depth,
                    "a": struct.unpack_from("<H", rec, 0xA)[0]})
    return out


def sprites():
    """The table as GAME.EXE holds it."""
    import disasm
    base, _entry, text = disasm.load_text()
    return parse(text[SPRITES - base:SPRITES - base + 64 * STRIDE])


def _over5000(v, k):
    """(v * k) / 5000 the way render_frame gets it: mult by 0x68db8bad, hi >> 11."""
    return ((v * k * DIV5000) >> 32) >> 11


def style2(hp, mp, weapon, magic):
    """{record: {field: value}} render_frame writes for style 2."""
    out = {}
    for first, v in ((17, hp), (22, mp)):
        v %= 1000
        for i, d in enumerate((v // 100, v % 100 // 10, v % 10)):
            out[first + i] = {"u": (12 * d - 0x80) & 0xFF}
    for rec, meter in ((25, weapon), (26, magic)):
        w = _over5000(meter, 64)
        out[rec] = {"w": w & 0xFF, "a": w & 0xFF}
    return out


def style1(hp, hp_max, mp, mp_max, weapon, magic):
    """{record: {field: value}} render_frame writes for style 1."""
    out = {}
    for rec, v, vmax in ((4, hp, hp_max), (6, mp, mp_max)):
        w = (48 * v) // vmax if vmax else 0
        out[rec] = {"w": w & 0xFF, "a": w & 0xFF}
    for rec, meter in ((5, weapon), (7, magic)):
        w = _over5000(meter, 48)
        out[rec] = {"w": w & 0xFF, "a": w & 0xFF}
    return out


def _ram(r, a, n=2):
    return struct.unpack_from("<H" if n == 2 else "<B", r, a & 0x1FFFFF)[0]


def check(out=sys.stdout):
    """The formulas against the table each snapshot's RAM holds."""
    ok = bad = snaps = bare = 0
    for path in sorted(glob.glob(os.path.join(ROOT, "out", "snap", "*.ram"))):
        r = open(path, "rb").read()
        style = r[STYLE & 0x1FFFFF]
        if style not in (1, 2):
            continue
        snaps += 1
        live = parse(r[SPRITES & 0x1FFFFF:(SPRITES & 0x1FFFFF) + 64 * STRIDE])
        # A frame drawn by render_frame_bare (0x80030568) -- the menus, a conversation, a find --
        # had the style at 0 while render_frame ran and put it back after, so
        # its table has every sprite off and the numbers still in.
        if not any(x["on"] for x in live):
            style = 0
            bare += 1
        want = (style2(_ram(r, HP), _ram(r, MP), _ram(r, WEAPON), _ram(r, MAGIC))
                if r[STYLE & 0x1FFFFF] == 2 else
                style1(_ram(r, HP), _ram(r, HP_MAX), _ram(r, MP), _ram(r, MP_MAX),
                       _ram(r, WEAPON), _ram(r, MAGIC)))
        on = {2: ROWS_STYLE2, 1: ROWS_STYLE1}.get(style, ())
        for s in live:
            fields = dict(want.get(s["index"], {}))
            fields["on"] = 1 if s["index"] in on else 0
            for f, v in fields.items():
                if s[f] == v:
                    ok += 1
                else:
                    bad += 1
                    print(f"  {os.path.basename(path)} record {s['index']} {f}: "
                          f"RAM {s[f]}, model {v}", file=out)
    print(f"  {ok} of {ok + bad} fields of the live sprite table reproduced "
          f"over {snaps} snapshots, {bare} of them drawn bare by render_frame_bare",
          file=out)
    return bad == 0 and snaps > 0


def export(out_dir):
    """hud.json, and the page under each CLUT the table uses, split in two.

    A semi-transparent primitive blends only the texels whose colour has STP
    (bit 15) set; the rest are drawn solid and colour 0 not at all. So each
    (clut, rate) gives a `_solid` picture, the STP texels cleared, and a
    `_semi` one holding only those, with the rate's alpha -- the port draws
    the first plainly and the second with the blend.
    """
    import rtim
    import tim
    table = sprites()
    vram = rtim.level_vram(0)          # entry 96 alone would do; this is it
    os.makedirs(os.path.join(out_dir, "hud"), exist_ok=True)
    made = set()
    for s in table:
        rate = (s["abr"] & 3) if s["abr"] != 0xFF else 0
        tp = s["tpage"] | (rate << 5)
        key = (s["clut"], rate)
        s["png"] = f"hud/hud_{s['clut']:04x}_{rate}"
        if key in made:
            continue
        made.add(key)
        # Which texels carry STP: under rate 0 page4 gives them alpha 128.
        stp = [q[3] == 128 for q in rtim.page4(vram, s["tpage"] & ~0x60,
                                                s["clut"], semi=True)]
        plain = rtim.page4(vram, tp, s["clut"], semi=False)
        semi = rtim.page4(vram, tp, s["clut"], semi=True)
        clear = (0, 0, 0, 0)
        solid = [clear if t else p for p, t in zip(plain, stp)]
        blend = [q if t else clear for q, t in zip(semi, stp)]
        tim.write_png(os.path.join(out_dir, s["png"] + "_solid.png"), 256, 256, solid)
        tim.write_png(os.path.join(out_dir, s["png"] + "_semi.png"), 256, 256, blend)
    doc = {"_note": "hud_sprites (0x800819b4): the panel's sprites, drawn by "
                    "sub_80041ad4 on a 320x240 screen; see tools/hud.py",
           "sprites": table,
           "style1": list(ROWS_STYLE1), "style2": list(ROWS_STYLE2)}
    path = os.path.join(out_dir, "hud.json")
    with open(path, "w") as f:
        json.dump(doc, f, separators=(",", ":"))
    export_messages(out_dir)
    return path


MESSAGES = 0x80081928        # message_tick's six sprites, ended by 0xff
MESSAGE_PAGE, MESSAGE_CLUT = 0x1A, 0x7804


def export_messages(out_dir):
    """messages.json and msgpage.png for godot/messages.gd: the six sprite
    records `message_draw` (`0x80041d9c`) draws the banners with, out of GAME.EXE, and the
    4-bit page at (640, 256) they cut the words from -- 36 pictures 127 x 14,
    eighteen to a column, and the digits at v 238 -- under CLUT (64, 480).
    Every texel but colour 0 has STP set, so the picture keeps its colours and
    the port blends all of it, as the game does."""
    import mips
    import rtim
    import tim
    raw = mips.load("game").bytes(MESSAGES, STRIDE * 8)
    table = parse(raw)
    vram = rtim.level_vram(0)
    px = rtim.page4(vram, MESSAGE_PAGE, MESSAGE_CLUT, semi=False)
    tim.write_png(os.path.join(out_dir, "msgpage.png"), 256, 256, px)
    doc = {"_note": "message_tick's sprites at 0x80081928 and the page they "
                    "draw from; tools/hud.py export_messages",
           "png": "msgpage.png", "sprites": table}
    path = os.path.join(out_dir, "messages.json")
    with open(path, "w") as f:
        json.dump(doc, f, separators=(",", ":"))
    return path


def main():
    a = sys.argv[1] if len(sys.argv) > 1 else None
    if a == "--check":
        sys.exit(0 if check() else 1)
    if a == "--godot":
        print(export(os.path.join(ROOT, "out", "godot")))
        return
    print(__doc__)
    for s in sprites():
        print(f"  {s['index']:2d} abr {s['abr']:#04x} uv ({s['u']:3d},{s['v']:3d}) "
              f"{s['w']:2d}x{s['h']:<2d} at ({s['x']:3d},{s['y']:3d}) "
              f"clut {s['clut']:#06x} depth {s['depth']}")
    check()


if __name__ == "__main__":
    main()
