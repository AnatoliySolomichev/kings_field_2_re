#!/usr/bin/env python3
"""The screen's fade: screen_fade, the quad render_frame draws for it, and
fade_frames, which runs frames of the game while it changes.

    python3 tools/fade.py            the model against the game's own, run by run
    python3 tools/fade.py --check    the counts alone

**`screen_fade(mode, r, g, b)`** (`0x8003d624`) only keeps its four bytes at
`0x801aeafa..0x801aeafd`; `render_flags_reset` (`0x80034180`, second in
game_main's frame) puts the mode back to `0xff` every frame, so whoever
fades says so every frame. **`screen_fade_draw`** (`0x8003d568`, render_frame's
seventeenth call) draws nothing for a mode of `0xff`; otherwise one
POLY_FT4 over the whole screen through **`prim_ft4_rect`** (`0x8003ccfc`):

```
corners   (0, 0) (0x140, 0) (0, 0xf0) (0x140, 0xf0)
texture   u 0..0xf, v 0xa0..0xaf of the page at x 768 (tpage 0x0c), 4-bit,
          CLUT 0x7a8d (x 208, y 490) -- every texel index 0, CLUT[0]
          0xffff in every snapshot: white, with the STP bit
tpage     0x0c | (mode & 3) << 5 -- the blend: 0 half and half, 1 adding,
          2 taking away, 3 adding a quarter
colour    (r, g, b); the code 0x2e, semi-transparent
depth     1 with the mode's bit 0x80, else 0x40 -- over the panel or under it
```

so the GPU puts `(31 * c) >> 7` of white (each channel, held to 31) onto the
screen by the mode's blend: the death (`0x82`, 0..0xff over 0x20 frames,
player_controller) takes the screen down to black over everything, and the
warp (`1`) adds white under the panel until the screen is white.

**`fade_frames(mode, from, to, step)`** (`0x80046c00`): for s from `from`,
by `step`, to `to` inclusive, a frame -- screen_fade(mode, v, v, v) with
v = (s * s) >> 16 held to 0xff, res_upload_spu, res_upload_vram,
camera_pose and render_frame -- and nothing else of the game's frame: the
world stands while the screen changes. warp_to's (1, 0, 0x1000, 0x100) is
17 frames to white -- v 0, 1, 4, 9 .. 225, 0xff -- then (1, 0x1000, 0x1000,
0) one more on the new place, and (1, 0x1000, 0, -0x100) 17 back.

**How it is held to the game.** `check()` runs GAME.EXE's own
`screen_fade` and `screen_fade_draw` with `tools/mipsrun.py` after the
menus' `frame_begin` over every snapshot, every mode's four kinds of blend
with and without bit 0x80, `0xff`, and the colour at random, and reads the
ordering table back (`tools/gpuframe.py`): the quad, its corners, UVs, CLUT,
page, colour, code and depth must be the model's. And the game's own
`fade_frames` over a snapshot, the four routines it calls logged with the
screen bytes they find: warp_to's three calls and random others, every
frame's bytes the model's.
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

SCREEN = 0x801AEAFA            # mode, r, g, b
SCREEN_FADE = 0x8003D624
SCREEN_FADE_DRAW = 0x8003D568
FADE_FRAMES = 0x80046C00
RES_UPLOAD_SPU, RES_UPLOAD_VRAM = 0x80015A48, 0x80018CD0
CAMERA_POSE, RENDER_FRAME = 0x8002B330, 0x800422B8
OFF = 0xFF
CORNERS = [(0, 0), (0x140, 0), (0, 0xF0), (0x140, 0xF0)]
UVS = [(0, 0xA0), (0xF, 0xA0), (0, 0xAF), (0xF, 0xAF)]
CLUT = 0x7A8D
PAGE = 0x0C
TEXEL = 31                     # CLUT[0], 0xffff: white, the STP bit set
WARP_FADES = ((1, 0, 0x1000, 0x100), (1, 0x1000, 0x1000, 0), (1, 0x1000, 0, -0x100))


def prim(mode, r, g, b):
    """screen_fade_draw's quad for the bytes (mode, r, g, b), as tools/
    gpuframe.py reads a POLY_FT4 and the depth it is filed at -- or None."""
    if mode == OFF:
        return None
    return {"depth": 1 if mode & 0x80 else 0x40, "kind": "quad", "pts": list(CORNERS),
            "uvs": list(UVS), "clut": CLUT, "tpage": PAGE | (mode & 3) << 5,
            "rgb": r | g << 8 | b << 16, "semi": True}


def modulated(c):
    """What the GPU makes of the white texel under the colour c: (31 * c)
    >> 7, held to 31, in 5 bits."""
    return min(TEXEL, (TEXEL * c) >> 7)


def frames(mode, frm, to, step):
    """fade_frames' screen bytes, frame by frame."""
    out = []
    s = frm
    while True:
        v = min(OFF, (s * s) >> 16)
        out.append((mode & 0xFF, v, v, v))
        if s == to:
            return out
        s += step


def _quad(cpu):
    import gpuframe
    buf = cpu.ram[0x1AEAE8]                                  # draw_buffer_index
    got = [(d, p) for d, p in gpuframe.frame(cpu.ram, buf)
           if p["kind"] == "quad" and p.get("clut") == CLUT]
    if not got:
        return None
    d, p = got[-1]
    q = dict(p)
    q["depth"] = d
    q["pts"] = [tuple(t) for t in q["pts"]]
    q["uvs"] = [tuple(t) for t in q["uvs"]]
    return q


def prim_check(out=sys.stdout, per=40, seed=0xFADE):
    import memcard
    import mipsrun
    rng = random.Random(seed)
    modes = [0, 1, 2, 3, 0x80, 0x81, 0x82, 0x83, OFF]
    ok = n = 0
    first = None
    for path in memcard._snapshots():
        ram = open(path, "rb").read()
        for i in range(per):
            mode = modes[i % len(modes)]
            r, g, b = (rng.choice((0, 0xFF, rng.randrange(0x100))) for _ in range(3))
            prims, cpu = mipsrun.frame(ram, [(SCREEN_FADE, mode, r, g, b),
                                             (SCREEN_FADE_DRAW,)])
            got = _quad(cpu)
            want = prim(mode, r, g, b)
            n += 1
            if got == want:
                ok += 1
            elif first is None:
                first = f"{os.path.basename(path)} mode {mode:#x}: game {got} model {want}"
    print(f"  screen_fade_draw's quad, as the game's own screen_fade and "
          f"screen_fade_draw file it over every snapshot: {ok} of {n} -- corners, "
          f"UVs, CLUT, page and blend, colour, code and depth", file=out)
    if first:
        print(f"  first difference: {first}", file=out)
    return ok == n


def frames_check(out=sys.stdout, n=40, seed=0xF4DE):
    import mipsrun
    rng = random.Random(seed)
    ram = open(os.path.join(ROOT, "out", "snap", "a1.ram"), "rb").read()
    cases = list(WARP_FADES)
    while len(cases) < n:
        step = rng.choice((0x100, 0x80, 0x200, -0x100, -0x200))
        k = rng.randrange(1, 20)
        frm = rng.randrange(0, 0x1001) if step > 0 else rng.randrange(0x400, 0x2000)
        cases.append((rng.choice((1, 2, 0x82)), frm, frm + k * step, step))
    ok = got_frames = 0
    first = None
    for c in cases:
        cpu = mipsrun.CPU(ram)
        seen = []
        cpu.hooks[RENDER_FRAME] = lambda m: seen.append(tuple(m.rd(SCREEN + i, 1) for i in range(4)))
        for a in (RES_UPLOAD_SPU, RES_UPLOAD_VRAM, CAMERA_POSE):
            cpu.hooks[a] = lambda m: 0
        cpu.call(FADE_FRAMES, c[0], c[1] & 0xFFFFFFFF, c[2] & 0xFFFFFFFF, c[3] & 0xFFFFFFFF)
        want = frames(*c)
        got_frames += len(want)
        if seen == want:
            ok += 1
        elif first is None:
            first = f"fade_frames{c}: game {seen[:6]}.. model {want[:6]}.."
    print(f"  fade_frames, the game's own over a1: {ok} of {len(cases)} runs, "
          f"{got_frames} frames' screen bytes -- warp_to's three calls among them", file=out)
    if first:
        print(f"  first difference: {first}", file=out)
    return ok == len(cases)


def texture_check(out=sys.stdout):
    """The quad's texture in every snapshot's VRAM: each texel of u 0..0xf,
    v 0xa0..0xaf in the 4-bit page at x 768 is index 0, and CLUT[0] at
    (208, 490) is 0xffff -- white, with the STP bit that lets it blend. The
    snapshots of the game, as the other checks take them (memcard)."""
    import struct
    import memcard
    ok = n = 0
    for path in memcard._snapshots():
        vp = path[:-4] + ".vram"
        if not os.path.exists(vp):
            continue
        v = open(vp, "rb").read()
        px = lambda x, y: struct.unpack_from("<H", v, 2 * (y * 1024 + x))[0]   # noqa: E731
        idx = {(px(768 + u // 4, y) >> (4 * (u % 4))) & 0xF
               for u in range(16) for y in range(0xA0, 0xB0)}
        n += 1
        ok += idx == {0} and px(208, 490) == 0xFFFF
    print(f"  its texture, in every snapshot's VRAM: index 0 at every texel and "
          f"CLUT[0] 0xffff in {ok} of {n}", file=out)
    return ok == n


def check(out=sys.stdout):
    a = prim_check(out)
    b = frames_check(out)
    c = texture_check(out)
    return a and b and c


def export(out_dir):
    """fadecheck.json for godot/selftest.gd: fade_frames' bytes for warp_to's
    three calls and the death's, and the quad and the modulated colour for
    each mode."""
    import json
    rows = []
    for c in WARP_FADES + ((0x82, 0, 0x1000, 0x80),):
        rows.append({"args": list(c), "frames": [list(f) for f in frames(*c)]})
    quads = []
    for mode in (0, 1, 2, 3, 0x81, 0x82, OFF):
        for c in (0, 1, 4, 0x40, 0x80, 0x81, 0xFF):
            p = prim(mode, c, c, c)
            quads.append({"mode": mode, "c": c, "depth": p["depth"] if p else -1,
                          "blend": (mode & 3) if p else -1, "five": modulated(c)})
    path = os.path.join(out_dir, "fadecheck.json")
    with open(path, "w") as fh:
        json.dump({"frames": rows, "quads": quads}, fh, separators=(",", ":"))
    return path


if __name__ == "__main__":
    sys.exit(0 if check() else 1)
